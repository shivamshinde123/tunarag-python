import asyncio
import json
import math
from pathlib import Path

import pytest

from tunarag import (
    Candidate,
    LLMSearch,
    MetricEvaluator,
    Objective,
    ObjectiveDirection,
    ObjectiveTerm,
    Optimizer,
    RagasEvaluator,
    RandomSearch,
    ResumeError,
    RetryPolicy,
    Settings,
    SQLiteCache,
    SQLiteStore,
    ValueStatus,
)

from .campaign import (
    ChatSuggestionProvider,
    PipelineBuilder,
    page_recall,
    question_sets,
    search_space,
    term_coverage,
)
from .test_provider import sample_mapper

pytestmark = [pytest.mark.live, pytest.mark.paid, pytest.mark.campaign]


@pytest.mark.parametrize("framework", ["langchain", "langgraph"])
@pytest.mark.parametrize("strategy_name", ["random", "llm"])
def test_full_pdf_campaign(
    framework, strategy_name, provider, pytestconfig, tracking_server, tmp_path
):
    from langchain_community.document_loaders import PyPDFLoader
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextRecall

    from tunarag.integrations import MLflowCallback
    from tunarag.serialization import content_hash

    pdf = pytestconfig.getoption("--live-pdf")
    assert provider["chat"].model_name == "openai/gpt-4.1-mini", (
        "Verify cost rates before changing the campaign model"
    )
    if not pdf or not Path(pdf).is_file():
        pytest.fail("--live-pdf must name the Attention Is All You Need PDF", pytrace=False)
    documents = PyPDFLoader(pdf).load()
    assert len(documents) >= 8
    assert "Attention Is All You Need" in documents[0].page_content
    assert "4000" in documents[6].page_content
    development, held_out = question_sets()
    builder = PipelineBuilder(documents, provider, framework, tmp_path)
    store = SQLiteStore(tmp_path / "study.db")
    cache = SQLiteCache(tmp_path / "cache.db")
    client, uri = tracking_server
    experiment = client.create_experiment(f"campaign-{framework}-{strategy_name}")
    suggestion_provider = ChatSuggestionProvider(provider["chat"])
    objective = Objective(
        (
            ObjectiveTerm("answer_terms", weight=0.6, minimum=0, maximum=1),
            ObjectiveTerm("page_recall", weight=0.25, minimum=0, maximum=1),
            ObjectiveTerm(
                "generation_cost_estimate",
                weight=0.1,
                direction=ObjectiveDirection.MINIMIZE,
                minimum=0,
                maximum=0.01,
            ),
            ObjectiveTerm(
                "latency", weight=0.05, direction=ObjectiveDirection.MINIMIZE, minimum=0, maximum=45
            ),
        )
    )
    evaluators = (
        MetricEvaluator("answer_terms", term_coverage),
        MetricEvaluator("page_recall", page_recall),
        MetricEvaluator(
            "generation_cost_estimate",
            lambda output, example: output["generation_cost_estimate"],
            status=ValueStatus.ESTIMATED,
        ),
        MetricEvaluator("latency", lambda output, example: output["latency_seconds"]),
    )

    def optimizer(revision=1):
        strategy = (
            RandomSearch(search_space(), seed=17)
            if strategy_name == "random"
            else LLMSearch(
                search_space(), suggestion_provider, max_suggestion_attempts=2, fallback_seed=17
            )
        )
        return Optimizer(
            adapter=builder.adapter(revision),
            strategy=strategy,
            evaluators=evaluators,
            objective=objective,
            store=store,
            cache=cache,
            settings=Settings.resolve(
                overrides={"max_trials": 4, "concurrency": 2, "sample_concurrency": 2}, environ={}
            ),
            retry_policy=RetryPolicy(
                max_retries=0, sample_timeout_seconds=180, trial_timeout_seconds=600
            ),
            callbacks=(MLflowCallback(store, tracking_uri=uri, experiment_id=experiment),),
        )

    runner = optimizer()
    try:
        result = runner.optimize(development, study_name=f"{framework}-{strategy_name}")
        assert len(result.successful_trials) == 4 and not result.failed_trials
        assert result.best_trial.objective.score == max(
            item.objective.score for item in result.successful_trials
        )
        assert len({content_hash(item.candidate.parameters) for item in result.trials}) == 4
        assert (
            sum(
                len({item.candidate.parameters[name] for item in result.trials}) > 1
                for name in search_space().describe()
            )
            >= 2
        )
        assert all(any(item.input_tokens for item in trial.usage) for trial in result.trials)
        assert all(
            objective.evaluate(trial.metrics).score == trial.objective.score
            for trial in result.trials
        )
        if strategy_name == "llm":
            assert suggestion_provider.valid >= 4
            assert all(
                "query" not in json.dumps(item) and "reference_answer" not in json.dumps(item)
                for item in suggestion_provider.requests
            )
        requests_before = provider["budget"].used
        runner.close()
        runner = optimizer()
        reloaded = runner.resume(development, study_id=result.study_id)
        assert reloaded.best_candidate == result.best_candidate
        assert provider["budget"].used == requests_before
        incompatible = optimizer(revision=2)
        try:
            with pytest.raises(ResumeError, match="incompatible"):
                incompatible.resume(development, study_id=result.study_id)
        finally:
            incompatible.close()
        assert provider["budget"].used == requests_before
        assert not any(
            event.type == "callback.failed" for event in store.list_events(result.study_id)
        )
        runs = client.search_runs([experiment])
        assert len(runs) == 1 and runs[0].info.status == "FINISHED"
        history = client.get_metric_history(runs[0].info.run_id, "answer_terms")
        assert {(entry.step, entry.value) for entry in history} == {
            (trial.sequence, trial.metric("answer_terms").value) for trial in result.trials
        }
        result.write_json(tmp_path / "result.json")
        result.write_csv(tmp_path / "trials.csv")
        parameters = dict(result.best_candidate.parameters)
        (tmp_path / "winning-config.json").write_text(
            json.dumps(parameters, indent=2), encoding="utf-8"
        )
        winner = Candidate(json.loads((tmp_path / "winning-config.json").read_text()))
        baseline = Candidate(
            {
                "top_k": 1,
                "chunk_size": 500,
                "overlap": 0,
                "search_type": "similarity",
                "prompt_style": "brief",
            }
        )
        judge = RagasEvaluator(
            [
                Faithfulness(llm=LangchainLLMWrapper(provider["judge"])),
                LLMContextRecall(llm=LangchainLLMWrapper(provider["judge"])),
            ],
            sample_mapper,
            raise_exceptions=True,
        )

        async def validate():
            rows = []
            for label, candidate in (("baseline", baseline), ("winner", winner)):
                for example in held_out.examples:
                    output = await builder.independent_run(candidate, example)
                    row = {
                        "configuration": label,
                        "example_id": example.id,
                        "query": example.query,
                        "reference_answer": example.reference_answer,
                        "source_pages": list(example.relevant_document_ids),
                        "output": output,
                        "answer_terms": term_coverage(output, example),
                        "page_recall": page_recall(output, example),
                    }
                    if example.id in ("h1", "h4"):
                        for metric in await judge.evaluate(output, example):
                            assert (
                                metric.value is not None
                                and math.isfinite(metric.value)
                                and 0 <= metric.value <= 1
                            )
                            row[metric.name] = metric.value
                    rows.append(row)
                    (tmp_path / "held-out.json").write_text(
                        json.dumps(rows, indent=2), encoding="utf-8"
                    )
            return rows

        rows = asyncio.run(asyncio.wait_for(validate(), timeout=1200))
        assert len(rows) == 40
        assert {row["example_id"] for row in rows} == {item.id for item in held_out.examples}
        summary = {
            label: {
                metric: sum(row[metric] for row in rows if row["configuration"] == label) / 20
                for metric in ("answer_terms", "page_recall")
            }
            for label in ("baseline", "winner")
        }
        (tmp_path / "quality-summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        (tmp_path / "manifest.json").write_text(
            json.dumps(
                {
                    "framework": framework,
                    "strategy": strategy_name,
                    "pdf_hash": builder.document_hash,
                    "development_version": development.version,
                    "held_out_version": held_out.version,
                    "built": builder.built,
                    "suggestions": suggestion_provider.requests,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        runner.close()
        cache.close()
        store.close()


def test_live_synthetic_qa_provenance(provider, tmp_path):
    from tunarag import (
        SourceDocument,
        SourceSpan,
        SyntheticDatasetBuilder,
        SyntheticGenerationResponse,
        SyntheticQA,
        UsageRecord,
    )
    from tunarag.serialization import storage_json

    source_data = json.loads(Path(__file__).with_name("documents.json").read_text())
    document = SourceDocument("source-1", source_data[0]["text"])

    class Provider:
        async def generate(self, request):
            message = await provider["chat"].ainvoke(
                [
                    (
                        "system",
                        "Generate exactly two factual question/answer pairs using only "
                        'the source. Return only JSON: {"items":[{"query":"...","answer":"..."}]}',
                    ),
                    ("human", request.document.text),
                ]
            )
            data = json.loads(message.content)
            assert len(data["items"]) == request.count
            metadata = message.usage_metadata
            return SyntheticGenerationResponse(
                tuple(
                    SyntheticQA(
                        item["query"], item["answer"], (SourceSpan(0, len(request.document.text)),)
                    )
                    for item in data["items"]
                ),
                (
                    UsageRecord(
                        "synthetic.chat",
                        input_tokens=metadata["input_tokens"],
                        output_tokens=metadata["output_tokens"],
                    ),
                ),
            )

    result = asyncio.run(
        SyntheticDatasetBuilder(
            Provider(), samples_per_document=2, concurrency=1, generator_version="live-campaign-v1"
        ).generate([document])
    )
    assert len(result.dataset.examples) == 2
    assert result.usage[0].input_tokens > 0
    for example in result.dataset.examples:
        assert example.synthetic
        assert example.relevant_document_ids == (document.id,)
        assert example.reference_contexts == (document.text,)
        assert example.metadata["review_status"] == "unreviewed"
    (tmp_path / "synthetic.json").write_bytes(
        storage_json([example.semantic_data() for example in result.dataset.examples])
    )


def test_live_judge_repeatability(provider, tmp_path):
    from tunarag import EvaluationExample

    from .test_provider import faithfulness

    evaluator = faithfulness(provider)
    example = EvaluationExample("calibration", "Where was Mira born?", reference_answer="Paris")

    async def calibrate():
        rows = []
        for repeat in range(3):
            supported = await evaluator.evaluate(
                {"answer": "Mira was born in Paris.", "contexts": ["Mira was born in Paris."]},
                example,
            )
            contradictory = await evaluator.evaluate(
                {"answer": "Mira was born on Mars.", "contexts": ["Mira was born in Paris."]},
                example,
            )
            values = {
                "repeat": repeat,
                "supported": supported[0].value,
                "contradictory": contradictory[0].value,
            }
            rows.append(values)
            assert values["supported"] is not None and values["contradictory"] is not None
            assert 0 <= values["contradictory"] < values["supported"] <= 1
        return rows

    rows = asyncio.run(asyncio.wait_for(calibrate(), timeout=600))
    (tmp_path / "calibration.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def test_live_llm_suggestion(provider, tmp_path):
    from tunarag.search import LLMSuggestionRequest

    remote = ChatSuggestionProvider(provider["chat"])
    request = LLMSuggestionRequest(search_space().describe(), (), 0, 0)
    candidate = asyncio.run(remote.suggest(request))
    search_space().validate(candidate)
    assert remote.valid == 1
    (tmp_path / "suggestion.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")


def test_live_full_held_out_scoring(provider, pytestconfig, tmp_path):
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextRecall

    path = pytestconfig.getoption("--live-held-out-report")
    if not path:
        pytest.skip("requires --live-held-out-report from a completed campaign")
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    assert len(rows) == 40
    examples = {example.id: example for example in question_sets()[1].examples}
    assert {(row["configuration"], row["example_id"]) for row in rows} == {
        (label, identifier) for label in ("baseline", "winner") for identifier in examples
    }
    judge = RagasEvaluator(
        [
            Faithfulness(llm=LangchainLLMWrapper(provider["judge"])),
            LLMContextRecall(llm=LangchainLLMWrapper(provider["judge"])),
        ],
        sample_mapper,
        raise_exceptions=True,
    )

    async def score():
        scored = []
        for row in rows:
            example = examples[row["example_id"]]
            assert (
                row["query"] == example.query
                and row["reference_answer"] == example.reference_answer
            )
            item = dict(row)
            if example.metadata.get("kind") == "unanswerable":
                item["ragas_status"] = "not_applicable_unanswerable"
            else:
                for metric in await judge.evaluate(row["output"], example):
                    assert (
                        metric.value is not None
                        and math.isfinite(metric.value)
                        and 0 <= metric.value <= 1
                    )
                    item[metric.name] = metric.value
                item["ragas_status"] = "scored"
            scored.append(item)
            (tmp_path / "full-scores.json").write_text(
                json.dumps(scored, indent=2), encoding="utf-8"
            )
        return scored

    scored = asyncio.run(asyncio.wait_for(score(), timeout=1200))
    assert sum(row["ragas_status"] == "scored" for row in scored) == 34
    summary = {
        label: {
            metric: sum(
                row[metric]
                for row in scored
                if row["configuration"] == label and row["ragas_status"] == "scored"
            )
            / 17
            for metric in ("ragas.faithfulness", "ragas.context_recall")
        }
        for label in ("baseline", "winner")
    }
    (tmp_path / "full-score-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
