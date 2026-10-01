"""The Alembic migrations build the same schema as the models."""

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask import Flask
from flask_migrate import downgrade, upgrade

from project_tracker import create_app
from project_tracker.extensions import db

MIGRATIONS_DIR = str(Path(__file__).resolve().parents[1] / "migrations")


@pytest.fixture()
def file_db_app(tmp_path: Path) -> Iterator[Flask]:
    """App pointed at an empty on-disk SQLite file, like a fresh install."""
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": url})
    with app.app_context():
        yield app
        db.session.remove()
        db.engine.dispose()


def test_upgrade_creates_schema_on_empty_database(file_db_app: Flask) -> None:
    upgrade(directory=MIGRATIONS_DIR)

    inspector = sa.inspect(db.engine)
    assert "projects" in inspector.get_table_names()
    assert {c["name"] for c in inspector.get_columns("projects")} == {
        "id",
        "name",
        "category",
        "medium",
        "priority",
        "status",
        "start_date",
        "estimated_completion_date",
        "created_at",
        "updated_at",
    }
    with db.engine.connect() as conn:
        index_sql = conn.execute(
            sa.text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'index' AND name = 'uq_projects_name_lower'"
            )
        ).scalar_one()
    assert "UNIQUE" in index_sql.upper()
    assert "lower(name)" in index_sql


# SQLite can't reflect expression indexes, so SQLAlchemy and Alembic warn and skip
# that index; test_upgrade_creates_schema_on_empty_database checks it instead.
@pytest.mark.filterwarnings("ignore:autogenerate skipping metadata-specified")
@pytest.mark.filterwarnings("ignore:Skipped unsupported reflection of expression")
def test_migrations_match_models(file_db_app: Flask) -> None:
    upgrade(directory=MIGRATIONS_DIR)

    with db.engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), db.metadata)

    assert diff == []


def test_downgrade_removes_schema(file_db_app: Flask) -> None:
    upgrade(directory=MIGRATIONS_DIR)
    downgrade(directory=MIGRATIONS_DIR, revision="base")

    assert "projects" not in sa.inspect(db.engine).get_table_names()
