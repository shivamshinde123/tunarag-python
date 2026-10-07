"""Build and tune a complete LangChain RAG pipeline with TunaRAG.

Install:
    python -m pip install tunarag-python langchain langchain-classic \
        langchain-openai langchain-text-splitters

Configure:
    PowerShell: $env:OPENAI_API_KEY = "your-key"
    bash/zsh:   export OPENAI_API_KEY="your-key"

Run:
    python examples/langchain_full_rag.py

Optional environment variables:
    TUNARAG_CHAT_MODEL       Default: gpt-4.1-mini
    TUNARAG_EMBEDDING_MODEL  Default: text-embedding-3-small
"""

from __future__ import annotations

import asyncio
import os
import re
from functools import cache
from pathlib import Path
from typing import Any

from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from tunarag import (
    Candidate,
    Categorical,
    EvaluationDataset,
    FloatRange,
    IntegerRange,
    LangChainAdapter,
    MetricEvaluator,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RandomSearch,
    RetryPolicy,
    SearchSpace,
    Settings,
    SQLiteCache,
    SQLiteStore,
)

OUTPUT_DIRECTORY = Path("tunarag-langchain-output")
CHAT_MODEL = os.getenv("TUNARAG_CHAT_MODEL", "gpt-4.1-mini")
EMBEDDING_MODEL = os.getenv("TUNARAG_EMBEDDING_MODEL", "text-embedding-3-small")

SOURCE_DOCUMENTS = (
    Document(
        page_content=(
            "TunaRAG improves an existing retrieval-augmented generation pipeline. "
            "The application supplies its RAG pipeline through RAGAdapter or an official "
            "LangChain or LangGraph adapter. TunaRAG then evaluates candidate configurations."
        ),
        metadata={"source_id": "overview"},
    ),
    Document(
        page_content=(
            "RandomSearch is deterministic when given the same search space and seed. "
            "LLMSearch is provider-neutral, validates every suggestion, and can fall back to "
            "deterministic random search after invalid suggestions."
        ),
        metadata={"source_id": "search"},
    ),
    Document(
        page_content=(
            "SQLite is TunaRAG's default authoritative experiment store. It persists studies, "
            "trials, attempts, metrics, usage, and ordered events. Interrupted compatible studies "
            "can resume without repeating committed successful trials."
        ),
        metadata={"source_id": "storage"},
    ),
    Document(
        page_content=(
            "TunaRAG can optimize answer quality, provider cost, and response latency with a "
            "weighted objective. Evaluators produce metrics, and the objective converts those "
            "metrics into one larger-is-better score."
        ),
        metadata={"source_id": "objectives"},
    ),
    Document(
        page_content=(
            "Evaluation caching is versioned by dataset, candidate, adapter, and evaluator "
            "identity. Retries isolate transient sample failures, while terminal trial failures "
            "do not abort the rest of an optimization study."
        ),
        metadata={"source_id": "reliability"},
    ),
)

EVALUATION_RECORDS = (
    {
        "id": "adapter",
        "query": "How does TunaRAG connect to an existing LangChain RAG pipeline?",
        "reference_answer": "through the official LangChain adapter",
        "relevant_document_ids": ["overview"],
    },
    {
        "id": "search",
        "query": "Which TunaRAG search strategy is deterministic with the same seed?",
        "reference_answer": "RandomSearch",
        "relevant_document_ids": ["search"],
    },
    {
        "id": "storage",
        "query": "What is TunaRAG's default authoritative experiment store?",
        "reference_answer": "SQLite",
        "relevant_document_ids": ["storage"],
    },
    {
        "id": "objective",
        "query": "Which three concerns can a TunaRAG weighted objective optimize?",
        "reference_answer": "answer quality, provider cost, and response latency",
        "relevant_document_ids": ["objectives"],
    },
    {
        "id": "failure",
        "query": "Does one terminal trial failure abort the entire optimization study?",
        "reference_answer": "No, trial failures are isolated",
        "relevant_document_ids": ["reliability"],
    },
)


def _require_openai_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "Set OPENAI_API_KEY before running this example. See the commands in the file header."
        )


def _normalized_words(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _answer_recall(output: dict[str, Any], example: Any) -> float:
    expected = _normalized_words(example.reference_answer or "")
    actual = _normalized_words(output["answer"])
    return len(expected & actual) / len(expected) if expected else 0.0


def _retrieval_recall(output: dict[str, Any], example: Any) -> float:
    expected = set(example.relevant_document_ids)
    actual = set(output["document_ids"])
    return len(expected & actual) / len(expected) if expected else 0.0


def _adapter_output(result: dict[str, Any]) -> dict[str, Any]:
    documents = result["context"]
    return {
        "answer": result["answer"],
        "contexts": [document.page_content for document in documents],
        "document_ids": [document.metadata["source_id"] for document in documents],
    }


def _prompt_for(style: str) -> ChatPromptTemplate:
    instruction = {
        "concise": "Answer in one concise sentence.",
        "grounded": "Answer precisely and mention only facts supported by the context.",
        "explanatory": "Answer clearly in two or three sentences and explain the key point.",
    }[style]
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You answer questions using only the supplied context. "
                "If the context does not contain the answer, say you do not know. "
                f"{instruction}\n\nContext:\n{{context}}",
            ),
            ("human", "{input}"),
        ]
    )


