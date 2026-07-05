"""Free-form WhatsApp assistant — an agentic, tool-calling, multi-turn agent.

Once a company has finished onboarding, any WhatsApp message that isn't a
numbered menu command, a follow-up reply, or a write-workflow step lands here.
Unlike the old fixed-context assistant, this is a real agent: it decides which
read tools to call (`app/services/agent/read_tools.py`), fetches live data from
the DB, and holds a conversation (last N turns of memory).

Money-safety is unchanged and central: the LLM never invents or computes a
figure — every number comes from a deterministic tool execution, and
`reply_has_unverified_money` discards any reply that states a figure the tools
didn't return. `answer_question` never raises (it runs on the public Meta
webhook, where an exception would 500 and trigger Meta's retry storm).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.company import Company
from app.models.conversation_turn import ConversationTurn
from app.services.agent.base import ToolContext
from app.services.agent.money_guard import reply_has_unverified_money
from app.services.agent.read_tools import READ_TOOLS
from app.services.agent.runner import run_agent

logger = logging.getLogger(__name__)

ASSISTANT_NOTIFICATION_TYPE = "assistant"

_SYSTEM_PROMPT = (
    "You are OpsGenie, a friendly WhatsApp assistant for a B2B distributor "
    "(owner: {owner}). You help them run their business finances — cash position, "
    "dealer and supplier balances, collections, upcoming payments, overdue accounts, "
    "and their product catalogue.\n"
    "Rules:\n"
    "- For ANY business number, you MUST call a tool to fetch it. Never guess, "
    "estimate, or calculate a figure yourself. Always write money with a ₹ prefix.\n"
    "- A short one- or two-word message (e.g. 'invoices', 'payments', 'dealers', "
    "'suppliers', 'cash') is a request for that data, not small talk — call the "
    "matching tool immediately instead of asking a clarifying question first. Only "
    "ask a clarifying question if no tool plausibly matches at all.\n"
    "- You cannot create orders/invoices or record payments yourself — you have no tool "
    "for it. If the user wants to place an order or log a payment, tell them to say "
    "'new order' or 'record payment' to start a guided step-by-step flow.\n"
    "- Party names may be abbreviated ('Ram' means 'Ram Traders') — match loosely.\n"
    "- Be warm and conversational: greet back, answer 'what can you do', thanks, and "
    "light small talk naturally.\n"
    "- Politely decline fully off-topic requests (jokes, general trivia, writing "
    "essays) and steer back to their business.\n"
    "- Keep replies short and clear for WhatsApp, in {language}."
)

_SAFE_FALLBACK = (
    "Sorry, I couldn't answer that right now. Reply 1 Cash · 2 Collections · "
    "3 Suppliers · 4 Dealer Risk, or try rephrasing."
)


async def _load_history(db: AsyncSession, company: Company, limit: int) -> list[dict[str, str]]:
    """The last `limit` dialogue turns, oldest-first, as provider-agnostic
    {role, content} messages.
    """
    turns = (
        await db.scalars(
            select(ConversationTurn)
            .where(ConversationTurn.company_id == company.id)
            .order_by(ConversationTurn.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [{"role": t.role, "content": t.content} for t in reversed(turns)]


async def _generate_reply(db: AsyncSession, company: Company, text: str) -> str:
    settings = get_settings()
    try:
        history = await _load_history(db, company, settings.agent_history_turns)
        ctx = ToolContext(db=db, company=company, tools={t.name: t for t in READ_TOOLS})
        result = await run_agent(
            system_prompt=_SYSTEM_PROMPT.format(
                owner=company.owner_name, language=company.preferred_language
            ),
            messages=[*history, {"role": "user", "content": text}],
            ctx=ctx,
            settings=settings,
        )
        # The money gate lives inside the guard too, so this function keeps its
        # "never raises into the webhook" contract end to end.
        if not result.text.strip():
            logger.warning(
                "Assistant (%s) returned empty text for company %s, message %r — using fallback.",
                result.provider,
                company.id,
                text,
            )
            return _SAFE_FALLBACK
        if reply_has_unverified_money(result.text, result.tool_outputs):
            logger.warning(
                "Assistant (%s) reply for company %s stated an unverified amount — using "
                "fallback. message=%r reply=%r tool_outputs=%r",
                result.provider,
                company.id,
                text,
                result.text,
                result.tool_outputs,
            )
            return _SAFE_FALLBACK
        return result.text
    except Exception as exc:  # noqa: BLE001 - never raise into the webhook
        logger.warning("Assistant failed for company %s, message %r: %s", company.id, text, exc)
        return _SAFE_FALLBACK


async def answer_question(db: AsyncSession, company: Company, text: str) -> str:
    """Answer a free-form message with the agent and record the exchange for
    multi-turn memory. Never raises; the caller (webhook) commits.
    """
    reply = await _generate_reply(db, company, text)

    # Persist the turn pair. created_at is set explicitly (not the DB's
    # transaction-time now()) so the user message reliably sorts before the
    # assistant reply when both are committed in the same transaction.
    now = datetime.now(UTC)
    db.add(ConversationTurn(company_id=company.id, role="user", content=text, created_at=now))
    db.add(
        ConversationTurn(
            company_id=company.id,
            role="assistant",
            content=reply,
            created_at=now + timedelta(microseconds=1),
        )
    )
    return reply
