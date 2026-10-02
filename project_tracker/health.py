"""Health check endpoint used to verify a deployment is serving requests."""

from flask import Blueprint, current_app
from sqlalchemy.exc import SQLAlchemyError

from project_tracker.extensions import db
from project_tracker.models import Project

bp = Blueprint("health", __name__)


@bp.get("/healthz")
def healthz() -> tuple[dict[str, str], int]:
    """Return 200 if the app can read the projects table, otherwise 503.

    Reading the table (not just ``SELECT 1``) also catches a ``DATABASE_URL``
    that points at an empty or unmigrated database, and file permission
    problems. The error detail goes to the log, never to the response.
    """
    try:
        db.session.execute(db.select(Project.id).limit(1)).first()
    except SQLAlchemyError:
        current_app.logger.exception("Health check database query failed")
        return {"status": "error", "database": "unavailable"}, 503
    return {"status": "ok"}, 200
