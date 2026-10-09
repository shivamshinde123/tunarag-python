"""Tune a pre-existing Google ADK 2.x RAG runner using session-state parameters.

Install: python -m pip install 'tunarag-python[google-adk]'
Pass your Runner and an evaluation dataset to tune(). Your agent must consume
top_k from session state, or supply a candidate factory to rebuild its retriever.
"""

from __future__ import annotations

from typing import Any

from tunarag import (
    EvaluationDataset,
    GoogleADKAdapter,
    IntegerRange,
    MetricEvaluator,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RandomSearch,
    SearchSpace,
    Settings,
)


async def tune(runner: Any, dataset: EvaluationDataset):
    """Return an optimization result for an existing framework RAG runner."""
    optimizer = Optimizer(
        adapter=GoogleADKAdapter(runner, identity={"pipeline_revision": "rag-v1"}),
        strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 8)}), seed=42),
        evaluators=(
            MetricEvaluator(
                "answer_recall",
                lambda output, example: float(
                    (example.reference_answer or "").casefold() in output["answer"].casefold()
                ),
            ),
        ),
        objective=Objective((ObjectiveTerm("answer_recall"),)),
        settings=Settings.resolve(overrides={"max_trials": 8}, environ={}),
    )
    try:
        return await optimizer.aoptimize(dataset, study_name="google-adk-rag")
    finally:
        optimizer.close()
