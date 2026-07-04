# Document 1 — Product Requirements Document (PRD)

## 1. Vision

### Mission

Build a WhatsApp-first daily financial operating assistant for B2B distributors that converts existing business records into daily operational decisions — delivered through WhatsApp, requiring zero learning curve.

### The Core Insight

Distributors don't get blindsided because they lack data. They get blindsided because their data never gets converted into a decision fast enough. OpsGenie fixes that gap every morning.

### The Product Loop

This loop is the actual product. Everything else is infrastructure supporting it.

Business event occurs → Business engine processes it → All downstream state updates → Business snapshot reflects new reality → Recommendation engine runs → Morning briefing delivered → Distributor takes action → New business event occurs → repeat.

The morning briefing is the output of this loop, not the product itself. The moat is the loop running daily with real data accumulating over months.

---

## 2. What OpsGenie Is Not

OpsGenie is not an ERP. OpsGenie is not accounting software. OpsGenie is not a Tally replacement. OpsGenie is not inventory management software. OpsGenie is not a CRM. OpsGenie is not GST filing software. OpsGenie is not payroll software. OpsGenie is not a general AI chatbot.

OpsGenie answers one question every morning: given everything happening in your business today, what should you do next.

---

## 3. Target Customer

B2B distributors who already maintain invoices, use accounting software, manage multiple dealers, and face cash flow surprises monthly or more often. Examples: FMCG distributors, pharma distributors, poultry and agricultural product distributors, wholesale supply chain businesses.

Target characteristics: uses Tally or Vyapar, has a Tally operator or accountant managing records, handles 20 to 50 dealer accounts, has multiple supplier relationships, faces cash shortfalls monthly or more often, uses WhatsApp as their primary communication tool, has no time or willingness to learn new software.

Not targeting: retail kirana stores, general SMBs, businesses without existing invoice records, businesses dominated by small cash transactions with no invoice trail.

---

## 4. Core Problem

A distributor's financial reality exists in Tally. Their daily decisions happen on WhatsApp and phone calls. Nothing connects the two. OpsGenie connects the data that exists to the decisions that need to be made, every morning, before the day begins.

---

## 5. Product Philosophy

Everything operational happens through WhatsApp. The website exists only for signup, subscription, and settings. Every number in every briefing must be traceable to a real invoice or payment record. The product earns trust through transparency, not through sounding confident.

### Engineering Principle — This Never Changes

LLMs never own business state. LLMs never calculate money. LLMs never update records. LLMs never decide recommendations. LLMs only understand language and generate natural responses. Everything else belongs to deterministic code.

Never ask the user for information the database already knows. When input is ambiguous, query the database for likely matches and present the best option for confirmation rather than asking an open question.

If you replace the LLM provider with any other model tomorrow, every number and every recommendation must remain identical. Only phrasing may change. If replacing the model changes a business decision, the architecture is wrong.

---

## 6. Feature Roadmap

### V0.0 — Proof of Value (Build This First)

Upload CSV from Tally → system generates morning briefing → founder sends via WhatsApp manually.

Nothing else. No onboarding flow. No subscription system. No notification engine. No query menu. No dashboard. Founder manually creates companies via direct database insert. Pilot users are set active manually.

This version answers one question: is the briefing itself valuable enough that distributors want it every morning?

### V0.1 — Operational Product

Numbered WhatsApp query menu for on-demand reports. Automated morning briefing scheduler. Invoice due date follow-up flow — when an invoice reaches its due date, WhatsApp asks "Has Ram Traders paid INV-1047 for ₹49,350?" and updates status based on response. Notification engine for overdue dealers and supplier payment reminders. Confidence indicator on every briefing showing data freshness.

### V0.2 — OpsGenie Becomes Source of Truth

Invoice creation directly through WhatsApp. Payment update through WhatsApp text. OpsGenie replaces the daily CSV dependency. Data is always fresh because OpsGenie generated it.

### V0.3 — Intelligence and Expansion

Free-form AI Q&A built from questions observed during V0.1 pilot. Inventory alerts derived from sales data once invoice creation exists. Marketing broadcast to dealer network. Business analytics and trend reporting.

