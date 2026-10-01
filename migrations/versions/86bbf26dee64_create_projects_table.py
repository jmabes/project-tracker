"""Create projects table.

Revision ID: 86bbf26dee64
Revises:
Create Date: 2026-10-01 18:40:29.241342

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "86bbf26dee64"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("medium", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("estimated_completion_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Added by hand: autogenerate cannot reflect expression indexes on SQLite.
    op.create_index(
        "uq_projects_name_lower",
        "projects",
        [sa.text("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_projects_name_lower", table_name="projects")
    op.drop_table("projects")
