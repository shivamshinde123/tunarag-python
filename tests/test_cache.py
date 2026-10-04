import sqlite3

import pytest

from tunarag import (
    CacheKey,
    CacheLookupStatus,
    CachePrivacy,
    Secret,
    SQLiteCache,
    SQLiteStore,
)


def test_cache_key_is_deterministic_namespaced_versioned_and_secret_safe() -> None:
    first = CacheKey.from_parts("adapter", {"model": "small", "token": Secret("first")})
    second = CacheKey.from_parts("adapter", {"token": Secret("second"), "model": "small"})

    assert first == second
    assert first != CacheKey.from_parts("evaluation", {"model": "small"})
    assert first != CacheKey.from_parts("adapter", {"model": "small"}, format_version=2)


def test_cache_payload_survives_reopen_and_retains_metadata(tmp_path) -> None:
    path = tmp_path / "cache.sqlite"
    key = CacheKey.from_parts("evaluation", "dataset-v1", {"top_k": 3})
    cache = SQLiteCache(path, clock=lambda: 100.0)

    entry = cache.put(
        key,
        b'{"quality":0.9}',
        privacy=CachePrivacy.SENSITIVE,
        ttl_seconds=60.0,
    )
    cache.close()

    reopened = SQLiteCache(path, clock=lambda: 120.0)
    lookup = reopened.get(key)

    assert lookup.status is CacheLookupStatus.HIT
    assert lookup.payload == b'{"quality":0.9}'
    assert lookup.checksum == entry.checksum
    assert lookup.privacy is CachePrivacy.SENSITIVE
    assert lookup.created_at == 100.0
    assert lookup.expires_at == 160.0
    reopened.close()


def test_expired_entry_is_not_returned_and_can_be_pruned() -> None:
    now = 10.0
    cache = SQLiteCache(clock=lambda: now)
    key = CacheKey.from_parts("adapter", "candidate")
    cache.put(key, b"result", ttl_seconds=5.0)

    now = 16.0
    lookup = cache.get(key)

    assert lookup.status is CacheLookupStatus.EXPIRED
    assert lookup.payload is None
    assert cache.prune() == 1
    assert cache.get(key).status is CacheLookupStatus.MISS
    cache.close()


def test_corrupt_payload_is_quarantined_and_never_returned(tmp_path) -> None:
    path = tmp_path / "cache.sqlite"
    key = CacheKey.from_parts("adapter", "candidate")
    cache = SQLiteCache(path)
    cache.put(key, b"verified")

    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            """UPDATE cache_entries SET payload = ?
            WHERE namespace = ? AND format_version = ? AND key_digest = ?""",
            (b"tampered", key.namespace, key.format_version, key.digest),
        )
    connection.close()

    first = cache.get(key)
    second = cache.get(key)

    assert first.status is CacheLookupStatus.CORRUPT
    assert first.payload is None
    assert first.reason == "payload checksum mismatch"
    assert second.status is CacheLookupStatus.QUARANTINED
    assert second.payload is None
    assert cache.prune(include_quarantined=True) == 1
    cache.close()


def test_cache_validates_keys_ttl_and_clock() -> None:
    with pytest.raises(ValueError, match="namespace"):
        CacheKey.from_parts("invalid namespace", "value")
    with pytest.raises(ValueError, match="semantic part"):
        CacheKey.from_parts("adapter")

    cache = SQLiteCache()
    key = CacheKey.from_parts("adapter", "candidate")
    with pytest.raises(ValueError, match="TTL"):
        cache.put(key, b"value", ttl_seconds=0)
    cache.close()

    invalid_clock = SQLiteCache(clock=lambda: float("inf"))
    with pytest.raises(ValueError, match="clock"):
        invalid_clock.put(key, b"value")
    invalid_clock.close()


def test_cache_rejects_unknown_schema_version(tmp_path) -> None:
    path = tmp_path / "future-cache.sqlite"
    connection = sqlite3.connect(path)
    with connection:
        connection.execute("CREATE TABLE cache_schema_version (version INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO cache_schema_version(version) VALUES (2)")
    connection.close()

    with pytest.raises(RuntimeError, match="unsupported cache schema"):
        SQLiteCache(path)


def test_cache_can_share_the_experiment_database(tmp_path) -> None:
    path = tmp_path / "tunarag.sqlite"
    store = SQLiteStore(path)
    study = store.create_study("shared", {"seed": 3})
    cache = SQLiteCache(path)
    key = CacheKey.from_parts("adapter", study.id, {"top_k": 4})

    cache.put(key, b"shared-file-result")

    assert cache.get(key).payload == b"shared-file-result"
    store.close()
    cache.close()