### Future

Real-time Tally API integration. Embedded working capital loans based on accumulated transaction history. OCR for invoice photos. Voice assistant.

---

## 7. Customer Journey

### Pilot Path — V0.0 and V0.1

No subscription payment required. Founder creates company via direct database insert. Founder collects opening balance, dealer list with outstanding amounts, supplier list with payment terms. Tally operator sends daily CSV export to founder via WhatsApp. Founder uploads file, system generates briefing, founder sends to distributor via WhatsApp by 8am. Founder tracks open rate, action rate, and avoided financial surprises daily.

### Invoice Due Date Follow-Up Flow

Invoice created and stored as Pending → due date arrives → system sends WhatsApp message: "Has Ram Traders paid INV-1047 for ₹49,350?" → distributor replies Yes, Partial, or Not Yet → if Yes, invoice closed, ledger updated, cash updated, tomorrow's briefing updated → if Partial, distributor states amount, partial payment recorded, remaining balance stays pending → if Not Yet, system asks expected payment date, updates the invoice, flags in next briefing.

This keeps data fresh without requiring the distributor to open any app. The system comes to them.

### Self-Serve Path — V0.2 Onward

User visits website. Creates company. Pays subscription. Receives WhatsApp onboarding. Completes setup through guided WhatsApp conversation. Daily operations begin automatically.

---

## 8. Data Freshness Strategy

Every evening, the Tally operator exports that day's transactions and sends the file to OpsGenie. The system processes incremental updates only. The morning briefing is generated at 8am from the most recently imported data.

Data completeness score tracked per distributor: days with complete data received divided by total days active. If data not received in 24 hours, founder is notified internally. A briefing from stale data includes a clear notice stating how many days old the data is.

In V0.2, distributor creates invoices and records payments directly through WhatsApp. No export required. Data always current.

---

## 9. Invoice Lifecycle

### V0.1 Lifecycle — Import Based

CSV exported → founder uploads → system validates and normalizes → invoice created → receivable recorded → cash position updated → business event written → morning briefing updated → due date arrives → WhatsApp asks if paid → distributor confirms → invoice closed → outstanding reduced → cash updated → business event written → tomorrow's briefing updated.

### V0.2 Lifecycle — WhatsApp Native

Distributor messages invoice details → system parses and confirms → PDF generated → sent to dealer → invoice stored → receivable recorded → cash updated → business event written → morning briefing updated → due date arrives → WhatsApp asks if paid → same closure flow as above.

### Invoice Status Lifecycle

Draft → Sent → Pending → Partially Paid → Paid → Overdue → Cancelled.

Every status change triggers a business event. Every business event updates the cash position and business snapshot. Nothing is stale.

---

## 10. What Is Explicitly Out of Scope for V0.0 and V0.1

Invoice creation through WhatsApp. Inventory tracking. Order management. OCR. Voice assistant. Marketing broadcast. Real-time Tally integration. Mobile app. Free-form AI Q&A. GST report generation. Subscription billing system. Self-serve onboarding. Dashboard or web interface.

These are deferred. Each gets built after the preceding layer is proven valuable by real distributors.

---

## 11. Milestone Plan

### Week 1 — Foundation

Project setup. Database schema. Company creation via admin endpoint. Dealer and supplier management endpoints.

### Week 2 — Core Business Logic

Invoice management and lifecycle. Payment management. Business events writer. Dealer outstanding calculation.

### Week 3 — Intelligence Layer

Business snapshot generator. Recommendation engine. Morning briefing generator with LLM narration.

### Week 4 — Delivery

WhatsApp webhook. Scheduled morning briefing. Invoice due date follow-up flow. Manual pilot begins with first distributor.

### After Pilot Starts — V0.1 Additions

Numbered query menu. Notification engine. Confidence indicator on briefings. Stale data warnings.

---

## 12. V0.0 Success Criteria

V0.0 succeeds if within 2 weeks across 2 to 3 distributors: distributor opens the briefing daily, distributor takes at least one action based on the briefing, distributor asks "can you send this tomorrow too."

