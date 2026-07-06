Inventory + FAQ + Guided Order Creation (Phase 2B)
Context
The user showed an n8n reference flow: WhatsApp Trigger → AI Agent (chat model + memory + tools: Get Inventory, Get FAQ, Post Orders) → Send message. OpsGenie already has the WhatsApp-trigger → multi-provider AI agent → reply pattern (app/services/assistant.py + app/services/agent/), built more safely than the n8n demo (money-guard on every reply). Confirmed with the user via AskUserQuestion:

Order creation ("Post Orders") is a guided workflow + confirm step, not a direct AI tool-call — matching this codebase's own principle that writes are deterministic workflows, not AI capabilities (same shape as the existing record_payment flow, Phase 2A). This is literally the "Phase 2B" app/models/product.py's docstring already earmarks ("this table supports V0.2 invoice creation via WhatsApp only").
Inventory needs real stock-quantity tracking on Product, decremented when an order is created.
FAQ is a simple per-company Q&A list the founder populates via admin API; the agent answers from it as a read tool.
"Get Invoice" from the reference flow is already covered by the existing list_recent_invoices agent tool — no new work there.

Shape of the change
Admin API (founder)                 WhatsApp (distributor)
─────────────────────               ───────────────────────────────────────
POST/GET  .../products    ┐         "new order"  ──▶ order_flow.py (state machine)
PATCH     .../products/:id│                              │  dealer → items× → preview
POST/GET  .../faqs        │                              ▼
PATCH/DEL .../faqs/:id    │                       PendingOperation(create_order)
                          │                              │  "YES"
                          ▼                              ▼
                   Product.stock_quantity      writes/orders.py::create_order
                   FAQ rows                       - find_or_create_party (dealer)
                          │                        - match/create Product (+price if missing)
                          │                        - Invoice + InvoiceItem rows
                          │                        - stock_quantity -= qty (may go negative)
                          ▼
              agent read tools: get_inventory, get_faqs  ◀── free-form chat questions
Everything left of "PendingOperation" is new state-machine code mirroring payment_flow.py; everything right of it mirrors writes/payments.py + the dispatch branch in writes/pending_operation.py. The admin CRUD and the two new read tools are independent, smaller additions.

Schema (one Alembic migration, chained off head 8524a9dbfe0c)
products.stock_quantity: Quantity type alias (app/models/_types.py, Numeric(14,4)), NOT NULL DEFAULT 0.
New faqs table: id (uuid pk), company_id (fk → companies, cascade), question (String, not null), answer (String, not null), created_at/updated_at via TimestampMixin.
ALTER TYPE pendingoperationtype ADD VALUE 'create_order' — hand-written op.execute, no-op downgrade, same convention as alembic/versions/146a970a5954_add_whatsapp_business_event_types.py.
Note: onboarding creates products with name only (app/services/onboarding_flow.py:112, Product(company_id=..., name=stripped)) — no price, no unit. So plenty of existing/real products will have selling_price=None. The order flow must treat "product matched but has no price on file" the same as "brand-new product" when it comes to asking for a price (see below) — this isn't just a new-product edge case, it's the common case for onboarded catalogues.

