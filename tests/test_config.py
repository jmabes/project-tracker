from pathlib import Path

import pytest

from project_tracker import create_app


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PROJECT_TRACKER_CONFIG", "SECRET_KEY", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)


def test_testing_config_uses_in_memory_database() -> None:
    app = create_app("testing")

    assert app.testing
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://"


def test_testing_config_ignores_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:////should/not/be/used.db")

    app = create_app("testing")

    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://"


def test_config_selected_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJECT_TRACKER_CONFIG", "testing")

    assert create_app().testing


def test_unknown_config_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown config"):
        create_app("staging")


def test_production_requires_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/prod.db")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")


def test_production_treats_blank_secret_key_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "   ")
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/prod.db")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")


def test_production_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "s3cret")

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app("production")


def test_production_reads_settings_from_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    url = f"sqlite:///{tmp_path / 'prod.db'}"
    monkeypatch.setenv("SECRET_KEY", "s3cret")
    monkeypatch.setenv("DATABASE_URL", url)

    app = create_app("production")

    assert not app.testing
    assert app.config["SECRET_KEY"] == "s3cret"
    assert app.config["SQLALCHEMY_DATABASE_URI"] == url
    assert app.config.get("WTF_CSRF_ENABLED", True) is True
