"""Exercise every TunaRAG feature on three real RAG apps (OpenRouter-backed).

Usage: python run_all.py <section> <workdir>   sections: data, langchain, langgraph, adk, synthetic
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
import time
from pathlib import Path

import apps
from corpus import DOCS, QUESTIONS

from tunarag import (
    CachePolicy,
    Categorical,
    DatasetSplit,
    EvaluationDataset,
    GoogleADKAdapter,
    IntegerRange,
    LangChainAdapter,
    LangGraphAdapter,
    LLMSearch,
    MaxFailures,
    MaxTrials,
    MetricEvaluator,
    NoImprovement,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RagasEvaluator,
    RandomSearch,
    RetryPolicy,
    SearchSpace,
    Settings,
    SourceDocument,
    SourceSpan,
    SplitRatios,
    SQLiteCache,
    SQLiteStore,
    SyntheticDatasetBuilder,
    SyntheticGenerationResponse,
    SyntheticQA,
    TargetScore,
    TimeBudget,
    UsageRecord,
)
from tunarag.integrations import MLflowCallback

SECTION, WORK = sys.argv[1], Path(sys.argv[2])
WORK.mkdir(parents=True, exist_ok=True)


def say(*parts):
    print(*parts, flush=True)


class Audit:
    """A user callback: records every durable event it receives."""

    def __init__(self):
        self.events = []

    async def on_event(self, event):
        self.events.append((event.sequence, event.type))


def settings(**overrides):
    return Settings.resolve(
        overrides={"cache_policy": CachePolicy.READ_WRITE, **overrides}, environ={}
    )


def check(label, ok, detail=""):
    say(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -> {detail}" if detail else ""))
    return ok


def report(result, label):
    say(
        f"  {label}: status={result.study_status.value} stop={result.stop_reason} "
        f"trials={len(result.trials)} ok={len(result.successful_trials)} failed={len(result.failed_trials)}"
    )
    for t in result.trials:
        metrics = {m.name: (None if m.value is None else round(m.value, 3)) for m in t.metrics}
        score = None if t.objective is None else round(t.objective.score, 3)
        say(
            f"    #{t.sequence} {dict(t.candidate.parameters)} {t.status.value} score={score} "
            f"cached={t.cached} attempts={t.attempts} {metrics} {t.error or ''}"
        )
    u = result.usage
    say(
        f"    usage: in={u.input_tokens} out={u.output_tokens} cost_exact={u.exact_cost} "
        f"cost_est={u.estimated_cost} latency={u.latency_seconds:.1f}s status={u.status.value}"
    )


def dataset_files():
    """Same records written as JSON, JSONL and CSV."""
    (WORK / "q.json").write_text(json.dumps(QUESTIONS), encoding="utf-8")
    (WORK / "q.jsonl").write_text(
        "\n".join(json.dumps(q) for q in QUESTIONS) + "\n", encoding="utf-8"
    )
    with (WORK / "q.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["id", "query", "reference_answer", "relevant_document_ids"]
        )
        w.writeheader()
        for q in QUESTIONS:
            w.writerow({**q, "relevant_document_ids": json.dumps(q["relevant_document_ids"])})


# ======================================================================================= DATA
async def data_section():
    dataset_files()
    a = EvaluationDataset.from_json(WORK / "q.json")
    b = EvaluationDataset.from_jsonl(WORK / "q.jsonl")
    c = EvaluationDataset.from_csv(WORK / "q.csv")
    check("JSON, JSONL and CSV give the same dataset version", a.version == b.version == c.version)
    split = a.with_splits(seed=1, ratios=SplitRatios(0.5, 0.25, 0.25))
    again = EvaluationDataset.from_records(list(reversed(QUESTIONS))).with_splits(
        seed=1, ratios=SplitRatios(0.5, 0.25, 0.25)
    )
    by_id = {e.id: e.split for e in split.examples}
    check(
        "split assignment is stable across input order",
        all(by_id[e.id] is e.split for e in again.examples),
    )
    counts = {s.value: sum(e.split is s for e in split.examples) for s in DatasetSplit}
    say(f"  split counts: {counts}")
    try:
        check("select(OPTIMIZE) works", len(split.select(DatasetSplit.OPTIMIZE).examples) > 0)
    except Exception as error:
        check("select(OPTIMIZE) works", False, repr(error))


# ======================================================================================= LANGCHAIN
def langchain_optimizer(store, cache, callbacks, ragas_llm, ragas_embeddings):
    from ragas.metrics import Faithfulness

    space = SearchSpace(
        {
            "top_k": IntegerRange(1, 3),
            "style": Categorical(("terse", "grounded")),
            "temperature": Categorical((0.0, 0.4)),
        }
    )
    return Optimizer(
        adapter=LangChainAdapter(
            factory=apps.langchain_factory(),
            input_key="input",
            output_mapper=apps.langchain_output,
            token_prices={apps.CHAT_MODEL: (0.40, 1.60)},
            identity={
                "app": "brightwave-langchain",
                "rev": 1,
                "model": apps.CHAT_MODEL,
                "embed": apps.EMBED_MODEL,
            },
        ),
        strategy=RandomSearch(space, seed=11),
        evaluators=(
            MetricEvaluator("answer_recall", apps.answer_recall),
            apps.RetrievalEvaluator(),
            RagasEvaluator(
                metrics=(Faithfulness(),),
                sample_mapper=lambda out, ex: {
                    "user_input": ex.query,
                    "response": out["answer"],
                    "retrieved_contexts": out["contexts"],
                },
                llm=ragas_llm,
                embeddings=ragas_embeddings,
            ),
        ),
        objective=Objective(
            (
                ObjectiveTerm("answer_recall", 0.5, minimum=0.0, maximum=1.0),
                ObjectiveTerm("ragas.faithfulness", 0.3, minimum=0.0, maximum=1.0),
                ObjectiveTerm("retrieval_recall", 0.2, minimum=0.0, maximum=1.0),
            )
        ),
        store=store,
        cache=cache,
        callbacks=callbacks,
        settings=settings(concurrency=2, sample_concurrency=4),
        stop_conditions=(
            MaxTrials(4),
            TargetScore(1.01),
            NoImprovement(patience=10),
            MaxFailures(3),
        ),
        retry_policy=RetryPolicy(
            max_retries=1, sample_timeout_seconds=90, trial_timeout_seconds=600
        ),
    )


async def langchain_section():
    from langchain_openai import OpenAIEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper

    ragas_llm = LangchainLLMWrapper(apps.chat(0.0, max_tokens=2000))
    ragas_emb = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(
            model=apps.EMBED_MODEL,
            api_key=apps.KEY,
            base_url=apps.BASE,
            check_embedding_ctx_length=False,
        )
    )
    data = (
        EvaluationDataset.from_json(WORK / "q.json")
        if (WORK / "q.json").exists()
        else EvaluationDataset.from_records(QUESTIONS)
    )
    store, cache = SQLiteStore(WORK / "lc2.db"), SQLiteCache(WORK / "lc2-cache.db")
    audit = Audit()
    mlflow_cb = MLflowCallback(
        store,
        tracking_uri=f"sqlite:///{(WORK / 'mlflow2.db').as_posix()}",
        tags={"app": "langchain", "api_key": "must-be-redacted"},
    )
    t0 = time.time()
    result = await langchain_optimizer(
        store, cache, [audit, mlflow_cb], ragas_llm, ragas_emb
    ).aoptimize(data, study_name="brightwave-langchain")
    say(f"  first run took {time.time() - t0:.0f}s")
    report(result, "LangChain study")
    check("study completed", result.study_status.value == "completed")
    check("all trials succeeded", len(result.successful_trials) == len(result.trials))
    check(
        "token usage captured from LangChain messages",
        result.usage.input_tokens > 0,
        f"{result.usage.input_tokens} in",
    )
    check(
        "cost estimated from token_prices",
        result.usage.estimated_cost > 0,
        f"${result.usage.estimated_cost:.5f} ({result.usage.status.value})",
    )
    cov = {t.sequence: t.metric("ragas.faithfulness").coverage for t in result.successful_trials}
    check("RAGAS judged every sample (coverage 1.0)", all(c == 1.0 for c in cov.values()), cov)
    check("best trial is the top-ranked trial", result.best_trial is result.ranked_trials[0])
    leaders = result.metric_leaders("answer_recall")
    check(
        "metric_leaders ranks answer_recall descending",
        all(
            leaders[i].metric("answer_recall").value >= leaders[i + 1].metric("answer_recall").value
            for i in range(len(leaders) - 1)
        ),
    )
    faith = [t.metric("ragas.faithfulness") for t in result.successful_trials]
    check(
        "RAGAS faithfulness scored by a real judge",
        all(m and m.value is not None for m in faith),
        [round(m.value, 3) if m and m.value is not None else None for m in faith],
    )
    result.write_json(WORK / "lc-result.json")
    result.write_csv(WORK / "lc-trials.csv")
    rows = list(csv.DictReader((WORK / "lc-trials.csv").open(encoding="utf-8")))
    check("CSV export has one row per trial", len(rows) == len(result.trials))
    check(
        "callback saw ordered events",
        [s for s, _ in audit.events] == sorted(s for s, _ in audit.events),
        f"{len(audit.events)} events",
    )
    failed_cb = [e for e in store.list_events(result.study_id) if e.type == "callback.failed"]
    check("no callback failures recorded", not failed_cb, [e.payload for e in failed_cb])

    # MLflow mirror
    import mlflow

    client = mlflow.MlflowClient(tracking_uri=f"sqlite:///{(WORK / 'mlflow2.db').as_posix()}")
    runs = client.search_runs(["0"], filter_string=f"tags.`tunarag.study_id` = '{result.study_id}'")
    check("MLflow has exactly one run for the study", len(runs) == 1, len(runs))
    if runs:
        run = runs[0]
        check("MLflow run FINISHED", run.info.status == "FINISHED", run.info.status)
        check(
            "MLflow tags redacted the secret-looking tag",
            run.data.tags.get("api_key") == "***redacted***",
            run.data.tags.get("api_key"),
        )
        hist = client.get_metric_history(run.info.run_id, "tunarag.objective")
        check(
            "MLflow objective history has one point per trial",
            len(hist) == len(result.successful_trials),
            len(hist),
        )

    # Cache: identical semantics, new study -> every trial a cache hit, no provider tokens
    store2 = SQLiteStore(WORK / "lc2.db")
    r2 = await langchain_optimizer(store2, cache, [], ragas_llm, ragas_emb).aoptimize(
        data, study_name="brightwave-langchain-again"
    )
    check(
        "second identical study: all trials cache hits",
        all(t.cached for t in r2.trials),
        [t.cached for t in r2.trials],
    )
    check(
        "second identical study: zero provider tokens",
        r2.usage.input_tokens == 0,
        r2.usage.input_tokens,
    )
    check(
        "cached scores equal original scores",
        [round(t.objective.score, 9) for t in r2.trials]
        == [round(t.objective.score, 9) for t in result.trials],
    )

    # Resume a completed study: returns without execution
    r3 = await langchain_optimizer(
        SQLiteStore(WORK / "lc2.db"), None, [], ragas_llm, ragas_emb
    ).aresume(data, study_id=result.study_id)
    check(
        "resume of completed study returns same best without calls",
        r3.best_candidate == result.best_candidate
        and r3.usage.input_tokens == result.usage.input_tokens,
    )
    cache.close()


# ======================================================================================= LANGGRAPH
class OpenRouterSuggester:
    """Real LLM search provider: asks the model for the next JSON candidate."""

    def __init__(self):
        self.requests = []

    async def suggest(self, request):
        self.requests.append(request)
        history = [
            {
                "candidate": dict(o.candidate.parameters),
                "metrics": {m.name: m.value for m in o.metrics},
            }
            for o in request.observations
        ]
        prompt = (
            "Propose the next RAG configuration to try as a JSON object with exactly the keys of "
            f"this search space: {json.dumps(request.search_space, default=list)}. "
            f"Previous results: {json.dumps(history)}. Do not repeat a previous candidate. "
            "Reply with JSON only."
        )
        reply = await apps.chat(0.7, max_tokens=300).ainvoke(prompt)
        text = reply.content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        return json.loads(text)

    def fingerprint(self):
        return {"provider": "openrouter", "model": apps.CHAT_MODEL, "v": 1}


async def langgraph_section():
    data = EvaluationDataset.from_records(QUESTIONS)
    store = SQLiteStore(WORK / "lg.db")
    suggester = OpenRouterSuggester()
    space = SearchSpace({"top_k": IntegerRange(1, 3), "style": Categorical(("terse", "grounded"))})
    optimizer = Optimizer(
        adapter=LangGraphAdapter(
            apps.langgraph_graph(),
            output_mapper=apps.langgraph_output,
            identity={"app": "brightwave-langgraph", "rev": 1},
        ),
        strategy=LLMSearch(space, suggester, max_suggestion_attempts=2, fallback_seed=5),
        evaluators=(
            MetricEvaluator("answer_recall", apps.answer_recall),
            apps.RetrievalEvaluator(),
        ),
        objective=Objective(
            (ObjectiveTerm("answer_recall", 0.7), ObjectiveTerm("retrieval_recall", 0.3))
        ),
        store=store,
        settings=settings(concurrency=1, sample_concurrency=4),
        stop_conditions=(MaxTrials(4), TimeBudget(600)),
    )
    result = await optimizer.aoptimize(data, study_name="brightwave-langgraph")
    report(result, "LangGraph study (LLMSearch)")
    check("study completed", result.study_status.value == "completed")
    check(
        "candidate params reached the graph via config (top_k changes context_count)",
        {t.candidate.parameters["top_k"] for t in result.successful_trials}
        == {round(t.metric("context_count").value) for t in result.successful_trials},
    )
    check(
        "token usage auto-captured from AIMessage in graph state",
        result.usage.input_tokens > 0,
        result.usage.input_tokens,
    )
    check("LLM provider was consulted", len(suggester.requests) > 0, len(suggester.requests))
    check(
        "LLM saw prior observations on later suggestions",
        any(len(r.observations) > 0 for r in suggester.requests),
    )
    distinct = {tuple(sorted(t.candidate.parameters.items())) for t in result.trials}
    check("all trials distinct candidates", len(distinct) == len(result.trials))


# ======================================================================================= ADK
async def adk_section():
    data = EvaluationDataset.from_records(QUESTIONS)
    runner = apps.adk_runner()
    space = SearchSpace({"top_k": IntegerRange(1, 3), "style": Categorical(("terse", "grounded"))})
    evidence = []

    def mapper(final_event):  # README: output_mapper "allowing retrieval evidence to be exposed"
        evidence.append(
            {
                "has_function_responses": bool(final_event.get_function_responses()),
                "state_delta_keys": list((final_event.actions.state_delta or {}).keys()),
            }
        )
        text = "".join(p.text or "" for p in (final_event.content.parts or ()) if not p.thought)
        return {"answer": text}

    optimizer = Optimizer(
        adapter=GoogleADKAdapter(
            runner,
            state_mapper=lambda c: {
                "top_k": c.parameters["top_k"],
                "style": apps.PROMPTS[c.parameters["style"]],
            },
            identity={"app": "brightwave-adk", "rev": 1},
        ),
        strategy=RandomSearch(space, seed=2),
        evaluators=(
            MetricEvaluator("answer_recall", apps.answer_recall),
            apps.RetrievalEvaluator(),
        ),
        objective=Objective(
            (ObjectiveTerm("answer_recall", 0.7), ObjectiveTerm("retrieval_recall", 0.3))
        ),
        store=SQLiteStore(WORK / "adk2.db"),
        settings=settings(concurrency=2, sample_concurrency=4),
        stop_conditions=(MaxTrials(4),),
        retry_policy=RetryPolicy(
            max_retries=1, sample_timeout_seconds=120, trial_timeout_seconds=600
        ),
    )
    result = await optimizer.aoptimize(data, study_name="brightwave-adk")
    report(result, "Google ADK study")
    check("study completed", result.study_status.value == "completed")
    check("all trials succeeded", len(result.successful_trials) == len(result.trials))
    check("ADK token usage captured", result.usage.input_tokens > 0, result.usage.input_tokens)
    sessions = await runner.session_service.list_sessions(
        app_name=runner.app_name, user_id="tunarag-evaluation"
    )
    check(
        "every evaluation session was deleted", len(sessions.sessions) == 0, len(sessions.sessions)
    )
    cov = [t.metric("retrieval_recall") for t in result.successful_trials]
    check(
        "retrieval evidence now reaches evaluators (tool_responses)",
        all(m is not None and m.value is not None and m.coverage == 1.0 for m in cov),
        [None if m is None else (m.value, m.coverage) for m in cov],
    )
    say(f"  retrieval_recall metric: {[None if m is None else (m.value, m.coverage) for m in cov]}")


# ======================================================================================= SYNTHETIC
class OpenRouterQA:
    async def generate(self, request):
        prompt = (
            f"From this text, write {request.count} question/answer pairs as a JSON list of objects "
            "with keys question, answer, quote (an exact substring of the text supporting the answer)."
            f" Reply with JSON only.\n\nText: {request.document.text}"
        )
        reply = await apps.chat(0.0, max_tokens=800).ainvoke(prompt)
        text = reply.content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        items = []
        for row in json.loads(text)[: request.count]:
            start = request.document.text.find(row["quote"])
            spans = (SourceSpan(start, start + len(row["quote"])),) if start >= 0 else ()
            items.append(SyntheticQA(row["question"], row["answer"], spans, confidence=0.9))
        usage = reply.usage_metadata or {}
        return SyntheticGenerationResponse(
            tuple(items),
            (
                UsageRecord(
                    "synthetic.llm",
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                ),
            ),
        )


async def synthetic_section():
    docs = [SourceDocument(doc_id, text) for doc_id, text in list(DOCS.items())[:3]]
    generated = await SyntheticDatasetBuilder(
        OpenRouterQA(), samples_per_document=2, seed=3, generator_version="probe-1"
    ).generate(docs)
    ds = generated.dataset
    check("synthetic dataset has count x docs examples", len(ds.examples) == 6, len(ds.examples))
    check(
        "examples are marked synthetic and unreviewed",
        all(e.synthetic and e.metadata["review_status"] == "unreviewed" for e in ds.examples),
    )
    check(
        "source spans resolve into the document text",
        all(
            all(c in DOCS[e.relevant_document_ids[0]] for c in e.reference_contexts)
            for e in ds.examples
        ),
    )
    check("generation usage recorded", sum(u.input_tokens or 0 for u in generated.usage) > 0)
    for e in ds.examples[:3]:
        say(f"    Q: {e.query} | A: {e.reference_answer}")


asyncio.run(
    {
        "data": data_section,
        "langchain": langchain_section,
        "langgraph": langgraph_section,
        "adk": adk_section,
        "synthetic": synthetic_section,
    }[SECTION]()
)
