"""English message catalog — the source of truth and fallback.

Every user-facing deterministic string OpsGenie sends lives here keyed by a
dotted id (``namespace.name``). The other locale catalogs mirror these exact
keys (enforced by tests/test_i18n.py). Values are ``str.format`` templates:
amounts, names, invoice numbers, dates and emoji are interpolated by the
caller and never translated — only OpsGenie's own words live here.
"""

from __future__ import annotations

# The full "help" block. Kept as one constant (not 50 keys) because it's a
# static wall of text; command keywords (cash, /add_product, balance <name>)
# stay English since they are the literal triggers read back as commands —
# only the surrounding prose/descriptions are localized per locale catalog.
_HELP_TEXT_EN = """*OpsGenie Help*

*Cash & Overview*
• cash / cash position — current cash, 7-day expected in/out, net position (or reply 1 / /cash)
• summary / business summary — cash, net position, 7-day collections/payments, overdue dealers
• priorities / what should I do — ranked actions: cash warnings, dealers to call, supplier dues

*Dealers (they owe you)*
• dealers / all dealers — every dealer with phone & outstanding
• top debtors / who owes most — dealers with the largest outstanding
• overdue / overdue dealers — days overdue & risk level (or reply 4 / /dealer_risk)
• balance <name> — outstanding for one dealer, e.g. balance Ram Traders
• add dealer (or /add_dealer) — add a new dealer: name, phone, credit days
• edit dealer (or /edit_dealer) — update phone, credit limit, terms, GSTIN, or direct reminders

*Suppliers (you owe them)*
• suppliers / all suppliers — every supplier with phone & outstanding
• top creditors — suppliers you owe the most
• balance <name> — outstanding for one supplier
• add supplier (or /add_supplier) — add a new supplier: name, phone, credit days
• edit supplier (or /edit_supplier) — update a supplier's phone, credit limit, terms, or GSTIN

*Upcoming Cash Flow*
• collections / upcoming collections — expected from dealers, next 7 days (or 2 / /collections)
• payments / upcoming payments — owed to suppliers in the next 7 days (or reply 3 / /suppliers)

*Inventory*
• inventory / products / stock — latest products added (stock qty, selling price)
• all inventory — every product, not just recent
• stock <product> — check a specific item, e.g. stock Rice

*Transactions*
• invoices / recent invoices — latest invoices (number, party, total, status, dates)
• all invoices — every invoice, not just recent
• payments / recent payments — latest payments recorded
• all payments / all time payments — every payment, not just recent
• faq / policy — your saved business policy answers (delivery days, returns, minimum order)

*Manage Products* (guided, one question at a time)
• add product (or /add_product) — add a new item: name, stock, unit, selling price, purchase price
• update stock (or /update_stock) — change a product's stock quantity
• update price (or /update_price) — change a product's selling price
• update purchase price (or /update_purchase_price) — change what you pay your supplier
• update product (or /update_product) — pick price, purchase price, or stock to update
• update gst (or /update_gst) — change GST for all products, or one specific product
• delete product (or /delete_product) — remove a catalogue item
• stock take (or /stock_take) — recount or adjust stock for several products in one go

*Orders & Payments*
• new order (or /create_order, or "new invoice") — record a sale to a dealer, product by product
• record payment (or /record_payment) — log a payment received from a dealer or paid to a supplier

*Corrections*
• undo payment (or /undo_payment) — void the payment you just recorded
• undo order (or /undo_order) — void the order you just created (only if it's still unpaid)
• edit invoice (or /edit_invoice) — correct an invoice's amount, date, or party (only if unpaid)
• edit payment (or /edit_payment) — correct a recorded payment's amount or date

*Your Data*
• export data (or /export_data) — a download link to your full business data as Excel
• morning briefing (or /morning_briefing) — resend today's briefing

*Reports & Statements* (this month, Excel + PDF where noted)
• ledger <name> — running-balance statement, Excel + PDF, e.g. ledger Ram Traders
• sales register / purchase register (or "gst report" for both) — GST register + rate-wise summary
• payment register (or receipt register) — receipts & payments this month
• day book — every invoice and payment this month, in one list
• outstanding report (or aging report) — 0-30/31-60/61-90/90+ day buckets, Excel + PDF
• trend report (or business trends) — week-over-week cash, dealer & product trends, Excel
• delivery status — Meta delivery/read status for invoices & broadcasts you've sent

*Marketing*
• broadcast (or /broadcast) — send a message to opted-in dealers (all, overdue, or picked by name)
• opt in all dealers — opt every dealer who hasn't opted out into broadcasts (confirm required)
• edit dealer — reply 'marketing' to opt one dealer in or out

*Quick Access*
• menu — tap through your options instead of typing
• help (or /help) — see this list again anytime"""

