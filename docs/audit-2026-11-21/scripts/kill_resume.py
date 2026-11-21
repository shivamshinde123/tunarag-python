"""Hard-kill a running study, then resume it. Usage: kill_resume.py run|resume <dir>."""
import asyncio
import json
import sys
import time
from pathlib import Path

from langchain_core.runnables import RunnableLambda

from tunarag import (
    EvaluationDataset, IntegerRange, LangChainAdapter, MaxTrials, MetricEvaluator, Objective,
    ObjectiveTerm, Optimizer, RandomSearch, ResumeError, RetryPolicy, SearchSpace, Settings,
    SQLiteStore,
)

mode, folder = sys.argv[1], Path(sys.argv[2])
CALLS = folder / "calls.jsonl"  # every real pipeline call, appended by both processes


async def pipeline(inputs, config):
    k = config["configurable"]["k"]
    with CALLS.open("a") as f:
        f.write(json.dumps({"pid": mode, "k": k, "q": inputs["question"]}) + "\n")
    await asyncio.sleep(1.0)
    return {"answer": f"k={k}"}


def build(store):
    return Optimizer(
        adapter=LangChainAdapter(RunnableLambda(pipeline), identity={"kill-test": 1}),
        strategy=RandomSearch(SearchSpace({"k": IntegerRange(1, 6)}), seed=3),
        evaluators=[MetricEvaluator("score", lambda o, e: float(o["answer"][-1]) / 6)],
        objective=Objective((ObjectiveTerm("score"),)), store=store,
        settings=Settings.resolve(overrides={"concurrency": 2, "sample_concurrency": 3}, environ={}),
        stop_conditions=[MaxTrials(6)],
        retry_policy=RetryPolicy(max_retries=0, trial_timeout_seconds=2.0),  # lease = 62 s
    )


DATA = EvaluationDataset.from_records([{"query": f"q{i}"} for i in range(3)])


async def main():
    store = SQLiteStore(folder / "study.db")
    if mode == "run":
        await build(store).aoptimize(DATA, study_name="kill-me")
        return
    sid, status = store._connection.execute("SELECT id, status FROM studies").fetchone()
    print("before resume: study", status, [(r[0], r[1]) for r in store._connection.execute(
        "SELECT sequence, status FROM trials ORDER BY sequence")])
    started = time.time()
    while True:
        try:
            result = await build(SQLiteStore(folder / "study.db")).aresume(DATA, study_id=sid)
            break
        except ResumeError as error:
            if not error.retryable:
                print("RESUME REFUSED:", error)
                return
            print(f"  lease still active after {time.time() - started:.0f}s, retrying...")
            await asyncio.sleep(10)
    print(f"resumed after {time.time() - started:.0f}s: status={result.study_status.value} "
          f"stop={result.stop_reason} trials={[(t.sequence, t.candidate.parameters['k'], t.status.value) for t in result.trials]} "
          f"best={result.best_candidate.parameters if result.best_candidate else None}")


asyncio.run(main())
