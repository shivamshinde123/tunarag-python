"""Probe README claims against real behaviour. Run with PYTHONPATH=<repo>/src."""
import asyncio

from langchain_core.runnables import RunnableLambda

from tunarag import (
    CachePolicy, CostBudget, EvaluationDataset, IntegerRange, LangChainAdapter, MaxTrials,
    MetricEvaluator, Objective, ObjectiveTerm, Optimizer, RandomSearch, RetryPolicy, SearchSpace,
    Settings, SQLiteCache, SQLiteStore, UsageRecord, ResumeError,
)
from tunarag.store import StudyStatus

DATA = EvaluationDataset.from_records([{"query": "q1"}, {"query": "q2"}])
SPACE = SearchSpace({"top_k": IntegerRange(1, 1)})  # one candidate -> deterministic


def build(adapter, evaluator, *, store=None, cache=None, policy=None, stops=None, retries=0):
    settings = Settings.resolve(overrides={"cache_policy": CachePolicy.READ_WRITE, "max_trials": 1}, environ={})
    return Optimizer(adapter=adapter, strategy=RandomSearch(SPACE, seed=1), evaluators=[evaluator],
                     objective=Objective((ObjectiveTerm("score"),)), store=store, cache=cache,
                     settings=settings, stop_conditions=stops,
                     retry_policy=policy or RetryPolicy(max_retries=retries))


async def p1_cancel_then_resume():
    async def slow(x):
        await asyncio.sleep(5)
        return x
    store = SQLiteStore(":memory:")
    opt = build(LangChainAdapter(RunnableLambda(lambda x: x).with_config() if False else RunnableLambda(slow)),
                MetricEvaluator("score", lambda o, e: 1.0), store=store)
    task = asyncio.create_task(opt.aoptimize(DATA, study_name="ctrl-c"))
    await asyncio.sleep(0.3)
    task.cancel()  # what asyncio.run does on Ctrl-C
    try:
        await task
    except asyncio.CancelledError:
        pass
    sid = store._connection.execute("SELECT id FROM studies").fetchone()[0]
    status = store.get_study(sid).status
    try:
        await build(LangChainAdapter(RunnableLambda(slow)), MetricEvaluator("score", lambda o, e: 1.0),
                    store=store).aresume(DATA, study_id=sid)
        resumed = "resumed OK"
    except ResumeError as error:
        resumed = f"ResumeError: {error}"
    print(f"P1 cancel (Ctrl-C) -> study status={status.value if hasattr(status,'value') else status}; resume -> {resumed}")


async def p2_lambda_evaluator_cache_collision():
    cache = SQLiteCache(":memory:")
    adapter = LangChainAdapter(RunnableLambda(lambda x: x), identity={"rev": 1})
    r1 = await build(adapter, MetricEvaluator("score", lambda o, e: 0.1), cache=cache).aoptimize(DATA, study_name="a")
    r2 = await build(adapter, MetricEvaluator("score", lambda o, e: 0.9), cache=cache).aoptimize(DATA, study_name="b")
    print(f"P2 changed lambda scorer 0.1 -> 0.9: second run score={r2.best_trial.objective.score} cached={r2.best_trial.cached}")


async def p3_adapter_without_identity_cache_collision():
    cache = SQLiteCache(":memory:")
    good = LangChainAdapter(RunnableLambda(lambda x: {"answer": "right"}))
    bad = LangChainAdapter(RunnableLambda(lambda x: {"answer": "wrong"}))
    def ev(o, e):
        return 1.0 if o["answer"] == "right" else 0.0
    await build(good, MetricEvaluator("score", ev), cache=cache).aoptimize(DATA, study_name="good")
    r = await build(bad, MetricEvaluator("score", ev), cache=cache).aoptimize(DATA, study_name="bad")
    print(f"P3 different pipeline, no identity: 'wrong' pipeline scored {r.best_trial.objective.score} cached={r.best_trial.cached}")


async def p4_timeout_drops_spent_usage():
    calls = {"n": 0}

    async def pipeline(x):
        calls["n"] += 1
        if x["question"] == "q2":
            await asyncio.sleep(1.0)  # trips the trial timeout after q1 already "spent" money
        return {"answer": "a", "cost": 1.0}

    adapter = LangChainAdapter(RunnableLambda(pipeline),
                               usage_mapper=lambda out: [UsageRecord("llm", cost=out["cost"])])
    policy = RetryPolicy(max_retries=2, sample_timeout_seconds=5, trial_timeout_seconds=0.3,
                         base_delay_seconds=0, max_delay_seconds=0)
    r = await build(adapter, MetricEvaluator("score", lambda o, e: 1.0), policy=policy,
                    stops=[MaxTrials(1), CostBudget(0.5)]).aoptimize(DATA, study_name="cost")
    t = r.trials[0]
    print(f"P4 trial timeout x3 attempts: pipeline calls={calls['n']} (q1 cost $1 each), "
          f"recorded cost=${r.usage.exact_cost + r.usage.estimated_cost}, trial status={t.status.value}")


async def main():
    for probe in (p1_cancel_then_resume, p2_lambda_evaluator_cache_collision,
                  p3_adapter_without_identity_cache_collision, p4_timeout_drops_spent_usage):
        try:
            await probe()
        except Exception as error:  # report, keep going
            print(f"{probe.__name__} raised {type(error).__name__}: {error}")


asyncio.run(main())
