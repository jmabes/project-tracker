# Architecture and codebase map

A condensed map of the codebase for agents (and humans) building on it. Read this
**before** opening source files: it should tell you which two or three files a change
touches, so you can read only those. `CLAUDE.md` holds the rules; this file describes
what exists. If they disagree, `CLAUDE.md` wins and this file needs fixing.

> **Keep it current.** A PR that adds, renames or moves a module, route, config key,
> table column, or cross-cutting convention updates this file in the same PR.
> Last checked against `main` at commit `bb56294` (Milestone 5 merged), when the suite
> was `545 passed`.

## 1. Status

- Milestones 1–5 are merged and the app is **deployed and running** on the owner's
  Ubuntu 24.04 server (systemd + Gunicorn, port 8002, LAN and tailnet only, no auth).
- Features: project CRUD, filterable/sortable list with finished projects hidden by
  default, spreadsheet import (.csv/.xlsx/.ods) with preview and confirm, `/healthz`.
- There is no milestone in progress. New work comes as one task per session/branch/PR.
- `docs/ROADMAP.md` holds the original Milestone 2–5 prompts. It is a historical record;
  its "only Milestone 1 is done" intro is stale.

## 2. Repository map

About 2,700 lines of app code, templates, config, migrations and scripts; the rest is tests and docs.

| Path | Lines | What it is |
| --- | --- | --- |
| `project_tracker/__init__.py` | 72 | `create_app(config_name, overrides)`: the app factory. Loads config, enforces production keys, inits extensions, registers blueprints and the app-wide 413 handler. |
| `project_tracker/config.py` | 61 | `Config` / `DevelopmentConfig` / `TestingConfig` / `ProductionConfig`, `CONFIGS`, `env_overrides()`, `MAX_UPLOAD_BYTES` (2 MB). |
| `project_tracker/extensions.py` | 41 | `db` (Flask-SQLAlchemy, `DeclarativeBase`), `migrate`, `csrf`; `register_sql_functions()` adds a `casefold()` SQL function to SQLite. |
| `project_tracker/choices.py` | 23 | **Single source** of allowed values: `CATEGORIES`, `MEDIUMS`, `PRIORITIES`, `STATUSES`, `FINISHED_STATUSES`. Tuple order is the sort order. |
| `project_tracker/models.py` | 45 | `Project` model, `NAME_MAX_LENGTH`, `utcnow()`, and the `uq_projects_name_lower` unique expression index. |
| `project_tracker/services.py` | 410 | **All validation and writes**, plus list query building. See §4 and §5. |
| `project_tracker/forms.py` | 52 | `ProjectForm`: collects input only (no validators). `PROJECT_FIELDS`, `raw_input()`, `add_errors()`. |
| `project_tracker/projects.py` | 191 | `projects` blueprint: list, detail, create, edit, delete views. `COLUMN_LABELS`, `SortHeader`. |
| `project_tracker/health.py` | 25 | `health` blueprint: `GET /healthz` reads one row; 200 or 503. |
| `project_tracker/importer/parsers.py` | 140 | Upload → `ParsedSheet` (header + numbered rows). One parser per extension in `PARSERS`. |
| `project_tracker/importer/preview.py` | 378 | Header-row search, column mapping, per-row outcome (`valid`/`invalid`/`skipped`), JSON encode/decode of rows for the confirm form. |
| `project_tracker/importer/confirm.py` | 37 | `save_rows()`: re-check rows, then `services.create_projects` in one transaction. |
| `project_tracker/importer/views.py` | 131 | `imports` blueprint (`/import`): upload form, upload→preview, confirm. 413 handler. |
| `project_tracker/templates/` | — | Jinja: `base.html`, `projects/{index,detail,form,delete}.html`, `imports/{upload,preview}.html`, `errors/413.html`. |
| `project_tracker/static/style.css` | 251 | Hand-written CSS, no framework, no JavaScript anywhere. |
| `migrations/` | — | Flask-Migrate/Alembic. `env.py` is lightly edited (type hints, `db.engine`). Two revisions, see §7. |
| `tests/` | — | pytest, 545 tests. `conftest.py` + one file per area; `fixtures/` holds generated spreadsheets. See §9. |
| `scripts/cloud-setup.sh` | 30 | SessionStart hook: builds `.venv` in cloud sessions only; skips pip if requirements are unchanged. |
| `scripts/make_fixtures.py` | 177 | Regenerates `tests/fixtures/*` (uses dev-only openpyxl + odfpy). |
| `gunicorn.conf.py` | 41 | Bind from `PROJECT_TRACKER_HOST`/`PORT` (default `127.0.0.1:8002`), 2 sync workers, logs to stdout. |
| `deploy/project-tracker.service` | 64 | Sandboxed systemd unit (`Type=notify`, `StateDirectory=project-tracker`, `ProtectSystem=strict`). |
| `docs/deployment.md` | 571 | Owner-facing server guide: install, update, backup/restore, rollback, logs. |
| `docs/decisions/` | — | ADR 0001 (stack and pinned versions), ADR 0002 (import preview state in a hidden field). |
| `.github/workflows/ci.yml` | 45 | CI: ruff check, ruff format --check, pytest on Python 3.12 / ubuntu-24.04. |

