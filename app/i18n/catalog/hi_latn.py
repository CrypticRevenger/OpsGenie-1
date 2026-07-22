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
• add dealer (ya /add_dealer) — naya dealer add karein: naam, phone, credit din
• edit dealer (ya /edit_dealer) — dealer ka phone, credit limit, terms, ya GSTIN badlein

*Suppliers (jinhe aap dete hain)*
• suppliers / all suppliers — har supplier phone & baaki ke saath
• top creditors — jinhe aap sabse zyada dete hain
• balance <name> — ek supplier ka baaki
• add supplier (ya /add_supplier) — naya supplier add karein: naam, phone, credit din
• edit supplier (ya /edit_supplier) — supplier ka phone, credit limit, terms, ya GSTIN badlein

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
• stock take (ya /stock_take) — kai products ka stock ek saath recount ya adjust karein

*Orders & Payments*
• new order (ya /create_order, ya "new invoice") — dealer ko sale record karein, product by product
• record payment (ya /record_payment) — dealer se aaya ya supplier ko diya payment log karein

*Corrections*
• undo payment (ya /undo_payment) — abhi record kiya payment void karein
• undo order (ya /undo_order) — abhi banaya order void karein (sirf agar unpaid hai)
• edit invoice (ya /edit_invoice) — invoice ka amount, date, ya party sudharein (sirf unpaid par)
• edit payment (ya /edit_payment) — record kiye payment ka amount ya date sudharein

*Aapka Data*
• export data (ya /export_data) — poora business data Excel me download link
• morning briefing (ya /morning_briefing) — aaj ki briefing dobara bhejein

*Reports & Statements* (is mahine ke, Excel + PDF jahan bataya gaya hai)
• ledger <name> — running-balance statement, Excel + PDF, jaise ledger Ram Traders
• sales register / purchase register (ya dono ke liye "gst report") — GST register + summary
• payment register (ya receipt register) — is mahine ki receipts & payments
• day book — is mahine ke sabhi invoice aur payment, ek hi list me
• outstanding report (ya aging report) — 0-30/31-60/61-90/90+ din ke buckets, Excel + PDF
• trend report (ya business trends) — hafta-wise cash, dealer aur product trends, Excel
• delivery status — aapke bheje invoices aur broadcasts ka Meta delivery/read status

