"""Regression tests for the 2026-11-21 code audit (docs/audit-2026-11-21/README.md).

Each test reproduces one finding that the previous code got wrong.
"""

import asyncio
import math
import random
import sys
import types
import warnings
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda
from pipeline_fixtures import framework_fixture

from tunarag import (
    Candidate,
    CostBudget,
    DatasetError,
    EvaluationDataset,
    InMemoryDataset,
    IntegerRange,
    LangChainAdapter,
    MaxFailures,
    MaxTrials,
    MetricEvaluator,
    MetricValue,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RagasEvaluator,
    RandomSearch,
    RetryPolicy,
    SearchSpace,
    Settings,
    SourceDocument,
    SQLiteStore,
    StopContext,
    StudyStatus,
    SyntheticDatasetBuilder,
    SyntheticGenerationRequest,
    SyntheticGenerationResponse,
    SyntheticQA,
    TrialStatus,
    UsageRecord,
    ValueStatus,
)
from tunarag.engine import _active_seconds
from tunarag.integrations import MLflowCallback
from tunarag.result import summarize_usage
from tunarag.serialization import content_hash
from tunarag.store import StudyEvent

DATA = InMemoryDataset((1, 2), version="audit-v1")


class ScoreEvaluator:
    def __init__(self, value: float) -> None:
        self.value = value

    async def evaluate(self, output: Any, example: Any) -> Sequence[MetricValue]:
        del output, example
        return (MetricValue("score", self.value),)

    def fingerprint(self) -> Any:
        return {"score": "fixed"}


class EchoAdapter:
    def __init__(self, usage: Sequence[UsageRecord] = (), delay: float = 0.0) -> None:
        self.usage = tuple(usage)
        self.delay = delay

    async def run(self, candidate: Candidate, example: Any) -> tuple[Any, Sequence[UsageRecord]]:
        if self.delay and example == 2:
            await asyncio.sleep(self.delay)
        return example, self.usage


def optimizer(adapter: Any, evaluator: Any, *, stops: Any = None, policy: Any = None) -> Optimizer:
    return Optimizer(
        adapter=framework_fixture(adapter),
        strategy=RandomSearch(SearchSpace({"k": IntegerRange(1, 3)}), seed=1),
        evaluators=[evaluator],
        objective=Objective((ObjectiveTerm("score"),)),
        settings=Settings.resolve(overrides={"concurrency": 1}, environ={}),
        stop_conditions=stops or (MaxTrials(3),),
        retry_policy=policy or RetryPolicy(max_retries=0),
    )


# H-1 ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", [math.nan, math.inf])
def test_non_finite_metric_fails_only_its_trial(value: float) -> None:
    result = asyncio.run(
        optimizer(EchoAdapter(), ScoreEvaluator(value)).aoptimize(DATA, study_name="nan")
    )

    assert result.study_status is StudyStatus.COMPLETED
    assert [trial.status for trial in result.trials] == [TrialStatus.FAILED] * 3


def test_non_finite_cost_fails_only_its_trial() -> None:
    adapter = LangChainAdapter(
        RunnableLambda(lambda inputs: {"answer": 1}),
        usage_mapper=lambda output: [UsageRecord("llm", cost=math.nan)],
        identity={"audit": "nan-cost"},
    )
    built = Optimizer(
        adapter=adapter,
        strategy=RandomSearch(SearchSpace({"k": IntegerRange(1, 2)}), seed=1),
        evaluators=[ScoreEvaluator(1.0)],
        objective=Objective((ObjectiveTerm("score"),)),
        stop_conditions=(MaxTrials(2),),
        retry_policy=RetryPolicy(max_retries=0),
    )
    result = asyncio.run(built.aoptimize(DATA, study_name="nan-cost"))

    assert result.study_status is StudyStatus.COMPLETED
    assert all(trial.status is TrialStatus.FAILED for trial in result.trials)


# H-3 ---------------------------------------------------------------------------------------
def test_string_output_chain_still_reports_model_token_usage() -> None:
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    def model() -> GenericFakeChatModel:
        reply = AIMessage(
            content="SQLite",
            usage_metadata={"input_tokens": 11, "output_tokens": 3, "total_tokens": 14},
            response_metadata={"model_name": "audit-model"},
        )
        return GenericFakeChatModel(messages=iter([reply]))

    chain = (
        ChatPromptTemplate.from_template("Q: {question}")
        | RunnableLambda(lambda prompt: prompt)
        | RunnableLambda(lambda prompt: model().invoke(prompt))
        | StrOutputParser()
    )
    adapter = LangChainAdapter(
        chain, token_prices={"audit-model": (1.0, 2.0)}, identity={"audit": "usage"}
    )

    output, usage = asyncio.run(adapter.run(Candidate({"k": 1}), {"question": "where?"}))

    assert output == "SQLite"
    model_usage = [item for item in usage if item.input_tokens]
    assert model_usage, "string-output chain lost its token usage"
    assert model_usage[0].component == "langchain.message"
    assert (model_usage[0].input_tokens, model_usage[0].output_tokens) == (11, 3)
    assert model_usage[0].cost == pytest.approx((11 * 1.0 + 3 * 2.0) / 1_000_000)
    assert model_usage[0].status is ValueStatus.ESTIMATED


