"""Typed settings and deterministic configuration resolution."""

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .errors import ConfigurationError

_ENV_TO_FIELD = {
    "TUNARAG_HOME": "home",
    "TUNARAG_DB_PATH": "db_path",
    "TUNARAG_CACHE_DIR": "cache_dir",
    "TUNARAG_ARTIFACT_DIR": "artifact_dir",
    "TUNARAG_MAX_TRIALS": "max_trials",
    "TUNARAG_CONCURRENCY": "concurrency",
    "TUNARAG_SAMPLE_CONCURRENCY": "sample_concurrency",
    "TUNARAG_SEED": "seed",
    "TUNARAG_MAX_RETRIES": "max_retries",
    "TUNARAG_CACHE_POLICY": "cache_policy",
}
_FIELDS = frozenset(_ENV_TO_FIELD.values())
_INTEGER_FIELDS = {
    "max_trials",
    "concurrency",
    "sample_concurrency",
    "seed",
    "max_retries",
}
_PATH_FIELDS = {"home", "db_path", "cache_dir", "artifact_dir"}


class CachePolicy(str, Enum):
    """Allowed cache read and write behavior."""

    OFF = "off"
    READ_ONLY = "read_only"
    WRITE_ONLY = "write_only"
    READ_WRITE = "read_write"


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved core settings with no provider credentials."""

    home: Path
    db_path: Path
    cache_dir: Path
    artifact_dir: Path
    max_trials: int = 25
    concurrency: int = 4
    sample_concurrency: int = 8
    seed: int = 0
    max_retries: int = 2
    cache_policy: CachePolicy = CachePolicy.READ_WRITE

    def __post_init__(self) -> None:
        _require_positive("max_trials", self.max_trials)
        _require_positive("concurrency", self.concurrency)
        _require_positive("sample_concurrency", self.sample_concurrency)
        _require_integer("seed", self.seed)
        _require_integer("max_retries", self.max_retries)
        if self.max_retries < 0:
            raise ConfigurationError("max_retries must not be negative", stage="config")

    @classmethod
    def resolve(
        cls,
        *,
        overrides: Mapping[str, Any] | None = None,
        config_path: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "Settings":
        """Resolve defaults, selected TOML, known environment variables, and overrides."""

        values: dict[str, Any] = {
            "max_trials": 25,
            "concurrency": 4,
            "sample_concurrency": 8,
            "seed": 0,
            "max_retries": 2,
            "cache_policy": CachePolicy.READ_WRITE,
        }
        if config_path is not None:
            values.update(_read_toml(Path(config_path)))
        values.update(_read_environment(os.environ if environ is None else environ))
        if overrides is not None:
            _reject_unknown(overrides, source="overrides")
            values.update(overrides)

        home = _as_path("home", values.get("home", _default_home()))
        values["home"] = home
        values.setdefault("db_path", home / "experiments.db")
        values.setdefault("cache_dir", home / "cache")
        values.setdefault("artifact_dir", home / "artifacts")

        for field in _PATH_FIELDS:
            values[field] = _as_path(field, values[field])
        for field in _INTEGER_FIELDS:
            values[field] = _as_integer(field, values[field])
        values["cache_policy"] = _as_cache_policy(values["cache_policy"])
        return cls(**values)

    def as_dict(self) -> dict[str, str | int]:
        """Return a serializable settings view containing no secrets."""

        return {
            "home": str(self.home),
            "db_path": str(self.db_path),
            "cache_dir": str(self.cache_dir),
            "artifact_dir": str(self.artifact_dir),
            "max_trials": self.max_trials,
            "concurrency": self.concurrency,
            "sample_concurrency": self.sample_concurrency,
            "seed": self.seed,
            "max_retries": self.max_retries,
            "cache_policy": self.cache_policy.value,
        }


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(
            f"could not read TunaRAG configuration: {path}",
            stage="config",
            details={"path": str(path), "cause": type(error).__name__},
        ) from error
    section = document.get("tunarag", {})
    if not isinstance(section, Mapping):
        raise ConfigurationError("the [tunarag] TOML section must be a table", stage="config")
    _reject_unknown(section, source=str(path))
    return dict(section)


def _read_environment(environ: Mapping[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for variable, field in _ENV_TO_FIELD.items():
        if variable not in environ:
            continue
        raw = environ[variable]
        if not raw.strip():
            raise ConfigurationError(
                f"{variable} must not be empty",
                stage="config",
                details={"variable": variable},
            )
        values[field] = raw
    return values


def _reject_unknown(values: Mapping[str, Any], *, source: str) -> None:
    unknown = sorted(str(key) for key in values if key not in _FIELDS)
    if unknown:
        raise ConfigurationError(
            f"unknown TunaRAG configuration keys in {source}",
            stage="config",
            details={"keys": unknown, "source": source},
        )


def _as_path(field: str, value: Any) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ConfigurationError(f"{field} must be a path", stage="config")
    if isinstance(value, str) and not value.strip():
        raise ConfigurationError(f"{field} must not be empty", stage="config")
    return Path(value).expanduser()


def _as_integer(field: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ConfigurationError(f"{field} must be an integer", stage="config")
    try:
        converted = int(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{field} must be an integer", stage="config") from error
    if isinstance(value, float) and not value.is_integer():
        raise ConfigurationError(f"{field} must be an integer", stage="config")
    if isinstance(value, str) and str(converted) != value.strip():
        raise ConfigurationError(f"{field} must be an integer", stage="config")
    return converted


def _as_cache_policy(value: Any) -> CachePolicy:
    if isinstance(value, CachePolicy):
        return value
    try:
        return CachePolicy(value)
    except (TypeError, ValueError) as error:
        choices = ", ".join(policy.value for policy in CachePolicy)
        raise ConfigurationError(
            f"cache_policy must be one of: {choices}", stage="config"
        ) from error


def _require_integer(field: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(f"{field} must be an integer", stage="config")


def _require_positive(field: str, value: int) -> None:
    _require_integer(field, value)
    if value < 1:
        raise ConfigurationError(f"{field} must be positive", stage="config")


def _default_home() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        return Path(root) / "TunaRAG" if root else Path.home() / "AppData" / "Local" / "TunaRAG"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TunaRAG"
    root = os.environ.get("XDG_DATA_HOME")
    return Path(root) / "tunarag" if root else Path.home() / ".local" / "share" / "tunarag"
