"""Rename estimated_completion_date to target_date.

Revision ID: 4ed531acccd0
Revises: 86bbf26dee64
Create Date: 2026-10-02 02:04:13.946112

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "4ed531acccd0"
down_revision = "86bbf26dee64"
branch_labels = None
depends_on = None

# A plain alter_column, not batch mode: on SQLite Alembic emits
# "ALTER TABLE ... RENAME COLUMN", which renames in place and keeps the data and
# the uq_projects_name_lower expression index. Batch mode would rebuild the table
# from reflection, and SQLite can't reflect that index, so it would be lost.


def upgrade() -> None:
    op.alter_column(
        "projects",
        "estimated_completion_date",
        new_column_name="target_date",
        existing_type=sa.Date(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "projects",
        "target_date",
        new_column_name="estimated_completion_date",
        existing_type=sa.Date(),
        existing_nullable=True,
    )
