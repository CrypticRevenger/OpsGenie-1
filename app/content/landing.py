"""Marketing-page copy for the landing page.

Plain data, deliberately free of any FastAPI/pydantic/SQLAlchemy import so it
can be imported by scripts/build_static_site.py (the Vercel static-site
build step) without installing the rest of the backend. app/api/site.py
imports these same lists for the live, FastAPI-served pages — this module is
the single source of truth for both.

Data-driven so future additions (invoice creation, inventory, purchase
orders, analytics) are a one-line list append, not a template redesign.
"""

from __future__ import annotations

OUTCOMES = [
    {"icon": "💰", "text": "Know who will pay you today."},
    {"icon": "📦", "text": "Never miss a supplier payment."},
    {"icon": "📊", "text": "See tomorrow's cash position."},
    {"icon": "💬", "text": "Ask your business questions on WhatsApp."},
]

BUILT_FOR = [
    "FMCG Distributors",
    "Pharma Distributors",
    "Feed Distributors",
    "Wholesale Businesses",
]

HOW_IT_WORKS = [
    "Start Free on WhatsApp",
    "Complete WhatsApp Setup",
    "Send invoices & payments",
    "Receive daily business briefing",
]

COMPARISON = [
    {"traditional": "Login daily", "opsgenie": "WhatsApp"},
    {"traditional": "Complex menus", "opsgenie": "Chat"},
    {"traditional": "Training required", "opsgenie": "No training"},
    {"traditional": "Desktop first", "opsgenie": "Mobile first"},
    {"traditional": "Expensive", "opsgenie": "Affordable"},
]

PRICING_FEATURES = [
    "Unlimited WhatsApp",
    "Morning Brief",
    "Outstanding Tracking",
    "Cash Flow",
    "AI Assistant",
]

FAQ = [
    {
        "question": "Do I need to install an app?",
        "answer": "No. Everything happens inside WhatsApp.",
    },
    {
        "question": "Can I use it with multiple employees?",
        "answer": "Coming soon.",
    },
    {
        "question": "Do you support inventory?",
        "answer": "Coming soon.",
    },
    {
        "question": "Can I cancel anytime?",
        "answer": "Yes.",
    },
    {
        "question": "Is my data secure?",
        "answer": "Yes.",
    },
]
