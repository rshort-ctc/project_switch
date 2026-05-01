"""storage architecture updates

Revision ID: 0003_storage
Revises: 0002_phase_12
Create Date: 2026-04-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_storage"
down_revision: str | None = "0002_phase_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    with op.batch_alter_table("repo_indexes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "vector_collection",
                sa.String(length=120),
                nullable=False,
                server_default="switch_code_chunks",
            )
        )
        batch_op.add_column(
            sa.Column("indexed_file_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("indexed_chunk_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))

    op.create_table(
        "model_calls",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("model_role", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("endpoint", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("request_summary", sa.Text(), nullable=False),
        sa.Column("response_summary", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("request_metadata", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
    )

    op.create_index(
        "ix_repo_indexes_repository_status", "repo_indexes", ["repository_id", "status"]
    )
    op.create_index(
        "ix_repo_indexes_repository_commit", "repo_indexes", ["repository_id", "commit_sha"]
    )
    op.create_index("ix_tasks_repository_status", "tasks", ["repository_id", "status"])
    op.create_index("ix_agent_runs_task_status", "agent_runs", ["task_id", "status"])
    op.create_index("ix_agent_steps_run_status", "agent_steps", ["agent_run_id", "status"])
    op.create_index("ix_tool_calls_step_status", "tool_calls", ["agent_step_id", "status"])
    op.create_index("ix_approval_requests_task_status", "approval_requests", ["task_id", "status"])
    op.create_index(
        "ix_approval_requests_run_status", "approval_requests", ["agent_run_id", "status"]
    )
    op.create_index("ix_patch_artifacts_run_status", "patch_artifacts", ["agent_run_id", "status"])
    op.create_index("ix_validation_runs_run_status", "validation_runs", ["agent_run_id", "status"])
    op.create_index("ix_model_calls_run_status", "model_calls", ["agent_run_id", "status"])
    op.create_index("ix_model_calls_role_model", "model_calls", ["model_role", "model_name"])
    op.create_index("ix_audit_events_subject", "audit_events", ["subject_type", "subject_id"])
    op.create_index(
        "ix_policy_decisions_run_decision", "policy_decisions", ["agent_run_id", "decision"]
    )


def downgrade() -> None:
    op.drop_index("ix_policy_decisions_run_decision", table_name="policy_decisions")
    op.drop_index("ix_audit_events_subject", table_name="audit_events")
    op.drop_index("ix_model_calls_role_model", table_name="model_calls")
    op.drop_index("ix_model_calls_run_status", table_name="model_calls")
    op.drop_index("ix_validation_runs_run_status", table_name="validation_runs")
    op.drop_index("ix_patch_artifacts_run_status", table_name="patch_artifacts")
    op.drop_index("ix_approval_requests_run_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_task_status", table_name="approval_requests")
    op.drop_index("ix_tool_calls_step_status", table_name="tool_calls")
    op.drop_index("ix_agent_steps_run_status", table_name="agent_steps")
    op.drop_index("ix_agent_runs_task_status", table_name="agent_runs")
    op.drop_index("ix_tasks_repository_status", table_name="tasks")
    op.drop_index("ix_repo_indexes_repository_commit", table_name="repo_indexes")
    op.drop_index("ix_repo_indexes_repository_status", table_name="repo_indexes")
    op.drop_table("model_calls")
    with op.batch_alter_table("repo_indexes") as batch_op:
        batch_op.drop_column("error_message")
        batch_op.drop_column("indexed_chunk_count")
        batch_op.drop_column("indexed_file_count")
        batch_op.drop_column("vector_collection")
