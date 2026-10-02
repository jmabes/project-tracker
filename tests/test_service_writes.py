from datetime import date

import pytest
from flask import Flask
from sqlalchemy import select

from project_tracker import services
from project_tracker.extensions import db
from project_tracker.models import Project
from project_tracker.services import (
    NAME_TAKEN_MESSAGE,
    ProjectValidationError,
    create_project,
    delete_project,
    update_project,
)


def valid_input(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "name": "Build a shed",
        "category": "Home",
        "medium": "DIY",
        "priority": "Medium",
        "status": "Not started",
        "start_date": "",
        "target_date": "",
    }
    raw.update(overrides)
    return raw


def all_names() -> list[str]:
    return list(db.session.scalars(select(Project.name).order_by(Project.id)))


# --- create_project ---------------------------------------------------------


def test_create_project_saves_cleaned_values(app: Flask) -> None:
    project = create_project(
        valid_input(name="  Build a shed ", start_date="2026-03-01")
    )

    assert project.id is not None
    saved = db.session.get(Project, project.id)
    assert saved is not None
    assert saved.name == "Build a shed"
    assert saved.category == "Home"
    assert saved.start_date == date(2026, 3, 1)
    assert saved.target_date is None


def test_create_project_invalid_input_writes_nothing(app: Flask) -> None:
    with pytest.raises(ProjectValidationError) as exc_info:
        create_project(valid_input(name="", priority="Urgent"))

    assert set(exc_info.value.errors) == {"name", "priority"}
    assert all_names() == []


@pytest.mark.parametrize(
    ("existing", "candidate"),
    [("Build a shed", "BUILD A SHED"), ("Café", "CAFÉ"), ("Straße", "STRASSE")],
)
def test_create_project_rejects_duplicate_names_in_any_case(
    app: Flask, existing: str, candidate: str
) -> None:
    create_project(valid_input(name=existing))

    with pytest.raises(ProjectValidationError) as exc_info:
        create_project(valid_input(name=candidate))

    assert exc_info.value.errors == {"name": [NAME_TAKEN_MESSAGE]}
    assert all_names() == [existing]


def test_create_project_turns_index_violation_into_name_error(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate a race: the Python check passes, the database index catches it.
    create_project(valid_input(name="Shed"))
    monkeypatch.setattr(services, "_name_taken", lambda name, exclude_id: False)

    with pytest.raises(ProjectValidationError) as exc_info:
        create_project(valid_input(name="SHED"))

    assert exc_info.value.errors == {"name": [NAME_TAKEN_MESSAGE]}
    # The session was rolled back and is usable again.
    assert all_names() == ["Shed"]
    create_project(valid_input(name="Garage"))
    assert all_names() == ["Shed", "Garage"]


# --- update_project ---------------------------------------------------------


def test_update_project_saves_new_values(app: Flask) -> None:
    project = create_project(valid_input())

    update_project(
        project,
        valid_input(
            name="Build a bigger shed",
            status="In progress",
            start_date="2026-03-01",
            target_date="2026-05-01",
        ),
    )

    db.session.expire_all()
    saved = db.session.get(Project, project.id)
    assert saved is not None
    assert saved.name == "Build a bigger shed"
    assert saved.status == "In progress"
    assert saved.target_date == date(2026, 5, 1)


def test_update_project_may_keep_its_own_name_in_another_case(app: Flask) -> None:
    project = create_project(valid_input(name="Café"))

    update_project(project, valid_input(name="CAFÉ"))

    assert all_names() == ["CAFÉ"]


def test_update_project_cannot_take_another_projects_name(app: Flask) -> None:
    create_project(valid_input(name="Café"))
    project = create_project(valid_input(name="Garage"))

    with pytest.raises(ProjectValidationError) as exc_info:
        update_project(project, valid_input(name="café"))

    assert exc_info.value.errors == {"name": [NAME_TAKEN_MESSAGE]}
    db.session.expire_all()
    assert all_names() == ["Café", "Garage"]


def test_update_project_invalid_input_changes_nothing(app: Flask) -> None:
    project = create_project(valid_input(status="Not started"))

    with pytest.raises(ProjectValidationError):
        update_project(project, valid_input(status="Done", category="Garden"))

    db.session.expire_all()
    saved = db.session.get(Project, project.id)
    assert saved is not None
    assert saved.status == "Not started"


def test_update_project_turns_index_violation_into_name_error(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_project(valid_input(name="Shed"))
    project = create_project(valid_input(name="Garage"))
    monkeypatch.setattr(services, "_name_taken", lambda name, exclude_id: False)

    with pytest.raises(ProjectValidationError) as exc_info:
        update_project(project, valid_input(name="shed"))

    assert exc_info.value.errors == {"name": [NAME_TAKEN_MESSAGE]}
    assert project.name == "Garage"  # rollback reloads the stored value
    assert all_names() == ["Shed", "Garage"]


@pytest.mark.parametrize("status", ["Done", "Abandoned"])
def test_finishing_a_project_only_changes_status(app: Flask, status: str) -> None:
    project = create_project(valid_input())

    update_project(project, valid_input(status=status))

    db.session.expire_all()
    saved = db.session.get(Project, project.id)
    assert saved is not None
    assert saved.status == status
    assert saved.name == "Build a shed"


# --- delete_project ---------------------------------------------------------


def test_delete_project_removes_only_that_project(app: Flask) -> None:
    keep = create_project(valid_input(name="Keep"))
    remove = create_project(valid_input(name="Remove"))

    delete_project(remove)

    assert all_names() == ["Keep"]
    assert db.session.get(Project, keep.id) is not None


def test_deleted_name_can_be_reused(app: Flask) -> None:
    delete_project(create_project(valid_input(name="Shed")))

    create_project(valid_input(name="SHED"))

    assert all_names() == ["SHED"]
