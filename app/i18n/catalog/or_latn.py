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
• add dealer (kimba /add_dealer) — natun dealer add karantu: naam, phone, credit dina
• edit dealer (kimba /edit_dealer) — dealer ra phone, credit limit, terms, kimba GSTIN badalantu

*Suppliers (jieman ku apana denti)*
• suppliers / all suppliers — pratyeka supplier phone & baki saha
• top creditors — jieman ku apana sabuthu besi denti
• balance <name> — gotie supplier ra baki
• add supplier (kimba /add_supplier) — natun supplier add karantu: naam, phone, credit dina
• edit supplier (kimba /edit_supplier) — supplier ra phone, credit limit, terms, kimba GSTIN

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
• stock take (kimba /stock_take) — bohut product ra stock ekathi recount kimba adjust karantu

*Orders & Payments*
• new order (kimba /create_order, kimba "new invoice") — dealer ku sale record karantu
• record payment (kimba /record_payment) — dealer thu asiba kimba supplier ku deba payment log

*Corrections*
• undo payment (kimba /undo_payment) — ebe record kariba payment void karantu
• undo order (kimba /undo_order) — ebe tiari kariba order void karantu (jadi unpaid achi)
• edit invoice (kimba /edit_invoice) — invoice ra amount, date, kimba party sudharantu (unpaid re)
• edit payment (kimba /edit_payment) — record hoithiba payment ra amount kimba date sudharantu

*Apanka Data*
• export data (kimba /export_data) — puura business data Excel re download link
• morning briefing (kimba /morning_briefing) — aji ra briefing punarbara pathantu

