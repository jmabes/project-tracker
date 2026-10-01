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


def test_index_lists_projects_linking_to_detail(
    app: Flask, client: FlaskClient
) -> None:
    shed = make_project(name="Build a shed")
    cafe = make_project(name="café rewrite", status="In progress")

    response = client.get("/")

    assert response.status_code == 200
    for project in (shed, cafe):
        assert f'href="/projects/{project.id}"' in response.text


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


# --- edit -------------------------------------------------------------------


def test_edit_form_is_filled_with_saved_values(app: Flask, client: FlaskClient) -> None:
    project = make_project(
        name="Home server",
        category="Tech",
        medium="Hardware",
        priority="High",
        status="On hold",
        start_date="2026-03-01",
        estimated_completion_date="2026-04-15",
    )

    response = client.get(f"/projects/{project.id}/edit")

    assert response.status_code == 200
    text = response.text
    assert f'action="/projects/{project.id}/edit"' in text
    assert 'value="Home server"' in text
    for value in ("Tech", "Hardware", "High", "On hold"):
        assert f'<option selected value="{value}">{value}</option>' in text
    assert 'name="start_date" type="date" value="2026-03-01"' in text
    assert 'name="estimated_completion_date" type="date" value="2026-04-15"' in text


def test_detail_links_to_edit(app: Flask, client: FlaskClient) -> None:
    project = make_project()

    response = client.get(f"/projects/{project.id}")

    assert f'href="/projects/{project.id}/edit"' in response.text


def test_edit_saves_and_redirects_to_detail(app: Flask, client: FlaskClient) -> None:
    project = make_project()

    response = client.post(
        f"/projects/{project.id}/edit",
        data=form_data(
            name="Build a bigger shed",
            priority="High",
            start_date="2026-06-01",
        ),
    )

    assert response.status_code == 302
    assert response.headers["Location"] == f"/projects/{project.id}"
    [saved] = all_projects()
    assert saved.name == "Build a bigger shed"
    assert saved.priority == "High"
    assert saved.start_date is not None
    assert saved.start_date.isoformat() == "2026-06-01"
    page = client.get(response.headers["Location"])
    assert "Saved “Build a bigger shed”." in page.text


def test_edit_can_clear_optional_dates(app: Flask, client: FlaskClient) -> None:
    project = make_project(start_date="2026-03-01")

    client.post(f"/projects/{project.id}/edit", data=form_data(start_date=""))

    [saved] = all_projects()
    assert saved.start_date is None


@pytest.mark.parametrize("new_name", ["Café", "CAFÉ", "  café  "])
def test_edit_may_keep_its_own_name_in_any_case(
    app: Flask, client: FlaskClient, new_name: str
) -> None:
    project = make_project(name="Café")

    response = client.post(
        f"/projects/{project.id}/edit", data=form_data(name=new_name)
    )

    assert response.status_code == 302
    [saved] = all_projects()
    assert saved.name == new_name.strip()


@pytest.mark.parametrize("candidate", ["Café", "CAFÉ", "café"])
def test_edit_rejects_another_projects_name(
    app: Flask, client: FlaskClient, candidate: str
) -> None:
    make_project(name="Café")
    project = make_project(name="Garage")

    response = client.post(
        f"/projects/{project.id}/edit", data=form_data(name=candidate)
    )

    assert response.status_code == 200
    assert NAME_TAKEN_MESSAGE in response.text
    assert 'id="name-errors"' in response.text
    assert f'value="{candidate}"' in response.text
    assert [p.name for p in all_projects()] == ["Café", "Garage"]


def test_edit_invalid_input_rerenders_and_changes_nothing(
    app: Flask, client: FlaskClient
) -> None:
    project = make_project(name="Build a shed", status="Not started")

    response = client.post(
        f"/projects/{project.id}/edit",
        data=form_data(name="", status="Done", start_date="2026-13-01"),
    )

    assert response.status_code == 200
    text = response.text
    assert "Edit “Build a shed”" in text  # heading keeps the saved name
    assert "Name is required." in text
    assert 'id="start_date-errors"' in text
    assert '<option selected value="Done">Done</option>' in text
    assert 'value="2026-13-01"' in text
    [saved] = all_projects()
    assert saved.name == "Build a shed"
    assert saved.status == "Not started"


def test_edit_post_missing_fields_does_not_keep_saved_values(
    app: Flask, client: FlaskClient
) -> None:
    project = make_project()

    response = client.post(f"/projects/{project.id}/edit", data={"name": "Renamed"})

    assert response.status_code == 200
    assert "Status is required." in response.text
    [saved] = all_projects()
    assert saved.name == "Build a shed"


@pytest.mark.parametrize("status", ["Done", "Abandoned"])
def test_finishing_a_project_keeps_it_visible(
    app: Flask, client: FlaskClient, status: str
) -> None:
    project = make_project(name="Build a shed", status="In progress")

    response = client.post(
        f"/projects/{project.id}/edit", data=form_data(status=status)
    )

    assert response.status_code == 302
    [saved] = all_projects()
    assert saved.status == status
    detail = client.get(f"/projects/{project.id}")
    assert detail.status_code == 200
    assert "Build a shed" in detail.text
    assert status in detail.text


@pytest.mark.parametrize("method", ["get", "post"])
def test_edit_unknown_id_is_404(client: FlaskClient, method: str) -> None:
    response = getattr(client, method)("/projects/999/edit", data=form_data())

    assert response.status_code == 404


# --- delete -----------------------------------------------------------------


def test_detail_links_to_delete_confirmation(app: Flask, client: FlaskClient) -> None:
    project = make_project()

    response = client.get(f"/projects/{project.id}")

    assert f'href="/projects/{project.id}/delete"' in response.text


def test_delete_get_shows_confirmation_and_deletes_nothing(
    app: Flask, client: FlaskClient
) -> None:
    project = make_project(name="Build a shed")

    response = client.get(f"/projects/{project.id}/delete")

    assert response.status_code == 200
    assert "Delete “Build a shed”?" in response.text
    assert (
        f'<form method="post" action="/projects/{project.id}/delete">' in response.text
    )
    assert len(all_projects()) == 1


def test_delete_post_removes_project_and_redirects(
    app: Flask, client: FlaskClient
) -> None:
    keep = make_project(name="Keep me")
    project = make_project(name="Build a shed")

    response = client.post(f"/projects/{project.id}/delete")

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert [p.name for p in all_projects()] == [keep.name]
    index = client.get("/")
    assert "Deleted “Build a shed”." in index.text
    assert client.get(f"/projects/{project.id}").status_code == 404


@pytest.mark.parametrize("method", ["put", "delete", "patch"])
def test_delete_only_accepts_get_and_post(
    app: Flask, client: FlaskClient, method: str
) -> None:
    project = make_project()

    response = getattr(client, method)(f"/projects/{project.id}/delete")

    assert response.status_code == 405
    assert len(all_projects()) == 1


@pytest.mark.parametrize("method", ["get", "post"])
def test_delete_unknown_id_is_404(client: FlaskClient, method: str) -> None:
    assert getattr(client, method)("/projects/999/delete").status_code == 404
