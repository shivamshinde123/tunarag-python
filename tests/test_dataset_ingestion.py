import asyncio
import json

import pytest

from tunarag import (
    DatasetError,
    DatasetFieldMap,
    DatasetSplit,
    EvaluationDataset,
    EvaluationExample,
    SplitRatios,
)


def test_evaluation_example_normalizes_text_and_freezes_metadata() -> None:
    example = EvaluationExample(
        id="  item-1 ",
        query="\ufeffCafe\u0301?\r\n",
        reference_contexts=(" first\rcontext ",),
        tags=(" docs ",),
        metadata={"nested": [1, True, None]},
    )

    assert example.id == "item-1"
    assert example.query == "Café?"
    assert example.reference_contexts == ("first\ncontext",)
    assert example.tags == ("docs",)
    with pytest.raises(TypeError):
        example.metadata["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        example.metadata["nested"][0] = 2  # type: ignore[index]


def test_records_generate_stable_ids_versions_and_async_iteration() -> None:
    records = [{"query": "What is TunaRAG?", "metadata": {"source": "guide"}}]

    first = EvaluationDataset.from_records(records)
    second = EvaluationDataset.from_records(records)

    assert first.version == second.version
    assert first.examples[0].id == second.examples[0].id

    async def collect() -> list[EvaluationExample]:
        return [example async for example in first]

    assert asyncio.run(collect()) == list(first.examples)


def test_field_map_and_explicit_split() -> None:
    dataset = EvaluationDataset.from_records(
        [{"sample": "a", "prompt": "Question", "partition": "test"}],
        field_map=DatasetFieldMap(id="sample", query="prompt", split="partition"),
    )

    assert dataset.examples[0].id == "a"
    assert dataset.examples[0].split is DatasetSplit.TEST


def test_load_json_jsonl_and_csv(tmp_path) -> None:
    records = [
        {
            "id": "one",
            "query": "Q?",
            "reference_contexts": ["context"],
            "tags": ["smoke"],
            "metadata": {"group": "a"},
        }
    ]
    json_path = tmp_path / "data.json"
    json_path.write_text(json.dumps(records), encoding="utf-8")
    jsonl_path = tmp_path / "data.jsonl"
    jsonl_path.write_text("\ufeff" + json.dumps(records[0]) + "\n\n", encoding="utf-8")
    csv_path = tmp_path / "data.csv"
    csv_path.write_text(
        "id,query,reference_contexts,tags,metadata\n"
        'one,Q?,"[""context""]","[""smoke""]","{""group"":""a""}"\n',
        encoding="utf-8",
    )

    loaded = [
        EvaluationDataset.from_json(json_path),
        EvaluationDataset.from_jsonl(jsonl_path),
        EvaluationDataset.from_csv(csv_path),
    ]

    assert len({dataset.version for dataset in loaded}) == 1


def test_deterministic_grouped_splits_and_selection() -> None:
    dataset = EvaluationDataset.from_records(
        [
            {"id": "a1", "query": "A1", "metadata": {"document": "a"}},
            {"id": "a2", "query": "A2", "metadata": {"document": "a"}},
            {"id": "b", "query": "B", "metadata": {"document": "b"}},
        ]
    )

    first = dataset.with_splits(seed=7, group_metadata_key="document")
    second = dataset.with_splits(seed=7, group_metadata_key="document")

    assert first.version == second.version
    assert first.examples[0].split is first.examples[1].split
    selected = first.select(first.examples[0].split)
    assert all(example.split is first.examples[0].split for example in selected.examples)


def test_dataset_errors_do_not_include_record_values(tmp_path) -> None:
    secret = "private query contents"
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps({"query": secret, "tags": "not-json"}), encoding="utf-8")

    with pytest.raises(DatasetError) as raised:
        EvaluationDataset.from_jsonl(path)

    assert secret not in str(raised.value)
    assert raised.value.details["record"] == 1

    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"query": "valid"}\nnot-json\n', encoding="utf-8")
    with pytest.raises(DatasetError) as malformed_error:
        EvaluationDataset.from_jsonl(malformed)
    assert malformed_error.value.details["record"] == 2


def test_duplicate_ids_and_invalid_metadata_are_rejected() -> None:
    with pytest.raises(DatasetError, match="validation"):
        EvaluationDataset.from_records([{"id": "same", "query": "A"}, {"id": "same", "query": "B"}])
    with pytest.raises(DatasetError, match="record"):
        EvaluationDataset.from_records([{"query": "A", "metadata": {"bad": float("nan")}}])


def test_split_ratio_validation_and_missing_groups() -> None:
    with pytest.raises(ValueError, match="sum"):
        SplitRatios(0.5, 0.5, 0.5)
    with pytest.raises(ValueError, match="nonnegative"):
        SplitRatios(-0.1, 0.6, 0.5)

    dataset = EvaluationDataset.from_records([{"id": "a", "query": "A"}])
    with pytest.raises(DatasetError, match="group metadata"):
        dataset.with_splits(group_metadata_key="document")
