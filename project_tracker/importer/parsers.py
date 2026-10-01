"""Read an uploaded spreadsheet into a header row and data rows.

Each supported extension maps to one parser function with the same signature, so
callers only ever see a ``ParsedSheet``. Files are read from the upload stream into
memory and never written to disk.
"""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import PurePath
from typing import IO

from python_calamine import CalamineError, CalamineWorkbook

# What a cell can hold after parsing. CSV cells are always str; calamine also
# returns numbers, booleans and native dates and times. Blank cells are "".
Cell = str | int | float | bool | date | datetime | time | timedelta


class ImportFileError(Exception):
    """Raised when a whole file can't be imported; the message is user-facing."""


@dataclass(frozen=True)
class SheetRow:
    """One data row and its 1-based row number in the spreadsheet."""

    number: int
    cells: list[Cell]


@dataclass(frozen=True)
class ParsedSheet:
    """The header row and the data rows below it.

    Blank rows are left out. ``header`` holds each header cell as trimmed text.
    """

    header: list[str]
    rows: list[SheetRow]


def parse_upload(filename: str, stream: IO[bytes]) -> ParsedSheet:
    """Parse an uploaded file, choosing the parser from its extension.

    Args:
        filename: The uploaded file's name, used only for its extension.
        stream: The file's contents.

    Raises:
        ImportFileError: If the extension isn't allowed, the file can't be read,
            or it has no header row.
    """
    parser = PARSERS.get(file_extension(filename))
    if parser is None:
        raise ImportFileError(
            f"Choose a {', '.join(ALLOWED_EXTENSIONS)} file. "
            f"“{filename}” isn't one of those types."
        )
    return _to_sheet(parser(stream))


def file_extension(filename: str) -> str:
    """Return a file name's last extension in lower case, e.g. ``.ods``."""
    return PurePath(filename).suffix.lower()


def parse_csv(stream: IO[bytes]) -> list[list[Cell]]:
    """Read a UTF-8 CSV file, with or without a byte order mark."""
    try:
        text = stream.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportFileError(
            "This CSV file isn't UTF-8 text. Save it as “CSV UTF-8” and try again."
        ) from None
    try:
        # newline="" so quoted fields may contain line breaks (see the csv docs).
        return list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as exc:
        raise ImportFileError(f"This CSV file couldn't be read: {exc}.") from None


def parse_workbook(stream: IO[bytes]) -> list[list[Cell]]:
    """Read the first sheet of an .xlsx or .ods file with python-calamine."""
    data = io.BytesIO(stream.read())
    try:
        with CalamineWorkbook.from_filelike(data) as workbook:
            if not workbook.sheet_names:
                return []
            # skip_empty_area=False keeps leading blank rows, so list positions
            # match spreadsheet row numbers.
            return workbook.get_sheet_by_index(0).to_python(skip_empty_area=False)
    except CalamineError:
        raise ImportFileError(
            "This file couldn't be read as a spreadsheet. Check that it opens in "
            "Excel or LibreOffice Calc and was saved as .xlsx or .ods."
        ) from None


PARSERS: dict[str, Callable[[IO[bytes]], list[list[Cell]]]] = {
    ".csv": parse_csv,
    ".xlsx": parse_workbook,
    ".ods": parse_workbook,
}
ALLOWED_EXTENSIONS: tuple[str, ...] = tuple(PARSERS)


def is_blank(value: Cell) -> bool:
    """Return True for an empty or whitespace-only cell."""
    return isinstance(value, str) and not value.strip()


def _to_sheet(grid: list[list[Cell]]) -> ParsedSheet:
    """Split a grid of cells into the header (first non-blank row) and data rows."""
    numbered = [
        SheetRow(number=index, cells=list(cells))
        for index, cells in enumerate(grid, start=1)
        if not all(is_blank(value) for value in cells)
    ]
    if not numbered:
        raise ImportFileError("This file is empty.")
    header_row, *rows = numbered
    header = [
        value.strip() if isinstance(value, str) else str(value)
        for value in header_row.cells
    ]
    return ParsedSheet(header=header, rows=rows)
