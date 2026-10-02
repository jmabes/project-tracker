from datetime import date

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from project_tracker.extensions import db
from project_tracker.models import Project


def make_project(**fields: object) -> Project:
    values: dict[str, object] = {
        "name": "Build a shed",
        "category": "Home",
        "medium": "DIY",
        "priority": "Medium",
        "status": "Not started",
    }
    values.update(fields)
    return Project(**values)


def test_project_round_trips_all_fields(app: Flask) -> None:
    project = make_project(start_date=date(2026, 3, 1), target_date=date(2026, 4, 1))
    db.session.add(project)
    db.session.commit()
    project_id = project.id
    db.session.expunge_all()

    stored = db.session.get(Project, project_id)

    assert stored is not None
    assert stored.name == "Build a shed"
    assert (stored.category, stored.medium) == ("Home", "DIY")
    assert (stored.priority, stored.status) == ("Medium", "Not started")
    assert stored.start_date == date(2026, 3, 1)
    assert stored.target_date == date(2026, 4, 1)


def test_optional_dates_default_to_none(app: Flask) -> None:
    project = make_project()
    db.session.add(project)
    db.session.commit()

    assert project.start_date is None
    assert project.target_date is None


def test_timestamps_set_on_insert_and_update(app: Flask) -> None:
    project = make_project()
    db.session.add(project)
    db.session.commit()
    created_at, first_updated_at = project.created_at, project.updated_at

    assert created_at is not None
    assert first_updated_at is not None

    project.status = "In progress"
    db.session.commit()

    assert project.created_at == created_at
    assert project.updated_at >= first_updated_at


@pytest.mark.parametrize("field", ["name", "category", "medium", "priority", "status"])
def test_required_columns_are_not_nullable(app: Flask, field: str) -> None:
    db.session.add(make_project(**{field: None}))

    with pytest.raises(IntegrityError):
        db.session.commit()


def test_database_rejects_case_insensitive_duplicate_name(app: Flask) -> None:
    db.session.add(make_project(name="Home Server"))
    db.session.commit()

    db.session.add(make_project(name="HOME server"))

    with pytest.raises(IntegrityError):
        db.session.commit()