Models
app/models/product.py: add stock_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False, default=Decimal("0")). Drop the stale "inventory tracking is explicitly out of scope" line from the module docstring.
app/models/faq.py (new): FAQ(UUIDMixin, TimestampMixin, Base), company_id FK (cascade), question: str, answer: str. Mirror Product's structure.
app/models/company.py: add faqs: Mapped[list[FAQ]] = relationship("FAQ", back_populates="company", cascade="all, delete-orphan"), alongside the existing relationship list; add FAQ to the TYPE_CHECKING imports.
app/models/pending_operation.py: add create_order = "create_order" to PendingOperationType; update its docstring (it already says "Room for create_invoice (Phase 2B)... later").
Schemas + Admin CRUD
No admin endpoint in this codebase currently has PATCH/PUT (checked all of app/api/admin/*.py — only DELETE /companies/{id} exists as a mutation beyond POST). So the update endpoints below are a new pattern, not a mirror of an existing one — keep them minimal and consistent with the POST/GET shape dealers.py already has.

app/schemas/product.py (new): ProductCreate (name, unit, selling_price, purchase_price, stock_quantity — all but name optional with sensible defaults), ProductUpdate (all fields optional, partial update), ProductResponse.
app/schemas/faq.py (new): FAQCreate (question, answer), FAQUpdate (both optional), FAQResponse.
app/api/admin/products.py (new), router prefix /companies/{company_id}/products: POST create, GET list (paginated, Page[ProductResponse] like dealers.py), GET /{product_id}, PATCH /{product_id} (partial update, 404 if missing/wrong company — reuse the _get_company_or_404 pattern from dealers.py).
app/api/admin/faq.py (new), same shape under /companies/{company_id}/faqs: POST, GET list, PATCH /{faq_id}, DELETE /{faq_id} (204).
Register both routers in app/api/admin/__init__.py.
Agent read tools (app/services/agent/read_tools.py)
Rename _list_products/list_products → _get_inventory/get_inventory; enrich the returned dict with unit, stock_quantity (stringified Decimal), selling_price (stringified Decimal or None) per product — one tool, not two, avoiding confusing the model with near-duplicates.
Update tests/test_agent_tools.py: rename test_list_products → test_get_inventory (line ~132) and the ctx.execute("list_products", {}) call (line ~159) to get_inventory.
Add _get_faqs/get_faqs (no params): returns {"faqs": [{"question": ..., "answer": ...}, ...]} for the company — same "load the whole sheet" shape the n8n Get FAQ node had.
app/services/assistant.py's _SYSTEM_PROMPT: add a line stating the agent cannot create orders or record payments itself — if asked, tell the user to say "new order" / "record payment" to start the guided flow. This closes a real gap: today nothing tells a free-text "I'd like to place an order" user that the keyword trigger exists.
Guided order workflow — app/services/workflows/order_flow.py (new, mirrors payment_flow.py)
State machine, Company.active_workflow = "create_order", steps stored in workflow_scratch:

start_order_workflow(company) → sets active_workflow/workflow_scratch, asks for the dealer name (orders here are sales to dealers only — matches "Post Orders" = receivable side, same convention payment_flow.py uses for direction).
awaiting_dealer → case-insensitive match against Dealer (reuse the func.lower(...)== pattern from payment_flow._match_direction/find_or_create_party). If unknown: confirm-add step (yes/no) before continuing — same reasoning as payment_flow.py's new-party confirmation (a typo shouldn't silently create a dealer). Unlike the payment flow, a brand-new dealer can proceed here (an order is what gives them their first invoice), so on "yes" just record the name and move on to items; the dealer row itself is created at confirm-time inside create_order, exactly like record_payment defers to find_or_create_party.
awaiting_product_name (repeatable loop) → case-insensitive match against Product.
Match found and selling_price is not None → ask quantity directly.
Match found but selling_price is None, or no match at all → ask "What's the selling price for {name}?" first, then quantity. Track is_new_product only for the confirm-time create-vs-reuse decision; the price question applies in both cases per the onboarding-created-products note above.
awaiting_quantity → parse as a plain number (reuse Quantity-shaped parsing, i.e. Decimal via app.services.importer.normalizer.parse_amount or a similar simple parse — reject <= 0). Append {product_name, quantity, price_if_new} to scratch["items"], then re-prompt "Add another product, or reply 'done'."
On "done" → preview: each line (product x quantity @ price = line_total) + grand total, "Reply YES to record, NO to cancel." → create_pending_operation(db, company, PendingOperationType.create_order, payload), clear active_workflow/workflow_scratch.
Payload stores raw inputs only: {"dealer_name": ..., "items": [{"product_name": ..., "quantity": "12", "price": "150.00" | null}, ...]} — per the PendingOperation contract (never a precomputed total), so confirm-time re-derives current prices/stock rather than trusting a possibly-stale preview.
"cancel"/"stop" recognized at every step (same _is(stripped, "cancel", "stop") check payment_flow.py opens with) — an active workflow outranks the menu, so a user needs a guaranteed way out.
Deterministic write — app/services/writes/orders.py (new, mirrors writes/payments.py)
create_order(db, company, *, dealer_name, items) -> CreateOrderResult (dataclass: invoice_number, dealer_name, line_totals, total_amount, negative_stock_warnings: list[str]):

dealer = await find_or_create_party(db, company.id, "receivable", dealer_name) (app/services/importer/parties.py — already the create-on-demand version; the flow's earlier confirm step is a UX gate, this is the actual row creation, exactly mirroring how record_payment defers to the same helper).
For each item: case-insensitive match against Product (same func.lower(Product.name) == pattern). If missing, create it with name, selling_price=Decimal(item["price"]), stock_quantity=0. If found but selling_price is None, backfill it from item["price"] (only if provided — re-validate: raise ValueError if a price is needed but wasn't collected, e.g. product got a price from someone else between preview and confirm and the payload lacks one — actually in that case just use the now-current DB price, only raise if genuinely still None with no item["price"]).
line_total = product.selling_price * quantity; decrement product.stock_quantity -= quantity (allowed to go negative — flag it in the result, don't block; physical counts can lag digital ones, matching the plan's earlier stock-tracking rationale).
Build one Invoice (direction=InvoiceDirection.receivable, source=InvoiceSource.whatsapp, status=InvoiceStatus.Pending, invoice_date=today, due_date = today + dealer.payment_terms_days if set else today, subtotal=sum(line_totals), gst_amount=Decimal("0"), total_amount=subtotal, invoice_number=f"WA-{uuid.uuid4().hex[:10]}" — same simplification and numbering convention onboarding_flow._add_opening_invoice already uses for its ONB- prefix) + one InvoiceItem per line (quantity, unit_price=product.selling_price, line_total, description=product.name, product_id=product.id).
Raise ValueError on re-validation failure (quantity <= 0, or a price genuinely missing) — caller turns it into a friendly reply, same pattern as record_payment.
Never commits — caller (execute_pending_operation) commits once.
Dispatch + webhook wiring
app/services/writes/pending_operation.py::execute_pending_operation: add an elif op.operation_type == PendingOperationType.create_order: branch calling create_order, catching (ValueError, KeyError, TypeError) exactly like the record_payment branch, formatting a success reply with invoice number, line items, total, and any negative-stock warning.
app/api/webhooks/whatsapp.py:
Import handle_order_workflow_message, start_order_workflow from the new order_flow.py.
_WORKFLOW_HANDLERS["create_order"] = handle_order_workflow_message.
_WORKFLOW_START_TRIGGERS: add "new order", "create order", "place order", "record order" → start_order_workflow.
Tests
tests/test_admin_products.py, tests/test_admin_faq.py (new) — CRUD against real Postgres, mirroring tests/test_admin_payments.py's conventions (no mocking).
tests/test_order_flow.py (new) — follow tests/test_payment_flow.py's convention exactly: real HMAC-signed POSTs against the actual /whatsapp webhook endpoint, send_text_message monkeypatched to capture outbound replies. Cover: existing dealer + existing priced product (happy path); new dealer; existing product with no price on file (must be asked); multi-item order; cancel mid-flow; zero/negative quantity rejected; order that drives stock negative still succeeds but flags a warning in the confirmation reply; assert final Invoice/InvoiceItem rows and decremented Product.stock_quantity directly against the DB.
tests/test_agent_tools.py: rename the list_products test to get_inventory (asserting the enriched fields too), add a get_faqs test.
Verification
uv run alembic upgrade head against local dev Postgres — confirm it applies cleanly, including the hand-written ALTER TYPE.
uv run pytest full suite green + uv run ruff check . clean (this project's standing convention).
Exercise the new flow end-to-end via the webhook test harness (per test_order_flow.py above) rather than only calling service functions directly — this is the pattern the codebase already uses for payment_flow, and it's what actually proves the webhook dispatch wiring works, not just the state machine in isolation.