def test_unknown_cost_is_unavailable_not_exact_zero() -> None:
    unpriced = summarize_usage(
        (UsageRecord("model", input_tokens=10), UsageRecord("run", latency_seconds=1.0))
    )
    priced = summarize_usage((UsageRecord("model", input_tokens=10, cost=0.2),))
    partial = summarize_usage(
        (UsageRecord("a", input_tokens=1, cost=0.1), UsageRecord("b", input_tokens=1))
    )

    assert unpriced.status is ValueStatus.UNAVAILABLE and unpriced.exact_cost == 0.0
    assert priced.status is ValueStatus.EXACT and priced.exact_cost == pytest.approx(0.2)
    assert partial.status is ValueStatus.ESTIMATED


def test_trial_timeout_keeps_usage_already_spent_and_budget_counts_it() -> None:
    adapter = EchoAdapter(usage=[UsageRecord("llm", cost=1.0)], delay=5.0)
    built = optimizer(
        adapter,
        ScoreEvaluator(1.0),
        stops=(MaxTrials(3), CostBudget(1.5)),
        policy=RetryPolicy(max_retries=0, trial_timeout_seconds=0.3, sample_timeout_seconds=10),
    )

    result = asyncio.run(built.aoptimize(DATA, study_name="timeout-usage"))

    assert result.trials[0].status is TrialStatus.FAILED
    assert result.trials[0].usage and result.usage.exact_cost >= 1.0
    assert result.stop_reason == "CostBudget"
    assert len(result.trials) == 2  # $1 per timed-out trial; the $1.5 budget stops after two


# H-4 ---------------------------------------------------------------------------------------
def _provider_error(name: str, **attributes: Any) -> Exception:
    error_type = type(name, (Exception,), {})
    error = error_type("provider failure")
    for key, value in attributes.items():
        setattr(error, key, value)
    return error


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (_provider_error("APITimeoutError"), True),
        (_provider_error("APIConnectionError"), True),
        (_provider_error("RateLimitError", status_code=429), True),
        (_provider_error("SomeServerError", status_code=503), True),
        (_provider_error("ConnectTimeout"), False),
        (_provider_error("BadRequestError", status_code=400), False),
        (_provider_error("ValueError"), False),
    ],
)
def test_provider_errors_are_classified_for_retry(error: Exception, retryable: bool) -> None:
    assert RetryPolicy().is_retryable(error) is retryable


def test_wrapped_transient_cause_is_retryable() -> None:
    from tunarag import EvaluationError

    try:
        try:
            raise _provider_error("RateLimitError", status_code=429)
        except Exception as cause:
            raise EvaluationError("RAGAS evaluation failed", stage="evaluation") from cause
    except EvaluationError as wrapped:
        assert RetryPolicy().is_retryable(wrapped)


# H-5 ---------------------------------------------------------------------------------------
def test_different_lambda_scorers_have_different_identities() -> None:
    low = MetricEvaluator("score", lambda output, example: 0.1)
    high = MetricEvaluator("score", lambda output, example: 0.9)

    assert content_hash(low.fingerprint()) != content_hash(high.fingerprint())
    assert content_hash(MetricEvaluator("score", lambda o, e: 0.1, identity=2).fingerprint()) != (
        content_hash(MetricEvaluator("score", lambda o, e: 0.1, identity=3).fingerprint())
    )


def test_identical_lambdas_keep_identity_regardless_of_surrounding_code() -> None:
    first = MetricEvaluator("score", lambda output, example: 1.0)
    second = MetricEvaluator(
        "score",
        lambda output, example: 1.0,
    )

    # Resume and the cache must not break because the enclosing line was edited.
    assert content_hash(first.fingerprint()) == content_hash(second.fingerprint())


