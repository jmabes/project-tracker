"""Health check endpoint used to verify a deployment is serving requests."""

from flask import Blueprint

bp = Blueprint("health", __name__)


@bp.get("/healthz")
def healthz() -> tuple[dict[str, str], int]:
    """Return 200 with a small JSON body when the app is up."""
    return {"status": "ok"}, 200