## 3. Layering and invariants

```text
request ─▶ blueprint view ─▶ form.raw_input() / importer rows ─▶ services ─▶ models/db
            (projects.py,      (collect only, never validate)     (validate,
             importer/views.py)                                    write, query)
```

Rules that every change must keep:

1. **Views never validate or write.** They call a `services` function and render the
   result. A `ProjectValidationError` is caught and its `.errors` dict
   (`field -> [messages]`) is shown next to the fields via `form.add_errors()`.
2. **Every project write goes through** `create_project`, `create_projects`,
   `update_project` or `delete_project`. Each of these calls `validate_project` first
   and commits itself.
3. **Allowed values live only in `choices.py`.** They are stored as plain `VARCHAR(50)`,
   with no DB enums or CHECK constraints, so adding a value needs no migration.
4. **Forms declare no validators** and views never call `form.validate()`. CSRF is
   enforced app-wide by `CSRFProtect` on every POST. Templates render `form.csrf_token`
   or `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
5. **Finished projects are never removed by status.** Done and Abandoned only hide a
   project from the default list. Deleting needs the GET confirmation page and then a POST.
6. **Name uniqueness ignores case and uses Unicode folding.** `services._name_taken`
   compares `str.casefold()` in Python, so "Café" = "CAFÉ" and "Straße" = "STRASSE". The
   DB index on `lower(name)` (ASCII-only in SQLite) is just a backstop. An
   `IntegrityError` on commit becomes the name error "A project with this name already
   exists." (`NAME_TAKEN_MESSAGE`).
7. **No server-side state between requests**, apart from Flask's signed session cookie,
   which holds flashes and the CSRF token. The import preview carries its rows in a
   hidden form field (ADR 0002).

## 4. Domain model and validation (`models.py`, `services.py`)

`projects` table: `id`, `name` (≤200), `category`, `medium`, `priority`, `status`
(all `String(50)`), `start_date`, `target_date` (nullable `Date`), `created_at`,
`updated_at` (naive UTC via `utcnow()`, set by the app). Field rules are in
`CLAUDE.md` → Domain model. There are deliberately **no** notes or next-steps fields.

Key service API (all in `project_tracker/services.py`):

| Symbol | Purpose |
| --- | --- |
| `validate_project(raw, *, exclude_id=None) -> ProjectData` | Trims text and checks required fields, choices (exact spelling), dates and date order, plus name uniqueness. It collects **every** failing field, then raises `ProjectValidationError(errors)`. |
| `ProjectData` | Frozen dataclass of cleaned values; `_fields(data)` turns it into model kwargs. |
| `create_project(raw)` / `update_project(project, raw)` | Validate, set fields, commit. Update passes `exclude_id` so a project can keep its own name. |
| `create_projects(raws)` | All-or-nothing batch. Every row is validated first, names must also be unique within the batch, and the batch rolls back on any DB error. Used by the import. |
| `delete_project(project)` | Permanent delete and commit. |
| `CHOICE_FIELDS` | `{"category": CATEGORIES, ...}`. Views, the list and the importer iterate this instead of naming the fields. |

Input coercion that `validate_project` does:

- Text: non-`str` values are rejected ("Name must be text."), never stringified.
- Dates: accepts `date`, `datetime` (the date part is kept), ISO `YYYY-MM-DD` text, or
  blank. Anything else is rejected. There is no guessing of `DD/MM/YYYY`.

## 5. Project list (`services.py` lower half, `projects.index`)

- `parse_list_options(request.args) -> ListOptions` ignores unknown or invalid values,
  so a bad URL never causes a 500. `ListOptions.query_args()` does the reverse and
  leaves defaults out, so the plain list stays at `/`.
- Query params: `category`, `medium`, `priority`, `status` (exact allowed value),
  `show_finished=1`, `sort` (one of `SORT_COLUMNS`), `dir` (`asc`/`desc`).
- Done/Abandoned (`FINISHED_STATUSES`) are hidden unless `show_finished=1` **or**
  `status` names one explicitly (`ListOptions.hides_finished`).
- `project_list_query(options)` combines filters with AND. Ordering:
  - `key IS NULL` comes first in the ORDER BY, so empty values sort last in both directions.
  - Then the sort key, then `casefold(name)`, then `id`.
- Priority and status sort by their position in `choices.py` via `CASE`. Priority is
  ranked so `desc` puts High first. The default sort is priority `desc`
  (`DEFAULT_DIRECTIONS`).
- `name` sorts by the registered SQLite `casefold()` function (`extensions.py`), which
  matches the uniqueness check.
- The view builds `SortHeader`s and passes a `list_url(**changes)` helper to the
  template. Clicking the current column flips its direction.

## 6. Spreadsheet import (`project_tracker/importer/`)

Flow: `GET /import/` → `POST /import/` (parse + preview, writes nothing) → `POST
/import/confirm` (re-check + save in one transaction) → redirect to `/` with a flash.

1. **`parsers.parse_upload(filename, stream) -> ParsedSheet`**
   - Picks the parser by lower-cased extension from `PARSERS`: `.csv` (stdlib `csv`,
     `utf-8-sig`), `.xlsx` and `.ods` (python-calamine, first sheet,
     `skip_empty_area=False` so list positions match row numbers).
   - Any other extension, including `.xlsm`, raises `ImportFileError`, whose message is
     shown to the user.
   - Blank rows are dropped and the remaining rows keep their 1-based spreadsheet row
     numbers.
   - Cells keep their native types (`Cell = str | int | float | bool | date | datetime
     | time | timedelta`).
2. **`preview.preview_sheet(sheet) -> Preview`**
   - `find_header` uses the first row naming all of `REQUIRED_COLUMNS` (`name`,
     `category`, `medium`, `priority`, `status`). Rows above it, such as titles, are
     ignored and counted.
   - `normalize_header` folds case and treats runs of spaces/underscores as `_`, so
     "Start Date" matches `start_date`. There are **no aliases** (owner decision).
   - Extra columns are ignored and listed. A missing date column means blank dates.
   - `build_preview(rows)` decides each row's outcome:
     - Skipped if the name matches an existing project or an earlier row in the file
       (first row wins).
     - Otherwise `validate_project` makes it `valid` or `invalid`.
   - Import-only conversions in `_normalize` happen before validation:
     - Choices match in any case and become the canonical spelling (`tech` → `Tech`).
     - A whole-number name becomes text (`1984.0` → `"1984"`).
3. **Preview → confirm state (ADR 0002)**
   - `encode_rows(preview)` puts the valid rows' cleaned values in a hidden `rows`
     field as JSON.
   - `decode_rows` checks only the JSON's shape.
   - `confirm.save_rows` runs `build_preview` again, then `create_projects`. If
     anything no longer passes, it raises `ImportChangedError(preview)` and the view
     re-renders the preview with a notice. Nothing is saved.
4. **Uploads are never stored.** They are read into memory and `file.close()` is
   called in `finally`. `MAX_CONTENT_LENGTH` (2 MB) causes a 413, rendered by
   `importer.views.request_entity_too_large`. It is registered app-wide because the
   size check can fire during CSRF checking, before any view runs.

## 7. Database and migrations

- Dev DB: `instance/project_tracker.db` (relative SQLite URL resolves against the
  instance folder). Tests: `sqlite://` in memory, built with `db.create_all()` per test.
  Production: `DATABASE_URL=sqlite:////var/lib/project-tracker/project_tracker.db`.
