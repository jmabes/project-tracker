# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Flask app factory with development, testing, and production config; production
  requires `SECRET_KEY` and `DATABASE_URL`.
- `GET /healthz` health check endpoint.
- `Project` model, single module of allowed values, and initial Alembic migration
  with a case-insensitive unique index on project names.
- Project validation service shared by future forms and the spreadsheet importer.
- Test suite, ruff configuration, and GitHub Actions CI running the quality gate on
  Python 3.12.
- SessionStart hook that prepares `.venv` in Claude Code cloud sessions.
- README, stack decision record (ADR 0001), and roadmap for Milestones 2–5.
- Project pages: create, view, edit, and delete (with a confirmation step) in the
  browser, plus a temporary index listing every project by name.
- Base page layout with a site header, flash messages, and a small stylesheet that
  works on phones.
- `create_project`, `update_project`, and `delete_project` service functions; a
  database name clash is reported as a "name already exists" field error.
- CSRF protection tests for every form POST.

[Unreleased]: https://github.com/jmabes/project-tracker/commits/main
