"""
SQLAlchemy ORM models mirroring schema.sql.

All tables use UUID PKs generated server-side.
Relationships are lazy-loaded by default (async-safe: use selectinload).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Reference tables
# ---------------------------------------------------------------------------

class Driver(Base):
    __tablename__ = "drivers"

    driver_id:    Mapped[str]  = mapped_column(Text, primary_key=True, default=_uuid)
    code:         Mapped[str]  = mapped_column(Text, nullable=False, unique=True)  # VER, HAM
    full_name:    Mapped[str]  = mapped_column(Text, nullable=False)
    abbreviation: Mapped[str | None] = mapped_column(Text)
    nationality:  Mapped[str | None] = mapped_column(Text)
    number:       Mapped[int | None] = mapped_column(SmallInteger)
    jolpica_id:   Mapped[int | None] = mapped_column(Integer, unique=True)
    active:       Mapped[bool] = mapped_column(Boolean, default=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Team(Base):
    __tablename__ = "teams"

    team_id:    Mapped[str]  = mapped_column(Text, primary_key=True, default=_uuid)
    name:       Mapped[str]  = mapped_column(Text, nullable=False)
    short_name: Mapped[str | None] = mapped_column(Text)
    jolpica_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    active:     Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Core tables
# ---------------------------------------------------------------------------

class Decision(Base):
    __tablename__ = "decisions"

    id:             Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    doc_id:         Mapped[str]      = mapped_column(Text, nullable=False, unique=True)
    sha256_hash:    Mapped[str]      = mapped_column(Text, nullable=False, unique=True)
    title:          Mapped[str]      = mapped_column(Text, nullable=False)
    pdf_url:        Mapped[str]      = mapped_column(Text, nullable=False)
    r2_key:         Mapped[str | None] = mapped_column(Text)
    season:         Mapped[int]      = mapped_column(SmallInteger, nullable=False)
    published_at:   Mapped[str | None] = mapped_column(Text)
    raw_text:       Mapped[str]      = mapped_column(Text, nullable=False, default="")
    char_count:     Mapped[int]      = mapped_column(Integer, nullable=False, default=0)
    needs_ocr:      Mapped[bool]     = mapped_column(Boolean, nullable=False, default=False)
    parser_version: Mapped[str]      = mapped_column(Text, nullable=False, default="v1.0-pdfplumber")
    parsed_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    incidents: Mapped[list[Incident]] = relationship("Incident", back_populates="decision")

    __table_args__ = (
        CheckConstraint("season >= 2018", name="ck_decisions_season"),
    )


class Incident(Base):
    __tablename__ = "incidents"

    incident_id:         Mapped[str]       = mapped_column(Text, primary_key=True, default=_uuid)
    doc_id:              Mapped[str]        = mapped_column(ForeignKey("decisions.doc_id"), nullable=False)
    drivers:             Mapped[list[Any]]  = mapped_column(JSONB, nullable=False, default=list)
    # The other cars in the incident — impeded, hit, or forced off the track.
    # Deliberately not merged into `drivers`: every driver-scoped query in the
    # API filters on that column to mean "was penalised", so a counterparty
    # stored there would count someone else's penalty against the victim.
    involved_drivers:    Mapped[list[Any]]  = mapped_column(JSONB, nullable=False, default=list)
    session_key:         Mapped[int | None] = mapped_column(Integer)
    lap:                 Mapped[int | None] = mapped_column(SmallInteger)
    corner:              Mapped[str | None] = mapped_column(Text)
    article_cited:       Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    infraction_category: Mapped[str | None] = mapped_column(Text)
    penalty_type:        Mapped[str | None] = mapped_column(Text)  # see ck_incidents_penalty_type
    penalty_seconds:     Mapped[int | None] = mapped_column(SmallInteger)
    penalty_points:      Mapped[int]        = mapped_column(SmallInteger, default=0)
    # 'full', 'partial', or NULL when the penalty was served normally. Without
    # this a suspended penalty is indistinguishable from one that was actually
    # served: Hulkenberg's 2026 Canadian stop-and-go was suspended in full and
    # never served, yet was stored as a bare 'SG'. 'partial' is a separate state
    # because most suspensions are half a fine — the other half really was paid.
    penalty_suspended:   Mapped[str | None] = mapped_column(Text)  # see ck_incidents_penalty_suspended
    grid_positions:      Mapped[int | None] = mapped_column(SmallInteger)
    contact:             Mapped[bool | None] = mapped_column(Boolean)
    position_change:     Mapped[int | None] = mapped_column(SmallInteger)
    reasoning_text:      Mapped[str]        = mapped_column(Text, nullable=False, default="")
    weather_context:     Mapped[dict | None] = mapped_column(JSONB)
    video_refs:          Mapped[list | None] = mapped_column(JSONB)
    extractor_version:   Mapped[str]        = mapped_column(Text, default="v1.0-regex")
    created_at:          Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:          Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    decision: Mapped[Decision] = relationship("Decision", back_populates="incidents")
    race_control_messages: Mapped[list[RaceControlMessage]] = relationship(
        "RaceControlMessage", back_populates="incident"
    )
    radio_clips: Mapped[list[TeamRadioClip]] = relationship(
        "TeamRadioClip", back_populates="incident"
    )

    __table_args__ = (
        # WARN, FINE and SG were missing: the stewards issue standalone warnings
        # and fines constantly, and a stop-and-go is a distinct penalty from a
        # drive-through. Rulings with those outcomes could not be represented at
        # all and stored NULL. The regex arm admits any "Ns" time penalty — the
        # FIA issues 15s/20s/30s as well as 5s/10s. Widened in migration 0010.
        CheckConstraint(
            "penalty_type IN ('NFA','REP','WARN','FINE','SG','DT','GRID','DSQ')"
            " OR penalty_type ~ '^[0-9]{1,2}s$'",
            name="ck_incidents_penalty_type",
        ),
        CheckConstraint(
            "penalty_suspended IS NULL OR penalty_suspended IN ('full','partial')",
            name="ck_incidents_penalty_suspended",
        ),
    )


class Event(Base):
    __tablename__ = "events"

    event_id:           Mapped[str]      = mapped_column(Text, primary_key=True, default=_uuid)
    season:             Mapped[int]      = mapped_column(SmallInteger, nullable=False)
    round_number:       Mapped[int]      = mapped_column(SmallInteger, nullable=False)
    circuit:            Mapped[str]      = mapped_column(Text, nullable=False)
    country:            Mapped[str]      = mapped_column(Text, nullable=False)
    event_name:         Mapped[str]      = mapped_column(Text, nullable=False)
    event_date:         Mapped[date | None] = mapped_column(Date)
    openf1_meeting_key: Mapped[int | None] = mapped_column(Integer)
    created_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sessions: Mapped[list[Session]] = relationship("Session", back_populates="event")

    __table_args__ = (
        CheckConstraint("season >= 2018", name="ck_events_season"),
        UniqueConstraint("season", "round_number", name="uq_events_season_round"),
    )


class Session(Base):
    __tablename__ = "sessions"

    session_id:   Mapped[str]      = mapped_column(Text, primary_key=True, default=_uuid)
    event_id:     Mapped[str]      = mapped_column(ForeignKey("events.event_id", ondelete="CASCADE"), nullable=False)
    session_type: Mapped[str]      = mapped_column(Text, nullable=False)
    session_key:  Mapped[int | None] = mapped_column(Integer, unique=True)
    start_time:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time:     Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped[Event] = relationship("Event", back_populates="sessions")


class RaceControlMessage(Base):
    __tablename__ = "race_control_messages"

    message_id:    Mapped[str]      = mapped_column(Text, primary_key=True, default=_uuid)
    session_key:   Mapped[int]      = mapped_column(Integer, nullable=False)
    date:          Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category:      Mapped[str | None] = mapped_column(Text)
    message:       Mapped[str]      = mapped_column(Text, nullable=False)
    flag:          Mapped[str | None] = mapped_column(Text)
    scope:         Mapped[str | None] = mapped_column(Text)
    sector:        Mapped[int | None] = mapped_column(SmallInteger)
    driver_number: Mapped[int | None] = mapped_column(SmallInteger)
    incident_id:   Mapped[str | None] = mapped_column(ForeignKey("incidents.incident_id"))
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    incident: Mapped[Incident | None] = relationship("Incident", back_populates="race_control_messages")


class TeamRadioClip(Base):
    __tablename__ = "team_radio_clips"

    clip_id:        Mapped[str]      = mapped_column(Text, primary_key=True, default=_uuid)
    session_key:    Mapped[int]      = mapped_column(Integer, nullable=False)
    driver_number:  Mapped[int]      = mapped_column(SmallInteger, nullable=False)
    date:           Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recording_url:  Mapped[str]      = mapped_column(Text, nullable=False, unique=True)
    r2_key:         Mapped[str | None] = mapped_column(Text)
    transcript:     Mapped[str | None] = mapped_column(Text)
    speaker_label:  Mapped[str | None] = mapped_column(Text)
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    urgency_score:  Mapped[float | None] = mapped_column(Float)
    incident_id:    Mapped[str | None] = mapped_column(ForeignKey("incidents.incident_id"))
    created_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    incident: Mapped[Incident | None] = relationship("Incident", back_populates="radio_clips")


class Annotation(Base):
    __tablename__ = "annotations"

    annotation_id:   Mapped[str]      = mapped_column(Text, primary_key=True, default=_uuid)
    doc_id:          Mapped[str]      = mapped_column(Text, nullable=False)
    annotator:       Mapped[str]      = mapped_column(Text, nullable=False, default="anonymous")
    infraction_type: Mapped[str | None] = mapped_column(Text)
    outcome:         Mapped[str | None] = mapped_column(Text)
    penalty_class:   Mapped[str | None] = mapped_column(Text)
    penalty_points:  Mapped[int | None] = mapped_column(SmallInteger)
    article_cited:   Mapped[str | None] = mapped_column(Text)
    notes:           Mapped[str | None] = mapped_column(Text)
    positive_doc_id: Mapped[str | None] = mapped_column(Text)
    negative_doc_id: Mapped[str | None] = mapped_column(Text)
    created_at:      Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())


class Guideline(Base):
    __tablename__ = "guidelines"

    article_id:         Mapped[str]      = mapped_column(Text, primary_key=True, default=_uuid)
    document_name:      Mapped[str]      = mapped_column(Text, nullable=False)
    section:            Mapped[str | None] = mapped_column(Text)
    article_number:     Mapped[str]      = mapped_column(Text, nullable=False)
    article_text:       Mapped[str]      = mapped_column(Text, nullable=False)
    recommended_penalty: Mapped[str | None] = mapped_column(Text)
    effective_date:     Mapped[date | None] = mapped_column(Date)
    created_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("document_name", "article_number", name="uq_guidelines_doc_article"),
    )


class StewardPanel(Base):
    __tablename__ = "steward_panels"

    panel_id:       Mapped[str]           = mapped_column(Text, primary_key=True, default=_uuid)
    event_id:       Mapped[str]           = mapped_column(ForeignKey("events.event_id"), nullable=False)
    chair:          Mapped[str]           = mapped_column(Text, nullable=False)
    members:        Mapped[list[str]]     = mapped_column(ARRAY(Text), nullable=False)
    driver_steward: Mapped[str | None]    = mapped_column(Text)
    created_at:     Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped[Event] = relationship("Event")


class PrecedentLink(Base):
    __tablename__ = "precedent_links"

    incident_id:         Mapped[str]   = mapped_column(ForeignKey("incidents.incident_id"), primary_key=True)
    similar_incident_id: Mapped[str]   = mapped_column(ForeignKey("incidents.incident_id"), primary_key=True)
    similarity_score:    Mapped[float] = mapped_column(Float, nullable=False)
    link_type:           Mapped[str]   = mapped_column(Text, default="semantic")
    created_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionLog(Base):
    __tablename__ = "predictions_log"

    prediction_id:  Mapped[str]      = mapped_column(Text, primary_key=True, default=_uuid)
    query_text:     Mapped[str]      = mapped_column(Text, nullable=False)
    query_features: Mapped[dict | None] = mapped_column(JSONB)
    predicted_dist: Mapped[dict]     = mapped_column(JSONB, nullable=False)
    ground_truth:   Mapped[str | None] = mapped_column(Text)
    model_version:  Mapped[str]      = mapped_column(Text, nullable=False)
    latency_ms:     Mapped[int | None] = mapped_column(Integer)
    created_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Phase 7 — billing / API keys
# ---------------------------------------------------------------------------

class ApiKey(Base):
    __tablename__ = "api_keys"

    key_id:         Mapped[str]           = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:        Mapped[str]           = mapped_column(Text, nullable=False)
    key_hash:       Mapped[str]           = mapped_column(Text, nullable=False, unique=True)
    key_prefix:     Mapped[str]           = mapped_column(Text, nullable=False)
    name:           Mapped[str | None]    = mapped_column(Text)
    tier:           Mapped[str]           = mapped_column(Text, nullable=False, default="free")
    is_active:      Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    requests_today: Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    requests_total: Mapped[int]           = mapped_column(BigInteger, nullable=False, default=0)
    last_used_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at:     Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:     Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    usage_logs: Mapped[list[UsageLog]] = relationship("UsageLog", back_populates="api_key")

    __table_args__ = (
        CheckConstraint("tier IN ('free','pro','team')", name="ck_api_keys_tier"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    subscription_id:        Mapped[str]           = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:                Mapped[str]           = mapped_column(Text, nullable=False, unique=True)
    stripe_customer_id:     Mapped[str | None]    = mapped_column(Text, unique=True)
    stripe_subscription_id: Mapped[str | None]    = mapped_column(Text, unique=True)
    tier:                   Mapped[str]           = mapped_column(Text, nullable=False, default="free")
    status:                 Mapped[str]           = mapped_column(Text, nullable=False, default="active")
    current_period_end:     Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end:   Mapped[bool]          = mapped_column(Boolean, nullable=False, default=False)
    created_at:             Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:             Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("tier IN ('free','pro','team')",                           name="ck_subscriptions_tier"),
        CheckConstraint("status IN ('active','canceled','past_due','trialing')",   name="ck_subscriptions_status"),
    )


class UsageLog(Base):
    __tablename__ = "usage_logs"

    log_id:      Mapped[str]           = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    key_id:      Mapped[str | None]    = mapped_column(ForeignKey("api_keys.key_id", ondelete="SET NULL"))
    user_id:     Mapped[str | None]    = mapped_column(Text)
    endpoint:    Mapped[str]           = mapped_column(Text, nullable=False)
    method:      Mapped[str]           = mapped_column(Text, nullable=False, default="GET")
    status_code: Mapped[int | None]    = mapped_column(SmallInteger)
    latency_ms:  Mapped[int | None]    = mapped_column(Integer)
    ip_address:  Mapped[str | None]    = mapped_column(Text)
    created_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    api_key: Mapped[ApiKey | None] = relationship("ApiKey", back_populates="usage_logs")
