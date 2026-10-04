"""Optimize a deterministic reference RAG through TunaRAG's public API."""

from __future__ import annotations

from pathlib import Path

from examples.reference_rag import ReferenceQualityEvaluator, ReferenceRAGAdapter
from tunarag import (
    EvaluationDataset,
    IntegerRange,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RandomSearch,
    SearchSpace,
    Settings,
    SQLiteStore,
)


def run(output_dir: str | Path) -> Path:
    """Run the quickstart study and return its JSON report path."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    documents = {
        "architecture": "TunaRAG optimizes an existing RAG pipeline through a typed adapter.",
        "storage": "SQLite is the authoritative local experiment store and supports resumability.",
        "search": "RandomSearch and LLMSearch are interchangeable search strategies.",
    }
    dataset = EvaluationDataset.from_records(
        [
            {
                "id": "adapter",
                "query": "How does TunaRAG connect to a RAG pipeline?",
                "reference_answer": "through a typed adapter",
                "relevant_document_ids": ["architecture"],
            },
            {
                "id": "storage",
                "query": "Which local store supports resumability?",
                "reference_answer": "SQLite",
                "relevant_document_ids": ["storage"],
            },
        ]
    )
    settings = Settings.resolve(
        overrides={
            "home": target,
            "db_path": target / "experiments.db",
            "cache_dir": target / "cache",
            "artifact_dir": target / "artifacts",
            "max_trials": 3,
            "concurrency": 1,
            "sample_concurrency": 2,
        },
        environ={},
    )

    store = SQLiteStore(settings.db_path)
    optimizer = Optimizer(
        adapter=ReferenceRAGAdapter(documents),
        strategy=RandomSearch(
            SearchSpace({"top_k": IntegerRange(1, 3)}),
            seed=settings.seed,
        ),
        evaluators=(ReferenceQualityEvaluator(),),
        objective=Objective((ObjectiveTerm("answer_recall"),)),
        store=store,
        settings=settings,
    )
    try:
        result = optimizer.optimize(dataset, study_name="reference-rag-quickstart")
        report_path = result.write_json(target / "result.json")
        result.write_csv(target / "trials.csv")
        return report_path
    finally:
        store.close()


if __name__ == "__main__":
    report = run(Path("tunarag-example-output"))
    print(f"Wrote optimization report to {report}")
