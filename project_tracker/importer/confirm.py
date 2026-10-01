"""Save confirmed import rows, checking them again first.

The rows come back from the preview page, so they are validated again. Another
project may also have been added since the preview was shown. If any row no
longer passes, nothing is saved and the caller gets a fresh preview to show.
"""

from collections.abc import Sequence

from project_tracker.importer.preview import Preview, SourceRow, build_preview
from project_tracker.models import Project
from project_tracker.services import ProjectValidationError, create_projects


class ImportChangedError(Exception):
    """Raised when confirmed rows no longer all pass; ``preview`` shows why."""

    def __init__(self, preview: Preview) -> None:
        """Store the fresh preview."""
        super().__init__("The import rows changed since the preview.")
        self.preview = preview


def save_rows(rows: Sequence[SourceRow]) -> list[Project]:
    """Check the rows again and save them all in one transaction.

    Raises:
        ImportChangedError: If any row is no longer valid, or saving fails.
            Nothing is saved.
    """
    preview = build_preview(rows)
    if not preview.all_valid:
        raise ImportChangedError(preview)
    try:
        return create_projects([row.values for row in preview.rows])
    except ProjectValidationError:
        raise ImportChangedError(build_preview(rows)) from None
