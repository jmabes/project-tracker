from datetime import date

import pytest
from flask import Flask
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from project_tracker import services
from project_tracker.extensions import db
from project_tracker.importer import confirm
from project_tracker.importer.confirm import ImportChangedError, save_rows
from project_tracker.importer.parsers import Cell
from project_tracker.importer.preview import COLUMNS, SourceRow
from project_tracker.models import Project
from project_tracker.services import (
    NAME_TAKEN_MESSAGE,
    ProjectValidationError,
    create_project,
    create_projects,
)


def raw(name: str, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "name": name,
        "category": "Home",
        "medium": "DIY",
        "priority": "Medium",
        "status": "Not started",
    }
    values.update(overrides)
    return values


def source(number: int, name: str, **overrides: str) -> SourceRow:
    values: dict[str, Cell | None] = dict.fromkeys(COLUMNS)
    values.update(name=name, category="Home", medium="DIY", priority="Medium")
    values.update(status="Not started", **overrides)
    return SourceRow(number=number, values=values)


def all_names() -> list[str]:
    db.session.expire_all()
    return list(db.session.scalars(select(Project.name).order_by(Project.id)))


# --- services.create_projects ----------------------------------------------------


def test_create_projects_saves_all(app: Flask) -> None:
    projects = create_projects(
        [raw(" A "), raw("B", start_date="2026-01-02"), raw("C")]
    )
    assert [p.id for p in projects] == [1, 2, 3]
    assert all_names() == ["A", "B", "C"]
    saved = db.session.get(Project, 2)
    assert saved is not None
    assert saved.start_date == date(2026, 1, 2)


def test_create_projects_invalid_input_saves_none(app: Flask) -> None:
    with pytest.raises(ProjectValidationError) as exc_info:
        create_projects([raw("A"), raw("B", status="?")])
    assert set(exc_info.value.errors) == {"status"}
    assert all_names() == []


def test_create_projects_duplicate_within_batch_saves_none(app: Flask) -> None:
    with pytest.raises(ProjectValidationError) as exc_info:
        create_projects([raw("A"), raw("B"), raw("a")])
    assert exc_info.value.errors == {"name": [NAME_TAKEN_MESSAGE]}
    assert all_names() == []


def test_create_projects_unique_index_failure_saves_none(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_project(raw("Existing"))
    # Simulate a project being added between the name check and the commit.
    monkeypatch.setattr(services, "_name_taken", lambda name, exclude_id: False)
    with pytest.raises(ProjectValidationError) as exc_info:
        create_projects([raw("New one"), raw("EXISTING")])
    assert exc_info.value.errors == {"name": [NAME_TAKEN_MESSAGE]}
    assert all_names() == ["Existing"]


def test_create_projects_database_error_saves_none(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_commit() -> None:
        db.session.flush()  # the rows reach the database before the failure
        raise OperationalError("COMMIT", {}, Exception("disk I/O error"))

    monkeypatch.setattr(db.session, "commit", failing_commit)
    with pytest.raises(OperationalError):
        create_projects([raw("A"), raw("B")])
    monkeypatch.undo()
    assert all_names() == []


# --- importer.confirm.save_rows --------------------------------------------------


def test_save_rows_saves_every_row(app: Flask) -> None:
    projects = save_rows([source(2, "A"), source(4, "B", category="tech")])
    assert [p.name for p in projects] == ["A", "B"]
    assert all_names() == ["A", "B"]
    assert projects[1].category == "Tech"


def test_save_rows_name_taken_since_preview_saves_none(app: Flask) -> None:
    create_project(raw("b"))
    with pytest.raises(ImportChangedError) as exc_info:
        save_rows([source(2, "A"), source(3, "B")])
    assert [(r.number, r.status) for r in exc_info.value.preview.rows] == [
        (2, "valid"),
        (3, "skipped"),
    ]
    assert all_names() == ["b"]


def test_save_rows_tampered_row_saves_none(app: Flask) -> None:
    with pytest.raises(ImportChangedError) as exc_info:
        save_rows([source(2, "A"), source(3, "B", priority="Urgent")])
    assert exc_info.value.preview.rows[1].status == "invalid"
    assert all_names() == []


def test_save_rows_failed_write_gives_fresh_preview(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_create(raws: object) -> list[Project]:
        raise ProjectValidationError({"name": [NAME_TAKEN_MESSAGE]})

    monkeypatch.setattr(confirm, "create_projects", failing_create)
    with pytest.raises(ImportChangedError) as exc_info:
        save_rows([source(2, "A")])
    assert exc_info.value.preview.rows[0].status == "valid"
    assert all_names() == []


def test_save_rows_without_rows_saves_none(app: Flask) -> None:
    with pytest.raises(ImportChangedError):
        save_rows([])
