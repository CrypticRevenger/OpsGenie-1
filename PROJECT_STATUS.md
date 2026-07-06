# OpsGenie — Project Status

_Last updated: 2026-07-06_

A running record of everything built so far, in order, and what's still open. See `SPEC.md` for the original product/technical spec and `docs/api.md` for the API reference. This file is the "what actually happened" complement to those two.

---

## What OpsGenie is

A WhatsApp-first daily financial operating assistant for B2B distributors. It ingests existing business records (Tally/Vyapar/Excel exports), maintains a deterministic ledger of invoices/payments/dealers/suppliers, and delivers daily cash-position briefings and guided write actions (record a payment, place an order) entirely over WhatsApp — with an LLM layer for narration and free-form Q&A, but **never** for owning business state or doing money math.

Being built solo, targeting real distributor pilots (not a demo/student project) — see the "Working principles" section below for what that discipline has meant in practice.

---

## Timeline: what's been built, in order

### Phase 0 — Project foundation
Repo scaffolding, FastAPI app factory, config/logging/exception-handling core.

### Phase 1 — Database schema
All 13 ORM models, first Alembic migration, full model test coverage.

### Phase 2 — Admin CRUD
`company` / `dealer` / `supplier` create/read endpoints.

### Phase 3 — Import pipeline
Pluggable importer architecture (Tally / Vyapar / Canonical CSV/Excel formats), idempotent invoice + payment import with FIFO payment allocation. Real pilot data first used here (see "Real pilot data" below).

### Phase 4 — Invoice/payment read APIs
Filterable list endpoints with computed `amount_paid` / `amount_outstanding`.

### Phase 5A — Business engine (pure Python, no LLM)
`BusinessSnapshotService`, `DealerOutstandingCalculator`, `RecommendationEngine`, `GET /admin/companies/{id}/cashflow`. Deliberately split from 5B so the deterministic engine shipped and got validated before any LLM code was written (see "Working principles").

### Phase 5B — LLM briefing/narration layer
`BriefingService` narrates the Phase 5A snapshot in natural language. Ended up as a **pluggable multi-provider failover chain** (`app/services/llm/`) rather than a single hardcoded Claude call: `ClaudeProvider`, `GeminiProvider`, `GroqProvider`, `OpenRouterProvider`, selected/chained via `.env` (`LLM_PROVIDER` + `LLM_FALLBACKS`). Verified in production: a real OpenRouter 429 failed over to Gemini automatically with identical dealer figures.

### Pre-Phase-6 production hardening
Full architect review, six real fixes: corrected 7-day cashflow math to use outstanding (not gross) invoice amounts, added `Company.timezone` (business-day boundaries were off by a day around UTC/IST midnight), committed `uv.lock`, made Docker run migrations before boot, capped import upload size at 10MB, stopped leaking exception internals from `/health`.

### Phase 6 — Auth + pagination
Shared-key `X-API-Key` auth (fails closed if unset) on all `/admin/*` routes; generic `Page[T]` pagination on all 5 list endpoints, `limit` capped at 200.

### Phase 7 — WhatsApp inbound webhook
`GET`/`POST /webhooks/whatsapp` — Meta verification handshake + HMAC-SHA256 signature check, both fail closed. Scope was "parse and durably log," not routing (no query menu yet).

### Phase 8 — Numbered query menu
Four canned reports (Cash / Collections / Suppliers / Dealer Risk) triggered by replying 1-4. First outbound WhatsApp sending (`whatsapp_client.py`), a generic `CommandRouter` (registry pattern, not if/elif), and full send→log→correlation-ID traceability from inbound message to delivery status.

### Phase 9 — Invoice due-date follow-up
On an invoice's due date, the bot asks "Has payment been received? 1 Yes 2 Partial 3 Not yet" and routes the reply into payment recording, entirely in-thread. Deterministic-only relative-date parsing (weekday names, "tomorrow", "N days") — no fuzzy date guessing.

### Phases 10-12 — Notifications, scheduler, stale-data banner
Built together in one pass — completed all of SPEC's V0.1 scope. `NotificationEngine` (4 rule-based alerts: supplier payment due, high-risk dealer with no recent follow-up, no data in 24h, briefing delivery failed), one `APScheduler` interval poll job (every 15 min, checks each company's own business-local hour against configured briefing/retry/follow-up hours), and a stale-data banner prepended to briefings when data is >24h old.

### Deploy checkpoint
First-ever push to GitHub (`github.com/CrypticRevenger/OpsGenie`), deployed to Render. Migrated the database from Render's free (30-day-expiring) Postgres to **Neon** free tier for persistence. Real Meta WhatsApp webhook verified live against the user's own phone — found and fixed the non-obvious gotcha that the app must be subscribed to the WABA (`POST /{WABA_ID}/subscribed_apps`), not just have the callback URL registered.

