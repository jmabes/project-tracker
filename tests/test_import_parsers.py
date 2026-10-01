import io
from datetime import date, datetime
from pathlib import Path

import pytest

from project_tracker.importer.parsers import (
    ALLOWED_EXTENSIONS,
    ImportFileError,
    ParsedSheet,
    file_extension,
    parse_upload,
)

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_FILES = ["projects.csv", "projects-bom.csv", "projects.xlsx", "projects.ods"]

HEADER = [
    "Name",
    "category",
    "MEDIUM",
    "Priority",
    "Status",
    "Start Date",
    "estimated_completion_date",
    "Notes",
]


def parse_fixture(name: str) -> ParsedSheet:
    with (FIXTURES / name).open("rb") as f:
        return parse_upload(name, f)


def test_allowed_extensions() -> None:
    assert ALLOWED_EXTENSIONS == (".csv", ".xlsx", ".ods")


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("projects.ODS", ".ods"),
        ("my.projects.xlsx", ".xlsx"),
        ("noext", ""),
        ("archive.tar.csv", ".csv"),
    ],
)
def test_file_extension(filename: str, expected: str) -> None:
    assert file_extension(filename) == expected


@pytest.mark.parametrize("name", FIXTURE_FILES)
def test_fixture_header_is_trimmed(name: str) -> None:
    assert parse_fixture(name).header == HEADER


@pytest.mark.parametrize("name", FIXTURE_FILES)
def test_fixture_rows_skip_blank_row_and_keep_row_numbers(name: str) -> None:
    numbers = [row.number for row in parse_fixture(name).rows]
    assert numbers == [2, 3, 4, 5, 6, 8, 9, 10]


@pytest.mark.parametrize("name", ["projects.xlsx", "projects.ods"])
def test_spreadsheet_native_dates(name: str) -> None:
    first = parse_fixture(name).rows[0].cells
    assert first[5] == date(2026, 1, 10)
    # The completion date was written as a date-time at midnight.
    assert first[6] in (date(2026, 6, 30), datetime(2026, 6, 30))


@pytest.mark.parametrize("name", ["projects.xlsx", "projects.ods"])
def test_spreadsheet_number_cell_stays_a_number(name: str) -> None:
    assert parse_fixture(name).rows[2].cells[0] == 1984.0


@pytest.mark.parametrize("name", ["projects.xlsx", "projects.ods"])
def test_spreadsheet_date_text_stays_text(name: str) -> None:
    assert parse_fixture(name).rows[1].cells[5] == "2026-02-01"


@pytest.mark.parametrize("name", ["projects.csv", "projects-bom.csv"])
def test_csv_cells_are_text(name: str) -> None:
    rows = parse_fixture(name).rows
    assert rows[0].cells[:7] == [
        "Home server rebuild",
        "Tech",
        "Hardware",
        "High",
        "In progress",
        "2026-01-10",
        "2026-06-30",
    ]
    assert rows[2].cells[0] == "1984"


def test_csv_bom_is_not_part_of_first_header() -> None:
    raw = "﻿Name,Status\r\nA,Done\r\n".encode()
    sheet = parse_upload("x.csv", io.BytesIO(raw))
    assert sheet.header == ["Name", "Status"]


def test_csv_quoted_field_with_line_break() -> None:
    raw = b'Name,Status\r\n"Two\r\nlines",Done\r\n'
    sheet = parse_upload("x.csv", io.BytesIO(raw))
    assert sheet.rows[0].cells == ["Two\r\nlines", "Done"]


def test_csv_leading_blank_rows_are_skipped_and_numbers_kept() -> None:
    raw = b",\r\n\r\nName\r\nA\r\n"
    sheet = parse_upload("x.csv", io.BytesIO(raw))
    assert sheet.header == ["Name"]
    assert [(row.number, row.cells) for row in sheet.rows] == [(4, ["A"])]


def test_csv_not_utf8_is_a_file_error() -> None:
    with pytest.raises(ImportFileError, match="UTF-8"):
        parse_upload("x.csv", io.BytesIO("Name\r\nCafé\r\n".encode("cp1252")))


def test_csv_parse_error_is_a_file_error() -> None:
    with pytest.raises(ImportFileError, match="couldn't be read"):
        parse_upload("x.csv", io.BytesIO(b'Name\r\n"x' + b"y" * 200_000 + b'"\r\n'))


@pytest.mark.parametrize("name", ["empty.csv", "empty.xlsx"])
def test_empty_file_is_a_file_error(name: str) -> None:
    with pytest.raises(ImportFileError):
        parse_upload(name, io.BytesIO(b""))


def test_blank_only_csv_is_empty() -> None:
    with pytest.raises(ImportFileError, match="empty"):
        parse_upload("x.csv", io.BytesIO(b" , \r\n,\r\n"))


@pytest.mark.parametrize("name", ["bad.xlsx", "bad.ods"])
def test_corrupt_spreadsheet_is_a_file_error(name: str) -> None:
    with pytest.raises(ImportFileError, match="couldn't be read as a spreadsheet"):
        parse_upload(name, io.BytesIO(b"PK\x03\x04 not really a zip"))


@pytest.mark.parametrize(
    "name", ["projects.xlsm", "projects.xls", "projects.txt", "projects", "x.csv.exe"]
)
def test_other_extensions_are_rejected(name: str) -> None:
    with pytest.raises(ImportFileError, match="isn't one of those types"):
        parse_upload(name, io.BytesIO(b"Name\r\nA\r\n"))


def test_xlsm_rejected_even_with_real_workbook_contents() -> None:
    data = (FIXTURES / "projects.xlsx").read_bytes()
    with pytest.raises(ImportFileError):
        parse_upload("projects.xlsm", io.BytesIO(data))


def test_extension_check_ignores_case() -> None:
    with (FIXTURES / "projects.ods").open("rb") as f:
        assert parse_upload("PROJECTS.ODS", f).header == HEADER


def test_header_number_is_first_non_blank_row() -> None:
    sheet = parse_upload("x.csv", io.BytesIO(b",\r\n\r\nTitle\r\nName\r\nA\r\n"))
    assert (sheet.header_number, sheet.header) == (3, ["Title"])
    assert [row.number for row in sheet.rows] == [4, 5]


def test_titled_ods_keeps_title_as_first_row() -> None:
    sheet = parse_fixture("projects-titled.ods")
    assert (sheet.header_number, sheet.header[0]) == (1, "My projects")
    assert [row.number for row in sheet.rows] == [2, 4, 5, 6]
