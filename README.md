# project-tracker

A small self-hosted web app that replaces a spreadsheet for tracking personal projects.
Each project has a name, category, medium, priority, status, and optional start and
target dates. It is built for one user on a home server, reached over the
LAN and Tailscale.

> **Status:** Milestone 5 (deployment). You can create, view, edit, and delete
> projects in the browser, filter and sort the main list, and import projects from a
> .csv, .xlsx, or .ods spreadsheet. [docs/deployment.md](docs/deployment.md) explains
> how to run it on the home server. See [docs/ROADMAP.md](docs/ROADMAP.md).

Stack: Flask, SQLite (Flask-SQLAlchemy + Flask-Migrate), Flask-WTF, python-calamine,
Gunicorn, pytest and ruff. The reasoning and versions are in
[docs/decisions/0001-stack.md](docs/decisions/0001-stack.md).

## Local setup

You need Python 3.12 (`python3 --version` should print `Python 3.12.x`).

```bash
# 1. Get the code and enter the folder
git clone https://github.com/jmabes/project-tracker.git
cd project-tracker

# 2. Create a virtual environment in .venv (keeps packages out of system Python)
python3 -m venv .venv

# 3. Install the app and development tools into the venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

If step 2 fails with "ensurepip is not available" on Ubuntu, install the venv module
with `sudo apt install python3.12-venv`, then delete the partial folder
(`rm -rf .venv`) and run step 2 again.

Every command below calls the venv's Python directly (`.venv/bin/python`), so you
don't need to activate the venv first.

## Quality gate

Run all three before every commit. CI runs the same checks on every pull request.

```bash
.venv/bin/python -m ruff check .            # lint
.venv/bin/python -m ruff format --check .   # formatting (drop --check to fix it)
.venv/bin/python -m pytest                  # tests
```

Each command should finish with no errors. pytest ends with a line like
`533 passed in 5.63s`.

## Running the development server

```bash
# Create or upgrade the database schema (development database: instance/project_tracker.db)
.venv/bin/flask --app project_tracker db upgrade

# Start the dev server with auto-reload and the debugger
.venv/bin/flask --app project_tracker run --debug
```

Check it's running by opening <http://127.0.0.1:5000/healthz> or running
`curl http://127.0.0.1:5000/healthz`. The response should contain `"status": "ok"`.
`/healthz` also reads the database, so it answers 503 with
`"database": "unavailable"` if the database can't be opened or `flask db upgrade`
hasn't been run. Stop the server with Ctrl+C.

## Using the app

Open <http://127.0.0.1:5000/>. The pages are:

