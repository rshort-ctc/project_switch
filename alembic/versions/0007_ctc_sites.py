"""ctc sites domain model

Revision ID: 0007_ctc_sites
Revises: 0006_approval_queue_skeleton
Create Date: 2026-05-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_ctc_sites"
down_revision: str | None = "0006_approval_queue_skeleton"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("site_name", sa.String(length=200), nullable=False),
        sa.Column("facility_type", sa.String(length=120), nullable=False),
        sa.Column("address_line_1", sa.String(length=240), nullable=True),
        sa.Column("address_line_2", sa.String(length=240), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=40), nullable=True),
        sa.Column("zip_code", sa.String(length=20), nullable=True),
        sa.Column("county", sa.String(length=120), nullable=True),
        sa.Column("timezone", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("primary_contact_name", sa.String(length=200), nullable=True),
        sa.Column("primary_contact_email", sa.String(length=320), nullable=True),
        sa.Column("primary_contact_phone", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sites_status", "sites", ["status"])
    op.create_index("ix_sites_city_state", "sites", ["city", "state"])
    op.create_index("ix_sites_site_name", "sites", ["site_name"])


def downgrade() -> None:
    op.drop_index("ix_sites_site_name", table_name="sites")
    op.drop_index("ix_sites_city_state", table_name="sites")
    op.drop_index("ix_sites_status", table_name="sites")
    op.drop_table("sites")
