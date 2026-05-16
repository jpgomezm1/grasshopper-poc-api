"""Bounded context: CRM comercial y productividad del equipo gh_commercial.

Contiene: BitrixSyncStatus, BitrixSyncLog, LeadProfile, Notification,
PushSubscription, TaskPriority, TaskStatus, Task, LeadTag,
LeadTagAssignment, SavedSearch, LeadComment, PipelineStage,
AutoAssignRule, PipelineRule.

Modelos intencionalmente independientes de las relaciones User/School
existentes para minimizar churn en los eager-loading paths del
HomeDashboard y el school panel.

Migrations 016-021 · gh_commercial productivity sprint · 2026-05-03.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.models.base import Base


class BitrixSyncStatus(str, enum.Enum):
    """Bitrix sync log status · GH-S10-DB-01."""
    PENDING = "pending"
    SUCCESS = "success"
    RETRY = "retry"
    FAILED = "failed"
    STUB = "stub"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class TaskStatus(str, enum.Enum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class BitrixSyncLog(Base):
    """Outbound + inbound Bitrix CRM sync log · GH-S10-DB-01.

    One row per sync attempt. The same (entity_type, entity_id) may have
    multiple rows over time (history). Status transitions:

        pending → retry* → success
        pending → retry* → failed   (after N attempts exhausted)
        pending → stub              (no BITRIX_WEBHOOK_URL configured · D-020)
        pending → success           (inbound webhook acknowledged)

    PII guard: payload may contain student name/email/phone. Logs use
    masking (mask_email helper in bitrix_client). DB row is authoritative
    record but never logged in stdout / metrics.

    The `provider` field tracks whether the row came from a real Bitrix
    call ('bitrix') or the stub mock ('stub'). On S12 cutover this lets
    us audit which rows need replay.
    """

    __tablename__ = "bitrix_sync_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entity_type = Column(String(40), nullable=False, index=True)
    entity_id = Column(String(120), nullable=False, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action = Column(String(40), nullable=False)
    payload = Column(JSON, nullable=True)
    bitrix_response = Column(JSON, nullable=True)

    status = Column(String(20), default=BitrixSyncStatus.PENDING.value, nullable=False, index=True)
    provider = Column(String(20), default="stub", nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class LeadProfile(Base):
    """Lead profiles from quick vocational quiz (no account required)."""
    __tablename__ = "lead_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Contact info (captured at end of quiz)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

    # Quiz data
    answers = Column(JSON, nullable=False)
    profile_result = Column(JSON, nullable=False)

    # Tracking
    converted = Column(Boolean, default=False, nullable=False)
    source = Column(String(50), default="landing_quiz", nullable=False)


class Notification(Base):
    """In-app notification for any role · GH-COMMPROD-A1 (migration 017).

    Created by hooks across services (lead assigned · pipeline change · SLA
    breach · task due soon · contact request created · @mention received).
    The frontend bell icon polls /notifications/me?status=unread.
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(String(60), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    data = Column(JSON, nullable=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PushSubscription(Base):
    """Web Push API subscription · GH-COMMPROD-A2 (migration 017).

    One row per (user, browser/device). The endpoint URL is unique across
    all users (it's effectively a globally unique push channel).
    """
    __tablename__ = "push_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)


class Task(Base):
    """Reminder / to-do · GH-COMMPROD-B3 (migration 018)."""
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assigned_to_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    description = Column(Text, nullable=False)
    due_at = Column(DateTime, nullable=True)
    priority = Column(String(10), default=TaskPriority.NORMAL.value, nullable=False)
    status = Column(String(10), default=TaskStatus.OPEN.value, nullable=False)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    notified_due_at = Column(DateTime, nullable=True)


class LeadTag(Base):
    """Catalog of tags applicable to leads · GH-COMMPROD-D1 (migration 019)."""
    __tablename__ = "lead_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(60), nullable=False, unique=True)
    label = Column(String(120), nullable=False)
    color = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LeadTagAssignment(Base):
    """Many-to-many between leads (users) and tags · GH-COMMPROD-D1."""
    __tablename__ = "lead_tag_assignments"
    __table_args__ = (
        UniqueConstraint("lead_user_id", "tag_id", name="uq_lead_tag"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_id = Column(
        UUID(as_uuid=True),
        ForeignKey("lead_tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SavedSearch(Base):
    """Personal saved CRM filter view · GH-COMMPROD-D3 (migration 020)."""
    __tablename__ = "saved_searches"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_saved_search_per_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(120), nullable=False)
    filters = Column(JSON, nullable=False)
    pinned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LeadComment(Base):
    """Threaded comment on a lead · GH-COMMPROD-F1 (migration 020)."""
    __tablename__ = "lead_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    body = Column(Text, nullable=False)
    mentions = Column(JSON, nullable=True)
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("lead_comments.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    edited_at = Column(DateTime, nullable=True)


class PipelineStage(Base):
    """Customizable pipeline stage · GH-COMMPROD-B6 (migration 021)."""
    __tablename__ = "pipeline_stages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(40), nullable=False, unique=True)
    label = Column(String(120), nullable=False)
    color = Column(String(20), nullable=True)
    order_index = Column(Integer, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AutoAssignRule(Base):
    """Rule that decides which gh_* gets a freshly created lead · GH-COMMPROD-E1.

    Strategies:
        round_robin    · cycle through gh_commercial actives
        least_loaded   · pick the gh_commercial with fewest open leads
        by_country     · `config = {"colombia": "<user_id>", ...}`
        by_language    · `config = {"es": "<id>", "en": "<id>"}`
    """
    __tablename__ = "auto_assign_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy = Column(String(40), nullable=False)
    config = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=100, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PipelineRule(Base):
    """IFTTT-style rule applied on lead state changes · GH-COMMPROD-E2."""
    __tablename__ = "pipeline_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    condition = Column(JSON, nullable=False)
    action = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
