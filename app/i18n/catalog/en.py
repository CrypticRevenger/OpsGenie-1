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

*Suppliers (you owe them)*
• suppliers / all suppliers — every supplier with phone & outstanding
• top creditors — suppliers you owe the most
• balance <name> — outstanding for one supplier

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

*Orders & Payments*
• new order (or /create_order, or "new invoice") — record a sale to a dealer, product by product
• record payment (or /record_payment) — log a payment received from a dealer or paid to a supplier

*Your Data*
• export data (or /export_data) — a download link to your full business data as Excel
• morning briefing (or /morning_briefing) — resend today's briefing

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
    "onboarding.product.first_name": (
        "Send your first product's name (e.g. Rice), or 'done' to skip."
    ),
    "onboarding.product.mode_invalid": (
        "Please reply 'one by one' or 'bulk' — or 'done' to skip adding products."
    ),
    "onboarding.product.bulk_error": "Couldn't read that: {error}",
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
        "Let's add your dealers (customers). Send the first dealer's name, or 'done'."
    ),
    "onboarding.dealer.credit_ask": "How many credit days do you give {name}? (e.g. 15, or 'skip')",
    "onboarding.dealer.added": "Added dealer {name}. Next dealer's name, or 'done'.",
    # Suppliers
    "onboarding.suppliers.intro": "Now your suppliers. Send the first supplier's name, or 'done'.",
    "onboarding.supplier.credit_ask": (
        "How many days does {name} give you to pay? (e.g. 15/'skip')"
    ),
    "onboarding.supplier.added": "Added supplier {name}. Next supplier's name, or 'done'.",
    # Shared party fields
    "onboarding.party.phone_ask": "Phone number for {name}? (or 'skip')",
    "onboarding.party.credit_invalid": "Please send a number of days, e.g. 15 (or 'skip').",
    # Opening cash
    "onboarding.opening.ask": "How much cash is currently in your business? (e.g. 320000)",
    "onboarding.opening.invalid": "Please send an amount, e.g. 320000.",
    # Receivables
    "onboarding.receivable.ask": "Do any dealers currently owe you money? (yes/no)",
    "onboarding.receivable.which": "Which dealer owes you? (name)",
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
    # ── Interactive menu ("menu") ──────────────────────────────────────────
    # The tappable-list plaintext that accompanies the list message, plus the
    # per-message body/button labels, section titles, and row titles +
    # descriptions. Row *ids* stay English (they are read back as commands);
    # only the human-readable titles/descriptions are localized.
    "menu.fallback": "Tap an option below, or reply /help for the full list.",
    "menu.msg.reports.body": "Reports & Overview — tap one:",
    "menu.msg.reports.button": "Choose a report",
    "menu.msg.inventory.body": "Inventory, Transactions & Products — tap one:",
    "menu.msg.inventory.button": "Choose an option",
    "menu.msg.orders.body": "Orders, Payments & Your Data — tap one:",
    "menu.msg.orders.button": "Choose an option",
    "menu.section.cash_overview": "Cash & Overview",
    "menu.section.money_flow": "Money Flow",
    "menu.section.dealers_suppliers": "Dealers & Suppliers",
    "menu.section.inventory_transactions": "Inventory & Transactions",
    "menu.section.manage_products": "Manage Products",
    "menu.section.orders_payments": "Orders & Payments",
    "menu.section.your_data": "Your Data",
    "menu.section.full_lists": "Full Lists",
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
}