If that happens, build V0.1. If it does not happen, diagnose which assumption broke before building further.

## V0.1 Success Criteria

Within 30 days across 3 to 5 distributors: 70% or more report monthly or more frequent cash surprises. 80% or more data completeness score. 70% or more daily briefing open rate. 50% or more of briefings lead to a real action taken. At least 2 distributors say unprompted they would miss this. At least 1 says they would pay ₹1,000 per month. At least 1 real financial surprise was genuinely avoided because of the briefing.

---

## 13. Long-Term Vision

OpsGenie becomes the WhatsApp-first Business Operating System for B2B distributors in emerging markets. Every distributor runs daily operations through a single WhatsApp number without opening a separate application.

The guiding principle: run your business through WhatsApp. OpsGenie organizes the data, tracks operations, and helps you make better daily decisions.

---

---

# Document 2 — Technical Design Document (TDD)

## 1. Architecture Overview

```
Sources
CSV | Excel (V0.0 and V0.1) | WhatsApp (V0.2) | OCR (V0.3) | Tally API (Future)
↓
Normalizer → Validator
↓
Business Engine
(processes events, updates all downstream state)
↓
Business Snapshot Generator
(single source of truth, recalculated on staleness flag)
↓
Recommendation Engine
(pure Python rules, no LLM)
↓
AI Narration Layer
(LLM Provider — language only, never business logic)
↓
Notification Engine
(pure rules, no LLM)
↓
Delivery Layer
(WhatsApp)
```

One AI component. Everything else deterministic. Every output traces to a specific rule or calculation.

---

## 2. Engineering Principles

LLMs never own business state. LLMs never calculate money. LLMs never update records. LLMs never decide recommendations. LLMs only understand language and generate natural responses. Everything else belongs to deterministic code.

Never ask the user for information the database already knows. When input is ambiguous, query for likely matches and confirm rather than asking an open question.

If you replace the LLM provider with any other model, every number and every recommendation must remain identical. Only phrasing may change.

Every briefing number must be traceable to a specific database record. No estimates, no smoothing.

All business rules live in the Recommendation Engine, not in prompts.

Every significant action writes an immutable BusinessEvent record before returning.

Do not optimize for scale until scale exists. Simplicity first. Refactor when real usage demands it.

---

## 3. Database Schema

### Companies
id UUID PK, business\_name, owner\_name, whatsapp\_number unique, email, business\_type, preferred\_language, subscription\_active boolean default true, opening\_balance decimal, created\_at

Note: subscription\_active is a simple boolean set manually for pilot users. No Stripe, no Razorpay, no expiry logic in V0.0 or V0.1.

### Dealers
id UUID PK, company\_id FK, name, phone, address, gst\_number, payment\_terms\_days, credit\_limit, notes, created\_at

### Suppliers
id UUID PK, company\_id FK, name, phone, payment\_terms\_days, credit\_limit, notes, created\_at

### Products
id UUID PK, company\_id FK, name, unit, selling\_price, purchase\_price, created\_at

Note: minimum\_stock and inventory tracking are excluded from V0.1. Products table exists for V0.2 invoice line items.

### Invoices
id UUID PK, company\_id FK, invoice\_number, direction enum (receivable, payable), dealer\_id FK nullable, supplier\_id FK nullable, invoice\_date, due\_date, subtotal decimal, gst\_amount decimal, total\_amount decimal, status enum (Draft, Sent, Pending, Partially\_Paid, Paid, Overdue, Cancelled), source enum (csv\_import, whatsapp), created\_at, updated\_at

### InvoiceItems
id UUID PK, invoice\_id FK, product\_id FK nullable, description, quantity decimal, unit\_price decimal, line\_total decimal

### Payments
id UUID PK, company\_id FK, invoice\_id FK, amount decimal, payment\_date, method, source enum (csv\_import, whatsapp), created\_at

### CashSnapshots
id UUID PK, company\_id FK, opening\_balance decimal, recorded\_at, recorded\_by

