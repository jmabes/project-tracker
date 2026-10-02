import html
import json
import re
import tempfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import IO

import pytest
from flask import Flask, Request
from flask.testing import FlaskClient
from sqlalchemy import select
from werkzeug.wrappers import Response

from project_tracker import create_app
from project_tracker.config import MAX_UPLOAD_BYTES
from project_tracker.extensions import db
from project_tracker.models import Project
from project_tracker.services import create_project

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_FILES = ["projects.csv", "projects-bom.csv", "projects.xlsx", "projects.ods"]
ROWS_RE = re.compile(r'name="rows" value="([^"]*)"')
HEADER = "Name,Category,Medium,Priority,Status,Start date,Target date\r\n"


def make_project(name: str) -> Project:
    return create_project(
        {
            "name": name,
            "category": "Home",
            "medium": "DIY",
            "priority": "Low",
            "status": "Not started",
        }
    )


def all_projects() -> list[Project]:
    db.session.expire_all()
    return list(db.session.scalars(select(Project).order_by(Project.id)))


def names() -> list[str]:
    return [p.name for p in all_projects()]


BOUNDARY = "test-boundary-0123456789"


def upload(client: FlaskClient, filename: str, data: bytes) -> Response:
    """POST a file as a browser would, building the multipart body in memory.

    Passing raw bytes keeps the test client from spooling big bodies to a
    temporary file of its own, which it never closes.
    """
    body = (
        (
            f"--{BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + data
        + f"\r\n--{BOUNDARY}--\r\n".encode()
    )
    return client.post(
        "/import/",
        data=body,
        content_type=f"multipart/form-data; boundary={BOUNDARY}",
    )


def upload_fixture(client: FlaskClient, name: str) -> Response:
    return upload(client, name, (FIXTURES / name).read_bytes())


def page_text(response: Response) -> str:
    """Return the page with entities decoded and whitespace collapsed."""
    return " ".join(html.unescape(response.text).split())


def payload_from(response: Response) -> str:
    match = ROWS_RE.search(response.text)
    assert match, "no confirm form on the preview page"
    return html.unescape(match.group(1))


def confirm(client: FlaskClient, payload: str) -> Response:
    return client.post("/import/confirm", data={"rows": payload})


# --- upload page ---------------------------------------------------------------


def test_upload_page(client: FlaskClient) -> None:
    response = client.get("/import/")
    assert response.status_code == 200
    assert 'enctype="multipart/form-data"' in page_text(response)
    assert 'accept=".csv,.xlsx,.ods"' in page_text(response)
    assert "up to 2 MB" in page_text(response)
    assert "<code>target_date</code>" in page_text(response)


def test_header_links_to_import(client: FlaskClient) -> None:
    assert 'href="/import/"' in page_text(client.get("/"))


# --- preview -------------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_FILES)
def test_preview_shows_every_row_and_writes_nothing(
    app: Flask, client: FlaskClient, name: str
) -> None:
    make_project("Garage shelves")

    response = upload_fixture(client, name)

    assert response.status_code == 200
    text = page_text(response)
    assert f"<strong>{name}</strong>" in text
    assert "3 ready to import, 3 with errors, 2 skipped (duplicate name)" in text
    assert "Ignored columns: Notes." in text
    for number in (2, 3, 4, 5, 6, 8, 9, 10):
        assert f"<td>{number}</td>" in text
    assert "Category must be one of: Tech, Finance, Home." in text
    assert "Same name as row 2 in this file." in text
    assert "A project named “Garage shelves” already exists." in text
    assert "Import 3 projects" in text
    assert names() == ["Garage shelves"]


def test_preview_shows_cleaned_values_for_valid_rows(client: FlaskClient) -> None:
    text = page_text(upload_fixture(client, "projects.xlsx"))
    assert "<td>Finance</td>" in text
    # The native date-time cell is shown as a date only.
    assert '<td class="date">2026-06-30</td>' in text
    assert '<td class="name">1984</td>' in text


def test_preview_with_no_valid_rows_has_no_confirm_form(client: FlaskClient) -> None:
    data = (HEADER + "A,Nope,DIY,Low,Done,,\r\n").encode()
    response = upload(client, "bad.csv", data)
    assert response.status_code == 200
    assert "No rows can be imported" in page_text(response)
    assert not ROWS_RE.search(response.text)


# --- rejected files ------------------------------------------------------------


def test_upload_without_file(client: FlaskClient) -> None:
    response = client.post("/import/", data={}, content_type="multipart/form-data")
    assert response.status_code == 200
    assert "Choose a file to import." in page_text(response)


@pytest.mark.parametrize(
    "filename", ["projects.xlsm", "projects.xls", "projects.txt", "projects"]
)
def test_other_extensions_are_rejected(
    app: Flask, client: FlaskClient, filename: str
) -> None:
    data = (FIXTURES / "projects.xlsx").read_bytes()
    response = upload(client, filename, data)
    assert response.status_code == 200
    assert "Choose a .csv, .xlsx, .ods file." in page_text(response)
    assert 'aria-invalid="true"' in page_text(response)
    assert names() == []


def test_title_rows_above_header_are_ignored(client: FlaskClient) -> None:
    response = upload_fixture(client, "projects-titled.ods")
    text = page_text(response)
    assert "2 ready to import, 0 with errors, 0 skipped" in text
    assert "Column names found in row 4; the 2 rows above it" in text

    response = confirm(client, payload_from(response))

    assert response.status_code == 302
    assert names() == ["Shed roof", "Tax return"]


def test_missing_required_column_is_reported(client: FlaskClient) -> None:
    response = upload(client, "p.csv", b"Name,Category\r\nA,Tech\r\n")
    assert "missing these required columns: medium, priority, status" in page_text(
        response
    )


def test_corrupt_spreadsheet_is_reported(client: FlaskClient) -> None:
    response = upload(client, "p.ods", b"not a spreadsheet")
    assert "couldn't be read as a spreadsheet" in page_text(response)


def test_oversized_upload_gets_friendly_413_page(
    app: Flask, client: FlaskClient
) -> None:
    data = b"x" * (MAX_UPLOAD_BYTES + 1)

    response = upload(client, "big.csv", data)

    assert response.status_code == 413
    assert "That file is too large" in page_text(response)
    assert "up to 2 MB" in page_text(response)
    assert names() == []


def test_upload_just_under_the_limit_is_accepted(client: FlaskClient) -> None:
    # Leave room for the multipart framing around the file.
    padding = "x" * 100_000
    body = HEADER.replace("\r\n", ",Notes\r\n")
    body += "".join(f"P{i},Tech,Coding,Low,Done,,,{padding}\r\n" for i in range(20))
    data = body.encode()
    assert 2_000_000 < len(data) < MAX_UPLOAD_BYTES - 1_000

    response = upload(client, "big.csv", data)

    assert response.status_code == 200
    assert "20 ready to import" in page_text(response)


# --- confirm -------------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_FILES)
def test_confirm_writes_every_valid_row(
    app: Flask, client: FlaskClient, name: str
) -> None:
    make_project("Garage shelves")
    payload = payload_from(upload_fixture(client, name))

    response = confirm(client, payload)

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    projects = {p.name: p for p in all_projects()}
    assert list(projects) == [
        "Garage shelves",
        "Home server rebuild",
        "Budget review",
        "1984",
    ]
    rebuild = projects["Home server rebuild"]
    assert (rebuild.category, rebuild.medium, rebuild.priority, rebuild.status) == (
        "Tech",
        "Hardware",
        "High",
        "In progress",
    )
    assert rebuild.start_date == date(2026, 1, 10)
    assert rebuild.target_date == date(2026, 6, 30)
    budget = projects["Budget review"]
    assert (budget.category, budget.medium, budget.priority, budget.status) == (
        "Finance",
        "Research",
        "Low",
        "Not started",
    )
    assert budget.start_date == date(2026, 2, 1)
    assert projects["1984"].status == "Done"
    assert "Imported 3 projects." in page_text(client.get("/"))


def test_confirming_twice_does_not_duplicate(client: FlaskClient) -> None:
    payload = payload_from(upload_fixture(client, "projects.ods"))
    confirm(client, payload)

    response = confirm(client, payload)

    assert response.status_code == 200
    assert "Something changed since the preview" in page_text(response)
    assert "0 ready to import, 0 with errors, 4 skipped (duplicate name)" in page_text(
        response
    )
    assert not ROWS_RE.search(response.text)
    assert len(names()) == 4


def test_name_taken_after_preview_writes_nothing(client: FlaskClient) -> None:
    payload = payload_from(upload_fixture(client, "projects.csv"))
    make_project("BUDGET REVIEW")

    response = confirm(client, payload)

    assert response.status_code == 200
    assert "Something changed since the preview" in page_text(response)
    assert "3 ready to import, 0 with errors, 1 skipped (duplicate name)" in page_text(
        response
    )
    assert names() == ["BUDGET REVIEW"]
    # The fresh preview offers the rows that are still valid.
    response = confirm(client, payload_from(response))
    assert response.status_code == 302
    assert names() == [
        "BUDGET REVIEW",
        "Home server rebuild",
        "1984",
        "Garage shelves",
    ]


def test_tampered_payload_is_validated_again(client: FlaskClient) -> None:
    values = {
        "name": "X",
        "category": "Tech",
        "medium": "DIY",
        "priority": "Urgent",
        "status": "Done",
    }
    payload = json.dumps([{"row": 2, "values": values}])

    response = confirm(client, payload)

    assert response.status_code == 200
    assert "Priority must be one of: High, Medium, Low." in page_text(response)
    assert names() == []


@pytest.mark.parametrize("payload", [None, "", "garbage", "[]"])
def test_missing_or_damaged_payload_redirects_to_upload(
    client: FlaskClient, payload: str | None
) -> None:
    data = {} if payload is None else {"rows": payload}

    response = client.post("/import/confirm", data=data)

    assert response.status_code == 302
    assert response.headers["Location"] == "/import/"
    assert "The import data was missing or damaged" in page_text(client.get("/import/"))
    assert names() == []


# --- uploaded files never stay on disk -------------------------------------------


@pytest.fixture()
def recording_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Flask, list[IO[bytes]]]]:
    """App whose requests record every upload stream Werkzeug creates.

    Temporary files go to an empty directory, so the test can check that nothing
    is left in it.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    streams: list[IO[bytes]] = []

    class RecordingRequest(Request):
        def _get_file_stream(
            self,
            total_content_length: int | None,
            content_type: str | None,
            filename: str | None = None,
            content_length: int | None = None,
        ) -> IO[bytes]:
            stream = super()._get_file_stream(
                total_content_length, content_type, filename, content_length
            )
            streams.append(stream)
            return stream

    app = create_app("testing")
    app.request_class = RecordingRequest
    with app.app_context():
        db.create_all()
        yield app, streams
        db.session.remove()
        db.drop_all()


def test_no_uploaded_file_remains_on_disk(
    recording_app: tuple[Flask, list[IO[bytes]]], tmp_path: Path
) -> None:
    app, streams = recording_app
    client = app.test_client()
    # Over Werkzeug's 500 KB in-memory threshold, so the upload spools to a
    # temporary file. The padding goes in an ignored column.
    padding = "x" * 100_000
    body = HEADER.replace("\r\n", ",Notes\r\n")
    body += "".join(f"P{i},Tech,Coding,Low,Done,,,{padding}\r\n" for i in range(8))

    preview = upload(client, "big.csv", body.encode())
    response = confirm(client, payload_from(preview))

    assert response.status_code == 302
    assert len(names()) == 8
    assert streams, "the upload did not go through Werkzeug's file stream"
    # SpooledTemporaryFile's private flag: the upload really did reach disk.
    assert all(getattr(stream, "_rolled", False) for stream in streams)
    assert all(stream.closed for stream in streams)
    assert list(tmp_path.iterdir()) == []


def test_rejected_upload_is_not_kept_either(
    recording_app: tuple[Flask, list[IO[bytes]]], tmp_path: Path
) -> None:
    app, streams = recording_app
    upload(app.test_client(), "big.xlsm", b"x" * 600_000)
    assert streams
    assert all(stream.closed for stream in streams)
    assert list(tmp_path.iterdir()) == []
