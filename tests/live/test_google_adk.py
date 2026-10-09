import asyncio
import json
import math
from pathlib import Path

import pytest

from tunarag import (
    Candidate,
    EvaluationDataset,
    GoogleADKAdapter,
    IntegerRange,
    MetricEvaluator,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RagasEvaluator,
    RandomSearch,
    ResumeError,
    RetryPolicy,
    SearchSpace,
    Settings,
    SQLiteCache,
    SQLiteStore,
)

from .campaign import page_recall, question_sets, term_coverage
from .test_provider import sample_mapper

pytestmark = [pytest.mark.live, pytest.mark.paid, pytest.mark.campaign]


def adk_model(chat):
    from google.adk.models.lite_llm import LiteLlm

    return LiteLlm(
        model="openai/" + chat.model_name,
        client=chat.root_async_client,
        api_base="https://openrouter.ai/api/v1",
        max_tokens=512,
        temperature=0,
        num_retries=0,
        timeout=45,
    )


def test_live_google_adk_rag(provider, pytestconfig, tracking_server, tmp_path, monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "true")
    from google.adk.agents import Agent
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from langchain_classic.embeddings import CacheBackedEmbeddings
    from langchain_classic.storage import LocalFileStore
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_core.vectorstores import InMemoryVectorStore
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextRecall

    from tunarag.integrations import MLflowCallback
    from tunarag.serialization import content_hash

    pdf = pytestconfig.getoption("--live-pdf")
    assert pdf and Path(pdf).is_file(), "Provide the approved paper with --live-pdf"
    documents = PyPDFLoader(pdf).load()
    assert "Attention Is All You Need" in documents[0].page_content
    assert provider["chat"].model_name == "openai/gpt-4.1-mini"
    embeddings = CacheBackedEmbeddings.from_bytes_store(
        provider["embeddings"],
        LocalFileStore(str(tmp_path / "embeddings")),
        namespace=provider["embeddings"].model,
        query_embedding_cache=True,
        key_encoder="sha256",
    )
    chunks = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=80).split_documents(
        documents
    )
    vectors = InMemoryVectorStore.from_documents(chunks, embeddings)
    runners = []
    retrievals = []

    async def retrieve(callback_context, llm_request):
        query = "".join(part.text or "" for part in llm_request.contents[-1].parts)
        top_k = callback_context.state["top_k"]
        found = await vectors.as_retriever(search_kwargs={"k": top_k}).ainvoke(query)
        assert len(found) == top_k
        contexts = [item.page_content for item in found]
        pages = [str(item.metadata["page"] + 1) for item in found]
        callback_context.state["contexts"] = contexts
        callback_context.state["pages"] = pages
        retrievals.append({"top_k": top_k, "count": len(found), "pages": pages})
        llm_request.config.system_instruction = (
            "Answer only from the paper excerpts. Give a short factual answer. "
            "If unsupported, say the paper does not provide the answer. Context:\n"
            + "\n\n".join(contexts)
        )

    def attach_context(callback_context, llm_response):
        llm_response.custom_metadata = {
            "contexts": callback_context.state["contexts"],
            "pages": callback_context.state["pages"],
        }

    def factory(candidate):
        pipeline = InMemoryRunner(
            app_name="tunarag_live_adk",
            agent=Agent(
                name="paper_rag",
                model=adk_model(provider["chat"]),
                generate_content_config=types.GenerateContentConfig(
                    temperature=0, max_output_tokens=512
                ),
                before_model_callback=retrieve,
                after_model_callback=attach_context,
            ),
        )
        runners.append(pipeline)
        return pipeline

    def output_mapper(event):
        return {
            "answer": "".join(part.text or "" for part in event.content.parts if not part.thought),
            **event.custom_metadata,
        }

    def adapter(revision=1):
        return GoogleADKAdapter(
            factory=factory,
            output_mapper=output_mapper,
            identity={
                "pdf": content_hash([item.page_content for item in documents]),
                "revision": revision,
                "model": provider["chat"].model_name,
                "chunk_size": 1000,
                "overlap": 80,
                "embedding_model": provider["embeddings"].model,
            },
        )

    development, held_out = question_sets()
    dataset = EvaluationDataset(development.examples[:3])
    judge = RagasEvaluator(
        [
            Faithfulness(llm=LangchainLLMWrapper(provider["judge"])),
            LLMContextRecall(llm=LangchainLLMWrapper(provider["judge"])),
        ],
        sample_mapper,
        raise_exceptions=True,
    )
    store = SQLiteStore(tmp_path / "study.db")
    cache = SQLiteCache(tmp_path / "cache.db")
    client, uri = tracking_server
    experiment = client.create_experiment("live-google-adk")

    def optimizer(revision=1):
        return Optimizer(
            adapter=adapter(revision),
            strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)}), seed=0),
            evaluators=(judge, MetricEvaluator("page_recall", page_recall)),
            objective=Objective(
                (
                    ObjectiveTerm("ragas.faithfulness", weight=0.4),
                    ObjectiveTerm("ragas.context_recall", weight=0.4),
                    ObjectiveTerm("page_recall", weight=0.2),
                )
            ),
            store=store,
            cache=cache,
            settings=Settings.resolve(overrides={"max_trials": 2}, environ={}),
            retry_policy=RetryPolicy(
                max_retries=0, sample_timeout_seconds=180, trial_timeout_seconds=600
            ),
            callbacks=(MLflowCallback(store, tracking_uri=uri, experiment_id=experiment),),
        )

    async def exercise():
        runner = optimizer()
        try:
            result = await runner.aoptimize(dataset, study_name="live-google-adk")
            assert len(result.successful_trials) == 2 and not result.failed_trials
            assert {trial.candidate.parameters["top_k"] for trial in result.trials} == {1, 2}
            for trial in result.trials:
                assert any(item.input_tokens and item.output_tokens for item in trial.usage)
                for name in ("ragas.faithfulness", "ragas.context_recall"):
                    assert math.isfinite(trial.metric(name).value)
                    assert 0 <= trial.metric(name).value <= 1
            assert len(retrievals) == 6
            requests_before = provider["budget"].used
            runner.close()
            runner = optimizer()
            resumed = await runner.aresume(dataset, study_id=result.study_id)
            assert resumed.best_candidate == result.best_candidate
            assert provider["budget"].used == requests_before and len(retrievals) == 6
            incompatible = optimizer(2)
            try:
                with pytest.raises(ResumeError, match="incompatible"):
                    await incompatible.aresume(dataset, study_id=result.study_id)
            finally:
                incompatible.close()
            assert provider["budget"].used == requests_before
            result.write_json(tmp_path / "result.json")
            result.write_csv(tmp_path / "trials.csv")
            (tmp_path / "winning-config.json").write_text(
                json.dumps(dict(result.best_candidate.parameters)), encoding="utf-8"
            )
            winner = Candidate(json.loads((tmp_path / "winning-config.json").read_text()))
            rows = []
            for label, candidate in (("baseline", Candidate({"top_k": 1})), ("winner", winner)):
                for example in held_out.examples[:3]:
                    output, usage = await adapter().run(candidate, example)
                    assert output["answer"]
                    assert len(output["contexts"]) == candidate.parameters["top_k"]
                    assert any(item.input_tokens for item in usage)
                    scores = {
                        metric.name: metric.value
                        for metric in await judge.evaluate(output, example)
                    }
                    assert all(
                        math.isfinite(value) and 0 <= value <= 1 for value in scores.values()
                    )
                    rows.append(
                        {
                            "configuration": label,
                            "example_id": example.id,
                            "output": output,
                            "scores": scores,
                            "answer_terms": term_coverage(output, example),
                            "page_recall": page_recall(output, example),
                        }
                    )
                    (tmp_path / "held-out.json").write_text(
                        json.dumps(rows, indent=2), encoding="utf-8"
                    )
            assert len(rows) == 6
            for pipeline in runners:
                sessions = await pipeline.session_service.list_sessions(
                    app_name=pipeline.app_name, user_id="tunarag-evaluation"
                )
                assert sessions.sessions == []
            assert not any(
                event.type == "callback.failed" for event in store.list_events(result.study_id)
            )
            runs = client.search_runs([experiment])
            assert len(runs) == 1 and runs[0].info.status == "FINISHED"
            assert len(client.get_metric_history(runs[0].info.run_id, "ragas.faithfulness")) == 2
            (tmp_path / "retrievals.json").write_text(
                json.dumps(retrievals, indent=2), encoding="utf-8"
            )
        finally:
            runner.close()
            for pipeline in runners:
                await pipeline.close()

    asyncio.run(asyncio.wait_for(exercise(), timeout=1200))
