"""Shared pytest fixtures: an isolated app, database and test client per test."""

from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from project_tracker import create_app
from project_tracker.extensions import db


@pytest.fixture()
def app() -> Iterator[Flask]:
    """App on the testing config with a fresh in-memory database."""
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    """Test client for the app fixture."""
    return app.test_client()