*Marketing*
• broadcast (ya /broadcast) — opted-in dealers ko message bhejein (all, overdue, ya name se pick)
• opt in all dealers — jinhone opt-out nahi kiya unhe broadcast me opt in karein (confirm zaroori)
• edit dealer — 'marketing' reply karke ek dealer ko opt in/opt out karein

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
    "reports.download.ready": (
        "Aapka {report_name} ({period}) taiyar hai.\nDownload ({ttl} min valid):\n{links}"
    ),
    "reports.ledger.not_found": "'{name}' se milta koi dealer ya supplier nahi mila.",
    # ── Business Trends report ────────────────────────────────────────────
    "reports.trend.headline": (
        "📈 Collections {collections_pct}, Payments {payments_pct}, Net Cash {net_delta} · "
        "{dealers_slowing} dealer slow ho rahe hain · {products_declining} product girr rahe hain"
    ),
    "reports.trend.header": "Cash Trend (is hafte vs pichle hafte)",
    "reports.trend.collections_line": "Collections: {current} (pehle {prior} tha)",
    "reports.trend.payments_line": "Supplier Payments: {current} (pehle {prior} tha)",
    "reports.trend.net_line": "Net Cash Movement: {current} (pehle {prior} tha)",
    "reports.trend.sales_line": "Sales (Invoiced): {current} (pehle {prior} tha)",
    "reports.trend.dealers_header": "Dealer Trend (pichle 30 din vs uske pehle 30 din)",
    "reports.trend.dealers_none": "Abhi dealer order activity kam hai, trend nahi dikha sakte.",
    "reports.trend.dealer_rising_line": (
        "▲ {name} — order value {value_delta}, outstanding {outstanding_delta}"
    ),
    "reports.trend.dealer_falling_line": (
        "▼ {name} — order value {value_delta}, outstanding {outstanding_delta}"
    ),
    "reports.trend.products_header": "Product Sales Trend (pichle 30 din vs uske pehle 30 din)",
    "reports.trend.products_none": "Abhi sales activity kam hai, product trend nahi dikha sakte.",
    "reports.trend.product_rising_line": "▲ {name} — units {unit_delta}, revenue {revenue_delta}",
    "reports.trend.product_falling_line": "▼ {name} — units {unit_delta}, revenue {revenue_delta}",
    "reports.trend.full_detail_link": "Har dealer aur product (Excel, {ttl} min valid): {link}",
    # ── Delivery/read status ("delivery status") ────────────────────────────
    "reports.delivery_status.header": "📨 Delivery Status",
    "reports.delivery_status.none": (
        "Abhi tak koi invoice ya broadcast dealers ko nahi bheja gaya hai."
    ),
    "reports.delivery_status.line": "{label} ({when}): {counts}",
    "reports.delivery_status.invoice_label": "{invoice} → {party}",
    "reports.delivery_status.broadcast_label": "Broadcast — {count} dealers",
    "reports.delivery_status.count_part": "{count} {status}",
    "reports.delivery_status.status.sent": "sent",
    "reports.delivery_status.status.delivered": "delivered",
    "reports.delivery_status.status.read": "read",
    "reports.delivery_status.status.failed": "failed",
    "reports.delivery_status.status.failed_to_send": "not sent",
    # ── Help text ──────────────────────────────────────────────────────────
    "menu.help_text": _HELP_TEXT,
    # ── Onboarding ─────────────────────────────────────────────────────────
    "onboarding.intro": (
        "👋 OpsGenie me swagat hai! Chaliye aapka business set up karein — 5 minute lagenge, "
        "aur aap kabhi bhi ruk kar continue kar sakte hain.\n\n"
        "Sabse pehle: aap kaisa business chalate hain? (jaise FMCG Distributor, Pharma Distributor)"
    ),
    "onboarding.progress": "✅ Step {step}/{total} ho gaya.",
    "onboarding.finish": (
        "🎉 Setup pura ho gaya!\n\n"
        "Kal subah se main aapko roz ki briefing bhejunga. Aap mujhse kuch bhi pooch sakte hain, "
        "jaise:\n"
        "• Cash position\n"
        "• Ram ko kitna dena hai?\n"
        "• Supplier dues\n"
        "• Dealer risk\n\n"
        "Kabhi bhi menu bhejein options tap karne ke liye, ya /help poori list dekhne ke liye."
    ),
    "onboarding.gst.mode_ask": (
        "Kya aapke sabhi products ka GST rate same hai, ya product ke hisab se alag? "
        "Reply karein 'same', 'varies', ya 'not sure' baad me decide karne ke liye."
    ),
    "onboarding.gst.rate_ask": "Aapka GST rate kya hai? (jaise 5, 12, 18, ya 0 agar exempt)",
    "onboarding.gst.mode_invalid": "Kripya reply karein 'same', 'varies', ya 'not sure'.",
    "onboarding.gst.rate_invalid": (
        "Kripya 0 se 100 ke beech number bhejein, jaise 18 (ya 'not sure' baad me decide karein)."
    ),
    "onboarding.gst.missing_ask": (
        "Humne aapke zyadatar products ke GST rates import kar liye hain. In {count} me abhi "
        "tak nahi hai: {names}. Inke liye kaunsa GST rate use karein? (jaise 5, 12, 18, ya 0 — "
        "ya 'skip' baad me decide karne ke liye)"
    ),
    "onboarding.product.intro": (
        "Ab apne products add karein. Reply 'one by one' ek-ek karke, ya 'bulk' sab ek saath "
        "poore details ke saath (jaise Rice, 300, 400, kg, 100, 5). 'done' skip karne ke liye."
    ),
    "onboarding.product.bulk_format": (
        "Apne products ek line me ek, is format me bhejein:\n"
        "Name, Purchase Price, Selling Price, Unit, Stock, GST%\n"
        "jaise\n"
        "Rice, 300, 400, kg, 100, 5\n"
        "Dal, 320, 450, kg, 50, 12\n"
        "Jo field set nahi karni uske liye 'skip' likhein "
        "(jaise Rice, skip, 400, kg, 100, skip). Ho jaye to 'done' bhejein."
    ),
    "onboarding.product.bulk_format_no_gst": (
        "Apne products ek line me ek, is format me bhejein:\n"
        "Name, Purchase Price, Selling Price, Unit, Stock\n"
        "jaise\n"
        "Rice, 300, 400, kg, 100\n"
        "Dal, 320, 450, kg, 50\n"
        "Jo field set nahi karni uske liye 'skip' likhein "
        "(jaise Rice, skip, 400, kg, 100). Ho jaye to 'done' bhejein."
    ),
    "onboarding.product.first_name": (
        "Apne pehle product ka naam bhejein (jaise Rice), ya 'done' skip karne ke liye."
    ),
    "onboarding.product.mode_invalid": (
        "Kripya reply karein 'one by one' ya 'bulk' — ya 'done' products skip karne ke liye."
    ),
    "onboarding.product.bulk_added": (
        "{count} product add kiye: {names}. Aur bhejein, ya ho jaye to 'done' bhejein."
    ),
    "onboarding.product.quantity_ask": (
        "Abhi aapke paas kitna {name} stock me hai? (jaise 100, ya 'skip')"
    ),
    "onboarding.product.quantity_invalid": "Kripya ek number bhejein, jaise 100 (ya 'skip').",
    "onboarding.product.unit": "Yeh kis unit me hai? (jaise kg, pcs, box, litre, ya 'skip')",
    "onboarding.product.price_ask": "{name} ki selling price kya hai? (jaise 400, ya 'skip')",
    "onboarding.product.price_invalid": "Kripya ek number bhejein, jaise 400 (ya 'skip').",
    "onboarding.product.purchase_ask": (
        "{name} ki purchase price (cost price) kya hai? (jaise 300, ya 'skip')"
    ),
    "onboarding.product.purchase_invalid": "Kripya ek number bhejein, jaise 300 (ya 'skip').",
    "onboarding.product.gst_ask": (
        "{name} ka GST% kya hai? (jaise 5, 12, 18, ya 'skip' baad me decide karne ke liye)"
    ),
    "onboarding.product.gst_invalid": (
        "Kripya 0 se 100 ke beech number bhejein, jaise 18 (ya 'skip' baad me decide karein)."
    ),
    "onboarding.product.added": (
        "Product add kiya: {name} ({stock} stock me). Aur bhejein, ya 'done'."
    ),
    "onboarding.dealers.intro": (
        "Ab apne dealers (customers) add karein. Reply 'one by one' ek-ek karke add karne ke liye, "
        "ya 'bulk' sabko ek saath bhejne ke liye (jaise Ram Traders, 9876543210, 15). "
        "'done' skip karne ke liye."
    ),
    "onboarding.dealer.bulk_format": (
        "Apne dealers ek line me ek, is format me bhejein:\n"
        "Name, Phone, Credit Days\n"
        "jaise\n"
        "Ram Traders, 9876543210, 15\n"
        "Shree Enterprises, 9123456780, 30\n"
        "Jo field set nahi karni uske liye 'skip' likhein "
        "(jaise Ram Traders, skip, 15). Ho jaye to 'done' bhejein."
    ),
    "onboarding.dealer.first_name": (
        "Apne pehle dealer ka naam bhejein (jaise Ram Traders), ya 'done' skip karne ke liye."
    ),
    "onboarding.dealer.mode_invalid": (
        "Kripya reply karein 'one by one' ya 'bulk' — ya 'done' dealers skip karne ke liye."
    ),
    "onboarding.dealer.bulk_added": (
        "{count} dealer add kiye: {names}. Aur bhejein, ya ho jaye to 'done' bhejein."
    ),
    "onboarding.dealer.credit_ask": (
        "{name} ko aap kitne credit din dete hain? (jaise 15, ya 'skip')"
    ),
    "onboarding.dealer.added": "Dealer {name} add kiya. Agle dealer ka naam, ya 'done'.",
    "onboarding.dealer.missing_ask": (
        "Aapke import se humein {count} dealer(s) mile, lekin unka phone number aur/ya credit "
        "days missing hai. Abhi complete karein, ya baad me? (now/later)"
    ),
    "onboarding.dealer.missing_list": (
        "{listing}\n\n'bulk' reply karein sabko ek saath paste karne ke liye, ya 'one by one' "
        "ek-ek karke fill karne ke liye."
    ),
    "onboarding.dealer.missing_bulk_format": (
        "Har dealer ki details fill karne ke liye ek line bhejein:\n"
        "Name, Phone, Credit Days\n"
        "jaise\n"
        "Ram Traders, 9876543210, 15\n"
        "Sirf upar wali list se match hone wale naam hi update honge."
    ),
    "onboarding.dealer.missing_bulk_done": "{count} dealer update kiye: {names}.",
    "onboarding.dealer.missing_bulk_unmatched": (
        "Yeh naam upar ki list se match nahi hue, isliye update nahi hue: {names}."
    ),
    "onboarding.suppliers.intro": (
        "Ab aapke suppliers. Reply 'one by one' ek-ek karke add karne ke liye, "
        "ya 'bulk' sabko ek saath bhejne ke liye (jaise Metro Distributors, 9988776655, 30). "
        "'done' skip karne ke liye."
    ),
    "onboarding.supplier.bulk_format": (
        "Apne suppliers ek line me ek, is format me bhejein:\n"
        "Name, Phone, Credit Days\n"
        "jaise\n"
        "Metro Distributors, 9988776655, 30\n"
        "Suresh Wholesale, 9871234560, 15\n"
        "Jo field set nahi karni uske liye 'skip' likhein "
        "(jaise Metro Distributors, skip, 30). Ho jaye to 'done' bhejein."
    ),
    "onboarding.supplier.first_name": (
        "Apne pehle supplier ka naam bhejein (jaise Metro Distributors), "
        "ya 'done' skip karne ke liye."
    ),
    "onboarding.supplier.mode_invalid": (
        "Kripya reply karein 'one by one' ya 'bulk' — ya 'done' suppliers skip karne ke liye."
    ),
    "onboarding.supplier.bulk_added": (
        "{count} supplier add kiye: {names}. Aur bhejein, ya ho jaye to 'done' bhejein."
    ),
    "onboarding.supplier.credit_ask": (
        "{name} aapko pay karne ke liye kitne din deta hai? (jaise 15/'skip')"
    ),
    "onboarding.supplier.added": "Supplier {name} add kiya. Agle supplier ka naam, ya 'done'.",
    "onboarding.supplier.missing_ask": (
        "Aapke import se humein {count} supplier(s) mile, lekin unka phone number aur/ya "
        "credit days missing hai. Abhi complete karein, ya baad me? (now/later)"
    ),
    "onboarding.supplier.missing_list": (
        "{listing}\n\n'bulk' reply karein sabko ek saath paste karne ke liye, ya 'one by one' "
        "ek-ek karke fill karne ke liye."
    ),
    "onboarding.supplier.missing_bulk_format": (
        "Har supplier ki details fill karne ke liye ek line bhejein:\n"
        "Name, Phone, Credit Days\n"
        "jaise\n"
        "Metro Distributors, 9988776655, 30\n"
        "Sirf upar wali list se match hone wale naam hi update honge."
    ),
    "onboarding.supplier.missing_bulk_done": "{count} supplier update kiye: {names}.",
    "onboarding.supplier.missing_bulk_unmatched": (
        "Yeh naam upar ki list se match nahi hue, isliye update nahi hue: {names}."
    ),
    "onboarding.party.phone_ask": "{name} ka phone number? (ya 'skip')",
    "onboarding.party.phone_invalid": (
        "Woh sahi phone number nahi lagta. Agar Indian nahi hai to country code shamil "
        "karein, jaise +919876543210."
    ),
    "onboarding.party.credit_invalid": "Kripya dino ka number bhejein, jaise 15 (ya 'skip').",
    "onboarding.bulk_error": "Yeh samajh nahi aaya: {error}",
    "onboarding.opening.ask": "Abhi aapke business me kitna cash hai? (jaise 320000)",
    "onboarding.opening.invalid": "Kripya ek amount bhejein, jaise 320000.",
    "onboarding.receivable.ask": "Kya kisi dealer par abhi aapka paisa baaki hai? (yes/no)",
    "onboarding.receivable.which": "Kaun sa dealer aapko dena hai? (naam)",
    "onboarding.receivable.confirm_new": (
        "Mere paas '{name}' naam ka dealer abhi nahi hai — naye dealer ke roop me add karein? "
        "(yes/no)"
    ),
    "onboarding.receivable.amount_ask": "{party} ko aapko kitna dena hai? (jaise 42000)",
    "onboarding.receivable.amount_invalid": "Kripya ek amount bhejein, jaise 42000.",
    "onboarding.receivable.date_ask": (
        "{party} se payment kab expect karte hain? (jaise Friday, 15 days, ya next week)"
    ),
    "onboarding.receivable.recorded": (
        "{amount} {party} se record kiya. Koi aur dealer dena hai? (yes/no)"
    ),
    "onboarding.payable.ask": "Kya koi supplier payment pending hai? (yes/no)",
    "onboarding.payable.which": "Kis supplier ko aap dena hai? (naam)",
    "onboarding.payable.confirm_new": (
        "Mere paas '{name}' naam ka supplier abhi nahi hai — naye supplier ke roop me add karein? "
        "(yes/no)"
    ),
    "onboarding.payable.amount_ask": "Aapko {party} ko kitna dena hai? (jaise 82000)",
    "onboarding.payable.amount_invalid": "Kripya ek amount bhejein, jaise 82000.",
    "onboarding.payable.date_ask": (
        "{party} ko payment kab due hai? (jaise Friday, 15 days, ya next week)"
    ),
    "onboarding.payable.recorded": (
        "{amount} {party} ko record kiya. Koi aur supplier pending? (yes/no)"
    ),
    "onboarding.yes_no_invalid": "Kripya yes ya no reply karein.",
    "onboarding.date_invalid": (
        "Maaf karein, woh date samajh nahi aayi. Try karein jaise Friday, 15 days, ya next week."
    ),
    "onboarding.briefing.ask": (
        "Aakhri step — main aapki morning briefing kab bhejun? Reply 7, 8, ya 9."
    ),
    "onboarding.briefing.invalid": "Kripya ek ghanta reply karein, jaise 7, 8, ya 9.",
    "onboarding.briefing.range": (
        "Kripya subah 5 se 11 ke beech ka ghanta chunein (jaise 7, 8, ya 9)."
    ),
    # Resume: progress checklist ("progress"/"status") and restart ("restart")
    "onboarding.section.business_type": "Business type",
    "onboarding.section.products": "Products",
    "onboarding.section.dealers": "Dealers",
    "onboarding.section.suppliers": "Suppliers",
    "onboarding.section.opening_balance": "Opening balance",
    "onboarding.section.receivables": "Dealer baaki",
    "onboarding.section.payables": "Supplier baaki",
    "onboarding.section.briefing_hour": "Briefing time",
    "onboarding.import_confirm.title": "📋 Aapke import se kuch data mila:",
    "onboarding.import_confirm.line_products": "✅ {count} product(s)",
    "onboarding.import_confirm.line_dealers": "✅ {count} dealer(s)",
    "onboarding.import_confirm.line_suppliers": "✅ {count} supplier(s)",
    "onboarding.import_confirm.line_receivables": (
        "✅ {count} outstanding receivable invoice(s) ({amount})"
    ),
    "onboarding.import_confirm.line_payables": (
        "✅ {count} outstanding payable invoice(s) ({amount})"
    ),
    "onboarding.import_confirm.ask": "Kya yeh sahi hai? (yes/no)",
    "onboarding.import_confirm.no_ack": (
        "Koi baat nahi — aap ise kabhi bhi theek kar sakte hain: 'edit dealer <name>', "
        "'edit supplier <name>', 'add dealer', 'add supplier', ya 'stock take' se "
        "product quantity badlein. Aapka baaki setup jaari hai."
    ),
    "onboarding.status.title": "📋 Setup progress — {percent}% pura ho gaya.",
    "onboarding.status.section_done": "✅ {name}",
    "onboarding.status.section_current": "▶️ {name} (aap yahan hain)",
    "onboarding.status.section_pending": "⬜ {name}",
    "onboarding.status.footer_generic": "Continue karne ke liye apna agla jawab reply karein.",
    "onboarding.status.restart_hint": "Setup phir se shuru karne ke liye 'restart' bhejein.",
    "onboarding.restart.confirm": (
        "⚠️ Isse ab tak bhari gayi saari jaankari (products, dealers, suppliers, opening "
        "balance) mit jayegi aur setup shuruaat se phir hoga. Pakka karna chahte hain? (yes/no)"
    ),
    "onboarding.restart.cancelled": (
        "Theek hai — aapka setup jaari hai. Upar wale aakhri sawaal ka jawab bhejein."
    ),
    "onboarding.restart.done": (
        "🔄 Sab kuch mit gaya. Chaliye phir se shuruaat se aapka business set up karte hain.\n\n"
        "Pehla sawaal: aap kis tarah ka business chalate hain? (jaise FMCG Distributor, Pharma "
        "Distributor)"
    ),
    # ── Interactive menu ───────────────────────────────────────────────────
    "menu.fallback": "Neeche se ek option tap karein, ya poori list ke liye /help bhejein.",
    "menu.msg.reports.body": "Reports & Overview — ek chunein:",
    "menu.msg.reports.button": "Report chunein",
    "menu.msg.inventory.body": "Inventory, Transactions & Products — ek chunein:",
    "menu.msg.inventory.button": "Ek option chunein",
    "menu.msg.orders.body": "Orders, Payments & aapka Data — ek chunein:",
    "menu.msg.orders.button": "Ek option chunein",
    "menu.msg.statements.body": "Reports & Statements — ek chunein:",
    "menu.msg.statements.button": "Statement chunein",
    "menu.msg.corrections.body": "Corrections — pehle se record kiya kuch undo ya edit karein:",
    "menu.msg.corrections.button": "Corrections",
    "menu.section.cash_overview": "Cash & Overview",
    "menu.section.money_flow": "Paise ka Flow",
    "menu.section.dealers_suppliers": "Dealers & Suppliers",
    "menu.section.inventory_transactions": "Inventory & Transactions",
    "menu.section.manage_products": "Products Manage karein",
    "menu.section.orders_payments": "Orders & Payments",
    "menu.section.manage_parties": "Party Manage Karein",
    "menu.section.your_data": "Aapka Data",
    "menu.section.full_lists": "Poori Lists",
    "menu.section.reports_statements": "Reports & Statements",
    "menu.section.corrections": "Corrections",
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
    "menu.row.add_dealer.title": "Dealer Add Karein",
    "menu.row.add_dealer.desc": "Naya dealer add karein",
    "menu.row.add_supplier.title": "Supplier Add Karein",
    "menu.row.add_supplier.desc": "Naya supplier add karein",
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
    "menu.row.gst_report.title": "GST Report",
    "menu.row.gst_report.desc": "Sales aur purchase register, dono ke liye",
    "menu.row.sales_register.title": "Sales Register",
    "menu.row.sales_register.desc": "GST sales register + rate-wise summary",
    "menu.row.purchase_register.title": "Purchase Register",
    "menu.row.purchase_register.desc": "GST purchase register + rate-wise summary",
    "menu.row.payment_register.title": "Payment Register",
    "menu.row.payment_register.desc": "Is mahine ki receipts & payments",
    "menu.row.day_book.title": "Day Book",
    "menu.row.day_book.desc": "Is mahine ke sabhi invoice aur payment",
    "menu.row.outstanding_report.title": "Outstanding Report",
    "menu.row.outstanding_report.desc": "0-30/31-60/61-90/90+ din ke buckets",
    "menu.row.trend_report.title": "Business Trends",
    "menu.row.trend_report.desc": "Hafta & mahina wise, dealers, products",
    "menu.row.delivery_status.title": "Delivery Status",
    "menu.row.delivery_status.desc": "Invoices aur broadcasts ka delivery/read status",
    "menu.row.undo_payment.title": "Undo Payment",
    "menu.row.undo_payment.desc": "Abhi record kiya payment void karein",
    "menu.row.undo_order.title": "Undo Order",
    "menu.row.undo_order.desc": "Abhi banaya order void karein",
    "menu.row.edit_invoice.title": "Edit Invoice",
    "menu.row.edit_invoice.desc": "Invoice ka amount, date, ya party sudharein",
    "menu.row.edit_payment.title": "Edit Payment",
    "menu.row.edit_payment.desc": "Payment ka amount ya date sudharein",
    "menu.row.edit_dealer.title": "Edit Dealer",
    "menu.row.edit_dealer.desc": "Dealer ka phone, limit, terms, GSTIN badlein",
    "menu.row.edit_supplier.title": "Edit Supplier",
    "menu.row.edit_supplier.desc": "Supplier ka phone, limit, terms, GSTIN badlein",
    "menu.row.stock_take.title": "Stock Take",
    "menu.row.stock_take.desc": "Kai products ka stock ek saath badlein",
    # ── Workflows (shared) ─────────────────────────────────────────────────
    "workflow.cancelled": "OK, cancel kar diya.",
    "workflow.yes_no": "Kripya yes ya no reply karein.",
    "workflow.error_restart": (
        "Kuch gadbad ho gayi. Kripya dobara '{trigger}' bolkar shuru karein."
    ),
    "workflow.kind_dealer": "dealer",
    "workflow.kind_supplier": "supplier",
    # ── Record payment ─────────────────────────────────────────────────────
    "payment.start": "Kisne aapko pay kiya, ya aapne kisko pay kiya? (party ka naam)",
    "payment.need_party": "Kripya party ka naam batayein.",
    "payment.amount_receivable": "Unhone aapko kitna pay kiya? (jaise 25000)",
    "payment.amount_payable": "Aapne unhe kitna pay kiya? (jaise 25000)",
    "payment.disambiguation": (
        "'{name}' dealer aur supplier dono se match karta hai. "
        "Reply 1 agar wo dealer hain (unhone aapko pay kiya), "
        "ya 2 agar supplier hain (aapne unhe pay kiya)."
    ),
    "payment.dealer_or_supplier_invalid": (
        "Kripya dealer ke liye 1 ya supplier ke liye 2 reply karein."
    ),
    "payment.invoice_selection_invalid": (
        "Kripya 1 se {count} ke beech number reply karein, ya 'all'."
    ),
    "payment.open_invoices": (
        "{party} ke {count} open invoices hain:\n{listing}\n"
        "Ek number reply karein, ya 'all' sab par apply karne ke liye (purane pehle)."
    ),
    "payment.open_invoice_line": (
        "{index}. {number} — {total} total, {outstanding} baaki, due {due}"
    ),
    "payment.new_party_type": (
        "Mere paas '{name}' nahi hai. Wo dealer (customer) hain ya supplier "
        "(jinse aap khareedte hain)? Reply 1 Dealer ya 2 Supplier."
    ),
    "payment.new_party_type_invalid": "Kripya 1 Dealer ya 2 Supplier reply karein.",
    "payment.add_new_party": "'{name}' ko naya {kind} add karein? yes/no",
    "payment.no_open_invoice": (
        "Main sirf kisi existing invoice ke against payment record kar sakta hoon, aur {party} "
        "ka {kind} ke roop me koi open invoice nahi hai. Pehle unke liye invoice banayein, phir "
        "'record payment' dobara bolein."
    ),
    "payment.got_it_no_invoice": "Theek hai. {message}",
    "payment.amount_invalid": "Kripya ek amount bhejein, jaise 25000.",
    "payment.amount_positive": "Kripya zero se zyada amount bhejein.",
    "payment.date_ask": (
        "Yeh kab pay hua? Reply 'today', 'yesterday', '3 days ago', ya skip aaj ke liye."
    ),
    "payment.date_invalid": (
        "Maaf karein, woh date samajh nahi aayi. Try 'today', 'yesterday', '3 days ago'."
    ),
    "payment.verb_from": "se",
    "payment.verb_to": "ko",
    "payment.target_invoice": " invoice {number} ke against",
    "payment.preview": (
        "Confirm: {amount} {party}{target} {verb} {date} ko.{warning}\n"
        "Reply YES record karne ke liye, NO cancel ke liye."
    ),
    "payment.duplicate_warning": (
        "⚠️ Yeh pehle se record kiye gaye payment jaisa lagta hai: {party}, {amount} {date} "
        "ko. Agar yeh ek alag, jaanbujhkar kiya gaya payment hai, to jaari rakhne ke liye "
        "YES bhejein."
    ),
    # ── Create order ───────────────────────────────────────────────────────
    "order.start": "Yeh order kiske liye hai? (dealer ka naam)",
    "order.need_dealer": "Kripya dealer ka naam batayein.",
    "order.dealer_found": "{dealer} ke liye order. Kaun sa product?",
    "order.add_new_dealer": (
        "Mere paas '{dealer}' dealer ke roop me nahi hai. Unhe naya dealer add karein? yes/no"
    ),
    "order.new_dealer_added": (
        "Theek hai, {dealer} ko naya dealer add kiya jayega. Kaun sa product?"
    ),
    "order.need_one_product": "Pehle kam se kam ek product add karein, ya 'cancel'.",
    "order.need_product": "Kripya product ka naam batayein, ya 'done' agar ho gaya.",
    "order.quantity_ask": "{product} ke kitne {unit}?",
    "order.price_ask": "{product} ki selling price kya hai?",
    "order.add_new_product": "Mere paas '{product}' catalogue me nahi hai. Add karein? yes/no",
    "order.new_product_declined": "Theek hai. Kaun sa product? (ya 'done')",
    "order.price_invalid": "Kripya ek price bhejein, jaise 55.",
    "order.price_positive": "Kripya zero se zyada price bhejein.",
    "order.quantity_invalid": "Kripya ek quantity bhejein, jaise 10.",
    "order.quantity_positive": "Kripya zero se zyada quantity bhejein.",
    "order.item_added": (
        "{quantity} x {product} add kiya. Aur product add karein, ya 'done' reply karein."
    ),
    "order.line": "- {quantity} x {product} @ {price} = {total}",
    "order.subtotal": "Subtotal: {amount}",
    "order.gst": "GST{rate_label}: {amount}",
    "order.total": "Total: {amount}",
    "order.payment_made": "Payment Made: {amount}",
    "order.balance_due": "Balance Due: {amount}",
    "order.advance_amount_ask": "Dealer ne advance mein kitna diya? (jaise 5000)",
    "order.advance_amount_invalid": "Kripya zero se zyada number bhejein, jaise 5000.",
    "order.advance_exceeds_total": (
        "Yeh order ke {total} total se zyada hai. Kam amount bhejein, ya bina advance ke "
        "order banane ke liye YES reply karein."
    ),
    "order.preview_header": "{dealer} ke liye order confirm karein:",
    "order.preview_footer": (
        "Reply YES banane ke liye, NO cancel ke liye, ya ADVANCE agar dealer ne pehle se "
        "kuch pay kar diya hai."
    ),
    "order.duplicate_warning": (
        "⚠️ Yeh is dealer ke existing invoice ({number}) jaisa lagta hai — same date aur "
        "total. Agar yeh ek alag, jaanbujhkar kiya gaya order hai, to jaari rakhne ke liye "
        "YES bhejein."
    ),
    "order.credit_limit_warning": (
        "⚠️ Yeh order {dealer} ka outstanding {prospective} tak le jaayega, jo unki "
        "{limit} ki credit limit se zyada hai."
    ),
    # ── Edit invoice / edit payment (safe cases only) ───────────────────────
    "edit.invoice_number_ask": "Kaun sa invoice? Uska invoice number bhejein, ya 'cancel'.",
    "edit.invoice_not_found": (
        "Mujhe '{number}' naam ka invoice nahi mila. Jaanch kar dobara bhejein, ya 'cancel'."
    ),
    "edit.invoice_has_payment": (
        "Invoice {number} par pehle se payment record hai — pehle use void karein "
        "aur dobara banayein."
    ),
    "edit.field_ask_invoice": (
        "Kya edit karna hai — amount, date, ya party? Reply karein 'amount', 'date', ya 'party'."
    ),
    "edit.field_invalid_invoice": (
        "Kripya reply karein 'amount', 'date', ya 'party' — ya 'cancel'."
    ),
    "edit.amount_ask": "Abhi ka amount {current} hai. Naya amount kya ho? (jaise 1200)",
    "edit.date_ask": "Abhi ki date {current} hai. Nayi date kya ho? (jaise 2026-01-15)",
    "edit.invoice_party_ask_dealer": "Abhi ka dealer {current} hai. Naye dealer ka naam bhejein.",
    "edit.invoice_party_ask_supplier": (
        "Abhi ka supplier {current} hai. Naye supplier ka naam bhejein."
    ),
    "edit.amount_invalid": "Kripya shunya se bada ek number bhejein, jaise 1200.",
    "edit.date_invalid": "Kripya 2026-01-15 jaisi date bhejein.",
    "edit.party_not_found": (
        "Mujhe '{name}' nahi mila. Spelling jaanch kar dobara bhejein, ya 'cancel'."
    ),
    "edit.value_preview": "{target} ka {field} badal kar {new} karein?",
    "edit.target_invoice": "invoice {number}",
    "edit.target_payment": "invoice {number} ka payment",
    "edit.reason_ask": "{preview}\nKyun? Chota sa reason bhejein, ya 'skip'.",
    "edit.confirm_prompt": "{preview}\nConfirm karne ke liye YES bhejein, ya NO cancel ke liye.",
    "edit.party_name_ask": (
        "Kis dealer ya supplier ka payment edit karna hai? Unka naam bhejein, ya 'cancel'."
    ),
    "edit.no_payments_for_party": "{name} ke liye koi payment nahi mila.",
    "edit.payment_pick_ask": (
        "{name} ke liye {count} haal ke payments mile:\n{listing}\nNumber bhejein, ya 'cancel'."
    ),
    "edit.payment_pick_invalid": "Kripya 1 se {count} ke beech ek number bhejein, ya 'cancel'.",
    "edit.payment_gone": (
        "Woh payment ab available nahi hai. 'edit payment' kahkar dobara shuru karein."
    ),
    "edit.field_ask_payment": (
        "Kya edit karna hai — amount ya date? Reply karein 'amount' ya 'date'."
    ),
    "edit.field_invalid_payment": "Kripya reply karein 'amount' ya 'date' — ya 'cancel'.",
    # ── Update GST ─────────────────────────────────────────────────────────
    "gst.scope_prompt": (
        "Sabhi products (company default) ka GST update karein, ya ek product ka? "
        "Reply 'all' ya product ka naam."
    ),
    "gst.rate_ask_all": "{target} ke liye naya default GST rate kya hai? (0-100, ya 'cancel')",
    "gst.rate_ask_product": (
        "{target} ke liye naya GST rate kya hai? (0-100, 'clear' override hatane aur company "
        "default use karne ke liye, ya 'cancel')"
    ),
    "gst.not_found": (
        "'{name}' naam ka product nahi mila. Reply 'all', doosra product naam, ya 'cancel'."
    ),
    "gst.rate_invalid": "Kripya 0 se 100 ke beech number bhejein, jaise 18.",
    "gst.all_products": "sabhi products",
    "gst.no_override": "koi override nahi (company default use karein)",
    "gst.rate_pct": "{rate}%",
    "gst.preview": "{target} ka GST {rate_text} set karein. Reply YES confirm, NO cancel.",
    # ── Product: mode / disambiguation / delete / update ───────────────────
    "product.mode_prompt": (
        "Chaliye products add karein. Reply 'one by one' ek-ek karke, ya 'bulk' sab ek saath "
        "poore details ke saath (jaise Rice, 300, 400, kg, 100, 5). Kabhi bhi 'done' rokne ke liye."
    ),
    "product.no_products_added": "OK, koi product add nahi kiya.",
    "product.all_done": "Products add karna ho gaya.",
    "product.name_or_done": "Product ka naam bhejein (jaise Rice), ya 'done' rokne ke liye.",
    "product.mode_invalid": "Kripya reply karein 'one by one' ya 'bulk' — ya 'done' rokne ke liye.",
    "product.not_found_retry": (
        "'{name}' naam ka product nahi mila. Spelling check karke dobara try karein, ya 'cancel'."
    ),
    "product.disambiguation": (
        "'{name}' naam ke {count} products mile:\n{listing}\n"
        "{action} karne ke liye number reply karein, ya 'cancel'."
    ),
    "product.disambiguation_invalid": (
        "Kripya 1 se {count} ke beech number reply karein, ya 'cancel'."
    ),
    "product.candidate_line": "{index}. {description}",
    "product.candidate_desc": "{name} ({details})",
    "product.candidate_stock": "{stock} stock me",
    "product.gone": (
        "Woh product ab available nahi hai. Kripya dobara '{trigger}' bolkar shuru karein."
    ),
    "product.delete_name_prompt": "Kaun sa product delete karna hai? Naam bhejein, ya 'cancel'.",
    "product.delete_confirm": (
        "{description} delete karein? Yeh undo nahi hoga. Reply YES delete, NO cancel."
    ),
    "product.delete_no": "OK, delete nahi kiya.",
    "product.delete_confirm_invalid": (
        "Kripya YES delete ke liye, ya NO cancel ke liye reply karein."
    ),
    "product.delete_already_gone": "{name} pehle hi hata diya gaya tha.",
    "product.deleted": "{name} delete kiya.",
    "product.field_prompt": (
        "Kya update karna hai — price, purchase price, ya stock? "
        "Reply 'price', 'purchase price', ya 'stock'."
    ),
    "product.action_update": "update",
    "product.action_delete": "delete",
    "product.label_price": "price",
    "product.label_purchase": "purchase price",
    "product.label_stock": "stock",
    "product.update_name_prompt": (
        "Kis product ki {label} update karni hai? Naam bhejein, ya 'cancel'."
    ),
    "product.current_price": (
        "{name} ki abhi price {current} hai. Nayi price kya honi chahiye? (jaise 450)"
    ),
    "product.current_purchase": (
        "{name} ki abhi purchase price {current} hai. "
        "Nayi purchase price kya honi chahiye? (jaise 300)"
    ),
    "product.current_stock": (
        "{name} ka abhi stock {current} hai. Naya stock kya hona chahiye? (jaise 100)"
    ),
    "product.value_invalid": "Kripya ek number bhejein, jaise 450.",
    "product.value_nonneg": "Kripya zero ya usse zyada number bhejein.",
    "product.value_positive": "Kripya zero se zyada number bhejein.",
    "product.gone_value": "Woh product ab available nahi hai.",
    "product.not_set": "set nahi",
    "product.updated_price": "{name} ki price {new} ki (pehle {old} thi).",
    "product.updated_purchase": "{name} ki purchase price {new} ki (pehle {old} thi).",
    "product.updated_stock": "{name} ka stock {new} kiya (pehle {old} tha).",
    # ── Stock take (bulk stock recount/adjustment) ──────────────────────────
    "stock_take.start_prompt": (
        "Chaliye stock take karte hain. Har product ke liye, uska naam bhejein, phir naya "
        "count (jaise 40) ya adjustment (jaise +15 mila, -3 kharab hua). Khatam hone par "
        "'done' bhejein, ya kabhi bhi 'cancel'."
    ),
    "stock_take.line_prompt": "Ek product ka naam bhejein, ya khatam karne ke liye 'done'.",
    "stock_take.value_ask": (
        "{name} — naya count bhejein (jaise 40) ya adjustment (jaise +15, -3)."
    ),
    "stock_take.value_invalid": "Kripya ek number bhejein, jaise 40, +15, ya -3.",
    "stock_take.line_added": "{name}: {old} → {new}. Agla product bhejein, ya 'done'.",
    "stock_take.nothing_to_apply": "OK, koi badlav nahi hua.",
    "stock_take.reason_ask": "Kyun? Chota sa reason bhejein, ya 'skip'.",
    "stock_take.confirm_prompt": (
        "{summary}\nApply karne ke liye YES bhejein, ya NO cancel ke liye."
    ),
    "stock_take.failed": "Stock take apply nahi ho paya: {error}. Kripya dobara shuru karein.",
    "stock_take.result_line": "- {name}: {new}",
    "stock_take.success": "✅ {count} product(s) ka stock update hua:\n{lines}{warning}",
    # ── Marketing broadcast (guided workflow) ───────────────────────────────
    "broadcast.segment_ask": (
        "Yeh broadcast kise milna chahiye?\n1. Sabhi dealers\n2. Overdue balance wale dealers\n"
        "3. Naam se specific dealers chunein\nReply karein 1, 2, ya 3 — ya 'cancel'."
    ),
    "broadcast.segment_invalid": "Kripya reply karein 1, 2, ya 3 — ya 'cancel'.",
    "broadcast.segment.all": "sabhi dealers",
    "broadcast.segment.overdue": "overdue balance wale dealers",
    "broadcast.segment.specific": "aapke chune hue dealers",
    "broadcast.dealer_names_ask": (
        "Dealer ke naam bhejein, ek line me ek (ya comma se alag), ya 'cancel'."
    ),
    "broadcast.dealer_names_none_matched": (
        "In me se koi bhi naam file me kisi dealer se match nahi hua: {names}. Kripya dobara "
        "koshish karein, ya 'cancel'."
    ),
    "broadcast.dealer_names_unmatched": (
        "\n(Match nahi hue: {names} — spelling jaanch kar alag se edit karein agar zaroorat ho.)"
    ),
    "broadcast.message_ask": (
        "Yeh opt-in kiye {count} dealer(s) tak pahunchega. Kya message bhejna hai?"
    ),
    "broadcast.message_empty": "Kripya broadcast karne ke liye ek message bhejein, ya 'cancel'.",
    "broadcast.no_opted_in": (
        "{segment} me se kisi ne bhi abhi tak marketing broadcasts opt in nahi kiya. Unhe opt "
        "in karne ko kahein, ya 'edit dealer' / 'opt in all dealers' use karein."
    ),
    "broadcast.confirm_prompt": (
        "{count} dealer(s) ko yeh bhejein?{capped_note}\n\n\"{message}\"\n\n"
        "Reply karein YES bhejne ke liye, NO cancel karne ke liye."
    ),
    "broadcast.confirm_capped": " (har broadcast me max {cap} tak)",
    "broadcast.opt_in_all_none": "Har dealer pehle se hi opt in hai.",
    "broadcast.opt_in_all_confirm": (
        "{count} dealer(s) ko marketing broadcasts me opt in karein? Reply karein YES confirm "
        "karne ke liye, NO cancel karne ke liye."
    ),
    "party.dealer.mode_prompt": (
        "Apne dealers add karein. Reply 'one by one' ek-ek karke add karne ke liye, "
        "ya 'bulk' sabko ek saath bhejne ke liye (jaise Ram Traders, 9876543210, 15). "
        "'done' kabhi bhi rukne ke liye."
    ),
    "party.dealer.no_added": "OK, koi dealer add nahi kiya.",
    "party.dealer.all_done": "Sabhi dealers add ho gaye.",
    "party.dealer.name_or_done": (
        "Dealer ka naam bhejein (jaise Ram Traders), ya rukne ke liye 'done'."
    ),
    "party.dealer.mode_invalid": (
        "Kripya reply karein 'one by one' ya 'bulk' — ya rukne ke liye 'done'."
    ),
    "party.supplier.mode_prompt": (
        "Apne suppliers add karein. Reply 'one by one' ek-ek karke add karne ke liye, "
        "ya 'bulk' sabko ek saath bhejne ke liye (jaise Metro Distributors, 9988776655, 30). "
        "'done' kabhi bhi rukne ke liye."
    ),
    "party.supplier.no_added": "OK, koi supplier add nahi kiya.",
    "party.supplier.all_done": "Sabhi suppliers add ho gaye.",
    "party.supplier.name_or_done": (
        "Supplier ka naam bhejein (jaise Metro Distributors), ya rukne ke liye 'done'."
    ),
    "party.supplier.mode_invalid": (
        "Kripya reply karein 'one by one' ya 'bulk' — ya rukne ke liye 'done'."
    ),
    # ── Edit dealer / edit supplier (phone, credit limit, terms, GSTIN) ─────
    "party.edit.field_prompt_dealer": (
        "Kya edit karna hai — phone, credit limit, payment terms, GSTIN, ya marketing opt-in? "
        "Reply karein 'phone', 'credit limit', 'payment terms', 'gstin', ya 'marketing'."
    ),
    "party.edit.field_invalid_dealer": (
        "Kripya reply karein 'phone', 'credit limit', 'payment terms', 'gstin', ya 'marketing' "
        "— ya 'cancel'."
    ),
    "party.edit.field_prompt_supplier": (
        "Kya edit karna hai — phone, credit limit, payment terms, ya GSTIN? "
        "Reply karein 'phone', 'credit limit', 'payment terms', ya 'gstin'."
    ),
    "party.edit.field_invalid_supplier": (
        "Kripya reply karein 'phone', 'credit limit', 'payment terms', ya 'gstin' — ya 'cancel'."
    ),
    "party.edit.name_ask_dealer": "Kaun sa dealer? Unka naam bhejein, ya 'cancel'.",
    "party.edit.name_ask_supplier": "Kaun sa supplier? Unka naam bhejein, ya 'cancel'.",
    "party.edit.not_found": (
        "Mujhe '{name}' nahi mila. Spelling jaanch kar dobara bhejein, ya 'cancel'."
    ),
    "party.edit.disambiguation": (
        "'{name}' naam ke {count} matches mile:\n{listing}\n"
        "Edit karne ke liye number bhejein, ya 'cancel'."
    ),
    "party.edit.disambiguation_invalid": (
        "Kripya 1 se {count} ke beech ek number bhejein, ya 'cancel'."
    ),
    "party.edit.gone": "Woh record ab available nahi hai. '{trigger}' kahkar dobara shuru karein.",
    "party.edit.gone_value": "Woh record ab available nahi hai.",
    "party.edit.phone_ask": "{name} ka abhi ka phone {current} hai. Naya phone kya ho?",
    "party.edit.credit_limit_ask": (
        "{name} ki abhi ki credit limit {current} hai. Nayi credit limit kya ho? (jaise 50000)"
    ),
    "party.edit.payment_terms_ask": (
        "{name} ke abhi ke payment terms {current} days hain. Naye terms din mein kya hon? "
        "(jaise 30)"
    ),
    "party.edit.gstin_ask": "{name} ka abhi ka GSTIN {current} hai. Naya GSTIN kya ho?",
    "party.edit.marketing_ask": (
        "{name} ka marketing opt-in abhi {current} hai. Reply karein 'yes'/'opt in' ya "
        "'no'/'opt out'."
    ),
    "party.edit.marketing_invalid": (
        "Kripya reply karein 'yes'/'opt in' ya 'no'/'opt out', ya 'cancel'."
    ),
    "party.edit.opted_in": "opted in",
    "party.edit.opted_out": "opted out",
    "party.edit.days_invalid": "Kripya dinon ki ek puri sankhya bhejein, jaise 30.",
    "party.edit.phone_invalid": (
        "Woh sahi phone number nahi lagta. Agar Indian nahi hai to country code shamil "
        "karein, jaise +919876543210."
    ),
    "party.edit.gstin_invalid": (
        "Woh sahi GSTIN nahi lagta. Kripya jaanch kar dobara bhejein, ya 'cancel'."
    ),
    "party.edit.value_preview": "{name} ka {field} badal kar {new} karein?",
    "party.edit.success": "✅ {name} ka {field} {new} ho gaya (pehle {old} tha).",
    # ── Void payment / void order ───────────────────────────────────────────
    "void.payment_none": "Undo karne ke liye koi WhatsApp payment nahi mila.",
    "void.payment_preview": (
        "Invoice {invoice_number} ke liye {party} ka {amount} payment void karein?"
    ),
    "void.order_none": "Undo karne ke liye koi WhatsApp order nahi mila.",
    "void.order_has_payment": (
        "Order {invoice_number} par pehle se payment record hai — pehle payment void "
        "karein, phir dobara koshish karein."
    ),
    "void.order_preview": "{dealer} ka order {invoice_number} void karein (total {total})?",
    "void.reason_ask": "{preview}\nKyun? Chota sa reason bhejein, ya 'skip'.",
    "void.confirm_prompt": "{preview}\nVoid karne ke liye YES bhejein, ya cancel ke liye NO.",
    # ── Pending-operation results ──────────────────────────────────────────
    "pending.reply_yes_no": "Reply YES confirm karne ke liye ya NO cancel ke liye.",
    "pending.payment_failed": (
        "Woh payment record nahi ho paya: {error}. Kripya dobara shuru karein."
    ),
    "pending.payment_success": (
        "✅ {amount} {party} {verb} record kiya.\n"
        "Invoices update hue: {invoices}\n"
        "Baaki outstanding: {outstanding}"
    ),
    "pending.order_failed": "Woh order nahi ban paya: {error}. Kripya dobara shuru karein.",
    "pending.order_line": "- {quantity} x {product} = {total}",
    "pending.order_stock_warning": "\n⚠️ Ab stock negative hai: {products}",
    "pending.order_pdf_sent": "\nPDF {dealer} ko bheja.",
    "pending.order_pdf_not_sent": (
        "\n(PDF {dealer} ko nahi bheja — phone nahi hai ya WhatsApp delivery abhi set nahi hai.)"
    ),
    "pending.order_pdf_sent_to_founder": (
        "\n({dealer} tak seedha nahi pahunch paya — PDF upar bhej diya hai, aap khud "
        "forward kar dein.)"
    ),
    "pending.order_success": (
        "✅ Order {number} {dealer} ke liye bana.\n{lines}\n"
        "Subtotal: {subtotal}\nGST: {gst}\nTotal: {total}\n"
        "Payment Made: {payment_made}\nBalance Due: {balance_due}{warning}{pdf_note}"
    ),
    "pending.gst_failed": "GST update nahi ho paya: {error}. Kripya dobara shuru karein.",
    "pending.gst_success": "✅ {target} ka GST {rate} set kiya.",
    "pending.gst_rate_default": "company default",
    "pending.void_payment_failed": (
        "Woh payment void nahi ho paya: {error}. Kripya dobara shuru karein."
    ),
    "pending.void_payment_success": (
        "✅ Invoice {invoice_number} ke liye {party} ka {amount} payment void ho gaya."
    ),
    "pending.void_order_failed": (
        "Woh order void nahi ho paya: {error}. Kripya dobara shuru karein."
    ),
    "pending.void_order_success": (
        "✅ {dealer} ka order {invoice_number} void ho gaya (total {total})."
    ),
    "pending.edit_invoice_failed": (
        "Woh invoice edit nahi ho paya: {error}. Kripya dobara shuru karein."
    ),
    "pending.edit_invoice_success": (
        "✅ Invoice {number} ka {field} {new} ho gaya (pehle {old} tha)."
    ),
    "pending.edit_payment_failed": (
        "Woh payment edit nahi ho paya: {error}. Kripya dobara shuru karein."
    ),
    "pending.edit_payment_success": (
        "✅ Invoice {number} ke payment ka {field} {new} ho gaya (pehle {old} tha)."
    ),
    "pending.broadcast_failed": (
        "Woh broadcast bhej nahi paye: {error}. Kripya dobara shuru karein."
    ),
    "pending.broadcast_success": (
        "✅ Broadcast {total} me se {sent} dealer(s) ko bhej diya ({failed} fail hue)."
    ),
    "pending.opt_in_all_failed": (
        "Dealers opt in nahi ho paye: {error}. Kripya dobara shuru karein."
    ),
    "pending.opt_in_all_success": "✅ {count} dealer(s) marketing broadcasts me opt in ho gaye.",
    "pending.unknown": "Us confirmation me kuch gadbad ho gayi. Kripya dobara shuru karein.",
    # ── Menu prompt / follow-up / notifications / evening ──────────────────
    "menu.prompt": "Reply karein 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk",
    "followup.message": (
        "📋 Payment Follow-Up\n\n"
        "{number} — {dealer} — {amount}\n"
        "Due date: aaj\n\n"
        "Payment mil gaya?\n"
        "1. Haan — poora amount\n"
        "2. Partial payment\n"
        "3. Abhi tak nahi"
    ),
    "followup.recorded_full": (
        "{amount} payment {dealer} se record kiya.\n"
        "{number} band ho gaya.\n"
        "Baaki: ₹0.\n"
        "Cash aur kal ki briefing update ho gayi."
    ),
    "followup.recorded_partial": (
        "{amount} partial payment record kiya.\n"
        "{number} — {remaining} abhi baaki.\n"
        "Cash aur kal ki briefing update ho gayi."
    ),
    "followup.invoice_gone": "Woh invoice ab available nahi. {menu_prompt}",
    "followup.ask_partial": "Kitna mila?",
    "followup.ask_expected_date": (
        "{dealer} se payment kab expect karte hain?\nExample: Friday, 3 days, next week"
    ),
    "followup.confirm_invalid": "Samajh nahi aaya. Reply 1, 2, ya 3.",
    "followup.amount_invalid": (
        "Woh amount samajh nahi aaya. Kripya ek number bhejein, jaise 25000."
    ),
    "followup.date_invalid": "Woh date samajh nahi aayi.\nExample: Friday, 3 days, next week",
    "followup.rescheduled": (
        "Note kiya. {number} follow-up {when} ke liye schedule kiya.\n"
        "{dealer} kal ki briefing me flag hai."
    ),
    "followup.error": "Us follow-up me kuch gadbad ho gayi. {menu_prompt}",
    "notify.supplier_reminder": (
        "⏰ Payment Reminder\n\n"
        "{supplier} ka {amount} payment {when} due hai.\n"
        "{cash_line}\n"
        "Koi action ki zaroorat nahi jab tak cash position na badle."
    ),
    "notify.when_today": "aaj",
    "notify.when_tomorrow": "kal",
    "notify.cash_line": "Abhi available cash: {amount} — {sufficiency}",
    "notify.cash_sufficient": "kaafi hai.",
    "notify.cash_insufficient": "kam pad sakta hai.",
    # ── Supplier-reminder payment confirmation ──────────────────────────────
    "reminder_confirm.ask_paid": (
        "Kya aapne {supplier} ko {amount} pay kar diya hai?\n"
        "Reply 1 agar haan, 2 agar abhi tak nahi kiya."
    ),
    "reminder_confirm.invalid_choice": (
        "Kripya reply 1 karein agar pay kar diya hai, ya 2 agar abhi tak nahi."
    ),
    "reminder_confirm.amount_ask": (
        "Amount confirm karein jo pay kiya: {amount}. Badalne ke liye alag number reply "
        "karein, ya 'ok' confirm karne ke liye."
    ),
    "reminder_confirm.amount_invalid": "Kripya ek amount bhejein, jaise 25000.",
    "reminder_confirm.amount_positive": "Kripya zero se zyada amount bhejein.",
    "reminder_confirm.reschedule_ask": (
        "Theek hai — is reminder ko reschedule karne ke liye nayi date reply karein (jaise "
        "'tomorrow', 'next week', '3 days'), ya 'skip' agar abhi bhi due rakhna hai — main "
        "phir se yaad dilaunga."
    ),
    "reminder_confirm.reschedule_invalid": (
        "Woh date samajh nahi aayi. Try 'tomorrow', 'next week', '3 days' — ya 'skip'."
    ),
    "reminder_confirm.rescheduled": (
        "Theek hai — {supplier} ka payment ab {date} ko due hai. Us samay ke kareeb phir se "
        "yaad dilaunga."
    ),
    "reminder_confirm.kept_due": "Theek hai, main phir se yaad dilaunga.",
    "reminder_confirm.invoice_gone": (
        "Woh bill ab open nahi hai — reschedule karne ki zaroorat nahi."
    ),
    "notify.dealer_alert": (
        "⚠ Collection Alert\n\n"
        "{dealer} — {amount} — ab {days} din overdue.\n"
        "3 din se koi follow-up nahi.\n"
        "Suggestion: naya order dene se pehle aaj call karein."
    ),
    # ── Proactive early-warning alerts (7-day forecasts) — DRAFT for founder review ─
    "notify.cash_shortage_forecast": (
        "⚠️ Cash Shortage Forecast\n\n"
        "Cash ~{days} din me negative hone ka anumaan hai.\n\n"
        "Sabse bada upcoming payment: {supplier} — {amount} ({trigger_days} din me due)\n\n"
        "Expected out (7d): {expected_out}\n"
        "Expected in (7d, cash on hand samet): {expected_in}"
    ),
    "notify.stock_out_forecast": (
        "📦 Stock Alert\n\n"
        "{product} current sales pace par ~{days} din me khatam ho sakta hai."
    ),
    "notify.predue_nudge": (
        "🔔 Due Soon\n\n"
        "{dealer}\n"
        "{amount}\n\n"
        "{days} din me due hai.\n\n"
        "Suggested action:\n"
        "• Dealer ko call karein\n"
        "• Payment confirm karein\n"
        "• Agar already mil chuka hai, reply karein: record payment"
    ),
    "briefing.watch.header": "⚠ Is hafte dhyan dein",
    "briefing.watch.cash_shortage": (
        "• ~{days} din me cash shortage — mukhya roop se {supplier} {amount}"
    ),
    "briefing.watch.stock_out": "• {product} ~{days} din me khatam ho sakta hai",
    "briefing.watch.predue": "• {dealer} ka payment {days} din me due hai",
    "evening.header": "🌙 Shaam ka Business Summary",
    "evening.counts": (
        "Invoices bane: {invoices} · WhatsApp se Orders: {orders} · Payments record: {payments}"
    ),
    "evening.sales": "Aaj ki Sales: {amount}",
    "evening.margin": "Sales Margin: {amount}",
    "evening.margin_excluded": " ({items} items, {amount} exclude — cost price nahi hai)",
    "evening.collections": "Collections: {amount}",
    "evening.supplier_payments": "Supplier Payments: {amount}",
    "evening.net_cash": "Net Cash Movement: {amount}",
    "evening.outstanding": "Outstanding Receivables: {amount}",
    "evening.priority_header": "Priority Actions:",
}
