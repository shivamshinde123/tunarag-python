"""Tune an offline LangChain retrieval pipeline through public TunaRAG APIs."""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake import FakeListLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.vectorstores import InMemoryVectorStore

from tunarag import (
    Candidate,
    EvaluationDataset,
    IntegerRange,
    LangChainAdapter,
    MetricEvaluator,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RandomSearch,
    SearchSpace,
    Settings,
    SQLiteStore,
)


def run(output_dir: str | Path) -> Path:
    """Write reports from a framework pipeline without provider credentials."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    documents = [
        Document(page_content="TunaRAG tunes LangChain, LangGraph, and Google ADK pipelines."),
        Document(page_content="SQLite stores experiments and supports resumability."),
        Document(page_content="RandomSearch explores typed parameter spaces."),
    ]
    vector_store = InMemoryVectorStore.from_documents(
        documents, DeterministicFakeEmbedding(size=32)
    )
    prompt = ChatPromptTemplate.from_template("Context: {context}\nQuestion: {question}")

    def build_chain(candidate: Candidate):
        retriever = vector_store.as_retriever(search_kwargs={"k": candidate.parameters["top_k"]})
        return (
            {"context": retriever, "question": RunnablePassthrough()}
            | prompt
            | FakeListLLM(
                responses=["TunaRAG tunes framework pipelines. SQLite stores experiments."]
            )
        )

    dataset = EvaluationDataset.from_records(
        [
            {
                "id": "frameworks",
                "query": "What does TunaRAG tune?",
                "reference_answer": "framework pipelines",
            },
            {
                "id": "storage",
                "query": "Where are experiments stored?",
                "reference_answer": "SQLite",
            },
        ]
    )
    evaluator = MetricEvaluator(
        "answer_recall",
        lambda output, example: float(example.reference_answer.lower() in output.lower()),
    )
    settings = Settings.resolve(
        overrides={"home": target, "max_trials": 3, "concurrency": 1}, environ={}
    )
    store = SQLiteStore(target / "experiments.db")
    optimizer = Optimizer(
        adapter=LangChainAdapter(
            factory=build_chain,
            input_mapper=lambda example, candidate: example.query,
            identity={"example": "offline-langchain", "version": 1},
        ),
        strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 3)}), seed=0),
        evaluators=(evaluator,),
        objective=Objective((ObjectiveTerm("answer_recall"),)),
        store=store,
        settings=settings,
    )
    try:
        result = optimizer.optimize(dataset, study_name="langchain-quickstart")
        report_path = result.write_json(target / "result.json")
        result.write_csv(target / "trials.csv")
        return report_path
    finally:
        store.close()


if __name__ == "__main__":
    print(run(Path("tunarag-example-output")))
