"""Romanized Odia message catalog (Odia in Latin letters, WhatsApp style).

DRAFT — needs a native Odia speaker's review before production go-live.
Likely the highest-adoption locale around Berhampur. Romanized spelling has no
single standard, so these are natural-WhatsApp drafts, not transliterations,
and common business terms are kept in English where distributors type them
that way. Mirrors the exact keys in en.py (enforced by tests/test_i18n.py);
English is the safe fallback for any key missing here.
"""

from __future__ import annotations

# Full "help" block — DRAFT. Command keywords stay English (literal triggers);
# only prose/descriptions are Romanized Odia.
_HELP_TEXT = """*OpsGenie Help*

*Cash & Overview*
• cash / cash position — ebe ra cash, 7-dina expected in/out, net position (kimba 1 / /cash)
• summary / business summary — cash, net position, 7-dina collections/payments, overdue dealers
• priorities / what should I do — mukhya kaam: cash warning, kaha ku call, supplier baki

*Dealers (jieman apananku denti)*
• dealers / all dealers — pratyeka dealer phone & baki saha
• top debtors / who owes most — sabuthu besi baki thiba dealers
• overdue / overdue dealers — kete dina late & risk level (kimba 4 / /dealer_risk)
• balance <name> — gotie dealer ra baki, jaise balance Ram Traders

*Suppliers (jieman ku apana denti)*
• suppliers / all suppliers — pratyeka supplier phone & baki saha
• top creditors — jieman ku apana sabuthu besi denti
• balance <name> — gotie supplier ra baki

*Asuthiba Cash Flow*
• collections / upcoming collections — dealers thu asiba, asanta 7 dina (kimba 2 / /collections)
• payments / upcoming payments — suppliers ku deba, asanta 7 dina (kimba 3 / /suppliers)

*Inventory*
• inventory / products / stock — natun add hoithiba products (stock qty, selling price)
• all inventory — pratyeka product, kebala natun nuhe
• stock <product> — gotie item check karantu, jaise stock Rice

*Transactions*
• invoices / recent invoices — natun invoices (number, party, total, status, dates)
• all invoices — pratyeka invoice, kebala natun nuhe
• payments / recent payments — natun record hoithiba payments
• all payments / all time payments — pratyeka payment, kebala natun nuhe
• faq / policy — apanka save hoithiba business policy (delivery days, returns, minimum order)

*Products Manage karantu* (guided, gotie gotie prashna)
• add product (kimba /add_product) — natun item: name, stock, unit, selling price, purchase price
• update stock (kimba /update_stock) — product ra stock badalantu
• update price (kimba /update_price) — product ra selling price badalantu
• update purchase price (kimba /update_purchase_price) — supplier ku jaha denti taha badalantu
• update product (kimba /update_product) — price, purchase price, kimba stock bachantu
• update gst (kimba /update_gst) — sabu kimba gotie product ra GST badalantu
• delete product (kimba /delete_product) — catalogue ru item hatantu

*Orders & Payments*
• new order (kimba /create_order, kimba "new invoice") — dealer ku sale record karantu
• record payment (kimba /record_payment) — dealer thu asiba kimba supplier ku deba payment log

*Apanka Data*
• export data (kimba /export_data) — puura business data Excel re download link
• morning briefing (kimba /morning_briefing) — aji ra briefing punarbara pathantu

*Quick Access*
• menu — type karibaru option tap karantu
• help (kimba /help) — e list kebe bi punarbara dekhantu"""

