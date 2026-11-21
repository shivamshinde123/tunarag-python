"""Does MLflow keep 'one run per study' across a hard kill + resume? Usage: mlflow_resume.py run|resume|inspect <dir>"""

import asyncio
import sys
from pathlib import Path

from langchain_core.runnables import RunnableLambda

from tunarag import (
    EvaluationDataset,
    IntegerRange,
    LangChainAdapter,
    MaxTrials,
    MetricEvaluator,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RandomSearch,
    ResumeError,
    RetryPolicy,
    SearchSpace,
    Settings,
    SQLiteStore,
)
from tunarag.integrations import MLflowCallback

mode, folder = sys.argv[1], Path(sys.argv[2])
URI = f"sqlite:///{(folder / 'mlflow.db').as_posix()}"


async def pipeline(inputs, config):
    await asyncio.sleep(1.0)
    return {"answer": str(config["configurable"]["k"])}


def build(store):
    return Optimizer(
        adapter=LangChainAdapter(RunnableLambda(pipeline), identity={"mlflow-test": 1}),
        strategy=RandomSearch(SearchSpace({"k": IntegerRange(1, 6)}), seed=3),
        evaluators=[MetricEvaluator("score", lambda o, e: float(o["answer"]) / 6)],
        objective=Objective((ObjectiveTerm("score"),)),
        store=store,
        callbacks=[MLflowCallback(store, tracking_uri=URI)],
        settings=Settings.resolve(overrides={"concurrency": 1}, environ={}),
        stop_conditions=[MaxTrials(4)],
        retry_policy=RetryPolicy(max_retries=0, trial_timeout_seconds=1.5),
    )


DATA = EvaluationDataset.from_records([{"query": "q"}])


async def main():
    store = SQLiteStore(folder / "study.db")
    if mode == "run":
        await build(store).aoptimize(DATA, study_name="mlflow-kill")
    elif mode == "resume":
        sid = store._connection.execute("SELECT id FROM studies").fetchone()[0]
        while True:
            try:
                r = await build(store).aresume(DATA, study_id=sid)
                print("resumed:", r.study_status.value, len(r.trials), "trials")
                return
            except ResumeError as error:
                if not error.retryable:
                    raise
                await asyncio.sleep(10)
    else:
        import mlflow

        sid = store._connection.execute("SELECT id FROM studies").fetchone()[0]
        client = mlflow.MlflowClient(tracking_uri=URI)
        runs = client.search_runs(["0"], filter_string=f"tags.`tunarag.study_id` = '{sid}'")
        print(f"MLflow runs for one study: {len(runs)}")
        for run in runs:
            steps = [
                m.step for m in client.get_metric_history(run.info.run_id, "tunarag.objective")
            ]
            print(
                f"  run {run.info.run_id[:8]} status={run.info.status} objective steps={sorted(steps)}"
            )


asyncio.run(main())
