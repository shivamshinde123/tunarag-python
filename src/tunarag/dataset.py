"""Repeatable datasets and normalized evaluation-example ingestion."""

from __future__ import annotations

import csv
import json
import math
import unicodedata
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .errors import DatasetError
from .serialization import content_hash

_SCHEMA_VERSION = 1


class DatasetSplit(str, Enum):
    """Canonical purpose assigned to an evaluation example."""

    OPTIMIZE = "optimize"
    VALIDATION = "validation"
    TEST = "test"


@dataclass(frozen=True, slots=True)
class SplitRatios:
    """Deterministic split thresholds."""

    optimize: float = 0.8
    validation: float = 0.1
    test: float = 0.1

    def __post_init__(self) -> None:
        values = (self.optimize, self.validation, self.test)
        if any(
            isinstance(value, bool) or not math.isfinite(value) or value < 0 for value in values
        ):
            raise ValueError("split ratios must be finite nonnegative numbers")
        if not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("split ratios must sum to 1")


@dataclass(frozen=True, slots=True)
class DatasetFieldMap:
    """Map source record fields to the canonical evaluation schema."""

    id: str = "id"
    query: str = "query"
    reference_answer: str = "reference_answer"
    reference_contexts: str = "reference_contexts"
    relevant_document_ids: str = "relevant_document_ids"
    tags: str = "tags"
    metadata: str = "metadata"
    split: str = "split"

    def __post_init__(self) -> None:
        values = tuple(getattr(self, name) for name in self.__dataclass_fields__)
        if any(not value.strip() for value in values):
            raise ValueError("dataset field names must not be empty")
        if len(set(values)) != len(values):
            raise ValueError("dataset field names must be unique")


