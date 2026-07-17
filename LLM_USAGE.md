# Where LLMs are (and aren't) used in this codebase

Verified by grepping every call site of the two functions that can reach an
LLM (`answer_question`, `generate_with_fallback`) and every import of an LLM
SDK (`openai`, `anthropic`, `google.generativeai`) across the whole `app/`
tree. Nothing else in this codebase can reach a model.

> **LLMs are never treated as a source of business truth. They are
> responsible only for natural-language understanding and response
> generation. All business state, arithmetic, financial calculations,
> recommendations, and persistence are deterministic and implemented in
> Python.** Every time a common free-form request turns out to have a fixed
> shape (a name lookup, an item lookup, a "what if I sell N of X"
> calculation), it gets its own deterministic parser/route instead of
> staying on the LLM path — the LLM's share of traffic should keep shrinking
> toward genuinely open-ended questions only.

## TL;DR

| Question | Answer |
|---|---|
| Does creating/PDF-generating an invoice use an LLM? | **No.** Pure `Decimal` math + `fpdf2`, zero network calls. |
| Does any arithmetic (GST, totals, profit, stock) ever run inside an LLM? | **No, enforced.** Every number is computed in Python *before* an LLM sees it, and a regex guard (`money_guard.py`) discards any LLM reply that states a number it didn't get from a tool call. |
| Does the tappable menu (Cash, Inventory, Dealers, Invoices, etc.) use an LLM? | **No.** Every fixed menu option is a deterministic DB query (`instant_reports.py`). |
| Does "balance Ram Traders" / "stock Rice" / "if I sell 50kg of Rice" use an LLM? | **No, as of the latest change.** These take a free-text argument, so they couldn't be an exact-match menu command — they now have their own conservative parsers (prefix match / regex) that resolve against the real catalogue/party list before ever considering the LLM. |
| So what *does* use an LLM? | Exactly two things: genuinely open-ended free-form questions (anything the deterministic parsers below don't confidently resolve), and the morning briefing's narration. Both only *phrase* numbers that were already computed deterministically. |

---

## 1. The two places an LLM is ever called

### 1a. Free-form questions (`app/services/assistant.py`)

Anything typed that isn't a recognized menu word, workflow keyword, slash
command, or one of the deterministic parsed patterns in 2g below — e.g.
*"how's my week looking?"*, *"is Ram Traders a reliable payer?"*, or a sales-
impact question phrased in a shape the parser doesn't recognize.

```
webhook (whatsapp.py) → answer_question() → run_agent() → provider chain → LLM
                                                  ↑
                                         calls read_tools.py functions
                                         to fetch/compute real numbers
```

- The LLM **decides which tool to call**, and **phrases the final sentence**.
- It never computes a number itself — the system prompt explicitly forbids
  even simple arithmetic ("subtracting a sold quantity from stock,
  multiplying a quantity by a price"), pointing it at
  `calculate_sales_impact` instead.
- `money_guard.py` re-scans the LLM's final reply for every money-shaped
  figure and **throws the whole reply away** (falls back to a safe error
  message) if any figure isn't one a tool actually returned. A model can't
  "helpfully" invent ₹50,000 and have it reach you.

### 1b. Morning briefing narration (`app/services/briefing.py`)

The scheduled 8am push, the on-demand "give me my morning briefing"
command, and the admin dashboard's briefing preview all call
`generate_briefing()`, which:

1. Builds a `Snapshot` and runs `build_recommendations()` — pure Python,
   all figures final.
2. Calls `generate_with_fallback()` once, handing the LLM the already-computed
   numbers and asking only for readable prose.
3. Regex-extracts every ₹ figure in the LLM's output and cross-checks it
   against the real numbers before saving — same "never trust, always
   verify" pattern as the assistant.

### The provider chain (shared by both)

Configured in `.env` (`LLM_PROVIDER` + `LLM_FALLBACKS`), tried in order,
skipping any provider with no key configured or a rate-limit hit:

```
groq → gemini → openrouter → anthropic → github_models → cohere
```

(Cerebras and NVIDIA NIM were tried and removed — Cerebras gates its "free"
tier behind billing, NVIDIA times out on every tool-calling request.)

---

## 2. Everything else: deterministic "custom agents" (no LLM, ever)

These aren't LLM agents — "agent" here just means a Python function that
directly queries Postgres and returns/formats a result. Grouped by what they
do.

### 2a. Data-fetching functions (`app/services/agent/read_tools.py`)

The interesting part: **these same functions serve two masters**. They're
exposed as callable "tools" to the LLM (for free-form questions), *and* the
exact same functions back the guaranteed-deterministic menu commands below.
One source of truth for the numbers either way — only whether an LLM
narrates them differs.

| Function | What it computes |
|---|---|
| `get_business_summary` | Cash, net position, 7-day collections/payments, overdue dealers |
| `get_cash_position` | Cash available now + 7-day in/out + net position |
| `get_party_balance` | One dealer/supplier's outstanding balance, by (partial) name match |
| `list_top_debtors` / `list_top_creditors` | Parties ranked by amount owed, largest first |
| `list_overdue_dealers` | Overdue dealers with days-overdue and risk level |
| `get_priority_actions` | Ranked action list (cash warnings, dealers to call, urgent payments) via `recommendations.py`'s fixed rule set |
| `get_upcoming_collections` / `get_upcoming_payments` | 7-day expected in/out, per party |
| `get_inventory` | Full product catalogue: unit, stock, selling price |
| `calculate_sales_impact` | **The** deterministic what-if calculator — "if I sell N of X" math, real catalogue prices, never estimated |
| `get_faqs` | Founder-authored policy Q&A |
| `list_dealers` / `list_suppliers` | Full directory with phone + outstanding |
| `list_recent_invoices` / `list_recent_payments` | Recent transaction history |

### 2b. Guaranteed-deterministic menu commands (`app/services/instant_reports.py`)

Wired into `_INSTANT_COMMANDS` in `whatsapp.py` — matched *before* the
webhook ever considers calling the LLM. Every row in the tappable "Reports &
Overview" / "Dealers & Suppliers" / "Inventory & Transactions" menus routes
here now:

`cash_position_reply`, `business_summary_reply`, `priorities_reply`,
`overdue_dealers_reply`, `upcoming_collections_reply`,
`upcoming_payments_reply`, `all_dealers_reply`, `all_suppliers_reply`,
`top_debtors_reply`, `top_creditors_reply`, `inventory_reply`,
`faqs_reply`, `invoices_reply`, `payments_reply`.

Each one calls the matching function from 2a (or `query_menu.py`'s own
Snapshot-based report builders for the original numbered "1"-"4" menu),
formats it as WhatsApp text, and returns — no network call beyond Postgres.

Also in `whatsapp.py` itself: `_export_link_reply` (signed download link),
`_help_reply` (static text). Both fully deterministic.

**One exception worth flagging:** `_morning_briefing_reply` (the
"give me my morning briefing" on-demand command) is deterministically
*routed*, but if no briefing has been generated yet today it calls
`generate_briefing()` internally — which **does** reach the LLM (see 1b).
If today's briefing already ran, it just reuses the saved text for free.

### 2c. Guided write workflows — never touch an LLM

Every write (creating data, not reading it) is a fixed, multi-step
state machine — no LLM involved at any point, by design (see each module's
own docstring for the "why"):

| Flow | Files |
|---|---|
| Create order / invoice | `workflows/order_flow.py` → `writes/orders.py` |
| Record payment (with invoice picker) | `workflows/payment_flow.py` → `writes/payments.py` → `importer/payment_row.py` |
| Add / update / delete product | `workflows/product_flow.py` |
| Update GST (company-wide or per-product) | `workflows/gst_flow.py` → `writes/update_gst.py` |
| Guided onboarding | `onboarding_flow.py` |
| Confirm/execute gate for all of the above | `writes/pending_operation.py` |

### 2d. Invoice PDF generation

`app/services/invoice_pdf.py` — pure function, takes an already-computed
`CreateOrderResult`, renders it with `fpdf2`. No DB access, no network call,
no LLM.

### 2e. Scheduled background jobs (`app/core/scheduler.py`)

Dispatches the 8am briefing (touches the LLM, see 1b), the follow-up
conversation checks, and notification checks. The follow-up/notification
logic itself is deterministic; only the briefing generation step it
triggers reaches an LLM.

### 2f. Parsed deterministic commands — `_try_deterministic_free_text` (`whatsapp.py`)

The tier checked *after* `_INSTANT_COMMANDS`' exact-match dict and *before*
the LLM fallback — for requests that take a free-text argument, so they
can't be a fixed dict key, but are still narrow enough to resolve with
certainty:

| Pattern | Handler | Behavior |
|---|---|---|
| `balance <name>` | `instant_reports.party_balance_reply` | Reuses `read_tools.py`'s own fuzzy dealer/supplier match — the same one the LLM tool would use, so it can never disagree. |
| `stock <item>` | `instant_reports.stock_item_reply` | Reuses `read_tools.py`'s `_find_product` (singular-folding, substring match). |
| `if I sell N of X` (and variants: `if I sold`, `what if I sell`, multiple items joined by "and") | `instant_reports.try_deterministic_sales_impact` | `sales_impact_parser.py` extracts `(quantity, raw name)` pairs via regex, requiring an explicit trigger phrase; each raw name is then trimmed word-by-word until `_find_product` confirms a real catalogue match. Calls the exact same `calculate_sales_impact` math as the LLM tool, just renders a fixed template instead of LLM prose. |

**The safety rule that makes this fine to auto-expand over time:** every one
of these returns `None` on any ambiguity — an unrecognized phrasing, a
product name that doesn't resolve, a non-positive quantity — and `None`
means "fall through to the LLM assistant exactly as before." Nothing here
can ever produce a wrong deterministic answer; the worst case is just no
speedup for an unusual phrasing.

### 2g. The safety net (`app/services/agent/money_guard.py`)

Not a data source — the enforcement layer. Regex-scans every LLM reply
(assistant *and* briefing) for money-shaped figures (₹/Rs/INR, comma-grouped,
or a bare 5+-digit number — framing-independent so a prompt injection can't
sneak a fabricated number past it in a different format) and rejects the
whole reply if any figure wasn't one a deterministic tool actually returned.

---

## 3. Quick mental model

```
Every inbound message
        │
        ▼
1. Fixed menu tap / slash command / write workflow keyword?
        │ yes                                    │ no
        ▼                                         ▼
100% deterministic Python + SQL          2. Parsed pattern? ("balance <name>",
never touches an LLM                        "stock <item>", "if I sell N of X")
                                                    │ yes                │ no
                                                    ▼                    ▼
                                          Resolves against the    3. Free-form question
                                          real catalogue/party            │
                                          list or returns None            ▼
                                          (→ step 3) — never a    run_agent() calls
                                          guess                   deterministic tools (2a)
                                                                   for the real numbers
                                                                           │
                                                                           ▼
                                                                   LLM only phrases
                                                                   the sentence
                                                                           │
                                                                           ▼
                                                                   money_guard.py verifies
                                                                   every figure before it
                                                                   reaches you
```