MESSAGES: dict[str, str] = {
    # ── Errors / fallbacks ────────────────────────────────────────────────
    "errors.something_wrong": "Kichi bhul heigala. Daya kari puni chesta karantu.",
    "errors.assistant_fallback": (
        "Kshama karantu, mun ebe ehar uttar dei parili nahin. Reply karantu 1 Cash · "
        "2 Collections · 3 Suppliers · 4 Dealer Risk, kimba puni lekhantu."
    ),
    "onboarding.language_changed": "✅ Heigala — ebethu mun apananku {language} re message karibi.",
    # ── Cash Position report ───────────────────────────────────────────────
    "reports.cash.header": "💰 Cash Position",
    "reports.cash.available_now": "Ebe available: {amount}",
    "reports.cash.expected_in": "Asiba (7 dina): {amount}",
    "reports.cash.due_out": "Deba ku achi (7 dina): {amount}",
    "reports.cash.net_expected": "Net expected: {amount}",
    "reports.cash.shortage": "E saptahare cash kami heipare.",
    "reports.cash.no_shortage": "E saptahare cash kami hebani.",
    # ── Collections report ─────────────────────────────────────────────────
    "reports.collections.header": "📥 Baki Collections",
    "reports.collections.none": "Asanta 7 dinare kono collection asiba nahin.",
    "reports.collections.total": "E saptahare total expected: {amount}",
    # ── Supplier payments report ───────────────────────────────────────────
    "reports.suppliers.header": "📤 Supplier Payments Baki",
    "reports.suppliers.none": "Asanta 7 dinare kono supplier payment baki nahin.",
    "reports.suppliers.total": "E saptahare total deba: {amount}",
    "reports.suppliers.cash_ok": "cash jathesta achi",
    "reports.suppliers.cash_short": "cash kami padipare",
    # ── Dealer risk report ─────────────────────────────────────────────────
    "reports.risk.header": "⚠ Dealer Risk Summary",
    "reports.risk.none": "Ebe kono overdue dealer nahin.",
    "reports.risk.high": "High Risk:",
    "reports.risk.medium": "Medium Risk:",
    "reports.risk.low": "Low Risk:",
    "reports.risk.dealer_line": "{name} — {amount} overdue ({days}d) — {late}",
    # ── Shared phrases ─────────────────────────────────────────────────────
    "reports.due.today": "aji due",
    "reports.due.weekday": "{day} re due",
    "reports.due.date": "{date} re due",
    "reports.late.none": "samaya re pay kare",
    "reports.late.one": "6 masare 1 late payment",
    "reports.late.many": "6 masare {count} late payments",
    # ── Business summary ───────────────────────────────────────────────────
    "reports.summary.header": "📊 Business Summary",
    "reports.summary.cash_now": "Ebe available cash: {amount}",
    "reports.summary.net_7d": "Net cash position (7d): {amount}",
    "reports.summary.expected_in": "Asiba (7d): {amount}",
    "reports.summary.expected_out": "Jiba (7d): {amount}",
    "reports.summary.shortage": "E saptahare cash kami heipare.",
    "reports.summary.no_shortage": "Cash kami hebani.",
    "reports.summary.overdue_count": "Overdue dealers: {count}",
    "reports.summary.overdue_hint": " — detail paain 'overdue' pathantu.",
    # ── Priorities ─────────────────────────────────────────────────────────
    "reports.priorities.none": "🎯 Ebe kichi urgent nahin — kono priority action nahin.",
    "reports.priorities.header": "🎯 Priorities",
    # ── Dealer / supplier lists ────────────────────────────────────────────
    "reports.dealers.none": "Apanka pakhare ebe kono dealer nahin.",
    "reports.dealers.header": "👥 Dealers ({count}):",
    "reports.suppliers_list.none": "Apanka pakhare ebe kono supplier nahin.",
    "reports.suppliers_list.header": "🚚 Suppliers ({count}):",
    "reports.party.no_phone": "phone nahin",
    "reports.party.line": "{name} — {phone} — baki {amount}",
    "reports.top_debtors.none": "Ebe kono dealer pakhare apanka kichi baki nahin.",
    "reports.top_debtors.header": "💰 Top Debtors",
    "reports.top_creditors.none": "Ebe apana kono supplier ku kichi denti nahin.",
    "reports.top_creditors.header": "💸 Top Creditors",
    # ── Inventory ──────────────────────────────────────────────────────────
    "reports.inventory.none": "Apanka catalogue re ebe kono product nahin.",
    "reports.inventory.label_recent": "Recent Inventory",
    "reports.inventory.label_all": "Sabu Inventory",
    "reports.inventory.header_partial": "📦 {label} ({count} of {total}):",
    "reports.inventory.header_full": "📦 {label} ({count}):",
    "reports.inventory.more": (
        "\n\n…au {remaining} adhika — puura list paain 'all inventory' pathantu."
    ),
    "reports.product.price_not_set": "price set nahin",
    # ── FAQs ───────────────────────────────────────────────────────────────
    "reports.faq.none": "Apanka pakhare ebe kono save policy nahin.",
    "reports.faq.header": "❓ FAQs ({count}):",
    "reports.faq.qa": "Q: {question}\nA: {answer}",
    # ── Invoices ───────────────────────────────────────────────────────────
    "reports.invoices.none": "Apanka pakhare ebe kono invoice nahin.",
    "reports.invoices.label_recent": "Recent Invoices",
    "reports.invoices.label_all": "Sabu Invoices",
    "reports.invoices.header_partial": "📄 {label} ({count} of {total}):",
    "reports.invoices.header_full": "📄 {label} ({count}):",
    "reports.invoices.more": (
        "\n\n…au {remaining} adhika — puura list paain 'all invoices' pathantu."
    ),
    "reports.invoices.line": "{number} — {party} — {amount} — {status} — {due}",
    "reports.unknown_party": "unknown party",
    # ── Payments ───────────────────────────────────────────────────────────
    "reports.payments.none": "Apanka pakhare ebe kono payment record nahin.",
    "reports.payments.label_recent": "Recent Payments",
    "reports.payments.label_all": "Sabu Payments",
    "reports.payments.header_partial": "💵 {label} ({count} of {total}):",
    "reports.payments.header_full": "💵 {label} ({count}):",
    "reports.payments.more": (
        "\n\n…au {remaining} adhika — puura list paain 'all payments' pathantu."
    ),
    "reports.payments.from": "thu",
    "reports.payments.to": "ku",
    "reports.payments.line": "{amount} — invoice {number} {direction} — {date}",
    # ── Party balance ──────────────────────────────────────────────────────
    "reports.balance.dealer_owes": "{party} apananku {amount} deba achi.",
    "reports.balance.you_owe": "Apana {party} ku {amount} deba achi.",
    # ── Stock item ─────────────────────────────────────────────────────────
    "reports.stock.not_found": "'{name}' saha milu thiba kono product milila nahin.",
    "reports.stock.line": "{name} — {stock} stock re — {price}",
    # ── Sales impact ───────────────────────────────────────────────────────
    "reports.sales.revenue": "revenue {amount}",
    "reports.sales.profit": "profit {amount}",
    "reports.sales.left": "{qty} stock re bachila",
    "reports.sales.total_revenue": "Total revenue: {amount}",
    "reports.sales.total_profit": "Total profit: {amount}",
    "reports.sales.no_cost": "({missing} ra purchase price nahin — profit ru badra)",
    # ── Excel export link ──────────────────────────────────────────────────
    "reports.export.not_configured": (
        "Data export link ebe setup nahin — nija OpsGenie admin nku configure karantu."
    ),
    "reports.export.ready": (
        "Apanka latest Excel export taiyar.\nDownload ({ttl} min valid): {link}"
    ),
    # ── Help text ──────────────────────────────────────────────────────────
    "menu.help_text": _HELP_TEXT,
    # ── Onboarding ─────────────────────────────────────────────────────────
    "onboarding.intro": (
        "👋 OpsGenie ku swagat! Chaluntu apanka business set up karantu — 5 minute lagiba, "
        "au apana kebe bi rukikari continue kari parantu.\n\n"
        "Prathame: apana kie prakara business chalanti? "
        "(jaise FMCG Distributor, Pharma Distributor)"
    ),
    "onboarding.progress": "✅ Step {step}/{total} heigala.",
    "onboarding.finish": (
        "🎉 Setup sarigala!\n\n"
        "Kali sakalu mun apananku pratidina briefing pathaibi. Apana mote kichi bi puchi parantu, "
        "jaise:\n"
        "• Cash position\n"
        "• Ram ku kete deba?\n"
        "• Supplier dues\n"
        "• Dealer risk\n\n"
        "Kebe bi menu pathantu option tap karibaku, kimba /help puura list dekhibaku."
    ),
    "onboarding.gst.mode_ask": (
        "Apanka sabu products ra GST rate same ki, kimba product hisabare alaga? "
        "Reply karantu 'same', 'varies', kimba 'not sure' pare thik karibaku."
    ),
    "onboarding.gst.rate_ask": "Apanka GST rate kete? (jaise 5, 12, 18, kimba 0 jadi exempt)",
    "onboarding.gst.mode_invalid": "Daya kari reply karantu 'same', 'varies', kimba 'not sure'.",
    "onboarding.gst.rate_invalid": (
        "Daya kari 0 ru 100 madhyare number pathantu, jaise 18 "
        "(kimba 'not sure' pare thik karibaku)."
    ),
    "onboarding.product.intro": (
        "Ebe apanka products add karantu. Reply 'one by one' gotie gotie, kimba 'bulk' sabu ekathi "
        "puura details saha (jaise Rice, 300, 400, kg, 100, 5). 'done' skip karibaku."
    ),
    "onboarding.product.bulk_format": (
        "Apanka products gotie line re gotie, ei format re pathantu:\n"
        "Name, Purchase Price, Selling Price, Unit, Stock, GST%\n"
        "jaise\n"
        "Rice, 300, 400, kg, 100, 5\n"
        "Dal, 320, 450, kg, 50, 12\n"
        "Je field set karibaku chahanti nahin sethipain 'skip' lekhantu "
        "(jaise Rice, skip, 400, kg, 100, skip). Sarile 'done' pathantu."
    ),
    "onboarding.product.first_name": (
        "Apanka prathama product ra naam pathantu (jaise Rice), kimba 'done' skip karibaku."
    ),
    "onboarding.product.mode_invalid": (
        "Daya kari reply karantu 'one by one' kimba 'bulk' — kimba 'done' products skip karibaku."
    ),
    "onboarding.product.bulk_error": "Eha bujhi hela nahin: {error}",
    "onboarding.product.bulk_added": (
        "{count} product add hela: {names}. Au pathantu, kimba sarile 'done' pathantu."
    ),
    "onboarding.product.quantity_ask": (
        "Ebe apanka pakhare kete {name} stock re achi? (jaise 100, kimba 'skip')"
    ),
    "onboarding.product.quantity_invalid": (
        "Daya kari gotie number pathantu, jaise 100 (kimba 'skip')."
    ),
    "onboarding.product.unit": "Eha kaun unit re? (jaise kg, pcs, box, litre, kimba 'skip')",
    "onboarding.product.price_ask": "{name} ra selling price kete? (jaise 400, kimba 'skip')",
    "onboarding.product.price_invalid": (
        "Daya kari gotie number pathantu, jaise 400 (kimba 'skip')."
    ),
    "onboarding.product.purchase_ask": (
        "{name} ra purchase price (cost price) kete? (jaise 300, kimba 'skip')"
    ),
    "onboarding.product.purchase_invalid": (
        "Daya kari gotie number pathantu, jaise 300 (kimba 'skip')."
    ),
    "onboarding.product.gst_ask": (
        "{name} ra GST% kete? (jaise 5, 12, 18, kimba 'skip' pare thik karibaku)"
    ),
    "onboarding.product.gst_invalid": (
        "Daya kari 0 ru 100 madhyare number pathantu, jaise 18 (kimba 'skip' pare thik karibaku)."
    ),
    "onboarding.product.added": (
        "Product add hela: {name} ({stock} stock re). Au pathantu, kimba 'done'."
    ),
    "onboarding.dealers.intro": (
        "Ebe apanka dealers (customers) add karantu. "
        "Prathama dealer ra naam pathantu, kimba 'done'."
    ),
    "onboarding.dealer.credit_ask": (
        "{name} ku apana kete credit dina denti? (jaise 15, kimba 'skip')"
    ),
    "onboarding.dealer.added": "Dealer {name} add hela. Parabarti dealer ra naam, kimba 'done'.",
    "onboarding.suppliers.intro": (
        "Ebe apanka suppliers. Prathama supplier ra naam pathantu, kimba 'done'."
    ),
    "onboarding.supplier.credit_ask": (
        "{name} apananku pay karibaku kete dina denti? (jaise 15/'skip')"
    ),
    "onboarding.supplier.added": (
        "Supplier {name} add hela. Parabarti supplier ra naam, kimba 'done'."
    ),
    "onboarding.party.phone_ask": "{name} ra phone number? (kimba 'skip')",
    "onboarding.party.credit_invalid": (
        "Daya kari dina ra number pathantu, jaise 15 (kimba 'skip')."
    ),
    "onboarding.opening.ask": "Ebe apanka business re kete cash achi? (jaise 320000)",
    "onboarding.opening.invalid": "Daya kari gotie amount pathantu, jaise 320000.",
    "onboarding.receivable.ask": "Kono dealer pakhare ebe apanka paisa baki achi ki? (yes/no)",
    "onboarding.receivable.which": "Kaun dealer apananku deba? (naam)",
    "onboarding.receivable.amount_ask": "{party} apananku kete deba? (jaise 42000)",
    "onboarding.receivable.amount_invalid": "Daya kari gotie amount pathantu, jaise 42000.",
    "onboarding.receivable.date_ask": (
        "{party} thu payment kebe expect karanti? (jaise Friday, 15 days, kimba next week)"
    ),
    "onboarding.receivable.recorded": (
        "{amount} {party} thu record hela. Au kono dealer deba? (yes/no)"
    ),
    "onboarding.payable.ask": "Kono supplier payment pending achi ki? (yes/no)",
    "onboarding.payable.which": "Kaun supplier ku apana deba? (naam)",
    "onboarding.payable.amount_ask": "Apana {party} ku kete deba? (jaise 82000)",
    "onboarding.payable.amount_invalid": "Daya kari gotie amount pathantu, jaise 82000.",
    "onboarding.payable.date_ask": (
        "{party} ku payment kebe due? (jaise Friday, 15 days, kimba next week)"
    ),
    "onboarding.payable.recorded": (
        "{amount} {party} ku record hela. Au kono supplier pending? (yes/no)"
    ),
    "onboarding.yes_no_invalid": "Daya kari yes kimba no reply karantu.",
    "onboarding.date_invalid": (
        "Kshama karantu, se date bujhi heli nahin. "
        "Try karantu jaise Friday, 15 days, kimba next week."
    ),
    "onboarding.briefing.ask": (
        "Sesha step — mun apanka morning briefing kebe pathaibi? Reply 7, 8, kimba 9."
    ),
    "onboarding.briefing.invalid": "Daya kari gotie ghanta reply karantu, jaise 7, 8, kimba 9.",
    "onboarding.briefing.range": (
        "Daya kari sakala 5 ru 11 madhyare ghanta bachantu (jaise 7, 8, kimba 9)."
    ),
    # ── Interactive menu ───────────────────────────────────────────────────
    "menu.fallback": "Tale gotie option tap karantu, kimba puura list paain /help pathantu.",
    "menu.msg.reports.body": "Reports & Overview — gotie bachantu:",
    "menu.msg.reports.button": "Report bachantu",
    "menu.msg.inventory.body": "Inventory, Transactions & Products — gotie bachantu:",
    "menu.msg.inventory.button": "Option bachantu",
    "menu.msg.orders.body": "Orders, Payments & aapanka Data — gotie bachantu:",
    "menu.msg.orders.button": "Option bachantu",
    "menu.section.cash_overview": "Cash & Overview",
    "menu.section.money_flow": "Paisa Flow",
    "menu.section.dealers_suppliers": "Dealers & Suppliers",
    "menu.section.inventory_transactions": "Inventory & Transactions",
    "menu.section.manage_products": "Products Manage karantu",
    "menu.section.orders_payments": "Orders & Payments",
    "menu.section.your_data": "Aapanka Data",
    "menu.section.full_lists": "Puura Lists",
    "menu.row.cash.title": "Cash Position",
    "menu.row.cash.desc": "Ebe cash & 7-dina in/out",
    "menu.row.summary.title": "Business Summary",
    "menu.row.summary.desc": "Sampurna snapshot",
    "menu.row.priorities.title": "Priorities",
    "menu.row.priorities.desc": "Aji kana karibi",
    "menu.row.overdue.title": "Overdue Dealers",
    "menu.row.overdue.desc": "Kete dina late & risk level",
    "menu.row.collections.title": "Collections Due",
    "menu.row.collections.desc": "Asanta 7 dinare asiba",
    "menu.row.payments.title": "Payments Due",
    "menu.row.payments.desc": "Suppliers ku deba, 7 dina",
    "menu.row.all_dealers.title": "Sabu Dealers",
    "menu.row.all_dealers.desc": "Pratyeka dealer, phone & baki",
    "menu.row.all_suppliers.title": "Sabu Suppliers",
    "menu.row.all_suppliers.desc": "Pratyeka supplier, phone & baki",
    "menu.row.top_debtors.title": "Top Debtors",
    "menu.row.top_debtors.desc": "Jie apananku sabuthu besi deba achi",
    "menu.row.top_creditors.title": "Top Creditors",
    "menu.row.top_creditors.desc": "Jieman ku apana sabuthu besi deba achi",
    "menu.row.inventory.title": "Recent Inventory",
    "menu.row.inventory.desc": "Natun products, stock & price",
    "menu.row.invoices.title": "Recent Invoices",
    "menu.row.invoices.desc": "Natun invoices, latest aage",
    "menu.row.recent_payments.title": "Recent Payments",
    "menu.row.recent_payments.desc": "Natun record heithiba payments",
    "menu.row.faq.title": "FAQs",
    "menu.row.faq.desc": "Aapanka save heithiba business policies",
    "menu.row.add_product.title": "Product Add karantu",
    "menu.row.add_product.desc": "Natun item add karantu",
    "menu.row.update_stock.title": "Stock Update karantu",
    "menu.row.update_stock.desc": "Product ra stock qty badalantu",
    "menu.row.update_price.title": "Price Update karantu",
    "menu.row.update_price.desc": "Product ra selling price badalantu",
    "menu.row.update_cost.title": "Cost Update karantu",
    "menu.row.update_cost.desc": "Supplier ku jaha denti taha badalantu",
    "menu.row.delete_product.title": "Product Delete karantu",
    "menu.row.delete_product.desc": "Catalogue ru item hatantu",
    "menu.row.update_product.title": "Product Update karantu",
    "menu.row.update_product.desc": "Price, cost, kimba stock bachantu",
    "menu.row.create_order.title": "Order Tiari karantu",
    "menu.row.create_order.desc": "Dealer ku sale record karantu",
    "menu.row.record_payment.title": "Payment Record karantu",
    "menu.row.record_payment.desc": "Asithiba kimba dithiba payment log karantu",
    "menu.row.update_gst.title": "GST Update karantu",
    "menu.row.update_gst.desc": "Sabu kimba gotie product ra GST badalantu",
    "menu.row.export_data.title": "Data Export karantu",
    "menu.row.export_data.desc": "Nija Excel data download karantu",
    "menu.row.morning_briefing.title": "Morning Briefing",
    "menu.row.morning_briefing.desc": "Aji ra briefing punarbara pathantu",
    "menu.row.all_inventory.title": "Sabu Inventory",
    "menu.row.all_inventory.desc": "Pratyeka product, kebala natun nuhe",
    "menu.row.all_invoices.title": "Sabu Invoices",
    "menu.row.all_invoices.desc": "Pratyeka invoice, kebala natun nuhe",
    "menu.row.all_payments.title": "Sabu Payments",
    "menu.row.all_payments.desc": "Pratyeka payment, kebala natun nuhe",
}