def test_explicit_identity_ignores_run_varying_closure_state() -> None:
    def build(mode: str) -> LangChainAdapter:
        def invoke(inputs: Any) -> Any:  # closes over `mode`, which differs between runs
            return {"answer": mode}

        return LangChainAdapter(RunnableLambda(invoke), identity={"pipeline": "v1"})

    # A crashed run and its resume differ only in process state; resume must still match.
    assert content_hash(build("crash").fingerprint()) == content_hash(build("resume").fingerprint())


def test_different_pipelines_without_identity_do_not_share_cache_keys() -> None:
    with pytest.warns(UserWarning, match="identity"):
        right = LangChainAdapter(RunnableLambda(lambda inputs: {"answer": "right"}))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wrong = LangChainAdapter(RunnableLambda(lambda inputs: {"answer": "wrong"}))

    assert content_hash(right.fingerprint()) != content_hash(wrong.fingerprint())


# H-6 ---------------------------------------------------------------------------------------
def test_ragas_concurrent_samples_do_not_strip_each_others_judge(monkeypatch) -> None:
    class Metric:
        llm: Any = None

    async def aevaluate(*, dataset: Any, metrics: list[Any], llm: Any, **kwargs: Any) -> Any:
        changed = [metric for metric in metrics if metric.llm is None]
        for metric in changed:
            metric.llm = llm
        try:
            await asyncio.sleep(random.uniform(0, 0.02))
            if any(metric.llm is None for metric in metrics):
                return SimpleNamespace(scores=[{"faithfulness": math.nan}])
            return SimpleNamespace(scores=[{"faithfulness": 1.0}])
        finally:  # what RAGAS does: detach the judge from metrics it attached it to
            for metric in changed:
                metric.llm = None

    ragas = types.ModuleType("ragas")
    ragas.EvaluationDataset = lambda samples: samples
    ragas.aevaluate = aevaluate
    schema = types.ModuleType("ragas.dataset_schema")
    schema.SingleTurnSample = lambda **data: data
    monkeypatch.setitem(sys.modules, "ragas", ragas)
    monkeypatch.setitem(sys.modules, "ragas.dataset_schema", schema)
    evaluator = RagasEvaluator((Metric(),), lambda output, example: {"response": "x"}, llm="judge")

    async def staggered(index: int) -> Any:
        await asyncio.sleep(index * 0.005)
        return (await evaluator.evaluate("output", index))[0].value

    async def run_all() -> list[Any]:
        return await asyncio.gather(*(staggered(index) for index in range(30)))

    assert asyncio.run(run_all()) == [1.0] * 30


def test_objective_marks_partial_coverage_and_enforces_min_coverage() -> None:
    partial = (MetricValue("faithfulness", 0.9, coverage=0.5),)

    assert (
        Objective((ObjectiveTerm("faithfulness"),)).evaluate(partial).status
        is ValueStatus.ESTIMATED
    )
    strict = Objective((ObjectiveTerm("faithfulness", min_coverage=1.0),)).evaluate(partial)
    assert strict.score is None and strict.status is ValueStatus.UNAVAILABLE


# M-1 ---------------------------------------------------------------------------------------
def test_adk_default_output_exposes_tool_responses() -> None:
    pytest.importorskip("google.adk")
    from google.adk.agents import BaseAgent
    from google.adk.events import Event
    from google.adk.runners import InMemoryRunner
    from google.genai import types as genai

    from tunarag import GoogleADKAdapter

    class RetrievingAgent(BaseAgent):
        async def _run_async_impl(self, ctx: Any):
            yield Event(
                author=self.name,
                content=genai.Content(
                    role="user",
                    parts=[
                        genai.Part.from_function_response(
                            name="search", response={"passages": ["returns within 45 days"]}
                        )
                    ],
                ),
            )
            yield Event(
                author=self.name,
                content=genai.Content(role="model", parts=[genai.Part.from_text(text="45 days")]),
            )

    async def exercise() -> Any:
        runner = InMemoryRunner(agent=RetrievingAgent(name="rag"), app_name="audit")
        try:
            adapter = GoogleADKAdapter(runner, identity={"audit": "evidence"})
            output, _usage = await adapter.run(Candidate({"k": 1}), "how long?")
            return output
        finally:
            await runner.close()

    output = asyncio.run(exercise())
    assert output["answer"] == "45 days"
    assert output["tool_responses"] == [
        {"name": "search", "response": {"passages": ["returns within 45 days"]}}
    ]


