"""Project validation, writes and list queries.

Web forms and the spreadsheet importer both call ``validate_project`` so every
project in the database has passed the same checks. All project writes go through
``create_project``, ``create_projects``, ``update_project`` and ``delete_project``.
The main list's filtering and sorting is built by ``parse_list_options`` and
``list_projects``.
"""

import dataclasses
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from sqlalchemy import ColumnElement, Select, case, func, select
from sqlalchemy.exc import IntegrityError

from project_tracker import choices
from project_tracker.extensions import db
from project_tracker.models import NAME_MAX_LENGTH, Project

ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
NAME_TAKEN_MESSAGE = "A project with this name already exists."

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
    target_date: date | None


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
        fail("name", NAME_TAKEN_MESSAGE)

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
    for field in ("start_date", "target_date"):
        try:
            dates[field] = _parse_date(raw.get(field))
        except ValueError as exc:
            fail(field, str(exc))

    start, target = dates.get("start_date"), dates.get("target_date")
    if start is not None and target is not None and target < start:
        fail(
            "target_date",
            "Target date must be on or after the start date.",
        )

    if errors or name is None:  # name is None always records an error
        raise ProjectValidationError(errors)

    return ProjectData(
        name=name,
        start_date=start,
        target_date=target,
        **cleaned_choices,
    )


def create_project(raw: Mapping[str, object]) -> Project:
    """Validate raw input and save it as a new project.

    Raises:
        ProjectValidationError: If validation fails or the name is already taken.
    """
    data = validate_project(raw)
    project = Project(**_fields(data))
    db.session.add(project)
    _commit_or_name_error()
    return project


def create_projects(raws: Sequence[Mapping[str, object]]) -> list[Project]:
    """Validate several projects and save them all in one transaction.

    Every input is validated before anything is added, and names must also be
    unique among the inputs. Either every project is saved or none is.

    Raises:
        ProjectValidationError: For the first input that fails, or if the commit
            fails; nothing is saved in either case.
    """
    batch = [validate_project(raw) for raw in raws]
    folded = [data.name.casefold() for data in batch]
    if len(set(folded)) != len(folded):
        raise ProjectValidationError({"name": [NAME_TAKEN_MESSAGE]})
    projects = [Project(**_fields(data)) for data in batch]
    db.session.add_all(projects)
    try:
        _commit_or_name_error()
    except Exception:
        # Any other database error: drop the pending projects so none are saved.
        db.session.rollback()
        raise
    return projects


def update_project(project: Project, raw: Mapping[str, object]) -> Project:
    """Validate raw input and save it over an existing project's fields.

    The project may keep its own name. On failure nothing is changed.

    Raises:
        ProjectValidationError: If validation fails or the name is already taken.
    """
    data = validate_project(raw, exclude_id=project.id)
    for field, value in _fields(data).items():
        setattr(project, field, value)
    _commit_or_name_error()
    return project


def delete_project(project: Project) -> None:
    """Permanently delete a project."""
    db.session.delete(project)
    db.session.commit()


def _fields(data: ProjectData) -> dict[str, object]:
    """Return the cleaned values as model keyword arguments."""
    return {
        "name": data.name,
        "category": data.category,
        "medium": data.medium,
        "priority": data.priority,
        "status": data.status,
        "start_date": data.start_date,
        "target_date": data.target_date,
    }


def _commit_or_name_error() -> None:
    """Commit, turning a unique-index violation into a name field error.

    The only unique constraint on projects is the case-insensitive name index, which
    backstops ``_name_taken`` if another write lands between the check and the commit.
    """
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ProjectValidationError({"name": [NAME_TAKEN_MESSAGE]}) from None


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


# --- project list ----------------------------------------------------------

Direction = Literal["asc", "desc"]

SORT_COLUMNS: tuple[str, ...] = (
    "name",
    "category",
    "medium",
    "priority",
    "status",
    "start_date",
    "target_date",
)
DEFAULT_SORT = "priority"
# Every column starts ascending except priority, which starts High first.
DEFAULT_DIRECTIONS: dict[str, Direction] = {"priority": "desc"}


def default_direction(sort: str) -> Direction:
    """Return the direction a column sorts in when first chosen."""
    return DEFAULT_DIRECTIONS.get(sort, "asc")