@dataclass(frozen=True, slots=True)
class EvaluationExample:
    """One normalized, provenance-bearing evaluation example."""

    id: str
    query: str
    reference_answer: str | None = None
    reference_contexts: tuple[str, ...] = ()
    relevant_document_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    split: DatasetSplit = DatasetSplit.OPTIMIZE
    synthetic: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _normalize_required(self.id, "example id"))
        object.__setattr__(self, "query", _normalize_required(self.query, "query"))
        if self.reference_answer is not None:
            normalized_answer = _normalize_text(self.reference_answer)
            object.__setattr__(self, "reference_answer", normalized_answer or None)
        object.__setattr__(
            self,
            "reference_contexts",
            _normalize_unique(self.reference_contexts, "reference context", unique=False),
        )
        object.__setattr__(
            self,
            "relevant_document_ids",
            _normalize_unique(self.relevant_document_ids, "relevant document id"),
        )
        object.__setattr__(self, "tags", _normalize_unique(self.tags, "tag"))
        normalized_metadata = _json_value(dict(self.metadata), path="metadata")
        object.__setattr__(self, "metadata", MappingProxyType(normalized_metadata))
        if not isinstance(self.split, DatasetSplit):
            try:
                object.__setattr__(self, "split", DatasetSplit(self.split))
            except (TypeError, ValueError) as error:
                raise ValueError("invalid dataset split") from error
        if not isinstance(self.synthetic, bool):
            raise TypeError("synthetic must be a boolean")

    def semantic_data(self) -> dict[str, Any]:
        """Return normalized content used for version hashing."""

        return {
            "id": self.id,
            "query": self.query,
            "reference_answer": self.reference_answer,
            "reference_contexts": self.reference_contexts,
            "relevant_document_ids": self.relevant_document_ids,
            "tags": self.tags,
            "metadata": self.metadata,
            "split": self.split.value,
            "synthetic": self.synthetic,
        }


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    """A normalized, immutable dataset with a content-derived version."""

    examples: tuple[EvaluationExample, ...]
    version: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.examples:
            raise ValueError("dataset must contain at least one example")
        ids = [example.id for example in self.examples]
        if len(ids) != len(set(ids)):
            raise ValueError("dataset example ids must be unique")
        version = content_hash(
            {
                "schema_version": _SCHEMA_VERSION,
                "examples": [example.semantic_data() for example in self.examples],
            },
            namespace="tunarag:dataset:v1",
        )
        object.__setattr__(self, "version", version)

    @classmethod
    def from_records(
        cls,
        records: Iterable[Mapping[str, Any]],
        *,
        field_map: DatasetFieldMap | None = None,
        source: str = "records",
    ) -> EvaluationDataset:
        """Normalize mapping records into an immutable dataset."""

        mapping = field_map or DatasetFieldMap()
        examples: list[EvaluationExample] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, Mapping):
                raise DatasetError(
                    "dataset record must be an object",
                    details={"source": source, "record": index},
                )
            try:
                examples.append(_example_from_record(record, mapping))
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise DatasetError(
                    "dataset record is invalid",
                    details={
                        "source": source,
                        "record": index,
                        "cause": type(error).__name__,
                    },
                ) from error
        try:
            return cls(tuple(examples))
        except ValueError as error:
            raise DatasetError(
                "dataset validation failed",
                details={"source": source, "cause": type(error).__name__},
            ) from error

    @classmethod
    def from_jsonl(
        cls, path: str | Path, *, field_map: DatasetFieldMap | None = None
    ) -> EvaluationDataset:
        """Load UTF-8 JSON Lines, ignoring blank lines."""

        source = str(path)
        records: list[Mapping[str, Any]] = []
        try:
            with Path(path).open("r", encoding="utf-8-sig") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise DatasetError(
                            "could not load JSONL dataset",
                            details={
                                "source": source,
                                "record": line_number,
                                "cause": type(error).__name__,
                            },
                        ) from error
                    if not isinstance(value, Mapping):
                        raise DatasetError(
                            "JSONL row must be an object",
                            details={"source": source, "record": line_number},
                        )
                    records.append(value)
        except DatasetError:
            raise
        except (OSError, UnicodeError) as error:
            raise DatasetError(
                "could not load JSONL dataset",
                details={"source": source, "cause": type(error).__name__},
            ) from error
        return cls.from_records(records, field_map=field_map, source=source)

    @classmethod
    def from_json(
        cls, path: str | Path, *, field_map: DatasetFieldMap | None = None
    ) -> EvaluationDataset:
        """Load a UTF-8 JSON array of objects."""

        source = str(path)
        try:
            with Path(path).open("r", encoding="utf-8-sig") as stream:
                value = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise DatasetError(
                "could not load JSON dataset",
                details={"source": source, "cause": type(error).__name__},
            ) from error
        if not isinstance(value, list):
            raise DatasetError("JSON dataset must be an array", details={"source": source})
        return cls.from_records(value, field_map=field_map, source=source)

    @classmethod
    def from_csv(
        cls, path: str | Path, *, field_map: DatasetFieldMap | None = None
    ) -> EvaluationDataset:
        """Load a UTF-8 CSV with JSON-encoded collection fields."""

        source = str(path)
        try:
            with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
                records = list(csv.DictReader(stream))
        except (OSError, UnicodeError, csv.Error) as error:
            raise DatasetError(
                "could not load CSV dataset",
                details={"source": source, "cause": type(error).__name__},
            ) from error
        return cls.from_records(records, field_map=field_map, source=source)

    def with_splits(
        self,
        *,
        seed: int = 0,
        ratios: SplitRatios | None = None,
        group_metadata_key: str | None = None,
    ) -> EvaluationDataset:
        """Return a deterministically split copy, optionally keeping groups together."""

        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("split seed must be an integer")
        if group_metadata_key is not None and not group_metadata_key.strip():
            raise ValueError("group metadata key must not be empty")
        thresholds = ratios or SplitRatios()
        examples = tuple(
            replace(
                example,
                split=_select_split(
                    seed,
                    _group_identity(example, group_metadata_key),
                    thresholds,
                ),
            )
            for example in self.examples
        )
        return EvaluationDataset(examples)

    def select(self, split: DatasetSplit) -> EvaluationDataset:
        """Return one nonempty canonical split."""

        selected = tuple(example for example in self.examples if example.split is split)
        if not selected:
            raise DatasetError("selected dataset split is empty", details={"split": split.value})
        return EvaluationDataset(selected)

    def __aiter__(self) -> AsyncIterator[EvaluationExample]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[EvaluationExample]:
        for example in self.examples:
            yield example


