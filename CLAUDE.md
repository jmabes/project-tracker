# project-tracker

Personal project tracker replacing a spreadsheet. Single user, self-hosted on a home
Ubuntu server, reached over the LAN and Tailscale. Developed in Claude Code cloud sessions
(one session → one branch → one PR). The owner deploys by cloning this public repo onto
the server.

**Start here:** read `docs/ARCHITECTURE.md` before opening source files. It maps every
module, route, invariant and recipe, so you only need to read the files your change
touches. Update it in the same PR when you change any of those.

## Ground rules

- **Documentation first.** Before using any library, framework, CLI, or config syntax,
  fetch and read the official documentation for the version pinned in this repo. Do not
  rely on memory for API signatures, config keys, CLI flags, or systemd/Gunicorn options.
- List every doc URL you consulted under a **References** heading in the PR description.
- If a docs fetch is blocked by the session's network allowlist, stop and tell the owner
  the exact domain to allow. Do not fall back to guessing.
- Do not add data fields, features, or dependencies beyond what the task asks for.
  Propose them under **Follow-ups** in the PR description instead.
- If requirements are ambiguous, ask and wait rather than inventing an answer.
- The owner is new to Linux server administration. Anything they must run on the server
  must be copy-pasteable, explained in one line per command, and include a way to verify
  it worked.

## Environment

- Target host: Ubuntu 24.04, Python 3.12 (server has 3.12.3).
- Pin the interpreter: `.python-version` contains `3.12`; `pyproject.toml` sets
  `requires-python = ">=3.12,<3.13"`.
- Always use a virtual environment at `.venv`. Never install into system Python and never
  use `sudo pip`.
- Cloud sessions: if `python3 --version` is not 3.12.x, create the venv with a uv-managed
  3.12 (`uv python install 3.12`, then `uv venv --python 3.12 .venv`). On the server, use
  `python3 -m venv .venv`.
- Call tools through the venv interpreter so commands work without activation:
  `.venv/bin/python -m pip ...`, `.venv/bin/python -m pytest`, `.venv/bin/python -m ruff ...`.
- `.claude/settings.json` has a SessionStart hook running `scripts/cloud-setup.sh`, which
  exits unless `CLAUDE_CODE_REMOTE=true`, then creates `.venv` if missing and installs
  `requirements-dev.txt`. Keep it fast and idempotent.

## Stack

Decided; changing it requires its own task and a new ADR in `docs/decisions/`.

- Flask (app factory pattern), server-rendered Jinja templates, minimal JavaScript
- SQLite via Flask-SQLAlchemy (SQLAlchemy 2.x style), migrations via Flask-Migrate (Alembic)
- Flask-WTF for forms and CSRF protection
- Spreadsheet import: stdlib `csv` for .csv; `python-calamine` for .xlsx and .ods
  (LibreOffice Calc)
- Gunicorn in production; pytest for tests; ruff for lint and formatting
- Runtime deps pinned with `==` in `requirements.txt`; dev deps in `requirements-dev.txt`
  (which starts with `-r requirements.txt`). Check a package's docs and current PyPI
  release before adding or bumping it.

## Domain model

A `Project` has exactly these user-facing fields (plus `id`, `created_at`, `updated_at`):

| Field | Rules |
| --- | --- |
| `name` | Required, trimmed, max 200 chars, unique (case-insensitive) |
| `category` | Required; one of: Tech, Finance, Home |
| `medium` | Required; one of: Coding, Hardware, Research, DIY |
| `priority` | Required; one of: High, Medium, Low |
| `status` | Required; one of: Not started, In progress, On hold, Done, Abandoned |
| `start_date` | Optional date |
| `target_date` | Optional date; must be on or after `start_date` when both are set |

- There are deliberately **no notes or next-steps fields**. Those live in each project's own
  tracker. Do not add them.
- Allowed values for category, medium, priority, and status are defined in **one** module
  and stored as validated strings (not DB enums), so adding a value is a one-line change
  with no migration.
- Finished projects persist. Marking a project Done or Abandoned never deletes or archives
  it away. The main list hides Done/Abandoned by default with a visible filter to show them.
  Deletion only happens through an explicit, confirmed user action.
- All validation lives in one service layer used by both the web forms and the importer.

## Spreadsheet import

- Accept `.csv`, `.xlsx`, and `.ods` only. Reject everything else, including `.xlsm`.
  Enforce an upload size limit.
- `.ods` support is a hard requirement: the owner's spreadsheet comes from LibreOffice Calc.
- All three formats go through one parser interface that yields header + rows, so the
  validation and preview logic is format-agnostic.
- Flow: upload → preview showing each row's validation result → confirm → write all valid
  rows in a single transaction. Nothing is written before confirmation.
- Header matching is case-insensitive and whitespace-tolerant; document accepted headers
  in the README.
- Dates: accept ISO `YYYY-MM-DD` text and native date cells from both Excel and Calc.
- Rows whose name matches an existing project are skipped and reported, never silently
  overwritten.
- Never store uploaded files after the import finishes.
- Test fixtures for each format live in `tests/fixtures/`. Generate the .xlsx and .ods
  fixtures with a committed script using dev-only dependencies, and document how to
  regenerate them.

## Code conventions

- Type hints on all functions; short docstrings on modules and public functions.
- Configuration comes from environment variables. Commit `.env.example`; never commit
  `.env` or any secret. Production config must refuse to start unless both
  `SECRET_KEY` and `DATABASE_URL` are set.
- The SQLite database path comes from config and lives outside the repo checkout in
  production.
- Every schema change ships with an Alembic migration in the same commit.

## Quality gate (run before every commit)

1. `.venv/bin/python -m ruff check .`
2. `.venv/bin/python -m ruff format --check .`
3. `.venv/bin/python -m pytest`

- New behavior needs tests; bug fixes need a regression test.
- Never claim tests pass without having run them; paste the summary line in the PR.

## Git

- Work only on the session's branch. Never push to `main`.
- Small, atomic commits: one logical change each, and the quality gate passes at every commit.
- Conventional Commits: `type(scope): imperative summary` (≤72 chars), with a body
  explaining *why*. Types: feat, fix, docs, test, refactor, chore, build, ci.
- Keep `.gitignore` current: `.venv/`, `*.db`, `instance/`, `.env`, `__pycache__/`,
  uploads, coverage output.
- Add an entry under `## [Unreleased]` in `CHANGELOG.md` (Keep a Changelog format) in every PR.
- PR description sections: Summary, How tested, References, Follow-ups.
- One milestone per session and PR. When the milestone is done, open the PR and stop.

## Deployment target

- Runs under systemd as a dedicated unprivileged system user, from a venv, via Gunicorn.
- Bind host and port come from config. The server also runs Jellyfin, qBittorrent, and
  Sonarr/Radarr/Prowlarr; don't default to their ports, and tell the owner to confirm the
  port is free with `ss -tlnp`.
- Reachable only on the LAN and tailnet. No auth in v1, so never document port forwarding
  or Tailscale Funnel.
- `docs/deployment.md` covers: first install, update (pull, install deps, `flask db upgrade`,
  restart), backup and restore of the SQLite file, rollback, and checking logs with
  `journalctl`.