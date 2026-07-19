# OpsGenie — Project Status

_Last updated: 2026-07-19 (Onboarding: seed from an existing export + self-serve reconciliation)_

A running record of everything built so far, mapped to the SPEC's version roadmap, plus what's still open. See `SPEC.md` for the original product/technical spec and `docs/api.md` for the API reference. This file is the "what actually happened / what's left" complement to those two.

---

## What OpsGenie is

A WhatsApp-first daily financial operating assistant for B2B distributors. It ingests existing business records (Tally / Vyapar / Excel exports), maintains a **deterministic** ledger of invoices / payments / dealers / suppliers, and delivers daily cash-position briefings, on-demand reports, and guided write actions (record a payment, create an order/invoice, update GST/stock) entirely over WhatsApp — with an LLM layer for narration and free-form Q&A, but **never** for owning business state or doing money math.

Built solo, targeting real distributor pilots (not a demo). First real pilot dataset: **AP BIOCARE** (veterinary/agri distributor, Berhampur, Odisha). Standing reconciliation check: Siddha Mahaveer Agencies' computed outstanding must equal **₹3,19,828.00**.

---

## Version status at a glance

| SPEC version | Scope | Status |
|---|---|---|
| **V0.0 — Proof of Value** | CSV import → deterministic snapshot → LLM briefing → manual WhatsApp send | ✅ Complete |
| **V0.1 — Operational Product** | WhatsApp webhook, numbered query menu, morning-briefing scheduler, invoice follow-up flow, notification engine, confidence/stale-data indicator | ✅ Complete (all Steps 11–16) |
| **V0.2 — Source of Truth** | Create invoices/orders via WhatsApp, record payments via WhatsApp, GST math, PDF invoice delivery to dealer | ✅ Complete (code); Meta document-template approval to confirm |
| **V0.3 — Intelligence & Expansion** | Free-form AI Q&A, inventory alerts, marketing broadcast, analytics/trends | 🚧 Partial — free-form AI Q&A + inventory tracking + daily/MTD analytics done; broadcast & trend reporting not built |
| **Post-SPEC additions** | Self-serve onboarding + subscription gating, public marketing site (Vercel), password-gated admin dashboard, per-company Excel export, FAQ, per-product GST | ✅ Done (user-driven, beyond original SPEC) |

**System size today:** 17 ORM table models · 37 Alembic migrations (single linear head, DB at head `f3a9c1d7b268`) · 62 test files / **800 tests** (LLM-network tests skip without a key) · ruff clean. Tests now run against a dedicated `<dbname>_test` database with a production tripwire (`tests/conftest.py`, added 2026-07-19 after the suite once populated the live Neon prod DB with 1,041 fixture companies — see Timeline); a remote DB host requires explicit `ALLOW_REMOTE_TEST_DB=1`. The multilingual work was validated file-by-file directly against Neon before that tripwire existed; a single-process full-suite marathon over a remote Postgres endpoint hits transient socket drops (NullPool opens a fresh SSL connection per query — a CI infra concern, not a code one; see the CI item under Deployment/ops).

---

## Timeline: what's been built, in order

### Phase 0 — Project foundation
Repo scaffolding, FastAPI app factory, config / logging / exception-handling core, health check.

### Phase 1 — Database schema
All ORM models + first Alembic migration. (SPEC named 13 tables; the schema has since grown to 17 as write features landed.)

### Phase 2 — Admin CRUD
`company` / `dealer` / `supplier` create/read endpoints (founder-facing, `X-API-Key` gated).

### Phase 3 — Import pipeline
Pluggable importer architecture (Tally / Vyapar / Canonical CSV/Excel), idempotent invoice + payment import with **FIFO payment allocation**. First real-pilot-data validation here.

### Phase 4 — Invoice/payment read APIs
Filterable list endpoints with computed `amount_paid` / `amount_outstanding`.

### Phase 5A — Business engine (pure Python, no LLM)
`BusinessSnapshotService`, `DealerOutstandingCalculator`, `RecommendationEngine`, `GET /admin/companies/{id}/cashflow`. Split from 5B so the deterministic engine shipped and was validated before any LLM code existed.

### Phase 5B — LLM briefing/narration layer
`BriefingService` narrates the 5A snapshot. Built as a **pluggable multi-provider failover chain** (`app/services/llm/`): Claude / Gemini / Groq / OpenRouter / GitHub Models / Cohere, selected & chained via `.env` (`LLM_PROVIDER` + `LLM_FALLBACKS`). Verified in production: a real OpenRouter 429 failed over to Gemini with identical figures. Money is never invented by the LLM — every figure comes from the deterministic snapshot.