MESSAGES: dict[str, str] = {
    # ── Errors / fallbacks ────────────────────────────────────────────────
    "errors.something_wrong": "Something went wrong. Please try again.",
    "errors.assistant_fallback": (
        "Sorry, I couldn't answer that right now. Reply 1 Cash · 2 Collections · "
        "3 Suppliers · 4 Dealer Risk, or try rephrasing."
    ),
    # ── Onboarding: language switch confirmation (shown in the NEW locale) ──
    "onboarding.language_changed": "✅ Done — I'll message you in {language} from now on.",
    # ── Cash Position report (reply 1 / /cash) ─────────────────────────────
    # Emoji stay in the template (universal); amounts are interpolated.
    "reports.cash.header": "💰 Cash Position",
    "reports.cash.available_now": "Available now: {amount}",
    "reports.cash.expected_in": "Expected in (7 days): {amount}",
    "reports.cash.due_out": "Due out (7 days): {amount}",
    "reports.cash.net_expected": "Net expected: {amount}",
    "reports.cash.shortage": "Shortage expected this week.",
    "reports.cash.no_shortage": "No shortage expected this week.",
    # ── Collections report (reply 2 / /collections) ────────────────────────
    "reports.collections.header": "📥 Outstanding Collections",
    "reports.collections.none": "No collections expected in the next 7 days.",
    "reports.collections.total": "Total expected this week: {amount}",
    # ── Supplier payments report (reply 3 / /suppliers) ────────────────────
    "reports.suppliers.header": "📤 Supplier Payments Due",
    "reports.suppliers.none": "No supplier payments due in the next 7 days.",
    "reports.suppliers.total": "Total due this week: {amount}",
    "reports.suppliers.cash_ok": "cash sufficient",
    "reports.suppliers.cash_short": "cash may be insufficient",
    # ── Dealer risk report (reply 4 / /dealer_risk) ────────────────────────
    "reports.risk.header": "⚠ Dealer Risk Summary",
    "reports.risk.none": "No overdue dealers right now.",
    "reports.risk.high": "High Risk:",
    "reports.risk.medium": "Medium Risk:",
    "reports.risk.low": "Low Risk:",
    # {name}/{amount}/{days} are interpolated data; only "overdue" is words.
    "reports.risk.dealer_line": "{name} — {amount} overdue ({days}d) — {late}",
    # ── Shared: due-date phrase (weekday name / ISO date interpolated) ─────
    "reports.due.today": "due today",
    "reports.due.weekday": "due {day}",
    "reports.due.date": "due {date}",
    # ── Shared: late-payment history phrase (0 / 1 / many) ─────────────────
    "reports.late.none": "pays on time",
    "reports.late.one": "1 late payment in 6 months",
    "reports.late.many": "{count} late payments in 6 months",
    # ── Business summary (instant report) ──────────────────────────────────
    "reports.summary.header": "📊 Business Summary",
    "reports.summary.cash_now": "Cash available now: {amount}",
    "reports.summary.net_7d": "Net cash position (7d): {amount}",
    "reports.summary.expected_in": "Expected in (7d): {amount}",
    "reports.summary.expected_out": "Expected out (7d): {amount}",
    "reports.summary.shortage": "Cash shortage expected this week.",
    "reports.summary.no_shortage": "No cash shortage expected.",
    "reports.summary.overdue_count": "Overdue dealers: {count}",
    "reports.summary.overdue_hint": " — reply 'overdue' for details.",
    # ── Priorities (instant report) ────────────────────────────────────────
    "reports.priorities.none": "🎯 Nothing urgent right now — no priority actions.",
    "reports.priorities.header": "🎯 Priorities",
    # ── Dealer / supplier lists ────────────────────────────────────────────
    "reports.dealers.none": "You don't have any dealers on file yet.",
    "reports.dealers.header": "👥 Dealers ({count}):",
    "reports.suppliers_list.none": "You don't have any suppliers on file yet.",
    "reports.suppliers_list.header": "🚚 Suppliers ({count}):",
    "reports.party.no_phone": "no phone",
    "reports.party.line": "{name} — {phone} — outstanding {amount}",
    "reports.top_debtors.none": "No dealer currently owes you anything.",
    "reports.top_debtors.header": "💰 Top Debtors",
    "reports.top_creditors.none": "You don't currently owe any supplier anything.",
    "reports.top_creditors.header": "💸 Top Creditors",
    # ── Inventory ──────────────────────────────────────────────────────────
    "reports.inventory.none": "You don't have any products in your catalogue yet.",
    "reports.inventory.label_recent": "Recent Inventory",
    "reports.inventory.label_all": "All Inventory",
    "reports.inventory.header_partial": "📦 {label} ({count} of {total}):",
    "reports.inventory.header_full": "📦 {label} ({count}):",
    "reports.inventory.more": (
        "\n\n…and {remaining} more — reply 'all inventory' for the full list."
    ),
    "reports.product.price_not_set": "price not set",
    # ── FAQs ───────────────────────────────────────────────────────────────
    "reports.faq.none": "You don't have any saved policy answers yet.",
    "reports.faq.header": "❓ FAQs ({count}):",
    "reports.faq.qa": "Q: {question}\nA: {answer}",
    # ── Invoices ───────────────────────────────────────────────────────────
    "reports.invoices.none": "You don't have any invoices yet.",
    "reports.invoices.label_recent": "Recent Invoices",
    "reports.invoices.label_all": "All Invoices",
    "reports.invoices.header_partial": "📄 {label} ({count} of {total}):",
    "reports.invoices.header_full": "📄 {label} ({count}):",
    "reports.invoices.more": "\n\n…and {remaining} more — reply 'all invoices' for the full list.",
    "reports.invoices.line": "{number} — {party} — {amount} — {status} — {due}",
    "reports.unknown_party": "unknown party",
    # ── Payments ───────────────────────────────────────────────────────────
    "reports.payments.none": "You don't have any payments recorded yet.",
    "reports.payments.label_recent": "Recent Payments",
    "reports.payments.label_all": "All Payments",
    "reports.payments.header_partial": "💵 {label} ({count} of {total}):",
    "reports.payments.header_full": "💵 {label} ({count}):",
    "reports.payments.more": "\n\n…and {remaining} more — reply 'all payments' for the full list.",
    "reports.payments.from": "from",
    "reports.payments.to": "to",
    "reports.payments.line": "{amount} — {direction} invoice {number} — {date}",
    # ── Party balance ("balance <name>") ───────────────────────────────────
    "reports.balance.dealer_owes": "{party} owes you {amount}.",
    "reports.balance.you_owe": "You owe {party} {amount}.",
    # ── Stock item ("stock <item>") ────────────────────────────────────────
    "reports.stock.not_found": "I couldn't find a product matching '{name}'.",
    "reports.stock.line": "{name} — {stock} in stock — {price}",
    # ── Sales impact ("if I sell N of X") ──────────────────────────────────
    "reports.sales.revenue": "revenue {amount}",
    "reports.sales.profit": "profit {amount}",
    "reports.sales.left": "{qty} left in stock",
    "reports.sales.total_revenue": "Total revenue: {amount}",
    "reports.sales.total_profit": "Total profit: {amount}",
    "reports.sales.no_cost": "(no purchase price on file for {missing} — excluded from profit)",
    # ── Excel export link ──────────────────────────────────────────────────
    "reports.export.not_configured": (
        "The data export link isn't set up yet — ask your OpsGenie admin to configure it."
    ),
    "reports.export.ready": (
        "Your latest Excel export is ready.\nDownload (valid {ttl} min): {link}"
    ),
    # ── Period-scoped report downloads (ledger, GST/sales/purchase
    # registers, payment register, day book, aging) ────────────────────────
    "reports.download.ready": (
        "Your {report_name} ({period}) is ready.\nDownload (valid {ttl} min):\n{links}"
    ),
    "reports.ledger.not_found": "I couldn't find a dealer or supplier matching '{name}'.",
    # ── Business Trends report ("trend report"/"business trends") ──────────
    "reports.trend.headline": (
        "📈 Collections {collections_pct}, Payments {payments_pct}, Net Cash {net_delta} · "
        "{dealers_slowing} dealer(s) slowing · {products_declining} product(s) declining"
    ),
    "reports.trend.header": "Cash Trend (this week vs last week)",
    "reports.trend.collections_line": "Collections: {current} (was {prior})",
    "reports.trend.payments_line": "Supplier Payments: {current} (was {prior})",
    "reports.trend.net_line": "Net Cash Movement: {current} (was {prior})",
    "reports.trend.sales_line": "Sales (Invoiced): {current} (was {prior})",
    "reports.trend.dealers_header": "Dealer Trend (last 30 days vs prior 30 days)",
    "reports.trend.dealers_none": "Not enough dealer order activity yet to show a trend.",
    "reports.trend.dealer_rising_line": (
        "▲ {name} — order value {value_delta}, outstanding {outstanding_delta}"
    ),
    "reports.trend.dealer_falling_line": (
        "▼ {name} — order value {value_delta}, outstanding {outstanding_delta}"
    ),
    "reports.trend.products_header": "Product Sales Trend (last 30 days vs prior 30 days)",
    "reports.trend.products_none": "Not enough sales activity yet to show a product trend.",
    "reports.trend.product_rising_line": "▲ {name} — units {unit_delta}, revenue {revenue_delta}",
    "reports.trend.product_falling_line": "▼ {name} — units {unit_delta}, revenue {revenue_delta}",
    "reports.trend.full_detail_link": (
        "Every dealer & product (Excel, valid {ttl} min): {link}"
    ),
    # ── Delivery/read status ("delivery status") ────────────────────────────
    "reports.delivery_status.header": "📨 Delivery Status",
    "reports.delivery_status.none": "No invoices or broadcasts sent to dealers yet.",
    "reports.delivery_status.line": "{label} ({when}): {counts}",
    "reports.delivery_status.invoice_label": "{invoice} → {party}",
    "reports.delivery_status.broadcast_label": "Broadcast — {count} dealers",
    "reports.delivery_status.count_part": "{count} {status}",
    "reports.delivery_status.status.sent": "sent",
    "reports.delivery_status.status.delivered": "delivered",
    "reports.delivery_status.status.read": "read",
    "reports.delivery_status.status.failed": "failed",
    "reports.delivery_status.status.failed_to_send": "not sent",
    # ── Help text (single block; command keywords stay English triggers) ───
    "menu.help_text": _HELP_TEXT_EN,
    # ── Onboarding: guided business setup (shown after language is chosen) ──
    "onboarding.intro": (
        "👋 Welcome to OpsGenie! Let's set up your business — it takes about 5 minutes, "
        "and you can stop and continue anytime.\n\n"
        "First: what kind of business do you run? (e.g. FMCG Distributor, Pharma Distributor)"
    ),
    "onboarding.progress": "✅ Step {step} of {total} done.",
    "onboarding.finish": (
        "🎉 Setup complete!\n\n"
        "From tomorrow morning I'll send you your daily briefing. You can ask me anything, "
        "like:\n"
        "• Cash position\n"
        "• How much does Ram owe?\n"
        "• Supplier dues\n"
        "• Dealer risk\n\n"
        "Reply menu anytime to tap through your options, or /help to see everything I can do "
        "as a full list."
    ),
    # GST setup
    "onboarding.gst.mode_ask": (
        "Do all your products have the same GST rate, or does it vary by product? "
        "Reply 'same', 'varies', or 'not sure' to decide later."
    ),
    "onboarding.gst.rate_ask": "What's your GST rate? (e.g. 5, 12, 18, or 0 if exempt)",
    "onboarding.gst.mode_invalid": "Please reply 'same', 'varies', or 'not sure'.",
    "onboarding.gst.rate_invalid": (
        "Please send a number between 0 and 100, e.g. 18 (or 'not sure' to decide later)."
    ),
    "onboarding.gst.missing_ask": (
        "We imported GST rates for most of your products. These {count} don't have one yet: "
        "{names}. What GST rate should they use? (e.g. 5, 12, 18, or 0 — or 'skip' to decide "
        "later)"
    ),
    # Products
    "onboarding.product.intro": (
        "Now let's add your products. Reply 'one by one' to add them individually, "
        "or 'bulk' to send them all at once with full details "
        "(e.g. Rice, 300, 400, kg, 100, 5). Reply 'done' to skip."
    ),
    "onboarding.product.bulk_format": (
        "Send your products one per line, in this format:\n"
        "Name, Purchase Price, Selling Price, Unit, Stock, GST%\n"
        "e.g.\n"
        "Rice, 300, 400, kg, 100, 5\n"
        "Dal, 320, 450, kg, 50, 12\n"
        "Use 'skip' for any field you don't want to set "
        "(e.g. Rice, skip, 400, kg, 100, skip). Reply 'done' when finished."
    ),
    # GST already answered "same"/"not sure" at gst_mode_ask — no per-product
    # GST% column here (that's only asked when it varies by product).
    "onboarding.product.bulk_format_no_gst": (
        "Send your products one per line, in this format:\n"
        "Name, Purchase Price, Selling Price, Unit, Stock\n"
        "e.g.\n"
        "Rice, 300, 400, kg, 100\n"
        "Dal, 320, 450, kg, 50\n"
        "Use 'skip' for any field you don't want to set "
        "(e.g. Rice, skip, 400, kg, 100). Reply 'done' when finished."
    ),
    "onboarding.product.first_name": (
        "Send your first product's name (e.g. Rice), or 'done' to skip."
    ),
    "onboarding.product.mode_invalid": (
        "Please reply 'one by one' or 'bulk' — or 'done' to skip adding products."
    ),
    "onboarding.product.bulk_added": (
        "Added {count} product(s): {names}. Send more, or reply 'done' when finished."
    ),
    "onboarding.product.quantity_ask": (
        "How much {name} do you have in stock right now? (e.g. 100, or 'skip')"
    ),
    "onboarding.product.quantity_invalid": "Please send a number, e.g. 100 (or 'skip').",
    "onboarding.product.unit": (
        "What unit is this measured in? (e.g. kg, pcs, box, litre, or 'skip')"
    ),
    "onboarding.product.price_ask": "What's the selling price for {name}? (e.g. 400, or 'skip')",
    "onboarding.product.price_invalid": "Please send a number, e.g. 400 (or 'skip').",
    "onboarding.product.purchase_ask": (
        "What's the purchase price (cost price) for {name}? (e.g. 300, or 'skip')"
    ),
    "onboarding.product.purchase_invalid": "Please send a number, e.g. 300 (or 'skip').",
    "onboarding.product.gst_ask": (
        "What's the GST% for {name}? (e.g. 5, 12, 18, or 'skip' to decide later)"
    ),
    "onboarding.product.gst_invalid": (
        "Please send a number between 0 and 100, e.g. 18 (or 'skip' to decide later)."
    ),
    "onboarding.product.added": (
        "Added product: {name} ({stock} in stock). Send another, or 'done'."
    ),
    # Dealers
    "onboarding.dealers.intro": (
        "Let's add your dealers (customers). Reply 'one by one' to add them individually, "
        "or 'bulk' to send them all at once (e.g. Ram Traders, 9876543210, 15). "
        "Reply 'done' to skip."
    ),
    "onboarding.dealer.bulk_format": (
        "Send your dealers one per line, in this format:\n"
        "Name, Phone, Credit Days\n"
        "e.g.\n"
        "Ram Traders, 9876543210, 15\n"
        "Shree Enterprises, 9123456780, 30\n"
        "Use 'skip' for any field you don't want to set "
        "(e.g. Ram Traders, skip, 15). Reply 'done' when finished."
    ),
    "onboarding.dealer.first_name": (
        "Send your first dealer's name (e.g. Ram Traders), or 'done' to skip."
    ),
    "onboarding.dealer.mode_invalid": (
        "Please reply 'one by one' or 'bulk' — or 'done' to skip adding dealers."
    ),
    "onboarding.dealer.bulk_added": (
        "Added {count} dealer(s): {names}. Send more, or reply 'done' when finished."
    ),
    "onboarding.dealer.credit_ask": "How many credit days do you give {name}? (e.g. 15, or 'skip')",
    "onboarding.dealer.added": "Added dealer {name}. Next dealer's name, or 'done'.",
    # Dealer missing-field backfill (import path only)
    "onboarding.dealer.missing_ask": (
        "We found {count} dealer(s) from your import, but they're missing a phone number "
        "and/or credit days. Complete them now, or later? (now/later)"
    ),
    "onboarding.dealer.missing_list": (
        "{listing}\n\nReply 'bulk' to paste them all at once, or 'one by one' to fill them in "
        "individually."
    ),
    "onboarding.dealer.missing_bulk_format": (
        "Send one line per dealer to fill in their details:\n"
        "Name, Phone, Credit Days\n"
        "e.g.\n"
        "Ram Traders, 9876543210, 15\n"
        "Only names matching the list above will be updated."
    ),
    "onboarding.dealer.missing_bulk_done": "Updated {count} dealer(s): {names}.",
    "onboarding.dealer.missing_bulk_unmatched": (
        "Couldn't match these names to the list above, so they weren't updated: {names}."
    ),
    # Suppliers
    "onboarding.suppliers.intro": (
        "Now your suppliers. Reply 'one by one' to add them individually, "
        "or 'bulk' to send them all at once (e.g. Metro Distributors, 9988776655, 30). "
        "Reply 'done' to skip."
    ),
    "onboarding.supplier.bulk_format": (
        "Send your suppliers one per line, in this format:\n"
        "Name, Phone, Credit Days\n"
        "e.g.\n"
        "Metro Distributors, 9988776655, 30\n"
        "Suresh Wholesale, 9871234560, 15\n"
        "Use 'skip' for any field you don't want to set "
        "(e.g. Metro Distributors, skip, 30). Reply 'done' when finished."
    ),
    "onboarding.supplier.first_name": (
        "Send your first supplier's name (e.g. Metro Distributors), or 'done' to skip."
    ),
    "onboarding.supplier.mode_invalid": (
        "Please reply 'one by one' or 'bulk' — or 'done' to skip adding suppliers."
    ),
    "onboarding.supplier.bulk_added": (
        "Added {count} supplier(s): {names}. Send more, or reply 'done' when finished."
    ),
    "onboarding.supplier.credit_ask": (
        "How many days does {name} give you to pay? (e.g. 15/'skip')"
    ),
    "onboarding.supplier.added": "Added supplier {name}. Next supplier's name, or 'done'.",
    # Supplier missing-field backfill (import path only)
    "onboarding.supplier.missing_ask": (
        "We found {count} supplier(s) from your import, but they're missing a phone number "
        "and/or credit days. Complete them now, or later? (now/later)"
    ),
    "onboarding.supplier.missing_list": (
        "{listing}\n\nReply 'bulk' to paste them all at once, or 'one by one' to fill them in "
        "individually."
    ),
    "onboarding.supplier.missing_bulk_format": (
        "Send one line per supplier to fill in their details:\n"
        "Name, Phone, Credit Days\n"
        "e.g.\n"
        "Metro Distributors, 9988776655, 30\n"
        "Only names matching the list above will be updated."
    ),
    "onboarding.supplier.missing_bulk_done": "Updated {count} supplier(s): {names}.",
    "onboarding.supplier.missing_bulk_unmatched": (
        "Couldn't match these names to the list above, so they weren't updated: {names}."
    ),
    # Shared party fields
    "onboarding.party.phone_ask": "Phone number for {name}? (or 'skip')",
    "onboarding.party.phone_invalid": (
        "That doesn't look like a valid phone number. Include the country code if it's not "
        "Indian, e.g. +919876543210."
    ),
    "onboarding.party.credit_invalid": "Please send a number of days, e.g. 15 (or 'skip').",
    # Shared bulk-paste error (products, dealers, suppliers)
    "onboarding.bulk_error": "Couldn't read that: {error}",
    # Opening cash
    "onboarding.opening.ask": "How much cash is currently in your business? (e.g. 320000)",
    "onboarding.opening.invalid": "Please send an amount, e.g. 320000.",
    # Receivables
    "onboarding.receivable.ask": "Do any dealers currently owe you money? (yes/no)",
    "onboarding.receivable.which": "Which dealer owes you? (name)",
    "onboarding.receivable.confirm_new": (
        "I don't have a dealer named '{name}' yet — add them as a new dealer? (yes/no)"
    ),
    "onboarding.receivable.amount_ask": "How much does {party} owe you? (e.g. 42000)",
    "onboarding.receivable.amount_invalid": "Please send an amount, e.g. 42000.",
    "onboarding.receivable.date_ask": (
        "When do you expect payment from {party}? (e.g. Friday, 15 days, or next week)"
    ),
    "onboarding.receivable.recorded": (
        "Recorded {amount} from {party}. Any other dealer owe you? (yes/no)"
    ),
    # Payables
    "onboarding.payable.ask": "Do you have any supplier payments pending? (yes/no)",
    "onboarding.payable.which": "Which supplier do you owe? (name)",
    "onboarding.payable.confirm_new": (
        "I don't have a supplier named '{name}' yet — add them as a new supplier? (yes/no)"
    ),
    "onboarding.payable.amount_ask": "How much do you owe {party}? (e.g. 82000)",
    "onboarding.payable.amount_invalid": "Please send an amount, e.g. 82000.",
    "onboarding.payable.date_ask": (
        "When is the payment to {party} due? (e.g. Friday, 15 days, or next week)"
    ),
    "onboarding.payable.recorded": (
        "Recorded {amount} to {party}. Any other supplier pending? (yes/no)"
    ),
    # Shared
    "onboarding.yes_no_invalid": "Please reply yes or no.",
    "onboarding.date_invalid": (
        "Sorry, I didn't get that date. Try e.g. Friday, 15 days, or next week."
    ),
    # Briefing hour
    "onboarding.briefing.ask": (
        "Last step — what time should I send your morning briefing? Reply 7, 8, or 9."
    ),
    "onboarding.briefing.invalid": "Please reply with an hour, e.g. 7, 8, or 9.",
    "onboarding.briefing.range": (
        "Please choose a morning hour between 5 and 11 (e.g. 7, 8, or 9)."
    ),
    # Resume: progress checklist ("progress"/"status", any in-flight
    # business-setup state) and restart ("restart", confirm-gated).
    "onboarding.section.business_type": "Business type",
    "onboarding.section.products": "Products",
    "onboarding.section.dealers": "Dealers",
    "onboarding.section.suppliers": "Suppliers",
    "onboarding.section.opening_balance": "Opening balance",
    "onboarding.section.receivables": "Receivables",
    "onboarding.section.payables": "Payables",
    "onboarding.section.briefing_hour": "Briefing time",
    # Import confirm (website "seed from an existing export" step,
    # app/api/onboarding.py's POST /onboard/{id}/import) — shown once, right
    # after GST setup, as one consolidated "here's what we found" summary
    # instead of a separate note per section.
    "onboarding.import_confirm.title": "📋 We found some data from your import:",
    "onboarding.import_confirm.line_products": "✅ {count} product(s)",
    "onboarding.import_confirm.line_dealers": "✅ {count} dealer(s)",
    "onboarding.import_confirm.line_suppliers": "✅ {count} supplier(s)",
    "onboarding.import_confirm.line_receivables": (
        "✅ {count} outstanding receivable invoice(s) ({amount})"
    ),
    "onboarding.import_confirm.line_payables": (
        "✅ {count} outstanding payable invoice(s) ({amount})"
    ),
    "onboarding.import_confirm.ask": "Does this look correct? (yes/no)",
    "onboarding.import_confirm.no_ack": (
        "No problem — you can fix any of this anytime: 'edit dealer <name>', "
        "'edit supplier <name>', 'add dealer', 'add supplier', or 'stock take' to "
        "adjust product quantities. Continuing with the rest of your setup."
    ),
    "onboarding.status.title": "📋 Setup progress — {percent}% complete",
    "onboarding.status.section_done": "✅ {name}",
    "onboarding.status.section_current": "▶️ {name} (you're here)",
    "onboarding.status.section_pending": "⬜ {name}",
    "onboarding.status.footer_generic": "Reply with your next answer to continue.",
    "onboarding.status.restart_hint": (
        "Type 'restart' to start your business setup over from the beginning."
    ),
    "onboarding.restart.confirm": (
        "⚠️ This will erase everything you've entered so far in this setup "
        "(products, dealers, suppliers, opening balances) and start over from "
        "the beginning. Are you sure? (yes/no)"
    ),
    "onboarding.restart.cancelled": (
        "Okay — continuing your setup. Reply with your answer to the last question above."
    ),
    "onboarding.restart.done": (
        "🔄 All cleared. Let's set up your business again from the beginning.\n\n"
        "First: what kind of business do you run? (e.g. FMCG Distributor, Pharma Distributor)"
    ),
    # ── Interactive menu ("menu") ──────────────────────────────────────────
    # The tappable-list plaintext that accompanies the list message, plus the
    # per-message body/button labels, section titles, and row titles +
    # descriptions. Row *ids* stay English (they are read back as commands);
    # only the human-readable titles/descriptions are localized.
    "menu.fallback": "Tap an option below, or reply /help for the full list.",
    "menu.msg.reports.body": "Reports & Overview — tap one:",
    "menu.msg.reports.button": "Reports & Overview",
    "menu.msg.inventory.body": "Inventory, Transactions & Products — tap one:",
    "menu.msg.inventory.button": "Inventory & Trans",
    "menu.msg.orders.body": "Orders, Payments & Your Data — tap one:",
    "menu.msg.orders.button": "Orders & Payments",
    "menu.msg.statements.body": "Reports & Statements — tap one:",
    "menu.msg.statements.button": "GST & Statements",
    "menu.msg.corrections.body": "Corrections — undo or edit something already recorded:",
    "menu.msg.corrections.button": "Corrections",
    "menu.section.cash_overview": "Cash & Overview",
    "menu.section.money_flow": "Money Flow",
    "menu.section.dealers_suppliers": "Dealers & Suppliers",
    "menu.section.inventory_transactions": "Inventory & Transactions",
    "menu.section.manage_products": "Manage Products",
    "menu.section.orders_payments": "Orders & Payments",
    "menu.section.manage_parties": "Manage Parties",
    "menu.section.your_data": "Your Data",
    "menu.section.full_lists": "Full Lists",
    "menu.section.reports_statements": "Reports & Statements",
    "menu.section.corrections": "Corrections",
    "menu.row.cash.title": "Cash Position",
    "menu.row.cash.desc": "Current cash & 7-day in/out",
    "menu.row.summary.title": "Business Summary",
    "menu.row.summary.desc": "Overall snapshot",
    "menu.row.priorities.title": "Priorities",
    "menu.row.priorities.desc": "What should I do today",
    "menu.row.overdue.title": "Overdue Dealers",
    "menu.row.overdue.desc": "Days overdue & risk level",
    "menu.row.collections.title": "Collections Due",
    "menu.row.collections.desc": "Expected in next 7 days",
    "menu.row.payments.title": "Payments Due",
    "menu.row.payments.desc": "Owed to suppliers, 7 days",
    "menu.row.all_dealers.title": "All Dealers",
    "menu.row.all_dealers.desc": "Every dealer, phone & outstanding",
    "menu.row.all_suppliers.title": "All Suppliers",
    "menu.row.all_suppliers.desc": "Every supplier, phone & outstanding",
    "menu.row.top_debtors.title": "Top Debtors",
    "menu.row.top_debtors.desc": "Dealers who owe you the most",
    "menu.row.top_creditors.title": "Top Creditors",
    "menu.row.top_creditors.desc": "Suppliers you owe the most",
    "menu.row.inventory.title": "Recent Inventory",
    "menu.row.inventory.desc": "Latest products added, stock & price",
    "menu.row.invoices.title": "Recent Invoices",
    "menu.row.invoices.desc": "Latest invoices, newest first",
    "menu.row.recent_payments.title": "Recent Payments",
    "menu.row.recent_payments.desc": "Latest payments recorded",
    "menu.row.faq.title": "FAQs",
    "menu.row.faq.desc": "Your saved business policies",
    "menu.row.add_product.title": "Add Product",
    "menu.row.add_product.desc": "Add a new catalogue item",
    "menu.row.update_stock.title": "Update Stock",
    "menu.row.update_stock.desc": "Change a product's stock qty",
    "menu.row.update_price.title": "Update Price",
    "menu.row.update_price.desc": "Change a product's selling price",
    "menu.row.update_cost.title": "Update Cost Price",
    "menu.row.update_cost.desc": "Change what you pay your supplier",
    "menu.row.delete_product.title": "Delete Product",
    "menu.row.delete_product.desc": "Remove a catalogue item",
    "menu.row.update_product.title": "Update Product",
    "menu.row.update_product.desc": "Pick price, cost, or stock to change",
    "menu.row.create_order.title": "Create Order",
    "menu.row.create_order.desc": "Record a sale to a dealer",
    "menu.row.record_payment.title": "Record Payment",
    "menu.row.record_payment.desc": "Log a payment received or paid",
    "menu.row.update_gst.title": "Update GST",
    "menu.row.update_gst.desc": "Change GST for all products, or one product",
    "menu.row.add_dealer.title": "Add Dealer",
    "menu.row.add_dealer.desc": "Add a new dealer (customer)",
    "menu.row.add_supplier.title": "Add Supplier",
    "menu.row.add_supplier.desc": "Add a new supplier",
    "menu.row.export_data.title": "Export Data",
    "menu.row.export_data.desc": "Download your Excel data",
    "menu.row.morning_briefing.title": "Morning Briefing",
    "menu.row.morning_briefing.desc": "Resend today's briefing",
    "menu.row.all_inventory.title": "All Inventory",
    "menu.row.all_inventory.desc": "Every product, not just recent",
    "menu.row.all_invoices.title": "All Invoices",
    "menu.row.all_invoices.desc": "Every invoice, not just recent",
    "menu.row.all_payments.title": "All Payments",
    "menu.row.all_payments.desc": "Every payment, not just recent",
    "menu.row.gst_report.title": "GST Report",
    "menu.row.gst_report.desc": "Sales + purchase register together",
    "menu.row.sales_register.title": "Sales Register",
    "menu.row.sales_register.desc": "GST register + rate-wise summary",
    "menu.row.purchase_register.title": "Purchase Register",
    "menu.row.purchase_register.desc": "GST register + rate-wise summary",
    "menu.row.payment_register.title": "Payment Register",
    "menu.row.payment_register.desc": "Receipts & payments this month",
    "menu.row.day_book.title": "Day Book",
    "menu.row.day_book.desc": "Every invoice & payment, one list",
    "menu.row.outstanding_report.title": "Outstanding Report",
    "menu.row.outstanding_report.desc": "0-30/31-60/61-90/90+ day buckets",
    "menu.row.trend_report.title": "Business Trends",
    "menu.row.trend_report.desc": "Week & month over month, dealers, products",
    "menu.row.delivery_status.title": "Delivery Status",
    "menu.row.delivery_status.desc": "Delivery/read status for invoices & broadcasts",
    "menu.row.undo_payment.title": "Undo Payment",
    "menu.row.undo_payment.desc": "Void the payment you just recorded",
    "menu.row.undo_order.title": "Undo Order",
    "menu.row.undo_order.desc": "Void the order you just created",
    "menu.row.edit_invoice.title": "Edit Invoice",
    "menu.row.edit_invoice.desc": "Correct an invoice's amount, date, or party",
    "menu.row.edit_payment.title": "Edit Payment",
    "menu.row.edit_payment.desc": "Correct a recorded payment's amount or date",
    "menu.row.edit_dealer.title": "Edit Dealer",
    "menu.row.edit_dealer.desc": "Update a dealer's phone, limit, terms, GSTIN",
    "menu.row.edit_supplier.title": "Edit Supplier",
    "menu.row.edit_supplier.desc": "Update a supplier's phone, limit, terms, GSTIN",
    "menu.row.stock_take.title": "Stock Take",
    "menu.row.stock_take.desc": "Recount or adjust stock for several products",
    # ── Guided write-workflows (shared) ────────────────────────────────────
    "workflow.cancelled": "OK, cancelled.",
    "workflow.yes_no": "Please reply yes or no.",
    "workflow.error_restart": (
        "Something went wrong with that. Please start again by saying '{trigger}'."
    ),
    "workflow.kind_dealer": "dealer",
    "workflow.kind_supplier": "supplier",
    # ── Record payment ─────────────────────────────────────────────────────
    "payment.start": "Who paid you, or who did you pay? (party name)",
    "payment.need_party": "Please tell me the party's name.",
    "payment.amount_receivable": "How much did they pay you? (e.g. 25000)",
    "payment.amount_payable": "How much did you pay them? (e.g. 25000)",
    "payment.disambiguation": (
        "'{name}' matches both a dealer and a supplier on file. "
        "Reply 1 if they're the dealer (they paid you), "
        "or 2 if they're the supplier (you paid them)."
    ),
    "payment.dealer_or_supplier_invalid": "Please reply 1 for dealer or 2 for supplier.",
    "payment.invoice_selection_invalid": "Please reply with a number from 1 to {count}, or 'all'.",
    "payment.open_invoices": (
        "{party} has {count} open invoices:\n{listing}\n"
        "Reply with a number, or 'all' to apply across all of them (oldest first)."
    ),
    "payment.open_invoice_line": (
        "{index}. {number} — {total} total, {outstanding} outstanding, due {due}"
    ),
    "payment.new_party_type": (
        "I don't have '{name}' on file. Are they a dealer (customer) or a supplier "
        "(you buy from)? Reply 1 Dealer or 2 Supplier."
    ),
    "payment.new_party_type_invalid": "Please reply 1 Dealer or 2 Supplier.",
    "payment.add_new_party": "Add '{name}' as a new {kind}? yes/no",
    "payment.no_open_invoice": (
        "I can only record a payment against an existing invoice, though, and {party} "
        "doesn't have an open one as a {kind}. Create an invoice for them first, then "
        "say 'record payment' again."
    ),
    "payment.got_it_no_invoice": "Got it. {message}",
    "payment.amount_invalid": "Please send an amount, e.g. 25000.",
    "payment.amount_positive": "Please send an amount greater than zero.",
    "payment.date_ask": (
        "When was this paid? Reply 'today', 'yesterday', '3 days ago', or skip for today."
    ),
    "payment.date_invalid": (
        "Sorry, I didn't get that date. Try 'today', 'yesterday', '3 days ago'."
    ),
    "payment.verb_from": "from",
    "payment.verb_to": "to",
    "payment.target_invoice": " against invoice {number}",
    "payment.preview": (
        "Confirm: {amount} {verb} {party}{target} on {date}.{warning}\n"
        "Reply YES to record, NO to cancel."
    ),
    "payment.duplicate_warning": (
        "⚠️ This looks similar to a payment already recorded: {party}, {amount} on {date}. "
        "If that's a separate, intentional payment, reply YES to continue."
    ),
    # ── Create order ───────────────────────────────────────────────────────
    "order.start": "Who is this order for? (dealer name)",
    "order.need_dealer": "Please tell me the dealer's name.",
    "order.dealer_found": "Order for {dealer}. What product?",
    "order.add_new_dealer": (
        "I don't have '{dealer}' on file as a dealer. Add them as a new dealer? yes/no"
    ),
    "order.new_dealer_added": "Got it, {dealer} will be added as a new dealer. What product?",
    "order.need_one_product": "Add at least one product first, or 'cancel'.",
    "order.need_product": "Please tell me the product name, or 'done' if you're finished.",
    "order.quantity_ask": "How many {unit} of {product}?",
    "order.price_ask": "What's the selling price for {product}?",
    "order.add_new_product": "I don't have '{product}' in your catalogue. Add it? yes/no",
    "order.new_product_declined": "OK. What product? (or 'done')",
    "order.price_invalid": "Please send a price, e.g. 55.",
    "order.price_positive": "Please send a price greater than zero.",
    "order.quantity_invalid": "Please send a quantity, e.g. 10.",
    "order.quantity_positive": "Please send a quantity greater than zero.",
    "order.item_added": "Added {quantity} x {product}. Add another product, or reply 'done'.",
    "order.line": "- {quantity} x {product} @ {price} = {total}",
    "order.subtotal": "Subtotal: {amount}",
    "order.gst": "GST{rate_label}: {amount}",
    "order.total": "Total: {amount}",
    "order.payment_made": "Payment Made: {amount}",
    "order.balance_due": "Balance Due: {amount}",
    "order.advance_amount_ask": "How much did the dealer pay in advance? (e.g. 5000)",
    "order.advance_amount_invalid": "Please send a number greater than zero, e.g. 5000.",
    "order.advance_exceeds_total": (
        "That's more than the order total of {total}. Send a smaller amount, or reply YES to "
        "create the order without an advance."
    ),
    "order.preview_header": "Confirm order for {dealer}:",
    "order.preview_footer": (
        "Reply YES to create, NO to cancel, or ADVANCE if the dealer already paid something."
    ),
    "order.duplicate_warning": (
        "⚠️ This looks similar to an existing invoice ({number}) for this dealer — same date "
        "and total. If this is a separate, intentional order, reply YES to continue."
    ),
    "order.credit_limit_warning": (
        "⚠️ This order would take {dealer}'s outstanding to {prospective}, over their credit "
        "limit of {limit}."
    ),
    # ── Edit invoice / edit payment (safe cases only) ───────────────────────
    "edit.invoice_number_ask": "Which invoice? Send its invoice number, or 'cancel'.",
    "edit.invoice_not_found": (
        "I couldn't find an invoice numbered '{number}'. Check and try again, or 'cancel'."
    ),
    "edit.invoice_has_payment": (
        "Invoice {number} already has a payment recorded against it — void it and recreate instead."
    ),
    "edit.field_ask_invoice": (
        "What do you want to edit — amount, date, or party? Reply 'amount', 'date', or 'party'."
    ),
    "edit.field_invalid_invoice": "Please reply 'amount', 'date', or 'party' — or 'cancel'.",
    "edit.amount_ask": "Current amount is {current}. What should the new amount be? (e.g. 1200)",
    "edit.date_ask": "Current date is {current}. What should the new date be? (e.g. 2026-01-15)",
    "edit.invoice_party_ask_dealer": "Current dealer is {current}. Send the new dealer's name.",
    "edit.invoice_party_ask_supplier": (
        "Current supplier is {current}. Send the new supplier's name."
    ),
    "edit.amount_invalid": "Please send a number greater than zero, e.g. 1200.",
    "edit.date_invalid": "Please send a date like 2026-01-15.",
    "edit.party_not_found": (
        "I couldn't find '{name}'. Check the spelling and try again, or 'cancel'."
    ),
    "edit.value_preview": "Change {target}'s {field} to {new}?",
    "edit.target_invoice": "invoice {number}",
    "edit.target_payment": "the payment on invoice {number}",
    "edit.reason_ask": "{preview}\nWhy? Reply with a short reason, or 'skip'.",
    "edit.confirm_prompt": "{preview}\nReply YES to confirm, NO to cancel.",
    "edit.party_name_ask": (
        "Which dealer or supplier's payment do you want to edit? Send their name, or 'cancel'."
    ),
    "edit.no_payments_for_party": "No payments on file for {name}.",
    "edit.payment_pick_ask": (
        "Found {count} recent payments for {name}:\n{listing}\nReply with the number, or 'cancel'."
    ),
    "edit.payment_pick_invalid": "Please reply with a number from 1 to {count}, or 'cancel'.",
    "edit.payment_gone": (
        "That payment is no longer available. Please start again by saying 'edit payment'."
    ),
    "edit.field_ask_payment": (
        "What do you want to edit — amount or date? Reply 'amount' or 'date'."
    ),
    "edit.field_invalid_payment": "Please reply 'amount' or 'date' — or 'cancel'.",
    # ── Update GST ─────────────────────────────────────────────────────────
    "gst.scope_prompt": (
        "Update GST for all products (company default), or one specific product? "
        "Reply 'all' or the product name."
    ),
    "gst.rate_ask_all": "What's the new default GST rate for {target}? (0-100, or 'cancel')",
    "gst.rate_ask_product": (
        "What's the new GST rate for {target}? (0-100, 'clear' to remove its override "
        "and use the company default, or 'cancel')"
    ),
    "gst.not_found": (
        "I couldn't find a product named '{name}'. Reply 'all', another product name, or 'cancel'."
    ),
    "gst.rate_invalid": "Please send a number between 0 and 100, e.g. 18.",
    "gst.all_products": "all products",
    "gst.no_override": "no override (use the company default)",
    "gst.rate_pct": "{rate}%",
    "gst.preview": "Set GST for {target} to {rate_text}. Reply YES to confirm, NO to cancel.",
    # ── Product: mode / disambiguation / delete / update ───────────────────
    "product.mode_prompt": (
        "Let's add products. Reply 'one by one' to add them individually, "
        "or 'bulk' to send them all at once with full details "
        "(e.g. Rice, 300, 400, kg, 100, 5). Reply 'done' to stop anytime."
    ),
    "product.no_products_added": "OK, no products added.",
    "product.all_done": "All done adding products.",
    "product.name_or_done": "Send the product's name (e.g. Rice), or 'done' to stop.",
    "product.mode_invalid": "Please reply 'one by one' or 'bulk' — or 'done' to stop.",
    "product.not_found_retry": (
        "I couldn't find a product named '{name}'. Check the spelling and try again, "
        "or reply 'cancel'."
    ),
    "product.disambiguation": (
        "Found {count} products named '{name}':\n{listing}\n"
        "Reply with the number to {action}, or 'cancel'."
    ),
    "product.disambiguation_invalid": "Please reply with a number from 1 to {count}, or 'cancel'.",
    "product.candidate_line": "{index}. {description}",
    "product.candidate_desc": "{name} ({details})",
    "product.candidate_stock": "{stock} in stock",
    "product.gone": (
        "That product is no longer available. Please start again by saying '{trigger}'."
    ),
    "product.delete_name_prompt": (
        "Which product do you want to delete? Send its name, or 'cancel'."
    ),
    "product.delete_confirm": (
        "Delete {description}? This can't be undone. Reply YES to delete, NO to cancel."
    ),
    "product.delete_no": "OK, not deleted.",
    "product.delete_confirm_invalid": "Please reply YES to delete, or NO to cancel.",
    "product.delete_already_gone": "{name} was already removed.",
    "product.deleted": "Deleted {name}.",
    "product.field_prompt": (
        "What do you want to update — price, purchase price, or stock? "
        "Reply 'price', 'purchase price', or 'stock'."
    ),
    "product.action_update": "update",
    "product.action_delete": "delete",
    "product.label_price": "price",
    "product.label_purchase": "purchase price",
    "product.label_stock": "stock",
    "product.update_name_prompt": (
        "Which product's {label} do you want to update? Send its name, or 'cancel'."
    ),
    "product.current_price": (
        "{name}'s current price is {current}. What should the new price be? (e.g. 450)"
    ),
    "product.current_purchase": (
        "{name}'s current purchase price is {current}. "
        "What should the new purchase price be? (e.g. 300)"
    ),
    "product.current_stock": (
        "{name}'s current stock is {current}. What should the new stock be? (e.g. 100)"
    ),
    "product.value_invalid": "Please send a number, e.g. 450.",
    "product.value_nonneg": "Please send a number of zero or more.",
    "product.value_positive": "Please send a number greater than zero.",
    "product.gone_value": "That product is no longer available.",
    "product.not_set": "not set",
    "product.updated_price": "Updated {name}'s price to {new} (was {old}).",
    "product.updated_purchase": "Updated {name}'s purchase price to {new} (was {old}).",
    "product.updated_stock": "Updated {name}'s stock to {new} (was {old}).",
    # ── Stock take (bulk stock recount/adjustment) ──────────────────────────
    "stock_take.start_prompt": (
        "Let's do a stock take. For each product, send its name, then the new count "
        "(e.g. 40) or an adjustment (e.g. +15 found, -3 damaged). Reply 'done' when "
        "finished, or 'cancel' anytime."
    ),
    "stock_take.line_prompt": "Send a product name, or 'done' to finish.",
    "stock_take.value_ask": (
        "{name} — send the new count (e.g. 40) or an adjustment (e.g. +15, -3)."
    ),
    "stock_take.value_invalid": "Please send a number, e.g. 40, +15, or -3.",
    "stock_take.line_added": "{name}: {old} → {new}. Send the next product, or 'done'.",
    "stock_take.nothing_to_apply": "OK, no changes made.",
    "stock_take.reason_ask": "Why? Reply with a short reason, or 'skip'.",
    "stock_take.confirm_prompt": "{summary}\nReply YES to apply, NO to cancel.",
    "stock_take.failed": "Couldn't apply the stock take: {error}. Please start again.",
    "stock_take.result_line": "- {name}: {new}",
    "stock_take.success": "✅ Stock updated for {count} product(s):\n{lines}{warning}",
    # ── Marketing broadcast (guided workflow) ───────────────────────────────
    "broadcast.segment_ask": (
        "Who should get this broadcast?\n1. All dealers\n2. Dealers with an overdue balance\n"
        "3. Pick specific dealers by name\nReply 1, 2, or 3 — or 'cancel'."
    ),
    "broadcast.segment_invalid": "Please reply 1, 2, or 3 — or 'cancel'.",
    "broadcast.segment.all": "all dealers",
    "broadcast.segment.overdue": "dealers with an overdue balance",
    "broadcast.segment.specific": "the dealers you picked",
    "broadcast.dealer_names_ask": (
        "Send the dealer name(s), one per line (or comma-separated), or 'cancel'."
    ),
    "broadcast.dealer_names_none_matched": (
        "I couldn't match any of these to a dealer on file: {names}. Please try again, "
        "or 'cancel'."
    ),
    "broadcast.dealer_names_unmatched": (
        "\n(Couldn't match: {names} — check the spelling and edit them in separately if needed.)"
    ),
    "broadcast.message_ask": (
        "This will reach {count} dealer(s) once opted in. What message should I send?"
    ),
    "broadcast.message_empty": "Please send a message to broadcast, or 'cancel'.",
    "broadcast.no_opted_in": (
        "None of {segment} have opted into marketing broadcasts yet. Ask them to opt in, "
        "or use 'edit dealer' / 'opt in all dealers'."
    ),
    "broadcast.confirm_prompt": (
        "Send this to {count} dealer(s)?{capped_note}\n\n\"{message}\"\n\n"
        "Reply YES to send, NO to cancel."
    ),
    "broadcast.confirm_capped": " (capped at {cap} per broadcast)",
    "broadcast.opt_in_all_none": "Every dealer is already opted in.",
    "broadcast.opt_in_all_confirm": (
        "Opt {count} dealer(s) into marketing broadcasts? Reply YES to confirm, NO to cancel."
    ),
    # ── Party: add-dealer / add-supplier workflow (mode / done wording) ────
    "party.dealer.mode_prompt": (
        "Let's add dealers. Reply 'one by one' to add them individually, "
        "or 'bulk' to send them all at once (e.g. Ram Traders, 9876543210, 15). "
        "Reply 'done' to stop anytime."
    ),
    "party.dealer.no_added": "OK, no dealers added.",
    "party.dealer.all_done": "All done adding dealers.",
    "party.dealer.name_or_done": "Send the dealer's name (e.g. Ram Traders), or 'done' to stop.",
    "party.dealer.mode_invalid": "Please reply 'one by one' or 'bulk' — or 'done' to stop.",
    "party.supplier.mode_prompt": (
        "Let's add suppliers. Reply 'one by one' to add them individually, "
        "or 'bulk' to send them all at once (e.g. Metro Distributors, 9988776655, 30). "
        "Reply 'done' to stop anytime."
    ),
    "party.supplier.no_added": "OK, no suppliers added.",
    "party.supplier.all_done": "All done adding suppliers.",
    "party.supplier.name_or_done": (
        "Send the supplier's name (e.g. Metro Distributors), or 'done' to stop."
    ),
    "party.supplier.mode_invalid": "Please reply 'one by one' or 'bulk' — or 'done' to stop.",
    # ── Edit dealer / edit supplier (phone, credit limit, terms, GSTIN) ─────
    "party.edit.field_prompt_dealer": (
        "What do you want to edit — phone, credit limit, payment terms, GSTIN, marketing "
        "opt-in, or direct reminders? Reply 'phone', 'credit limit', 'payment terms', 'gstin', "
        "'marketing', or 'reminders'."
    ),
    "party.edit.field_invalid_dealer": (
        "Please reply 'phone', 'credit limit', 'payment terms', 'gstin', 'marketing', or "
        "'reminders' — or 'cancel'."
    ),
    "party.edit.field_prompt_supplier": (
        "What do you want to edit — phone, credit limit, payment terms, or GSTIN? "
        "Reply 'phone', 'credit limit', 'payment terms', or 'gstin'."
    ),
    "party.edit.field_invalid_supplier": (
        "Please reply 'phone', 'credit limit', 'payment terms', or 'gstin' — or 'cancel'."
    ),
    "party.edit.name_ask_dealer": "Which dealer? Send their name, or 'cancel'.",
    "party.edit.name_ask_supplier": "Which supplier? Send their name, or 'cancel'.",
    "party.edit.not_found": (
        "I couldn't find '{name}'. Check the spelling and try again, or 'cancel'."
    ),
    "party.edit.disambiguation": (
        "Found {count} matches named '{name}':\n{listing}\n"
        "Reply with the number to edit, or 'cancel'."
    ),
    "party.edit.disambiguation_invalid": (
        "Please reply with a number from 1 to {count}, or 'cancel'."
    ),
    "party.edit.gone": (
        "That record is no longer available. Please start again by saying '{trigger}'."
    ),
    "party.edit.gone_value": "That record is no longer available.",
    "party.edit.phone_ask": "{name}'s current phone is {current}. What should the new phone be?",
    "party.edit.credit_limit_ask": (
        "{name}'s current credit limit is {current}. What should the new credit limit be? "
        "(e.g. 50000)"
    ),
    "party.edit.payment_terms_ask": (
        "{name}'s current payment terms are {current} days. What should the new terms be, "
        "in days? (e.g. 30)"
    ),
    "party.edit.gstin_ask": "{name}'s current GSTIN is {current}. What should the new GSTIN be?",
    "party.edit.marketing_ask": (
        "{name}'s marketing opt-in is currently {current}. Reply 'yes'/'opt in' or "
        "'no'/'opt out'."
    ),
    "party.edit.marketing_invalid": "Please reply 'yes'/'opt in' or 'no'/'opt out', or 'cancel'.",
    "party.edit.opted_in": "opted in",
    "party.edit.opted_out": "opted out",
    "party.edit.direct_reminders_ask": (
        "{name}'s direct reminders are currently {current}. Reply 'yes'/'enable' or "
        "'no'/'disable'."
    ),
    "party.edit.direct_reminders_invalid": (
        "Please reply 'yes'/'enable' or 'no'/'disable', or 'cancel'."
    ),
    "party.edit.reminders_enabled": "enabled",
    "party.edit.reminders_disabled": "disabled",
    "party.edit.days_invalid": "Please send a whole number of days, e.g. 30.",
    "party.edit.phone_invalid": (
        "That doesn't look like a valid phone number. Include the country code if it's not "
        "Indian, e.g. +919876543210."
    ),
    "party.edit.gstin_invalid": (
        "That doesn't look like a valid GSTIN. Please check and try again, or 'cancel'."
    ),
    "party.edit.value_preview": "Change {name}'s {field} to {new}?",
    "party.edit.success": "✅ {name}'s {field} updated to {new} (was {old}).",
    # ── Void payment / void order ───────────────────────────────────────────
    "void.payment_none": "No WhatsApp-recorded payment to undo.",
    "void.payment_preview": (
        "Void payment of {amount} against invoice {invoice_number} for {party}?"
    ),
    "void.order_none": "No WhatsApp-recorded order to undo.",
    "void.order_has_payment": (
        "Order {invoice_number} already has a payment recorded against it — "
        "void the payment first, then try again."
    ),
    "void.order_preview": "Void order {invoice_number} for {dealer} (total {total})?",
    "void.reason_ask": "{preview}\nWhy? Reply with a short reason, or 'skip'.",
    "void.confirm_prompt": "{preview}\nReply YES to void, or NO to cancel.",
    # ── Pending-operation confirm/execute results ──────────────────────────
    "pending.reply_yes_no": "Reply YES to confirm or NO to cancel.",
    "pending.payment_failed": "Couldn't record that payment: {error}. Please start again.",
    "pending.payment_success": (
        "✅ {amount} recorded {verb} {party}.\n"
        "Invoices updated: {invoices}\n"
        "Remaining outstanding: {outstanding}"
    ),
    "pending.order_failed": "Couldn't create that order: {error}. Please start again.",
    "pending.order_line": "- {quantity} x {product} = {total}",
    "pending.order_stock_warning": "\n⚠️ Stock now negative for: {products}",
    "pending.order_pdf_sent": "\nPDF sent to {dealer}.",
    "pending.order_pdf_not_sent": (
        "\n(PDF not sent to {dealer} — no phone on file or WhatsApp delivery not yet configured.)"
    ),
    "pending.order_pdf_sent_to_founder": (
        "\n(Couldn't reach {dealer} directly — sent you the PDF above so you can forward "
        "it yourself.)"
    ),
    "pending.order_success": (
        "✅ Order {number} created for {dealer}.\n{lines}\n"
        "Subtotal: {subtotal}\nGST: {gst}\nTotal: {total}\n"
        "Payment Made: {payment_made}\nBalance Due: {balance_due}{warning}{pdf_note}"
    ),
    "pending.gst_failed": "Couldn't update GST: {error}. Please start again.",
    "pending.gst_success": "✅ GST for {target} set to {rate}.",
    "pending.gst_rate_default": "the company default",
    "pending.void_payment_failed": "Couldn't void that payment: {error}. Please start again.",
    "pending.void_payment_success": (
        "✅ Voided payment of {amount} against invoice {invoice_number} for {party}."
    ),
    "pending.void_order_failed": "Couldn't void that order: {error}. Please start again.",
    "pending.void_order_success": "✅ Voided order {invoice_number} for {dealer} (total {total}).",
    "pending.edit_invoice_failed": "Couldn't edit that invoice: {error}. Please start again.",
    "pending.edit_invoice_success": "✅ Invoice {number}'s {field} updated to {new} (was {old}).",
    "pending.edit_payment_failed": "Couldn't edit that payment: {error}. Please start again.",
    "pending.edit_payment_success": (
        "✅ Payment on invoice {number}: {field} updated to {new} (was {old})."
    ),
    "pending.broadcast_failed": "Couldn't send that broadcast: {error}. Please start again.",
    "pending.broadcast_success": (
        "✅ Broadcast sent to {sent} of {total} dealer(s) ({failed} failed)."
    ),
    "pending.opt_in_all_failed": "Couldn't opt dealers in: {error}. Please start again.",
    "pending.opt_in_all_success": "✅ Opted {count} dealer(s) into marketing broadcasts.",
    "pending.unknown": "Something went wrong with that confirmation. Please start again.",
    # ── Numbered-menu prompt (shared: follow-up fallback, briefing footer) ──
    "menu.prompt": "Reply 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk",
    # ── Invoice due-date follow-up conversation (distributor-facing) ───────
    "followup.message": (
        "📋 Payment Follow-Up\n\n"
        "{number} — {dealer} — {amount}\n"
        "Due date: today\n\n"
        "Has payment been received?\n"
        "1. Yes — full amount\n"
        "2. Partial payment\n"
        "3. Not yet received"
    ),
    "followup.recorded_full": (
        "{amount} payment recorded from {dealer}.\n"
        "{number} closed.\n"
        "Outstanding: ₹0.\n"
        "Cash and tomorrow's briefing updated."
    ),
    "followup.recorded_partial": (
        "{amount} partial payment recorded.\n"
        "{number} — {remaining} still outstanding.\n"
        "Cash and tomorrow's briefing updated."
    ),
    "followup.invoice_gone": "That invoice is no longer available. {menu_prompt}",
    "followup.ask_partial": "How much was received?",
    "followup.ask_expected_date": (
        "When do you expect payment from {dealer}?\nExample: Friday, 3 days, next week"
    ),
    "followup.confirm_invalid": "I didn't understand that. Reply 1, 2, or 3.",
    "followup.amount_invalid": "I didn't understand that amount. Please send a number, e.g. 25000.",
    "followup.date_invalid": "I didn't understand that date.\nExample: Friday, 3 days, next week",
    "followup.rescheduled": (
        "Noted. {number} follow-up scheduled for {when}.\n{dealer} flagged in tomorrow's briefing."
    ),
    "followup.error": "Something went wrong with that follow-up. {menu_prompt}",
    # ── Proactive notifications (distributor-facing only; founder alerts EN) ─
    "notify.supplier_reminder": (
        "⏰ Payment Reminder\n\n"
        "{supplier} payment of {amount} due {when}.\n"
        "{cash_line}\n"
        "No action needed unless cash position has changed."
    ),
    "notify.when_today": "today",
    "notify.when_tomorrow": "tomorrow",
    "notify.cash_line": "Current cash available: {amount} — {sufficiency}",
    "notify.cash_sufficient": "sufficient.",
    "notify.cash_insufficient": "may be insufficient.",
    # ── Supplier-reminder payment confirmation ──────────────────────────────
    "reminder_confirm.ask_paid": (
        "Have you already paid {supplier} {amount}?\nReply 1 if yes, 2 if not yet paid."
    ),
    "reminder_confirm.invalid_choice": (
        "Sorry, I didn't catch that. Have you already paid {supplier} {amount}?\n"
        "Reply 1 if yes, 2 if not yet paid."
    ),
    "reminder_confirm.amount_ask": (
        "Confirm the amount paid: {amount}. Reply a different number to change it, "
        "or 'ok' to confirm."
    ),
    "reminder_confirm.amount_invalid": "Please send an amount, e.g. 25000.",
    "reminder_confirm.amount_positive": "Please send an amount greater than zero.",
    "reminder_confirm.reschedule_ask": (
        "OK — reply with a new date to reschedule this reminder (e.g. 'tomorrow', 'next week', "
        "'3 days'), or 'skip' to leave it due — I'll remind you again."
    ),
    "reminder_confirm.reschedule_invalid": (
        "I didn't understand that date. Try 'tomorrow', 'next week', '3 days' — or 'skip'."
    ),
    "reminder_confirm.rescheduled": (
        "Got it — {supplier}'s payment is now due {date}. I'll remind you again closer to then."
    ),
    "reminder_confirm.kept_due": "OK, I'll remind you again.",
    "reminder_confirm.invoice_gone": "That bill is no longer open — no need to reschedule.",
    "notify.dealer_alert": (
        "⚠ Collection Alert\n\n"
        "{dealer} — {amount} — now {days} days overdue.\n"
        "No follow-up recorded in 3 days.\n"
        "Suggested: call today before placing new order."
    ),
    # Sent straight to the dealer's own WhatsApp (not the distributor) —
    # only when that dealer has direct_reminders_enabled. Kept polite/plain,
    # no interactive reply expected (a dealer's reply lands on the same
    # webhook as any other unrecognized sender and is simply ignored — see
    # Dealer.direct_reminders_enabled's docstring).
    "notify.dealer_direct_reminder": (
        "Hi {dealer}, this is a reminder from {business} — a payment of {amount} was due "
        "{days} day(s) ago. Please arrange payment at your earliest convenience. Thank you!"
    ),
    # ── Proactive early-warning alerts (7-day forecasts) ────────────────────
    "notify.cash_shortage_forecast": (
        "⚠️ Cash Shortage Forecast\n\n"
        "Cash is projected to go negative in ~{days} day(s).\n\n"
        "Main upcoming payment: {supplier} — {amount} (due in {trigger_days} day(s))\n\n"
        "Expected out (7d): {expected_out}\n"
        "Expected in (7d, incl. cash on hand): {expected_in}"
    ),
    "notify.stock_out_forecast": (
        "📦 Stock Alert\n\n"
        "{product} may run out in ~{days} day(s) at the current sales pace."
    ),
    "notify.predue_nudge": (
        "🔔 Due Soon\n\n"
        "{dealer}\n"
        "{amount}\n\n"
        "Due in {days} day(s).\n\n"
        "Suggested action:\n"
        "• Call the dealer\n"
        "• Confirm payment\n"
        "• If already received, reply: record payment"
    ),
    # ── Briefing "Watch this week" section (deterministic, not LLM-narrated) ─
    "briefing.watch.header": "⚠ Watch this week",
    "briefing.watch.cash_shortage": (
        "• Cash shortage in ~{days} day(s) — mainly {supplier} {amount}"
    ),
    "briefing.watch.stock_out": "• {product} may run out in ~{days} day(s)",
    "briefing.watch.predue": "• {dealer} payment due in {days} day(s)",
    # ── Evening business summary ───────────────────────────────────────────
    "evening.header": "🌙 Evening Business Summary",
    "evening.counts": (
        "Invoices Created: {invoices} · Orders via WhatsApp: {orders} · "
        "Payments Recorded: {payments}"
    ),
    "evening.sales": "Sales Today: {amount}",
    "evening.margin": "Sales Margin: {amount}",
    "evening.margin_excluded": " ({items} items, {amount} excluded — no cost price on file)",
    "evening.collections": "Collections: {amount}",
    "evening.supplier_payments": "Supplier Payments: {amount}",
    "evening.net_cash": "Net Cash Movement: {amount}",
    "evening.outstanding": "Outstanding Receivables: {amount}",
    "evening.priority_header": "Priority Actions:",
}