### BusinessEvents
id UUID PK, company\_id FK, event\_type enum (invoice\_created, invoice\_status\_updated, payment\_received, supplier\_paid, reminder\_sent, dealer\_called, briefing\_sent, data\_imported, follow\_up\_sent, follow\_up\_responded), entity\_type, entity\_id UUID, payload JSONB, created\_at, created\_by. Append-only. Never updated after insert.

### ActivityTimeline
id UUID PK, company\_id FK, entity\_type enum (dealer, supplier), entity\_id UUID, event\_type enum (invoice\_created, payment\_received, reminder\_sent, dealer\_called, briefing\_mentioned, overdue\_flagged, follow\_up\_sent, follow\_up\_responded), amount decimal nullable, notes text, event\_timestamp. Append-only.

### MorningBriefings
id UUID PK, company\_id FK, generated\_text text, snapshot\_json JSONB, confidence\_score decimal, data\_freshness\_hours integer, sent\_at, delivery\_status

### ImportLogs
id UUID PK, company\_id FK, filename, source\_format, imported\_at, rows\_processed integer, rows\_succeeded integer, rows\_failed integer, error\_detail\_json JSONB

### NotificationLogs
id UUID PK, company\_id FK, notification\_type, recipient\_whatsapp, message\_text, sent\_at, delivery\_status

Note: DealerLedger is not a stored table in V0.0 and V0.1. Outstanding balance is calculated from Invoices and Payments on each query. Add a materialized DealerLedger table only when query performance becomes a real problem, not before.

---

## 4. Core Services

### ImportService

Accepts CSV or Excel file. Detects column mapping against known Tally and Vyapar export formats. Validates required columns before processing any rows. Normalizes column names, date formats, and amounts. Validates each row — missing amounts, invalid dates, duplicate invoice numbers, payments exceeding invoice totals. Writes clean records to database. Triggers BusinessEngine for each created record. Returns import summary. Logs to ImportLogs. One bad row never fails the whole import.

### BusinessEngine

Central processor. Every data change flows through here. Receives event type and entity reference. Executes the correct downstream update sequence.

Invoice created: recalculate dealer outstanding from Invoices and Payments, mark snapshot stale, write to ActivityTimeline, write to BusinessEvents.

Payment received: update invoice status, recalculate dealer outstanding, update cash position, mark snapshot stale, write to ActivityTimeline, write to BusinessEvents.

Follow-up responded — paid: close invoice, recalculate outstanding, update cash, mark snapshot stale, write events. Follow-up responded — partial: record partial payment, update invoice status, mark snapshot stale, write events. Follow-up responded — not yet: update expected payment date on invoice, mark snapshot stale, write events.

### BusinessSnapshotService

Single function build\_snapshot(company\_id) returning complete structured state. Regenerates only when marked stale by BusinessEngine. Result cached with staleness flag.

Snapshot contains: cash available today (opening balance plus all payments received minus all payments made since opening balance recorded), expected collections next 7 days by dealer, expected payments next 7 days by supplier, net cash position with deficit flag and amount, list of overdue dealers with days overdue and count of late payments in last 6 months (calculated from Invoices and Payments), list of upcoming supplier payments with urgency flag, data freshness timestamp, data completeness score, confidence score.

### DealerOutstandingCalculator

Simple function called within BusinessEngine and BusinessSnapshotService. Calculates outstanding for a dealer as: sum of total\_amount for all receivable invoices in status Pending, Partially\_Paid, or Overdue, minus sum of all payments recorded against those invoices. No stored DealerLedger table. Pure calculation from Invoices and Payments.

### RecommendationEngine

Pure Python. No LLM. Reads snapshot. Outputs ranked action list as structured JSON.

Rules in priority order: if net cash position negative, add cash deficit warning as priority 1 with deficit amount and suggested collection target. For each dealer with outstanding above threshold and overdue more than 15 days, add call action ordered by amount descending. For each supplier payment due within 48 hours where cash insufficient, add critical payment warning as priority 1. If data freshness exceeds 24 hours, add stale data warning. For each dealer overdue between 5 and 15 days, add follow-up reminder ordered by amount.

Each action item contains: priority integer, action\_type, entity\_name, entity\_id, amount, reason, days\_overdue. The LLM provider receives this list and converts it to natural language. It never modifies priority, amounts, or entity names.

