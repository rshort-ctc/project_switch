"""courthouse governed memory foundation

Revision ID: 0004_courthouse_memory
Revises: 0003_storage
Create Date: 2026-05-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_courthouse_memory"
down_revision: str | None = "0003_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "evidence_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("drawer_id", sa.String(length=120), nullable=True),
        sa.Column("source_uri", sa.String(length=1024), nullable=True),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("adapter_name", sa.String(length=160), nullable=True),
        sa.Column("adapter_version", sa.String(length=80), nullable=True),
        sa.Column("transform_chain", sa.JSON(), nullable=True),
        sa.Column("privacy_class", sa.String(length=40), nullable=False),
        sa.Column("exposure", sa.String(length=40), nullable=False),
        sa.Column("workspace", sa.String(length=200), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_table(
        "claims",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=40), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=True),
        sa.Column("predicate", sa.String(length=160), nullable=True),
        sa.Column("object", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(length=300), nullable=True),
        sa.Column("workspace", sa.String(length=200), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extracted_from_evidence_id", sa.String(length=36), nullable=True),
        sa.Column("extractor", sa.String(length=160), nullable=True),
        sa.Column("extractor_version", sa.String(length=80), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["extracted_from_evidence_id"], ["evidence_items.id"]),
    )
    op.create_table(
        "verdicts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("claim_id", sa.String(length=36), nullable=False),
        sa.Column("verdict", sa.String(length=40), nullable=False),
        sa.Column("authority_level", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("decided_by", sa.String(length=160), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("supersedes_claim_id", sa.String(length=36), nullable=True),
        sa.Column("contradicts_claim_id", sa.String(length=36), nullable=True),
        sa.Column("appeal_status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["supersedes_claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["contradicts_claim_id"], ["claims.id"]),
    )
    op.create_table(
        "canonical_state",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("workspace", sa.String(length=200), nullable=True),
        sa.Column("authority_level", sa.String(length=40), nullable=False),
        sa.Column("source_verdict_id", sa.String(length=36), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_verdict_id"], ["verdicts.id"]),
        sa.UniqueConstraint("workspace", "key", name="uq_canonical_state_workspace_key"),
    )
    op.create_table(
        "open_loops",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("workspace", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("blocking_question", sa.Text(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("source_evidence_id", sa.String(length=36), nullable=True),
        sa.Column("source_verdict_id", sa.String(length=36), nullable=True),
        sa.Column("stale_after", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_evidence_id"], ["evidence_items.id"]),
        sa.ForeignKeyConstraint(["source_verdict_id"], ["verdicts.id"]),
    )
    op.create_table(
        "context_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("workspace", sa.String(length=200), nullable=True),
        sa.Column("mode", sa.String(length=80), nullable=True),
        sa.Column("compiler_version", sa.String(length=80), nullable=False),
        sa.Column("token_budget", sa.Integer(), nullable=True),
        sa.Column("included_json", sa.JSON(), nullable=False),
        sa.Column("excluded_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_evidence_items_workspace", "evidence_items", ["workspace"])
    op.create_index("ix_evidence_items_content_hash", "evidence_items", ["content_hash"])
    op.create_index("ix_claims_workspace_status", "claims", ["workspace", "status"])
    op.create_index(
        "ix_claims_subject_scope",
        "claims",
        ["workspace", "subject", "predicate", "scope"],
    )
    op.create_index("ix_verdicts_claim_id", "verdicts", ["claim_id"])
    op.create_index("ix_verdicts_authority", "verdicts", ["authority_level"])
    op.create_index("ix_canonical_state_workspace_key", "canonical_state", ["workspace", "key"])
    op.create_index("ix_open_loops_workspace_status", "open_loops", ["workspace", "status"])
    op.create_index(
        "ix_context_snapshots_workspace_created",
        "context_snapshots",
        ["workspace", "created_at"],
    )
    op.create_index("ix_context_snapshots_hash", "context_snapshots", ["snapshot_hash"])


def downgrade() -> None:
    op.drop_index("ix_context_snapshots_hash", table_name="context_snapshots")
    op.drop_index("ix_context_snapshots_workspace_created", table_name="context_snapshots")
    op.drop_index("ix_open_loops_workspace_status", table_name="open_loops")
    op.drop_index("ix_canonical_state_workspace_key", table_name="canonical_state")
    op.drop_index("ix_verdicts_authority", table_name="verdicts")
    op.drop_index("ix_verdicts_claim_id", table_name="verdicts")
    op.drop_index("ix_claims_subject_scope", table_name="claims")
    op.drop_index("ix_claims_workspace_status", table_name="claims")
    op.drop_index("ix_evidence_items_content_hash", table_name="evidence_items")
    op.drop_index("ix_evidence_items_workspace", table_name="evidence_items")
    op.drop_table("context_snapshots")
    op.drop_table("open_loops")
    op.drop_table("canonical_state")
    op.drop_table("verdicts")
    op.drop_table("claims")
    op.drop_table("evidence_items")
