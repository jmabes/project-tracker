"""Flask extension instances, created unbound and initialised in the app factory."""

import sqlite3

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import Engine, event
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import ConnectionPoolEntry


class Base(DeclarativeBase):
    """Declarative base class for all models."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
csrf = CSRFProtect()


def register_sql_functions(engine: Engine) -> None:
    """Make Python's ``str.casefold`` callable as ``casefold(text)`` in SQLite.

    SQLite's own ``lower()`` only folds ASCII letters. Sorting names with this
    function folds case the same way the service layer's uniqueness check does.
    """
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _add_casefold)


def _add_casefold(
    dbapi_connection: sqlite3.Connection, connection_record: ConnectionPoolEntry
) -> None:
    """Register ``casefold`` on a new SQLite connection."""
    dbapi_connection.create_function("casefold", 1, _casefold, deterministic=True)


def _casefold(value: object) -> object:
    """Casefold text; pass NULL and non-text values through unchanged."""
    return value.casefold() if isinstance(value, str) else value
