"""Database models."""

from datetime import UTC, date, datetime

from sqlalchemy import Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from project_tracker.extensions import db

NAME_MAX_LENGTH = 200


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (SQLite stores no zone)."""
    return datetime.now(UTC).replace(tzinfo=None)


class Project(db.Model):
    """A tracked personal project.

    Field rules live in ``project_tracker.services``, not here. Choice fields are plain
    strings so allowed values can change without a migration.
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    category: Mapped[str] = mapped_column(String(50))
    medium: Mapped[str] = mapped_column(String(50))
    priority: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    start_date: Mapped[date | None]
    estimated_completion_date: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        """Return a debugging representation."""
        return f"<Project {self.id} {self.name!r}>"


# Backstop for case-insensitive uniqueness. SQLite's lower() only folds ASCII, so the
# service layer also checks with str.casefold() to catch non-ASCII names.
Index("uq_projects_name_lower", func.lower(Project.name), unique=True)
