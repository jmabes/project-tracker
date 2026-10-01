# Roadmap

Milestone 1 (foundation: stack, scaffold, domain layer, `/healthz`, CI) is done. Each
milestone below gets its own Claude Code session, branch, and PR. Paste the prompt
block into a new session as-is.

Every milestone also inherits the standing acceptance criteria:

- Fresh clone → venv → `.venv/bin/python -m pip install -r requirements-dev.txt` →
  quality gate passes.
- Commits are atomic, follow Conventional Commits, and each one passes the quality gate.
- CI passes on the PR.
- PR description has Summary, How tested (with the actual pytest summary line),
  References, and Follow-ups. `CHANGELOG.md` has an `[Unreleased]` entry.
- Any decision CLAUDE.md doesn't cover is listed under Follow-ups for review.

---

## Milestone 2 — Project CRUD UI

```text
Milestone 2: project CRUD UI for project-tracker.
Read CLAUDE.md first and follow it throughout. This session covers Milestone 2 only.

Scope
1. Base Jinja layout (server-rendered, minimal or no JavaScript) with a site header
   and flash-message area. Keep styling simple and readable on desktop and phone;
   propose any CSS framework under Follow-ups rather than adding one.
2. A Flask-WTF form for Project covering exactly the fields in CLAUDE.md → Domain
   model. Choice fields are <select>s populated from project_tracker/choices.py.
   Dates use <input type="date">.
3. Views (in a blueprint):
   - GET  /projects/new and POST /projects       → create
   - GET  /projects/<id>                         → detail
   - GET  /projects/<id>/edit, POST /projects/<id>/edit → edit
   - GET  /projects/<id>/delete (confirmation page) and POST /projects/<id>/delete
   - A temporary plain index at / that lists project names linking to detail
     (Milestone 3 replaces it with the real list).
4. All validation goes through project_tracker.services.validate_project; the form
   only collects input. Show per-field errors from ProjectValidationError next to
   the fields. Editing passes exclude_id so a project can keep its own name.
5. Add small service functions create_project / update_project / delete_project in
   project_tracker/services.py and route all writes through them. Handle an
   IntegrityError on the name index as a "name already exists" field error.
6. Marking a project Done or Abandoned only changes status; never delete or hide it
   from its detail page.
7. CSRF protection is on for every POST (Flask-WTF). 404 for unknown ids.

Out of scope
Sorting/filtering, spreadsheet import, authentication, deployment files.

Acceptance criteria
☐ Create, view, edit, and delete work end to end in the browser.
☐ Delete requires a confirmation step and only happens on POST.
☐ Invalid input re-renders the form with the user's values and per-field errors.
☐ Duplicate names (any case, including non-ASCII like "Café"/"CAFÉ") are rejected.
☐ A POST without a valid CSRF token is rejected (test with CSRF enabled).
☐ Tests cover each view's success and failure paths, and the service functions.
☐ No new data fields or dependencies.

Start by giving me a short plan of the commits you intend to make. Wait for my
approval before writing code.
```

---

## Milestone 3 — Project list with sort and filter

```text
Milestone 3: main project list with sort and filter for project-tracker.
Read CLAUDE.md first and follow it throughout. This session covers Milestone 3 only.

Scope
1. Replace the temporary index at / with the main project list: a table showing
   name (linking to detail), category, medium, priority, status, start date, and
   estimated completion date.
2. Filters for category, medium, priority, and status, built from
   project_tracker/choices.py. Done and Abandoned are hidden by default; a clearly
   visible control shows them. Filters combine with AND.
3. Sorting by any column, ascending/descending. Priority sorts by meaning
   (High > Medium > Low) and status by its order in choices.py, not alphabetically.
   Empty dates sort last in both directions.
4. Filter and sort state live in the query string (GET form), so a view can be
   bookmarked and the back button works. No JavaScript required.
5. Put the query-building logic in the service layer, not the view, and unit test it.
6. Show an empty state when nothing matches, including a hint when finished
   projects are hidden.

Out of scope
Pagination (propose under Follow-ups if needed), full-text search, import,
authentication, deployment files.

Acceptance criteria
☐ Default view hides Done and Abandoned; one click shows them; they are never deleted.
☐ Every filter and every sortable column has tests, including the default
  (no query string) case and invalid query-string values (ignored, not 500).
☐ Priority and status sort by meaning, and empty dates sort last.
☐ The ordering of allowed values is defined once (choices.py), not duplicated.
☐ No new data fields or dependencies.

Start by giving me a short plan of the commits you intend to make. Wait for my
approval before writing code.
```

---

## Milestone 4 — Spreadsheet import (.csv, .xlsx, .ods)

