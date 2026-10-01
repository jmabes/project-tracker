import json
from datetime import date, datetime
from pathlib import Path

import pytest
from flask import Flask

from project_tracker.importer.parsers import (
    Cell,
    ImportFileError,
    ParsedSheet,
    SheetRow,
    parse_upload,
)
from project_tracker.importer.preview import (
    COLUMNS,
    DAMAGED_MESSAGE,
    Preview,
    SourceRow,
    build_preview,
    decode_rows,
    display_value,
    encode_rows,
    map_columns,
    normalize_header,
    preview_sheet,
    source_rows,
)
from project_tracker.services import count_projects, create_project

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_FILES = ["projects.csv", "projects-bom.csv", "projects.xlsx", "projects.ods"]


def row(number: int = 2, **overrides: Cell | None) -> SourceRow:
    values: dict[str, Cell | None] = {
        "name": "Build a shed",
        "category": "Home",
        "medium": "DIY",
        "priority": "Medium",
        "status": "Not started",
        "start_date": None,
        "estimated_completion_date": None,
    }
    values.update(overrides)
    return SourceRow(number=number, values=values)


def existing(name: str) -> None:
    create_project(
        {
            "name": name,
            "category": "Home",
            "medium": "DIY",
            "priority": "Low",
            "status": "Not started",
        }
    )


def preview_fixture(name: str) -> Preview:
    with (FIXTURES / name).open("rb") as f:
        return preview_sheet(parse_upload(name, f))


# --- headers ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Name", "name"),
        ("  STATUS  ", "status"),
        ("Start Date", "start_date"),
        ("start_date", "start_date"),
        ("Estimated  Completion\tDate", "estimated_completion_date"),
        ("estimated _ completion date", "estimated_completion_date"),
        ("", ""),
    ],
)
def test_normalize_header(text: str, expected: str) -> None:
    assert normalize_header(text) == expected


def test_map_columns_finds_fields_and_ignores_others() -> None:
    columns = map_columns(
        ["Notes", "name", "Category", "MEDIUM", "priority", "Status", "Start date", ""]
    )
    assert columns.positions == {
        "name": 1,
        "category": 2,
        "medium": 3,
        "priority": 4,
        "status": 5,
        "start_date": 6,
    }
    assert columns.ignored == ["Notes"]


def test_map_columns_date_columns_are_optional() -> None:
    columns = map_columns(["name", "category", "medium", "priority", "status"])
    assert set(columns.positions) == {
        "name",
        "category",
        "medium",
        "priority",
        "status",
    }


def test_map_columns_missing_required_is_a_file_error() -> None:
    with pytest.raises(ImportFileError, match="missing these required columns: "):
        map_columns(["Name", "Category", "Start date"])
    with pytest.raises(ImportFileError, match="medium, priority, status"):
        map_columns(["Name", "Category", "Start date"])


def test_map_columns_aliases_are_not_accepted() -> None:
    with pytest.raises(ImportFileError, match="name"):
        map_columns(["Project", "category", "medium", "priority", "status"])


def test_map_columns_repeated_field_is_a_file_error() -> None:
    with pytest.raises(ImportFileError, match="“name” appears more than once"):
        map_columns(["Name", "name ", "category", "medium", "priority", "status"])


def test_source_rows_fill_missing_columns_and_short_rows_with_none() -> None:
    sheet = ParsedSheet(
        header=["name", "category", "medium", "priority", "status", "start date"],
        rows=[SheetRow(number=3, cells=["A", "Tech"])],
    )
    [result] = source_rows(sheet, map_columns(sheet.header))
    assert result.number == 3
    assert result.values == {
        "name": "A",
        "category": "Tech",
        "medium": None,
        "priority": None,
        "status": None,
        "start_date": None,
        "estimated_completion_date": None,
    }


def test_preview_sheet_without_data_rows_is_a_file_error(app: Flask) -> None:
    sheet = ParsedSheet(
        header=["name", "category", "medium", "priority", "status"], rows=[]
    )
    with pytest.raises(ImportFileError, match="no project rows"):
        preview_sheet(sheet)


