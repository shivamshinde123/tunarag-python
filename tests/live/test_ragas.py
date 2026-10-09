import asyncio
from types import SimpleNamespace

import pytest

from tunarag import EvaluationExample, RagasEvaluator

pytestmark = pytest.mark.live


def test_real_ragas_exact_match_without_provider():
    from ragas.metrics import ExactMatch

    evaluator = RagasEvaluator(
        [ExactMatch()],
        lambda output, example: {"response": output, "reference": example.reference_answer},
        raise_exceptions=True,
    )
    example = EvaluationExample("q", "What stores experiments?", reference_answer="SQLite")

    async def evaluate():
        correct = await evaluator.evaluate("SQLite", example)
        incorrect = await evaluator.evaluate("Redis", example)
        return correct, incorrect

    correct, incorrect = asyncio.run(evaluate())
    assert correct[0].value == 1
    assert incorrect[0].value == 0


def test_real_provider_and_judge_construction_without_requests(monkeypatch):
    from .conftest import provider
    from .test_provider import faithfulness

    monkeypatch.setenv("OPENROUTER_API_KEY", "placeholder-not-a-real-key")
    config = SimpleNamespace(getoption=lambda name: 1 if name == "--live-request-limit" else None)
    generator = provider.__wrapped__(config)
    clients = next(generator)
    try:
        assert isinstance(faithfulness(clients), RagasEvaluator)
        assert clients["budget"].used == 0
    finally:
        next(generator, None)