def _build_vector_store() -> InMemoryVectorStore:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=240,
        chunk_overlap=40,
        add_start_index=True,
    )
    chunks = splitter.split_documents(SOURCE_DOCUMENTS)
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return InMemoryVectorStore.from_documents(chunks, embeddings)


def _chain_factory(vector_store: InMemoryVectorStore):
    @cache
    def build_cached(
        top_k: int,
        search_type: str,
        temperature: float,
        prompt_style: str,
    ):
        search_kwargs: dict[str, Any] = {"k": top_k}
        if search_type == "mmr":
            search_kwargs["fetch_k"] = max(8, top_k * 3)
        retriever = vector_store.as_retriever(
            search_type=search_type,
            search_kwargs=search_kwargs,
        )
        model = ChatOpenAI(model=CHAT_MODEL, temperature=temperature)
        answer_chain = create_stuff_documents_chain(model, _prompt_for(prompt_style))
        return create_retrieval_chain(retriever, answer_chain)

    def build(candidate: Candidate):
        parameters = candidate.parameters
        return build_cached(
            int(parameters["top_k"]),
            str(parameters["search_type"]),
            float(parameters["temperature"]),
            str(parameters["prompt_style"]),
        )

    return build


async def main() -> None:
    _require_openai_key()
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    print("1. Splitting documents, creating embeddings, and building the vector store...")
    vector_store = _build_vector_store()
    build_chain = _chain_factory(vector_store)

    baseline_candidate = Candidate(
        {
            "top_k": 2,
            "search_type": "similarity",
            "temperature": 0.0,
            "prompt_style": "grounded",
        }
    )
    baseline = await build_chain(baseline_candidate).ainvoke(
        {"input": "What does TunaRAG optimize?"}
    )
    print(f"2. Baseline LangChain RAG answer: {baseline['answer']}\n")

    dataset = EvaluationDataset.from_records(EVALUATION_RECORDS)
    search_space = SearchSpace(
        {
            "top_k": IntegerRange(1, 4),
            "search_type": Categorical(("similarity", "mmr")),
            "temperature": FloatRange(0.0, 0.6),
            "prompt_style": Categorical(("concise", "grounded", "explanatory")),
        }
    )
    adapter = LangChainAdapter(
        factory=build_chain,
        input_key="input",
        output_mapper=_adapter_output,
        identity={
            "example": "langchain-full-rag",
            "version": 1,
            "chat_model": CHAT_MODEL,
            "embedding_model": EMBEDDING_MODEL,
            "chunk_size": 240,
            "chunk_overlap": 40,
        },
    )
    evaluators = (
        MetricEvaluator("answer_recall", _answer_recall),
        MetricEvaluator("retrieval_recall", _retrieval_recall),
    )
    objective = Objective(
        (
            ObjectiveTerm("answer_recall", weight=0.7, minimum=0.0, maximum=1.0),
            ObjectiveTerm("retrieval_recall", weight=0.3, minimum=0.0, maximum=1.0),
        )
    )
    settings = Settings.resolve(
        overrides={
            "home": OUTPUT_DIRECTORY,
            "db_path": OUTPUT_DIRECTORY / "experiments.db",
            "cache_dir": OUTPUT_DIRECTORY / "cache",
            "artifact_dir": OUTPUT_DIRECTORY / "artifacts",
            "max_trials": 8,
            "concurrency": 1,
            "sample_concurrency": 2,
            "seed": 42,
        },
        environ={},
    )
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(settings.db_path)
    cache = SQLiteCache(settings.cache_dir / "evaluations.db")
    optimizer = Optimizer(
        adapter=adapter,
        strategy=RandomSearch(search_space, seed=settings.seed),
        evaluators=evaluators,
        objective=objective,
        store=store,
        cache=cache,
        settings=settings,
        retry_policy=RetryPolicy(
            max_retries=2,
            sample_timeout_seconds=60.0,
            trial_timeout_seconds=300.0,
            base_delay_seconds=1.0,
            max_delay_seconds=8.0,
        ),
    )

    try:
        print("3. Running the TunaRAG optimization study...")
        result = await optimizer.aoptimize(dataset, study_name="langchain-full-rag")
        result.write_json(OUTPUT_DIRECTORY / "result.json")
        result.write_csv(OUTPUT_DIRECTORY / "trials.csv")

        if result.best_candidate is None:
            raise RuntimeError("The study completed without a successful candidate.")

        print(f"4. Best parameters: {dict(result.best_candidate.parameters)}")
        print(f"   Best objective score: {result.best_trial.objective.score}")
        print(f"   Study ID: {result.study_id}")

        tuned = await build_chain(result.best_candidate).ainvoke(
            {"input": "How does TunaRAG recover from interruptions?"}
        )
        print(f"5. Tuned LangChain RAG answer: {tuned['answer']}")
        print(f"6. Reports: {OUTPUT_DIRECTORY / 'result.json'}")
        print(f"            {OUTPUT_DIRECTORY / 'trials.csv'}")
        print(f"   SQLite: {settings.db_path}")
    finally:
        cache.close()
        store.close()


if __name__ == "__main__":
    asyncio.run(main())