# --- the fixtures, in every format -----------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_FILES)
def test_fixture_preview_outcomes(app: Flask, name: str) -> None:
    existing("Garage shelves")
    preview = preview_fixture(name)

    assert preview.ignored_columns == ["Notes"]
    outcomes = {r.number: (r.status, r.messages) for r in preview.rows}
    assert outcomes == {
        2: ("valid", []),
        3: ("valid", []),
        4: ("valid", []),
        5: ("invalid", ["Category must be one of: Tech, Finance, Home."]),
        6: (
            "invalid",
            ["Estimated completion date must be on or after the start date."],
        ),
        8: ("skipped", ["Same name as row 2 in this file."]),
        9: ("skipped", ["A project named “Garage shelves” already exists."]),
        10: ("invalid", ["'15/03/2026' is not a valid date; use YYYY-MM-DD."]),
    }
    assert count_projects() == 1  # previewing writes nothing


@pytest.mark.parametrize("name", FIXTURE_FILES)
def test_fixture_valid_rows_are_cleaned(app: Flask, name: str) -> None:
    existing("Garage shelves")
    data = [r.data for r in preview_fixture(name).valid_rows]
    assert [d.name for d in data if d] == [
        "Home server rebuild",
        "Budget review",
        "1984",
    ]
    first, second, third = data
    assert first and first.start_date == date(2026, 1, 10)
    assert first.estimated_completion_date == date(2026, 6, 30)
    assert second and (
        second.category,
        second.medium,
        second.priority,
        second.status,
    ) == ("Finance", "Research", "Low", "Not started")
    assert second.start_date == date(2026, 2, 1)
    assert third and third.start_date is None


# --- rows from any source ------------------------------------------------------


def test_valid_row(app: Flask) -> None:
    [result] = build_preview([row()]).rows
    assert result.status == "valid"
    assert result.data and result.data.name == "Build a shed"


def test_choices_match_any_capitalisation_and_store_canonical(app: Flask) -> None:
    [result] = build_preview(
        [row(category=" tech ", medium="diy", priority="HIGH", status="in PROGRESS")]
    ).rows
    assert result.status == "valid"
    assert result.data
    assert (
        result.data.category,
        result.data.medium,
        result.data.priority,
        result.data.status,
    ) == ("Tech", "DIY", "High", "In progress")


def test_unknown_choice_is_still_invalid(app: Flask) -> None:
    [result] = build_preview([row(priority="urgent")]).rows
    assert result.status == "invalid"
    assert result.messages == ["Priority must be one of: High, Medium, Low."]


@pytest.mark.parametrize(("cell", "expected"), [(1984.0, "1984"), (7, "7")])
def test_whole_number_name_becomes_text(app: Flask, cell: Cell, expected: str) -> None:
    [result] = build_preview([row(name=cell)]).rows
    assert result.status == "valid"
    assert result.data and result.data.name == expected


@pytest.mark.parametrize("cell", [3.5, True, date(2026, 1, 1)])
def test_other_non_text_names_are_rejected(app: Flask, cell: Cell) -> None:
    [result] = build_preview([row(name=cell)]).rows
    assert result.status == "invalid"
    assert result.messages == ["Name must be text."]


def test_native_dates_and_iso_text(app: Flask) -> None:
    [result] = build_preview(
        [
            row(
                start_date=datetime(2026, 3, 1, 9, 30),
                estimated_completion_date="2026-04-01",
            )
        ]
    ).rows
    assert result.data
    assert result.data.start_date == date(2026, 3, 1)
    assert result.data.estimated_completion_date == date(2026, 4, 1)


def test_invalid_row_lists_every_error_in_column_order(app: Flask) -> None:
    [result] = build_preview([row(name="", category="x", start_date="tomorrow")]).rows
    assert result.status == "invalid"
    assert result.messages == [
        "Name is required.",
        "Category must be one of: Tech, Finance, Home.",
        "'tomorrow' is not a valid date; use YYYY-MM-DD.",
    ]


