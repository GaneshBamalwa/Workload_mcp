"""SQLAlchemy ORM models for database entities."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Organization(Base):
    """Organization entity for multi-tenancy."""

    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    logo_url = Column(String(500), nullable=True)
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = relationship("User", back_populates="organization")
    integrations = relationship("Integration", back_populates="organization")

    __table_args__ = (Index("idx_org_slug", "slug"),)


class User(Base):
    """User entity."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    full_name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)  # None if OAuth only
    avatar_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    role = Column(String(50), default="user")  # admin, manager, user
    timezone = Column(String(50), default="UTC")
    preferences = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="users")
    tokens = relationship("Token", back_populates="user")
    integrations = relationship("Integration", back_populates="user")
    work_items = relationship("WorkItem", back_populates="user")
    schedules = relationship("Schedule", back_populates="user")

    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_org", "organization_id"),
    )


class Token(Base):
    """OAuth and refresh tokens."""

    __tablename__ = "tokens"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    connector_type = Column(String(50), nullable=False)  # google, slack, jira
    access_token = Column(Text, nullable=False)  # Encrypted
    refresh_token = Column(Text, nullable=True)  # Encrypted
    token_type = Column(String(50), default="Bearer")
    expires_at = Column(DateTime, nullable=True)
    scopes = Column(JSON, default=[])
    is_valid = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="tokens")

    __table_args__ = (
        Index("idx_token_user", "user_id"),
        Index("idx_token_connector", "connector_type"),
    )


class Integration(Base):
    """External service integrations."""

    __tablename__ = "integrations"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    connector_type = Column(String(50), nullable=False)  # gmail, slack, jira, calendar
    external_user_id = Column(String(255), nullable=True)
    external_workspace_id = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    sync_enabled = Column(Boolean, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    sync_cursor = Column(String(500), nullable=True)  # For incremental sync
    settings = Column(JSON, default={})
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="integrations")
    user = relationship("User", back_populates="integrations")

    __table_args__ = (
        UniqueConstraint("user_id", "connector_type", name="uq_user_connector"),
        Index("idx_integration_org", "organization_id"),
        Index("idx_integration_user", "user_id"),
    )


class WorkItem(Base):
    """Unified work item from any source."""

    __tablename__ = "work_items"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    source = Column(String(50), nullable=False)  # gmail, slack, jira, calendar
    source_id = Column(String(255), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    urgency = Column(Float, default=0.5)  # 0.0-1.0
    importance = Column(Float, default=0.5)  # 0.0-1.0
    estimated_effort_minutes = Column(Integer, nullable=True)
    due_date = Column(DateTime, nullable=True)
    created_by = Column(String(255), nullable=True)
    stakeholders = Column(JSON, default=[])  # List of emails/users
    dependencies = Column(JSON, default=[])  # List of work item IDs
    requires_response = Column(Boolean, default=False)
    requires_deep_work = Column(Boolean, default=False)
    confidence_score = Column(Float, default=0.7)  # AI extraction confidence
    category = Column(String(100), nullable=True)  # deep_work, shallow, meeting, etc.
    status = Column(String(50), default="pending")  # pending, scheduled, completed, skipped
    metadata = Column(JSON, default={})  # Source-specific data
    embedding = Column(JSON, nullable=True)  # Vector embedding for similarity
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="work_items")

    __table_args__ = (
        Index("idx_workitem_user", "user_id"),
        Index("idx_workitem_source", "source"),
        Index("idx_workitem_status", "status"),
        Index("idx_workitem_due_date", "due_date"),
    )


class Schedule(Base):
    """Daily optimized schedule."""

    __tablename__ = "schedules"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    scheduled_date = Column(DateTime, nullable=False)
    work_items = Column(JSON, default=[])  # List of WorkItem IDs in order
    blocks = Column(JSON, default=[])  # Time blocks with duration
    focus_blocks = Column(JSON, default=[])  # Deep work blocks
    metrics = Column(JSON, default={})  # Workload metrics
    confidence_score = Column(Float, default=0.7)  # Schedule quality
    is_locked = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="schedules")

    __table_args__ = (
        Index("idx_schedule_user_date", "user_id", "scheduled_date"),
    )


class SyncState(Base):
    """Track incremental sync state per connector."""

    __tablename__ = "sync_states"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    connector_type = Column(String(50), nullable=False)
    last_full_sync = Column(DateTime, nullable=True)
    last_incremental_sync = Column(DateTime, nullable=True)
    sync_cursor = Column(String(500), nullable=True)
    next_sync_time = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    status = Column(String(50), default="idle")  # idle, syncing, error
    metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "connector_type", name="uq_sync_state"),
        Index("idx_syncstate_user", "user_id"),
    )


class AuditLog(Base):
    """Audit trail for compliance."""

    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(255), nullable=False)
    changes = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
        Index("idx_audit_action", "action"),
    )
