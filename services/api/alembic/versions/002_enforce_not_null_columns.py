"""enforce NOT NULL on columns that models already declare required

The initial migration left server-defaulted columns nullable. SQLAlchemy infers
nullable=False for the non-optional `Mapped[...]` annotations, so `alembic
check` reported drift. Backfill any legacy NULLs, then tighten the constraints.

Revision ID: 002_enforce_not_null
Revises: 001_initial
Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002_enforce_not_null"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, backfill expression)
_COLUMNS = [
    ("users", "role", "'user'"),
    ("users", "is_active", "true"),
    ("users", "created_at", "now()"),
    ("users", "updated_at", "now()"),
    ("recordings", "status", "'uploaded'"),
    ("recordings", "created_at", "now()"),
    ("recordings", "updated_at", "now()"),
    ("recording_metadata", "channel_count", "1"),
    ("recording_metadata", "is_complex", "false"),
    ("recording_metadata", "created_at", "now()"),
    ("recording_metadata", "updated_at", "now()"),
    ("analysis_projects", "status", "'active'"),
    ("analysis_projects", "created_at", "now()"),
    ("analysis_projects", "updated_at", "now()"),
    ("parameter_estimates", "created_at", "now()"),
    ("artifacts", "created_at", "now()"),
]


def upgrade() -> None:
    for table, column, expression in _COLUMNS:
        op.execute(f"UPDATE {table} SET {column} = {expression} WHERE {column} IS NULL")
        op.alter_column(table, column, nullable=False)


def downgrade() -> None:
    for table, column, _ in reversed(_COLUMNS):
        op.alter_column(table, column, nullable=True)
