import asyncio
from typing import Any

import pytest

from tunarag import (
    AdapterError,
    Candidate,
    EvaluationDataset,
    EvaluationExample,
    GoogleADKAdapter,
    IntegerRange,
    LangChainAdapter,
    MetricEvaluator,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RandomSearch,
    SearchSpace,
    Settings,
)

adk = pytest.importorskip("google.adk")
from google.adk.agents import BaseAgent  # noqa: E402
from google.adk.events import Event  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402


class EchoAgent(BaseAgent):
    mode: str = "success"

    async def _run_async_impl(self, ctx: Any):
        if self.mode == "failure":
            raise ConnectionError("transient provider failure")
        if self.mode == "hang":
            await asyncio.Event().wait()
        if self.mode == "empty":
            return
        if self.mode == "error":
            yield Event(author=self.name, error_code="UNAVAILABLE", error_message="sensitive")
            return
        if self.mode == "structured":
            yield Event(author=self.name, output={"answer": "structured answer"})
            return
        yield Event(
            author=self.name,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=f"top_k={ctx.session.state['top_k']}")],
            ),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=4, candidates_token_count=2
            ),
        )


def runner(mode: str = "success") -> InMemoryRunner:
    return InMemoryRunner(agent=EchoAgent(name="echo", mode=mode), app_name="evaluation")


@pytest.mark.frameworks
def test_adk_optimizer_executes_real_runner_and_cleans_sessions() -> None:
    async def exercise():
        pipeline = runner()
        optimizer = Optimizer(
            adapter=GoogleADKAdapter(pipeline, identity={"agent": "echo-v1"}),
            strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)}), seed=0),
            evaluators=(
                MetricEvaluator(
                    "quality", lambda output, example: float(output["answer"].split("=")[1])
                ),
            ),
            objective=Objective((ObjectiveTerm("quality"),)),
            settings=Settings.resolve(overrides={"max_trials": 2}, environ={}),
        )
        try:
            result = await optimizer.aoptimize(
                EvaluationDataset.from_records([{"id": "q", "query": "question"}]),
                study_name="adk-compatibility",
            )
            assert len(result.ranked_trials) == 2
            assert result.best_candidate.parameters["top_k"] == 2
            assert {trial.objective.score for trial in result.successful_trials} == {1.0, 2.0}
            sessions = await pipeline.session_service.list_sessions(
                app_name=pipeline.app_name, user_id="tunarag-evaluation"
            )
            assert sessions.sessions == []
        finally:
            optimizer.close()
            await pipeline.close()

    asyncio.run(exercise())


@pytest.mark.frameworks
def test_adk_maps_parameters_and_usage() -> None:
    async def exercise():
        pipeline = runner()
        try:
            output, usage = await GoogleADKAdapter(pipeline).run(
                Candidate({"top_k": 3}), EvaluationExample("q", "question")
            )
            assert output == {"answer": "top_k=3"}
            assert usage[0].input_tokens == 4
            assert usage[0].output_tokens == 2
            assert usage[-1].component == "google_adk.runner"
        finally:
            await pipeline.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("mode", ["empty", "error", "failure", "hang"])
def test_adk_cleans_sessions_on_failure_and_timeout(mode: str) -> None:
    async def exercise():
        pipeline = runner(mode)
        try:
            with pytest.raises((AdapterError, ConnectionError, TimeoutError)):
                await asyncio.wait_for(
                    GoogleADKAdapter(pipeline).run(
                        Candidate({"top_k": 2}), EvaluationExample("q", "question")
                    ),
                    timeout=0.1,
                )
            sessions = await pipeline.session_service.list_sessions(
                app_name=pipeline.app_name, user_id="tunarag-evaluation"
            )
            assert sessions.sessions == []
        finally:
            await pipeline.close()

    asyncio.run(exercise())


def test_custom_objects_are_rejected() -> None:
    class CustomPipeline:
        async def ainvoke(self, payload, config=None):
            return payload

        async def run(self, candidate, example):
            return example, ()

    with pytest.raises(TypeError, match="real Runnable"):
        LangChainAdapter(CustomPipeline())
    with pytest.raises(TypeError, match="real Google ADK Runner"):
        GoogleADKAdapter(CustomPipeline())
    with pytest.raises(TypeError, match="custom RAG adapters are unsupported"):
        Optimizer(
            adapter=CustomPipeline(),
            strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)})),
            evaluators=(MetricEvaluator("quality", lambda output, example: 1.0),),
            objective=Objective((ObjectiveTerm("quality"),)),
        )


def test_adk_factory_and_mapper_accept_structured_v2_events() -> None:
    async def exercise():
        pipeline = runner("structured")
        adapter = GoogleADKAdapter(
            factory=lambda candidate: pipeline,
            state_mapper=lambda candidate: {"retrieval_k": candidate.parameters["top_k"]},
            output_mapper=lambda event: event.output,
        )
        try:
            output, usage = await adapter.run(
                Candidate({"top_k": 3}), EvaluationExample("q", "question")
            )
            assert output == {"answer": "structured answer"}
            assert usage[-1].component == "google_adk.runner"
            sessions = await pipeline.session_service.list_sessions(
                app_name=pipeline.app_name, user_id="tunarag-evaluation"
            )
            assert sessions.sessions == []
        finally:
            await pipeline.close()

    asyncio.run(exercise())