| Page | What it does |
| --- | --- |
| `/` | The project list: a table you can filter by category, medium, priority, and status (under **Filters**), and sort by clicking any column heading (click again to reverse). On a phone each project is a card and you sort with the **Sort** button instead. Done and Abandoned projects are hidden until you click **Show finished projects**. |
| `/projects/new` | Form to add a project. Also linked as **New project** in the header (the tab bar at the bottom on a phone). |
| `/projects/<id>` | One project's details, with **Edit** and **Delete** links. |
| `/projects/<id>/edit` | Change any field. To finish a project, set its status to Done or Abandoned; it stays in the tracker. |
| `/projects/<id>/delete` | Asks for confirmation; only the **Delete project** button removes it, permanently. |
| `/import/` | Import projects from a spreadsheet: upload, check the preview, then confirm. Also linked as **Import** in the header. See [Importing a spreadsheet](#importing-a-spreadsheet). |

If a field is invalid the form is shown again with your values kept and the error
under the field. Names must be unique ignoring case, so "Café" and "CAFÉ" count as
the same name.

### Bookmarkable list views

The list's filters and sort order live in the address bar, so you can bookmark a
view (for example "High-priority Tech projects") and the back button works. The
list understands these query-string parameters; anything else, or an invalid value,
is ignored and the default is used:

| Parameter | Values | Default |
| --- | --- | --- |
| `category`, `medium`, `priority`, `status` | One allowed value each (as shown in the filter menus). Filters combine: a project must match all of them. | Any |
| `show_finished` | `1` to include Done and Abandoned projects. Choosing Done or Abandoned as the `status` filter shows them too. | Hidden |
| `sort` | `name`, `category`, `medium`, `priority`, `status`, `start_date`, `target_date` | `priority` |
| `dir` | `asc` or `desc` | `desc` (High first) for priority, `asc` for the rest |

Priority sorts by importance (High, Medium, Low) and status in workflow order
(Not started, In progress, On hold, Done, Abandoned), not alphabetically. Names sort
ignoring case. Projects without a date always sort after those with one.
Example: `/?category=Tech&priority=High&sort=start_date&dir=asc`.

### On an iPhone

The app is styled for Safari on an iPhone first and works as a Home Screen web app.
In Safari, open the tracker, tap **Share**, then **Add to Home Screen**. The icon
is a white checkmark on blue, labelled **Projects**. Opened from the Home Screen it
runs full screen without Safari's address bar, the layout stays clear of the notch,
Dynamic Island and home indicator, and on narrow screens the navigation is a tab
bar at the bottom. It follows the phone's Light/Dark setting.

This works over plain HTTP on the LAN or tailnet: from iOS 26 every site added to
the Home Screen opens as a web app, and older iOS versions use the manifest's
`"display": "standalone"`. What HTTP can't give you is anything that needs a
secure context, such as a service worker, so there is no offline mode and no push
notifications.

The home-screen icon, `project_tracker/static/apple-touch-icon.png`, is generated.
To change it, edit the colours or checkmark in `scripts/make_icon.py`, then run:

```bash
.venv/bin/python scripts/make_icon.py   # rewrites project_tracker/static/apple-touch-icon.png
.venv/bin/python -m pytest              # a test checks the PNG matches the script
```

iOS copies the icon when you add the app, so remove and re-add the Home Screen
icon to see a new one.

The development server is for local use only. Production runs under Gunicorn and
systemd; see [docs/deployment.md](docs/deployment.md).

## Importing a spreadsheet

Open **Import** in the header, choose a file, and click **Preview import**. The
preview lists every row with its outcome:

- **Ready**: the row is valid and will be imported.
- **Error**: the row has a problem (the messages say what). It is not imported.
- **Skipped**: the name matches a project already in the tracker, or an earlier row
  in the same file, ignoring case. Existing projects are never changed. Within the
  file, the first row with a name is checked as usual and every later row with the
  same name is skipped.

Nothing is saved until you click **Import N projects**. All the Ready rows are then
saved together: either all of them are saved or, if anything goes wrong, none are.
If something changed after the preview (for example, you added a project with the
same name in another tab), nothing is saved and you get a fresh preview to confirm.
The uploaded file is read in memory and never kept.

### File rules

- **Formats:** `.csv`, `.xlsx` (Excel), and `.ods` (LibreOffice Calc). Anything
  else is refused, including `.xlsm` and `.xls`. Uploads can be up to 2 MB; a bigger
  file gets a "file is too large" page.
- **Which sheet:** the first sheet of an .xlsx or .ods file. Blank rows are ignored.
- **CSV encoding:** UTF-8, with or without a byte order mark. When saving a CSV
  from Excel or LibreOffice Calc, choose UTF-8 as the character set.

### Accepted headers

The header row names the columns, in any order. It doesn't have to be row 1: the
importer uses the first row that names all five required columns, and ignores
anything above it, such as a title, notes, or blank rows. The preview says which row
it used.

| Header | Required | Values |
| --- | --- | --- |
| `name` | Yes | Text, at most 200 characters, unique ignoring case. A whole-number cell such as `1984` is read as the text "1984"; a decimal such as `3.5` is an error. |
| `category` | Yes | Tech, Finance, Home |
| `medium` | Yes | Coding, Hardware, Research, DIY |
| `priority` | Yes | High, Medium, Low |
| `status` | Yes | Not started, In progress, On hold, Done, Abandoned |
| `start_date` | No | A date (see below), or blank |
| `target_date` | No | A date on or after the start date, or blank |

- Header matching ignores case and spaces around the name, and a space can stand
  for an underscore, so `Start Date`, `start date`, and `START_DATE` all work. No
  other spellings (such as "Project" for `name`) are accepted.
- If no row names all five required columns, the import stops and the message
  points at the closest row and the columns it is missing. A missing date column
  just means those dates are blank.
- Any other column (for example `Notes`) is ignored; the preview lists ignored
  columns.
- Category, medium, priority, and status values match in any case and are saved in
  the spelling above, so `tech` is saved as `Tech`.

### Dates

- Date cells from Excel or LibreOffice Calc. A date with a time keeps only the
  date.
- Text written as `YYYY-MM-DD`, for example `2026-03-15`. Other text such as
  `15/03/2026` is an error, so the day and month can't be mixed up. In a CSV file,
  dates are always text, so use `YYYY-MM-DD`.

### Test fixtures

The importer's test files live in `tests/fixtures/`. They are generated, not
hand-edited; see [tests/fixtures/README.md](tests/fixtures/README.md). To regenerate
them after changing the rows in `scripts/make_fixtures.py`:

```bash
.venv/bin/python scripts/make_fixtures.py   # rewrites tests/fixtures/projects.*
.venv/bin/python -m pytest                  # check the tests still pass
```

## Configuration

Settings come from environment variables; [.env.example](.env.example) lists them all.

| Variable | Purpose | Default |
| --- | --- | --- |
| `PROJECT_TRACKER_CONFIG` | `development`, `production`, or `testing` | `development` |
| `SECRET_KEY` | Signs sessions and CSRF tokens. **Required in production.** | insecure dev key |
| `DATABASE_URL` | SQLAlchemy URL for the SQLite file. **Required in production** (keep the file outside the repo). | `instance/project_tracker.db` |
| `PROJECT_TRACKER_HOST` | Address Gunicorn listens on (read by `gunicorn.conf.py`). The server uses `0.0.0.0`. | `127.0.0.1` |
| `PROJECT_TRACKER_PORT` | Port Gunicorn listens on. | `8002` |

The app does not read a `.env` file by itself. To set a variable for one command, put
it in front, for example:

```bash
DATABASE_URL=sqlite:////tmp/scratch.db .venv/bin/flask --app project_tracker db upgrade
```

## Database migrations

The schema is managed by Alembic through Flask-Migrate. After changing a model:

```bash
.venv/bin/flask --app project_tracker db migrate -m "describe the change"
```

Review the generated file in `migrations/versions/` before committing it, in the same
commit as the model change. Autogenerate can't see expression indexes on SQLite, such
as the case-insensitive name index, so those have to be written by hand.