### Pre-Phase-6 production hardening
Money math corrected (outstanding, not gross, in 7-day windows), business-timezone boundaries (`Company.timezone`, IST), `uv.lock` committed, deploy migration step, upload size cap, health endpoint leak fix.

### Phase 6 — Auth + pagination
Single shared `ADMIN_API_KEY` (fails closed, generic 401), `Page[T]` pagination on all 5 list endpoints (limit capped at 200).

### Phase 7 — WhatsApp inbound webhook (V0.1 Step 11)
`GET`/`POST /webhooks/whatsapp` with its own two security mechanisms (verify-token handshake + `X-Hub-Signature-256` HMAC over raw body). Parses Meta payloads, matches sender to a `Company`, durably logs every message/status as a `BusinessEvent`.

### Phase 8 — Numbered query menu (V0.1 Step 12)
Generic `CommandRouter`, first-ever outbound sender (`whatsapp_client.py`), four canned reports (Cash / Collections / Suppliers / Dealer Risk) built strictly from snapshot fields. End-to-end traceability: inbound event → reply → Meta wamid → `NotificationLog` → status webhook. Idempotency against Meta redelivery.

### Phase 9 — Invoice due-date follow-up (V0.1 Step 13)
`InvoiceDueDateFollowUpService` — a full WhatsApp state machine ("Has payment been received? 1 Yes / 2 Partial / 3 Not yet") routing replies back through payment recording. One active follow-up per company at a time; deterministic-only date parsing.

### Phases 10–12 — Notifications + scheduler + stale-data banner (V0.1 Steps 14–16)
`NotificationEngine` (4 pure-rule alerts, internal dedup), `APScheduler` single-poll tick honoring each company's business-local hour, stale-data banner on briefings. **Completes all of V0.1.**

### Post-V0.1 deployment & product work
- `DELETE /admin/companies/{id}` (cascade), migrated prod DB Render→**Neon** (persistent), deployed at `https://opsgenie.onrender.com`.
- **Live WhatsApp integration verified** (real menu/fallback replies to the founder's phone; the WABA `subscribed_apps` gotcha was the blocker).
- **Self-serve onboarding + subscription gating** (contradicts original SPEC, but intended): public `/onboard`, founder activation flips `subscription_active` + sends welcome template; webhook only replies to active companies.
- **Public marketing site** (landing / onboard wizard / privacy / terms / contact), also deploys standalone to **Vercel**; `/onboard` + API + scheduler stay on Render.
- **Password-gated admin dashboard** (`/dashboard`, session cookie).

### V0.2 — WhatsApp-native writes ("Source of Truth")
- **Phase 2A — record payment** via guided WhatsApp workflow: generic `PendingOperation` confirm-gate (YES/NO), reuses the FIFO allocator; unknown parties confirmed before creating.
- **Phase 2B — create order** via guided workflow: real `stock_quantity` on `Product` (decremented per line), FAQ table + `get_faqs` agent tool, `get_inventory` tool.
- **Invoice-creation completion**: company-configurable GST (`Company.gst_rate` + per-product override), 14-day default due date, **PDF invoice generation** (`fpdf2`) + **delivery to dealer** via Meta document template.
- **Daily Business Summary**: `DailyBusinessSnapshot` (separate honest metrics — never a blended P/L), evening WhatsApp brief, dashboard card, month-to-date totals; shared `priority_actions.py` engine.
- Purchase-price collection (cost basis for margin), per-product GST, "update gst" flow.

### V0.3 (partial) — Intelligence
- **Free-form AI Q&A**: agentic read agent (`app/services/agent/`) with 13 read-only tools, multi-turn memory (`ConversationTurn`), provider-agnostic tool loop, and a **money-safety guard** that discards any LLM reply containing a figure the tools didn't actually return.
- **Deterministic report tier** (`instant_reports.py`): every menu keyword answers straight from the DB, never depending on an LLM call succeeding.
- **Sales-impact fast-path** ("if I sell N of X" → remaining stock / revenue / profit), computed deterministically.
- **Per-company Excel export** (`company_export.py`, 11 sheets), downloadable via short-lived HMAC-signed WhatsApp link or the dashboard.

### Whole-codebase audit pass — `def0c1c` (2026-07-17)
Verified enum↔DB parity (all 6 enum types), single migration head, config↔`.env.example` parity, no anti-patterns, tz-aware math. Fixed 3 real bugs (each with a regression test):
1. **Order creation crashed for any non-Latin-1 name** — fpdf2's core font raises on Odia/Hindi/Telugu (common for our distributors' dealer/product names); the PDF call was unguarded and 500'd the webhook before commit, wedging the order on Meta's retry loop. Now non-blocking + PDF sanitizes/renders.
2. **`_format_quantity` corrupted whole-number quantities** (`Decimal("50")` → `"5"`); now strips only fractional zeros.
3. **`notify_briefing_failed` didn't dedup** (founder spammed ~4×/day during a send outage); now once-per-day like its siblings.