@dataclass(frozen=True, slots=True)
class InMemoryDataset:
    """A versioned, repeatable dataset backed by an immutable tuple."""

    examples: tuple[Any, ...]
    version: str

    def __post_init__(self) -> None:
        if not self.examples:
            raise ValueError("dataset must contain at least one example")
        if not self.version.strip():
            raise ValueError("dataset version must not be empty")

    @classmethod
    def from_iterable(cls, examples: Iterable[Any], *, version: str) -> InMemoryDataset:
        """Materialize a repeatable dataset from an iterable."""

        return cls(tuple(examples), version)

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        for example in self.examples:
            yield example


def _example_from_record(record: Mapping[str, Any], fields: DatasetFieldMap) -> EvaluationExample:
    query = _required_record_value(record, fields.query)
    example_id = record.get(fields.id)
    reference_answer = _optional_string(record.get(fields.reference_answer))
    reference_contexts = _string_sequence(record.get(fields.reference_contexts))
    relevant_document_ids = _string_sequence(record.get(fields.relevant_document_ids))
    tags = _string_sequence(record.get(fields.tags))
    metadata = _metadata(record.get(fields.metadata))
    split = _split(record.get(fields.split))
    if example_id is None or (isinstance(example_id, str) and not example_id.strip()):
        example_id = content_hash(
            {
                "query": query,
                "reference_answer": reference_answer,
                "reference_contexts": reference_contexts,
                "relevant_document_ids": relevant_document_ids,
                "tags": tags,
                "metadata": metadata,
                "split": split.value,
                "synthetic": False,
            },
            namespace="tunarag:example-id:v1",
        )
    if not isinstance(example_id, str):
        raise TypeError("example id must be a string")
    return EvaluationExample(
        id=example_id,
        query=query,
        reference_answer=reference_answer,
        reference_contexts=reference_contexts,
        relevant_document_ids=relevant_document_ids,
        tags=tags,
        metadata=metadata,
        split=split,
        synthetic=False,
    )


def _required_record_value(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TypeError("optional text field must be a string")
    return value


def _string_sequence(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError("collection field must be an array of strings")
    if any(not isinstance(item, str) for item in value):
        raise TypeError("collection field must contain only strings")
    return tuple(value)


def _metadata(value: Any) -> Mapping[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise TypeError("metadata must be an object")
    return value


def _split(value: Any) -> DatasetSplit:
    if value is None or value == "":
        return DatasetSplit.OPTIMIZE
    if not isinstance(value, str):
        raise TypeError("split must be a string")
    return DatasetSplit(value.strip().lower())


def _normalize_required(value: str, label: str) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized


def _normalize_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("text value must be a string")
    normalized = unicodedata.normalize("NFC", value.lstrip("\ufeff"))
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n").strip()
    if any(unicodedata.category(char) == "Cc" and char not in {"\n", "\t"} for char in normalized):
        raise ValueError("text contains a disallowed control character")
    return normalized


def _normalize_unique(values: Iterable[str], label: str, *, unique: bool = True) -> tuple[str, ...]:
    normalized = tuple(_normalize_required(value, label) for value in values)
    if unique and len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} values must be unique")
    return normalized


def _json_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a nonfinite number")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError(f"{path} keys must be strings")
        return MappingProxyType(
            {key: _json_value(item, path=f"{path}.{key}") for key, item in value.items()}
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_json_value(item, path=f"{path}[]") for item in value)
    raise TypeError(f"{path} contains unsupported value type {type(value).__name__}")


def _group_identity(example: EvaluationExample, metadata_key: str | None) -> str:
    if metadata_key is None:
        return example.id
    if metadata_key not in example.metadata:
        raise DatasetError(
            "group metadata is missing",
            details={"example_id": example.id, "metadata_key": metadata_key},
        )
    value = example.metadata[metadata_key]
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise DatasetError(
            "group metadata must be a string or integer",
            details={"example_id": example.id, "metadata_key": metadata_key},
        )
    return str(value)


def _select_split(seed: int, identity: str, ratios: SplitRatios) -> DatasetSplit:
    digest = content_hash(
        {"seed": seed, "identity": identity}, namespace="tunarag:dataset-split:v1"
    )
    fraction = int(digest[:16], 16) / float(2**64)
    if fraction < ratios.optimize:
        return DatasetSplit.OPTIMIZE
    if fraction < ratios.optimize + ratios.validation:
        return DatasetSplit.VALIDATION
    return DatasetSplit.TEST
