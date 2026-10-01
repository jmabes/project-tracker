from flask import Flask
from sqlalchemy import func, select

from project_tracker.extensions import db


def test_casefold_matches_python_casefold(app: Flask) -> None:
    for text in ["ÉCLAIR", "Straße", "Café", "plain ascii"]:
        assert db.session.scalar(select(func.casefold(text))) == text.casefold()


def test_casefold_folds_what_sqlite_lower_does_not(app: Flask) -> None:
    # SQLite's lower() only folds ASCII, so it leaves "É" alone.
    assert db.session.scalar(select(func.lower("É"))) == "É"
    assert db.session.scalar(select(func.casefold("É"))) == "é"


def test_casefold_passes_null_through(app: Flask) -> None:
    assert db.session.scalar(select(func.casefold(None))) is None
