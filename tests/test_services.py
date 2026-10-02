from datetime import date, datetime

import pytest
from flask import Flask

from project_tracker import choices
from project_tracker.extensions import db
from project_tracker.models import Project
from project_tracker.services import (
    ProjectData,
    ProjectValidationError,
    validate_project,
)

REQUIRED_FIELDS = ["name", "category", "medium", "priority", "status"]


def valid_input(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "name": "Build a shed",
        "category": "Home",
        "medium": "DIY",
        "priority": "Medium",
        "status": "Not started",
        "start_date": None,
        "target_date": None,
    }
    raw.update(overrides)
    return raw


def errors_for(
    raw: dict[str, object], exclude_id: int | None = None
) -> dict[str, list[str]]:
    with pytest.raises(ProjectValidationError) as exc_info:
        validate_project(raw, exclude_id=exclude_id)
    return exc_info.value.errors


def add_project(name: str) -> Project:
    project = Project(
        name=name, category="Tech", medium="Coding", priority="Low", status="Done"
    )
    db.session.add(project)
    db.session.commit()
    return project


# --- happy path -------------------------------------------------------------


def test_valid_input_returns_cleaned_data(app: Flask) -> None:
    data = validate_project(
        valid_input(
            name="  Build a shed  ",
            category=" Home ",
            start_date="2026-03-01",
            target_date="2026-04-01",
        )
    )

    assert data == ProjectData(
        name="Build a shed",
        category="Home",
        medium="DIY",
        priority="Medium",
        status="Not started",
        start_date=date(2026, 3, 1),
        target_date=date(2026, 4, 1),
    )


def test_optional_dates_may_be_omitted_entirely(app: Flask) -> None:
    raw = valid_input()
    del raw["start_date"], raw["target_date"]

    data = validate_project(raw)

    assert data.start_date is None
    assert data.target_date is None


# --- required fields --------------------------------------------------------


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
@pytest.mark.parametrize("blank", [None, "", "   "], ids=["none", "empty", "spaces"])
def test_required_field_missing_or_blank(
    app: Flask, field: str, blank: str | None
) -> None:
    errors = errors_for(valid_input(**{field: blank}))

    assert list(errors) == [field]
    assert "required" in errors[field][0]


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_required_field_absent_from_input(app: Flask, field: str) -> None:
    raw = valid_input()
    del raw[field]

    assert list(errors_for(raw)) == [field]


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_non_text_values_are_rejected(app: Flask, field: str) -> None:
    errors = errors_for(valid_input(**{field: 1984.0}))

    assert errors == {field: [f"{field.capitalize()} must be text."]}


def test_all_errors_reported_together(app: Flask) -> None:
    errors = errors_for(
        valid_input(
            name="",
            category="Garden",
            start_date="2026-05-01",
            target_date="2026-04-01",
        )
    )

    assert set(errors) == {"name", "category", "target_date"}


# --- name -------------------------------------------------------------------


def test_name_at_max_length_is_accepted(app: Flask) -> None:
    assert validate_project(valid_input(name="x" * 200)).name == "x" * 200


def test_name_over_max_length_is_rejected(app: Flask) -> None:
    errors = errors_for(valid_input(name="x" * 201))

    assert errors == {"name": ["Name must be at most 200 characters."]}


def test_name_length_measured_after_trimming(app: Flask) -> None:
    assert validate_project(valid_input(name=f"  {'x' * 200}  ")).name == "x" * 200


@pytest.mark.parametrize(
    "candidate", ["Home Server", "home server", "HOME SERVER", "  hOmE sErVeR  "]
)
def test_duplicate_name_rejected_case_insensitively(app: Flask, candidate: str) -> None:
    add_project("Home Server")

    errors = errors_for(valid_input(name=candidate))

    assert errors == {"name": ["A project with this name already exists."]}


@pytest.mark.parametrize(
    ("existing", "candidate"), [("Café", "CAFÉ"), ("Straße", "STRASSE")]
)
def test_duplicate_name_rejected_for_non_ascii_case(
    app: Flask, existing: str, candidate: str
) -> None:
    # SQLite's lower() only folds ASCII; the service must still catch these.
    add_project(existing)

    assert "name" in errors_for(valid_input(name=candidate))


