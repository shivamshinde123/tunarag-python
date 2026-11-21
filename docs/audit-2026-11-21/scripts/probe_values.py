"""Probe non-finite values and dataset identity edge cases. PYTHONPATH=<repo>/src."""
import asyncio
import math

from langchain_core.runnables import RunnableLambda

from tunarag import (
    DatasetError, EvaluationDataset, IntegerRange, LangChainAdapter, MaxTrials, MetricValue,
    Objective, ObjectiveTerm, Optimizer, RandomSearch, SearchSpace, Settings, SQLiteStore,
    UsageRecord,
)

DATA = EvaluationDataset.from_records([{"query": "q1"}, {"query": "q2"}])


class NaNEvaluator:  # a custom evaluator, as the README shows (class with evaluate())
    def __init__(self, value):
        self.value = value

    async def evaluate(self, output, example):
        return (MetricValue("score", self.value),)


def optimizer(evaluator, adapter, store):
    return Optimizer(adapter=adapter, strategy=RandomSearch(SearchSpace({"k": IntegerRange(1, 3)}), seed=1),
                     evaluators=[evaluator], objective=Objective((ObjectiveTerm("score"),)), store=store,
                     settings=Settings.resolve(overrides={"concurrency": 1}, environ={}),
                     stop_conditions=[MaxTrials(3)])


async def run(label, evaluator, adapter):
    store = SQLiteStore(":memory:")
    try:
        r = await optimizer(evaluator, adapter, store).aoptimize(DATA, study_name=label)
        statuses = [t.status.value for t in r.trials]
        try:
            r.to_json()
            exported = "to_json ok"
        except Exception as error:
            exported = f"to_json {type(error).__name__}"
        print(f"{label}: study={r.study_status.value} trials={statuses} {exported}")
    except Exception as error:
        sid = store._connection.execute("SELECT id, status FROM studies").fetchone()
        print(f"{label}: WHOLE STUDY RAISED {type(error).__name__}: {error} (study status in DB: {sid[1]})")


async def main():
    plain = LangChainAdapter(RunnableLambda(lambda x: {"a": 1}), identity={"r": 1})
    await run("P5 custom evaluator returns NaN", NaNEvaluator(math.nan), plain)
    await run("P5b custom evaluator returns inf", NaNEvaluator(math.inf), plain)
    nan_cost = LangChainAdapter(RunnableLambda(lambda x: {"a": 1}), identity={"r": 2},
                                usage_mapper=lambda o: [UsageRecord("llm", cost=math.nan)])
    await run("P6 usage cost is NaN", NaNEvaluator(1.0), nan_cost)

    try:
        EvaluationDataset.from_records([{"query": "same question"}, {"query": "same question"}])
        print("P12 duplicate rows without ids: accepted")
    except DatasetError as error:
        print(f"P12 duplicate rows without ids: DatasetError ({error.details})")
    a = EvaluationDataset.from_records([{"id": "1", "query": "x"}, {"id": "2", "query": "y"}])
    b = EvaluationDataset.from_records([{"id": "2", "query": "y"}, {"id": "1", "query": "x"}])
    print(f"P13 same rows, different order -> same version? {a.version == b.version}")


asyncio.run(main())
