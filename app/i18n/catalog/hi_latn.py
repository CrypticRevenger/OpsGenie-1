"""Romanized Hindi message catalog (Hindi in Latin letters, WhatsApp style).

DRAFT — needs a native Hindi speaker's review before production go-live.
Romanized spelling has no single standard, so these are natural-WhatsApp
drafts, not transliterations, and business/finance terms are kept in English
where that's how distributors actually type them ("cash", "stock", "GST").
Mirrors the exact keys in en.py (enforced by tests/test_i18n.py); English is
the safe fallback for any key missing here.
"""

from __future__ import annotations

# Full "help" block — DRAFT. Command keywords (cash, /add_product, balance
# <name>) stay English since they are the literal triggers; only the prose /
# descriptions are Romanized Hindi.
_HELP_TEXT = """*OpsGenie Help*

*Cash & Overview*
• cash / cash position — abhi ka cash, 7-din ka expected in/out, net position (ya 1 / /cash)
• summary / business summary — cash, net position, 7-din collections/payments, overdue dealers
• priorities / what should I do — ranked kaam: cash warning, jinko call karna hai, supplier dues

*Dealers (jo aapko dete hain)*
• dealers / all dealers — har dealer phone & baaki ke saath
• top debtors / who owes most — sabse zyada baaki wale dealers
• overdue / overdue dealers — kitne din late & risk level (ya 4 / /dealer_risk)
• balance <name> — ek dealer ka baaki, jaise balance Ram Traders

*Suppliers (jinhe aap dete hain)*
• suppliers / all suppliers — har supplier phone & baaki ke saath
• top creditors — jinhe aap sabse zyada dete hain
• balance <name> — ek supplier ka baaki

*Aane wala Cash Flow*
• collections / upcoming collections — dealers se aane wala, agle 7 din (ya 2 / /collections)
• payments / upcoming payments — suppliers ko dena, agle 7 din (ya 3 / /suppliers)

*Inventory*
• inventory / products / stock — naye add kiye products (stock qty, selling price)
• all inventory — har product, sirf naye nahi
• stock <product> — ek item check karein, jaise stock Rice

*Transactions*
• invoices / recent invoices — naye invoices (number, party, total, status, dates)
• all invoices — har invoice, sirf naye nahi
• payments / recent payments — naye record kiye payments
• all payments / all time payments — har payment, sirf naye nahi
• faq / policy — aapki saved business policy (delivery days, returns, minimum order)

*Products Manage karein* (guided, ek-ek sawaal)
• add product (ya /add_product) — naya item: name, stock, unit, selling price, purchase price
• update stock (ya /update_stock) — product ka stock quantity badlein
• update price (ya /update_price) — product ki selling price badlein
• update purchase price (ya /update_purchase_price) — supplier ko jo dete hain wo badlein
• update product (ya /update_product) — price, purchase price, ya stock chunein
• update gst (ya /update_gst) — sabhi ya ek product ka GST badlein
• delete product (ya /delete_product) — catalogue se item hatayein

*Orders & Payments*
• new order (ya /create_order, ya "new invoice") — dealer ko sale record karein, product by product
• record payment (ya /record_payment) — dealer se aaya ya supplier ko diya payment log karein

*Aapka Data*
• export data (ya /export_data) — poora business data Excel me download link
• morning briefing (ya /morning_briefing) — aaj ki briefing dobara bhejein

*Quick Access*
• menu — type karne ki jagah options tap karein
• help (ya /help) — yeh list kabhi bhi dobara dekhein"""