### BriefingService

Runs at 8am daily via APScheduler. Calls BusinessSnapshotService. Calls RecommendationEngine. Assembles structured payload. Calls the configured LLM provider with system prompt: "You are a WhatsApp financial assistant for a B2B distributor. Convert the following structured business data into a brief, friendly, sectioned WhatsApp morning briefing in [language]. Sections: Cash Position, Attention Required, Today's Actions. Every number comes from the data provided — do not add, estimate, or modify any figure. Keep each section to 3 to 5 lines. Use simple language readable in 30 seconds on a phone screen." Appends confidence indicator showing data freshness. Sends via WhatsApp. Logs to MorningBriefings with full snapshot JSON.

### InvoiceDueDateFollowUpService

Runs daily at a configured time, separate from the morning briefing. Queries all invoices where due\_date equals today and status is Pending or Partially\_Paid. For each, sends WhatsApp message to the distributor asking for payment confirmation. Logs follow-up to ActivityTimeline and BusinessEvents. Awaits response via the WhatsApp webhook. Routes response to BusinessEngine based on distributor reply.

### NotificationEngine

Pure Python rules. No LLM. Runs on schedule and on event triggers. Supplier payment due within 24 hours: send WhatsApp reminder. Dealer outstanding flagged High Risk and no follow-up in 3 days: send prompt to distributor. Data not received in 24 hours: send internal alert to founder's number. Morning briefing delivery failed: retry at 9am, alert founder if retry fails. All notifications logged to NotificationLogs.

### ActivityTimelineService

Append-only writer called by BusinessEngine on every significant event. Provides fast per-dealer and per-supplier event history used by AI context and recommendation engine to avoid repeating recently acted-on suggestions.

---

## 5. Technology Stack

Python 3.11, FastAPI, SQLAlchemy 2.0 async, Alembic for migrations. PostgreSQL 16 on Neon free tier for pilot. Redis via Upstash for snapshot staleness flags and session state. APScheduler inside FastAPI lifespan for 8am briefing and notification schedules. Pluggable LLM provider (Anthropic Claude, Google Gemini, Groq, or OpenRouter) with automatic failover across configured providers, selected via LLM\_PROVIDER/LLM\_FALLBACKS — claude-haiku-4-5, gemini-2.5-flash, or another configured model for pilot. Meta WhatsApp Business Cloud API via httpx. Cloudflare R2 for uploaded CSV and Excel files. Railway for pilot deployment. Sentry and Betterstack for error tracking and uptime monitoring.

---

## 6. Build Order — V0.0 First, Then V0.1

Follow this exactly. One module fully working and tested before starting the next. No placeholder code. No stubbed functions.

### V0.0 Build Order

Step 1: Project setup — FastAPI, PostgreSQL connection, SQLAlchemy async, Alembic, environment config, health check endpoint.

Step 2: Database schema — all tables from schema above, initial Alembic migration, verify connection.

Step 3: Company and dealer management — admin endpoint to create company, create dealer, create supplier. No user-facing onboarding. Founder creates via these endpoints directly.

Step 4: Invoice and payment management — create invoice, record payment, update invoice status. Get the real Tally export file before this step. Schema must match actual file contents.

Step 5: BusinessEngine and BusinessEvents — wire events for invoice created and payment received, verify ActivityTimeline writes, verify snapshot is marked stale on each event.

Step 6: BusinessSnapshotService — build snapshot from real data, verify every field is correct against known test data before proceeding.

Step 7: RecommendationEngine — test against multiple snapshot scenarios with known expected outputs. Verify every rule fires correctly.

Step 8: BriefingService — integrate the LLM provider, send to one real distributor, verify every number in the output matches the snapshot exactly.

Step 9: ImportService — build against the real Tally export file, verify row-level error handling, verify BusinessEngine is triggered correctly per imported record.

Step 10: Manual pilot begins. Founder uploads file, system generates briefing, founder sends via WhatsApp. Collect feedback for 2 weeks before continuing.

