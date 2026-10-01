# project-tracker

A small self-hosted web app that replaces a spreadsheet for tracking personal projects.
Each project has a name, category, medium, priority, status, and optional start and
estimated completion dates. It is built for one user on a home server, reached over the
LAN and Tailscale.

> **Status:** Milestone 3 (project list). You can create, view, edit, and delete
> projects in the browser, and filter and sort the main list. Spreadsheet import and
> the deployment guide arrive in later milestones. See [docs/ROADMAP.md](docs/ROADMAP.md).

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
`377 passed in 4.38s`.

## Running the development server

```bash
# Create or upgrade the database schema (development database: instance/project_tracker.db)
.venv/bin/flask --app project_tracker db upgrade

# Start the dev server with auto-reload and the debugger
.venv/bin/flask --app project_tracker run --debug
```

Check it's running by opening <http://127.0.0.1:5000/healthz> or running
`curl http://127.0.0.1:5000/healthz`. The response should contain `"status": "ok"`.
Stop the server with Ctrl+C.

## Using the app

Open <http://127.0.0.1:5000/>. The pages are:

| Page | What it does |
| --- | --- |
| `/` | The project list: a table you can filter by category, medium, priority, and status, and sort by clicking any column heading (click again to reverse). Done and Abandoned projects are hidden until you click **Show finished projects**. |
| `/projects/new` | Form to add a project. Also linked as **New project** in the header. |
| `/projects/<id>` | One project's details, with **Edit** and **Delete** links. |
| `/projects/<id>/edit` | Change any field. To finish a project, set its status to Done or Abandoned; it stays in the tracker. |
| `/projects/<id>/delete` | Asks for confirmation; only the **Delete project** button removes it, permanently. |

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
| `sort` | `name`, `category`, `medium`, `priority`, `status`, `start_date`, `estimated_completion_date` | `priority` |
| `dir` | `asc` or `desc` | `desc` (High first) for priority, `asc` for the rest |

Priority sorts by importance (High, Medium, Low) and status in workflow order
(Not started, In progress, On hold, Done, Abandoned), not alphabetically. Names sort
ignoring case. Projects without a date always sort after those with one.
Example: `/?category=Tech&priority=High&sort=start_date&dir=asc`.

The development server is for local use only. Production runs under Gunicorn and
systemd; that guide arrives with the deployment milestone.

## Configuration

Settings come from environment variables; [.env.example](.env.example) lists them all.

| Variable | Purpose | Default |
| --- | --- | --- |
| `PROJECT_TRACKER_CONFIG` | `development`, `production`, or `testing` | `development` |
| `SECRET_KEY` | Signs sessions and CSRF tokens. **Required in production.** | insecure dev key |
| `DATABASE_URL` | SQLAlchemy URL for the SQLite file. **Required in production** (keep the file outside the repo). | `instance/project_tracker.db` |

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
