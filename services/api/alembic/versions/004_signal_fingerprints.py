"""add signal fingerprints

Revision ID: 004_signal_fingerprints
Revises: 003_analysis_insights
Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSON

revision: str = "004_signal_fingerprints"
down_revision: Union[str, None] = "003_analysis_insights"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent for databases that already created the table via create_all.
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("signal_fingerprints"):
        op.create_table(
            "signal_fingerprints",
            sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "project_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("analysis_projects.id"),
                nullable=False,
            ),
            sa.Column(
                "recording_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("recordings.id"),
                nullable=False,
            ),
            sa.Column("version", sa.String(20), nullable=False),
            sa.Column("dimensions", sa.Integer(), nullable=False),
            sa.Column("vector_json", JSON, nullable=False),
            sa.Column("embedding_json", JSON),
            sa.Column("features_json", JSON),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        )

    index_names = {i["name"] for i in insp.get_indexes("signal_fingerprints")}
    for name, columns, unique in (
        ("ix_signal_fingerprints_project_id", ["project_id"], True),
        ("ix_signal_fingerprints_recording_id", ["recording_id"], False),
        ("ix_signal_fingerprints_version", ["version"], False),
    ):
        if name not in index_names:
            op.create_index(name, "signal_fingerprints", columns, unique=unique)


def downgrade() -> None:
    for name in (
        "ix_signal_fingerprints_version",
        "ix_signal_fingerprints_recording_id",
        "ix_signal_fingerprints_project_id",
    ):
        op.drop_index(name, table_name="signal_fingerprints")
    op.drop_table("signal_fingerprints")
