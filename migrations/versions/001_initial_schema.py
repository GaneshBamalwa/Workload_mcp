"""Initial migration - create base tables.

Revision ID: 001_initial_schema
Revises:
Create Date: 2024-01-20 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial schema."""
    # Create organizations table
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_org_slug"),
    )
    op.create_index("idx_org_slug", "organizations", ["slug"])

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_user_email"),
        sa.UniqueConstraint("username", name="uq_user_username"),
    )
    op.create_index("idx_user_email", "users", ["email"])
    op.create_index("idx_user_org", "users", ["organization_id"])

    # Create tokens table
    op.create_table(
        "tokens",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("connector_type", sa.String(50), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_type", sa.String(50), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_token_user", "tokens", ["user_id"])
    op.create_index("idx_token_connector", "tokens", ["connector_type"])

    # Create integrations table
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("connector_type", sa.String(50), nullable=False),
        sa.Column("external_user_id", sa.String(255), nullable=True),
        sa.Column("external_workspace_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("sync_cursor", sa.String(500), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "connector_type", name="uq_user_connector"),
    )
    op.create_index("idx_integration_org", "integrations", ["organization_id"])
    op.create_index("idx_integration_user", "integrations", ["user_id"])

    # Create work_items table
    op.create_table(
        "work_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("urgency", sa.Float(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("estimated_effort_minutes", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("stakeholders", sa.JSON(), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("requires_response", sa.Boolean(), nullable=False),
        sa.Column("requires_deep_work", sa.Boolean(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_workitem_user", "work_items", ["user_id"])
    op.create_index("idx_workitem_source", "work_items", ["source"])
    op.create_index("idx_workitem_status", "work_items", ["status"])
    op.create_index("idx_workitem_due_date", "work_items", ["due_date"])

    # Create schedules table
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("scheduled_date", sa.DateTime(), nullable=False),
        sa.Column("work_items", sa.JSON(), nullable=False),
        sa.Column("blocks", sa.JSON(), nullable=False),
        sa.Column("focus_blocks", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("is_locked", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_schedule_user_date", "schedules", ["user_id", "scheduled_date"])

    # Create sync_states table
    op.create_table(
        "sync_states",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("connector_type", sa.String(50), nullable=False),
        sa.Column("last_full_sync", sa.DateTime(), nullable=True),
        sa.Column("last_incremental_sync", sa.DateTime(), nullable=True),
        sa.Column("sync_cursor", sa.String(500), nullable=True),
        sa.Column("next_sync_time", sa.DateTime(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "connector_type", name="uq_sync_state"),
    )
    op.create_index("idx_syncstate_user", "sync_states", ["user_id"])

    # Create audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_user", "audit_logs", ["user_id"])
    op.create_index("idx_audit_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_index("idx_audit_action", "audit_logs", ["action"])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("audit_logs")
    op.drop_table("sync_states")
    op.drop_table("schedules")
    op.drop_table("work_items")
    op.drop_table("integrations")
    op.drop_table("tokens")
    op.drop_table("users")
    op.drop_table("organizations")