- Revisions: `86bbf26dee64` (create `projects` + index) → `4ed531acccd0` (rename
  `estimated_completion_date` → `target_date`). Head is `4ed531acccd0`.
- **Gotchas:**
  - Autogenerate can't see the `lower(name)` expression index on SQLite, so write
    index changes by hand.
  - Don't use Alembic batch mode on `projects`: it rebuilds the table from reflection
    and would silently **drop** `uq_projects_name_lower`. Plain `op.alter_column(...,
    new_column_name=...)` compiles to `ALTER TABLE ... RENAME COLUMN` on SQLite. See
    the comment in `4ed531acccd0`.
  - Never edit an applied migration; the production DB is live.
- `tests/test_migrations.py` checks that upgrading an empty file gives the models'
  schema (`compare_metadata`), that the index exists, and that upgrade/downgrade keep
  data. Extend it with every new revision.
- Create a revision: `.venv/bin/flask --app project_tracker db migrate -m "..."`, review
  it, and commit it **with** the model change.

## 8. Configuration

| Env var | Read by | Notes |
| --- | --- | --- |
| `PROJECT_TRACKER_CONFIG` | `create_app` | `development` (default) / `testing` / `production`. |
| `SECRET_KEY` | `config.env_overrides` | Production refuses to start without it (`RuntimeError`). |
| `DATABASE_URL` | `config.env_overrides` | Mapped to `SQLALCHEMY_DATABASE_URI`. Required in production. |
| `PROJECT_TRACKER_HOST` / `PROJECT_TRACKER_PORT` | `gunicorn.conf.py` only | Default `127.0.0.1:8002`; the server uses `0.0.0.0:8002`. |