### V0.1 Build Order (Only After V0.0 Pilot Validates)

Step 11: WhatsApp webhook — verify endpoint, message routing.

Step 12: Numbered query menu — four canned reports from snapshot.

Step 13: InvoiceDueDateFollowUpService — follow-up flow, response routing through BusinessEngine.

Step 14: NotificationEngine — overdue alerts, supplier payment reminders, stale data warnings.

Step 15: APScheduler for automated morning briefing dispatch.

Step 16: Confidence indicator and stale data notice in briefings.

---

---

# Document 3 — WhatsApp Conversation Specification

## Design Principles

Every conversation has a defined happy path and a defined error path. The system never leaves the distributor in an ambiguous state. Every action confirms before finalizing. The system never asks for information the database already knows. When input is ambiguous, present the most likely match and ask for confirmation.

---

## Conversation 1 — Morning Briefing (Outbound, 8am Daily)

### Standard Briefing — No Shortage

Good morning Rajesh.
Data updated: yesterday 9:14pm — confidence 94%

💰 Cash Position
Available: ₹1,84,000
In this week: ₹3,20,000
Out this week: ₹2,45,000
Net: +₹75,000 — no shortage expected

🚨 Attention Required
XYZ Traders — ₹42,000 — 12 days overdue — High Risk
Kumar Agency — ₹18,000 — due today

📋 Today's Actions
Call XYZ Traders first
Confirm Kumar Agency payment
Amul payment Friday — cash sufficient

Reply 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk

### Cash Deficit Briefing

Good morning Rajesh.
Data updated: yesterday 8:45pm — confidence 91%

💰 Cash Position
Available: ₹1,20,000
In this week: ₹1,80,000
Out this week: ₹2,45,000
Net: -₹65,000 ⚠ Shortage expected

🚨 Critical
Amul payment ₹82,000 due Friday — cash may be insufficient
XYZ Traders ₹42,000 overdue 12 days — collect first

📋 Today's Actions
Call XYZ Traders immediately
Delay non-critical purchases until Friday
Confirm Amul payment plan

Reply 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk

### Stale Data Briefing

Good morning Rajesh.
⚠ Data last received 2 days ago. This briefing may not reflect today's actual position. Please ask your operator to send today's Tally export.

Based on last available data:

💰 Cash Position
Available: ₹1,84,000
Net estimated: +₹75,000

🚨 Attention Required
XYZ Traders — ₹42,000 — overdue

📋 Today's Actions
Send today's export to get an accurate briefing
Call XYZ Traders

Reply 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk

---

## Conversation 2 — Numbered Query Menu

### Reply 1 — Cash Position

💰 Cash Position

Available now: ₹1,84,000
Expected in (7 days): ₹3,20,000
Due out (7 days): ₹2,45,000
Net expected: +₹75,000
No shortage expected this week.

### Reply 2 — Collections

📥 Outstanding Collections

XYZ Traders — ₹42,000 — 12 days overdue — High Risk
Kumar Agency — ₹18,000 — due today — Medium Risk
Ram Traders — ₹31,000 — due Friday — Low Risk

Total expected this week: ₹91,000

### Reply 3 — Suppliers

📤 Supplier Payments Due

Amul — ₹82,000 — due Friday — cash sufficient
Sharma Traders — ₹45,000 — due next Monday

Total due this week: ₹82,000

### Reply 4 — Dealer Risk

⚠ Dealer Risk Summary

High Risk:
XYZ Traders — ₹42,000 overdue — 3 late payments in 6 months

Medium Risk:
Kumar Agency — ₹18,000 due today — 1 late payment in 6 months

Low Risk:
Ram Traders — ₹31,000 due Friday — pays on time

---

## Conversation 3 — Invoice Due Date Follow-Up (V0.1)

### System Initiates (Due Date Arrives)

System sends:

📋 Payment Follow-Up

INV-1047 — Ram Traders — ₹49,350
Due date: today

Has payment been received?
1. Yes — full amount
2. Partial payment
3. Not yet received

### Distributor Replies 1 — Full Payment