### Post-audit polish + production incident (2026-07-18 — 2026-07-19)
- **Multilingual phases 4–5 completed**: guided onboarding, write-workflows/`pending_operation` confirmations, follow-up, notifications, evening brief, and briefing footer all localized across the 5 locales; Unicode invoice PDF (bundled Noto Sans/Devanagari/Oriya fonts, per-cell script-aware font selection). Closes out the ⭐ Multilingual support item below.
- **Vyapar/Tally-style reports** (`684b034`): ledger statements, GST sales/purchase registers, payment register, day book, and outstanding aging report — all period-scoped, dispatched through one signed-link endpoint, with PDF versions for ledger/aging. Wired into a new "Reports & Statements" WhatsApp list message (the original 3 lists were already at Meta's 10-row cap) and `/help` in all 5 locales.
- **Production incident — founder WhatsApp flood + Neon pollution** (`b6e6e13`, `f500fd1`): the test suite had been running against the live Neon prod DB, leaving 1,041 never-imported fixture companies that the stale-data nudge then alerted on every scheduler tick. Fixed with two guardrails: `tests/conftest.py` now hard-refuses to run against any non-local DB host unless `ALLOW_REMOTE_TEST_DB=1` (and always targets a `<dbname>_test` database, never the working dev DB), and `send_stale_data_digest` replaces the old per-company stale alert with one founder digest per tick, hard-capped to once per ~20h regardless of how many companies are flagged. The 1,041 fixture companies were wiped from Neon prod the same day.
- **Render cold-start wake-gate hardening** (`27281b9`, `d4dd922`, `d71ab70`): fixed the branded "waking up" overlay falsely reporting the backend awake against Render's own splash page (it used a `no-cors` fetch, which resolves on literally any response); extended wake-gate coverage to direct visits/bookmarks/refreshes of `/onboard` and `/dashboard` via a Vercel-rewritten `gate.html` (previously only click-through marketing links were covered); fixed the overlay getting stuck forever on a browser-back bfcache restore.
- **Onboarding polish**: bulk dealer/supplier entry (one-by-one vs. paste, matching the existing product flow) with confirm-before-create for unrecognized parties (`121b815`); standalone `add dealer`/`add supplier` commands usable any time, not just during onboarding (`d6504e8`); bulk-paste GST column now correctly hidden when GST doesn't vary by product (`9f35462`); wizard "Back"/homepage links now point at the real Vercel marketing site instead of Render's own copy (`5f3c0ec`); founder-number 409 now surfaces its real reason instead of a generic error (`a6a8f69`); WhatsApp menu buttons renamed to describe their contents (`159a48c`).

### Onboarding: seed from an existing export + self-serve reconciliation (2026-07-19)
Product decision (explicitly directed, not the model's default): the file-upload step belongs on the **website**, before WhatsApp ever starts, not as a WhatsApp document attachment — "Website collects information that is easier with forms" (onboarding.md) extends naturally to a bulk file upload, and a parsing failure mid-WhatsApp-conversation is much harder to recover from than one on a form. Reconciliation is shown **immediately after import**, still on the website, so a distributor can verify the numbers before ever touching WhatsApp — matching the AP BIOCARE ₹3,19,828 reconciliation check, made self-serve and moved earlier in the funnel rather than left to the founder to eyeball later.
- **New wizard step** (`app/templates/onboard.html` + `app/static/js/onboard.js`, now 5 steps) between Business Details and Activate: two optional file inputs (dealer invoices / supplier invoices — a real Tally/Vyapar export is usually a sales register and a purchase register, not one combined file), a "Skip — I'll enter everything through WhatsApp instead" link, and a reconciliation summary (dealers/suppliers/invoice counts, receivable/payable totals) rendered in place of the upload fields once import succeeds, with a "Looks good — Continue" second click before advancing — not auto-advanced, so the distributor has to actually look at it.
- **New public route** `POST /onboard/{id}/import` (`app/api/onboarding.py`) reuses `ImportEngine.run_import` unchanged (`file_kind="invoices"` only — opening receivables/payables, not full payment history import, matching what onboarding is actually for), scoped to one direction per call like the founder admin route it mirrors. Gated to `onboarding_state == not_started and not subscription_active` — stricter than the existing activate route's check, closing the same "guessed/leaked UUID" hole but for a route that can *write* data, not just flip a flag: without it, any UUID could inject invoices into a real, already-active distributor's live books after go-live. 5 MB upload cap (half the founder route's 10 MB) as cheap defense-in-depth on an unauthenticated surface — the real guard is the state gate, not the byte cap, since this repo has no rate-limiting infrastructure anywhere and none was added here (Phase-discipline call: not justified at pilot scale yet).
- **Reconciliation primitive**: `summarize_business_data()` (`app/services/onboarding.py`) is not import-specific — it just queries current Dealer/Supplier/Invoice state via the existing `calculate_outstanding_for_company`, so it's correct regardless of how the data got there. Returned alongside every import response so the wizard never needs a second round trip.
- **WhatsApp onboarding now skips what's already imported**: `onboarding_flow.py` gained a compositional skip chain (`_after_products` → `_after_dealers` → `_after_suppliers`, and `_after_opening_balance` → `_after_receivables`) that checks its own section's row count exactly once, at the moment that section would otherwise start — a company with no import sees count 0 and nothing changes (all 786 pre-existing tests stayed green through this refactor, unmodified). A company with imported dealers/suppliers/receivables/payables gets a short "found N from your import" note and jumps straight past the redundant section; partially-imported companies (e.g. only a payable file) still get asked normally for whatever wasn't provided. Products are always asked either way — a sales/purchase register doesn't carry a product catalogue with purchase price/stock. 4 new i18n keys × 5 locales.
- 14 new tests (`test_onboarding_import.py`: upload happy path, combined-direction summary, per-row error surfacing without failing the whole file, the security gate rejecting an already-activated company, oversize/bad-format/disabled-onboarding; 6 new skip-logic tests in `test_onboarding_flow.py`). Also fixed a stale TODO discovered while scoping this work: **per-party opening balances** (`receivable_ask`/`payable_ask`) turned out to already be built, and had been since the very first onboarding commit (2026-07-05) — the TODO claiming otherwise was added two weeks later and never reconciled against the code.
- Verified live against the local dev DB (not just the isolated test DB): registered a company, uploaded a real CSV through the new endpoint, confirmed the reconciliation totals, activated, then confirmed the endpoint correctly 404s post-activation — before cleaning up the smoke-test company via the admin API.

### Onboarding: resumable progress checklist + restart (2026-07-19)
The guided WhatsApp setup was already resumable by construction (state lives in durable `Company` columns, not a session — see `onboarding_flow.py`'s docstring), but a distributor returning after a break had no way to see how far along they were or to bail out and start clean. Two typed commands, same convention as the existing "done"/"skip"/"bulk" keywords (English triggers regardless of locale, localized replies), checked ahead of every per-field handler so neither word is ever swallowed as data:
- **`progress` / `status`** — an 8-section checklist (✅ done / ▶️ current / ⬜ pending) + % complete, plus a re-shown current question where that's safe to reconstruct verbatim (mid-entry sub-steps fall back to a generic continue line rather than duplicating every prompt's scratch-interpolation logic). Read-only — never mutates state.
- **`restart`** (confirm-gated, new `restart_confirm` OnboardingState + migration `f3a9c1d7b268`) — wipes every dealer/supplier/product/invoice the conversation has created so far (Invoice deleted before Dealer/Supplier — their FK is `ON DELETE SET NULL`, not `CASCADE`, so deleting the party first would silently orphan its opening-balance invoice instead of removing it) and resets the collected company fields, then restarts the 8-step sequence from business type. "no" restores the exact prior state and in-progress scratch (e.g. a half-entered product's name survives the detour).

17 new i18n keys across all 5 locale catalogs (parity + placeholder tests green). 6 new tests in `test_onboarding_flow.py` (checklist content/state-preservation, restart word not swallowed as data, restart cancel resumes mid-entry, restart confirm wipes rows + company fields including an opening-balance invoice). Full suite green (786 tests) and ruff clean.

### Edit / correction / data-management (2026-07-19)
Completes the four items of the same name under "What remains to do" — undo/void, edit invoice/payment, edit dealer/supplier, stock-take — all as guided WhatsApp workflows on the existing architecture (`PendingOperation` for money-affecting writes, write-immediately for attribute edits, `BusinessEvent` as a generic audit trail with an optional `reason` field on every entry). Two new migrations: 4 new `PendingOperationType` values + 6 new `BusinessEventType` values in one file, plus `suppliers.gst_number` (didn't exist before — only `Dealer` had it). New `validate_gstin()` in `app/services/gst.py`. A first design pass proposed automated FIFO reallocation for editing an already-paid invoice/payment; cut after review as too risky/hard to explain (real accounting systems prefer reverse-then-recreate over editing history) — editing an invoice with any payment recorded is refused outright rather than attempting to move money between invoices. New WhatsApp "Corrections" list message (the other 3 lists were already at Meta's 10-row cap, same fix the Reports feature used). 4 new test files (`test_void_flow.py`, `test_edit_flow.py`, `test_stock_take_flow.py`, `test_gst.py`) plus extensions to `test_party_flow.py`. Full suite green (780 tests) and ruff clean; the AP BIOCARE ₹3,19,828 reconciliation figure was **not** independently re-run live this session — no standalone repeatable test for it exists in the current suite — but `calculate_party_outstanding` and the FIFO allocator it depends on are untouched by this work (the new void/edit paths only ever delete a payment, bounds-check an edit against its own invoice, or refuse outright; none of them call the allocator).

---

## Current system inventory

**Models (17 tables):** company, dealer, supplier, product, invoice, invoice_item, payment, business_event, activity_timeline, morning_briefing, import_log, notification_log, conversation_turn, pending_operation, faq, daily_business_snapshot, cash_snapshot _(modeled but unused — per SPEC, outstanding is always computed from invoices+payments)_.

**Core services:** snapshot · party_outstanding · party_lookup · recommendations · priority_actions · briefing · llm/* (6 providers + factory) · assistant + agent/* (read tools, runner, money_guard) · command_router · query_menu · instant_reports · followup · notifications · scheduler · daily_snapshot · evening_brief · importer/* · workflows/* (payment, order, product, gst, party, void, edit, stock_take) · writes/* (payments, orders, pending_operation, update_gst, void, edit_invoice_payment, stock_take) · whatsapp_client · invoice_pdf · invoice_delivery · company_export · reports/* (registry, ledger, registers, aging, period, xlsx_common, pdf_common, statuses) · onboarding_flow · activation · gst · money_format · sales_impact_parser.

**API surface:** `/webhooks/whatsapp`, `/onboard`, public marketing site, `/health`, signed `/export`, `X-API-Key` admin API (companies, dealers, suppliers, products, invoices, payments, imports, cashflow, briefing, followup, daily_snapshot, scheduler, faq, export), and the session-authed `/dashboard/*` portal.

**Deployment:** Render web service (API + scheduler) + Neon Postgres (persistent) + Vercel static marketing site. Local dev uses a separate Docker Postgres.

---

## What remains to do

> ⭐ = explicitly requested next / high customer value. Items reference existing code where a foundation already exists to build on.

### ⭐ Multilingual support (Hindi / Odia; language × script, Romanized-first)
Locale model = **language × script** with Romanized variants as first-class, recommended defaults for Indian WhatsApp (`en`, `hi-Deva`, `hi-Latn`, `or-Orya`, `or-Latn`). New `app/i18n/` package: `Locale` registry + `resolve_locale` + `t()` (English is the source of truth and fallback); 5 hand-authored catalogs (~280 keys each, non-English marked **DRAFT for founder review**), parity + placeholder-safety enforced by `tests/test_i18n.py`. Stored in the existing `companies.preferred_language` (migration `a7f3e21c9b40` normalizes legacy free text → locale codes). All work verified against a Neon test branch, ruff clean.
- [x] **Drive LLM narration + assistant replies in the chosen language** — `assistant.py` / `briefing.py` fed `Locale.narration_instruction` (incl. explicit "Romanized Hindi/Odia, Latin letters" wording).
- [x] **Language switch command** — `change language` / `change script` / `script` re-enters the same two-step onboarding language/script picker; onboarding now asks language **first**.
- [x] **Localize the deterministic surfaces** — every deterministic WhatsApp surface now renders in the company's locale (money/names/dates interpolated, never translated; trigger keywords stay English): the interactive **menu** (row ids stay English commands), all 4 **numbered reports** (via `Snapshot.locale`), the full **`instant_reports.py`** replies, the **help text**, the entire guided **onboarding** flow (language picker + all business-setup steps), the guided **write-workflows** (`workflows/*` — record payment, create order, update GST, add/delete/update product) + `pending_operation` confirmations, the **follow-up** conversation (`followup.py`), distributor-facing **notifications** (`notifications.py`), the **evening brief** (`evening_brief.py`), and the briefing menu-prompt footer. _Remaining sliver:_ the briefing's stale-data banner + confidence-indicator footers are still English (small scaffolding around the already-localized LLM body).
- [x] **Unicode invoice PDF** — bundled OFL Noto Sans + Noto Sans Devanagari + Noto Sans Oriya (regular+bold) under `app/assets/fonts/`; `invoice_pdf.py` now renders regional-script dealer/product/business names and the real ₹ glyph, choosing the font **per cell by script** (fpdf2's global `set_fallback_fonts` state-leaked onto later Latin cells and blanked them). `_latin1()` + core Helvetica stays as a graceful fallback when a font file is absent, so a valid PDF is always produced. Fonts are SIL OFL 1.1 (redistributable) so they're committed.
- [x] **Numerals & date formatting** — Indian digit grouping already in `money_format.py`; amounts/dates are interpolated, never translated.

### ⭐ Reports & downloadable statements — Vyapar / Tally style — complete (2026-07-19)
Today there is one all-time Excel workbook (`company_export.py`) plus six new period-scoped reports, all dispatched through one extended signed-link endpoint via `app/services/reports/registry.py`'s `REPORTS` table (new `app/services/reports/` package: `xlsx_common`, `pdf_common`, `period`, `statuses`, `ledger`, `registers`, `aging`, `registry`). GST report = a GSTR-1-*style* register (taxable value/rate/GST amount + rate-wise summary), not a filing-ready CGST/SGST/IGST split — Dealer/Supplier have no state/place-of-supply field, confirmed out of scope for this phase.
- [x] **Month-wise / date-range filtering** — `report`/`format`/`from`/`to`/`month`/`party` query params on the existing signed `/export/{company_id}/{expires_at}/{signature}` route (`app/api/export.py`); signature still only covers `company_id:expires_at`, unchanged. No params = identical byte-for-byte behavior to the original all-time workbook.
- [x] **Party ledger statement** — opening → running balance → closing balance (`reports/ledger.py`), cross-checked against `calculate_party_outstanding` in tests. WhatsApp "ledger <name>" (new `app/services/party_lookup.py::find_party`, shared with `_get_party_balance`'s "balance <name>").
- [x] **Payment / receipt register** by month, Receipts/Payments/Net cash-movement totals kept separate from any accrual figure (`reports/registers.py`).
- [x] **GST reports** — sales/purchase register, per-invoice-line, plus a rate-wise summary sheet (`reports/registers.py`); doubles as the "sales & purchase registers" bullet below rather than building both twice.
- [x] **Day book** (all invoices+payments per period, `reports/registers.py`) and **outstanding aging report** bucketed Not Due / 0-30 / 31-60 / 61-90 / 90+ (`reports/aging.py`).
- [x] **PDF versions** — ledger + aging report only (the two a distributor would print/forward), reusing `invoice_pdf.py`'s per-cell Unicode-script font logic (now factored into `reports/pdf_common.py`, both modules byte-identical to before). Same signed-link mechanism, `format=pdf`.
- [x] **WhatsApp triggers** for every report ("ledger <name>", "gst report", "sales register", "purchase register", "payment register", "day book", "outstanding report"), current-month default; aging is always as-of-today. `/help` updated in all 5 locale catalogs.

### ⭐ Proactive early-warning alerts (7 days ahead)
The snapshot already computes 7-day expected collections/payments and a `cash_deficit` flag, but nothing sends a *forward-looking* heads-up. Wire scheduled predictive alerts on top of the existing engine:
- [ ] **Cash-shortage forecast** — "⚠️ Cash is projected to go negative in ~N days (expected out ₹X > cash+in ₹Y)"; a scheduled `NotificationEngine` rule using the 7-day window, deduped like the existing rules.
- [ ] **Stock-out forecast** — using sales velocity (units sold / period from `InvoiceItem`) vs current `stock_quantity`, alert "Product X will run out in ~N days at current sales pace." Also covers the unbuilt V0.3 "inventory alerts" item.
- [ ] **Overdue-about-to-happen** — nudge before an invoice's due date, not only after (complements the existing after-due follow-up flow).
- [ ] Fold all three into the morning briefing as a "Watch this week" section, and as standalone push alerts.

### Onboarding improvements — complete (2026-07-19)
All four items below are done — see Timeline for both sessions' detail.
- [x] **Seed from an existing export** — website wizard step (before WhatsApp starts) uploading a dealer-invoices and/or supplier-invoices file through a new public `POST /onboard/{id}/import`, reusing `ImportEngine.run_import` unchanged. Product decision: website, not WhatsApp — a form recovers from a bad upload far more gracefully than a chat conversation would.
- [x] **Per-party opening balances** — already built, this checkbox was just stale. `onboarding_flow.py`'s `receivable_ask`/`receivable_dealer`/`receivable_amount`/`receivable_date` and the mirrored `payable_*` states (looping "which dealer/supplier, how much, due date" until "done") have captured this since the very first onboarding commit (`954af50`, 2026-07-05) — predating this TODO line (added 2026-07-18) by two weeks. The parenthetical ("today only company opening cash is collected") was never true of the code; corrected here rather than left to mislead the next read of this file.
- [x] **Self-serve reconciliation check** — the import wizard step shows dealer/supplier/invoice counts + receivable/payable totals (`summarize_business_data()`, reusing `calculate_outstanding_for_company`) immediately after import, before the distributor ever reaches Activate — the AP BIOCARE-style reconciliation, made self-serve and moved to the point of import rather than left to be eyeballed later. WhatsApp onboarding then skips any section already satisfied by the import (with a short "found N from your import" note) instead of re-asking.
- [x] **Resume/partial onboarding** — complete (2026-07-19, see Timeline). The flow was already resumable by construction (durable `Company` state, not a session); this adds visibility (`progress`/`status` — an 8-section checklist + % complete) and an explicit fresh-start escape hatch (`restart`, confirm-gated — wipes what's been entered so far and starts the 8 steps over) for a distributor who'd rather not continue with partial data than be forced to.

### Interaction & input improvements
- [ ] **Voice notes** — accept WhatsApp audio, transcribe, and route through the same handlers (huge for low-literacy operators; SPEC lists voice as Future).
- [ ] **Invoice photo → OCR** — accept an image of a paper invoice and pre-fill an order/invoice for confirmation (SPEC V0.3/Future).
- [ ] **Dealer-facing reminders** — send overdue reminders directly to the *dealer's* WhatsApp (with the distributor's consent), not only to the distributor.
- [x] **Richer confirmations** — delivered for every new correction workflow below (edit/void/stock-take all show old→new before committing); still not retrofitted onto the original `create_order`/`record_payment` flows, which don't have a "before" state to show.
- [ ] **Delivery/read status surfaced** to the distributor for messages they trigger (data is already captured in `NotificationLog`).

### Edit / correction / data-management — complete (2026-07-19)
All four built as guided WhatsApp workflows reusing the existing architecture (`PendingOperation` confirm gate for money-affecting writes, write-immediately for attribute edits — matching `update_product`'s existing tier), with a generic `BusinessEvent`-based audit trail (`{field, old, new, reason}`, `reason` optional) on every one. See `app/services/workflows/void_flow.py`, `edit_flow.py`, `party_flow.py`'s edit-dealer/edit-supplier additions, `stock_take_flow.py`, and their `app/services/writes/*` counterparts.
- [x] **Undo / void** a payment or order — targets only the single most-recently WhatsApp-recorded one (`"undo payment"`/`"undo order"`); voiding an order with a payment already against it is refused (void the payment first). Soft-cancels the invoice (`InvoiceStatus.Cancelled` — the enum value existed but nothing ever set it before this) rather than hard-deleting, restores stock.
- [x] **Edit an invoice/payment** (amount, date, party) with a full audit trail — **deliberately scoped to safe cases only** after a design review cut a more "clever" automated FIFO-reallocation version (release money from one invoice, re-spill it across a party's other open invoices) for being hard to explain and the highest-risk surface in the whole feature. An invoice with *any* payment recorded is refused outright, regardless of field — points to void-and-recreate instead. A payment's amount edit is bounds-checked only against its own invoice's total; it never moves money to a different invoice. Cross-party payment reassignment is out of scope this iteration, to reconsider only if pilot users actually ask for it.
- [x] **Edit party details over WhatsApp** — phone, credit limit, payment terms, GSTIN, for both dealers and suppliers (`Supplier` gained a `gst_number` column — it had none before, only `Dealer` did). New `validate_gstin()` (format + mod-36 checksum) in `app/services/gst.py`, also closing out part of the "GSTIN format validation" item below.
- [x] **Stock-take / bulk stock adjustment** flow — loops over multiple products in one session, accepting either an absolute recount (`40`) or a signed delta (`+15`/`-3`); negative resulting stock is flagged, not blocked (same convention `create_order` already uses).
- [ ] **Deferred: edit an already-paid invoice/payment beyond the safe cases** — today, editing an invoice with any payment recorded is refused outright (points to void-and-recreate), and a payment's amount edit can never move money to a different invoice. An earlier design pass sketched what real support would need: release the excess/freed amount from the edited invoice or payment, then re-run `allocate_payment_fifo` (`app/services/importer/payment_row.py`) against the party's other open invoices to re-place it — reusing the exact function CSV import and `record_payment` already call, no new allocation engine needed. Cut for the first release as the highest-risk surface (hard to explain to a distributor when money silently moves between invoices) — revisit only once pilot users actually hit the "void and recreate" wall often enough to justify it. Cross-party payment reassignment (moving a payment to a different dealer/supplier entirely) was dropped from scope even further back and would need the same reallocation primitive plus a decision on where a payment "belongs" when it was originally split across invoices.

### Validation & data-integrity
- [ ] **Duplicate-entry warning at capture time** — warn on a likely-duplicate invoice/payment before writing (ties to the known `(party, date, amount)` idempotency gap below).
- [ ] **Credit-limit breach warning** — when an order would push a dealer over their `credit_limit`, flag it in the confirm step (limit is already stored and used in risk scoring).
- [x] **GSTIN format validation** — 15-char format + mod-36 checksum (`validate_gstin()`, `app/services/gst.py`), enforced on the new edit-dealer/edit-supplier GSTIN entry point. Not yet retrofitted into dealer-creation (`party_flow.py`'s add-dealer) or the CSV importer — deliberately scoped to the one entry point that motivated it.
- [ ] **Phone normalization/validation** to E.164 at every entry point (webhook already normalizes; entry forms/flows should too).
- [ ] **Consistent amount/quantity guards** — extend the existing negative/zero rejections uniformly across all write flows.

### Deployment / ops (verify & finish)
- [ ] **Confirm production is redeployed** with the latest `master` and that Alembic migrations have been run on the Neon prod DB (it's a manual/one-shot step; local DB is at head `f3a9c1d7b268`).
- [ ] **Set production env vars** correctly — notably `PUBLIC_BASE_URL` (local `.env` currently points to `http://localhost:8000`; prod must be the real Render URL for export/onboarding links to work).
- [x] **Always-on scheduler** — solved via external cron rather than an always-on instance: `.github/workflows/keep-alive.yml` pings `/health` and `POST /admin/scheduler/tick` every 10 minutes (comfortably inside Render's 15-minute idle timeout), so the daily 8am dispatch fires on schedule even when no real traffic wakes the process first.
- [ ] **CI**: still no GitHub Actions (or similar) pipeline running the test suite on push/PR — the only workflow that exists is the keep-alive/scheduler-tick cron above. Tests do now run against an isolated `<dbname>_test` database with a production tripwire (fixed 2026-07-19 after a real incident, see Timeline), so the old "shared dev DB with accumulated fixture rows" problem is resolved locally — but there's still no automated run on every change.

### Meta / WhatsApp approvals (external, can't verify from repo)
- [x] Confirm the **`opsgenie_welcome`** template is Meta-approved (now set in `.env`; was a `hello_world` stub earlier). Approved (Active - Quality) and confirmed sending in practice.
- [ ] Confirm the **`invoice_document`** template (document header) is Meta-approved so dealer PDF delivery works end-to-end (now set in `.env`; delivery is fail-open, so an unapproved template just skips silently). First approval (2026-07-19) had the header component set to **Text** (literal text "Document") instead of **Document** format — `send_invoice_document()` always sends a `document`-type header parameter (`whatsapp_client.py:150-161`), so every PDF send would have failed silently against that version. Fixed the header format to Document in Meta's editor and resubmitted (2026-07-19) — back to **Pending** review. Once it flips to Active, still need one live end-to-end test (real order → real dealer phone → PDF actually arrives, or check `NotificationLog.delivery_status`/`whatsapp_message_id`) before checking this off.

### V0.3 features not yet built
- [ ] **Marketing broadcast** to the dealer network.
- [ ] **Business analytics / trend reporting** beyond today + month-to-date (e.g. week-over-week, dealer trends) — overlaps the reports section above.
- [ ] **Inventory alerts** — covered by the ⭐ 7-day stock-out forecast above (stock is tracked now, alerts are not).

### Known gaps / tech debt (deliberately deferred, pilot-acceptable)
- [ ] **Payment idempotency** keys on `(party, date, amount)` — a genuine same-day, same-amount duplicate payment can still be dropped as a "re-import".
- [ ] **No payment gateway** — "buying a subscription" = the founder manually activating (intentional for pilot; self-serve accounts are free today despite the ₹999/mo copy on the onboarding page).
- [ ] **Party de-dup** — `find_or_create_party` matches case-insensitively but two concurrent creates of a brand-new name could race into duplicates (not a concern at serialized pilot scale).
- [ ] **Scheduler retry re-send** — during the retry hour the retry *send* re-fires each 15-min tick (harmless for a truly-failed send; only a "succeeded-at-Meta-but-timed-out" edge could double-deliver). Founder alerting is now correctly deduped once/day.

---

## Working principles (how this project is built)
- **Phase discipline** — deterministic business engine solid and real-data-validated before any AI; money math never touches the LLM.
- **Writes are guided workflows**, not AI tool-calls — a confirm gate (`PendingOperation`) re-derives the write fresh at confirm time.
- **No blended financial metrics** — accrual (margin) and cash-basis (collections/payments) are always reported separately.
- **Never commit generated output** (Excel/PDF/static site are built at request/deploy time).
- **Before closing work**: full pytest green + `ruff check` clean + a structured multi-angle review, then re-verify against the real AP BIOCARE reconciliation figure.
