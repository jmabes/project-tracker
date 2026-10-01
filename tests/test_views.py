from flask import Flask
from flask.testing import FlaskClient

from project_tracker.models import Project
from project_tracker.services import create_project


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