# M-2 ---------------------------------------------------------------------------------------
def test_mlflow_reuses_the_studys_existing_run(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "mlflow.sqlite")
    study = store.create_study("mirror", {"version": 1})
    store.transition_study(study.id, StudyStatus.RUNNING)
    event = store.append_event(study.id, "study.resumed", {})

    class Client:
        def __init__(self) -> None:
            self.created = 0
            self.updated: list[tuple[str, str]] = []

        def search_runs(self, experiment_ids: Any, *, filter_string: str, **kwargs: Any) -> Any:
            assert study.id in filter_string
            return [SimpleNamespace(info=SimpleNamespace(run_id="existing"))]

        def create_run(self, *args: Any, **kwargs: Any) -> Any:
            self.created += 1

        def update_run(self, run_id: str, *, status: str) -> None:
            self.updated.append((run_id, status))

        def set_tag(self, *args: Any) -> None:
            pass

    client = Client()
    asyncio.run(MLflowCallback(store, client=client).on_event(event))

    assert client.created == 0
    assert client.updated == [("existing", "RUNNING")]
    store.close()


# M-3 ---------------------------------------------------------------------------------------
class EvenInteger:  # verbatim shape from the README "Extension contracts" section
    def __init__(self, minimum: int, maximum: int) -> None:
        self.minimum = minimum
        self.maximum = maximum

    def sample(self, generator: Any) -> int:
        return generator.choice(tuple(range(self.minimum + self.minimum % 2, self.maximum + 1, 2)))

    def accepts(self, value: Any) -> bool:
        return isinstance(value, int) and self.minimum <= value <= self.maximum and value % 2 == 0

    def describe(self) -> Any:
        return {
            "type": "integer",
            "minimum": self.minimum,
            "maximum": self.maximum,
            "multiple_of": 2,
        }


def test_readme_custom_parameter_works_with_the_optimizer() -> None:
    built = Optimizer(
        adapter=framework_fixture(EchoAdapter()),
        strategy=RandomSearch(SearchSpace({"chunk": EvenInteger(2, 10)}), seed=1),
        evaluators=[ScoreEvaluator(1.0)],
        objective=Objective((ObjectiveTerm("score"),)),
        stop_conditions=(MaxTrials(2),),
    )

    result = asyncio.run(built.aoptimize(DATA, study_name="even"))

    assert result.study_status is StudyStatus.COMPLETED
    assert all(trial.candidate.parameters["chunk"] % 2 == 0 for trial in result.trials)


# L-1, L-2, L-4, L-6, L-7 -------------------------------------------------------------------
def test_active_time_spans_resumed_segments_but_not_downtime() -> None:
    def event(sequence: int, kind: str, at: str) -> StudyEvent:
        return StudyEvent("s", sequence, kind, {}, f"2026-11-21 10:{at}")

    events = [
        event(0, "study.running", "00:00"),
        event(1, "trial.succeeded", "00:30"),  # 30 s of work, then the process is killed
        event(2, "study.running", "10:00"),  # resumed ~10 minutes later
        event(3, "study.resumed", "10:00"),
        event(4, "trial.succeeded", "10:20"),
    ]

    assert _active_seconds(events) == pytest.approx(50.0)


def test_dataset_version_ignores_row_order() -> None:
    rows = [{"id": "1", "query": "x"}, {"id": "2", "query": "y"}]

    assert (
        EvaluationDataset.from_records(rows).version
        == EvaluationDataset.from_records(list(reversed(rows))).version
    )


def test_synthetic_generation_can_keep_successful_documents() -> None:
    class Provider:
        async def generate(
            self, request: SyntheticGenerationRequest
        ) -> SyntheticGenerationResponse:
            if request.document.id == "bad":
                raise RuntimeError("provider failure")
            return SyntheticGenerationResponse((SyntheticQA("q?", "a"),))

    documents = (SourceDocument("good", "text"), SourceDocument("bad", "text"))
    with pytest.raises(DatasetError, match="1 of 2"):
        asyncio.run(SyntheticDatasetBuilder(Provider(), samples_per_document=1).generate(documents))

    partial = asyncio.run(
        SyntheticDatasetBuilder(Provider(), samples_per_document=1, allow_partial=True).generate(
            documents
        )
    )
    assert len(partial.dataset.examples) == 1
    assert partial.failed_document_ids == ("bad",)


def test_consecutive_failures_ignore_cancelled_trials() -> None:
    context = StopContext(
        completed_trials=3,
        failed_trials=1,
        objective_scores=(None, None, None),
        failure_history=(True, False, False),  # one failure, then two cancelled trials
    )

    assert not MaxFailures(2, consecutive=True).should_stop(context)


def test_float_and_string_candidates_hash_differently() -> None:
    assert content_hash({"x": 0.5}) != content_hash({"x": "0.5"})
