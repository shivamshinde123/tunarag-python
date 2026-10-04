import pytest

from tunarag import Candidate, MetricValue, Secret, UsageRecord, ValueStatus
from tunarag.serialization import canonical_json, content_hash, storage_json


def test_secret_is_redacted_and_excluded_from_mapping_identity() -> None:
    secret = Secret("do-not-leak")

    assert repr(secret) == "Secret(***redacted***)"
    assert str(secret) == "***redacted***"
    assert content_hash({"token": secret, "model": "small"}) == content_hash({"model": "small"})
    assert b"do-not-leak" not in canonical_json({"token": secret})


def test_storage_json_preserves_numbers_and_omits_mapping_secrets() -> None:
    payload = storage_json({"ratio": 1.5, "token": Secret("do-not-leak")})

    assert payload == b'{"ratio":1.5}'


def test_mapping_order_does_not_change_identity() -> None:
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})


def test_domain_values_validate_boundaries() -> None:
    assert MetricValue("quality", 0.9).status is ValueStatus.EXACT
    assert UsageRecord("llm", input_tokens=10).input_tokens == 10
    assert Candidate({"top_k": 5}).parameters["top_k"] == 5

    with pytest.raises(ValueError, match="coverage"):
        MetricValue("quality", 0.9, coverage=1.1)

    with pytest.raises(ValueError, match="must not be negative"):
        UsageRecord("llm", cost=-1)
