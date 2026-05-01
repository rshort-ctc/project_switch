"""approval queue skeleton fields

Revision ID: 0006_approval_queue_skeleton
Revises: 0005_audit_log_interface
Create Date: 2026-05-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_approval_queue_skeleton"
down_revision: str | None = "0005_audit_log_interface"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.alter_column(
            "agent_run_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.alter_column(
            "requested_by_user_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.add_column(sa.Column("requested_by", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("action", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("action_class", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("target_type", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("target_id", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("proposed_payload", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("risk_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("review_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("audit_event_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_approval_requests_audit_event_id_audit_events",
            "audit_events",
            ["audit_event_id"],
            ["id"],
        )

    op.execute(
        sa.text(
            """
            UPDATE approval_requests
            SET requested_by = COALESCE(requested_by, requested_by_user_id),
                action = COALESCE(action, requested_action),
                target_type = COALESCE(target_type, 'agent_run'),
                target_id = COALESCE(target_id, agent_run_id),
                proposed_payload = COALESCE(proposed_payload, '{}'),
                risk_summary = COALESCE(risk_summary, reason)
            """
        )
    )
    op.create_index(
        "ix_approval_requests_target_status",
        "approval_requests",
        ["target_type", "target_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_approval_requests_target_status", table_name="approval_requests")
    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.drop_constraint(
            "fk_approval_requests_audit_event_id_audit_events",
            type_="foreignkey",
        )
        batch_op.drop_column("audit_event_id")
        batch_op.drop_column("review_note")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("risk_summary")
        batch_op.drop_column("proposed_payload")
        batch_op.drop_column("target_id")
        batch_op.drop_column("target_type")
        batch_op.drop_column("action_class")
        batch_op.drop_column("action")
        batch_op.drop_column("requested_by")
        batch_op.alter_column(
            "requested_by_user_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.alter_column(
            "agent_run_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
