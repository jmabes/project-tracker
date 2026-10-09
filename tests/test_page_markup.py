"""Detail and error page markup that style.css relies on."""

from flask import Flask, render_template
from flask.testing import FlaskClient

from project_tracker.services import create_project


def test_detail_shows_status_pill_and_priority_dot(
    app: Flask, client: FlaskClient
) -> None:
    project = create_project(
        {
            "name": "Shed",
            "category": "Home",
            "medium": "DIY",
            "priority": "High",
            "status": "On hold",
        }
    )
    text = client.get(f"/projects/{project.id}").text
    assert '<dd class="priority" data-priority="High">High</dd>' in text
    assert '<dd><span class="badge" data-status="On hold">On hold</span></dd>' in text


def test_detail_marks_delete_as_destructive(app: Flask, client: FlaskClient) -> None:
    project = create_project(
        {
            "name": "Shed",
            "category": "Home",
            "medium": "DIY",
            "priority": "Low",
            "status": "Not started",
        }
    )
    text = client.get(f"/projects/{project.id}").text
    assert f'<a class="danger" href="/projects/{project.id}/delete">Delete</a>' in text


def test_413_page_offers_a_button_back_to_import(app: Flask) -> None:
    with app.test_request_context("/import/", method="POST"):
        page = render_template("errors/413.html", limit="2 MB")
    actions = page[page.index('<div class="actions">') :]
    assert '<a href="/import/">Back to import</a>' in actions
