"""Match spreadsheet columns to project fields and check every row before import.

Nothing here knows which file format the rows came from, and nothing here writes
to the database. Rows are checked with ``services.validate_project``, the same
validation the web forms use, after two import-only conversions: choice values
match in any capitalisation (``tech`` becomes ``Tech``), and a whole-number name
cell becomes text (``1984.0`` becomes ``"1984"``).

The preview page carries the valid rows to the confirm request in a hidden form
field (see ``encode_rows``), so the server keeps no state between the two requests.
docs/decisions/0002-import-preview-state.md explains why.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from sqlalchemy import select

from project_tracker.extensions import db
from project_tracker.importer.parsers import Cell, ImportFileError, ParsedSheet
from project_tracker.models import Project
from project_tracker.services import (
    CHOICE_FIELDS,
    NAME_TAKEN_MESSAGE,
    ProjectData,
    ProjectValidationError,
    validate_project,
)

REQUIRED_COLUMNS: tuple[str, ...] = ("name", "category", "medium", "priority", "status")
# A missing date column means every row's date is blank.
OPTIONAL_COLUMNS: tuple[str, ...] = ("start_date", "estimated_completion_date")
COLUMNS: tuple[str, ...] = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

DAMAGED_MESSAGE = "The import data was missing or damaged. Upload the file again."

RowStatus = Literal["valid", "invalid", "skipped"]


def normalize_header(text: str) -> str:
    """Return a header cell as a field name to match against.

    Matching ignores case and surrounding whitespace, and treats any run of spaces
    and underscores as one underscore, so ``" Start  Date "`` gives
    ``start_date``.
    """
    return "_".join(part for part in re.split(r"[\s_]+", text.casefold()) if part)


@dataclass(frozen=True)
class ColumnMap:
    """Where each project field is in the sheet, and which columns are ignored."""

    positions: dict[str, int]
    ignored: list[str]


def map_columns(header: Sequence[str]) -> ColumnMap:
    """Find each project field's column in the header row.

    Raises:
        ImportFileError: If a required column is missing or a field appears in
            more than one column.
    """
    positions: dict[str, int] = {}
    ignored: list[str] = []
    for index, text in enumerate(header):
        key = normalize_header(text)
        if key in COLUMNS:
            if key in positions:
                raise ImportFileError(
                    f"The column “{key}” appears more than once in the header row."
                )
            positions[key] = index
        elif key:
            ignored.append(text)
    missing = [column for column in REQUIRED_COLUMNS if column not in positions]
    if missing:
        raise ImportFileError(
            "The header row is missing these required columns: "
            f"{', '.join(missing)}. The first non-blank row must name the columns."
        )
    return ColumnMap(positions=positions, ignored=ignored)


@dataclass(frozen=True)
class SourceRow:
    """One row's raw values keyed by field name, with its spreadsheet row number."""

    number: int
    values: dict[str, Cell | None]


def source_rows(sheet: ParsedSheet, columns: ColumnMap) -> list[SourceRow]:
    """Pick each project field's value out of every data row.

    Fields with no column, and cells past the end of a short row, are ``None``.
    """
    rows = []
    for row in sheet.rows:
        values: dict[str, Cell | None] = dict.fromkeys(COLUMNS)
        for name, index in columns.positions.items():
            if index < len(row.cells):
                values[name] = row.cells[index]
        rows.append(SourceRow(number=row.number, values=values))
    return rows


@dataclass(frozen=True)
class RowResult:
    """The outcome for one row: valid (with cleaned data), invalid, or skipped."""

    number: int
    values: dict[str, Cell | None]
    status: RowStatus
    messages: list[str] = field(default_factory=list)
    data: ProjectData | None = None


@dataclass(frozen=True)
class Preview:
    """Every row's outcome, plus the header columns that were ignored."""

    rows: list[RowResult]
    ignored_columns: list[str] = field(default_factory=list)

    @property
    def valid_rows(self) -> list[RowResult]:
        """Return the rows that would be imported."""
        return [row for row in self.rows if row.status == "valid"]

    def count(self, status: RowStatus) -> int:
        """Return how many rows have the given outcome."""
        return sum(1 for row in self.rows if row.status == status)

    @property
    def all_valid(self) -> bool:
        """Return True if there is at least one row and every row is valid."""
        return bool(self.rows) and len(self.valid_rows) == len(self.rows)


def preview_sheet(sheet: ParsedSheet) -> Preview:
    """Map a parsed sheet's columns and check every data row.

    Raises:
        ImportFileError: If the header is unusable or there are no data rows.
    """
    columns = map_columns(sheet.header)
    rows = source_rows(sheet, columns)
    if not rows:
        raise ImportFileError("This file has a header row but no project rows.")
    return build_preview(rows, ignored_columns=columns.ignored)


