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
from project_tracker.services import (
    ProjectValidationError,
    create_project,
    delete_project,
    update_project,
)

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


@bp.get("/projects/<int:project_id>/edit")
def edit(project_id: int) -> str:
    """Show the edit form filled with the project's saved values."""
    project = db.get_or_404(Project, project_id)
    return _render_edit_form(project, ProjectForm(obj=project))


@bp.post("/projects/<int:project_id>/edit")
def update(project_id: int) -> Response | str:
    """Save changes to a project, or re-render the form with per-field errors."""
    project = db.get_or_404(Project, project_id)
    # Built from the request only: with obj=project, a field missing from the POST
    # would silently keep its saved value instead of failing validation.
    form = ProjectForm()
    try:
        update_project(project, form.raw_input())
    except ProjectValidationError as exc:
        form.add_errors(exc.errors)
        return _render_edit_form(project, form)
    flash(f"Saved “{project.name}”.")
    return redirect(url_for(".detail", project_id=project.id))


@bp.get("/projects/<int:project_id>/delete")
def confirm_delete(project_id: int) -> str:
    """Ask for confirmation before deleting a project."""
    project = db.get_or_404(Project, project_id)
    return render_template("projects/delete.html", project=project)


@bp.post("/projects/<int:project_id>/delete")
def delete(project_id: int) -> Response:
    """Delete a project after the user confirmed it."""
    project = db.get_or_404(Project, project_id)
    name = project.name
    delete_project(project)
    flash(f"Deleted “{name}”.")
    return redirect(url_for(".index"))


def _render_create_form(form: ProjectForm) -> str:
    """Render the form used to create a project."""
    return _render_form(
        form,
        heading="New project",
        action=url_for(".create"),
        submit_label="Create project",
        cancel_url=url_for(".index"),
    )


def _render_edit_form(project: Project, form: ProjectForm) -> str:
    """Render the form used to edit a project."""
    return _render_form(
        form,
        heading=f"Edit “{project.name}”",
        action=url_for(".update", project_id=project.id),
        submit_label="Save changes",
        cancel_url=url_for(".detail", project_id=project.id),
    )


def _render_form(
    form: ProjectForm, *, heading: str, action: str, submit_label: str, cancel_url: str
) -> str:
    """Render the shared project form page."""
    return render_template(
        "projects/form.html",
        form=form,
        field_names=PROJECT_FIELDS,
        heading=heading,
        action=action,
        submit_label=submit_label,
        cancel_url=cancel_url,
    )
