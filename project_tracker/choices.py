"""Allowed values for a project's choice fields.

This is the only place they are defined. They are stored as plain validated strings,
not database enums, so adding a value is a one-line change here with no migration.

Order matters: the project list sorts priority and status by their position in these
tuples, not alphabetically.
"""

CATEGORIES: tuple[str, ...] = ("Tech", "Finance", "Home")
MEDIUMS: tuple[str, ...] = ("Coding", "Hardware", "Research", "DIY")
# Most important first.
PRIORITIES: tuple[str, ...] = ("High", "Medium", "Low")
# Workflow order: a project usually moves left to right.
STATUSES: tuple[str, ...] = (
    "Not started",
    "In progress",
    "On hold",
    "Done",
    "Abandoned",
)
# Statuses the main list hides unless the user asks to see finished projects.
FINISHED_STATUSES: tuple[str, ...] = ("Done", "Abandoned")
