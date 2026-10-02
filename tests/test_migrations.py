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
        "target_date",
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


def test_rename_to_target_date_keeps_data_and_name_index(file_db_app: Flask) -> None:
    # Start from the schema before the rename, with a project in it.
    upgrade(directory=MIGRATIONS_DIR, revision="86bbf26dee64")
    with db.engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO projects (name, category, medium, priority, status, "
                "start_date, estimated_completion_date, created_at, updated_at) "
                "VALUES ('Shed', 'Home', 'DIY', 'Low', 'Done', '2026-01-01', "
                "'2026-06-30', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )

    upgrade(directory=MIGRATIONS_DIR, revision="4ed531acccd0")

    columns = {c["name"] for c in sa.inspect(db.engine).get_columns("projects")}
    assert "target_date" in columns
    assert "estimated_completion_date" not in columns
    with db.engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT target_date FROM projects WHERE name = 'Shed'")
            ).scalar_one()
            == "2026-06-30"
        )
    # The case-insensitive unique name index still rejects a clashing name.
    with pytest.raises(sa.exc.IntegrityError), db.engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO projects (name, category, medium, priority, status, "
                "created_at, updated_at) VALUES ('SHED', 'Home', 'DIY', 'Low', "
                "'Done', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )

    downgrade(directory=MIGRATIONS_DIR, revision="86bbf26dee64")

    with db.engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT estimated_completion_date FROM projects")
            ).scalar_one()
            == "2026-06-30"
        )
