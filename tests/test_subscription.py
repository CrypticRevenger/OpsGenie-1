"""Subscription activate/deactivate tests.

Activation sends the welcome template — monkeypatched here (real Meta creds
would otherwise send for real, and the template only exists once approved).

    uv run alembic upgrade head
    uv run pytest tests/test_subscription.py -v
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from app.db.session import async_session_factory
from app.models.company import Company
from app.models.notification_log import NotificationLog
from app.services.activation import activate_company
from app.services.whatsapp_client import WhatsAppSendResult
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_pending_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Sub Co",
        owner_name="Owner",
        whatsapp_number=_unique_number(),
        subscription_active=False,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@pytest.fixture
def welcome_calls(monkeypatch):
    """Force a configured welcome template + capture template sends."""
    calls = []

    async def _fake_template(to, template_name, language_code, body_params=None):
        calls.append((to, template_name, language_code, body_params))
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    class _Settings:
        welcome_template_name = "welcome"
        welcome_template_language = "en_US"
        welcome_template_has_variable = True

    monkeypatch.setattr("app.services.activation.send_template_message", _fake_template)
    monkeypatch.setattr("app.services.activation.get_settings", lambda: _Settings())
    return calls


@pytest.mark.asyncio
async def test_activate_flips_flag_and_sends_welcome(
    client: AsyncClient, db: AsyncSession, welcome_calls
) -> None:
    company = await _make_pending_company(db)

    resp = await client.post(f"/admin/companies/{company.id}/activate-subscription")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "activated"
    assert data["subscription_active"] is True
    assert data["welcome_sent"] is True
    assert len(welcome_calls) == 1
    to, _template, _lang, body_params = welcome_calls[0]
    assert to == company.whatsapp_number
    assert body_params == [company.business_name]  # personalized with the business name

    await db.refresh(company)
    assert company.subscription_active is True
    log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "welcome",
        )
    )
    assert log is not None
    assert log.delivery_status == "sent"


@pytest.mark.asyncio
async def test_activate_already_active_is_noop(
    client: AsyncClient, db: AsyncSession, welcome_calls
) -> None:
    company = await _make_pending_company(db)
    await client.post(f"/admin/companies/{company.id}/activate-subscription")  # first: activates
    welcome_calls.clear()

    resp = await client.post(f"/admin/companies/{company.id}/activate-subscription")  # second
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_active"
    assert resp.json()["welcome_sent"] is False
    assert welcome_calls == []  # no duplicate welcome


@pytest.mark.asyncio
async def test_activate_welcome_send_failure_still_activates(
    client: AsyncClient, db: AsyncSession, monkeypatch
) -> None:
    """A failed welcome send is logged, not raised — activation still succeeds."""
    from app.services.whatsapp_client import WhatsAppSendError

    async def _failing(to, template_name, language_code, body_params=None):
        raise WhatsAppSendError("meta down")

    class _Settings:
        welcome_template_name = "welcome"
        welcome_template_language = "en_US"
        welcome_template_has_variable = True

    monkeypatch.setattr("app.services.activation.send_template_message", _failing)
    monkeypatch.setattr("app.services.activation.get_settings", lambda: _Settings())

    company = await _make_pending_company(db)
    resp = await client.post(f"/admin/companies/{company.id}/activate-subscription")
    assert resp.status_code == 200
    assert resp.json()["status"] == "activated"
    assert resp.json()["welcome_sent"] is False
    await db.refresh(company)
    assert company.subscription_active is True  # activated despite send failure


@pytest.mark.asyncio
async def test_deactivate(client: AsyncClient, db: AsyncSession, welcome_calls) -> None:
    company = await _make_pending_company(db)
    await client.post(f"/admin/companies/{company.id}/activate-subscription")

    resp = await client.post(f"/admin/companies/{company.id}/deactivate-subscription")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deactivated"
    assert resp.json()["subscription_active"] is False
    await db.refresh(company)
    assert company.subscription_active is False


@pytest.mark.asyncio
async def test_activate_unknown_company_404(client: AsyncClient) -> None:
    resp = await client.post(f"/admin/companies/{uuid.uuid4()}/activate-subscription")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_concurrent_activate_calls_send_welcome_only_once(
    db: AsyncSession, monkeypatch
) -> None:
    """Real bug class, same shape as tests/test_evening_brief.py::
    test_concurrent_calls_from_separate_sessions_send_only_once — see
    app/services/activation.py::activate_company's docstring.
    activate_company used to be a plain "read subscription_active, then
    decide, then write" with no lock behind it, and both the admin
    activate-subscription route and the public /onboard wizard's final step
    call it directly. Two genuinely concurrent callers for the same company
    must flip the flag and send the real welcome template only once.
    """
    company = Company(
        business_name="Activation Race Co",
        owner_name="Owner",
        whatsapp_number=_unique_number(),
        subscription_active=False,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    company_id = company.id

    sent: list[str] = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_template(to, template_name, language_code, body_params=None):
        started.set()
        await release.wait()
        sent.append(to)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    class _Settings:
        welcome_template_name = "welcome"
        welcome_template_language = "en_US"
        welcome_template_has_variable = True

    monkeypatch.setattr("app.services.activation.send_template_message", _slow_template)
    monkeypatch.setattr("app.services.activation.get_settings", lambda: _Settings())

    async def _attempt() -> tuple[str, bool]:
        async with async_session_factory() as session:
            company_row = await session.get(Company, company_id)
            return await activate_company(session, company_row)

    async def _watcher() -> None:
        await started.wait()
        await asyncio.sleep(0.2)
        release.set()

    results = await asyncio.gather(_attempt(), _attempt(), _watcher())
    attempt_results = results[:2]

    statuses = sorted(status for status, _ in attempt_results)
    assert statuses == ["activated", "already_active"]
    welcome_sent_flags = sorted(welcome_sent for _, welcome_sent in attempt_results)
    assert welcome_sent_flags == [False, True]
    assert len(sent) == 1  # only one real welcome template send

    async with async_session_factory() as verify_db:
        refreshed = await verify_db.get(Company, company_id)
        assert refreshed.subscription_active is True
        logs = (
            await verify_db.scalars(
                select(NotificationLog).where(
                    NotificationLog.company_id == company_id,
                    NotificationLog.notification_type == "welcome",
                )
            )
        ).all()
        assert len(logs) == 1
