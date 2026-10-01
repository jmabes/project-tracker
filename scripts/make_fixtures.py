"""Write the spreadsheet import test fixtures in tests/fixtures/.

Every format gets the same rows, so the importer tests can expect the same outcome
whichever file they read. The .xlsx file is written with openpyxl and the .ods file
with odfpy (both dev-only dependencies), so their date cells are real native date
cells, as Excel and LibreOffice Calc would save them. The .csv files hold the same
rows as text, one with a UTF-8 byte order mark and one without.

Run from the repository root:

    .venv/bin/python scripts/make_fixtures.py
"""

import csv
from datetime import date, datetime
from pathlib import Path

from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableCell, TableRow
from odf.text import P
from openpyxl import Workbook

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

Cell = str | int | float | date | datetime | None

# Header spelling deliberately varies: matching ignores case, surrounding spaces
# and spaces versus underscores. "Notes" is not a project field and is ignored.
HEADER: list[Cell] = [
    "Name",
    " category ",
    "MEDIUM",
    "Priority",
    "Status",
    "Start Date",
    "estimated_completion_date",
    "Notes",
]

# Spreadsheet row 1 is the header, so the first data row is row 2.
ROWS: list[list[Cell]] = [
    # Row 2: valid; native date and date-time cells in the spreadsheets.
    [
        "Home server rebuild",
        "Tech",
        "Hardware",
        "High",
        "In progress",
        date(2026, 1, 10),
        datetime(2026, 6, 30, 0, 0),
        "ignored column",
    ],
    # Row 3: valid; choices in the wrong case and the start date as ISO text.
    ["Budget review", "finance", "research", "LOW", "not started", "2026-02-01"],
    # Row 4: valid; an all-number name (a numeric cell in the spreadsheets).
    [1984, "Home", "DIY", "Medium", "Done", None, None],
    # Row 5: invalid category.
    ["Fence repair", "Garden", "DIY", "High", "In progress", None, None],
    # Row 6: invalid; estimated completion before the start date.
    [
        "Backwards dates",
        "Tech",
        "Coding",
        "Low",
        "On hold",
        date(2026, 5, 1),
        date(2026, 4, 1),
    ],
    # Row 7: blank, so it is left out of the preview.
    [None, None, None, None, None, None, None],
    # Row 8: same name as row 2 in a different case: skipped as a duplicate.
    ["home server REBUILD", "Tech", "Coding", "Low", "Not started", None, None],
    # Row 9: the tests create a project with this name first: skipped as existing.
    ["Garage shelves", "Home", "DIY", "Low", "Not started", None, None],
    # Row 10: invalid; a date written as text that isn't YYYY-MM-DD.
    ["Not a date", "Tech", "Coding", "High", "In progress", "15/03/2026", None],
]


def csv_text(value: Cell) -> str:
    """Return a cell as CSV text: ISO dates, whole numbers without ".0"."""
    if value is None:
        return ""
    if isinstance(value, datetime | date):
        return value.isoformat()[:10]
    return str(value)


def write_csv(path: Path, *, bom: bool) -> None:
    """Write the rows as UTF-8 CSV, optionally with a byte order mark."""
    encoding = "utf-8-sig" if bom else "utf-8"
    with path.open("w", encoding=encoding, newline="") as f:
        writer = csv.writer(f)
        for row in [HEADER, *ROWS]:
            writer.writerow([csv_text(value) for value in row])


def write_xlsx(path: Path) -> None:
    """Write the rows to the first sheet of an .xlsx workbook."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Projects"
    for row in [HEADER, *ROWS]:
        sheet.append(row)
    # Fixed timestamps so regenerating doesn't change the metadata needlessly.
    workbook.properties.created = datetime(2026, 1, 1)
    workbook.properties.modified = datetime(2026, 1, 1)
    workbook.save(path)


def ods_cell(value: Cell) -> TableCell:
    """Return an ODS table cell holding a value with its native type."""
    if value is None:
        return TableCell()
    if isinstance(value, datetime | date):
        cell = TableCell(valuetype="date", datevalue=value.isoformat())
        cell.addElement(P(text=value.isoformat()[:10]))
        return cell
    if isinstance(value, int | float):
        cell = TableCell(valuetype="float", value=value)
    else:
        cell = TableCell(valuetype="string")
    cell.addElement(P(text=str(value)))
    return cell


def write_ods(path: Path) -> None:
    """Write the rows to the first sheet of an .ods spreadsheet."""
    document = OpenDocumentSpreadsheet()
    table = Table(name="Projects")
    for row in [HEADER, *ROWS]:
        table_row = TableRow()
        for value in row:
            table_row.addElement(ods_cell(value))
        table.addElement(table_row)
    document.spreadsheet.addElement(table)
    document.save(str(path))


def main() -> None:
    """Write every fixture file."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    write_csv(FIXTURES / "projects.csv", bom=False)
    write_csv(FIXTURES / "projects-bom.csv", bom=True)
    write_xlsx(FIXTURES / "projects.xlsx")
    write_ods(FIXTURES / "projects.ods")
    print(f"Wrote fixtures to {FIXTURES}")


if __name__ == "__main__":
    main()
