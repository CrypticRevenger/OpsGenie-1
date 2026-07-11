"""Company ORM model.

A Company represents a single B2B distributor using OpsGenie.  All other
entities (dealers, invoices, payments …) are scoped to a company.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin
from app.models._types import Money

if TYPE_CHECKING:
    from app.models.activity_timeline import ActivityTimeline
    from app.models.business_event import BusinessEvent
    from app.models.cash_snapshot import CashSnapshot
    from app.models.conversation_turn import ConversationTurn
    from app.models.daily_business_snapshot import DailyBusinessSnapshot
    from app.models.dealer import Dealer
    from app.models.faq import FAQ
    from app.models.import_log import ImportLog
    from app.models.invoice import Invoice
    from app.models.morning_briefing import MorningBriefing
    from app.models.notification_log import NotificationLog
    from app.models.payment import Payment
    from app.models.pending_operation import PendingOperation
    from app.models.product import Product
    from app.models.supplier import Supplier


class FollowUpState(enum.StrEnum):
    """Where a company's single active InvoiceDueDateFollowUp conversation
    (Phase 9) currently stands. Only one follow-up is in flight per company
    at a time — see app/services/followup.py.
    """

    awaiting_confirmation = "awaiting_confirmation"
    awaiting_partial_amount = "awaiting_partial_amount"
    awaiting_expected_date = "awaiting_expected_date"


class OnboardingState(enum.StrEnum):
    """Where a self-serve company is in the guided WhatsApp setup conversation
    (see app/services/onboarding_flow.py). `completed` is the terminal state and
    the server default — every existing/admin-created company is treated as
    already set up, so only companies created through the public /onboard flow
    walk the conversation.
    """

    not_started = "not_started"
    awaiting_business_type = "awaiting_business_type"
    product_awaiting_mode = "product_awaiting_mode"
    product_awaiting_bulk = "product_awaiting_bulk"
    product_awaiting_bulk_unit = "product_awaiting_bulk_unit"
    # Asked right after unit, before the batch is actually created — see
    # app/services/onboarding_flow.py. Purchase price feeds the Daily
    # Business Summary's sales_margin calculation (app/services/daily_snapshot.py).
    product_awaiting_bulk_purchase_price = "product_awaiting_bulk_purchase_price"
    product_awaiting_name = "product_awaiting_name"
    product_awaiting_quantity = "product_awaiting_quantity"
    product_awaiting_unit = "product_awaiting_unit"
    product_awaiting_purchase_price = "product_awaiting_purchase_price"
    dealer_awaiting_name = "dealer_awaiting_name"
    dealer_awaiting_phone = "dealer_awaiting_phone"
    dealer_awaiting_credit = "dealer_awaiting_credit"
    supplier_awaiting_name = "supplier_awaiting_name"
    supplier_awaiting_phone = "supplier_awaiting_phone"
    supplier_awaiting_credit = "supplier_awaiting_credit"
    awaiting_opening_balance = "awaiting_opening_balance"
    receivable_ask = "receivable_ask"
    receivable_dealer = "receivable_dealer"
    receivable_amount = "receivable_amount"
    receivable_date = "receivable_date"
    payable_ask = "payable_ask"
    payable_supplier = "payable_supplier"
    payable_amount = "payable_amount"
    payable_date = "payable_date"
    awaiting_language = "awaiting_language"
    awaiting_briefing_hour = "awaiting_briefing_hour"
    completed = "completed"


class Company(UUIDMixin, TimestampMixin, Base):
    """A B2B distributor company registered with OpsGenie."""

    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("whatsapp_number", name="uq_companies_whatsapp_number"),)

    business_name: Mapped[str] = mapped_column(String, nullable=False)
    owner_name: Mapped[str] = mapped_column(String, nullable=False)
    whatsapp_number: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    business_type: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    gst_number: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    # IANA timezone name (e.g. "Asia/Kolkata"). Business-day boundaries in the
    # snapshot — "today", overdue, the 7-day window — are computed in this zone,
    # NOT in UTC, so an 8am-local briefing reasons about the right calendar day.
    timezone: Mapped[str] = mapped_column(
        String, nullable=False, default="Asia/Kolkata", server_default=text("'Asia/Kolkata'")
    )
    # Manually toggled for pilot users — no billing system in V0.0 or V0.1.
    subscription_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    opening_balance: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    # V0.2 — GST percentage applied to WhatsApp-guided invoices (see
    # app/services/writes/orders.py::create_order). Opt-in: 0 until the
    # founder sets it via PATCH /admin/companies/{id}, so no distributor gets
    # surprise tax added to their invoices without configuring it first.
    gst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0"), server_default=text("0")
    )

    # Phase 9 — InvoiceDueDateFollowUpService conversation state (see
    # app/services/followup.py). Only one follow-up conversation is active
    # per company at a time; these three fields are always set/cleared
    # together. pending_follow_up_created_at is unused for now (no timeout
    # logic yet) but present so a later phase can expire a stale pending
    # follow-up without a schema change.
    pending_follow_up_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    pending_follow_up_state: Mapped[FollowUpState | None] = mapped_column(
        Enum(FollowUpState, name="followupstate", create_constraint=True),
        nullable=True,
    )
    pending_follow_up_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Guided WhatsApp onboarding (see app/services/onboarding_flow.py).
    # server_default `completed` so existing rows and founder/admin-created
    # companies never get pulled into the setup conversation; the public
    # /onboard path sets `not_started`. onboarding_scratch buffers the
    # in-progress dealer/supplier/invoice being collected across messages.
    onboarding_state: Mapped[OnboardingState] = mapped_column(
        Enum(OnboardingState, name="onboardingstate", create_constraint=True),
        nullable=False,
        server_default=OnboardingState.completed.value,
    )
    onboarding_scratch: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Per-company morning-briefing hour (0-23, business-local); overrides the
    # global BRIEFING_HOUR when set. Collected in onboarding.
    briefing_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Per-company evening-business-summary hour (0-23, business-local);
    # overrides the global EVENING_BRIEF_HOUR when set. Mirrors briefing_hour
    # exactly — see app/services/evening_brief.py.
    evening_brief_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Phase 2A — guided write workflows (see app/services/workflows/). Plain
    # string, not an enum, deliberately: unlike onboarding_state (a fixed,
    # known sequence), new workflow types get added over time (record_payment
    # now, create_invoice/add_dealer/... later) and a plain string means that
    # never needs a schema migration. workflow_scratch mirrors
    # onboarding_scratch's role — the in-flight flow's collected fields.
    active_workflow: Mapped[str | None] = mapped_column(String, nullable=True)
    workflow_scratch: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Mirrors pending_follow_up_invoice_id's pattern: an in-memory pointer so
    # the webhook can check "does this company have a pending confirmation"
    # with a plain attribute read on the already-loaded Company row, instead
    # of an extra query on every single inbound message for every company
    # (including the vast majority who never use a guided write workflow).
    # Set in app/services/writes/pending_operation.py::create_pending_operation,
    # cleared whenever that PendingOperation row is deleted.
    active_pending_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pending_operations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ────────────────────────────────────────────────────────
    dealers: Mapped[list[Dealer]] = relationship(
        "Dealer", back_populates="company", cascade="all, delete-orphan"
    )
    suppliers: Mapped[list[Supplier]] = relationship(
        "Supplier", back_populates="company", cascade="all, delete-orphan"
    )
    products: Mapped[list[Product]] = relationship(
        "Product", back_populates="company", cascade="all, delete-orphan"
    )
    invoices: Mapped[list[Invoice]] = relationship(
        "Invoice",
        back_populates="company",
        cascade="all, delete-orphan",
        # pending_follow_up_invoice_id (Phase 9) is a second FK path between
        # companies and invoices — without this, SQLAlchemy can't tell which
        # column this relationship (a company's own invoices) should join on.
        foreign_keys="Invoice.company_id",
    )
    payments: Mapped[list[Payment]] = relationship(
        "Payment", back_populates="company", cascade="all, delete-orphan"
    )
    cash_snapshots: Mapped[list[CashSnapshot]] = relationship(
        "CashSnapshot", back_populates="company", cascade="all, delete-orphan"
    )
    business_events: Mapped[list[BusinessEvent]] = relationship(
        "BusinessEvent", back_populates="company", cascade="all, delete-orphan"
    )
    activity_timelines: Mapped[list[ActivityTimeline]] = relationship(
        "ActivityTimeline", back_populates="company", cascade="all, delete-orphan"
    )
    morning_briefings: Mapped[list[MorningBriefing]] = relationship(
        "MorningBriefing", back_populates="company", cascade="all, delete-orphan"
    )
    import_logs: Mapped[list[ImportLog]] = relationship(
        "ImportLog", back_populates="company", cascade="all, delete-orphan"
    )
    notification_logs: Mapped[list[NotificationLog]] = relationship(
        "NotificationLog", back_populates="company", cascade="all, delete-orphan"
    )
    conversation_turns: Mapped[list[ConversationTurn]] = relationship(
        "ConversationTurn", back_populates="company", cascade="all, delete-orphan"
    )
    pending_operations: Mapped[list[PendingOperation]] = relationship(
        "PendingOperation",
        back_populates="company",
        cascade="all, delete-orphan",
        # active_pending_operation_id (above) is a second FK path between
        # companies and pending_operations — without this, SQLAlchemy can't
        # tell which column this relationship (a company's own pending
        # operations) should join on. Same fix as Company.invoices' own
        # foreign_keys= disambiguation for pending_follow_up_invoice_id.
        foreign_keys="PendingOperation.company_id",
    )
    faqs: Mapped[list[FAQ]] = relationship(
        "FAQ", back_populates="company", cascade="all, delete-orphan"
    )
    daily_business_snapshots: Mapped[list[DailyBusinessSnapshot]] = relationship(
        "DailyBusinessSnapshot", back_populates="company", cascade="all, delete-orphan"
    )
