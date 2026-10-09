import asyncio
import math

import pytest

from tunarag import (
    EvaluationDataset,
    EvaluationExample,
    IntegerRange,
    LangChainAdapter,
    MetricEvaluator,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RagasEvaluator,
    RandomSearch,
    RetryPolicy,
    SearchSpace,
    Settings,
    SQLiteCache,
    SQLiteStore,
)

pytestmark = [pytest.mark.live, pytest.mark.paid]


def sample_mapper(output, example):
    return {
        "user_input": example.query,
        "response": output["answer"],
        "retrieved_contexts": output["contexts"],
        "reference": example.reference_answer,
    }


def faithfulness(provider):
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness

    judge = LangchainLLMWrapper(provider["judge"])
    return RagasEvaluator([Faithfulness(llm=judge)], sample_mapper, raise_exceptions=True)


@pytest.fixture(scope="session")
def rag_pipeline(provider, corpus):
    from langchain_classic.chains import create_retrieval_chain
    from langchain_classic.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.documents import Document
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.vectorstores import InMemoryVectorStore

    documents, records = corpus
    store = InMemoryVectorStore.from_documents(
        [
            Document(page_content=item["text"], metadata={"source_id": item["id"]})
            for item in documents
        ],
        provider["embeddings"],
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "Use only this context. Give a short factual answer. Context: {context}"),
            ("human", "{input}"),
        ]
    )

    def factory(candidate):
        return create_retrieval_chain(
            store.as_retriever(search_kwargs={"k": candidate.parameters["top_k"]}),
            create_stuff_documents_chain(
                provider["chat"], prompt, output_parser=RunnablePassthrough()
            ),
        )

    def output_mapper(output):
        return {
            "answer": output["answer"].content,
            "contexts": [document.page_content for document in output["context"]],
            "document_ids": [document.metadata["source_id"] for document in output["context"]],
        }

    return (
        LangChainAdapter(
            factory=factory,
            input_key="input",
            output_mapper=output_mapper,
            identity={"live_test": 1, "model": getattr(provider["chat"], "model_name", "offline")},
        ),
        EvaluationDataset.from_records(records),
    )


@pytest.mark.parametrize("metric", ["retrieval_recall", "ragas.faithfulness"])
def test_live_rag_optimization_and_completed_resume(metric, rag_pipeline, provider, tmp_path):
    adapter, dataset = rag_pipeline
    evaluator = (
        faithfulness(provider)
        if metric == "ragas.faithfulness"
        else MetricEvaluator(
            metric,
            lambda output, example: (
                len(set(output["document_ids"]) & set(example.relevant_document_ids))
                / len(set(example.relevant_document_ids))
            ),
        )
    )
    store = SQLiteStore(tmp_path / "study.db")
    cache = SQLiteCache(tmp_path / "cache.db")

    def build_optimizer():
        return Optimizer(
            adapter=adapter,
            strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)}), seed=0),
            evaluators=(evaluator,),
            objective=Objective((ObjectiveTerm(metric),)),
            settings=Settings.resolve(
                overrides={"max_trials": 2, "concurrency": 1, "sample_concurrency": 1}, environ={}
            ),
            retry_policy=RetryPolicy(
                max_retries=0, sample_timeout_seconds=180, trial_timeout_seconds=600
            ),
            store=store,
            cache=cache,
        )

    runner = build_optimizer()
    try:
        result = runner.optimize(dataset, study_name=metric)
        assert not result.failed_trials
        assert len(result.successful_trials) == 2
        assert {trial.candidate.parameters["top_k"] for trial in result.trials} == {1, 2}
        assert result.best_trial.objective.score == max(
            trial.objective.score for trial in result.successful_trials
        )
        for trial in result.successful_trials:
            value = trial.metric(metric).value
            assert value is not None and math.isfinite(value) and 0 <= value <= 1
        assert any(record.input_tokens for trial in result.trials for record in trial.usage)
        requests_before_resume = provider["budget"].used
        runner.close()
        runner = build_optimizer()
        resumed = runner.resume(dataset, study_id=result.study_id)
        assert resumed.best_candidate == result.best_candidate
        assert provider["budget"].used == requests_before_resume
        runner.close()
        runner = build_optimizer()
        cached = runner.optimize(dataset, study_name=f"{metric}-cached")
        assert all(trial.cached for trial in cached.successful_trials)
        assert len(cached.successful_trials) == 2
        assert cached.best_candidate == result.best_candidate
        assert provider["budget"].used == requests_before_resume
        result.write_json(tmp_path / "result.json")
        result.write_csv(tmp_path / "trials.csv")
    finally:
        runner.close()
        cache.close()
        store.close()


def test_live_ragas_supported_and_contradictory_answers(provider):
    evaluator = faithfulness(provider)
    example = EvaluationExample("calibration", "Where was Mira born?", reference_answer="Paris")

    async def evaluate():
        supported = await evaluator.evaluate(
            {"answer": "Mira was born in Paris.", "contexts": ["Mira was born in Paris."]},
            example,
        )
        unsupported = await evaluator.evaluate(
            {"answer": "Mira was born on Mars.", "contexts": ["Mira was born in Paris."]},
            example,
        )
        return supported[0].value, unsupported[0].value

    supported, unsupported = asyncio.run(asyncio.wait_for(evaluate(), timeout=180))
    assert supported is not None and unsupported is not None
    assert 0 <= unsupported < supported <= 1
