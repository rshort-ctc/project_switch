"""phase 12 approval context

Revision ID: 0002_phase_12
Revises: 0001_phase_2
Create Date: 2026-04-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_phase_12"
down_revision: str | None = "0001_phase_2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column(
                "requested_action",
                sa.String(length=120),
                nullable=False,
                server_default="unspecified",
            )
        )
        batch_op.add_column(
            sa.Column(
                "risk_level",
                sa.String(length=40),
                nullable=False,
                server_default="medium",
            )
        )
        batch_op.add_column(sa.Column("diff_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("command", sa.String(length=240), nullable=True))
        batch_op.add_column(sa.Column("denial_reason", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_approval_requests_task_id_tasks",
            "tasks",
            ["task_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.drop_constraint("fk_approval_requests_task_id_tasks", type_="foreignkey")
        batch_op.drop_column("denial_reason")
        batch_op.drop_column("command")
        batch_op.drop_column("diff_summary")
        batch_op.drop_column("risk_level")
        batch_op.drop_column("requested_action")
        batch_op.drop_column("task_id")
