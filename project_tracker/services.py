"""Project validation: the one place field rules are enforced.

Web forms and the spreadsheet importer both call ``validate_project`` so every
project in the database has passed the same checks.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select

from project_tracker import choices
from project_tracker.extensions import db
from project_tracker.models import NAME_MAX_LENGTH, Project

ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

CHOICE_FIELDS: dict[str, tuple[str, ...]] = {
    "category": choices.CATEGORIES,
    "medium": choices.MEDIUMS,
    "priority": choices.PRIORITIES,
    "status": choices.STATUSES,
}


@dataclass(frozen=True)
class ProjectData:
    """Cleaned, validated values for a project's user-facing fields."""

    name: str
    category: str
    medium: str
    priority: str
    status: str
    start_date: date | None
    estimated_completion_date: date | None


class ProjectValidationError(Exception):
    """Raised when input fails validation; ``errors`` maps field to messages."""

    def __init__(self, errors: dict[str, list[str]]) -> None:
        """Store the per-field error messages."""
        super().__init__(errors)
        self.errors = errors


def validate_project(
    raw: Mapping[str, object], *, exclude_id: int | None = None
) -> ProjectData:
    """Validate raw input for a project and return cleaned values.

    Text values are trimmed. Dates may be ``date`` objects, ``datetime`` objects
    (the time is dropped), ISO ``YYYY-MM-DD`` strings, or blank.

    Args:
        raw: Field name to raw value, e.g. form data or a spreadsheet row.
        exclude_id: ID of the project being edited, so it doesn't clash with its
            own name.

    Raises:
        ProjectValidationError: With every failing field, not just the first.
    """
    errors: dict[str, list[str]] = {}

    def fail(field: str, message: str) -> None:
        errors.setdefault(field, []).append(message)

    name = _clean_text(raw.get("name"))
    if isinstance(name, _NotText):
        fail("name", "Name must be text.")
        name = None
    elif name is None:
        fail("name", "Name is required.")
    elif len(name) > NAME_MAX_LENGTH:
        fail("name", f"Name must be at most {NAME_MAX_LENGTH} characters.")
    elif _name_taken(name, exclude_id):
        fail("name", "A project with this name already exists.")

    cleaned_choices: dict[str, str] = {}
    for field, allowed in CHOICE_FIELDS.items():
        label = field.capitalize()
        value = _clean_text(raw.get(field))
        if isinstance(value, _NotText):
            fail(field, f"{label} must be text.")
        elif value is None:
            fail(field, f"{label} is required.")
        elif value not in allowed:
            fail(field, f"{label} must be one of: {', '.join(allowed)}.")
        else:
            cleaned_choices[field] = value

    dates: dict[str, date | None] = {}
    for field in ("start_date", "estimated_completion_date"):
        try:
            dates[field] = _parse_date(raw.get(field))
        except ValueError as exc:
            fail(field, str(exc))

    start, estimate = dates.get("start_date"), dates.get("estimated_completion_date")
    if start is not None and estimate is not None and estimate < start:
        fail(
            "estimated_completion_date",
            "Estimated completion date must be on or after the start date.",
        )

    if errors or name is None:  # name is None always records an error
        raise ProjectValidationError(errors)

    return ProjectData(
        name=name,
        start_date=start,
        estimated_completion_date=estimate,
        **cleaned_choices,
    )


class _NotText:
    """Marker returned by _clean_text for values that aren't strings."""


def _clean_text(value: object) -> str | None | _NotText:
    """Return trimmed text, None for missing/blank values, or _NotText.

    Non-strings (e.g. a number from a spreadsheet cell) are rejected rather than
    converted, so 1984.0 never silently becomes the name "1984.0".
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return _NotText()
    return value.strip() or None


def _parse_date(value: object) -> date | None:
    """Parse an optional date; raise ValueError with a user-facing message."""
    if value is None:
        return None
    if isinstance(value, datetime):  # check first: datetime is a subclass of date
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if ISO_DATE_RE.fullmatch(text):
            try:
                return date.fromisoformat(text)
            except ValueError:
                pass
    raise ValueError(f"{value!r} is not a valid date; use YYYY-MM-DD.")


def _name_taken(name: str, exclude_id: int | None) -> bool:
    """Return True if another project has this name, ignoring case.

    Compares with str.casefold() in Python because SQLite's lower() only folds
    ASCII letters.
    """
    folded = name.casefold()
    rows = db.session.execute(select(Project.id, Project.name)).all()
    return any(row.name.casefold() == folded and row.id != exclude_id for row in rows)