@dataclass(frozen=True)
class ListOptions:
    """Filters and sort order for the main project list.

    A ``None`` filter means "any value". Finished projects (``FINISHED_STATUSES``)
    are hidden unless ``show_finished`` is set or ``status`` names one explicitly.
    """

    category: str | None = None
    medium: str | None = None
    priority: str | None = None
    status: str | None = None
    show_finished: bool = False
    sort: str = DEFAULT_SORT
    # None means the sort column's own default direction (see default_direction).
    direction: Direction | None = None

    def __post_init__(self) -> None:
        """Fill in the sort column's default direction when none was given."""
        if self.direction is None:
            object.__setattr__(self, "direction", default_direction(self.sort))

    @property
    def hides_finished(self) -> bool:
        """Return True if finished projects are being left out of the list."""
        return not self.show_finished and self.status is None

    def replace(self, **changes: object) -> "ListOptions":
        """Return a copy with some options changed."""
        return dataclasses.replace(self, **changes)

    def query_args(self) -> dict[str, str]:
        """Return query-string arguments that reproduce these options.

        Defaults are left out so the plain list stays at ``/``.
        """
        args = {
            field: value
            for field in CHOICE_FIELDS
            if (value := getattr(self, field)) is not None
        }
        if self.show_finished:
            args["show_finished"] = "1"
        if (self.sort, self.direction) != (
            DEFAULT_SORT,
            default_direction(DEFAULT_SORT),
        ):
            args["sort"] = self.sort
            args["dir"] = self.direction
        return args


def parse_list_options(args: Mapping[str, str]) -> ListOptions:
    """Build list options from query-string arguments.

    Unknown or invalid values are ignored and the default is used instead, so a
    hand-edited or stale URL still shows a list rather than an error. Accepted
    arguments: ``category``, ``medium``, ``priority``, ``status`` (an allowed value),
    ``show_finished`` (``1``), ``sort`` (a name in ``SORT_COLUMNS``) and ``dir``
    (``asc`` or ``desc``; defaults to the column's own default direction).
    """
    filters = {
        field: value if (value := args.get(field)) in allowed else None
        for field, allowed in CHOICE_FIELDS.items()
    }
    sort = args.get("sort")
    if sort not in SORT_COLUMNS:
        sort = DEFAULT_SORT
    direction = args.get("dir")
    if direction != "asc" and direction != "desc":
        direction = None
    return ListOptions(
        **filters,
        show_finished=args.get("show_finished") == "1",
        sort=sort,
        direction=direction,
    )


def project_list_query(options: ListOptions) -> Select[tuple[Project]]:
    """Return the SELECT for the main project list.

    Filters combine with AND. Priority and status sort by their position in
    ``project_tracker.choices`` (descending priority puts High first); names sort
    ignoring case; empty values sort last in both directions. Ties are broken by
    name, then id, so the order is stable.
    """
    query = select(Project)
    for field in CHOICE_FIELDS:
        value = getattr(options, field)
        if value is not None:
            query = query.where(getattr(Project, field) == value)
    if options.hides_finished:
        query = query.where(Project.status.not_in(choices.FINISHED_STATUSES))

    key = _sort_key(options.sort)
    ordered = key.desc() if options.direction == "desc" else key.asc()
    name_key = func.casefold(Project.name)
    # "key IS NULL" is 0 for values and 1 for empties, so empties always come last.
    return query.order_by(key.is_(None), ordered, name_key, Project.id)


def list_projects(options: ListOptions) -> list[Project]:
    """Return the projects matching ``options``, in display order."""
    return list(db.session.scalars(project_list_query(options)))


def count_projects() -> int:
    """Return how many projects exist, ignoring any filters."""
    return db.session.scalar(select(func.count(Project.id))) or 0


def _sort_key(sort: str) -> ColumnElement[object]:
    """Return the SQL expression a list column sorts by."""
    if sort == "name":
        return func.casefold(Project.name)
    if sort == "priority":
        # Rank by importance so that larger means more important: High sorts last
        # ascending and first descending. Unknown values rank NULL (always last).
        ranks = {
            value: len(choices.PRIORITIES) - i
            for i, value in enumerate(choices.PRIORITIES)
        }
        return case(ranks, value=Project.priority)
    if sort == "status":
        ranks = {value: i for i, value in enumerate(choices.STATUSES)}
        return case(ranks, value=Project.status)
    return getattr(Project, sort)