- The `testing` config ignores the environment, sets `WTF_CSRF_ENABLED = False` and
  uses an in-memory DB.
- `create_app(name, overrides={...})` applies `overrides` last; tests use it for
  per-test config.
- There is no `.env` autoloading (python-dotenv was deliberately not added).
- A new setting goes in a `Config` class plus `env_overrides()` if it comes from the
  environment, `.env.example`, the README config table, and the server env file
  instructions in `docs/deployment.md`.

## 9. Routes and templates

| Method + path | Endpoint | Template |
| --- | --- | --- |
| GET `/` | `projects.index` | `projects/index.html` |
| GET `/projects/new` · POST `/projects` | `projects.new` · `projects.create` | `projects/form.html` |
| GET `/projects/<id>` | `projects.detail` | `projects/detail.html` |
| GET/POST `/projects/<id>/edit` | `projects.edit` · `projects.update` | `projects/form.html` |
| GET/POST `/projects/<id>/delete` | `projects.confirm_delete` · `projects.delete` | `projects/delete.html` |
| GET/POST `/import/` | `imports.upload_form` · `imports.upload` | `imports/upload.html` → `imports/preview.html` |
| POST `/import/confirm` | `imports.confirm` | redirect, or `imports/preview.html` on change |
| GET `/healthz` | `health.healthz` | JSON `{"status": "ok"}` 200 / `{"status": "error", "database": "unavailable"}` 503 |

Template conventions:

- Every page extends `base.html` and uses the blocks `title`, `content`, and
  optionally `main_class`. `wide` (72rem) is used by the list and the preview; other
  pages are 40rem.
- Flashes are rendered in `base.html` with a category (`flash-error` for errors).
- Successful POSTs redirect (post/redirect/get) with a flash such as `Created “Name”.`
  Failed POSTs re-render with status 200.
- Unknown ids use `db.get_or_404`.
- Accessibility: invalid fields get `aria-invalid` and `aria-describedby` pointing to
  an error list; the list headers use `aria-sort`.
- 404 and CSRF-failure pages are still Flask's plain defaults.

## 10. Tests (`tests/`)

- `conftest.py` provides `app` (`create_app("testing")`, `db.create_all()` inside an
  app context, `drop_all` after) and `client`.
- pytest runs with `strict = true` and `filterwarnings = ["error"]`, so any warning,
  such as a `ResourceWarning` or a deprecation, fails the test.
- Ruff selects `E W F I B UP ANN D` (Google docstrings). Tests and migrations skip `D`
  but still need type hints.

| Area | File(s) |
| --- | --- |
| Config, factory, production refusal | `test_config.py` |
| Validation rules | `test_services.py` |
| create/update/delete, IntegrityError path | `test_service_writes.py` |
| List options and query | `test_list_projects.py` (service), `test_list_view.py` (HTTP) |
| CRUD views | `test_views.py` (helpers `make_project`, `form_data`, `all_projects`) |
| CSRF on (own `app` fixture with `WTF_CSRF_ENABLED=True`) | `test_csrf.py`: add every new POST here |
| Import | `test_import_parsers.py`, `test_import_preview.py`, `test_import_confirm.py`, `test_import_views.py` |
| Migrations | `test_migrations.py` (on-disk DB under `tmp_path`) |
| Health, Gunicorn conf, SQL `casefold`, model | `test_health.py`, `test_gunicorn_conf.py`, `test_sql_functions.py`, `test_models.py` |

