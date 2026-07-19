# OpsGenie — Project Status

_Last updated: 2026-07-18 (multilingual: all deterministic WhatsApp surfaces localized across 5 locales — commit `14d11a6`)_

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

**System size today:** 17 ORM table models · 33 Alembic migrations (single linear head, DB at head `a7f3e21c9b40`) · 54 test files / **~665 tests** (LLM-network tests skip without a key) · ruff clean. Verified green against Neon **per test-file/chunk** (the multilingual work was validated file-by-file on Neon); a single-process full-suite marathon over the remote Neon endpoint hits transient socket drops (NullPool opens a fresh SSL connection per query — a CI infra concern, not a code one; see the CI item under Deployment/ops).

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

---

## Current system inventory

**Models (17 tables):** company, dealer, supplier, product, invoice, invoice_item, payment, business_event, activity_timeline, morning_briefing, import_log, notification_log, conversation_turn, pending_operation, faq, daily_business_snapshot, cash_snapshot _(modeled but unused — per SPEC, outstanding is always computed from invoices+payments)_.

**Core services:** snapshot · party_outstanding · party_lookup · recommendations · priority_actions · briefing · llm/* (6 providers + factory) · assistant + agent/* (read tools, runner, money_guard) · command_router · query_menu · instant_reports · followup · notifications · scheduler · daily_snapshot · evening_brief · importer/* · workflows/* (payment, order, product, gst) · writes/* (payments, orders, pending_operation, update_gst) · whatsapp_client · invoice_pdf · invoice_delivery · company_export · reports/* (registry, ledger, registers, aging, period, xlsx_common, pdf_common, statuses) · onboarding_flow · activation · gst · money_format · sales_impact_parser.

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

### Onboarding improvements
- [ ] **Seed from an existing export** — let a new distributor upload their Tally/Vyapar file during onboarding to bootstrap dealers/suppliers/invoices, instead of typing everything (importer already exists; wire it into the onboarding flow).
- [ ] **Per-party opening balances** — capture each dealer/supplier's existing outstanding at onboarding so historical balances are correct from day one (today only company opening cash is collected).
- [ ] **Self-serve reconciliation check** — after seeding, show the distributor a computed outstanding per party and ask them to confirm it matches their books (the AP BIOCARE ₹3,19,828 check, made self-serve).
- [ ] **Resume/partial onboarding** — let a distributor pause and continue later; show a progress indicator.

### Interaction & input improvements
- [ ] **Voice notes** — accept WhatsApp audio, transcribe, and route through the same handlers (huge for low-literacy operators; SPEC lists voice as Future).
- [ ] **Invoice photo → OCR** — accept an image of a paper invoice and pre-fill an order/invoice for confirmation (SPEC V0.3/Future).
- [ ] **Dealer-facing reminders** — send overdue reminders directly to the *dealer's* WhatsApp (with the distributor's consent), not only to the distributor.
- [ ] **Richer confirmations** — show before/after state on every write ("stock 40 → 30", "outstanding ₹3,19,828 → ₹2,70,478").
- [ ] **Delivery/read status surfaced** to the distributor for messages they trigger (data is already captured in `NotificationLog`).

### Edit / correction / data-management
- [ ] **Undo / void** a just-recorded payment or order (mistakes happen; there is no reversal path today — only create).
- [ ] **Edit an invoice/payment** after creation (amount, date, party) with a full audit trail.
- [ ] **Edit party details over WhatsApp** — phone, credit limit, payment terms, GSTIN (currently only via admin API/dashboard).
- [ ] **Stock-take / bulk stock adjustment** flow (count correction, not just per-sale decrement).

### Validation & data-integrity
- [ ] **Duplicate-entry warning at capture time** — warn on a likely-duplicate invoice/payment before writing (ties to the known `(party, date, amount)` idempotency gap below).
- [ ] **Credit-limit breach warning** — when an order would push a dealer over their `credit_limit`, flag it in the confirm step (limit is already stored and used in risk scoring).
- [ ] **GSTIN format validation** — the 15-char India GSTIN checksum, on entry.
- [ ] **Phone normalization/validation** to E.164 at every entry point (webhook already normalizes; entry forms/flows should too).
- [ ] **Consistent amount/quantity guards** — extend the existing negative/zero rejections uniformly across all write flows.

### Deployment / ops (verify & finish)
- [ ] **Confirm production is redeployed** with the latest `master` (through `def0c1c`) and that Alembic migrations have been run on the Neon prod DB (it's a manual/one-shot step; local DB is at head).
- [ ] **Set production env vars** correctly — notably `PUBLIC_BASE_URL` (local `.env` currently points to `http://localhost:8000`; prod must be the real Render URL for export/onboarding links to work).
- [ ] **Always-on scheduler**: APScheduler runs inside the web process, so on a spin-down free tier, ticks only fire while awake. For a real always-on daily 8am push, use an always-on instance or a dedicated worker (or drive `POST /admin/scheduler/tick` from an external cron).
- [ ] **CI**: tests currently run only locally against a shared dev DB (with accumulated fixture rows, never cleaned). No CI pipeline or isolated test DB yet.

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
