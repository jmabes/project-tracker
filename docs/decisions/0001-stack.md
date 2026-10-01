# 0001 — Application stack

- Status: Accepted
- Date: 2026-10-01

## Context

project-tracker replaces a personal spreadsheet. It is single-user, self-hosted on an
Ubuntu 24.04 server with Python 3.12.3, and reached over the LAN and Tailscale.
`CLAUDE.md` already names the stack. This ADR records checking it against the current
official documentation and PyPI releases, and the versions picked for Milestone 1.

## Decision

Use the stack from `CLAUDE.md` with these pinned versions:

| Package | Version | Python 3.12 support (from docs / PyPI metadata) |
| --- | --- | --- |
| Flask | 3.1.3 | Docs: "Flask supports Python 3.9 and newer." |
| Flask-SQLAlchemy | 3.1.1 | `requires-python >=3.8`; needs SQLAlchemy >=2.0.16 |
| SQLAlchemy | 2.0.54 | 2.0 line; see note below |
| Flask-Migrate (Alembic 1.20.0) | 4.1.0 | `requires-python >=3.6`; Alembic `>=3.10` |
| Flask-WTF (WTForms 3.2.2) | 1.3.0 | 1.3.0 changelog: dropped 3.9, added 3.14 |
| python-calamine | 0.8.2 | `requires-python >=3.10`, 3.12 classifier |
| Gunicorn | 26.2.0 | Docs: "Gunicorn requires **Python 3.12 or newer**." |
| pytest (dev) | 9.1.1 | pytest 9.0+ needs Python 3.10+ |
| ruff (dev) | 0.16.10 | Works with any Python; infers the target from `requires-python` |

CI uses `actions/checkout@v7` and `actions/setup-python@v7` (current majors per their
READMEs) on `ubuntu-24.04`, matching the server OS.

### SQLAlchemy 2.0 rather than 2.1

SQLAlchemy 2.1.0 came out on 2026-09-24. Flask-SQLAlchemy's latest release (3.1.1,
2023-09-11) predates it, and its changelog does not mention 2.1. SQLAlchemy 2.0.x is
still being released (2.0.54 on 2026-09-15) and is what Flask-SQLAlchemy 3.1 was built
against. We pin 2.0.54 and use the 2.x API (`DeclarativeBase`, `Mapped`,
`mapped_column`, `select()`), so moving to 2.1 later should mostly mean bumping a pin.

### Gunicorn now needs Python 3.12

Gunicorn 26 needs Python 3.12 or newer. The server has 3.12.3 and `requires-python`
is `>=3.12,<3.13`, so this fits. It does mean the project cannot drop to an older
interpreter.

### python-calamine and `.ods` dates

- Its type stubs declare that `CalamineSheet.to_python()` returns cells as
  `int | float | str | bool | datetime.time | datetime.date | datetime.datetime |
  datetime.timedelta`.
- Its test suite (`tests/test_base.py::test_ods_read`, fixture `base.ods`) expects an
  ODS date cell as `date(2010, 10, 10)`, a date-time cell as
  `datetime(2010, 10, 10, 10, 10, 10)`, and time cells as `datetime.time`. ODS
  durations come back as ISO strings such as `"PT255H10M10S"`, not `timedelta`.
- Hand check with 0.8.2 on a minimal `.ods` file: a date-only cell
  (`office:date-value="2026-03-15"`) returned `datetime.date(2026, 3, 15)`, a date-time
  cell returned `datetime.datetime(2026, 3, 15, 0, 0)`, and the text `"2026-03-15"`
  stayed a `str`.
- The calamine ODS parser rejected a hand-written `content.xml` that had whitespace
  text between `<table:table-cell>` elements. Real Calc files don't contain that, but
  the `.ods` test fixtures should be written by a proper ODS library, not as raw XML.

So the validation service accepts `date`, `datetime` (keeping only the date part) and
ISO `YYYY-MM-DD` strings for date fields.

## Consequences

- No problems found with the chosen stack. Every package supports Python 3.12.
- The SQLAlchemy pin needs another look when Flask-SQLAlchemy releases with 2.1
  support.
- Only direct dependencies are pinned. Transitive packages (Werkzeug, Jinja2, Alembic
  and so on) can change between installs. A fully locked file is listed as a follow-up.

## Links

- Flask installation: https://flask.palletsprojects.com/en/stable/installation/
- Flask-SQLAlchemy changelog: https://flask-sqlalchemy.readthedocs.io/en/stable/changes/
- SQLAlchemy 2.1 migration notes: https://docs.sqlalchemy.org/en/21/changelog/migration_21.html
- Flask-Migrate: https://flask-migrate.readthedocs.io/en/latest/
- Flask-WTF changelog: https://github.com/pallets-eco/flask-wtf/blob/main/docs/changes.rst
- python-calamine: https://github.com/dimastbk/python-calamine
  (stubs `python/python_calamine/_python_calamine.pyi`, tests `tests/test_base.py`)
- Gunicorn install: https://gunicorn.org/install/
- pytest Python support: https://docs.pytest.org/en/stable/backwards-compatibility.html
- ruff configuration: https://docs.astral.sh/ruff/configuration/
- actions/checkout: https://github.com/actions/checkout
- actions/setup-python: https://github.com/actions/setup-python