- Fixtures in `tests/fixtures/` are **generated**. Edit the rows in
  `scripts/make_fixtures.py`, then run `.venv/bin/python scripts/make_fixtures.py`.
- In import view tests, build multipart bodies in memory. Werkzeug's test client
  spools large bodies to temp files it never closes, which raises `ResourceWarning`
  and therefore errors.

## 11. Production (as deployed)

| What | Where |
| --- | --- |
| Code + venv | `/opt/project-tracker` (owned by the owner's login user; read-only to the service) |
| Env file | `/etc/project-tracker/project-tracker.env` (`root:project-tracker 0640`) |
| Database | `/var/lib/project-tracker/project_tracker.db` (systemd `StateDirectory`) |
| Backups | `/var/backups/project-tracker/` (sqlite3 `.backup`) |
| Service / logs | `project-tracker.service`; `journalctl -u project-tracker` |

What this means for changes:

- The owner updates with: backup → `git pull` → `pip install -r requirements.txt` →
  stop → `flask db upgrade` → reinstall the unit file → start (`docs/deployment.md` §2).
  A PR with a migration or new env var must say so plainly in its Summary, because the
  owner runs those steps by hand.
- Only `requirements.txt` is installed on the server, so runtime imports must not
  come from `requirements-dev.txt`.
- The service sandbox makes everything except `/var/lib/project-tracker` read-only and
  gives it a private `/tmp`. Code must not write anywhere else at runtime.
- Never document port forwarding or Tailscale Funnel. Server commands must follow
  the CLAUDE.md format: copy-pasteable, a one-line explanation, and a verify step.

## 12. Recipes

**Add an allowed value** (e.g. a new category): add it to the tuple in `choices.py`;
its position is its sort order. For a status that should be hidden by default, also
add it to `FINISHED_STATUSES`. Update the value lists in the README import table and
in `CLAUDE.md`'s domain table. No migration is needed. Add a test.

**Add a page or route:** add a view to the relevant blueprint (or a new blueprint
registered in `create_app`). Put any logic in `services.py`. Add a template extending
`base.html` and, if needed, a nav link in `base.html`. Add HTTP tests, plus a CSRF
test for any POST. Update the README pages table and §9 here.

**Add a project field** (only when a task explicitly asks; `CLAUDE.md` forbids
unrequested fields). Every place that enumerates fields:

- `models.Project` and a new Alembic migration (plus a test in `test_migrations.py`)
- `services`: `ProjectData`, `validate_project`, `_fields`, and `SORT_COLUMNS` if sortable
- `forms`: the form field and `PROJECT_FIELDS`
- `projects.COLUMN_LABELS`
- templates: `projects/detail.html`, plus `projects/index.html` (header and cell) if listed
- importer: `preview.REQUIRED_COLUMNS` or `OPTIONAL_COLUMNS`
- `scripts/make_fixtures.py`, then regenerate the fixtures
- docs: the README (pages, import headers, sort params) and `CLAUDE.md`'s domain table

**Add or bump a dependency:**

- Check its docs and the current PyPI release first.
- Pin it with `==` in `requirements.txt`, or in `requirements-dev.txt` for dev-only use.
- Record why in the PR's References and Follow-ups.
- A stack change needs an ADR in `docs/decisions/`.
- `SQLAlchemy` stays on 2.0.x until Flask-SQLAlchemy supports 2.1 (ADR 0001).

## 13. Open follow-ups (proposed in earlier PRs, not done)

- **Deps:**
  - Bump Gunicorn 26.2.0 → 26.2.2 (chunked-encoding hardening).
  - SQLAlchemy 2.1 once Flask-SQLAlchemy supports it.
  - Lock transitive deps.
  - Dependabot.
- **Ops:**
  - Daily backup timer with pruning and an off-machine copy.
  - `ExecStartPre=` running `flask db upgrade`.
  - Tighter sandboxing (`SystemCallFilter`, `MemoryDenyWriteExecute`).
  - Reverse proxy/TLS or `tailscale serve`.
- **UI:**
  - Custom 404 and CSRF-error pages.
  - Multi-select filters.
  - Locale-aware name sorting.
  - Browser-side `required`/`maxlength` hints.
  - Pagination if the list grows large.
- **Import:**
  - Row/cell caps against compressed-file blowup.
  - Other text date formats (would need an explicit owner decision).
  - The header-row search rule isn't written in `CLAUDE.md`.
- **Docs:** refresh `docs/ROADMAP.md`'s status intro.
