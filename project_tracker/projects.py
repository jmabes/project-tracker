"""Project pages: list, detail, create, edit and delete.

Views only collect input and render results; every write goes through
``project_tracker.services``.
"""

from flask import Blueprint, render_template
from sqlalchemy import select

from project_tracker.extensions import db
from project_tracker.models import Project

bp = Blueprint("projects", __name__)


@bp.get("/")
def index() -> str:
    """List every project's name, linking to its detail page.

    Temporary: Milestone 3 replaces this with the sortable, filterable list.
    """
    projects = sorted(
        db.session.scalars(select(Project)), key=lambda p: p.name.casefold()
    )
    return render_template("projects/index.html", projects=projects)


@bp.get("/projects/<int:project_id>")
def detail(project_id: int) -> str:
    """Show one project, whatever its status."""
    project = db.get_or_404(Project, project_id)
    return render_template("projects/detail.html", project=project)
