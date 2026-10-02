from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from project_tracker import create_app
from project_tracker.extensions import db


def test_healthz_returns_200(client: FlaskClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def _app_with_database(url: str) -> Flask:
    return create_app("testing", overrides={"SQLALCHEMY_DATABASE_URI": url})


def test_healthz_returns_503_when_database_directory_is_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Same failure as a mistyped DATABASE_URL or a directory the service user
    # cannot write: SQLite cannot open the file.
    app = _app_with_database(f"sqlite:///{tmp_path / 'missing' / 'tracker.db'}")

    with caplog.at_level("ERROR"):
        response = app.test_client().get("/healthz")

    assert response.status_code == 503
    assert response.get_json() == {"status": "error", "database": "unavailable"}
    assert "Health check database query failed" in caplog.text
    # The error detail stays in the log.
    assert "unable to open" not in response.get_data(as_text=True)


def test_healthz_returns_503_when_database_is_not_migrated(tmp_path: Path) -> None:
    # An empty database, e.g. DATABASE_URL pointing at the wrong file or
    # `flask db upgrade` not run yet.
    app = _app_with_database(f"sqlite:///{tmp_path / 'empty.db'}")

    response = app.test_client().get("/healthz")

    assert response.status_code == 503


def test_healthz_returns_200_with_a_migrated_file_database(tmp_path: Path) -> None:
    app = _app_with_database(f"sqlite:///{tmp_path / 'tracker.db'}")
    with app.app_context():
        db.create_all()

    response = app.test_client().get("/healthz")

    assert response.status_code == 200
