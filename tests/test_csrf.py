"""CSRF protection with it switched on (the testing config turns it off)."""

import re
from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from project_tracker import create_app
from project_tracker.extensions import db
from project_tracker.models import Project
from project_tracker.services import create_project

TOKEN_RE = re.compile(r'name="csrf_token" type="hidden" value="([^"]+)"')
TOKEN_RE_ALT = re.compile(r'type="hidden" name="csrf_token" value="([^"]+)"')

FORM_DATA = {
    "name": "Build a shed",
    "category": "Home",
    "medium": "DIY",
    "priority": "Medium",
    "status": "Not started",
}


@pytest.fixture()
def app() -> Iterator[Flask]:
    app = create_app("testing", overrides={"WTF_CSRF_ENABLED": True})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def project(app: Flask) -> Project:
    return create_project({**FORM_DATA, "name": "Existing"})


def token_from(client: FlaskClient, path: str) -> str:
    text = client.get(path).text
    match = TOKEN_RE.search(text) or TOKEN_RE_ALT.search(text)
    assert match, f"no CSRF token rendered on {path}"
    return match.group(1)


def names() -> list[str]:
    db.session.expire_all()
    return list(db.session.scalars(select(Project.name).order_by(Project.id)))


def post_targets(project: Project) -> list[tuple[str, str, dict[str, str]]]:
    """(page that renders the form, URL it posts to, form data) for each POST."""
    return [
        ("/projects/new", "/projects", {**FORM_DATA, "name": "New one"}),
        (
            f"/projects/{project.id}/edit",
            f"/projects/{project.id}/edit",
            {**FORM_DATA, "name": "Renamed"},
        ),
        (f"/projects/{project.id}/delete", f"/projects/{project.id}/delete", {}),
    ]


@pytest.mark.parametrize("target", [0, 1, 2], ids=["create", "edit", "delete"])
def test_post_without_token_is_rejected(
    app: Flask, client: FlaskClient, project: Project, target: int
) -> None:
    _, url, data = post_targets(project)[target]

    response = client.post(url, data=data)

    assert response.status_code == 400
    assert "CSRF" in response.text
    assert names() == ["Existing"]


@pytest.mark.parametrize("target", [0, 1, 2], ids=["create", "edit", "delete"])
def test_post_with_forged_token_is_rejected(
    app: Flask, client: FlaskClient, project: Project, target: int
) -> None:
    page, url, data = post_targets(project)[target]
    client.get(page)  # start a session, as a real browser would

    response = client.post(url, data={**data, "csrf_token": "forged"})

    assert response.status_code == 400
    assert names() == ["Existing"]


def test_token_from_another_session_is_rejected(app: Flask, project: Project) -> None:
    token = token_from(app.test_client(), "/projects/new")

    response = app.test_client().post(
        "/projects", data={**FORM_DATA, "csrf_token": token}
    )

    assert response.status_code == 400
    assert names() == ["Existing"]


@pytest.mark.parametrize(
    ("target", "expected"),
    [(0, ["Existing", "New one"]), (1, ["Renamed"]), (2, [])],
    ids=["create", "edit", "delete"],
)
def test_post_with_rendered_token_succeeds(
    app: Flask,
    client: FlaskClient,
    project: Project,
    target: int,
    expected: list[str],
) -> None:
    page, url, data = post_targets(project)[target]
    token = token_from(client, page)

    response = client.post(url, data={**data, "csrf_token": token})

    assert response.status_code == 302
    assert names() == expected
