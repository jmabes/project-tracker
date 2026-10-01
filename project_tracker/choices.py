"""Allowed values for a project's choice fields.

This is the only place they are defined. They are stored as plain validated strings,
not database enums, so adding a value is a one-line change here with no migration.
"""

CATEGORIES: tuple[str, ...] = ("Tech", "Finance", "Home")
MEDIUMS: tuple[str, ...] = ("Coding", "Hardware", "Research", "DIY")
PRIORITIES: tuple[str, ...] = ("High", "Medium", "Low")
STATUSES: tuple[str, ...] = (
    "Not started",
    "In progress",
    "On hold",
    "Done",
    "Abandoned",
)
