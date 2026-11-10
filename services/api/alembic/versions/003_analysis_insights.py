"""add analysis insights

Revision ID: 003_analysis_insights
Revises: 002_enforce_not_null
Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSON

revision: str = "003_analysis_insights"
down_revision: Union[str, None] = "002_enforce_not_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: some databases got this table via create_all before the
    # migration existed, leaving alembic_version behind.
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("analysis_insights"):
        op.create_table(
            "analysis_insights",
            sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "project_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("analysis_projects.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("model_name", sa.String(120), nullable=False),
            sa.Column("prompt_version", sa.String(40), nullable=False),
            sa.Column("status", sa.String(20), server_default="queued", nullable=False, index=True),
            sa.Column("response_json", JSON),
            sa.Column("tool_trace_json", JSON),
            sa.Column("citations_json", JSON),
            sa.Column("error_message", sa.Text),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )
    index_names = {i["name"] for i in insp.get_indexes("analysis_insights")}
    if "ix_analysis_insights_project_created" not in index_names:
        op.create_index(
            "ix_analysis_insights_project_created",
            "analysis_insights",
            ["project_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_analysis_insights_project_created", table_name="analysis_insights")
    op.drop_table("analysis_insights")