MESSAGES: dict[str, str] = {
    # ── Errors / fallbacks ────────────────────────────────────────────────
    "errors.something_wrong": "Kuch gadbad ho gayi. Kripya phir se koshish karein.",
    "errors.assistant_fallback": (
        "Maaf karein, main abhi iska jawab nahi de paya. Reply karein 1 Cash · "
        "2 Collections · 3 Suppliers · 4 Dealer Risk, ya dobara likhein."
    ),
    "onboarding.language_changed": "✅ Ho gaya — ab se main aapko {language} mein message karunga.",
    # ── Cash Position report ───────────────────────────────────────────────
    "reports.cash.header": "💰 Cash Position",
    "reports.cash.available_now": "Abhi available: {amount}",
    "reports.cash.expected_in": "Aane wala (7 din): {amount}",
    "reports.cash.due_out": "Dena hai (7 din): {amount}",
    "reports.cash.net_expected": "Net expected: {amount}",
    "reports.cash.shortage": "Is hafte cash ki kami ho sakti hai.",
    "reports.cash.no_shortage": "Is hafte cash ki kami nahi hogi.",
    # ── Collections report ─────────────────────────────────────────────────
    "reports.collections.header": "📥 Baaki Collections",
    "reports.collections.none": "Agle 7 din me koi collection nahi aane wala.",
    "reports.collections.total": "Is hafte total expected: {amount}",
    # ── Supplier payments report ───────────────────────────────────────────
    "reports.suppliers.header": "📤 Supplier Payments Baaki",
    "reports.suppliers.none": "Agle 7 din me koi supplier payment baaki nahi.",
    "reports.suppliers.total": "Is hafte total dena: {amount}",
    "reports.suppliers.cash_ok": "cash kaafi hai",
    "reports.suppliers.cash_short": "cash kam pad sakta hai",
    # ── Dealer risk report ─────────────────────────────────────────────────
    "reports.risk.header": "⚠ Dealer Risk Summary",
    "reports.risk.none": "Abhi koi overdue dealer nahi.",
    "reports.risk.high": "High Risk:",
    "reports.risk.medium": "Medium Risk:",
    "reports.risk.low": "Low Risk:",
    "reports.risk.dealer_line": "{name} — {amount} overdue ({days}d) — {late}",
    # ── Shared phrases ─────────────────────────────────────────────────────
    "reports.due.today": "aaj due",
    "reports.due.weekday": "{day} ko due",
    "reports.due.date": "{date} ko due",
    "reports.late.none": "time par pay karta hai",
    "reports.late.one": "6 mahine me 1 late payment",
    "reports.late.many": "6 mahine me {count} late payments",
    # ── Business summary ───────────────────────────────────────────────────
    "reports.summary.header": "📊 Business Summary",
    "reports.summary.cash_now": "Abhi available cash: {amount}",
    "reports.summary.net_7d": "Net cash position (7d): {amount}",
    "reports.summary.expected_in": "Aane wala (7d): {amount}",
    "reports.summary.expected_out": "Jaane wala (7d): {amount}",
    "reports.summary.shortage": "Is hafte cash ki kami ho sakti hai.",
    "reports.summary.no_shortage": "Cash ki kami nahi hogi.",
    "reports.summary.overdue_count": "Overdue dealers: {count}",
    "reports.summary.overdue_hint": " — detail ke liye 'overdue' bhejein.",
    # ── Priorities ─────────────────────────────────────────────────────────
    "reports.priorities.none": "🎯 Abhi kuch urgent nahi — koi priority action nahi.",
    "reports.priorities.header": "🎯 Priorities",
    # ── Dealer / supplier lists ────────────────────────────────────────────
    "reports.dealers.none": "Aapke paas abhi koi dealer nahi hai.",
    "reports.dealers.header": "👥 Dealers ({count}):",
    "reports.suppliers_list.none": "Aapke paas abhi koi supplier nahi hai.",
    "reports.suppliers_list.header": "🚚 Suppliers ({count}):",
    "reports.party.no_phone": "phone nahi",
    "reports.party.line": "{name} — {phone} — baaki {amount}",
    "reports.top_debtors.none": "Abhi kisi dealer par aapka kuch baaki nahi.",
    "reports.top_debtors.header": "💰 Top Debtors",
    "reports.top_creditors.none": "Abhi aap kisi supplier ko kuch nahi dete.",
    "reports.top_creditors.header": "💸 Top Creditors",
    # ── Inventory ──────────────────────────────────────────────────────────
    "reports.inventory.none": "Aapke catalogue me abhi koi product nahi.",
    "reports.inventory.label_recent": "Recent Inventory",
    "reports.inventory.label_all": "Saara Inventory",
    "reports.inventory.header_partial": "📦 {label} ({count} of {total}):",
    "reports.inventory.header_full": "📦 {label} ({count}):",
    "reports.inventory.more": (
        "\n\n…aur {remaining} zyada — poori list ke liye 'all inventory' bhejein."
    ),
    "reports.product.price_not_set": "price set nahi",
    # ── FAQs ───────────────────────────────────────────────────────────────
    "reports.faq.none": "Aapke paas abhi koi saved policy nahi.",
    "reports.faq.header": "❓ FAQs ({count}):",
    "reports.faq.qa": "Q: {question}\nA: {answer}",
    # ── Invoices ───────────────────────────────────────────────────────────
    "reports.invoices.none": "Aapke paas abhi koi invoice nahi.",
    "reports.invoices.label_recent": "Recent Invoices",
    "reports.invoices.label_all": "Saare Invoices",
    "reports.invoices.header_partial": "📄 {label} ({count} of {total}):",
    "reports.invoices.header_full": "📄 {label} ({count}):",
    "reports.invoices.more": (
        "\n\n…aur {remaining} zyada — poori list ke liye 'all invoices' bhejein."
    ),
    "reports.invoices.line": "{number} — {party} — {amount} — {status} — {due}",
    "reports.unknown_party": "unknown party",
    # ── Payments ───────────────────────────────────────────────────────────
    "reports.payments.none": "Aapke paas abhi koi payment record nahi.",
    "reports.payments.label_recent": "Recent Payments",
    "reports.payments.label_all": "Saare Payments",
    "reports.payments.header_partial": "💵 {label} ({count} of {total}):",
    "reports.payments.header_full": "💵 {label} ({count}):",
    "reports.payments.more": (
        "\n\n…aur {remaining} zyada — poori list ke liye 'all payments' bhejein."
    ),
    "reports.payments.from": "se",
    "reports.payments.to": "ko",
    "reports.payments.line": "{amount} — invoice {number} {direction} — {date}",
    # ── Party balance ──────────────────────────────────────────────────────
    "reports.balance.dealer_owes": "{party} ko aapko {amount} dena hai.",
    "reports.balance.you_owe": "Aapko {party} ko {amount} dena hai.",
    # ── Stock item ─────────────────────────────────────────────────────────
    "reports.stock.not_found": "'{name}' se milta koi product nahi mila.",
    "reports.stock.line": "{name} — {stock} stock me — {price}",
    # ── Sales impact ───────────────────────────────────────────────────────
    "reports.sales.revenue": "revenue {amount}",
    "reports.sales.profit": "profit {amount}",
    "reports.sales.left": "{qty} stock me bacha",
    "reports.sales.total_revenue": "Total revenue: {amount}",
    "reports.sales.total_profit": "Total profit: {amount}",
    "reports.sales.no_cost": "({missing} ka purchase price nahi hai — profit se hataya)",
    # ── Excel export link ──────────────────────────────────────────────────
    "reports.export.not_configured": (
        "Data export link abhi setup nahi hai — apne OpsGenie admin se configure karwayein."
    ),
    "reports.export.ready": (
        "Aapka latest Excel export taiyar hai.\nDownload ({ttl} min valid): {link}"
    ),
    # ── Help text ──────────────────────────────────────────────────────────
    "menu.help_text": _HELP_TEXT,
    # ── Interactive menu ───────────────────────────────────────────────────
    "menu.fallback": "Neeche se ek option tap karein, ya poori list ke liye /help bhejein.",
    "menu.msg.reports.body": "Reports & Overview — ek chunein:",
    "menu.msg.reports.button": "Report chunein",
    "menu.msg.inventory.body": "Inventory, Transactions & Products — ek chunein:",
    "menu.msg.inventory.button": "Ek option chunein",
    "menu.msg.orders.body": "Orders, Payments & aapka Data — ek chunein:",
    "menu.msg.orders.button": "Ek option chunein",
    "menu.section.cash_overview": "Cash & Overview",
    "menu.section.money_flow": "Paise ka Flow",
    "menu.section.dealers_suppliers": "Dealers & Suppliers",
    "menu.section.inventory_transactions": "Inventory & Transactions",
    "menu.section.manage_products": "Products Manage karein",
    "menu.section.orders_payments": "Orders & Payments",
    "menu.section.your_data": "Aapka Data",
    "menu.section.full_lists": "Poori Lists",
    "menu.row.cash.title": "Cash Position",
    "menu.row.cash.desc": "Abhi cash & 7-din in/out",
    "menu.row.summary.title": "Business Summary",
    "menu.row.summary.desc": "Poora snapshot",
    "menu.row.priorities.title": "Priorities",
    "menu.row.priorities.desc": "Aaj kya karun",
    "menu.row.overdue.title": "Overdue Dealers",
    "menu.row.overdue.desc": "Kitne din late & risk level",
    "menu.row.collections.title": "Collections Due",
    "menu.row.collections.desc": "Agle 7 din me aane wala",
    "menu.row.payments.title": "Payments Due",
    "menu.row.payments.desc": "Suppliers ko dena, 7 din",
    "menu.row.all_dealers.title": "Sabhi Dealers",
    "menu.row.all_dealers.desc": "Har dealer, phone & baaki",
    "menu.row.all_suppliers.title": "Sabhi Suppliers",
    "menu.row.all_suppliers.desc": "Har supplier, phone & baaki",
    "menu.row.top_debtors.title": "Top Debtors",
    "menu.row.top_debtors.desc": "Jinko aapko sabse zyada dena hai",
    "menu.row.top_creditors.title": "Top Creditors",
    "menu.row.top_creditors.desc": "Jinhe aap sabse zyada dete hain",
    "menu.row.inventory.title": "Recent Inventory",
    "menu.row.inventory.desc": "Naye products, stock & price",
    "menu.row.invoices.title": "Recent Invoices",
    "menu.row.invoices.desc": "Naye invoices, latest pehle",
    "menu.row.recent_payments.title": "Recent Payments",
    "menu.row.recent_payments.desc": "Naye record kiye payments",
    "menu.row.faq.title": "FAQs",
    "menu.row.faq.desc": "Aapki saved business policies",
    "menu.row.add_product.title": "Product Add karein",
    "menu.row.add_product.desc": "Naya item add karein",
    "menu.row.update_stock.title": "Stock Update karein",
    "menu.row.update_stock.desc": "Product ka stock qty badlein",
    "menu.row.update_price.title": "Price Update karein",
    "menu.row.update_price.desc": "Product ki selling price badlein",
    "menu.row.update_cost.title": "Cost Price Update karein",
    "menu.row.update_cost.desc": "Supplier ko jo dete hain wo badlein",
    "menu.row.delete_product.title": "Product Delete karein",
    "menu.row.delete_product.desc": "Catalogue se item hatayein",
    "menu.row.update_product.title": "Product Update karein",
    "menu.row.update_product.desc": "Price, cost, ya stock chunein",
    "menu.row.create_order.title": "Order Banayein",
    "menu.row.create_order.desc": "Dealer ko sale record karein",
    "menu.row.record_payment.title": "Payment Record karein",
    "menu.row.record_payment.desc": "Aaya ya diya payment log karein",
    "menu.row.update_gst.title": "GST Update karein",
    "menu.row.update_gst.desc": "Sabhi ya ek product ka GST badlein",
    "menu.row.export_data.title": "Data Export karein",
    "menu.row.export_data.desc": "Apna Excel data download karein",
    "menu.row.morning_briefing.title": "Morning Briefing",
    "menu.row.morning_briefing.desc": "Aaj ki briefing dobara bhejein",
    "menu.row.all_inventory.title": "Saara Inventory",
    "menu.row.all_inventory.desc": "Har product, sirf naye nahi",
    "menu.row.all_invoices.title": "Saare Invoices",
    "menu.row.all_invoices.desc": "Har invoice, sirf naye nahi",
    "menu.row.all_payments.title": "Saare Payments",
    "menu.row.all_payments.desc": "Har payment, sirf naye nahi",
}