System: ₹49,350 payment recorded from Ram Traders.
INV-1047 closed.
Outstanding: ₹0.
Cash and tomorrow's briefing updated.

### Distributor Replies 2 — Partial Payment

System: How much was received?

Distributor: 25000

System: ₹25,000 partial payment recorded.
INV-1047 — ₹24,350 still outstanding.
Cash and tomorrow's briefing updated.

### Distributor Replies 3 — Not Yet Received

System: When do you expect payment from Ram Traders?
Example: Friday, 3 days, next week

Distributor: Friday

System: Noted. INV-1047 follow-up scheduled for Friday.
Ram Traders flagged in tomorrow's briefing.

---

## Conversation 4 — Invoice Creation (V0.2)

### Standard Flow

Distributor: create invoice Ram Traders rice 500kg dal 100kg

System: Confirm invoice for Ram Traders?
Rice — 500kg — ₹35,000
Dal — 100kg — ₹12,000
GST 5% — ₹2,350
Total — ₹49,350
Due: 14 days from today

Reply YES to confirm or NO to cancel.

Distributor: yes

System: Invoice INV-1047 created.
PDF sent to Ram Traders.
Receivable ₹49,350 added.
Tomorrow's briefing updated.

### Incomplete Invoice — System Asks for Missing Information

Distributor: create invoice ABC Traders

System: What products for ABC Traders?
Example: rice 200kg, oil 50 litre

Distributor: wheat 300kg sugar 100kg

System: Confirm invoice for ABC Traders?
Wheat — 300kg — ₹18,000
Sugar — 100kg — ₹14,000
GST 5% — ₹1,600
Total — ₹33,600
Due: 14 days from today

Reply YES to confirm or NO to cancel.

---

## Conversation 5 — Payment Update (V0.2)

### Smart Matching — Distributor Says Dealer Name Only

Distributor: Ram paid

System: Did you mean Ram Traders?
Pending: INV-1047 — ₹49,350 — due today
Full amount or partial?

Distributor: full

System: ₹49,350 payment recorded from Ram Traders.
INV-1047 closed. Outstanding: ₹0.
Cash and tomorrow's briefing updated.

### Distributor States Amount

Distributor: Ram paid 25000

System: ₹25,000 payment recorded from Ram Traders.
INV-1047 partially paid — ₹24,350 still outstanding.
Cash and tomorrow's briefing updated.

---

## Conversation 6 — Automated Notifications (Outbound)

### Supplier Payment Due Tomorrow

⏰ Payment Reminder

Amul payment of ₹82,000 due tomorrow.
Current cash available: ₹1,84,000 — sufficient.
No action needed unless cash position has changed.

### Dealer Overdue Alert

⚠ Collection Alert

XYZ Traders — ₹42,000 — now 15 days overdue.
No follow-up recorded in 3 days.
Suggested: call today before placing new order.

### Data Not Received

📂 Data Update Needed

No Tally export received today.
Tomorrow's briefing will be based on yesterday's data.
Please ask your operator to send today's export.

---

## Conversation 7 — Error Handling

### Unknown Input

I didn't understand that.
Reply 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk
Or send your Tally export file.

### Wrong File Format

This file format is not supported.
Please send a CSV or Excel export from Tally.
Reply TEMPLATE to receive a sample file.

### Missing Columns in Import

Import failed — missing columns: due\_date, invoice\_amount.
Please check the file and resend.
Reply TEMPLATE for the correct column format.

### Partial Import with Row Errors

Import complete — 47 of 50 rows processed.
3 rows failed:
Row 12 — missing due date
Row 31 — amount format unreadable
Row 44 — duplicate invoice number INV-0291

Please correct and resend only the failed rows.

### Briefing Delivery Failure

System logs error internally. Retries automatically at 9am. If retry fails, founder receives internal alert. Distributor is not notified of failure — they receive the briefing when it succeeds or a manual message from the founder.

---

These three documents are final. The PRD defines what you build and why. The TDD defines how you build it. The conversation spec defines every WhatsApp interaction. Build V0.0 first, get it in front of 2 to 3 real distributors within 4 weeks, and let their behavior tell you what to build next. Everything else will come from that.