def test_different_name_is_accepted(app: Flask) -> None:
    add_project("Home Server")

    assert validate_project(valid_input(name="Home Server 2")).name == "Home Server 2"


def test_editing_a_project_may_keep_its_own_name(app: Flask) -> None:
    project = add_project("Home Server")

    data = validate_project(valid_input(name="home server"), exclude_id=project.id)

    assert data.name == "home server"


def test_editing_cannot_take_another_projects_name(app: Flask) -> None:
    add_project("Home Server")
    other = add_project("Budget")

    errors = errors_for(valid_input(name="HOME SERVER"), exclude_id=other.id)

    assert "name" in errors


# --- allowed values ---------------------------------------------------------

CHOICES = [
    ("category", choices.CATEGORIES),
    ("medium", choices.MEDIUMS),
    ("priority", choices.PRIORITIES),
    ("status", choices.STATUSES),
]


@pytest.mark.parametrize(
    ("field", "value"),
    [(field, value) for field, allowed in CHOICES for value in allowed],
)
def test_every_allowed_value_is_accepted(app: Flask, field: str, value: str) -> None:
    data = validate_project(valid_input(**{field: value}))

    assert getattr(data, field) == value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", "Garden"),
        ("category", "tech"),
        ("medium", "Writing"),
        ("priority", "Urgent"),
        ("priority", "high"),
        ("status", "Complete"),
        ("status", "not started"),
    ],
)
def test_values_outside_allowed_list_are_rejected(
    app: Flask, field: str, value: str
) -> None:
    errors = errors_for(valid_input(**{field: value}))

    assert list(errors) == [field]
    assert "must be one of" in errors[field][0]


def test_allowed_values_match_the_domain_model() -> None:
    assert choices.CATEGORIES == ("Tech", "Finance", "Home")
    assert choices.MEDIUMS == ("Coding", "Hardware", "Research", "DIY")
    assert choices.PRIORITIES == ("High", "Medium", "Low")
    assert choices.STATUSES == (
        "Not started",
        "In progress",
        "On hold",
        "Done",
        "Abandoned",
    )


# --- dates ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-03-01", date(2026, 3, 1)),
        (" 2026-03-01 ", date(2026, 3, 1)),
        (date(2026, 3, 1), date(2026, 3, 1)),
        (datetime(2026, 3, 1, 0, 0), date(2026, 3, 1)),
        (datetime(2026, 3, 1, 15, 30), date(2026, 3, 1)),
        (None, None),
        ("", None),
        ("  ", None),
    ],
)
@pytest.mark.parametrize("field", ["start_date", "target_date"])
def test_accepted_date_inputs(
    app: Flask, field: str, value: object, expected: date | None
) -> None:
    data = validate_project(valid_input(**{field: value}))

    assert getattr(data, field) == expected


@pytest.mark.parametrize(
    "value",
    ["2026/03/01", "01/03/2026", "20260301", "2026-3-1", "2026-02-30", "soon", 45000],
)
@pytest.mark.parametrize("field", ["start_date", "target_date"])
def test_rejected_date_inputs(app: Flask, field: str, value: object) -> None:
    errors = errors_for(valid_input(**{field: value}))

    assert list(errors) == [field]
    assert "YYYY-MM-DD" in errors[field][0]


# --- date order -------------------------------------------------------------


def test_target_before_start_is_rejected(app: Flask) -> None:
    errors = errors_for(valid_input(start_date="2026-05-02", target_date="2026-05-01"))

    assert errors == {
        "target_date": ["Target date must be on or after the start date."]
    }


def test_target_on_start_date_is_accepted(app: Flask) -> None:
    data = validate_project(
        valid_input(start_date="2026-05-01", target_date="2026-05-01")
    )

    assert data.start_date == data.target_date == date(2026, 5, 1)


@pytest.mark.parametrize(
    ("start", "target"), [("2026-05-01", None), (None, "2026-05-01")]
)
def test_date_order_not_checked_when_one_date_missing(
    app: Flask, start: str | None, target: str | None
) -> None:
    validate_project(valid_input(start_date=start, target_date=target))


def test_date_order_compares_mixed_input_types(app: Flask) -> None:
    errors = errors_for(
        valid_input(
            start_date=datetime(2026, 5, 2, 9, 0),
            target_date="2026-05-01",
        )
    )

    assert "target_date" in errors
