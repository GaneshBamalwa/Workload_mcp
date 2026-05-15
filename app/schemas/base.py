"""Pydantic v2 schemas for API request/response validation."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl


# ============================================================
# Organization Schemas
# ============================================================


class OrganizationCreate(BaseModel):
    """Create organization request."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    logo_url: Optional[HttpUrl] = None


class OrganizationUpdate(BaseModel):
    """Update organization request."""

    name: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[HttpUrl] = None


class OrganizationResponse(BaseModel):
    """Organization response."""

    id: str
    name: str
    slug: str
    description: Optional[str]
    logo_url: Optional[str]
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# User Schemas
# ============================================================


class UserCreate(BaseModel):
    """Create user request."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: Optional[str] = None
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    """Update user request."""

    full_name: Optional[str] = None
    timezone: Optional[str] = None
    preferences: Optional[dict[str, Any]] = None


class UserResponse(BaseModel):
    """User response."""

    id: str
    email: str
    username: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    role: str
    timezone: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserWithOrganization(UserResponse):
    """User response with organization."""

    organization: OrganizationResponse


# ============================================================
# Authentication Schemas
# ============================================================


class TokenRequest(BaseModel):
    """Token request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response."""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int  # seconds


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


# ============================================================
# OAuth Schemas
# ============================================================


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request."""

    code: str
    state: str


class OAuthToken(BaseModel):
    """OAuth token storage."""

    access_token: str
    refresh_token: Optional[str]
    token_type: str
    expires_at: Optional[datetime]
    scopes: list[str]


# ============================================================
# Integration Schemas
# ============================================================


class IntegrationCreate(BaseModel):
    """Create integration request."""

    connector_type: str = Field(..., pattern="^(gmail|slack|jira|calendar)$")


class IntegrationResponse(BaseModel):
    """Integration response."""

    id: str
    connector_type: str
    external_user_id: Optional[str]
    is_active: bool
    sync_enabled: bool
    last_synced_at: Optional[datetime]
    error_count: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Work Item Schemas
# ============================================================


class WorkItemCreate(BaseModel):
    """Create work item request."""

    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    source: str = Field(..., pattern="^(gmail|slack|jira|calendar|manual)$")
    source_id: str
    urgency: float = Field(default=0.5, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    estimated_effort_minutes: Optional[int] = None
    due_date: Optional[datetime] = None
    requires_response: bool = False
    requires_deep_work: bool = False
    category: Optional[str] = None
    stakeholders: Optional[list[str]] = []
    dependencies: Optional[list[str]] = []


class WorkItemUpdate(BaseModel):
    """Update work item request."""

    urgency: Optional[float] = None
    importance: Optional[float] = None
    estimated_effort_minutes: Optional[int] = None
    status: Optional[str] = None
    category: Optional[str] = None


class WorkItemResponse(BaseModel):
    """Work item response."""

    id: str
    source: str
    source_id: str
    title: str
    description: Optional[str]
    urgency: float
    importance: float
    estimated_effort_minutes: Optional[int]
    due_date: Optional[datetime]
    created_by: Optional[str]
    stakeholders: list[str]
    dependencies: list[str]
    requires_response: bool
    requires_deep_work: bool
    confidence_score: float
    category: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Schedule Schemas
# ============================================================


class ScheduleBlock(BaseModel):
    """Time block in schedule."""

    start_time: datetime
    end_time: datetime
    work_item_id: Optional[str] = None
    title: str
    is_focus_block: bool = False
    is_meeting: bool = False


class ScheduleCreate(BaseModel):
    """Create schedule request."""

    scheduled_date: datetime
    preferences: Optional[dict[str, Any]] = None


class ScheduleResponse(BaseModel):
    """Schedule response."""

    id: str
    scheduled_date: datetime
    blocks: list[ScheduleBlock]
    focus_blocks: list[ScheduleBlock]
    confidence_score: float
    is_locked: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Workload Schemas
# ============================================================


class WorkloadMetrics(BaseModel):
    """Workload metrics."""

    total_items: int
    deep_work_items: int
    meeting_count: int
    context_switches: int
    total_estimated_hours: float
    overload_risk: float  # 0.0-1.0
    focus_time_available: int  # minutes


class WorkloadResponse(BaseModel):
    """Current workload response."""

    today: list[WorkItemResponse]
    tomorrow: list[WorkItemResponse]
    this_week: list[WorkItemResponse]
    metrics: WorkloadMetrics
    generated_at: datetime


# ============================================================
# Error Response
# ============================================================


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    message: str
    details: Optional[dict[str, Any]] = None
    timestamp: datetime


# ============================================================
# Health Check
# ============================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    timestamp: datetime
