import json
import sys
from pathlib import Path

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

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
    url = sys.argv[3]
    chat = ChatOpenAI(
        api_key="local-test-only",
        base_url=url,
        model="openai/gpt-4.1-mini",
        max_tokens=512,
        max_retries=1,
        timeout=120,
        temperature=0,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(
                content="Answer briefly from this approved paper excerpt: "
                + (directory / "context.txt").read_text(encoding="utf-8"),
            ),
            ("human", "{input}"),
        ]
    )

    class SaveStudy:
        async def on_event(self, event):
            (directory / "study-id.txt").write_text(event.study_id)

    store = SQLiteStore(directory / "study.db")
    runner = Optimizer(
        adapter=LangChainAdapter(
            prompt | chat, input_key="input", identity={"provider-recovery": url}
        ),
        strategy=RandomSearch(SearchSpace({"marker": IntegerRange(1, 2)}), seed=0),
        evaluators=(
            MetricEvaluator("nonempty", lambda output, example: float(bool(output.content))),
        ),
        objective=Objective((ObjectiveTerm("nonempty"),)),
        store=store,
        settings=Settings.resolve(overrides={"max_trials": 2, "cache_policy": "off"}, environ={}),
        retry_policy=RetryPolicy(max_retries=0, trial_timeout_seconds=30),
        callbacks=(SaveStudy(),),
    )
    dataset = EvaluationDataset.from_records([{"id": "q", "query": "How many heads are used?"}])
    try:
        result = (
            runner.optimize(dataset, study_name="provider-recovery")
            if mode == "start"
            else runner.resume(dataset, study_id=(directory / "study-id.txt").read_text())
        )
        assert len(result.successful_trials) == 2 and not result.failed_trials
        result.write_json(directory / "result.json")
        (directory / "completed.json").write_text(json.dumps({"study_id": result.study_id}))
    finally:
        runner.close()
        store.close()


if __name__ == "__main__":
    main()