```text
Milestone 4: spreadsheet import for project-tracker.
Read CLAUDE.md first (especially "Spreadsheet import") and follow it throughout.
This session covers Milestone 4 only. Read docs/decisions/0001-stack.md for what we
already know about python-calamine date handling.

Scope
1. One parser interface that takes an uploaded file and yields a header row plus
   data rows, with implementations for .csv (stdlib csv, UTF-8 with or without BOM)
   and .xlsx/.ods (python-calamine, first sheet). The validation and preview code
   must not know which format the rows came from.
2. Accept only .csv, .xlsx and .ods (reject everything else, including .xlsm), and
   enforce an upload size limit via MAX_CONTENT_LENGTH with a friendly 413 page.
   Ask me what limit to use before choosing one.
3. Header matching: case-insensitive and whitespace-tolerant. Document the accepted
   headers in the README. Missing required columns is a file-level error. Ask me
   before accepting header aliases beyond the field names themselves.
4. Each row goes through project_tracker.services.validate_project. Dates accept ISO
   YYYY-MM-DD text and native date cells from Excel and Calc. Rows whose name
   matches an existing project (case-insensitive) are skipped and reported, never
   overwritten. Also detect duplicate names within the same file.
   Before writing code, ask me about two decisions left open in Milestone 1:
   - Choice matching: validate_project currently requires exact spelling for
     category, medium, priority and status ("tech" is rejected). Should the import
     accept any capitalisation and store the canonical value ("tech" → "Tech")?
   - All-number names: calamine returns a numeric cell such as 1984 as the float
     1984.0, which validate_project rejects with "Name must be text.". Should the
     importer convert whole numbers to text ("1984") before validation?
5. Flow: upload → preview table showing each row's result (valid / error messages /
   skipped as duplicate) → confirm → write all valid rows in a single transaction.
   Nothing is written before confirmation. Decide how preview state survives between
   the preview and confirm requests WITHOUT storing the uploaded file after the
   import finishes; explain the choice in the PR and in a new ADR if it's
   significant.
6. Fixtures in tests/fixtures/ for each format (valid rows, invalid rows, native date
   cells, duplicate names). Generate the .xlsx and .ods fixtures with a committed
   script using dev-only dependencies (check the docs and PyPI for the writer
   libraries before adding them), and document how to regenerate them. Note from
   ADR 0001: calamine rejects hand-written ODS XML with whitespace between cells,
   so use a real ODS writer.

Out of scope
Updating existing projects from a spreadsheet, export, authentication, deployment.

Acceptance criteria
☐ .csv, .xlsx, and .ods files each import correctly, including native date cells.
☐ .xlsm and other extensions are rejected; oversized uploads get a 413 page.
☐ Preview shows every row's outcome; nothing is written until confirm.
☐ Confirm writes all valid rows in one transaction (a failure writes none).
☐ Existing and in-file duplicate names are skipped and reported.
☐ No uploaded file remains on disk after the import finishes (tested).
☐ Fixture generator script committed and documented; fixtures committed.
☐ README documents accepted headers and date formats.

Start by giving me a short plan of the commits you intend to make. Wait for my
approval before writing code.
```

---

## Milestone 5 — Deployment to the home server

```text
Milestone 5: deployment for project-tracker.
Read CLAUDE.md first (especially "Deployment target") and follow it throughout.
This session covers Milestone 5 only. I am new to Linux server administration.

Scope
1. Gunicorn config (gunicorn.conf.py or command-line flags, from the Gunicorn docs
   for the pinned version) with bind host and port coming from configuration. Do not
   default to ports used by Jellyfin, qBittorrent, Sonarr, Radarr, or Prowlarr; ask
   me which port to use and tell me to confirm it is free with `ss -tlnp`.
2. A systemd unit file running the app as a dedicated unprivileged system user from
   the venv via Gunicorn, with an EnvironmentFile for SECRET_KEY, DATABASE_URL and
   PROJECT_TRACKER_CONFIG=production. Check the systemd docs for every directive
   used, and consider sandboxing options (e.g. ProtectSystem, ReadWritePaths) for the
   database directory.
3. docs/deployment.md covering: first install (system user, directories, clone,
   venv, env file with a generated SECRET_KEY, `flask db upgrade`, enable/start the
   service), update (pull, install deps, `flask db upgrade`, restart), backup and
   restore of the SQLite file (safe online backup, not a raw copy of a live DB),
   rollback to a previous commit, and checking logs with journalctl.
4. Every server command must be copy-pasteable, explained in one line, and followed
   by a way to verify it worked (e.g. `systemctl status`, `curl .../healthz`).
5. Reachable only on the LAN and tailnet. No authentication exists, so never
   document port forwarding or Tailscale Funnel.
6. Extend GET /healthz to run a trivial database query and return 503 if it fails,
   so the deployment's verify step also catches a wrong DATABASE_URL or file
   permissions (decided in the Milestone 1 review). Test both outcomes.

Out of scope
Reverse proxy/TLS (propose under Follow-ups), authentication, new app features.

Acceptance criteria
☐ Following docs/deployment.md on a fresh Ubuntu 24.04 box results in
  `curl http://<server>:<port>/healthz` returning 200 from another LAN machine.
☐ /healthz returns 503 when the database can't be reached (tested).
☐ The service runs as the dedicated user, restarts on failure, and starts at boot.
☐ The database lives outside the repo checkout and survives an update.
☐ Backup, restore, and rollback steps are tested at least once in the session's
  container (or explained why not) and documented with verification steps.
☐ Production refuses to start without SECRET_KEY / DATABASE_URL (already enforced;
  the docs explain the error message if seen).

Start by giving me a short plan of the commits you intend to make. Wait for my
approval before writing code.
```
