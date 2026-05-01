"""audit log interface fields

Revision ID: 0005_audit_log_interface
Revises: 0004_courthouse_memory
Create Date: 2026-05-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_audit_log_interface"
down_revision: str | None = "0004_courthouse_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("actor", sa.String(length=200), nullable=True))
    op.add_column(
        "audit_events", sa.Column("action_class", sa.String(length=40), nullable=True)
    )
    op.add_column("audit_events", sa.Column("metadata_json", sa.JSON(), nullable=True))
    op.add_column("audit_events", sa.Column("status", sa.String(length=40), nullable=True))
    op.add_column(
        "audit_events", sa.Column("correlation_id", sa.String(length=64), nullable=True)
    )
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_correlation_id", table_name="audit_events")
    op.drop_column("audit_events", "correlation_id")
    op.drop_column("audit_events", "status")
    op.drop_column("audit_events", "metadata_json")
    op.drop_column("audit_events", "action_class")
    op.drop_column("audit_events", "actor")
