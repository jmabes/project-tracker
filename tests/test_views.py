import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from project_tracker import choices
from project_tracker.extensions import db
from project_tracker.models import Project
from project_tracker.services import NAME_TAKEN_MESSAGE, create_project


def make_project(**overrides: object) -> Project:
    raw: dict[str, object] = {
        "name": "Build a shed",
        "category": "Home",
        "medium": "DIY",
        "priority": "Medium",
        "status": "Not started",
    }
    raw.update(overrides)
    return create_project(raw)


def form_data(**overrides: str) -> dict[str, str]:
    data = {
        "name": "Build a shed",
        "category": "Home",
        "medium": "DIY",
        "priority": "Medium",
        "status": "Not started",
        "start_date": "",
        "estimated_completion_date": "",
    }
    data.update(overrides)
    return data


def all_projects() -> list[Project]:
    db.session.expire_all()
    return list(db.session.scalars(select(Project).order_by(Project.id)))


# --- layout and index -------------------------------------------------------


def test_index_with_no_projects(client: FlaskClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "No projects yet." in response.text
    assert "Project Tracker" in response.text  # site header from base layout


def test_index_lists_every_project_linking_to_detail(
    app: Flask, client: FlaskClient
) -> None:
    shed = make_project(name="Build a shed")
    done = make_project(name="Ancient project", status="Done")
    gone = make_project(name="café rewrite", status="Abandoned")

    response = client.get("/")

    assert response.status_code == 200
    for project in (shed, done, gone):
        assert f'href="/projects/{project.id}"' in response.text
    # Sorted by name, ignoring case.
    text = response.text
    assert text.index("Ancient project") < text.index("Build a shed")
    assert text.index("Build a shed") < text.index("café rewrite")


def test_index_escapes_project_names(app: Flask, client: FlaskClient) -> None:
    make_project(name="<script>alert(1)</script>")

    response = client.get("/")

    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_stylesheet_is_served(client: FlaskClient) -> None:
    response = client.get("/static/style.css")

    assert response.status_code == 200
    response.close()


# --- detail -----------------------------------------------------------------


def test_detail_shows_all_fields(app: Flask, client: FlaskClient) -> None:
    project = make_project(
        name="Home server",
        category="Tech",
        medium="Hardware",
        priority="High",
        status="In progress",
        start_date="2026-03-01",
        estimated_completion_date="2026-04-15",
    )

    response = client.get(f"/projects/{project.id}")

    assert response.status_code == 200
    for value in (
        "Home server",
        "Tech",
        "Hardware",
        "High",
        "In progress",
        "2026-03-01",
        "2026-04-15",
    ):
        assert value in response.text


def test_detail_unknown_id_is_404(client: FlaskClient) -> None:
    assert client.get("/projects/999").status_code == 404


# --- create -----------------------------------------------------------------


def test_new_form_renders_every_field(client: FlaskClient) -> None:
    response = client.get("/projects/new")

    assert response.status_code == 200
    text = response.text
    assert 'action="/projects"' in text
    assert '<input id="name" name="name" type="text" value="">' in text
    for field, values in (
        ("category", choices.CATEGORIES),
        ("medium", choices.MEDIUMS),
        ("priority", choices.PRIORITIES),
        ("status", choices.STATUSES),
    ):
        assert f'<select id="{field}" name="{field}">' in text
        assert '<option value="">Select…</option>' in text
        for value in values:
            assert f'<option value="{value}">{value}</option>' in text
    assert 'id="start_date" name="start_date" type="date"' in text
    assert (
        'id="estimated_completion_date" name="estimated_completion_date" type="date"'
        in text
    )


def test_header_links_to_new_project(client: FlaskClient) -> None:
    assert 'href="/projects/new"' in client.get("/").text


def test_create_saves_and_redirects_to_detail(app: Flask, client: FlaskClient) -> None:
    response = client.post(
        "/projects",
        data=form_data(
            name="  Home server  ",
            category="Tech",
            medium="Hardware",
            priority="High",
            status="In progress",
            start_date="2026-03-01",
            estimated_completion_date="2026-04-15",
        ),
    )

    [project] = all_projects()
    assert response.status_code == 302
    assert response.headers["Location"] == f"/projects/{project.id}"
    assert project.name == "Home server"
    assert project.status == "In progress"
    assert project.start_date is not None
    assert project.start_date.isoformat() == "2026-03-01"

    page = client.get(response.headers["Location"])
    assert "Created “Home server”." in page.text  # flash message


def test_create_with_blank_dates(app: Flask, client: FlaskClient) -> None:
    response = client.post("/projects", data=form_data())

    assert response.status_code == 302
    [project] = all_projects()
    assert project.start_date is None
    assert project.estimated_completion_date is None


def test_create_invalid_input_rerenders_with_values_and_errors(
    app: Flask, client: FlaskClient
) -> None:
    response = client.post(
        "/projects",
        data=form_data(
            name="Too late",
            category="Tech",
            medium="",
            start_date="2026-05-01",
            estimated_completion_date="2026-04-01",
        ),
    )

    assert response.status_code == 200
    assert all_projects() == []
    text = response.text
    # The user's values are kept.
    assert 'value="Too late"' in text
    assert '<option selected value="Tech">Tech</option>' in text
    assert 'value="2026-05-01"' in text
    assert 'value="2026-04-01"' in text
    # Errors appear with the field they belong to.
    assert '<ul class="field-errors" id="medium-errors">' in text
    assert "Medium is required." in text
    assert '<ul class="field-errors" id="estimated_completion_date-errors">' in text
    assert "Estimated completion date must be on or after the start date." in text
    assert 'id="name-errors"' not in text


def test_create_with_missing_fields_reports_each(
    app: Flask, client: FlaskClient
) -> None:
    response = client.post("/projects", data={})

    assert response.status_code == 200
    assert all_projects() == []
    for field in ("name", "category", "medium", "priority", "status"):
        assert f'id="{field}-errors"' in response.text


def test_create_rejects_tampered_choice_and_bad_date(
    app: Flask, client: FlaskClient
) -> None:
    response = client.post(
        "/projects", data=form_data(status="Archived", start_date="01/03/2026")
    )

    assert response.status_code == 200
    assert all_projects() == []
    assert "Status must be one of:" in response.text
    assert "is not a valid date; use YYYY-MM-DD." in response.text


@pytest.mark.parametrize(
    ("existing", "candidate"),
    [("Build a shed", "build a SHED"), ("Café", "CAFÉ"), ("café", "Café")],
)
def test_create_rejects_duplicate_name_in_any_case(
    app: Flask, client: FlaskClient, existing: str, candidate: str
) -> None:
    make_project(name=existing)

    response = client.post("/projects", data=form_data(name=candidate))

    assert response.status_code == 200
    assert NAME_TAKEN_MESSAGE in response.text
    assert 'id="name-errors"' in response.text
    assert [p.name for p in all_projects()] == [existing]