*Reports & Statements* (e mahara, Excel + PDF jahin bataithiba)
• ledger <name> — running-balance statement, Excel + PDF, jemiti ledger Ram Traders
• sales register / purchase register (kimba duhenka pain "gst report") — GST register + summary
• payment register (kimba receipt register) — e mahara receipts o payments
• day book — e mahara sabu invoice o payment, eka list re
• outstanding report (kimba aging report) — 0-30/31-60/61-90/90+ dina bucket, Excel + PDF

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
    "reports.download.ready": (
        "Apanka {report_name} ({period}) taiyar.\nDownload ({ttl} min valid):\n{links}"
    ),
    "reports.ledger.not_found": "'{name}' saha milu thiba kono dealer kimba supplier milila nahin.",
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
    "onboarding.gst.missing_ask": (
        "Amane apanka jyada products ra GST rates import kari deichhu. Ei {count} re abhi "
        "nahin achi: {names}. Etiki kaun GST rate use karibaku? (jaise 5, 12, 18, kimba 0 — "
        "kimba 'skip' pare thik karibaku)"
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
    "onboarding.product.bulk_format_no_gst": (
        "Apanka products gotie line re gotie, ei format re pathantu:\n"
        "Name, Purchase Price, Selling Price, Unit, Stock\n"
        "jaise\n"
        "Rice, 300, 400, kg, 100\n"
        "Dal, 320, 450, kg, 50\n"
        "Je field set karibaku chahanti nahin sethipain 'skip' lekhantu "
        "(jaise Rice, skip, 400, kg, 100). Sarile 'done' pathantu."
    ),
    "onboarding.product.first_name": (
        "Apanka prathama product ra naam pathantu (jaise Rice), kimba 'done' skip karibaku."
    ),
    "onboarding.product.mode_invalid": (
        "Daya kari reply karantu 'one by one' kimba 'bulk' — kimba 'done' products skip karibaku."
    ),
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
        "Ebe apanka dealers (customers) add karantu. Reply 'one by one' gotie gotie add karibaku, "
        "kimba 'bulk' sabu ekathi pathaibaku (jaise Ram Traders, 9876543210, 15). "
        "'done' skip karibaku."
    ),
    "onboarding.dealer.bulk_format": (
        "Apanka dealers gotie line re gotie, ei format re pathantu:\n"
        "Name, Phone, Credit Days\n"
        "jaise\n"
        "Ram Traders, 9876543210, 15\n"
        "Shree Enterprises, 9123456780, 30\n"
        "Je field set karibaku chahanti nahin sethipain 'skip' lekhantu "
        "(jaise Ram Traders, skip, 15). Sarile 'done' pathantu."
    ),
    "onboarding.dealer.first_name": (
        "Apanka prathama dealer ra naam pathantu (jaise Ram Traders), kimba 'done' skip karibaku."
    ),
    "onboarding.dealer.mode_invalid": (
        "Daya kari reply karantu 'one by one' kimba 'bulk' — kimba 'done' dealers skip karibaku."
    ),
    "onboarding.dealer.bulk_added": (
        "{count} dealer add hela: {names}. Au pathantu, kimba sarile 'done' pathantu."
    ),
    "onboarding.dealer.credit_ask": (
        "{name} ku apana kete credit dina denti? (jaise 15, kimba 'skip')"
    ),
    "onboarding.dealer.added": "Dealer {name} add hela. Parabarti dealer ra naam, kimba 'done'.",
    "onboarding.dealer.missing_ask": (
        "Apanka import ru amaku {count} dealer(s) milila, kintu tankara phone number kimba "
        "credit days missing achi. Ebe complete karibaku, kimba pare? (now/later)"
    ),
    "onboarding.dealer.missing_list": (
        "{listing}\n\n'bulk' reply karantu sabuku ekathi paste karibaku, kimba 'one by one' "
        "gotie gotie fill karibaku."
    ),
    "onboarding.dealer.missing_bulk_format": (
        "Pratiek dealer ra details fill karibaku gotie line pathantu:\n"
        "Name, Phone, Credit Days\n"
        "jaise\n"
        "Ram Traders, 9876543210, 15\n"
        "Kebala uparara list saha match hela naam update hebe."
    ),
    "onboarding.dealer.missing_bulk_done": "{count} dealer update hela: {names}.",
    "onboarding.dealer.missing_bulk_unmatched": (
        "Ei naam uparara list saha match nahin hela, sethipain update nahin hela: {names}."
    ),
    "onboarding.suppliers.intro": (
        "Ebe apanka suppliers. Reply 'one by one' gotie gotie add karibaku, "
        "kimba 'bulk' sabu ekathi pathaibaku (jaise Metro Distributors, 9988776655, 30). "
        "'done' skip karibaku."
    ),
    "onboarding.supplier.bulk_format": (
        "Apanka suppliers gotie line re gotie, ei format re pathantu:\n"
        "Name, Phone, Credit Days\n"
        "jaise\n"
        "Metro Distributors, 9988776655, 30\n"
        "Suresh Wholesale, 9871234560, 15\n"
        "Je field set karibaku chahanti nahin sethipain 'skip' lekhantu "
        "(jaise Metro Distributors, skip, 30). Sarile 'done' pathantu."
    ),
    "onboarding.supplier.first_name": (
        "Apanka prathama supplier ra naam pathantu (jaise Metro Distributors), "
        "kimba 'done' skip karibaku."
    ),
    "onboarding.supplier.mode_invalid": (
        "Daya kari reply karantu 'one by one' kimba 'bulk' — kimba 'done' suppliers skip karibaku."
    ),
    "onboarding.supplier.bulk_added": (
        "{count} supplier add hela: {names}. Au pathantu, kimba sarile 'done' pathantu."
    ),
    "onboarding.supplier.credit_ask": (
        "{name} apananku pay karibaku kete dina denti? (jaise 15/'skip')"
    ),
    "onboarding.supplier.added": (
        "Supplier {name} add hela. Parabarti supplier ra naam, kimba 'done'."
    ),
    "onboarding.supplier.missing_ask": (
        "Apanka import ru amaku {count} supplier(s) milila, kintu tankara phone number kimba "
        "credit days missing achi. Ebe complete karibaku, kimba pare? (now/later)"
    ),
    "onboarding.supplier.missing_list": (
        "{listing}\n\n'bulk' reply karantu sabuku ekathi paste karibaku, kimba 'one by one' "
        "gotie gotie fill karibaku."
    ),
    "onboarding.supplier.missing_bulk_format": (
        "Pratiek supplier ra details fill karibaku gotie line pathantu:\n"
        "Name, Phone, Credit Days\n"
        "jaise\n"
        "Metro Distributors, 9988776655, 30\n"
        "Kebala uparara list saha match hela naam update hebe."
    ),
    "onboarding.supplier.missing_bulk_done": "{count} supplier update hela: {names}.",
    "onboarding.supplier.missing_bulk_unmatched": (
        "Ei naam uparara list saha match nahin hela, sethipain update nahin hela: {names}."
    ),
    "onboarding.party.phone_ask": "{name} ra phone number? (kimba 'skip')",
    "onboarding.party.credit_invalid": (
        "Daya kari dina ra number pathantu, jaise 15 (kimba 'skip')."
    ),
    "onboarding.bulk_error": "Eha bujhi hela nahin: {error}",
    "onboarding.opening.ask": "Ebe apanka business re kete cash achi? (jaise 320000)",
    "onboarding.opening.invalid": "Daya kari gotie amount pathantu, jaise 320000.",
    "onboarding.receivable.ask": "Kono dealer pakhare ebe apanka paisa baki achi ki? (yes/no)",
    "onboarding.receivable.which": "Kaun dealer apananku deba? (naam)",
    "onboarding.receivable.confirm_new": (
        "Mo pakhare '{name}' naam re dealer ebe nahin — natun dealer bhabare add karibi ki? "
        "(yes/no)"
    ),
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
    "onboarding.payable.confirm_new": (
        "Mo pakhare '{name}' naam re supplier ebe nahin — natun supplier bhabare add karibi ki? "
        "(yes/no)"
    ),
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
    # Resume: progress checklist ("progress"/"status") and restart ("restart")
    "onboarding.section.business_type": "Business type",
    "onboarding.section.products": "Products",
    "onboarding.section.dealers": "Dealers",
    "onboarding.section.suppliers": "Suppliers",
    "onboarding.section.opening_balance": "Opening balance",
    "onboarding.section.receivables": "Dealer baki",
    "onboarding.section.payables": "Supplier baki",
    "onboarding.section.briefing_hour": "Briefing samaya",
    "onboarding.import_confirm.title": "📋 Apanka import ru kichi tathya milila:",
    "onboarding.import_confirm.line_products": "✅ {count} product(s)",
    "onboarding.import_confirm.line_dealers": "✅ {count} dealer(s)",
    "onboarding.import_confirm.line_suppliers": "✅ {count} supplier(s)",
    "onboarding.import_confirm.line_receivables": (
        "✅ {count} outstanding receivable invoice(s) ({amount})"
    ),
    "onboarding.import_confirm.line_payables": (
        "✅ {count} outstanding payable invoice(s) ({amount})"
    ),
    "onboarding.import_confirm.ask": "Eha thik ki? (yes/no)",
    "onboarding.import_confirm.no_ack": (
        "Kichi asubidha nahi — apana eha ku jekauNsi samaya re thik kari paribe: "
        "'edit dealer <name>', 'edit supplier <name>', 'add dealer', 'add supplier', "
        "kimba 'stock take' re product quantity badalantu. Apanka baki setup jari achi."
    ),
    "onboarding.status.title": "📋 Setup progress — {percent}% sampurna heigala.",
    "onboarding.status.section_done": "✅ {name}",
    "onboarding.status.section_current": "▶️ {name} (apana ethare achanti)",
    "onboarding.status.section_pending": "⬜ {name}",
    "onboarding.status.footer_generic": "Jari rakhibaku apanka paravarti uttara reply karantu.",
    "onboarding.status.restart_hint": "Setup puni arambha karibaku 'restart' pathantu.",
    "onboarding.restart.confirm": (
        "⚠️ Ehare apana ebe paryanta bharithiba saba tathya (products, dealers, suppliers, "
        "opening balance) mucchi jiba au setup arambharu puni heba. Apana nishchita ki? (yes/no)"
    ),
    "onboarding.restart.cancelled": (
        "Thik achi — apanka setup jari achi. Upara sesha prashna ra uttara pathantu."
    ),
    "onboarding.restart.done": (
        "🔄 Saba mucchigala. Chaluntu puni arambharu apanka business set up karibaa.\n\n"
        "Prathama prashna: apana kaun prakara business karanti? (jaise FMCG Distributor, Pharma "
        "Distributor)"
    ),
    # ── Interactive menu ───────────────────────────────────────────────────
    "menu.fallback": "Tale gotie option tap karantu, kimba puura list paain /help pathantu.",
    "menu.msg.reports.body": "Reports & Overview — gotie bachantu:",
    "menu.msg.reports.button": "Report bachantu",
    "menu.msg.inventory.body": "Inventory, Transactions & Products — gotie bachantu:",
    "menu.msg.inventory.button": "Option bachantu",
    "menu.msg.orders.body": "Orders, Payments & aapanka Data — gotie bachantu:",
    "menu.msg.orders.button": "Option bachantu",
    "menu.msg.statements.body": "Reports & Statements — gotie bachantu:",
    "menu.msg.statements.button": "Statement bachantu",
    "menu.msg.corrections.body": (
        "Corrections — purbaru record hoithiba kichi undo kimba edit karantu:"
    ),
    "menu.msg.corrections.button": "Corrections",
    "menu.section.cash_overview": "Cash & Overview",
    "menu.section.money_flow": "Paisa Flow",
    "menu.section.dealers_suppliers": "Dealers & Suppliers",
    "menu.section.inventory_transactions": "Inventory & Transactions",
    "menu.section.manage_products": "Products Manage karantu",
    "menu.section.orders_payments": "Orders & Payments",
    "menu.section.manage_parties": "Party Paricalana",
    "menu.section.your_data": "Aapanka Data",
    "menu.section.full_lists": "Puura Lists",
    "menu.section.reports_statements": "Reports & Statements",
    "menu.section.corrections": "Corrections",
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
    "menu.row.add_dealer.title": "Dealer Add Karantu",
    "menu.row.add_dealer.desc": "Natun dealer add karantu",
    "menu.row.add_supplier.title": "Supplier Add Karantu",
    "menu.row.add_supplier.desc": "Natun supplier add karantu",
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
    "menu.row.gst_report.title": "GST Report",
    "menu.row.gst_report.desc": "Sales o purchase register, duhenka pain",
    "menu.row.sales_register.title": "Sales Register",
    "menu.row.sales_register.desc": "GST sales register + rate-wise summary",
    "menu.row.purchase_register.title": "Purchase Register",
    "menu.row.purchase_register.desc": "GST purchase register + rate-wise summary",
    "menu.row.payment_register.title": "Payment Register",
    "menu.row.payment_register.desc": "E mahara receipts o payments",
    "menu.row.day_book.title": "Day Book",
    "menu.row.day_book.desc": "E mahara sabu invoice o payment",
    "menu.row.outstanding_report.title": "Outstanding Report",
    "menu.row.outstanding_report.desc": "0-30/31-60/61-90/90+ dina bucket",
    "menu.row.undo_payment.title": "Undo Payment",
    "menu.row.undo_payment.desc": "Ebe record kariba payment void karantu",
    "menu.row.undo_order.title": "Undo Order",
    "menu.row.undo_order.desc": "Ebe tiari kariba order void karantu",
    "menu.row.edit_invoice.title": "Edit Invoice",
    "menu.row.edit_invoice.desc": "Invoice ra amount, date, kimba party sudharantu",
    "menu.row.edit_payment.title": "Edit Payment",
    "menu.row.edit_payment.desc": "Payment ra amount kimba date sudharantu",
    "menu.row.edit_dealer.title": "Edit Dealer",
    "menu.row.edit_dealer.desc": "Dealer ra phone, limit, terms, GSTIN badalantu",
    "menu.row.edit_supplier.title": "Edit Supplier",
    "menu.row.edit_supplier.desc": "Supplier ra phone, limit, terms, GSTIN badalantu",
    "menu.row.stock_take.title": "Stock Take",
    "menu.row.stock_take.desc": "Bohut products ra stock ekathi badalantu",
    # ── Workflows (shared) ─────────────────────────────────────────────────
    "workflow.cancelled": "OK, cancel karidela.",
    "workflow.yes_no": "Daya kari yes kimba no reply karantu.",
    "workflow.error_restart": (
        "Kichi bhul heigala. Daya kari puni '{trigger}' kahi arambha karantu."
    ),
    "workflow.kind_dealer": "dealer",
    "workflow.kind_supplier": "supplier",
    # ── Record payment ─────────────────────────────────────────────────────
    "payment.start": "Kie apananku pay kala, kimba apana kahaku pay kale? (party naam)",
    "payment.need_party": "Daya kari party naam kuhantu.",
    "payment.amount_receivable": "Semane apananku kete pay kale? (jaise 25000)",
    "payment.amount_payable": "Apana semananku kete pay kale? (jaise 25000)",
    "payment.disambiguation": (
        "'{name}' dealer au supplier dui saha match kare. "
        "Reply 1 jadi se dealer (semane apananku pay kale), "
        "kimba 2 jadi supplier (apana semananku pay kale)."
    ),
    "payment.dealer_or_supplier_invalid": (
        "Daya kari dealer paain 1 kimba supplier paain 2 reply karantu."
    ),
    "payment.invoice_selection_invalid": (
        "Daya kari 1 ru {count} madhyare number reply karantu, kimba 'all'."
    ),
    "payment.open_invoices": (
        "{party} ra {count} open invoices achi:\n{listing}\n"
        "Gotie number reply karantu, kimba 'all' sabu upare apply karibaku (purana aage)."
    ),
    "payment.open_invoice_line": (
        "{index}. {number} — {total} total, {outstanding} baki, due {due}"
    ),
    "payment.new_party_type": (
        "Mo pakhare '{name}' nahin. Se dealer (customer) ki supplier "
        "(jahathu apana kinanti)? Reply 1 Dealer kimba 2 Supplier."
    ),
    "payment.new_party_type_invalid": "Daya kari 1 Dealer kimba 2 Supplier reply karantu.",
    "payment.add_new_party": "'{name}' ku natun {kind} add karibe? yes/no",
    "payment.no_open_invoice": (
        "Mun kebala existing invoice birudhare payment record kari paribi, au {party} ra "
        "{kind} hisabare kono open invoice nahin. Prathame semananka paain invoice tiari "
        "karantu, tapare 'record payment' puni kuhantu."
    ),
    "payment.got_it_no_invoice": "Thik achi. {message}",
    "payment.amount_invalid": "Daya kari gotie amount pathantu, jaise 25000.",
    "payment.amount_positive": "Daya kari zero tharu adhika amount pathantu.",
    "payment.date_ask": (
        "Eha kebe pay hela? Reply 'today', 'yesterday', '3 days ago', kimba skip aji paain."
    ),
    "payment.date_invalid": (
        "Kshama karantu, se date bujhi heli nahin. Try 'today', 'yesterday', '3 days ago'."
    ),
    "payment.verb_from": "thu",
    "payment.verb_to": "ku",
    "payment.target_invoice": " invoice {number} birudhare",
    "payment.preview": (
        "Confirm: {amount} {party}{target} {verb} {date} re.\n"
        "Reply YES record karibaku, NO cancel karibaku."
    ),
    # ── Create order ───────────────────────────────────────────────────────
    "order.start": "E order kaha paain? (dealer naam)",
    "order.need_dealer": "Daya kari dealer naam kuhantu.",
    "order.dealer_found": "{dealer} paain order. Kaun product?",
    "order.add_new_dealer": (
        "Mo pakhare '{dealer}' dealer hisabare nahin. Semananku natun dealer add karibe? yes/no"
    ),
    "order.new_dealer_added": "Thik achi, {dealer} ku natun dealer add heba. Kaun product?",
    "order.need_one_product": "Prathame anteast gotie product add karantu, kimba 'cancel'.",
    "order.need_product": "Daya kari product naam kuhantu, kimba 'done' jadi sarigala.",
    "order.quantity_ask": "{product} ra kete {unit}?",
    "order.price_ask": "{product} ra selling price kete?",
    "order.add_new_product": "Mo pakhare '{product}' catalogue re nahin. Add karibe? yes/no",
    "order.new_product_declined": "Thik achi. Kaun product? (kimba 'done')",
    "order.price_invalid": "Daya kari gotie price pathantu, jaise 55.",
    "order.price_positive": "Daya kari zero tharu adhika price pathantu.",
    "order.quantity_invalid": "Daya kari gotie quantity pathantu, jaise 10.",
    "order.quantity_positive": "Daya kari zero tharu adhika quantity pathantu.",
    "order.item_added": (
        "{quantity} x {product} add hela. Au product add karantu, kimba 'done' reply karantu."
    ),
    "order.line": "- {quantity} x {product} @ {price} = {total}",
    "order.subtotal": "Subtotal: {amount}",
    "order.gst": "GST{rate_label}: {amount}",
    "order.total": "Total: {amount}",
    "order.preview_header": "{dealer} paain order confirm karantu:",
    "order.preview_footer": "Reply YES tiari karibaku, NO cancel karibaku.",
    # ── Edit invoice / edit payment (safe cases only) ───────────────────────
    "edit.invoice_number_ask": "Kauna invoice? Ehara invoice number pathantu, kimba 'cancel'.",
    "edit.invoice_not_found": (
        "Mote '{number}' naamara invoice milila nahin. Jaanch kari puni pathantu, kimba 'cancel'."
    ),
    "edit.invoice_has_payment": (
        "Invoice {number} re purbaru payment record achi — prathame eha void karantu "
        "ebong puni tiari karantu."
    ),
    "edit.field_ask_invoice": (
        "Kana edit karibe — amount, date, kimba party? "
        "Reply karantu 'amount', 'date', kimba 'party'."
    ),
    "edit.field_invalid_invoice": (
        "Daya kari reply karantu 'amount', 'date', kimba 'party' — kimba 'cancel'."
    ),
    "edit.amount_ask": "Bartaman ra amount {current}. Nua amount kana heba? (jemiti 1200)",
    "edit.date_ask": "Bartaman ra date {current}. Nua date kana heba? (jemiti 2026-01-15)",
    "edit.invoice_party_ask_dealer": "Bartaman ra dealer {current}. Nua dealer ra naam pathantu.",
    "edit.invoice_party_ask_supplier": (
        "Bartaman ra supplier {current}. Nua supplier ra naam pathantu."
    ),
    "edit.amount_invalid": "Daya kari shunyaru bada eka number pathantu, jemiti 1200.",
    "edit.date_invalid": "Daya kari 2026-01-15 pari eka date pathantu.",
    "edit.party_not_found": (
        "Mote '{name}' milila nahin. Spelling jaanch kari puni pathantu, kimba 'cancel'."
    ),
    "edit.value_preview": "{target} ra {field} badalei {new} karibe?",
    "edit.target_invoice": "invoice {number}",
    "edit.target_payment": "invoice {number} ra payment",
    "edit.reason_ask": "{preview}\nKahinki? Eka chota reason pathantu, kimba 'skip'.",
    "edit.confirm_prompt": "{preview}\nConfirm karibaku YES pathantu, kimba cancel karibaku NO.",
    "edit.party_name_ask": (
        "Kauna dealer kimba supplier ra payment edit karibe? Semananka naam pathantu, "
        "kimba 'cancel'."
    ),
    "edit.no_payments_for_party": "{name} paain kono payment milila nahin.",
    "edit.payment_pick_ask": (
        "{name} paain {count} sampratika payments milila:\n{listing}\n"
        "Number pathantu, kimba 'cancel'."
    ),
    "edit.payment_pick_invalid": (
        "Daya kari 1 ru {count} madhyare eka number pathantu, kimba 'cancel'."
    ),
    "edit.payment_gone": (
        "Se payment aau upalabdha nahin. 'edit payment' kahi puni arambha karantu."
    ),
    "edit.field_ask_payment": (
        "Kana edit karibe — amount kimba date? Reply karantu 'amount' kimba 'date'."
    ),
    "edit.field_invalid_payment": "Daya kari reply karantu 'amount' kimba 'date' — kimba 'cancel'.",
    # ── Update GST ─────────────────────────────────────────────────────────
    "gst.scope_prompt": (
        "Sabu products (company default) ra GST update karantu, kimba gotie product ra? "
        "Reply 'all' kimba product naam."
    ),
    "gst.rate_ask_all": "{target} paain natun default GST rate kete? (0-100, kimba 'cancel')",
    "gst.rate_ask_product": (
        "{target} paain natun GST rate kete? (0-100, 'clear' override hatai company default "
        "use karibaku, kimba 'cancel')"
    ),
    "gst.not_found": (
        "'{name}' naam ra product milila nahin. Reply 'all', anya product naam, kimba 'cancel'."
    ),
    "gst.rate_invalid": "Daya kari 0 ru 100 madhyare number pathantu, jaise 18.",
    "gst.all_products": "sabu products",
    "gst.no_override": "kono override nahin (company default use karantu)",
    "gst.rate_pct": "{rate}%",
    "gst.preview": "{target} ra GST {rate_text} set karantu. Reply YES confirm, NO cancel.",
    # ── Product ────────────────────────────────────────────────────────────
    "product.mode_prompt": (
        "Chaluntu products add karantu. Reply 'one by one' gotie gotie, kimba 'bulk' sabu ekathi "
        "puura details saha (jaise Rice, 300, 400, kg, 100, 5). Kebe bi 'done' rokibaku."
    ),
    "product.no_products_added": "OK, kono product add heli nahin.",
    "product.all_done": "Products add kariba sarigala.",
    "product.name_or_done": "Product naam pathantu (jaise Rice), kimba 'done' rokibaku.",
    "product.mode_invalid": (
        "Daya kari reply karantu 'one by one' kimba 'bulk' — kimba 'done' rokibaku."
    ),
    "product.not_found_retry": (
        "'{name}' naam ra product milila nahin. "
        "Spelling check kari puni try karantu, kimba 'cancel'."
    ),
    "product.disambiguation": (
        "'{name}' naam ra {count} products milila:\n{listing}\n"
        "{action} karibaku number reply karantu, kimba 'cancel'."
    ),
    "product.disambiguation_invalid": (
        "Daya kari 1 ru {count} madhyare number reply karantu, kimba 'cancel'."
    ),
    "product.candidate_line": "{index}. {description}",
    "product.candidate_desc": "{name} ({details})",
    "product.candidate_stock": "{stock} stock re",
    "product.gone": (
        "Se product ebe available nahin. Daya kari puni '{trigger}' kahi arambha karantu."
    ),
    "product.delete_name_prompt": "Kaun product delete karibaku? Naam pathantu, kimba 'cancel'.",
    "product.delete_confirm": (
        "{description} delete karibe? Eha undo heba nahin. Reply YES delete, NO cancel."
    ),
    "product.delete_no": "OK, delete heli nahin.",
    "product.delete_confirm_invalid": (
        "Daya kari YES delete paain, kimba NO cancel paain reply karantu."
    ),
    "product.delete_already_gone": "{name} agaru hatai deithila.",
    "product.deleted": "{name} delete hela.",
    "product.field_prompt": (
        "Kana update karibaku — price, purchase price, kimba stock? "
        "Reply 'price', 'purchase price', kimba 'stock'."
    ),
    "product.action_update": "update",
    "product.action_delete": "delete",
    "product.label_price": "price",
    "product.label_purchase": "purchase price",
    "product.label_stock": "stock",
    "product.update_name_prompt": (
        "Kaun product ra {label} update karibaku? Naam pathantu, kimba 'cancel'."
    ),
    "product.current_price": ("{name} ra ebe price {current}. Natun price kete heba? (jaise 450)"),
    "product.current_purchase": (
        "{name} ra ebe purchase price {current}. Natun purchase price kete heba? (jaise 300)"
    ),
    "product.current_stock": ("{name} ra ebe stock {current}. Natun stock kete heba? (jaise 100)"),
    "product.value_invalid": "Daya kari gotie number pathantu, jaise 450.",
    "product.value_nonneg": "Daya kari zero kimba tharu adhika number pathantu.",
    "product.gone_value": "Se product ebe available nahin.",
    "product.not_set": "set nahin",
    "product.updated_price": "{name} ra price {new} kala (aage {old} thila).",
    "product.updated_purchase": "{name} ra purchase price {new} kala (aage {old} thila).",
    "product.updated_stock": "{name} ra stock {new} kala (aage {old} thila).",
    # ── Stock take (bulk stock recount/adjustment) ──────────────────────────
    "stock_take.start_prompt": (
        "Asantu stock take karibaa. Pratyeka product paain, ehara naam pathantu, tapare "
        "nua count (jemiti 40) kimba adjustment (jemiti +15 milila, -3 kharap hela). "
        "Sarile pare 'done' pathantu, kimba jekauna samayare 'cancel'."
    ),
    "stock_take.line_prompt": "Eka product ra naam pathantu, kimba saribaku 'done'.",
    "stock_take.value_ask": (
        "{name} — nua count pathantu (jemiti 40) kimba adjustment (jemiti +15, -3)."
    ),
    "stock_take.value_invalid": "Daya kari eka number pathantu, jemiti 40, +15, kimba -3.",
    "stock_take.line_added": "{name}: {old} → {new}. Parabartee product pathantu, kimba 'done'.",
    "stock_take.nothing_to_apply": "Thik achi, kono paribartana hela nahin.",
    "stock_take.reason_ask": "Kahinki? Eka chota reason pathantu, kimba 'skip'.",
    "stock_take.confirm_prompt": (
        "{summary}\nApply karibaku YES pathantu, kimba cancel karibaku NO."
    ),
    "stock_take.failed": "Stock take apply heli nahin: {error}. Daya kari puni arambha karantu.",
    "stock_take.result_line": "- {name}: {new}",
    "stock_take.success": "✅ {count} product(s) ra stock update hela:\n{lines}{warning}",
    "party.dealer.mode_prompt": (
        "Apanka dealers add karantu. Reply 'one by one' gotie gotie add karibaku, "
        "kimba 'bulk' sabu ekathi pathaibaku (jaise Ram Traders, 9876543210, 15). "
        "Jekaunasi samaya re rahibaku 'done'."
    ),
    "party.dealer.no_added": "Thik achi, kono dealer add hela nahin.",
    "party.dealer.all_done": "Sabu dealers add hoigala.",
    "party.dealer.name_or_done": (
        "Dealer ra naam pathantu (jaise Ram Traders), kimba rahibaku 'done'."
    ),
    "party.dealer.mode_invalid": (
        "Daya kari reply karantu 'one by one' kimba 'bulk' — kimba rahibaku 'done'."
    ),
    "party.supplier.mode_prompt": (
        "Apanka suppliers add karantu. Reply 'one by one' gotie gotie add karibaku, "
        "kimba 'bulk' sabu ekathi pathaibaku (jaise Metro Distributors, 9988776655, 30). "
        "Jekaunasi samaya re rahibaku 'done'."
    ),
    "party.supplier.no_added": "Thik achi, kono supplier add hela nahin.",
    "party.supplier.all_done": "Sabu suppliers add hoigala.",
    "party.supplier.name_or_done": (
        "Supplier ra naam pathantu (jaise Metro Distributors), kimba rahibaku 'done'."
    ),
    "party.supplier.mode_invalid": (
        "Daya kari reply karantu 'one by one' kimba 'bulk' — kimba rahibaku 'done'."
    ),
    # ── Edit dealer / edit supplier (phone, credit limit, terms, GSTIN) ─────
    "party.edit.field_prompt": (
        "Kana edit karibe — phone, credit limit, payment terms, kimba GSTIN? "
        "Reply karantu 'phone', 'credit limit', 'payment terms', kimba 'gstin'."
    ),
    "party.edit.field_invalid": (
        "Daya kari reply karantu 'phone', 'credit limit', 'payment terms', kimba 'gstin' — "
        "kimba 'cancel'."
    ),
    "party.edit.name_ask_dealer": "Kauna dealer? Semananka naam pathantu, kimba 'cancel'.",
    "party.edit.name_ask_supplier": "Kauna supplier? Semananka naam pathantu, kimba 'cancel'.",
    "party.edit.not_found": (
        "Mote '{name}' milila nahin. Spelling jaanch kari puni pathantu, kimba 'cancel'."
    ),
    "party.edit.disambiguation": (
        "'{name}' naam re {count} matches milila:\n{listing}\n"
        "Edit karibaku number pathantu, kimba 'cancel'."
    ),
    "party.edit.disambiguation_invalid": (
        "Daya kari 1 ru {count} madhyare eka number pathantu, kimba 'cancel'."
    ),
    "party.edit.gone": "Se record aau upalabdha nahin. '{trigger}' kahi puni arambha karantu.",
    "party.edit.gone_value": "Se record aau upalabdha nahin.",
    "party.edit.phone_ask": "{name} ra bartaman ra phone {current}. Nua phone kana heba?",
    "party.edit.credit_limit_ask": (
        "{name} ra bartaman ra credit limit {current}. Nua credit limit kana heba? (jemiti 50000)"
    ),
    "party.edit.payment_terms_ask": (
        "{name} ra bartaman ra payment terms {current} days. Nua terms dina re kana heba? "
        "(jemiti 30)"
    ),
    "party.edit.gstin_ask": "{name} ra bartaman ra GSTIN {current}. Nua GSTIN kana heba?",
    "party.edit.days_invalid": "Daya kari dina ra eka purna sankhya pathantu, jemiti 30.",
    "party.edit.gstin_invalid": (
        "Seha thik GSTIN pari lagunahin. Daya kari jaanch kari puni pathantu, kimba 'cancel'."
    ),
    "party.edit.value_preview": "{name} ra {field} badalei {new} karibe?",
    "party.edit.success": "✅ {name} ra {field} {new} hela (purbaru {old} thila).",
    # ── Void payment / void order ───────────────────────────────────────────
    "void.payment_none": "Undo karibaku kono WhatsApp payment milila nahin.",
    "void.payment_preview": (
        "Invoice {invoice_number} paain {party} ra {amount} payment void karibe?"
    ),
    "void.order_none": "Undo karibaku kono WhatsApp order milila nahin.",
    "void.order_has_payment": (
        "Order {invoice_number} re purbaru payment record achi — prathame payment "
        "void karantu, tapare puni cesta karantu."
    ),
    "void.order_preview": "{dealer} ra order {invoice_number} void karibe (total {total})?",
    "void.reason_ask": "{preview}\nKahinki? Eka chota reason pathantu, kimba 'skip'.",
    "void.confirm_prompt": "{preview}\nVoid karibaku YES pathantu, kimba cancel karibaku NO.",
    # ── Pending-operation results ──────────────────────────────────────────
    "pending.reply_yes_no": "Reply YES confirm karibaku kimba NO cancel karibaku.",
    "pending.payment_failed": (
        "Se payment record heli nahin: {error}. Daya kari puni arambha karantu."
    ),
    "pending.payment_success": (
        "✅ {amount} {party} {verb} record hela.\n"
        "Invoices update hela: {invoices}\n"
        "Baki outstanding: {outstanding}"
    ),
    "pending.order_failed": "Se order tiari heli nahin: {error}. Daya kari puni arambha karantu.",
    "pending.order_line": "- {quantity} x {product} = {total}",
    "pending.order_stock_warning": "\n⚠️ Ebe stock negative: {products}",
    "pending.order_pdf_sent": "\nPDF {dealer} ku pathana hela.",
    "pending.order_pdf_not_sent": (
        "\n(PDF {dealer} ku pathana heli nahin — "
        "phone nahin kimba WhatsApp delivery ebe set nahin.)"
    ),
    "pending.order_pdf_sent_to_founder": (
        "\n({dealer} ku sidha pahunchi paridele nahin — PDF upare pathaideli, apana nije "
        "forward karidiantu.)"
    ),
    "pending.order_success": (
        "✅ Order {number} {dealer} paain tiari hela.\n{lines}\n"
        "Subtotal: {subtotal}\nGST: {gst}\nTotal: {total}{warning}{pdf_note}"
    ),
    "pending.gst_failed": "GST update heli nahin: {error}. Daya kari puni arambha karantu.",
    "pending.gst_success": "✅ {target} ra GST {rate} set hela.",
    "pending.gst_rate_default": "company default",
    "pending.void_payment_failed": (
        "Se payment void heli nahin: {error}. Daya kari puni arambha karantu."
    ),
    "pending.void_payment_success": (
        "✅ Invoice {invoice_number} paain {party} ra {amount} payment void hela."
    ),
    "pending.void_order_failed": (
        "Se order void heli nahin: {error}. Daya kari puni arambha karantu."
    ),
    "pending.void_order_success": (
        "✅ {dealer} ra order {invoice_number} void hela (total {total})."
    ),
    "pending.edit_invoice_failed": (
        "Se invoice edit heli nahin: {error}. Daya kari puni arambha karantu."
    ),
    "pending.edit_invoice_success": (
        "✅ Invoice {number} ra {field} {new} hela (purbaru {old} thila)."
    ),
    "pending.edit_payment_failed": (
        "Se payment edit heli nahin: {error}. Daya kari puni arambha karantu."
    ),
    "pending.edit_payment_success": (
        "✅ Invoice {number} ra payment ra {field} {new} hela (purbaru {old} thila)."
    ),
    "pending.unknown": "Se confirmation re kichi bhul heigala. Daya kari puni arambha karantu.",
    # ── Menu prompt / follow-up / notifications / evening ──────────────────
    "menu.prompt": "Reply karantu 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk",
    "followup.message": (
        "📋 Payment Follow-Up\n\n"
        "{number} — {dealer} — {amount}\n"
        "Due date: aji\n\n"
        "Payment milila ki?\n"
        "1. Han — puura amount\n"
        "2. Partial payment\n"
        "3. Ebe janha nahin"
    ),
    "followup.recorded_full": (
        "{amount} payment {dealer} thu record hela.\n"
        "{number} banda hela.\n"
        "Baki: ₹0.\n"
        "Cash au kali ra briefing update hela."
    ),
    "followup.recorded_partial": (
        "{amount} partial payment record hela.\n"
        "{number} — {remaining} ebe baki.\n"
        "Cash au kali ra briefing update hela."
    ),
    "followup.invoice_gone": "Se invoice ebe available nahin. {menu_prompt}",
    "followup.ask_partial": "Kete milila?",
    "followup.ask_expected_date": (
        "{dealer} thu payment kebe expect karanti?\nExample: Friday, 3 days, next week"
    ),
    "followup.confirm_invalid": "Bujhi heli nahin. Reply 1, 2, kimba 3.",
    "followup.amount_invalid": (
        "Se amount bujhi heli nahin. Daya kari gotie number pathantu, jaise 25000."
    ),
    "followup.date_invalid": "Se date bujhi heli nahin.\nExample: Friday, 3 days, next week",
    "followup.rescheduled": (
        "Note karagala. {number} follow-up {when} paain schedule hela.\n"
        "{dealer} kali ra briefing re flag achi."
    ),
    "followup.error": "Se follow-up re kichi bhul heigala. {menu_prompt}",
    "notify.supplier_reminder": (
        "⏰ Payment Reminder\n\n"
        "{supplier} ra {amount} payment {when} due achi.\n"
        "{cash_line}\n"
        "Kono action darkar nahin jabaju cash position na badle."
    ),
    "notify.when_today": "aji",
    "notify.when_tomorrow": "kali",
    "notify.cash_line": "Ebe available cash: {amount} — {sufficiency}",
    "notify.cash_sufficient": "jathesta achi.",
    "notify.cash_insufficient": "kami padipare.",
    # ── Supplier-reminder payment confirmation ──────────────────────────────
    "reminder_confirm.ask_paid": (
        "Apana {supplier} ku {amount} pay kari sarile ki?\n"
        "Reply 1 jadi han, 2 jadi ebe paryanta nahin."
    ),
    "reminder_confirm.invalid_choice": (
        "Daya kari reply 1 karantu jadi pay kari sarile, kimba 2 jadi nahin."
    ),
    "reminder_confirm.amount_ask": (
        "Pay kari thiba amount confirm karantu: {amount}. Badalibaku alaga number reply "
        "karantu, kimba 'ok' confirm karibaku."
    ),
    "reminder_confirm.amount_invalid": "Daya kari gotie amount pathantu, jaise 25000.",
    "reminder_confirm.amount_positive": "Daya kari zero tharu adhika amount pathantu.",
    "reminder_confirm.reschedule_ask": (
        "Thik achi — e reminder ku reschedule karibaku natun date reply karantu (jaise "
        "'tomorrow', 'next week', '3 days'), kimba 'skip' jadi ebe bhi due rakhibaku achi — "
        "mun punibi yaad karaibi."
    ),
    "reminder_confirm.reschedule_invalid": (
        "Se date bujhi heli nahin. Try 'tomorrow', 'next week', '3 days' — kimba 'skip'."
    ),
    "reminder_confirm.rescheduled": (
        "Thik achi — {supplier} ra payment ebe {date} re due achi. Se samay paakhare punibi "
        "yaad karaibi."
    ),
    "reminder_confirm.kept_due": "Thik achi, mun punibi yaad karaibi.",
    "reminder_confirm.invoice_gone": "Se bill ebe open nahin — reschedule karibara darkar nahin.",
    "notify.dealer_alert": (
        "⚠ Collection Alert\n\n"
        "{dealer} — {amount} — ebe {days} dina overdue.\n"
        "3 dina ru kono follow-up nahin.\n"
        "Suggestion: natun order dei aage aji call karantu."
    ),
    "evening.header": "🌙 Sanjha Business Summary",
    "evening.counts": (
        "Invoices tiari: {invoices} · WhatsApp ru Orders: {orders} · Payments record: {payments}"
    ),
    "evening.sales": "Aji ra Sales: {amount}",
    "evening.margin": "Sales Margin: {amount}",
    "evening.margin_excluded": " ({items} items, {amount} exclude — cost price nahin)",
    "evening.collections": "Collections: {amount}",
    "evening.supplier_payments": "Supplier Payments: {amount}",
    "evening.net_cash": "Net Cash Movement: {amount}",
    "evening.outstanding": "Outstanding Receivables: {amount}",
    "evening.priority_header": "Priority Actions:",
}
