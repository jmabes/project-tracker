# Spreadsheet import fixtures

`projects.csv`, `projects-bom.csv`, `projects.xlsx` and `projects.ods` hold the same
header and rows, so the importer tests expect the same result from every format. The
spreadsheets use real native date cells; the CSV files hold the dates as
`YYYY-MM-DD` text (`projects-bom.csv` starts with a UTF-8 byte order mark, as Excel
writes it).

Don't edit these files by hand. Change the rows in `scripts/make_fixtures.py` and
regenerate all of them from the repository root:

```bash
.venv/bin/python scripts/make_fixtures.py
```

It should print `Wrote fixtures to .../tests/fixtures`. The script needs the dev-only
packages `openpyxl` and `odfpy` from `requirements-dev.txt`. Then run
`.venv/bin/python -m pytest` and update the tests if you changed the rows.
