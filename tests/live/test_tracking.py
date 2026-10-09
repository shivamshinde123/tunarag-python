import os
import signal
import socket
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from tunarag import (
    IntegerRange,
    LangChainAdapter,
    MetricEvaluator,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RandomSearch,
    SearchSpace,
    Settings,
    SQLiteStore,
)
from tunarag.integrations import MLflowCallback

pytestmark = pytest.mark.live


@pytest.fixture
def tracking_server(tmp_path):
    from mlflow import MlflowClient

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    uri = f"http://127.0.0.1:{port}"
    with (tmp_path / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mlflow",
                "server",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--backend-store-uri",
                "sqlite:///tracking.db",
                "--workers",
                "1",
            ],
            cwd=tmp_path,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        try:
            client = MlflowClient(tracking_uri=uri)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail("MLflow server exited; inspect retained server.log", pytrace=False)
                try:
                    client.search_experiments()
                    break
                except Exception:
                    time.sleep(0.5)
            else:
                pytest.fail("MLflow server did not become ready within 90 seconds", pytrace=False)
            yield client, uri
        finally:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)


def test_live_mlflow_mirrors_authoritative_sqlite(tracking_server, tmp_path):
    from langchain_core.runnables import RunnableLambda

    from tunarag import EvaluationDataset

    client, uri = tracking_server
    experiment = client.create_experiment(f"tunarag-live-{uuid4().hex}")
    store = SQLiteStore(tmp_path / "authoritative.db")
    adapter = LangChainAdapter(
        RunnableLambda(lambda inputs, config: config["configurable"]["top_k"])
    )
    runner = Optimizer(
        adapter=adapter,
        strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)}), seed=0),
        evaluators=(MetricEvaluator("quality", lambda output, example: float(output)),),
        objective=Objective((ObjectiveTerm("quality"),)),
        settings=Settings.resolve(overrides={"max_trials": 2}, environ={}),
        store=store,
        callbacks=(MLflowCallback(store, tracking_uri=uri, experiment_id=experiment),),
    )
    try:
        result = runner.optimize(
            EvaluationDataset.from_records([{"id": "q", "query": "question"}]),
            study_name="live-tracking",
        )
        assert result.best_candidate.parameters["top_k"] == 2
        assert not any(
            event.type == "callback.failed" for event in store.list_events(result.study_id)
        )
        runs = client.search_runs([experiment])
        assert len(runs) == 1
        run = runs[0]
        assert run.info.status == "FINISHED"
        assert run.data.tags["tunarag.study_id"] == result.study_id
        history = client.get_metric_history(run.info.run_id, "quality")
        assert {(entry.step, entry.value) for entry in history} == {
            (trial.sequence, trial.metric("quality").value) for trial in result.successful_trials
        }
        for trial in result.successful_trials:
            assert run.data.params[f"trial.{trial.sequence}.candidate.top_k"] == str(
                trial.candidate.parameters["top_k"]
            )
        result.write_json(tmp_path / "result.json")
    finally:
        runner.close()
        store.close()
