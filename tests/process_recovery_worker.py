import json
import os
import sys
import time
from pathlib import Path

from langchain_core.runnables import RunnableLambda

from tunarag import (
    EvaluationDataset,
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
    SQLiteStore,
)


def main():
    directory = Path(sys.argv[1])
    mode = sys.argv[2]
    store = SQLiteStore(
        directory / "study.db", clock=lambda: time.time() + (400 if mode != "crash" else 0)
    )

    def invoke(inputs, config):
        value = config["configurable"]["top_k"]
        with (directory / "calls.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"top_k": value}) + "\n")
        if mode == "crash" and value == 1:
            os._exit(23)
        return value

    class SaveStudy:
        async def on_event(self, event):
            (directory / "study-id.txt").write_text(event.study_id, encoding="utf-8")

    runner = Optimizer(
        adapter=LangChainAdapter(RunnableLambda(invoke), identity={"pipeline": "process-recovery"}),
        strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)}), seed=0),
        evaluators=(MetricEvaluator("quality", lambda output, example: float(output)),),
        objective=Objective((ObjectiveTerm("quality"),)),
        settings=Settings.resolve(
            overrides={
                "max_trials": 2,
                "concurrency": 1,
                "sample_concurrency": 1,
                "cache_policy": "off",
            },
            environ={},
        ),
        retry_policy=RetryPolicy(max_retries=0, trial_timeout_seconds=30),
        store=store,
        callbacks=(SaveStudy(),),
    )
    dataset = EvaluationDataset.from_records([{"id": "q", "query": "question"}])
    try:
        if mode == "crash":
            runner.optimize(dataset, study_name="process-recovery")
            raise AssertionError("worker did not crash")
        study_id = (directory / "study-id.txt").read_text(encoding="utf-8")
        result = runner.resume(dataset, study_id=study_id)
        assert len(result.successful_trials) == 2
        assert result.best_candidate.parameters["top_k"] == 2
        result.write_json(directory / "result.json")
    finally:
        runner.close()
        store.close()


if __name__ == "__main__":
    main()
