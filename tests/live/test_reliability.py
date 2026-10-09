import asyncio
import json
import time
from pathlib import Path

import pytest

from tunarag import (
    Candidate,
    Categorical,
    EvaluationDataset,
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

from .campaign import PipelineBuilder
from .quality import ReferenceQualityEvaluator

pytestmark = [pytest.mark.live, pytest.mark.paid, pytest.mark.campaign]


def reliability_data():
    records = json.loads(Path(__file__).with_name("reliability_questions.json").read_text())
    development = EvaluationDataset.from_records(
        [item for item in records if item["split"] == "optimize"]
    )
    held_out = EvaluationDataset.from_records([item for item in records if item["split"] == "test"])
    return development, held_out, {item["id"]: item["facts"] for item in records}


def small_space():
    return SearchSpace(
        {
            "top_k": Categorical((1, 3)),
            "prompt_style": Categorical(("brief", "structured")),
            "chunk_size": Categorical((1000,)),
            "overlap": Categorical((80,)),
            "search_type": Categorical(("similarity",)),
        }
    )


def paper_builder(provider, pytestconfig, tmp_path):
    from langchain_community.document_loaders import PyPDFLoader

    documents = PyPDFLoader(pytestconfig.getoption("--live-pdf")).load()
    assert "Attention Is All You Need" in documents[0].page_content
    return PipelineBuilder(documents, provider, "langchain", tmp_path)


def test_reliability_quality(provider, pytestconfig, tmp_path):
    development, held_out, facts = reliability_data()
    builder = paper_builder(provider, pytestconfig, tmp_path)
    judge = ReferenceQualityEvaluator(provider["judge"], facts)
    winners = []
    rows = []

    async def exercise():
        for seed in (1, 4, 7):
            runner = Optimizer(
                adapter=builder.adapter(),
                strategy=RandomSearch(small_space(), seed=seed),
                evaluators=(judge,),
                objective=Objective((ObjectiveTerm("quality.reference_score"),)),
                store=SQLiteStore(tmp_path / f"seed-{seed}.db"),
                settings=Settings.resolve(overrides={"max_trials": 2}, environ={}),
                retry_policy=RetryPolicy(max_retries=0, trial_timeout_seconds=300),
            )
            try:
                result = await runner.aoptimize(development, study_name=f"repeat-{seed}")
                assert len(result.successful_trials) == 2 and not result.failed_trials
                assert result.best_trial.objective.score == max(
                    trial.objective.score for trial in result.trials
                )
                result.write_json(tmp_path / f"seed-{seed}.json")
                winners.append((f"seed-{seed}", result.best_candidate))
            finally:
                runner.close()
        baseline = Candidate(
            {
                "top_k": 1,
                "prompt_style": "brief",
                "chunk_size": 1000,
                "overlap": 80,
                "search_type": "similarity",
            }
        )
        for label, candidate in [("baseline", baseline), *winners]:
            for example in held_out.examples:
                output = await builder.independent_run(candidate, example)
                metrics = await judge.evaluate(output, example)
                rows.append(
                    {
                        "configuration": label,
                        "parameters": dict(candidate.parameters),
                        "example_id": example.id,
                        "output": output,
                        "scores": {metric.name: metric.value for metric in metrics},
                    }
                )
                (tmp_path / "held-out.json").write_text(json.dumps(rows, indent=2))
        assert len(rows) == 16
        (tmp_path / "judgments.json").write_text(json.dumps(judge.records, indent=2))

    asyncio.run(asyncio.wait_for(exercise(), timeout=900))


def test_reliability_load(provider, pytestconfig, tmp_path):
    from langchain_core.runnables import RunnableLambda

    development, _, _ = reliability_data()
    builder = paper_builder(provider, pytestconfig, tmp_path)
    rows = []

    async def exercise():
        for limit in (1, 2, 4):
            active = 0
            peak = 0

            async def enter(value):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                return value

            async def leave(value):
                nonlocal active
                active -= 1
                return value

            def factory(candidate):
                return RunnableLambda(enter) | builder.factory(candidate) | RunnableLambda(leave)

            original = builder.adapter()
            adapter = LangChainAdapter(
                factory=factory,
                input_key="input",
                output_mapper=original._output_mapper,
                identity={"load": limit},
            )
            runner = Optimizer(
                adapter=adapter,
                strategy=RandomSearch(small_space(), seed=1),
                evaluators=(
                    MetricEvaluator(
                        "nonempty", lambda output, example: float(bool(output["answer"]))
                    ),
                ),
                objective=Objective((ObjectiveTerm("nonempty"),)),
                store=SQLiteStore(tmp_path / f"load-{limit}.db"),
                settings=Settings.resolve(
                    overrides={
                        "max_trials": 2,
                        "concurrency": 1 if limit == 1 else 2,
                        "sample_concurrency": 2 if limit == 4 else 1,
                    },
                    environ={},
                ),
                retry_policy=RetryPolicy(max_retries=0, trial_timeout_seconds=300),
            )
            started = time.monotonic()
            try:
                result = await runner.aoptimize(development, study_name=f"load-{limit}")
                assert len(result.successful_trials) == 2 and not result.failed_trials
                assert active == 0 and peak == limit
                rows.append(
                    {
                        "requested": limit,
                        "peak": peak,
                        "seconds": time.monotonic() - started,
                        "successful_trials": 2,
                    }
                )
            finally:
                runner.close()
            (tmp_path / "load.json").write_text(json.dumps(rows, indent=2))

    asyncio.run(asyncio.wait_for(exercise(), timeout=600))


def test_reliability_recovery(provider, pytestconfig, tmp_path):
    import os
    import subprocess
    import sys
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from langchain_community.document_loaders import PyPDFLoader

    import tunarag

    documents = PyPDFLoader(pytestconfig.getoption("--live-pdf")).load()
    (tmp_path / "context.txt").write_text(documents[3].page_content[:3000], encoding="utf-8")
    blocked = threading.Event()
    release = threading.Event()
    counter_lock = threading.Lock()
    remote = []
    local = []
    errors = []

    class Gateway(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return None

        def do_POST(self):
            try:
                assert self.path == "/v1/chat/completions"
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with counter_lock:
                    local.append(body)
                    number = len(local)
                if number == 1:
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":{"message":"controlled local retry"}}')
                    return
                response = provider["chat"].root_client.chat.completions.create(**body)
                with counter_lock:
                    remote.append(response.model_dump())
                    paid_number = len(remote)
                if paid_number == 2:
                    blocked.set()
                    assert release.wait(180)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response.model_dump_json().encode())
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except Exception as error:
                errors.append(type(error).__name__ + ": " + str(error))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1"
    environment = dict(os.environ)
    for name in list(environment):
        if "KEY" in name.upper() or "TOKEN" in name.upper():
            environment.pop(name)
    environment["PYTHONPATH"] = str(Path(tunarag.__file__).resolve().parents[1])
    worker = Path(__file__).with_name("provider_recovery_worker.py")
    processes = []
    streams = []

    def launch(mode):
        stream = (tmp_path / f"worker-{mode}-{len(processes)}.log").open("w")
        streams.append(stream)
        process = subprocess.Popen(
            [sys.executable, str(worker), str(tmp_path), mode, url],
            env=environment,
            stdout=stream,
            stderr=stream,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        processes.append(process)
        return process

    started = time.monotonic()
    store = SQLiteStore(tmp_path / "study.db")
    try:
        first = launch("start")
        deadline = time.monotonic() + 90
        while not blocked.wait(0.2) and first.poll() is None and time.monotonic() < deadline:
            pass
        assert blocked.is_set(), "Worker did not reach the blocked second provider reply"
        first.kill()
        first.wait(timeout=15)
        release.set()
        study_id = (tmp_path / "study-id.txt").read_text()
        trials = store.list_trials(study_id)
        assert sum(trial.status.value == "succeeded" for trial in trials) == 1
        attempts = [attempt for trial in trials for attempt in store.list_attempts(trial.id)]
        running = [attempt for attempt in attempts if attempt.status.value == "running"]
        assert len(running) == 1
        expiry = running[0].lease_expires_at
        assert expiry is not None
        wait_seconds = max(0, expiry - time.time()) + 0.2
        time.sleep(wait_seconds)
        resumed = launch("resume")
        assert resumed.wait(timeout=90) == 0
        assert len(remote) == 3 and len(local) == 4 and not errors
        attempts = [attempt for trial in trials for attempt in store.list_attempts(trial.id)]
        assert sorted(attempt.status.value for attempt in attempts) == [
            "abandoned",
            "succeeded",
            "succeeded",
        ]
        reload = launch("resume")
        assert reload.wait(timeout=90) == 0
        assert len(remote) == 3 and len(local) == 4
        (tmp_path / "recovery.json").write_text(
            json.dumps(
                {
                    "paid_responses": len(remote),
                    "local_requests": len(local),
                    "controlled_503": 1,
                    "lost_paid_reply": 1,
                    "attempts": [attempt.status.value for attempt in attempts],
                    "real_lease_wait_seconds": wait_seconds,
                    "seconds": time.monotonic() - started,
                    "reload_added_requests": 0,
                },
                indent=2,
            )
        )
    finally:
        release.set()
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=15)
        for stream in streams:
            stream.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        store.close()


def test_reliability_adk(provider, pytestconfig, tmp_path, monkeypatch):
    import itertools

    from tunarag import LLMSearch

    from .adk_tools import ToolPipeline
    from .campaign import ChatSuggestionProvider

    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "true")
    development, _, facts = reliability_data()
    builder = paper_builder(provider, pytestconfig, tmp_path)
    builder.factory(
        Candidate(
            {
                "top_k": 1,
                "prompt_style": "brief",
                "chunk_size": 1000,
                "overlap": 80,
                "search_type": "similarity",
            }
        )
    )
    pipeline = ToolPipeline(builder.stores[(1000, 80)], provider["chat"])
    suggestions = ChatSuggestionProvider(provider["chat"])
    dimensions = small_space().describe()
    suggestions.choices = [
        dict(zip(dimensions, values, strict=True))
        for values in itertools.product(*(item["values"] for item in dimensions.values()))
    ]
    judge = ReferenceQualityEvaluator(provider["judge"], facts)
    store = SQLiteStore(tmp_path / "adk.db")

    def optimizer():
        return Optimizer(
            adapter=pipeline.adapter(),
            strategy=LLMSearch(small_space(), suggestions, max_suggestion_attempts=1),
            evaluators=(judge,),
            objective=Objective((ObjectiveTerm("quality.reference_score"),)),
            store=store,
            settings=Settings.resolve(
                overrides={"max_trials": 2, "concurrency": 2, "sample_concurrency": 2}, environ={}
            ),
            retry_policy=RetryPolicy(max_retries=0, trial_timeout_seconds=300),
        )

    async def exercise():
        runner = optimizer()
        try:
            result = await runner.aoptimize(development, study_name="adk-tools")
            assert len(result.successful_trials) == 2 and not result.failed_trials
            assert suggestions.valid == 2
            assert [trial.sequence for trial in result.trials] == [0, 1]
            events = store.list_events(result.study_id)
            assert [event.sequence for event in events] == list(range(len(events)))
            assert not any(event.type == "callback.failed" for event in events)
            assert len(pipeline.calls) == len(pipeline.sessions) == 4
            assert 2 <= pipeline.peak <= 4 and pipeline.active == 0
            assert all(
                sum(item.component == "google_adk.model" for item in trial.usage) == 4
                for trial in result.trials
            )
            used = provider["budget"].used
            resumed = await runner.aresume(development, study_id=result.study_id)
            assert resumed.best_candidate == result.best_candidate
            assert provider["budget"].used == used and len(pipeline.calls) == 4
            result.write_json(tmp_path / "result.json")
            (tmp_path / "tools.json").write_text(
                json.dumps(
                    {
                        "calls": pipeline.calls,
                        "peak": pipeline.peak,
                        "suggestions": suggestions.requests,
                    },
                    indent=2,
                )
            )
        finally:
            runner.close()
            await pipeline.close()

    asyncio.run(asyncio.wait_for(exercise(), timeout=600))
