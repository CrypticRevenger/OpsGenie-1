"""Read tools — deterministic DB queries the agent can call to ground answers.

Every executor returns a JSON-safe dict with stringified Decimals so the
money-safety gate can treat the values as the set of "known" amounts, and —
critically — **every query is scoped to the bound `company.id`**. The company is
resolved once, from the sender's WhatsApp number, in the webhook; the LLM only
picks which of these tools to run and never sees another distributor's data.
These reuse existing services (snapshot, party_outstanding) — no new business
logic, just broad coverage so a distributor can ask about any of their own data.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.dealer import Dealer
from app.models.faq import FAQ
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.product import Product
from app.models.supplier import Supplier
from app.services.agent.base import AgentTool, no_params
from app.services.party_outstanding import (
    calculate_outstanding_for_company,
    calculate_party_outstanding,
)
from app.services.snapshot import build_snapshot


async def _get_business_summary(db: AsyncSession, company: Company) -> dict:
    s = await build_snapshot(db, company.id)
    return {
        "cash_available_now": str(s.cash_available_today),
        "net_cash_position": str(s.net_cash_position),
        "expected_collections_7d_total": str(s.expected_collections_7d_total),
        "expected_payments_7d_total": str(s.expected_payments_7d_total),
        "cash_shortage_expected": s.cash_deficit,
        "overdue_dealers": [
            {
                "name": od.dealer_name,
                "outstanding": str(od.outstanding),
                "days_overdue": od.days_overdue,
                "risk": od.risk_level,
            }
            for od in s.overdue_dealers
        ],
    }


async def _get_cash_position(db: AsyncSession, company: Company) -> dict:
    s = await build_snapshot(db, company.id)
    return {
        "cash_available_now": str(s.cash_available_today),
        "expected_collections_7d_total": str(s.expected_collections_7d_total),
        "expected_payments_7d_total": str(s.expected_payments_7d_total),
        "net_cash_position": str(s.net_cash_position),
        "cash_shortage_expected": s.cash_deficit,
    }


async def _get_party_balance(db: AsyncSession, company: Company, name: str) -> dict:
    like = f"%{name.strip().lower()}%"
    dealer = await db.scalar(
        select(Dealer)
        .where(Dealer.company_id == company.id, func.lower(Dealer.name).like(like))
        .limit(1)
    )
    if dealer is not None:
        amount = await calculate_party_outstanding(db, direction="receivable", party_id=dealer.id)
        return {"party": dealer.name, "relationship": "dealer_owes_you", "outstanding": str(amount)}
    supplier = await db.scalar(
        select(Supplier)
        .where(Supplier.company_id == company.id, func.lower(Supplier.name).like(like))
        .limit(1)
    )
    if supplier is not None:
        amount = await calculate_party_outstanding(db, direction="payable", party_id=supplier.id)
        return {
            "party": supplier.name,
            "relationship": "you_owe_supplier",
            "outstanding": str(amount),
        }
    return {"error": f"No dealer or supplier found matching '{name}'."}


async def _top_parties(
    db: AsyncSession, company: Company, *, direction: str, limit: int
) -> list[dict]:
    outstanding = await calculate_outstanding_for_company(
        db,
        company_id=company.id,
        direction=direction,  # type: ignore[arg-type]
    )
    model = Dealer if direction == "receivable" else Supplier
    names = {
        p.id: p.name
        for p in (await db.scalars(select(model).where(model.company_id == company.id))).all()
    }
    rows = sorted(
        (
            (names.get(pid, "Unknown"), amt)
            for pid, amt in outstanding.items()
            if amt > Decimal("0.00")
        ),
        key=lambda r: r[1],
        reverse=True,
    )[: max(1, min(limit, 20))]
    return [{"name": n, "outstanding": str(a)} for n, a in rows]


async def _list_top_debtors(db: AsyncSession, company: Company, limit: int = 5) -> dict:
    return {
        "dealers_who_owe_you": await _top_parties(db, company, direction="receivable", limit=limit)
    }


async def _list_top_creditors(db: AsyncSession, company: Company, limit: int = 5) -> dict:
    return {"suppliers_you_owe": await _top_parties(db, company, direction="payable", limit=limit)}


async def _list_overdue_dealers(db: AsyncSession, company: Company) -> dict:
    s = await build_snapshot(db, company.id)
    return {
        "overdue_dealers": [
            {
                "name": od.dealer_name,
                "outstanding": str(od.outstanding),
                "days_overdue": od.days_overdue,
                "risk": od.risk_level,
            }
            for od in s.overdue_dealers
        ]
    }


async def _get_upcoming_collections(db: AsyncSession, company: Company) -> dict:
    s = await build_snapshot(db, company.id)
    return {
        "total": str(s.expected_collections_7d_total),
        "collections_next_7_days": [
            {"dealer": c.dealer_name, "amount": str(c.amount), "due_date": c.due_date.isoformat()}
            for c in s.expected_collections_7d
        ],
    }


async def _get_upcoming_payments(db: AsyncSession, company: Company) -> dict:
    s = await build_snapshot(db, company.id)
    return {
        "total": str(s.expected_payments_7d_total),
        "payments_next_7_days": [
            {
                "supplier": p.supplier_name,
                "amount": str(p.amount),
                "due_date": p.due_date.isoformat(),
                "urgent": p.urgent,
            }
            for p in s.expected_payments_7d
        ],
    }


async def _get_inventory(db: AsyncSession, company: Company) -> dict:
    products = (await db.scalars(select(Product).where(Product.company_id == company.id))).all()
    return {
        "inventory": [
            {
                "name": p.name,
                "unit": p.unit,
                "stock_quantity": str(p.stock_quantity),
                "selling_price": str(p.selling_price) if p.selling_price is not None else None,
            }
            for p in products
        ]
    }


async def _get_faqs(db: AsyncSession, company: Company) -> dict:
    faqs = (
        await db.scalars(
            select(FAQ).where(FAQ.company_id == company.id).order_by(FAQ.created_at)
        )
    ).all()
    return {"faqs": [{"question": f.question, "answer": f.answer} for f in faqs]}


async def _all_parties(db: AsyncSession, company: Company, *, direction: str) -> list[dict]:
    outstanding = await calculate_outstanding_for_company(
        db,
        company_id=company.id,
        direction=direction,  # type: ignore[arg-type]
    )
    model = Dealer if direction == "receivable" else Supplier
    parties = (await db.scalars(select(model).where(model.company_id == company.id))).all()
    return [
        {
            "name": p.name,
            "phone": p.phone,
            "outstanding": str(outstanding.get(p.id, Decimal("0.00"))),
        }
        for p in parties
    ]


async def _list_dealers(db: AsyncSession, company: Company) -> dict:
    return {"dealers": await _all_parties(db, company, direction="receivable")}


async def _list_suppliers(db: AsyncSession, company: Company) -> dict:
    return {"suppliers": await _all_parties(db, company, direction="payable")}


def _clamp(limit: int, default: int = 10, hi: int = 25) -> int:
    try:
        return max(1, min(int(limit), hi))
    except (TypeError, ValueError):
        return default


async def _list_recent_invoices(db: AsyncSession, company: Company, limit: int = 10) -> dict:
    stmt = (
        select(Invoice, Dealer.name, Supplier.name)
        .outerjoin(Dealer, Invoice.dealer_id == Dealer.id)
        .outerjoin(Supplier, Invoice.supplier_id == Supplier.id)
        .where(Invoice.company_id == company.id)
        .order_by(Invoice.invoice_date.desc(), Invoice.invoice_number)
        .limit(_clamp(limit))
    )
    rows = (await db.execute(stmt)).all()
    return {
        "invoices": [
            {
                "number": inv.invoice_number,
                "direction": inv.direction.value,
                "party": dealer_name or supplier_name,
                "total": str(inv.total_amount),
                "status": inv.status.value,
                "invoice_date": inv.invoice_date.isoformat(),
                "due_date": inv.due_date.isoformat(),
            }
            for inv, dealer_name, supplier_name in rows
        ]
    }


async def _list_recent_payments(db: AsyncSession, company: Company, limit: int = 10) -> dict:
    stmt = (
        select(Payment, Invoice.invoice_number, Invoice.direction)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(Payment.company_id == company.id)
        .order_by(Payment.payment_date.desc())
        .limit(_clamp(limit))
    )
    rows = (await db.execute(stmt)).all()
    return {
        "payments": [
            {
                "amount": str(pmt.amount),
                "payment_date": pmt.payment_date.isoformat(),
                "method": pmt.method,
                "against_invoice": invoice_number,
                "direction": direction.value,
            }
            for pmt, invoice_number, direction in rows
        ]
    }


_LIMIT_PARAM = {
    "type": "object",
    "properties": {"limit": {"type": "integer", "description": "How many to return (max 20)."}},
    "required": [],
}
_NAME_PARAM = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Dealer or supplier name (may be partial)."}
    },
    "required": ["name"],
}

READ_TOOLS: list[AgentTool] = [
    AgentTool(
        "get_business_summary",
        "Overall snapshot: cash, net position, 7-day collections/payments, overdue dealers. "
        "Use for 'how's my business' / 'what should I focus on'.",
        no_params(),
        _get_business_summary,
    ),
    AgentTool(
        "get_cash_position",
        "Cash available now, expected in/out over the next 7 days, and net position.",
        no_params(),
        _get_cash_position,
    ),
    AgentTool(
        "get_party_balance",
        "Outstanding balance for one dealer (they owe you) or supplier (you owe them) by name.",
        _NAME_PARAM,
        _get_party_balance,
    ),
    AgentTool(
        "list_top_debtors",
        "Dealers who owe you the most money, largest first.",
        _LIMIT_PARAM,
        _list_top_debtors,
    ),
    AgentTool(
        "list_top_creditors",
        "Suppliers you owe the most money, largest first.",
        _LIMIT_PARAM,
        _list_top_creditors,
    ),
    AgentTool(
        "list_overdue_dealers",
        "Dealers whose payments are overdue, with days overdue and risk level.",
        no_params(),
        _list_overdue_dealers,
    ),
    AgentTool(
        "get_upcoming_collections",
        "Payments expected FROM dealers in the next 7 days.",
        no_params(),
        _get_upcoming_collections,
    ),
    AgentTool(
        "get_upcoming_payments",
        "Payments you owe TO suppliers in the next 7 days.",
        no_params(),
        _get_upcoming_payments,
    ),
    AgentTool(
        "get_inventory",
        "The distributor's product catalogue with unit, current stock quantity, and selling "
        "price. Use for 'what's my stock', 'how much Rice do I have', or any inventory question.",
        no_params(),
        _get_inventory,
    ),
    AgentTool(
        "get_faqs",
        "The distributor's founder-authored FAQ list (policy questions like delivery days, "
        "return policy, minimum order). Use this to answer questions about business policy "
        "rather than guessing.",
        no_params(),
        _get_faqs,
    ),
    AgentTool(
        "list_dealers",
        "All of the distributor's dealers (customers) with phone and current outstanding.",
        no_params(),
        _list_dealers,
    ),
    AgentTool(
        "list_suppliers",
        "All of the distributor's suppliers with phone and current outstanding.",
        no_params(),
        _list_suppliers,
    ),
    AgentTool(
        "list_recent_invoices",
        "Most recent invoices (number, party, total, status, dates), newest first.",
        _LIMIT_PARAM,
        _list_recent_invoices,
    ),
    AgentTool(
        "list_recent_payments",
        "Most recent payments recorded (amount, date, which invoice), newest first.",
        _LIMIT_PARAM,
        _list_recent_payments,
    ),
]