def build_preview(
    rows: Sequence[SourceRow], *, ignored_columns: Sequence[str] = ()
) -> Preview:
    """Check every row without writing anything.

    A row is skipped if its name matches an existing project or an earlier row
    in the same rows, ignoring case. Otherwise it is valid or invalid according
    to ``validate_project``.
    """
    existing = {name.casefold() for name in db.session.scalars(select(Project.name))}
    first_row_for_name: dict[str, int] = {}
    results = []
    for row in rows:
        values = _normalize(row.values)
        key = _name_key(values["name"])
        if key is not None and key in existing:
            results.append(_skipped_existing(row.number, values))
            continue
        if key is not None and key in first_row_for_name:
            results.append(
                RowResult(
                    number=row.number,
                    values=values,
                    status="skipped",
                    messages=[
                        f"Same name as row {first_row_for_name[key]} in this file."
                    ],
                )
            )
            continue
        if key is not None:
            first_row_for_name[key] = row.number
        try:
            data = validate_project(values)
        except ProjectValidationError as exc:
            if NAME_TAKEN_MESSAGE in exc.errors.get("name", []):
                # Added since ``existing`` was read.
                results.append(_skipped_existing(row.number, values))
            else:
                results.append(
                    RowResult(
                        number=row.number,
                        values=values,
                        status="invalid",
                        messages=_messages(exc.errors),
                    )
                )
            continue
        results.append(
            RowResult(number=row.number, values=values, status="valid", data=data)
        )
    return Preview(rows=results, ignored_columns=list(ignored_columns))


def encode_rows(preview: Preview) -> str:
    """Return the valid rows' cleaned values as JSON for the confirm form.

    Dates become ISO ``YYYY-MM-DD`` text, which ``validate_project`` accepts, so
    the confirm request can check the rows again with ``decode_rows``.
    """
    payload = []
    for row in preview.valid_rows:
        assert row.data is not None  # valid rows always carry data
        values = {
            name: value.isoformat() if isinstance(value, date) else value
            for name in COLUMNS
            if (value := getattr(row.data, name)) is not None
        }
        payload.append({"row": row.number, "values": values})
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_rows(text: str) -> list[SourceRow]:
    """Turn the confirm form's JSON back into rows to check again.

    Only the shape is checked here; the values go through ``build_preview``.

    Raises:
        ImportFileError: If the data is missing, not JSON, or the wrong shape.
    """
    try:
        payload = json.loads(text)
    except ValueError:
        raise ImportFileError(DAMAGED_MESSAGE) from None
    if not isinstance(payload, list) or not payload:
        raise ImportFileError(DAMAGED_MESSAGE)
    rows = []
    for item in payload:
        if not isinstance(item, dict) or set(item) != {"row", "values"}:
            raise ImportFileError(DAMAGED_MESSAGE)
        number, values = item["row"], item["values"]
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or not isinstance(values, dict)
            or not set(values) <= set(COLUMNS)
            or not all(isinstance(value, str) for value in values.values())
        ):
            raise ImportFileError(DAMAGED_MESSAGE)
        row_values: dict[str, Cell | None] = dict.fromkeys(COLUMNS)
        row_values.update(values)
        rows.append(SourceRow(number=number, values=row_values))
    return rows


def display_value(value: object) -> str:
    """Return a cell value as text for the preview table."""
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _normalize(values: dict[str, Cell | None]) -> dict[str, Cell | None]:
    """Apply the import-only conversions before validation."""
    normalized = dict(values)
    name = normalized.get("name")
    if isinstance(name, int | float) and not isinstance(name, bool):
        # Whole numbers only: a name such as 3.5 still fails as "must be text".
        if isinstance(name, int) or name.is_integer():
            normalized["name"] = str(int(name))
    for column, allowed in CHOICE_FIELDS.items():
        value = normalized.get(column)
        if isinstance(value, str):
            folded = value.strip().casefold()
            normalized[column] = next(
                (choice for choice in allowed if choice.casefold() == folded), value
            )
    return normalized


def _name_key(value: Cell | None) -> str | None:
    """Return the name to compare for duplicates, or None if it isn't usable."""
    if isinstance(value, str) and value.strip():
        return value.strip().casefold()
    return None


def _skipped_existing(number: int, values: dict[str, Cell | None]) -> RowResult:
    """Return the result for a row whose name is already in the tracker."""
    name = values["name"]
    assert isinstance(name, str)  # only text names can match
    return RowResult(
        number=number,
        values=values,
        status="skipped",
        messages=[f"A project named “{name.strip()}” already exists."],
    )


def _messages(errors: dict[str, list[str]]) -> list[str]:
    """Flatten per-field errors into a list in column order."""
    return [message for name in COLUMNS for message in errors.get(name, [])]