### Post-V0.1: self-serve product additions (beyond original SPEC)
- `DELETE /admin/companies/{id}` — cascade delete.
- **Self-serve onboarding + subscription gating**: public `/onboard` wizard creates a pending company; founder (or now the public flow itself) activates via a shared activation service that flips `subscription_active` and sends a Meta-approved WhatsApp welcome template. Webhook only replies to active subscriptions.
- **Public marketing website**: landing page, onboarding wizard, privacy/terms/contact — deployed standalone to **Vercel** as a static build (`scripts/build_static_site.py`) while the API/scheduler stay on Render (Vercel can't run APScheduler). Shared content lives in framework-free `app/content/landing.py` so the static build doesn't need FastAPI installed. Logo, WhatsApp-styled theme, animations, responsive polish.
- `WELCOME_TEMPLATE_NAME` currently uses Meta's stock `hello_world` template as a stand-in while the real `opsgenie_welcome` template is pending Meta approval.

### V0.2 Phase 1 — Agentic read agent
Multi-turn conversational memory (`ConversationTurn` model) + a provider-agnostic tool-calling loop (`app/services/agent/`) with 13 read-only tools over the existing snapshot/outstanding services. A **money-safety gate** (`money_guard.py`) discards any LLM reply containing a rupee figure not actually present in the tool outputs it fetched — falls back to a safe canned reply instead of ever risking a hallucinated number.

### V0.2 Phase 2A — Guided payment recording
First guided **write** workflow over WhatsApp: "record payment" → party → amount → date → preview → YES/NO. Built on a new generic `PendingOperation` confirm-gate (30-min TTL, reusable for every future write type) and the existing FIFO payment allocator. Deliberately narrower than the original design: unknown parties are confirmed before creation (never silently auto-created), and the flow is keyword-triggered rather than agent-tool-callable. A structured review caught and fixed 10 issues, two serious (an unbounded date input could crash the whole webhook request; only one conversation step recognized "cancel," so users could get stuck mid-flow).

### V0.2 Phase 2B — Inventory, FAQ, guided order creation
Prompted by an n8n reference flow the user wanted matched (WhatsApp → AI agent with inventory/FAQ/order tools). Confirmed up front that order creation stays a guided workflow + confirm (same shape as 2A), not a direct AI tool-call — consistent with the "writes are workflows" principle.
- Real `stock_quantity` tracking added to `Product` (previously name/price only), decremented on order creation, allowed to go negative with a flagged warning (physical counts can lag digital ones).
- Per-company FAQ table + admin CRUD, read by the agent via a new `get_faqs` tool.
- `list_products` renamed/enriched to `get_inventory`.
- New guided flow `order_flow.py` (dealer → repeatable product/quantity loop → preview → confirm) + `writes/orders.py::create_order`, mirroring the Phase 2A payment flow exactly.
- First-ever `PATCH` endpoints in the admin API (products, FAQ).
- 419 tests passing at the end of this phase.

### Latest commit — onboarding fix (2026-07-06)
The guided WhatsApp onboarding only ever asked for a product's *name*, leaving every onboarded product at `stock_quantity = 0` — silently breaking Phase 2B's inventory tracking for every real signup. Fixed by adding a `product_awaiting_quantity` onboarding state between name and the next product/done.

### Live production check (2026-07-06)
Confirmed the deployed backend (`https://opsgenie.onrender.com`) is reachable and reflects real usage: 2 real companies existed from the user's own end-to-end test of the public onboarding wizard, proving the self-serve signup → WhatsApp guided setup flow genuinely works. Both were deleted at the user's request afterward — production currently has 0 companies.

### Website bug-fix pass (2026-07-06)
Live-tested the deployed site + WhatsApp agent on a real phone and fixed 6 issues: free-text AI assistant falling back to the canned menu on short queries (strengthened system prompt + added diagnostic logging), missing Back button on onboarding step 1, a resubmit-with-same-number flow that looked identical to a fresh signup (added a banner), plus verified two reported "bugs" that turned out not to be bugs (data was in fact being saved; duplicate numbers are structurally blocked by a DB unique constraint).

---

## LLM usage: which provider, and where tokens actually get spent

**Provider chain** (multi-provider failover, not one fixed model — configured in `.env`):
- **Primary: Groq** — `llama-3.3-70b-versatile` ("reliable tool-caller")
- **Fallback 1: Gemini** — `gemini-2.5-flash`
- **Fallback 2: OpenRouter** — `openai/gpt-oss-120b:free`
- **Fallback 3: Anthropic (Claude)** — `claude-haiku-4-5`

If the primary fails or rate-limits, `generate_with_fallback()` (`app/services/llm/factory.py`) automatically tries the next provider in order. Same chain is used for both token-consuming flows below.

**Only two places in the codebase spend LLM tokens** — everything else (menu replies, guided payment/order workflows, notifications, onboarding, admin CRUD, scheduler ticks) is pure deterministic Python with zero token cost:

1. **Morning briefing narration** — `app/services/briefing.py:generate_briefing()` calls `generate_with_fallback()`. Triggered from:
   - `app/core/scheduler.py:130` — the daily APScheduler tick, auto-generating each company's briefing at their configured hour.
   - `app/api/admin/briefing.py:73` — `POST /admin/companies/{id}/briefing`, the founder manually requesting/regenerating one.
   - What it does: takes the already-computed `BusinessSnapshot` (cash, dealers, recommendations — all pure Python) and asks the LLM to narrate it into readable text. One LLM call per briefing.

2. **WhatsApp free-form Q&A assistant** — `app/services/assistant.py:answer_question()` → `app/services/agent/runner.py` → `provider.run_tool_loop()`. Triggered from:
   - `app/api/webhooks/whatsapp.py:441` — any inbound message that doesn't match the numbered menu (1-4), isn't a workflow keyword ("record payment", "new order"), and isn't a reply inside an active guided workflow — i.e. genuine free text like "how much does Ram owe?"
   - What it does: runs the tool-calling loop, which may issue multiple LLM calls per user message (one per read-tool call it decides to make — inventory, cashflow, dealer outstanding, etc.) before producing a final answer. The money-guard then checks the reply before sending.

---

## Current state (as of 2026-07-06)

- **~430+ tests passing** (419 as of Phase 2B, plus a few more added in the latest onboarding fix), ruff-clean, real Postgres in every test (no mocking).
- **Deployed and live**: Render (API + scheduler + WhatsApp webhook) + Vercel (static marketing site) + Neon (Postgres).
- **Real WhatsApp integration verified working end-to-end** on the user's own phone, both for the numbered menu and the self-serve onboarding wizard.
- **Production database currently empty** (0 companies) — the 2 test signups were deleted after verification.
- **Local dev database** has 6000+ accumulated rows from the test suite (tests never clean up after themselves, by long-standing convention) plus the real AP BIOCARE pilot dataset used as the standing reconciliation check (Siddha Mahaveer Agencies' outstanding balance must equal ₹3,19,828.00 after any change touching invoice/payment logic).
- **Welcome WhatsApp template** is still the generic Meta `hello_world` stand-in — the real branded template is pending Meta's approval.
- **No payment gateway** — "subscribing" is a manual `subscription_active` flag flip, by design for the pilot phase.
- **Pricing page shows ₹999/month but activation is currently free** ("Coming soon" payment) — an intentional pilot-phase choice, not a bug, but means unlimited free signups today.

---

## What's not built yet / open items

- **Real distributor pilot hasn't formally started** — the infrastructure is proven end-to-end with the user's own test numbers, but no actual external distributor has been onboarded yet.
- **Payment gateway** for real subscription billing (Stripe/Razorpay or similar) — deliberately deferred.
- **Branded WhatsApp welcome template** — waiting on Meta approval.
- **Deploying Phase 2B (inventory/FAQ/orders) to production** — built and tested locally only; the migration hasn't been run against the live Render/Neon database yet.
- **Guided invoice creation** (multi-line-item, beyond the simple order flow) — `PendingOperation` infrastructure is designed to support it but it hasn't been built.
- **Employee/role-based permissions** — the read/write tool split was designed with this in mind but no second role exists yet.
- **`CashSnapshot`/`ActivityTimeline` tables** — modeled early on, still partially or fully unused.
- **`data_completeness_score`** in the business snapshot is still a stub (needs daily-import-cadence tracking).
- **Scheduler runs inside the web process** — fine at pilot scale, but a free-tier host spinning down when idle means ticks only fire while the process is awake; would need an always-on instance or dedicated worker for a real always-on pilot.
- **Payment idempotency** is still just `(party, date, amount)` — could in theory drop a genuine same-day/same-amount duplicate payment (flagged, not yet hardened).

---

## Working principles (how this project gets built)

- **Strict phase discipline**: no skipping ahead, no AI/LLM features before the deterministic business engine is solid and tested.
- **Validate with real data**: the AP BIOCARE pilot dataset (real invoices/payments for an actual veterinary/agri distributor) is the standing reconciliation check re-run after any change to money logic.
- **Writes are workflows, not AI capabilities**: every write (payment, order, eventually invoice) is a deterministic guided conversation with an explicit confirm step — the LLM's only job is recognizing intent, never producing or calculating the numbers.
- **Money always traceable**: a money-guard gate blocks any AI-generated reply containing a figure that isn't verifiably sourced from a real tool/DB call.
- **Structured review before calling a phase done**: multi-angle background-agent code review (line-by-line, cross-file, reuse, simplification, efficiency, conventions) on every phase, real bugs fixed before moving on.
- **Commit/push only when explicitly asked** — not batched, not assumed.
