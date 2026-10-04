from pathlib import Path

import pytest

from tunarag import CachePolicy, ConfigurationError, Settings


def test_settings_resolve_precedence_and_dependent_paths(tmp_path) -> None:
    config = tmp_path / "tunarag.toml"
    config.write_text(
        """[tunarag]
home = "file-home"
max_trials = 10
concurrency = 2
cache_policy = "read_only"
""",
        encoding="utf-8",
    )

    settings = Settings.resolve(
        config_path=config,
        environ={"TUNARAG_HOME": "env-home", "TUNARAG_MAX_TRIALS": "20"},
        overrides={"max_trials": 30, "sample_concurrency": 3},
    )

    assert settings.home == Path("env-home")
    assert settings.db_path == Path("env-home/experiments.db")
    assert settings.cache_dir == Path("env-home/cache")
    assert settings.max_trials == 30
    assert settings.concurrency == 2
    assert settings.sample_concurrency == 3
    assert settings.cache_policy is CachePolicy.READ_ONLY


def test_settings_read_only_known_environment_variables() -> None:
    settings = Settings.resolve(
        overrides={"home": "explicit-home"},
        environ={
            "TUNARAG_CONCURRENCY": "6",
            "OPENAI_API_KEY": "must-not-enter-settings",
            "UNRELATED": "ignored",
        },
    )

    assert settings.concurrency == 6
    assert "must-not-enter-settings" not in repr(settings.as_dict())
    assert set(settings.as_dict()) == {
        "home",
        "db_path",
        "cache_dir",
        "artifact_dir",
        "max_trials",
        "concurrency",
        "sample_concurrency",
        "seed",
        "max_retries",
        "cache_policy",
    }


def test_settings_reject_unknown_and_invalid_values(tmp_path) -> None:
    config = tmp_path / "invalid.toml"
    config.write_text("[tunarag]\nunknown = true\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="unknown"):
        Settings.resolve(config_path=config, environ={})
    with pytest.raises(ConfigurationError, match="integer"):
        Settings.resolve(environ={"TUNARAG_MAX_TRIALS": "2.5"})
    with pytest.raises(ConfigurationError, match="positive"):
        Settings.resolve(overrides={"max_trials": 0}, environ={})
    with pytest.raises(ConfigurationError, match="cache_policy"):
        Settings.resolve(overrides={"cache_policy": "sometimes"}, environ={})


def test_settings_do_not_load_dotenv_implicitly(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TUNARAG_MAX_TRIALS=999\n", encoding="utf-8")

    settings = Settings.resolve(overrides={"home": tmp_path}, environ={})

    assert settings.max_trials == 25
