"""app/services/workflows/payment_reminder_confirm.py — the guided "did you
actually pay this supplier bill?" flow. No dedicated test file existed before
this (flagged as a gap in PROJECT_STATUS.md's Timeline when the context-
restatement/cancel-escape fix landed on 2026-07-22); this adds coverage for
that existing behavior plus the new "help"/"menu" orientation-word handling
(a real production report, 2026-07-24: typing "help" mid-reminder fell
through to the generic "didn't understand, reply 1/2" restatement with no
indication of *why* "help" didn't work).
"""

from __future__ import annotations

import uuid

import pytest
from app.models.company import Company
from app.services.workflows.payment_reminder_confirm import (
    handle_reminder_confirm_workflow_message,
    promote_queued_reminder,
    start_reminder_confirm,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Reminder Confirm Test Co",
        owner_name="Owner",
        whatsapp_number=_unique_phone(),
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


def _item() -> dict:
    return {
        "supplier_id": str(uuid.uuid4()),
        "supplier_name": "Royal Meat Suppliers",
        "amount": "90000.00",
        "invoice_id": str(uuid.uuid4()),
        "invoice_number": "INV-RM-001",
    }


def _item2() -> dict:
    return {
        "supplier_id": str(uuid.uuid4()),
        "supplier_name": "Premium Poultry",
        "amount": "21000.00",
        "invoice_id": str(uuid.uuid4()),
        "invoice_number": "INV-PP-002",
    }


# ── start_reminder_confirm / awaiting_paid_choice ────────────────────────────


def test_start_reminder_confirm_sets_workflow_and_asks_paid() -> None:
    company = Company(business_name="Co", owner_name="Owner", whatsapp_number=_unique_phone())
    question = start_reminder_confirm(company, _item(), [])

    assert company.active_workflow == "confirm_supplier_payment"
    assert company.workflow_scratch["step"] == "awaiting_paid_choice"
    assert "Royal Meat Suppliers" in question
    assert "90,000" in question


@pytest.mark.asyncio
async def test_invalid_choice_restates_supplier_and_amount(db: AsyncSession) -> None:
    company = await _make_company(db)
    start_reminder_confirm(company, _item(), [])

    reply = await handle_reminder_confirm_workflow_message(db, company, "banana")

    assert "Royal Meat Suppliers" in reply
    assert "90,000" in reply
    assert company.active_workflow == "confirm_supplier_payment"


@pytest.mark.asyncio
async def test_cancel_clears_the_workflow(db: AsyncSession) -> None:
    company = await _make_company(db)
    start_reminder_confirm(company, _item(), [])

    reply = await handle_reminder_confirm_workflow_message(db, company, "cancel")

    assert "cancel" in reply.lower()
    assert company.active_workflow is None
    assert company.workflow_scratch is None


# ── "help"/"menu" mid-reminder — explain without cancelling ──────────────────


@pytest.mark.asyncio
async def test_help_mid_paid_choice_explains_without_cancelling(db: AsyncSession) -> None:
    company = await _make_company(db)
    start_reminder_confirm(company, _item(), [])

    reply = await handle_reminder_confirm_workflow_message(db, company, "help")

    assert "first" in reply.lower()
    assert "Royal Meat Suppliers" in reply
    assert "90,000" in reply
    assert company.active_workflow == "confirm_supplier_payment"
    assert company.workflow_scratch["step"] == "awaiting_paid_choice"


@pytest.mark.asyncio
async def test_menu_mid_amount_confirm_explains_without_cancelling(db: AsyncSession) -> None:
    company = await _make_company(db)
    start_reminder_confirm(company, _item(), [])
    await handle_reminder_confirm_workflow_message(db, company, "1")

    reply = await handle_reminder_confirm_workflow_message(db, company, "menu")

    assert "first" in reply.lower()
    assert "90,000" in reply
    assert company.workflow_scratch["step"] == "awaiting_amount_confirm"


@pytest.mark.asyncio
async def test_slash_help_mid_reschedule_explains_without_cancelling(db: AsyncSession) -> None:
    company = await _make_company(db)
    start_reminder_confirm(company, _item(), [])
    await handle_reminder_confirm_workflow_message(db, company, "2")

    reply = await handle_reminder_confirm_workflow_message(db, company, "/help")

    assert "first" in reply.lower()
    assert company.workflow_scratch["step"] == "awaiting_reschedule"


@pytest.mark.asyncio
async def test_skip_after_help_still_works(db: AsyncSession) -> None:
    """The orientation-word reply must never leave the flow unable to
    actually finish — the founder can still answer normally right after.
    """
    company = await _make_company(db)
    start_reminder_confirm(company, _item(), [])
    await handle_reminder_confirm_workflow_message(db, company, "2")
    await handle_reminder_confirm_workflow_message(db, company, "help")

    reply = await handle_reminder_confirm_workflow_message(db, company, "skip")

    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "remind" in reply.lower()


# ── promote_queued_reminder — quote-reply queue-jumping ──────────────────────
# A real production request (2026-07-24): let the founder use WhatsApp's
# native swipe/tap "Reply" on any pending reminder message and have that
# specific bill answered immediately, even before the currently-active one.


def test_promote_queued_reminder_jumps_to_the_matched_item() -> None:
    company = Company(business_name="Co", owner_name="Owner", whatsapp_number=_unique_phone())
    active_item = {**_item(), "whatsapp_message_id": "wamid.active"}
    queued_item = {**_item2(), "whatsapp_message_id": "wamid.queued"}
    company.active_workflow = "confirm_supplier_payment"
    company.workflow_scratch = {
        "step": "awaiting_paid_choice",
        "queue": [queued_item],
        **active_item,
    }

    promoted = promote_queued_reminder(company, "wamid.queued")

    assert promoted is True
    assert company.active_workflow == "confirm_supplier_payment"
    assert company.workflow_scratch["supplier_name"] == "Premium Poultry"
    assert company.workflow_scratch["step"] == "awaiting_paid_choice"
    # The previously-active bill (Royal Meat Suppliers) is requeued, not lost.
    requeued = company.workflow_scratch["queue"]
    assert len(requeued) == 1
    assert requeued[0]["supplier_name"] == "Royal Meat Suppliers"
    assert requeued[0]["whatsapp_message_id"] == "wamid.active"


def test_promote_queued_reminder_noop_when_quoting_the_active_message() -> None:
    company = Company(business_name="Co", owner_name="Owner", whatsapp_number=_unique_phone())
    active_item = {**_item(), "whatsapp_message_id": "wamid.active"}
    company.active_workflow = "confirm_supplier_payment"
    company.workflow_scratch = {"step": "awaiting_paid_choice", "queue": [], **active_item}

    promoted = promote_queued_reminder(company, "wamid.active")

    assert promoted is False
    assert company.workflow_scratch["supplier_name"] == "Royal Meat Suppliers"  # unchanged


def test_promote_queued_reminder_noop_when_no_match() -> None:
    company = Company(business_name="Co", owner_name="Owner", whatsapp_number=_unique_phone())
    active_item = {**_item(), "whatsapp_message_id": "wamid.active"}
    company.active_workflow = "confirm_supplier_payment"
    company.workflow_scratch = {"step": "awaiting_paid_choice", "queue": [], **active_item}

    promoted = promote_queued_reminder(company, "wamid.some_unrelated_old_message")

    assert promoted is False
    assert company.active_workflow == "confirm_supplier_payment"
    assert company.workflow_scratch["supplier_name"] == "Royal Meat Suppliers"


def test_promote_queued_reminder_noop_when_no_active_reminder() -> None:
    company = Company(business_name="Co", owner_name="Owner", whatsapp_number=_unique_phone())

    assert promote_queued_reminder(company, "wamid.anything") is False


def test_promote_queued_reminder_from_a_deeper_step_restarts_fresh_and_is_requeued() -> None:
    """Partial progress on the previously-active bill (already past
    awaiting_paid_choice) is discarded, not preserved — it restarts fresh
    once its turn comes back around."""
    company = Company(business_name="Co", owner_name="Owner", whatsapp_number=_unique_phone())
    active_item = {**_item(), "whatsapp_message_id": "wamid.active"}
    queued_item = {**_item2(), "whatsapp_message_id": "wamid.queued"}
    company.active_workflow = "confirm_supplier_payment"
    company.workflow_scratch = {
        "step": "awaiting_amount_confirm",
        "queue": [queued_item],
        **active_item,
    }

    promoted = promote_queued_reminder(company, "wamid.queued")

    assert promoted is True
    requeued = company.workflow_scratch["queue"]
    assert requeued[0]["supplier_name"] == "Royal Meat Suppliers"
    assert "step" not in requeued[0]  # stored as a plain item dict, not mid-step
