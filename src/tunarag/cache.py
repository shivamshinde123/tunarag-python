"""Versioned, checksum-verified local cache persistence."""

import hashlib
import math
import re
import sqlite3
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

from .serialization import content_hash

_NAMESPACE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")


class CachePrivacy(str, Enum):
    """Privacy classification retained with a cache payload."""

    STANDARD = "standard"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class CacheLookupStatus(str, Enum):
    """Outcome of a cache lookup."""

    HIT = "hit"
    MISS = "miss"
    EXPIRED = "expired"
    CORRUPT = "corrupt"
    QUARANTINED = "quarantined"


class CacheEntryState(str, Enum):
    """Persisted cache-entry lifecycle state."""

    ACTIVE = "active"
    EXPIRED = "expired"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class CacheKey:
    """Namespaced identity for one semantic cache value."""

    namespace: str
    digest: str
    format_version: int = 1

    def __post_init__(self) -> None:
        if _NAMESPACE_PATTERN.fullmatch(self.namespace) is None:
            raise ValueError("cache namespace must use 1-128 safe characters")
        if _DIGEST_PATTERN.fullmatch(self.digest) is None:
            raise ValueError("cache digest must be a lowercase SHA-256 hex digest")
        if (
            not isinstance(self.format_version, int)
            or isinstance(self.format_version, bool)
            or self.format_version < 1
        ):
            raise ValueError("cache format version must be a positive integer")

    @classmethod
    def from_parts(cls, namespace: str, *parts: Any, format_version: int = 1) -> "CacheKey":
        """Build a key from canonical semantic inputs."""

        if not parts:
            raise ValueError("cache key requires at least one semantic part")
        digest = content_hash(
            {"format_version": format_version, "parts": parts},
            namespace=f"tunarag:cache-key:{namespace}:v1",
        )
        return cls(namespace=namespace, digest=digest, format_version=format_version)


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """Metadata returned after an atomic cache write."""

    key: CacheKey
    checksum: str
    privacy: CachePrivacy
    created_at: float
    expires_at: float | None


@dataclass(frozen=True, slots=True)
class CacheLookup:
    """Payload and metadata returned by a cache lookup."""

    key: CacheKey
    status: CacheLookupStatus
    payload: bytes | None = None
    checksum: str | None = None
    privacy: CachePrivacy | None = None
    created_at: float | None = None
    expires_at: float | None = None
    reason: str | None = None

    @property
    def is_hit(self) -> bool:
        """Return whether this lookup contains a verified payload."""

        return self.status is CacheLookupStatus.HIT


