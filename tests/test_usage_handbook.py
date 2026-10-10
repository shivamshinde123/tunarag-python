import asyncio
import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

from tunarag import Candidate, EvaluationDataset, MetricEvaluator

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_usage_handbook", ROOT / "scripts" / "build_usage_handbook.py"
)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def test_handbook_expansion_and_python_syntax():
    content = BUILDER.expand_source()
    BUILDER.validate(content)
    assert len(BUILDER.python_blocks(content)) == 45
    assert "{{feature:" not in content
    assert "No paid provider calls were made" in content
    assert "not a hard billing firewall" in content
    assert "unresolved adversarial-prompt failure" in content


def test_standalone_example_loads_env_beside_script():
    blocks = BUILDER.python_blocks(BUILDER.expand_source())
    standalone = next(block for block in blocks if "_build_vector_store" in block)
    assert "PROJECT_ROOT = Path(__file__).resolve().parent\n" in standalone
    assert "parents[1]" not in standalone
    assert "asyncio.run(main())" in standalone


def test_holdout_helper_supports_dataset_async_iteration():
    blocks = BUILDER.python_blocks(BUILDER.expand_source())
    helper = next(block for block in blocks if "async def compare_fixed_candidates" in block)
    namespace = {}
    exec(compile(helper, "handbook-heldout", "exec"), namespace)

    class AdapterStub:
        async def run(self, candidate, example):
            return candidate.parameters["answer"], ()

    dataset = EvaluationDataset.from_records(
        [{"id": "storage", "query": "Where?", "reference_answer": "SQLite"}]
    )
    evaluator = MetricEvaluator("correct", lambda output, example: float(output == "SQLite"))
    rows = asyncio.run(
        namespace["compare_fixed_candidates"](
            AdapterStub(),
            (evaluator,),
            dataset,
            Candidate({"answer": "Redis"}),
            Candidate({"answer": "SQLite"}),
        )
    )
    assert [row["label"] for row in rows] == ["baseline", "selected"]
    assert [row["metrics"][0][1] for row in rows] == [0.0, 1.0]


def test_reference_examples_are_expanded_once():
    content = BUILDER.expand_source()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    reference_blocks = re.findall(r"^```python\n(.*?)^```", readme, re.M | re.S)
    assert len(reference_blocks) == 36
    for block in reference_blocks[1:]:
        assert content.count(block) >= 1


def test_usage_template_preserves_tokens_and_labels_estimated_cost():
    block = next(
        block
        for block in BUILDER.python_blocks(BUILDER.expand_source())
        if "def make_usage_mapper" in block
    )
    namespace = {}
    exec(compile(block, "handbook-usage", "exec"), namespace)
    mapper = namespace["make_usage_mapper"](1.0, 2.0, "test-prices")
    records = mapper(
        {"answer": SimpleNamespace(usage_metadata={"input_tokens": 100, "output_tokens": 50})}
    )
    assert records[0].input_tokens == 100
    assert records[1].cost == 0.0002
    assert records[1].status.value == "estimated"
    partial = mapper({"answer": SimpleNamespace(usage_metadata={"input_tokens": 100})})
    assert len(partial) == 1 and partial[0].cost is None


def test_llmsearch_template_returns_mapping_without_real_requests(monkeypatch):
    import sys

    block = next(
        block
        for block in BUILDER.python_blocks(BUILDER.expand_source())
        if "class OpenRouterSuggestions" in block
    )
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"top_k": 2}'))]
        )

    class ClientStub:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

        async def close(self):
            pass

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=ClientStub))
    namespace = {}
    exec(compile(block, "handbook-search", "exec"), namespace)
    provider = namespace["OpenRouterSuggestions"]("placeholder", "test-model")
    request = SimpleNamespace(
        search_space={"top_k": {"type": "integer", "minimum": 1, "maximum": 3}},
        observations=(),
        suggestion_number=0,
        attempt_number=0,
    )
    assert asyncio.run(provider.suggest(request)) == {"top_k": 2}
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "placeholder" not in str(provider.fingerprint())
    asyncio.run(provider.close())
