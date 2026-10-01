"""Project pages: list, detail, create, edit and delete.

Views only collect input and render results; every write goes through
``project_tracker.services``.
"""

from flask import Blueprint, flash, redirect, render_template, url_for
from sqlalchemy import select
from werkzeug.wrappers import Response

from project_tracker.extensions import db
from project_tracker.forms import PROJECT_FIELDS, ProjectForm
from project_tracker.models import Project
from project_tracker.services import ProjectValidationError, create_project

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


@bp.get("/projects/new")
def new() -> str:
    """Show an empty form for a new project."""
    return _render_create_form(ProjectForm())


@bp.post("/projects")
def create() -> Response | str:
    """Create a project, or re-render the form with per-field errors."""
    form = ProjectForm()
    try:
        project = create_project(form.raw_input())
    except ProjectValidationError as exc:
        form.add_errors(exc.errors)
        return _render_create_form(form)
    flash(f"Created “{project.name}”.")
    return redirect(url_for(".detail", project_id=project.id))


def _render_create_form(form: ProjectForm) -> str:
    """Render the form used to create a project."""
    return render_template(
        "projects/form.html",
        form=form,
        field_names=PROJECT_FIELDS,
        heading="New project",
        action=url_for(".create"),
        submit_label="Create project",
        cancel_url=url_for(".index"),
    )