class SQLiteCache:
    """Transactional SQLite cache with expiry and corruption quarantine."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._connection = sqlite3.connect(str(path))
        self._connection.row_factory = sqlite3.Row
        self._clock = clock
        self.initialize()

    def initialize(self) -> None:
        """Create the independently versioned cache schema."""

        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cache_schema_version (
                version INTEGER PRIMARY KEY
            );
            INSERT OR IGNORE INTO cache_schema_version(version) VALUES (1);
            CREATE TABLE IF NOT EXISTS cache_entries (
                namespace TEXT NOT NULL,
                format_version INTEGER NOT NULL,
                key_digest TEXT NOT NULL,
                payload BLOB NOT NULL,
                checksum TEXT NOT NULL,
                privacy TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL,
                last_accessed_at REAL,
                hit_count INTEGER NOT NULL DEFAULT 0,
                quarantine_reason TEXT,
                PRIMARY KEY(namespace, format_version, key_digest),
                CHECK(format_version > 0),
                CHECK(hit_count >= 0),
                CHECK(privacy IN ('standard', 'sensitive', 'restricted')),
                CHECK(state IN ('active', 'expired', 'quarantined'))
            );
            CREATE INDEX IF NOT EXISTS idx_cache_entries_retention
                ON cache_entries(state, expires_at);
            """
        )
        self._connection.commit()
        versions = [
            int(row[0])
            for row in self._connection.execute(
                "SELECT version FROM cache_schema_version ORDER BY version"
            )
        ]
        if versions != [1]:
            self._connection.close()
            raise RuntimeError(f"unsupported cache schema versions: {versions}")

    def put(
        self,
        key: CacheKey,
        payload: bytes | bytearray | memoryview,
        *,
        privacy: CachePrivacy = CachePrivacy.STANDARD,
        ttl_seconds: float | None = None,
    ) -> CacheEntry:
        """Atomically insert or replace a cache payload."""

        payload_bytes = bytes(payload)
        if ttl_seconds is not None:
            if not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
                raise ValueError("cache TTL must be a positive finite number")
        now = self._now()
        expires_at = None if ttl_seconds is None else now + ttl_seconds
        checksum = _payload_checksum(payload_bytes)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO cache_entries(
                    namespace, format_version, key_digest, payload, checksum, privacy,
                    state, created_at, expires_at, last_accessed_at, hit_count,
                    quarantine_reason
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, NULL, 0, NULL)
                ON CONFLICT(namespace, format_version, key_digest) DO UPDATE SET
                    payload = excluded.payload,
                    checksum = excluded.checksum,
                    privacy = excluded.privacy,
                    state = 'active',
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    last_accessed_at = NULL,
                    hit_count = 0,
                    quarantine_reason = NULL
                """,
                (
                    key.namespace,
                    key.format_version,
                    key.digest,
                    payload_bytes,
                    checksum,
                    privacy.value,
                    now,
                    expires_at,
                ),
            )
        return CacheEntry(key, checksum, privacy, now, expires_at)

    def get(self, key: CacheKey) -> CacheLookup:
        """Return a verified payload or an explicit miss reason."""

        row = self._select(key)
        if row is None:
            return CacheLookup(key, CacheLookupStatus.MISS)

        privacy = CachePrivacy(row["privacy"])
        created_at = float(row["created_at"])
        expires_at = row["expires_at"]
        metadata = {
            "checksum": row["checksum"],
            "privacy": privacy,
            "created_at": created_at,
            "expires_at": expires_at,
        }
        state = CacheEntryState(row["state"])
        if state is CacheEntryState.QUARANTINED:
            return CacheLookup(
                key,
                CacheLookupStatus.QUARANTINED,
                reason=row["quarantine_reason"],
                **metadata,
            )

        now = self._now()
        if state is CacheEntryState.EXPIRED or (expires_at is not None and expires_at <= now):
            if state is CacheEntryState.ACTIVE:
                with self._connection:
                    self._connection.execute(
                        """UPDATE cache_entries SET state = 'expired'
                        WHERE namespace = ? AND format_version = ? AND key_digest = ?""",
                        (key.namespace, key.format_version, key.digest),
                    )
            return CacheLookup(key, CacheLookupStatus.EXPIRED, **metadata)

        payload = bytes(row["payload"])
        if _payload_checksum(payload) != row["checksum"]:
            reason = "payload checksum mismatch"
            with self._connection:
                self._connection.execute(
                    """UPDATE cache_entries
                    SET state = 'quarantined', quarantine_reason = ?
                    WHERE namespace = ? AND format_version = ? AND key_digest = ?""",
                    (reason, key.namespace, key.format_version, key.digest),
                )
            return CacheLookup(key, CacheLookupStatus.CORRUPT, reason=reason, **metadata)

        with self._connection:
            self._connection.execute(
                """UPDATE cache_entries
                SET last_accessed_at = ?, hit_count = hit_count + 1
                WHERE namespace = ? AND format_version = ? AND key_digest = ?""",
                (now, key.namespace, key.format_version, key.digest),
            )
        return CacheLookup(key, CacheLookupStatus.HIT, payload=payload, **metadata)

    def delete(self, key: CacheKey) -> bool:
        """Delete one cache entry and report whether it existed."""

        with self._connection:
            cursor = self._connection.execute(
                """DELETE FROM cache_entries
                WHERE namespace = ? AND format_version = ? AND key_digest = ?""",
                (key.namespace, key.format_version, key.digest),
            )
        return cursor.rowcount == 1

    def prune(self, *, include_quarantined: bool = False) -> int:
        """Remove expired entries and optionally quarantined entries."""

        now = self._now()
        conditions: Sequence[str] = (
            "state = 'expired'",
            "(expires_at IS NOT NULL AND expires_at <= ?)",
        )
        where = " OR ".join(conditions)
        parameters: list[float] = [now]
        if include_quarantined:
            where += " OR state = 'quarantined'"
        with self._connection:
            cursor = self._connection.execute(
                f"DELETE FROM cache_entries WHERE {where}", parameters
            )
        return cursor.rowcount

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self._connection.close()

    def _select(self, key: CacheKey) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self._connection.execute(
                """SELECT payload, checksum, privacy, state, created_at, expires_at,
                quarantine_reason FROM cache_entries
                WHERE namespace = ? AND format_version = ? AND key_digest = ?""",
                (key.namespace, key.format_version, key.digest),
            ).fetchone(),
        )

    def _now(self) -> float:
        now = float(self._clock())
        if not math.isfinite(now):
            raise ValueError("cache clock must return a finite timestamp")
        return now


def _payload_checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