def test_existing_name_is_skipped_ignoring_case(app: Flask) -> None:
    existing("Café")
    [result] = build_preview([row(name="  CAFÉ ")]).rows
    assert result.status == "skipped"
    assert result.messages == ["A project named “CAFÉ” already exists."]


def test_existing_name_is_skipped_even_if_row_is_invalid(app: Flask) -> None:
    existing("Shed")
    [result] = build_preview([row(name="Shed", category="nope")]).rows
    assert result.status == "skipped"


def test_in_file_duplicates_after_the_first_are_skipped(app: Flask) -> None:
    results = build_preview(
        [
            row(2, name="Shed"),
            row(3, name="Other"),
            row(4, name="SHED"),
            row(5, name="shed"),
        ]
    ).rows
    assert [(r.number, r.status, r.messages) for r in results] == [
        (2, "valid", []),
        (3, "valid", []),
        (4, "skipped", ["Same name as row 2 in this file."]),
        (5, "skipped", ["Same name as row 2 in this file."]),
    ]


def test_in_file_duplicate_of_an_invalid_row_is_still_skipped(app: Flask) -> None:
    results = build_preview([row(2, name="Shed", status="?"), row(3, name="Shed")]).rows
    assert [r.status for r in results] == ["invalid", "skipped"]


def test_blank_names_are_not_duplicates_of_each_other(app: Flask) -> None:
    results = build_preview([row(2, name=""), row(3, name=None)]).rows
    assert [r.status for r in results] == ["invalid", "invalid"]


def test_preview_counts(app: Flask) -> None:
    preview = build_preview([row(2, name="A"), row(3, name="a"), row(4, status="x")])
    assert (
        preview.count("valid"),
        preview.count("skipped"),
        preview.count("invalid"),
    ) == (
        1,
        1,
        1,
    )
    assert not preview.all_valid
    assert build_preview([row()]).all_valid
    assert not build_preview([]).all_valid


# --- carrying rows from preview to confirm ---------------------------------------


def test_encode_rows_holds_only_valid_rows_with_iso_dates(app: Flask) -> None:
    preview = build_preview(
        [
            row(2, name=1984.0, category="tech", start_date=date(2026, 1, 2)),
            row(3, name="Bad", status="?"),
        ]
    )
    assert json.loads(encode_rows(preview)) == [
        {
            "row": 2,
            "values": {
                "name": "1984",
                "category": "Tech",
                "medium": "DIY",
                "priority": "Medium",
                "status": "Not started",
                "start_date": "2026-01-02",
            },
        }
    ]


def test_encode_then_decode_round_trip(app: Flask) -> None:
    preview = build_preview(
        [row(5, name="Café", estimated_completion_date=datetime(2026, 2, 3))]
    )
    rows = decode_rows(encode_rows(preview))
    assert [r.number for r in rows] == [5]
    assert set(rows[0].values) == set(COLUMNS)
    again = build_preview(rows)
    assert again.all_valid
    assert again.rows[0].data == preview.rows[0].data


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "{}",
        "[]",
        "[1]",
        '[{"row": 2}]',
        '[{"row": "2", "values": {}}]',
        '[{"row": true, "values": {}}]',
        '[{"row": 2, "values": []}]',
        '[{"row": 2, "values": {"notes": "x"}}]',
        '[{"row": 2, "values": {"name": 5}}]',
        '[{"row": 2, "values": {"name": null}}]',
        '[{"row": 2, "values": {}, "extra": 1}]',
    ],
)
def test_decode_rows_rejects_damaged_data(text: str) -> None:
    with pytest.raises(ImportFileError, match=DAMAGED_MESSAGE):
        decode_rows(text)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("x", "x"),
        (date(2026, 1, 2), "2026-01-02"),
        (datetime(2026, 1, 2, 3, 4), "2026-01-02T03:04:00"),
        (3.5, "3.5"),
    ],
)
def test_display_value(value: object, expected: str) -> None:
    assert display_value(value) == expected
