"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSON

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("role", sa.String(50), server_default="user"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "recordings",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False, index=True),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("file_format", sa.String(50), nullable=False),
        sa.Column("uploaded_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("status", sa.String(50), server_default="uploaded", index=True),
        sa.Column("duration_seconds", sa.Float),
        sa.Column("total_samples", sa.BigInteger),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_recordings_user_status", "recordings", ["uploaded_by", "status"])

    op.create_table(
        "recording_metadata",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("recording_id", PG_UUID(as_uuid=True), sa.ForeignKey("recordings.id"), nullable=False),
        sa.Column("sample_rate", sa.Float),
        sa.Column("center_frequency", sa.Float),
        sa.Column("data_type", sa.String(50)),
        sa.Column("iq_layout", sa.String(50)),
        sa.Column("endian", sa.String(20)),
        sa.Column("channel_count", sa.Integer, server_default=sa.text("1")),
        sa.Column("sample_width", sa.String(50)),
        sa.Column("is_complex", sa.Boolean, server_default=sa.text("false")),
        sa.Column("metadata_source", sa.String(50)),
        sa.Column("metadata_confidence", sa.Float),
        sa.Column("raw_metadata_json", JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "analysis_projects",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("recording_id", PG_UUID(as_uuid=True), sa.ForeignKey("recordings.id"), nullable=False, index=True),
        sa.Column("created_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("status", sa.String(50), server_default="active", index=True),
        sa.Column("selected_start_sample", sa.BigInteger),
        sa.Column("selected_end_sample", sa.BigInteger),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "parameter_estimates",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", PG_UUID(as_uuid=True), sa.ForeignKey("analysis_projects.id"), nullable=False, index=True),
        sa.Column("parameter_name", sa.String(255), nullable=False),
        sa.Column("value_json", JSON, nullable=False),
        sa.Column("value_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float),
        sa.Column("evidence_json", JSON),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "artifacts",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", PG_UUID(as_uuid=True), sa.ForeignKey("analysis_projects.id"), nullable=False, index=True),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("metadata_json", JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("parameter_estimates")
    op.drop_table("analysis_projects")
    op.drop_table("recording_metadata")
    op.drop_index("ix_recordings_user_status", table_name="recordings")
    op.drop_table("recordings")
    op.drop_table("users")
