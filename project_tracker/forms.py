"""Web forms. They only collect input; validation lives in ``services``.

The forms declare no validators and views never call ``validate()``. CSRF is
checked for every POST by the app-wide ``CSRFProtect`` extension.
"""

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField

from project_tracker import choices

PLACEHOLDER = ("", "Select…")

# Plain text fields rendered as <input type="date">. WTForms' DateField would parse
# the value itself and add its own error; we pass the raw text to the service.
DATE_INPUT = {"type": "date"}

PROJECT_FIELDS = (
    "name",
    "category",
    "medium",
    "priority",
    "status",
    "start_date",
    "target_date",
)


def _options(values: tuple[str, ...]) -> list[tuple[str, str]]:
    """Return select options for the allowed values, after a blank placeholder."""
    return [PLACEHOLDER, *((value, value) for value in values)]


class ProjectForm(FlaskForm):
    """Collects a project's user-facing fields."""

    name = StringField("Name")
    category = SelectField("Category", choices=_options(choices.CATEGORIES))
    medium = SelectField("Medium", choices=_options(choices.MEDIUMS))
    priority = SelectField("Priority", choices=_options(choices.PRIORITIES))
    status = SelectField("Status", choices=_options(choices.STATUSES))
    start_date = StringField("Start date", render_kw=DATE_INPUT)
    target_date = StringField("Target date", render_kw=DATE_INPUT)

    def raw_input(self) -> dict[str, object]:
        """Return the submitted values, unvalidated, keyed by field name."""
        return {field: self[field].data for field in PROJECT_FIELDS}

    def add_errors(self, errors: dict[str, list[str]]) -> None:
        """Attach per-field messages from a ProjectValidationError."""
        for field, messages in errors.items():
            self[field].errors = list(messages)
