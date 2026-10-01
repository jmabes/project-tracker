"""Import pages: upload a spreadsheet, preview every row, then confirm.

Uploading only parses and checks the file; nothing is written and the file is not
kept. The preview page sends the valid rows back with the confirm request, which
checks them again and saves them all in one transaction.
"""

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.wrappers import Response

from project_tracker.importer.confirm import ImportChangedError, save_rows
from project_tracker.importer.parsers import (
    ALLOWED_EXTENSIONS,
    ImportFileError,
    parse_upload,
)
from project_tracker.importer.preview import (
    COLUMNS,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    Preview,
    decode_rows,
    display_value,
    encode_rows,
    preview_sheet,
)
from project_tracker.projects import COLUMN_LABELS

bp = Blueprint("imports", __name__, url_prefix="/import")

# Form field names for the uploaded file and the rows carried to confirm.
FILE_FIELD = "file"
ROWS_FIELD = "rows"

CHANGED_MESSAGE = (
    "Something changed since the preview, so nothing was imported. "
    "Check the rows below and confirm again."
)


@bp.get("/")
def upload_form() -> str:
    """Show the upload form."""
    return _render_upload()


@bp.post("/")
def upload() -> str:
    """Parse and check an uploaded file, then show the preview. Writes nothing."""
    file = request.files.get(FILE_FIELD)
    if file is None or not file.filename:
        return _render_upload(error="Choose a file to import.")
    try:
        preview = preview_sheet(parse_upload(file.filename, file.stream))
    except ImportFileError as exc:
        return _render_upload(error=str(exc))
    finally:
        # Werkzeug also closes uploads when the request ends; closing here frees
        # any temporary file as soon as the rows are in memory.
        file.close()
    return _render_preview(preview, filename=file.filename)


@bp.post("/confirm")
def confirm() -> Response | str:
    """Check the previewed rows again and save them all, or show what changed."""
    try:
        rows = decode_rows(request.form.get(ROWS_FIELD, ""))
    except ImportFileError as exc:
        flash(str(exc), "error")
        return redirect(url_for(".upload_form"))
    try:
        projects = save_rows(rows)
    except ImportChangedError as exc:
        return _render_preview(exc.preview, notice=CHANGED_MESSAGE)
    count = len(projects)
    flash(f"Imported {count} project{'' if count == 1 else 's'}.")
    return redirect(url_for("projects.index"))


def request_entity_too_large(error: RequestEntityTooLarge) -> tuple[str, int]:
    """Show a friendly page when an upload is over the size limit."""
    return render_template("errors/413.html", limit=_upload_limit()), 413


def _render_upload(error: str | None = None) -> str:
    """Render the upload page, with a file-level error if there is one."""
    return render_template(
        "imports/upload.html",
        error=error,
        accept=",".join(ALLOWED_EXTENSIONS),
        extensions=ALLOWED_EXTENSIONS,
        required_columns=REQUIRED_COLUMNS,
        optional_columns=OPTIONAL_COLUMNS,
        limit=_upload_limit(),
        file_field=FILE_FIELD,
    )


def _render_preview(
    preview: Preview, *, filename: str | None = None, notice: str | None = None
) -> str:
    """Render the preview table and, if any row is valid, the confirm form."""
    return render_template(
        "imports/preview.html",
        preview=preview,
        filename=filename,
        notice=notice,
        columns=COLUMNS,
        labels=COLUMN_LABELS,
        rows_field=ROWS_FIELD,
        payload=encode_rows(preview) if preview.valid_rows else None,
        display_value=display_value,
    )


def _upload_limit() -> str:
    """Return the upload size limit for display, e.g. ``2 MB``."""
    limit = current_app.config.get("MAX_CONTENT_LENGTH")
    if not limit:
        return "no limit"
    return f"{limit / (1024 * 1024):g} MB"
