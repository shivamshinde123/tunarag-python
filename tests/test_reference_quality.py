import asyncio
from types import SimpleNamespace

import pytest
from live.quality import ReferenceQualityEvaluator, verdict_scores

from tunarag import EvaluationExample, ValueStatus


def test_quality_scoring_separates_coverage_from_contradiction():
    complete = {"covered": [True, True], "contradiction": False, "reason": "complete"}
    partial = {"covered": [True, False], "contradiction": False, "reason": "missing cosine"}
    wrong = {"covered": [True, True], "contradiction": True, "reason": "negated facts"}
    assert verdict_scores(complete, 2)["quality.reference_score"] == 1
    assert verdict_scores(partial, 2)["quality.reference_score"] == 0.5
    assert verdict_scores(wrong, 2)["quality.reference_score"] == 0
    assert verdict_scores(wrong, 2)["quality.completeness"] == 1


@pytest.mark.parametrize(
    "verdict",
    [
        {},
        {"covered": [True], "contradiction": False, "reason": "wrong length"},
        {"covered": [1, 0], "contradiction": False, "reason": "numeric flags"},
        {"covered": [True, False], "contradiction": "false", "reason": "string flag"},
        {"covered": [True, False], "contradiction": False, "reason": ""},
        {"covered": [True, False], "contradiction": False, "reason": "ok", "extra": 1},
    ],
)
def test_quality_verdict_rejects_malformed_output(verdict):
    with pytest.raises(ValueError):
        verdict_scores(verdict, 2)


def test_quality_evaluator_is_pluggable_and_rubric_versioned():
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    fake = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content='{"covered":[true,false],"contradiction":false,"reason":"missing cosine"}'
            )
        ]
    )
    chat = SimpleNamespace(model_name="offline", bind=lambda **options: fake)
    evaluator = ReferenceQualityEvaluator(chat, {"q": ["sine", "cosine"]})
    changed = ReferenceQualityEvaluator(chat, {"q": ["sine"]})
    assert evaluator.fingerprint() != changed.fingerprint()
    metrics = asyncio.run(
        evaluator.evaluate(
            {"answer": "Sine"},
            EvaluationExample("q", "Which functions?", reference_answer="Sine and cosine"),
        )
    )
    assert all(metric.status == ValueStatus.ESTIMATED for metric in metrics)
    assert {metric.name: metric.value for metric in metrics}["quality.completeness"] == 0.5


def test_optimizer_selects_complete_answer_with_reference_objective():
    import json

    from langchain_core.runnables import RunnableLambda

    from tunarag import (
        EvaluationDataset,
        IntegerRange,
        LangChainAdapter,
        Objective,
        ObjectiveTerm,
        Optimizer,
        RandomSearch,
        SearchSpace,
        Settings,
    )

    async def judge(messages):
        answer = json.loads(messages[-1][1])["answer"]
        return SimpleNamespace(
            content=json.dumps(
                {
                    "covered": [True, answer == "Sine and cosine"],
                    "contradiction": False,
                    "reason": "offline expected coverage",
                }
            ),
            usage_metadata=None,
        )

    chat = SimpleNamespace(
        model_name="offline", bind=lambda **options: SimpleNamespace(ainvoke=judge)
    )
    evaluator = ReferenceQualityEvaluator(chat, {"q": ["sine", "cosine"]})

    def factory(candidate):
        answer = "Sine and cosine" if candidate.parameters["detail"] == 2 else "Sine"
        return RunnableLambda(lambda inputs: {"answer": answer})

    runner = Optimizer(
        adapter=LangChainAdapter(factory=factory),
        strategy=RandomSearch(SearchSpace({"detail": IntegerRange(1, 2)}), seed=0),
        evaluators=(evaluator,),
        objective=Objective((ObjectiveTerm("quality.reference_score"),)),
        settings=Settings.resolve(overrides={"max_trials": 2, "concurrency": 1}, environ={}),
    )
    try:
        result = runner.optimize(
            EvaluationDataset.from_records(
                [{"id": "q", "query": "Which functions?", "reference_answer": "Sine and cosine"}]
            ),
            study_name="reference-quality-objective",
        )
        assert not result.failed_trials and len(result.successful_trials) == 2
        assert result.best_candidate.parameters["detail"] == 2
        assert {trial.objective.score for trial in result.trials} == {0.5, 1.0}
    finally:
        runner.close()
