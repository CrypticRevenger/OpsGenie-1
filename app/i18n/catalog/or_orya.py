"""Odia (Odia script) message catalog.

DRAFT — needs a native Odia speaker's review before production go-live.
Widely-used English business terms/acronyms (GST, Excel, FAQ) are kept as-is,
matching real Odia WhatsApp business chat. Mirrors the exact keys in en.py
(enforced by tests/test_i18n.py); English is the safe fallback for any key
missing here.
"""

from __future__ import annotations

# Full "help" block — DRAFT. Command keywords stay English (literal triggers);
# only prose/descriptions are Odia.
_HELP_TEXT = """*OpsGenie Help*

*ନଗଦ ଓ ସାରାଂଶ*
• cash / cash position — ବର୍ତ୍ତମାନ ନଗଦ, 7-ଦିନ ଇନ୍/ଆଉଟ୍, ନେଟ୍ ପୋଜିସନ୍ (କିମ୍ବା 1 / /cash)
• summary / business summary — ନଗଦ, ନେଟ୍ ପୋଜିସନ୍, 7-ଦିନ କଲେକ୍ସନ/ପେମେଣ୍ଟ, ଓଭରଡ୍ୟୁ ଡିଲର
• priorities / what should I do — ମୁଖ୍ୟ କାମ: ନଗଦ ଚେତାବନୀ, କାହାକୁ କଲ୍, ସପ୍ଲାୟର ବାକି

*ଡିଲର (ଯେଉଁମାନେ ଆପଣଙ୍କୁ ଦିଅନ୍ତି)*
• dealers / all dealers — ପ୍ରତ୍ୟେକ ଡିଲର ଫୋନ୍ ଓ ବାକି ସହ
• top debtors / who owes most — ସବୁଠୁ ଅଧିକ ବାକି ଥିବା ଡିଲର
• overdue / overdue dealers — କେତେ ଦିନ ବିଳମ୍ବ ଓ ରିସ୍କ ଲେଭଲ୍ (କିମ୍ବା 4 / /dealer_risk)
• balance <name> — ଗୋଟିଏ ଡିଲରର ବାକି, ଯେମିତି balance Ram Traders
• add dealer (କିମ୍ବା /add_dealer) — ନୂଆ dealer add କରନ୍ତୁ: ନାମ, ଫୋନ୍, credit ଦିନ
• edit dealer (କିମ୍ବା /edit_dealer) — dealer ର phone, credit limit, terms, କିମ୍ବା GSTIN ବଦଳାନ୍ତୁ

*ସପ୍ଲାୟର (ଯେଉଁମାନଙ୍କୁ ଆପଣ ଦିଅନ୍ତି)*
• suppliers / all suppliers — ପ୍ରତ୍ୟେକ ସପ୍ଲାୟର ଫୋନ୍ ଓ ବାକି ସହ
• top creditors — ଯେଉଁମାନଙ୍କୁ ଆପଣ ସବୁଠୁ ଅଧିକ ଦିଅନ୍ତି
• balance <name> — ଗୋଟିଏ ସପ୍ଲାୟରର ବାକି
• add supplier (କିମ୍ବା /add_supplier) — ନୂଆ supplier add କରନ୍ତୁ: ନାମ, ଫୋନ୍, credit ଦିନ
• edit supplier (କିମ୍ବା /edit_supplier) — supplier ର phone, credit limit, terms, କିମ୍ବା GSTIN ବଦଳାନ୍ତୁ

*ଆସୁଥିବା କ୍ୟାସ ଫ୍ଲୋ*
• collections / upcoming collections — ଡିଲରଙ୍କଠାରୁ ଆସିବ, ଆସନ୍ତା 7 ଦିନ (କିମ୍ବା 2 / /collections)
• payments / upcoming payments — ସପ୍ଲାୟରଙ୍କୁ ଦେବା, ଆସନ୍ତା 7 ଦିନ (କିମ୍ବା 3 / /suppliers)

*ଇନଭେଣ୍ଟୋରୀ*
• inventory / products / stock — ନୂଆ ଯୋଡ଼ାଯାଇଥିବା ପ୍ରୋଡକ୍ଟ (ଷ୍ଟକ୍ qty, ବିକ୍ରୟ ମୂଲ୍ୟ)
• all inventory — ପ୍ରତ୍ୟେକ ପ୍ରୋଡକ୍ଟ, କେବଳ ନୂଆ ନୁହେଁ
• stock <product> — ଗୋଟିଏ ଆଇଟମ୍ ଚେକ୍ କରନ୍ତୁ, ଯେମିତି stock Rice

*ଟ୍ରାଞ୍ଜାକ୍ସନ୍*
• invoices / recent invoices — ନୂଆ ଇନଭଏସ୍ (number, party, total, status, dates)
• all invoices — ପ୍ରତ୍ୟେକ ଇନଭଏସ୍, କେବଳ ନୂଆ ନୁହେଁ
• payments / recent payments — ନୂଆ ରେକର୍ଡ ପେମେଣ୍ଟ
• all payments / all time payments — ପ୍ରତ୍ୟେକ ପେମେଣ୍ଟ, କେବଳ ନୂଆ ନୁହେଁ
• faq / policy — ଆପଣଙ୍କ ସେଭ୍ ହୋଇଥିବା ବ୍ୟବସାୟ ନୀତି (delivery days, returns, minimum order)

*ପ୍ରୋଡକ୍ଟ ପରିଚାଳନା* (guided, ଗୋଟିଏ ଗୋଟିଏ ପ୍ରଶ୍ନ)
• add product (କିମ୍ବା /add_product) — ନୂଆ ଆଇଟମ୍: name, stock, unit, ବିକ୍ରୟ ମୂଲ୍ୟ, କ୍ରୟ ମୂଲ୍ୟ
• update stock (କିମ୍ବା /update_stock) — ପ୍ରୋଡକ୍ଟର ଷ୍ଟକ୍ ବଦଳାନ୍ତୁ
• update price (କିମ୍ବା /update_price) — ପ୍ରୋଡକ୍ଟର ବିକ୍ରୟ ମୂଲ୍ୟ ବଦଳାନ୍ତୁ
• update purchase price (କିମ୍ବା /update_purchase_price) — ସପ୍ଲାୟରଙ୍କୁ ଯାହା ଦିଅନ୍ତି ତାହା ବଦଳାନ୍ତୁ
• update product (କିମ୍ବା /update_product) — ମୂଲ୍ୟ, କ୍ରୟ ମୂଲ୍ୟ, କିମ୍ବା ଷ୍ଟକ୍ ବାଛନ୍ତୁ
• update gst (କିମ୍ବା /update_gst) — ସମସ୍ତ କିମ୍ବା ଗୋଟିଏ ପ୍ରୋଡକ୍ଟର GST ବଦଳାନ୍ତୁ
• delete product (କିମ୍ବା /delete_product) — catalogue ରୁ ଆଇଟମ୍ ହଟାନ୍ତୁ
• stock take (କିମ୍ବା /stock_take) — ଅନେକ ପ୍ରୋଡକ୍ଟର stock ଏକାଠି recount କିମ୍ବା adjust କରନ୍ତୁ

*ଅର୍ଡର ଓ ପେମେଣ୍ଟ*
• new order (କିମ୍ବା /create_order, କିମ୍ବା "new invoice") — ଡିଲରକୁ ସେଲ ରେକର୍ଡ କରନ୍ତୁ
• record payment (କିମ୍ବା /record_payment) — ଡିଲରଠାରୁ ଆସିଥିବା କିମ୍ବା ସପ୍ଲାୟରକୁ ଦେଇଥିବା ପେମେଣ୍ଟ ଲଗ୍

*ସୁଧାର (Corrections)*
• undo payment (କିମ୍ବା /undo_payment) — ଏବେ record କରିଥିବା payment void କରନ୍ତୁ
• undo order (କିମ୍ବା /undo_order) — ଏବେ ତିଆରି କରିଥିବା order void କରନ୍ତୁ (ଯଦି unpaid ଅଛି)
• edit invoice (କିମ୍ବା /edit_invoice) — invoice ର amount, date, କିମ୍ବା party ସୁଧାରନ୍ତୁ (unpaid ଉପରେ)
• edit payment (କିମ୍ବା /edit_payment) — ରେକର୍ଡ ହୋଇଥିବା payment ର amount କିମ୍ବା date ସୁଧାରନ୍ତୁ

*ଆପଣଙ୍କ ଡାଟା*
• export data (କିମ୍ବା /export_data) — ପୂରା ବ୍ୟବସାୟ ଡାଟା Excel ରେ download link
• morning briefing (କିମ୍ବା /morning_briefing) — ଆଜିର ବ୍ରିଫିଂ ପୁଣି ପଠାନ୍ତୁ

*ରିପୋର୍ଟ ଓ ଷ୍ଟେଟମେଣ୍ଟ* (ଏହି ମାସର, Excel + PDF ଯେଉଁଠି କୁହାଯାଇଛି)
• ledger <name> — ଏକ ଡିଲର/ସପ୍ଲାୟରର running-balance ଷ୍ଟେଟମେଣ୍ଟ, Excel + PDF, ଯେମିତି ledger Ram Traders
• sales register / purchase register (କିମ୍ବା ଉଭୟ ପାଇଁ "gst report") — GST register, rate-wise summary ସହ
• payment register (କିମ୍ବା receipt register) — ଏହି ମାସର receipts ଓ payments
• day book — ଏହି ମାସର ସବୁ invoice ଓ payment, ଏକ ତାଲିକାରେ
• outstanding report (କିମ୍ବା aging report) — 0-30/31-60/61-90/90+ ଦିନ bucket, Excel + PDF

*Quick Access*
• menu — ଟାଇପ୍ କରିବା ବଦଳରେ option tap କରନ୍ତୁ
• help (କିମ୍ବା /help) — ଏହି ତାଲିକା ଯେକୌଣସି ସମୟରେ ପୁଣି ଦେଖନ୍ତୁ"""

MESSAGES: dict[str, str] = {
    # ── Errors / fallbacks ────────────────────────────────────────────────
    "errors.something_wrong": "କିଛି ଭୁଲ୍ ହୋଇଗଲା। ଦୟାକରି ପୁଣି ଚେଷ୍ଟା କରନ୍ତୁ।",
    "errors.assistant_fallback": (
        "କ୍ଷମା କରନ୍ତୁ, ମୁଁ ବର୍ତ୍ତମାନ ଏହାର ଉତ୍ତର ଦେଇପାରିଲି ନାହିଁ। ଉତ୍ତର ଦିଅନ୍ତୁ 1 Cash · "
        "2 Collections · 3 Suppliers · 4 Dealer Risk, କିମ୍ବା ପୁଣି ଲେଖନ୍ତୁ।"
    ),
    "onboarding.language_changed": (
        "✅ ହୋଇଗଲା — ବର୍ତ୍ତମାନଠାରୁ ମୁଁ ଆପଣଙ୍କୁ {language} ରେ ମେସେଜ୍ କରିବି।"
    ),
    # ── Cash Position report ───────────────────────────────────────────────
    "reports.cash.header": "💰 ନଗଦ ସ୍ଥିତି",
    "reports.cash.available_now": "ବର୍ତ୍ତମାନ ଉପଲବ୍ଧ: {amount}",
    "reports.cash.expected_in": "ଆସିବ (7 ଦିନ): {amount}",
    "reports.cash.due_out": "ଦେବାକୁ ଅଛି (7 ଦିନ): {amount}",
    "reports.cash.net_expected": "ନେଟ୍ ଆଶାୟୀ: {amount}",
    "reports.cash.shortage": "ଏହି ସପ୍ତାହରେ ନଗଦ ଅଭାବ ହୋଇପାରେ।",
    "reports.cash.no_shortage": "ଏହି ସପ୍ତାହରେ ନଗଦ ଅଭାବ ହେବନାହିଁ।",
    # ── Collections report ─────────────────────────────────────────────────
    "reports.collections.header": "📥 ବାକି ସଂଗ୍ରହ",
    "reports.collections.none": "ଆସନ୍ତା 7 ଦିନରେ କୌଣସି ସଂଗ୍ରହ ଆସିବ ନାହିଁ।",
    "reports.collections.total": "ଏହି ସପ୍ତାହରେ ମୋଟ ଆଶାୟୀ: {amount}",
    # ── Supplier payments report ───────────────────────────────────────────
    "reports.suppliers.header": "📤 ସପ୍ଲାୟର ପେମେଣ୍ଟ ବାକି",
    "reports.suppliers.none": "ଆସନ୍ତା 7 ଦିନରେ କୌଣସି ସପ୍ଲାୟର ପେମେଣ୍ଟ ବାକି ନାହିଁ।",
    "reports.suppliers.total": "ଏହି ସପ୍ତାହରେ ମୋଟ ଦେବା: {amount}",
    "reports.suppliers.cash_ok": "ନଗଦ ଯଥେଷ୍ଟ ଅଛି",
    "reports.suppliers.cash_short": "ନଗଦ କମ ପଡ଼ିପାରେ",
    # ── Dealer risk report ─────────────────────────────────────────────────
    "reports.risk.header": "⚠ ଡିଲର ରିସ୍କ ସାରାଂଶ",
    "reports.risk.none": "ବର୍ତ୍ତମାନ କୌଣସି ଓଭରଡ୍ୟୁ ଡିଲର ନାହିଁ।",
    "reports.risk.high": "ଉଚ୍ଚ ରିସ୍କ:",
    "reports.risk.medium": "ମଧ୍ୟମ ରିସ୍କ:",
    "reports.risk.low": "ନିମ୍ନ ରିସ୍କ:",
    "reports.risk.dealer_line": "{name} — {amount} ଓଭରଡ୍ୟୁ ({days}d) — {late}",
    # ── Shared phrases ─────────────────────────────────────────────────────
    "reports.due.today": "ଆଜି ଦେୟ",
    "reports.due.weekday": "{day} ରେ ଦେୟ",
    "reports.due.date": "{date} ରେ ଦେୟ",
    "reports.late.none": "ସମୟରେ ପେମେଣ୍ଟ କରେ",
    "reports.late.one": "6 ମାସରେ 1 ଲେଟ ପେମେଣ୍ଟ",
    "reports.late.many": "6 ମାସରେ {count} ଲେଟ ପେମେଣ୍ଟ",
    # ── Business summary ───────────────────────────────────────────────────
    "reports.summary.header": "📊 ବ୍ୟବସାୟ ସାରାଂଶ",
    "reports.summary.cash_now": "ବର୍ତ୍ତମାନ ଉପଲବ୍ଧ ନଗଦ: {amount}",
    "reports.summary.net_7d": "ନେଟ୍ ନଗଦ ପୋଜିସନ୍ (7d): {amount}",
    "reports.summary.expected_in": "ଆସିବ (7d): {amount}",
    "reports.summary.expected_out": "ଯିବ (7d): {amount}",
    "reports.summary.shortage": "ଏହି ସପ୍ତାହରେ ନଗଦ ଅଭାବ ହୋଇପାରେ।",
    "reports.summary.no_shortage": "ନଗଦ ଅଭାବ ହେବନାହିଁ।",
    "reports.summary.overdue_count": "ଓଭରଡ୍ୟୁ ଡିଲର: {count}",
    "reports.summary.overdue_hint": " — ବିବରଣୀ ପାଇଁ 'overdue' ପଠାନ୍ତୁ।",
    # ── Priorities ─────────────────────────────────────────────────────────
    "reports.priorities.none": "🎯 ବର୍ତ୍ତମାନ କିଛି ଜରୁରୀ ନାହିଁ — କୌଣସି ପ୍ରାଥମିକତା ନାହିଁ।",
    "reports.priorities.header": "🎯 ପ୍ରାଥମିକତା",
    # ── Dealer / supplier lists ────────────────────────────────────────────
    "reports.dealers.none": "ଆପଣଙ୍କ ପାଖରେ ବର୍ତ୍ତମାନ କୌଣସି ଡିଲର ନାହିଁ।",
    "reports.dealers.header": "👥 ଡିଲର ({count}):",
    "reports.suppliers_list.none": "ଆପଣଙ୍କ ପାଖରେ ବର୍ତ୍ତମାନ କୌଣସି ସପ୍ଲାୟର ନାହିଁ।",
    "reports.suppliers_list.header": "🚚 ସପ୍ଲାୟର ({count}):",
    "reports.party.no_phone": "ଫୋନ୍ ନାହିଁ",
    "reports.party.line": "{name} — {phone} — ବାକି {amount}",
    "reports.top_debtors.none": "ବର୍ତ୍ତମାନ କୌଣସି ଡିଲର ପାଖରେ ଆପଣଙ୍କ କିଛି ବାକି ନାହିଁ।",
    "reports.top_debtors.header": "💰 ଟପ୍ ଦେନଦାର",
    "reports.top_creditors.none": "ବର୍ତ୍ତମାନ ଆପଣ କୌଣସି ସପ୍ଲାୟରକୁ କିଛି ଦିଅନ୍ତି ନାହିଁ।",
    "reports.top_creditors.header": "💸 ଟପ୍ ଲେନଦାର",
    # ── Inventory ──────────────────────────────────────────────────────────
    "reports.inventory.none": "ଆପଣଙ୍କ catalogue ରେ ବର୍ତ୍ତମାନ କୌଣସି ପ୍ରୋଡକ୍ଟ ନାହିଁ।",
    "reports.inventory.label_recent": "ସାମ୍ପ୍ରତିକ ଇନଭେଣ୍ଟୋରୀ",
    "reports.inventory.label_all": "ସମସ୍ତ ଇନଭେଣ୍ଟୋରୀ",
    "reports.inventory.header_partial": "📦 {label} ({count} of {total}):",
    "reports.inventory.header_full": "📦 {label} ({count}):",
    "reports.inventory.more": (
        "\n\n…ଆଉ {remaining} ଅଧିକ — ପୂରା ତାଲିକା ପାଇଁ 'all inventory' ପଠାନ୍ତୁ।"
    ),
    "reports.product.price_not_set": "ମୂଲ୍ୟ ସେଟ୍ ନାହିଁ",
    # ── FAQs ───────────────────────────────────────────────────────────────
    "reports.faq.none": "ଆପଣଙ୍କ ପାଖରେ ବର୍ତ୍ତମାନ କୌଣସି ସେଭ୍ ପଲିସି ନାହିଁ।",
    "reports.faq.header": "❓ FAQs ({count}):",
    "reports.faq.qa": "Q: {question}\nA: {answer}",
    # ── Invoices ───────────────────────────────────────────────────────────
    "reports.invoices.none": "ଆପଣଙ୍କ ପାଖରେ ବର୍ତ୍ତମାନ କୌଣସି ଇନଭଏସ୍ ନାହିଁ।",
    "reports.invoices.label_recent": "ସାମ୍ପ୍ରତିକ ଇନଭଏସ୍",
    "reports.invoices.label_all": "ସମସ୍ତ ଇନଭଏସ୍",
    "reports.invoices.header_partial": "📄 {label} ({count} of {total}):",
    "reports.invoices.header_full": "📄 {label} ({count}):",
    "reports.invoices.more": "\n\n…ଆଉ {remaining} ଅଧିକ — ପୂରା ତାଲିକା ପାଇଁ 'all invoices' ପଠାନ୍ତୁ।",
    "reports.invoices.line": "{number} — {party} — {amount} — {status} — {due}",
    "reports.unknown_party": "ଅଜ୍ଞାତ party",
    # ── Payments ───────────────────────────────────────────────────────────
    "reports.payments.none": "ଆପଣଙ୍କ ପାଖରେ ବର୍ତ୍ତମାନ କୌଣସି ପେମେଣ୍ଟ ରେକର୍ଡ ନାହିଁ।",
    "reports.payments.label_recent": "ସାମ୍ପ୍ରତିକ ପେମେଣ୍ଟ",
    "reports.payments.label_all": "ସମସ୍ତ ପେମେଣ୍ଟ",
    "reports.payments.header_partial": "💵 {label} ({count} of {total}):",
    "reports.payments.header_full": "💵 {label} ({count}):",
    "reports.payments.more": "\n\n…ଆଉ {remaining} ଅଧିକ — ପୂରା ତାଲିକା ପାଇଁ 'all payments' ପଠାନ୍ତୁ।",
    "reports.payments.from": "ଠାରୁ",
    "reports.payments.to": "କୁ",
    "reports.payments.line": "{amount} — invoice {number} {direction} — {date}",
    # ── Party balance ──────────────────────────────────────────────────────
    "reports.balance.dealer_owes": "{party} ଆପଣଙ୍କୁ {amount} ଦେବା ଅଛି।",
    "reports.balance.you_owe": "ଆପଣ {party} କୁ {amount} ଦେବା ଅଛି।",
    # ── Stock item ─────────────────────────────────────────────────────────
    "reports.stock.not_found": "'{name}' ସହ ମିଳୁଥିବା କୌଣସି ପ୍ରୋଡକ୍ଟ ମିଳିଲା ନାହିଁ।",
    "reports.stock.line": "{name} — {stock} ଷ୍ଟକ୍ ରେ — {price}",
    # ── Sales impact ───────────────────────────────────────────────────────
    "reports.sales.revenue": "revenue {amount}",
    "reports.sales.profit": "profit {amount}",
    "reports.sales.left": "{qty} ଷ୍ଟକ୍ ରେ ବାକି",
    "reports.sales.total_revenue": "Total revenue: {amount}",
    "reports.sales.total_profit": "Total profit: {amount}",
    "reports.sales.no_cost": "({missing} ର କ୍ରୟ ମୂଲ୍ୟ ନାହିଁ — profit ରୁ ବାଦ)",
    # ── Excel export link ──────────────────────────────────────────────────
    "reports.export.not_configured": (
        "Data export link ବର୍ତ୍ତମାନ setup ନାହିଁ — ନିଜ OpsGenie admin ଙ୍କୁ configure କରାନ୍ତୁ।"
    ),
    "reports.export.ready": (
        "ଆପଣଙ୍କ latest Excel export ପ୍ରସ୍ତୁତ।\nDownload ({ttl} min valid): {link}"
    ),
    "reports.download.ready": (
        "ଆପଣଙ୍କ {report_name} ({period}) ପ୍ରସ୍ତୁତ।\nDownload ({ttl} min valid):\n{links}"
    ),
    "reports.ledger.not_found": "'{name}' ସହ ମିଳୁଥିବା କୌଣସି ଡିଲର କିମ୍ବା ସପ୍ଲାୟର ମିଳିଲା ନାହିଁ।",
    # ── Help text ──────────────────────────────────────────────────────────
    "menu.help_text": _HELP_TEXT,
    # ── Onboarding ─────────────────────────────────────────────────────────
    "onboarding.intro": (
        "👋 OpsGenie କୁ ସ୍ୱାଗତ! ଚାଲନ୍ତୁ ଆପଣଙ୍କ ବ୍ୟବସାୟ ସେଟ୍ ଅପ୍ କରିବା — 5 ମିନିଟ୍ ଲାଗିବ, "
        "ଏବଂ ଆପଣ ଯେକୌଣସି ସମୟରେ ରୋକି ଜାରି ରଖିପାରିବେ।\n\n"
        "ପ୍ରଥମେ: ଆପଣ କେଉଁ ପ୍ରକାରର ବ୍ୟବସାୟ ଚଳାନ୍ତି? (ଯେମିତି FMCG Distributor, Pharma Distributor)"
    ),
    "onboarding.progress": "✅ Step {step}/{total} ହୋଇଗଲା।",
    "onboarding.finish": (
        "🎉 ସେଟ୍ ଅପ୍ ସମ୍ପୂର୍ଣ୍ଣ ହୋଇଗଲା!\n\n"
        "କାଲି ସକାଳୁ ମୁଁ ଆପଣଙ୍କୁ ପ୍ରତିଦିନ ବ୍ରିଫିଂ ପଠାଇବି। ଆପଣ ମୋତେ କିଛି ବି ପଚାରି ପାରିବେ, ଯେମିତି:\n"
        "• Cash position\n"
        "• Ram କୁ କେତେ ଦେବା?\n"
        "• Supplier dues\n"
        "• Dealer risk\n\n"
        "ଯେକୌଣସି ସମୟରେ menu ପଠାନ୍ତୁ option tap କରିବାକୁ, କିମ୍ବା /help ପୂରା ତାଲିକା ଦେଖିବାକୁ।"
    ),
    "onboarding.gst.mode_ask": (
        "ଆପଣଙ୍କ ସବୁ products ର GST rate same କି, କିମ୍ବା product ହିସାବରେ ଅଲଗା? "
        "Reply କରନ୍ତୁ 'same', 'varies', କିମ୍ବା 'not sure' ପରେ ଠିକ୍ କରିବାକୁ।"
    ),
    "onboarding.gst.rate_ask": "ଆପଣଙ୍କ GST rate କେତେ? (ଯେମିତି 5, 12, 18, କିମ୍ବା 0 ଯଦି exempt)",
    "onboarding.gst.mode_invalid": "ଦୟାକରି reply କରନ୍ତୁ 'same', 'varies', କିମ୍ବା 'not sure'।",
    "onboarding.gst.rate_invalid": (
        "ଦୟାକରି 0 ରୁ 100 ମଧ୍ୟରେ number ପଠାନ୍ତୁ, ଯେମିତି 18 (କିମ୍ବା 'not sure' ପରେ ଠିକ୍ କରିବାକୁ)।"
    ),
    "onboarding.product.intro": (
        "ଏବେ ଆପଣଙ୍କ products add କରନ୍ତୁ। Reply 'one by one' ଗୋଟିଏ ଗୋଟିଏ, କିମ୍ବା 'bulk' ସବୁ ଏକାଠି "
        "ପୂରା details ସହ (ଯେମିତି Rice, 300, 400, kg, 100, 5)। 'done' skip କରିବାକୁ।"
    ),
    "onboarding.product.bulk_format": (
        "ଆପଣଙ୍କ products ଗୋଟିଏ line ରେ ଗୋଟିଏ, ଏହି format ରେ ପଠାନ୍ତୁ:\n"
        "Name, Purchase Price, Selling Price, Unit, Stock, GST%\n"
        "ଯେମିତି\n"
        "Rice, 300, 400, kg, 100, 5\n"
        "Dal, 320, 450, kg, 50, 12\n"
        "ଯେଉଁ field set କରିବାକୁ ଚାହାନ୍ତି ନାହିଁ ସେଥିପାଇଁ 'skip' ଲେଖନ୍ତୁ "
        "(ଯେମିତି Rice, skip, 400, kg, 100, skip)। ସରିଲେ 'done' ପଠାନ୍ତୁ।"
    ),
    "onboarding.product.bulk_format_no_gst": (
        "ଆପଣଙ୍କ products ଗୋଟିଏ line ରେ ଗୋଟିଏ, ଏହି format ରେ ପଠାନ୍ତୁ:\n"
        "Name, Purchase Price, Selling Price, Unit, Stock\n"
        "ଯେମିତି\n"
        "Rice, 300, 400, kg, 100\n"
        "Dal, 320, 450, kg, 50\n"
        "ଯେଉଁ field set କରିବାକୁ ଚାହାନ୍ତି ନାହିଁ ସେଥିପାଇଁ 'skip' ଲେଖନ୍ତୁ "
        "(ଯେମିତି Rice, skip, 400, kg, 100)। ସରିଲେ 'done' ପଠାନ୍ତୁ।"
    ),
    "onboarding.product.first_name": (
        "ଆପଣଙ୍କ ପ୍ରଥମ product ର ନାମ ପଠାନ୍ତୁ (ଯେମିତି Rice), କିମ୍ବା 'done' skip କରିବାକୁ।"
    ),
    "onboarding.product.mode_invalid": (
        "ଦୟାକରି reply କରନ୍ତୁ 'one by one' କିମ୍ବା 'bulk' — କିମ୍ବା 'done' products skip କରିବାକୁ।"
    ),
    "onboarding.product.bulk_added": (
        "{count} product add ହେଲା: {names}। ଆଉ ପଠାନ୍ତୁ, କିମ୍ବା ସରିଲେ 'done' ପଠାନ୍ତୁ।"
    ),
    "onboarding.product.quantity_ask": (
        "ଏବେ ଆପଣଙ୍କ ପାଖରେ କେତେ {name} stock ରେ ଅଛି? (ଯେମିତି 100, କିମ୍ବା 'skip')"
    ),
    "onboarding.product.quantity_invalid": (
        "ଦୟାକରି ଗୋଟିଏ number ପଠାନ୍ତୁ, ଯେମିତି 100 (କିମ୍ବା 'skip')।"
    ),
    "onboarding.product.unit": "ଏହା କେଉଁ unit ରେ? (ଯେମିତି kg, pcs, box, litre, କିମ୍ବା 'skip')",
    "onboarding.product.price_ask": "{name} ର selling price କେତେ? (ଯେମିତି 400, କିମ୍ବା 'skip')",
    "onboarding.product.price_invalid": "ଦୟାକରି ଗୋଟିଏ number ପଠାନ୍ତୁ, ଯେମିତି 400 (କିମ୍ବା 'skip')।",
    "onboarding.product.purchase_ask": (
        "{name} ର purchase price (cost price) କେତେ? (ଯେମିତି 300, କିମ୍ବା 'skip')"
    ),
    "onboarding.product.purchase_invalid": (
        "ଦୟାକରି ଗୋଟିଏ number ପଠାନ୍ତୁ, ଯେମିତି 300 (କିମ୍ବା 'skip')।"
    ),
    "onboarding.product.gst_ask": (
        "{name} ର GST% କେତେ? (ଯେମିତି 5, 12, 18, କିମ୍ବା 'skip' ପରେ ଠିକ୍ କରିବାକୁ)"
    ),
    "onboarding.product.gst_invalid": (
        "ଦୟାକରି 0 ରୁ 100 ମଧ୍ୟରେ number ପଠାନ୍ତୁ, ଯେମିତି 18 (କିମ୍ବା 'skip' ପରେ ଠିକ୍ କରିବାକୁ)।"
    ),
    "onboarding.product.added": (
        "Product add ହେଲା: {name} ({stock} stock ରେ)। ଆଉ ପଠାନ୍ତୁ, କିମ୍ବା 'done'।"
    ),
    "onboarding.dealers.intro": (
        "ଏବେ ଆପଣଙ୍କ dealers (customers) add କରନ୍ତୁ। Reply 'one by one' ଗୋଟିଏ ଗୋଟିଏ add କରିବାକୁ, "
        "କିମ୍ବା 'bulk' ସବୁ ଏକାଠି ପଠାଇବାକୁ (ଯେମିତି Ram Traders, 9876543210, 15)। "
        "'done' skip କରିବାକୁ।"
    ),
    "onboarding.dealer.bulk_format": (
        "ଆପଣଙ୍କ dealers ଗୋଟିଏ line ରେ ଗୋଟିଏ, ଏହି format ରେ ପଠାନ୍ତୁ:\n"
        "Name, Phone, Credit Days\n"
        "ଯେମିତି\n"
        "Ram Traders, 9876543210, 15\n"
        "Shree Enterprises, 9123456780, 30\n"
        "ଯେଉଁ field set କରିବାକୁ ଚାହାନ୍ତି ନାହିଁ ସେଥିପାଇଁ 'skip' ଲେଖନ୍ତୁ "
        "(ଯେମିତି Ram Traders, skip, 15)। ସରିଲେ 'done' ପଠାନ୍ତୁ।"
    ),
    "onboarding.dealer.first_name": (
        "ଆପଣଙ୍କ ପ୍ରଥମ dealer ର ନାମ ପଠାନ୍ତୁ (ଯେମିତି Ram Traders), କିମ୍ବା 'done' skip କରିବାକୁ।"
    ),
    "onboarding.dealer.mode_invalid": (
        "ଦୟାକରି reply କରନ୍ତୁ 'one by one' କିମ୍ବା 'bulk' — କିମ୍ବା 'done' dealers skip କରିବାକୁ।"
    ),
    "onboarding.dealer.bulk_added": (
        "{count} dealer add ହେଲା: {names}। ଆଉ ପଠାନ୍ତୁ, କିମ୍ବା ସରିଲେ 'done' ପଠାନ୍ତୁ।"
    ),
    "onboarding.dealer.credit_ask": (
        "{name} କୁ ଆପଣ କେତେ credit ଦିନ ଦିଅନ୍ତି? (ଯେମିତି 15, କିମ୍ବା 'skip')"
    ),
    "onboarding.dealer.added": "Dealer {name} add ହେଲା। ପରବର୍ତ୍ତୀ dealer ର ନାମ, କିମ୍ବା 'done'।",
    "onboarding.suppliers.intro": (
        "ଏବେ ଆପଣଙ୍କ suppliers। Reply 'one by one' ଗୋଟିଏ ଗୋଟିଏ add କରିବାକୁ, "
        "କିମ୍ବା 'bulk' ସବୁ ଏକାଠି ପଠାଇବାକୁ (ଯେମିତି Metro Distributors, 9988776655, 30)। "
        "'done' skip କରିବାକୁ।"
    ),
    "onboarding.supplier.bulk_format": (
        "ଆପଣଙ୍କ suppliers ଗୋଟିଏ line ରେ ଗୋଟିଏ, ଏହି format ରେ ପଠାନ୍ତୁ:\n"
        "Name, Phone, Credit Days\n"
        "ଯେମିତି\n"
        "Metro Distributors, 9988776655, 30\n"
        "Suresh Wholesale, 9871234560, 15\n"
        "ଯେଉଁ field set କରିବାକୁ ଚାହାନ୍ତି ନାହିଁ ସେଥିପାଇଁ 'skip' ଲେଖନ୍ତୁ "
        "(ଯେମିତି Metro Distributors, skip, 30)। ସରିଲେ 'done' ପଠାନ୍ତୁ।"
    ),
    "onboarding.supplier.first_name": (
        "ଆପଣଙ୍କ ପ୍ରଥମ supplier ର ନାମ ପଠାନ୍ତୁ (ଯେମିତି Metro Distributors), କିମ୍ବା 'done' skip କରିବାକୁ।"
    ),
    "onboarding.supplier.mode_invalid": (
        "ଦୟାକରି reply କରନ୍ତୁ 'one by one' କିମ୍ବା 'bulk' — କିମ୍ବା 'done' suppliers skip କରିବାକୁ।"
    ),
    "onboarding.supplier.bulk_added": (
        "{count} supplier add ହେଲା: {names}। ଆଉ ପଠାନ୍ତୁ, କିମ୍ବା ସରିଲେ 'done' ପଠାନ୍ତୁ।"
    ),
    "onboarding.supplier.credit_ask": (
        "{name} ଆପଣଙ୍କୁ pay କରିବାକୁ କେତେ ଦିନ ଦିଏ? (ଯେମିତି 15/'skip')"
    ),
    "onboarding.supplier.added": (
        "Supplier {name} add ହେଲା। ପରବର୍ତ୍ତୀ supplier ର ନାମ, କିମ୍ବା 'done'।"
    ),
    "onboarding.party.phone_ask": "{name} ର phone number? (କିମ୍ବା 'skip')",
    "onboarding.party.credit_invalid": "ଦୟାକରି ଦିନର number ପଠାନ୍ତୁ, ଯେମିତି 15 (କିମ୍ବା 'skip')।",
    "onboarding.bulk_error": "ଏହା ବୁଝି ହେଲା ନାହିଁ: {error}",
    "onboarding.opening.ask": "ଏବେ ଆପଣଙ୍କ ବ୍ୟବସାୟରେ କେତେ cash ଅଛି? (ଯେମିତି 320000)",
    "onboarding.opening.invalid": "ଦୟାକରି ଗୋଟିଏ amount ପଠାନ୍ତୁ, ଯେମିତି 320000।",
    "onboarding.receivable.ask": "କୌଣସି dealer ପାଖରେ ଏବେ ଆପଣଙ୍କ ପଇସା ବାକି ଅଛି କି? (yes/no)",
    "onboarding.receivable.which": "କେଉଁ dealer ଆପଣଙ୍କୁ ଦେବ? (ନାମ)",
    "onboarding.receivable.confirm_new": (
        "ମୋ ପାଖରେ '{name}' ନାମରେ dealer ଏବେ ନାହିଁ — ନୂଆ dealer ଭାବରେ add କରିବି କି? (yes/no)"
    ),
    "onboarding.receivable.amount_ask": "{party} ଆପଣଙ୍କୁ କେତେ ଦେବ? (ଯେମିତି 42000)",
    "onboarding.receivable.amount_invalid": "ଦୟାକରି ଗୋଟିଏ amount ପଠାନ୍ତୁ, ଯେମିତି 42000।",
    "onboarding.receivable.date_ask": (
        "{party} ଠାରୁ payment କେବେ expect କରନ୍ତି? (ଯେମିତି Friday, 15 days, କିମ୍ବା next week)"
    ),
    "onboarding.receivable.recorded": (
        "{amount} {party} ଠାରୁ record ହେଲା। ଆଉ କୌଣସି dealer ଦେବ? (yes/no)"
    ),
    "onboarding.payable.ask": "କୌଣସି supplier payment pending ଅଛି କି? (yes/no)",
    "onboarding.payable.which": "କେଉଁ supplier କୁ ଆପଣ ଦେବ? (ନାମ)",
    "onboarding.payable.confirm_new": (
        "ମୋ ପାଖରେ '{name}' ନାମରେ supplier ଏବେ ନାହିଁ — ନୂଆ supplier ଭାବରେ add କରିବି କି? (yes/no)"
    ),
    "onboarding.payable.amount_ask": "ଆପଣ {party} କୁ କେତେ ଦେବ? (ଯେମିତି 82000)",
    "onboarding.payable.amount_invalid": "ଦୟାକରି ଗୋଟିଏ amount ପଠାନ୍ତୁ, ଯେମିତି 82000।",
    "onboarding.payable.date_ask": (
        "{party} କୁ payment କେବେ due? (ଯେମିତି Friday, 15 days, କିମ୍ବା next week)"
    ),
    "onboarding.payable.recorded": (
        "{amount} {party} କୁ record ହେଲା। ଆଉ କୌଣସି supplier pending? (yes/no)"
    ),
    "onboarding.yes_no_invalid": "ଦୟାକରି yes କିମ୍ବା no reply କରନ୍ତୁ।",
    "onboarding.date_invalid": (
        "କ୍ଷମା କରନ୍ତୁ, ସେ date ବୁଝି ହେଲା ନାହିଁ। Try କରନ୍ତୁ ଯେମିତି Friday, 15 days, କିମ୍ବା next week।"
    ),
    "onboarding.briefing.ask": (
        "ଶେଷ step — ମୁଁ ଆପଣଙ୍କ morning briefing କେବେ ପଠାଇବି? Reply 7, 8, କିମ୍ବା 9।"
    ),
    "onboarding.briefing.invalid": "ଦୟାକରି ଗୋଟିଏ ଘଣ୍ଟା reply କରନ୍ତୁ, ଯେମିତି 7, 8, କିମ୍ବା 9।",
    "onboarding.briefing.range": (
        "ଦୟାକରି ସକାଳ 5 ରୁ 11 ମଧ୍ୟରେ ଘଣ୍ଟା ବାଛନ୍ତୁ (ଯେମିତି 7, 8, କିମ୍ବା 9)।"
    ),
    # Resume: progress checklist ("progress"/"status") and restart ("restart")
    "onboarding.section.business_type": "ବ୍ୟବସାୟ ପ୍ରକାର",
    "onboarding.section.products": "ପ୍ରୋଡକ୍ଟସ୍",
    "onboarding.section.dealers": "ଡିଲର",
    "onboarding.section.suppliers": "ସପ୍ଲାୟର",
    "onboarding.section.opening_balance": "ଓପନିଂ ବ୍ୟାଲାନ୍ସ",
    "onboarding.section.receivables": "ଡିଲର ବାକି",
    "onboarding.section.payables": "ସପ୍ଲାୟର ବାକି",
    "onboarding.section.briefing_hour": "ବ୍ରିଫିଂ ସମୟ",
    "onboarding.import_confirm.title": "📋 ଆପଣଙ୍କ import ରୁ କିଛି ତଥ୍ୟ ମିଳିଲା:",
    "onboarding.import_confirm.line_products": "✅ {count} ପ୍ରୋଡକ୍ଟସ୍",
    "onboarding.import_confirm.line_dealers": "✅ {count} ଡିଲର",
    "onboarding.import_confirm.line_suppliers": "✅ {count} ସପ୍ଲାୟର",
    "onboarding.import_confirm.line_receivables": (
        "✅ {count} outstanding receivable invoice ({amount})"
    ),
    "onboarding.import_confirm.line_payables": (
        "✅ {count} outstanding payable invoice ({amount})"
    ),
    "onboarding.import_confirm.ask": "ଏହା ଠିକ୍ କି? (yes/no)",
    "onboarding.import_confirm.no_ack": (
        "କିଛି ଅସୁବିଧା ନାହିଁ — ଆପଣ ଏହାକୁ ଯେକୌଣସି ସମୟରେ ଠିକ୍ କରିପାରିବେ: "
        "'edit dealer <name>', 'edit supplier <name>', 'add dealer', 'add supplier', "
        "କିମ୍ବା 'stock take' ରେ product quantity ବଦଳାନ୍ତୁ। ଆପଣଙ୍କ ବାକି ସେଟଅପ୍ ଜାରି ଅଛି।"
    ),
    "onboarding.status.title": "📋 Setup progress — {percent}% ସମ୍ପୂର୍ଣ୍ଣ ହେଲା।",
    "onboarding.status.section_done": "✅ {name}",
    "onboarding.status.section_current": "▶️ {name} (ଆପଣ ଏଠାରେ ଅଛନ୍ତି)",
    "onboarding.status.section_pending": "⬜ {name}",
    "onboarding.status.footer_generic": "ଜାରି ରଖିବାକୁ ଆପଣଙ୍କ ପରବର୍ତ୍ତୀ ଉତ୍ତର reply କରନ୍ତୁ।",
    "onboarding.status.restart_hint": "ସେଟଅପ୍ ପୁଣି ଆରମ୍ଭ କରିବାକୁ 'restart' ପଠାନ୍ତୁ।",
    "onboarding.restart.confirm": (
        "⚠️ ଏଥିରେ ଆପଣ ଏବେ ପର୍ଯ୍ୟନ୍ତ ଭରିଥିବା ସବୁ ତଥ୍ୟ (products, dealers, suppliers, opening "
        "balance) ଲିଭିଯିବ ଏବଂ ସେଟଅପ୍ ଆରମ୍ଭରୁ ପୁଣି ହେବ। ଆପଣ ନିଶ୍ଚିତ କି? (yes/no)"
    ),
    "onboarding.restart.cancelled": (
        "ଠିକ୍ ଅଛି — ଆପଣଙ୍କ ସେଟଅପ୍ ଜାରି ଅଛି। ଉପରର ଶେଷ ପ୍ରଶ୍ନର ଉତ୍ତର ପଠାନ୍ତୁ।"
    ),
    "onboarding.restart.done": (
        "🔄 ସବୁ ଲିଭିଗଲା। ଚାଲନ୍ତୁ ପୁଣି ଆରମ୍ଭରୁ ଆପଣଙ୍କ ବ୍ୟବସାୟ ସେଟ୍ ଅପ୍ କରିବା।\n\n"
        "ପ୍ରଥମ ପ୍ରଶ୍ନ: ଆପଣ କେଉଁ ପ୍ରକାର ବ୍ୟବସାୟ କରନ୍ତି? (ଯେମିତି FMCG Distributor, Pharma "
        "Distributor)"
    ),
    # ── Interactive menu ───────────────────────────────────────────────────
    "menu.fallback": "ତଳେ ଗୋଟିଏ ବିକଳ୍ପ ଟାପ୍ କରନ୍ତୁ, କିମ୍ବା ପୂରା ତାଲିକା ପାଇଁ /help ପଠାନ୍ତୁ।",
    "menu.msg.reports.body": "ରିପୋର୍ଟ ଓ ସାରାଂଶ — ଗୋଟିଏ ବାଛନ୍ତୁ:",
    "menu.msg.reports.button": "ରିପୋର୍ଟ ବାଛନ୍ତୁ",
    "menu.msg.inventory.body": "ଇନଭେଣ୍ଟୋରୀ, ଲେଣଦେଣ ଓ ପ୍ରୋଡକ୍ଟ — ଗୋଟିଏ ବାଛନ୍ତୁ:",
    "menu.msg.inventory.button": "ଗୋଟିଏ ବିକଳ୍ପ ବାଛନ୍ତୁ",
    "menu.msg.orders.body": "ଅର୍ଡର, ପେମେଣ୍ଟ ଓ ଆପଣଙ୍କ ଡାଟା — ଗୋଟିଏ ବାଛନ୍ତୁ:",
    "menu.msg.orders.button": "ଗୋଟିଏ ବିକଳ୍ପ ବାଛନ୍ତୁ",
    "menu.msg.statements.body": "ରିପୋର୍ଟ ଓ ଷ୍ଟେଟମେଣ୍ଟ — ଗୋଟିଏ ବାଛନ୍ତୁ:",
    "menu.msg.statements.button": "ଷ୍ଟେଟମେଣ୍ଟ ବାଛନ୍ତୁ",
    "menu.msg.corrections.body": "ସୁଧାର — ପୂର୍ବରୁ record ହୋଇଥିବା କିଛି undo କିମ୍ବା edit କରନ୍ତୁ:",
    "menu.msg.corrections.button": "ସୁଧାର",
    "menu.section.cash_overview": "ନଗଦ ଓ ସାରାଂଶ",
    "menu.section.money_flow": "ପଇସା ପ୍ରବାହ",
    "menu.section.dealers_suppliers": "ଡିଲର ଓ ସପ୍ଲାୟର",
    "menu.section.inventory_transactions": "ଇନଭେଣ୍ଟୋରୀ ଓ ଲେଣଦେଣ",
    "menu.section.manage_products": "ପ୍ରୋଡକ୍ଟ ପରିଚାଳନା",
    "menu.section.orders_payments": "ଅର୍ଡର ଓ ପେମେଣ୍ଟ",
    "menu.section.manage_parties": "ପାର୍ଟି ପରିଚାଳନା",
    "menu.section.your_data": "ଆପଣଙ୍କ ଡାଟା",
    "menu.section.full_lists": "ପୂର୍ଣ୍ଣ ତାଲିକା",
    "menu.section.reports_statements": "ରିପୋର୍ଟ ଓ ଷ୍ଟେଟମେଣ୍ଟ",
    "menu.section.corrections": "ସୁଧାର",
    "menu.row.cash.title": "ନଗଦ ସ୍ଥିତି",
    "menu.row.cash.desc": "ବର୍ତ୍ତମାନ ନଗଦ ଓ 7-ଦିନ ଇନ୍/ଆଉଟ୍",
    "menu.row.summary.title": "ବ୍ୟବସାୟ ସାରାଂଶ",
    "menu.row.summary.desc": "ସମ୍ପୂର୍ଣ୍ଣ ସ୍ନାପସଟ୍",
    "menu.row.priorities.title": "ପ୍ରାଥମିକତା",
    "menu.row.priorities.desc": "ଆଜି କଣ କରିବି",
    "menu.row.overdue.title": "ଓଭରଡ୍ୟୁ ଡିଲର",
    "menu.row.overdue.desc": "କେତେ ଦିନ ବିଳମ୍ବ ଓ ରିସ୍କ ଲେଭଲ୍",
    "menu.row.collections.title": "ସଂଗ୍ରହ ବାକି",
    "menu.row.collections.desc": "ଆସନ୍ତା 7 ଦିନରେ ଆସିବ",
    "menu.row.payments.title": "ପେମେଣ୍ଟ ବାକି",
    "menu.row.payments.desc": "ସପ୍ଲାୟରଙ୍କୁ ଦେବା, 7 ଦିନ",
    "menu.row.all_dealers.title": "ସମସ୍ତ ଡିଲର",
    "menu.row.all_dealers.desc": "ପ୍ରତ୍ୟେକ ଡିଲର, ଫୋନ୍ ଓ ବାକି",
    "menu.row.all_suppliers.title": "ସମସ୍ତ ସପ୍ଲାୟର",
    "menu.row.all_suppliers.desc": "ପ୍ରତ୍ୟେକ ସପ୍ଲାୟର, ଫୋନ୍ ଓ ବାକି",
    "menu.row.top_debtors.title": "ଟପ୍ ଦେନଦାର",
    "menu.row.top_debtors.desc": "ଯେଉଁମାନେ ଆପଣଙ୍କୁ ସବୁଠୁ ଅଧିକ ଦେବେ",
    "menu.row.top_creditors.title": "ଟପ୍ ଲେନଦାର",
    "menu.row.top_creditors.desc": "ଯେଉଁମାନଙ୍କୁ ଆପଣ ସବୁଠୁ ଅଧିକ ଦେବେ",
    "menu.row.inventory.title": "ସାମ୍ପ୍ରତିକ ଇନଭେଣ୍ଟୋରୀ",
    "menu.row.inventory.desc": "ନୂଆ ପ୍ରୋଡକ୍ଟ, ଷ୍ଟକ୍ ଓ ମୂଲ୍ୟ",
    "menu.row.invoices.title": "ସାମ୍ପ୍ରତିକ ଇନଭଏସ୍",
    "menu.row.invoices.desc": "ନୂଆ ଇନଭଏସ୍, ନୂତନତମ ପ୍ରଥମେ",
    "menu.row.recent_payments.title": "ସାମ୍ପ୍ରତିକ ପେମେଣ୍ଟ",
    "menu.row.recent_payments.desc": "ସାମ୍ପ୍ରତିକ ରେକର୍ଡ ପେମେଣ୍ଟ",
    "menu.row.faq.title": "FAQs",
    "menu.row.faq.desc": "ଆପଣଙ୍କ ସେଭ୍ ହୋଇଥିବା ବ୍ୟବସାୟ ନୀତି",
    "menu.row.add_product.title": "ପ୍ରୋଡକ୍ଟ ଯୋଡ଼ନ୍ତୁ",
    "menu.row.add_product.desc": "ନୂଆ ଆଇଟମ୍ ଯୋଡ଼ନ୍ତୁ",
    "menu.row.update_stock.title": "ଷ୍ଟକ୍ ଅପଡେଟ୍ କରନ୍ତୁ",
    "menu.row.update_stock.desc": "ପ୍ରୋଡକ୍ଟର ଷ୍ଟକ୍ ବଦଳାନ୍ତୁ",
    "menu.row.update_price.title": "ମୂଲ୍ୟ ଅପଡେଟ୍ କରନ୍ତୁ",
    "menu.row.update_price.desc": "ପ୍ରୋଡକ୍ଟର ବିକ୍ରୟ ମୂଲ୍ୟ ବଦଳାନ୍ତୁ",
    "menu.row.update_cost.title": "କ୍ରୟ ମୂଲ୍ୟ ଅପଡେଟ୍ କରନ୍ତୁ",
    "menu.row.update_cost.desc": "ସପ୍ଲାୟରଙ୍କୁ ଯାହା ଦିଅନ୍ତି ତାହା ବଦଳାନ୍ତୁ",
    "menu.row.delete_product.title": "ପ୍ରୋଡକ୍ଟ ଡିଲିଟ୍ କରନ୍ତୁ",
    "menu.row.delete_product.desc": "କାଟାଲଗରୁ ଆଇଟମ୍ ହଟାନ୍ତୁ",
    "menu.row.update_product.title": "ପ୍ରୋଡକ୍ଟ ଅପଡେଟ୍ କରନ୍ତୁ",
    "menu.row.update_product.desc": "ମୂଲ୍ୟ, କ୍ରୟ ମୂଲ୍ୟ, କିମ୍ବା ଷ୍ଟକ୍ ବାଛନ୍ତୁ",
    "menu.row.create_order.title": "ଅର୍ଡର ତିଆରି କରନ୍ତୁ",
    "menu.row.create_order.desc": "ଡିଲରକୁ ବିକ୍ରୟ ରେକର୍ଡ କରନ୍ତୁ",
    "menu.row.record_payment.title": "ପେମେଣ୍ଟ ରେକର୍ଡ କରନ୍ତୁ",
    "menu.row.record_payment.desc": "ଆସିଥିବା କିମ୍ବା ଦେଇଥିବା ପେମେଣ୍ଟ ଲଗ୍ କରନ୍ତୁ",
    "menu.row.update_gst.title": "GST ଅପଡେଟ୍ କରନ୍ତୁ",
    "menu.row.update_gst.desc": "ସମସ୍ତ କିମ୍ବା ଗୋଟିଏ ପ୍ରୋଡକ୍ଟର GST ବଦଳାନ୍ତୁ",
    "menu.row.add_dealer.title": "Dealer Add କରନ୍ତୁ",
    "menu.row.add_dealer.desc": "ନୂଆ dealer add କରନ୍ତୁ",
    "menu.row.add_supplier.title": "Supplier Add କରନ୍ତୁ",
    "menu.row.add_supplier.desc": "ନୂଆ supplier add କରନ୍ତୁ",
    "menu.row.export_data.title": "ଡାଟା ଏକ୍ସପୋର୍ଟ କରନ୍ତୁ",
    "menu.row.export_data.desc": "ନିଜ Excel ଡାଟା ଡାଉନଲୋଡ୍ କରନ୍ତୁ",
    "menu.row.morning_briefing.title": "ମର୍ନିଂ ବ୍ରିଫିଂ",
    "menu.row.morning_briefing.desc": "ଆଜିର ବ୍ରିଫିଂ ପୁଣି ପଠାନ୍ତୁ",
    "menu.row.all_inventory.title": "ସମସ୍ତ ଇନଭେଣ୍ଟୋରୀ",
    "menu.row.all_inventory.desc": "ପ୍ରତ୍ୟେକ ପ୍ରୋଡକ୍ଟ, କେବଳ ନୂଆ ନୁହେଁ",
    "menu.row.all_invoices.title": "ସମସ୍ତ ଇନଭଏସ୍",
    "menu.row.all_invoices.desc": "ପ୍ରତ୍ୟେକ ଇନଭଏସ୍, କେବଳ ନୂଆ ନୁହେଁ",
    "menu.row.all_payments.title": "ସମସ୍ତ ପେମେଣ୍ଟ",
    "menu.row.all_payments.desc": "ପ୍ରତ୍ୟେକ ପେମେଣ୍ଟ, କେବଳ ନୂଆ ନୁହେଁ",
    "menu.row.gst_report.title": "GST ରିପୋର୍ଟ",
    "menu.row.gst_report.desc": "ସେଲ୍ସ ଓ ପର୍ଚେଜ୍ ରେଜିଷ୍ଟର ଉଭୟ ପାଇଁ",
    "menu.row.sales_register.title": "ସେଲ୍ସ ରେଜିଷ୍ଟର",
    "menu.row.sales_register.desc": "GST ରେଜିଷ୍ଟର + ରେଟ୍-ୱାଇଜ୍ ସାରାଂଶ",
    "menu.row.purchase_register.title": "ପର୍ଚେଜ୍ ରେଜିଷ୍ଟର",
    "menu.row.purchase_register.desc": "GST ରେଜିଷ୍ଟର + ରେଟ୍-ୱାଇଜ୍ ସାରାଂଶ",
    "menu.row.payment_register.title": "ପେମେଣ୍ଟ ରେଜିଷ୍ଟର",
    "menu.row.payment_register.desc": "ଏହି ମାସର ରସିଦ ଓ ପେମେଣ୍ଟ",
    "menu.row.day_book.title": "ଡେ ବୁକ୍",
    "menu.row.day_book.desc": "ଏହି ମାସର ସବୁ ଇନଭଏସ୍ ଓ ପେମେଣ୍ଟ",
    "menu.row.outstanding_report.title": "ଆଉଟଷ୍ଟାଣ୍ଡିଂ ରିପୋର୍ଟ",
    "menu.row.outstanding_report.desc": "0-30/31-60/61-90/90+ ଦିନ ବକେଟ",
    "menu.row.undo_payment.title": "Undo Payment",
    "menu.row.undo_payment.desc": "ଏବେ record କରିଥିବା payment void କରନ୍ତୁ",
    "menu.row.undo_order.title": "Undo Order",
    "menu.row.undo_order.desc": "ଏବେ ତିଆରି କରିଥିବା order void କରନ୍ତୁ",
    "menu.row.edit_invoice.title": "Edit Invoice",
    "menu.row.edit_invoice.desc": "invoice ର amount, date, କିମ୍ବା party ସୁଧାରନ୍ତୁ",
    "menu.row.edit_payment.title": "Edit Payment",
    "menu.row.edit_payment.desc": "payment ର amount କିମ୍ବା date ସୁଧାରନ୍ତୁ",
    "menu.row.edit_dealer.title": "Edit Dealer",
    "menu.row.edit_dealer.desc": "dealer ର phone, limit, terms, GSTIN ବଦଳାନ୍ତୁ",
    "menu.row.edit_supplier.title": "Edit Supplier",
    "menu.row.edit_supplier.desc": "supplier ର phone, limit, terms, GSTIN ବଦଳାନ୍ତୁ",
    "menu.row.stock_take.title": "Stock Take",
    "menu.row.stock_take.desc": "ଅନେକ products ର stock ଏକାଠି ବଦଳାନ୍ତୁ",
    # ── Workflows (shared) ─────────────────────────────────────────────────
    "workflow.cancelled": "OK, cancel କରିଦେଲି।",
    "workflow.yes_no": "ଦୟାକରି yes କିମ୍ବା no reply କରନ୍ତୁ।",
    "workflow.error_restart": (
        "କିଛି ଭୁଲ୍ ହୋଇଗଲା। ଦୟାକରି ପୁଣି '{trigger}' କହି ଆରମ୍ଭ କରନ୍ତୁ।"
    ),
    "workflow.kind_dealer": "dealer",
    "workflow.kind_supplier": "supplier",
    # ── Record payment ─────────────────────────────────────────────────────
    "payment.start": "କିଏ ଆପଣଙ୍କୁ pay କଲା, କିମ୍ବା ଆପଣ କାହାକୁ pay କଲେ? (party ନାମ)",
    "payment.need_party": "ଦୟାକରି party ନାମ କୁହନ୍ତୁ।",
    "payment.amount_receivable": "ସେମାନେ ଆପଣଙ୍କୁ କେତେ pay କଲେ? (ଯେମିତି 25000)",
    "payment.amount_payable": "ଆପଣ ସେମାନଙ୍କୁ କେତେ pay କଲେ? (ଯେମିତି 25000)",
    "payment.disambiguation": (
        "'{name}' dealer ଓ supplier ଦୁଇ ସହ match କରେ। "
        "Reply 1 ଯଦି ସେ dealer (ସେମାନେ ଆପଣଙ୍କୁ pay କଲେ), "
        "କିମ୍ବା 2 ଯଦି supplier (ଆପଣ ସେମାନଙ୍କୁ pay କଲେ)।"
    ),
    "payment.dealer_or_supplier_invalid": (
        "ଦୟାକରି dealer ପାଇଁ 1 କିମ୍ବା supplier ପାଇଁ 2 reply କରନ୍ତୁ।"
    ),
    "payment.invoice_selection_invalid": (
        "ଦୟାକରି 1 ରୁ {count} ମଧ୍ୟରେ number reply କରନ୍ତୁ, କିମ୍ବା 'all'।"
    ),
    "payment.open_invoices": (
        "{party} ର {count} open invoices ଅଛି:\n{listing}\n"
        "ଗୋଟିଏ number reply କରନ୍ତୁ, କିମ୍ବା 'all' ସବୁ ଉପରେ apply କରିବାକୁ (ପୁରୁଣା ଆଗେ)।"
    ),
    "payment.open_invoice_line": (
        "{index}. {number} — {total} total, {outstanding} ବାକି, due {due}"
    ),
    "payment.new_party_type": (
        "ମୋ ପାଖରେ '{name}' ନାହିଁ। ସେ dealer (customer) କି supplier "
        "(ଯାହାଠାରୁ ଆପଣ କିଣନ୍ତି)? Reply 1 Dealer କିମ୍ବା 2 Supplier।"
    ),
    "payment.new_party_type_invalid": "ଦୟାକରି 1 Dealer କିମ୍ବା 2 Supplier reply କରନ୍ତୁ।",
    "payment.add_new_party": "'{name}' କୁ ନୂଆ {kind} add କରିବେ? yes/no",
    "payment.no_open_invoice": (
        "ମୁଁ କେବଳ existing invoice ବିରୁଦ୍ଧରେ payment record କରିପାରିବି, ଓ {party} ର "
        "{kind} ହିସାବରେ କୌଣସି open invoice ନାହିଁ। ପ୍ରଥମେ ସେମାନଙ୍କ ପାଇଁ invoice ତିଆରି "
        "କରନ୍ତୁ, ତାପରେ 'record payment' ପୁଣି କୁହନ୍ତୁ।"
    ),
    "payment.got_it_no_invoice": "ଠିକ୍ ଅଛି। {message}",
    "payment.amount_invalid": "ଦୟାକରି ଗୋଟିଏ amount ପଠାନ୍ତୁ, ଯେମିତି 25000।",
    "payment.amount_positive": "ଦୟାକରି zero ଠାରୁ ଅଧିକ amount ପଠାନ୍ତୁ।",
    "payment.date_ask": (
        "ଏହା କେବେ pay ହେଲା? Reply 'today', 'yesterday', '3 days ago', କିମ୍ବା skip ଆଜି ପାଇଁ।"
    ),
    "payment.date_invalid": (
        "କ୍ଷମା କରନ୍ତୁ, ସେ date ବୁଝି ହେଲା ନାହିଁ। Try 'today', 'yesterday', '3 days ago'।"
    ),
    "payment.verb_from": "ଠାରୁ",
    "payment.verb_to": "କୁ",
    "payment.target_invoice": " invoice {number} ବିରୁଦ୍ଧରେ",
    "payment.preview": (
        "Confirm: {amount} {party}{target} {verb} {date} ରେ।\n"
        "Reply YES record କରିବାକୁ, NO cancel କରିବାକୁ।"
    ),
    # ── Create order ───────────────────────────────────────────────────────
    "order.start": "ଏ order କାହା ପାଇଁ? (dealer ନାମ)",
    "order.need_dealer": "ଦୟାକରି dealer ନାମ କୁହନ୍ତୁ।",
    "order.dealer_found": "{dealer} ପାଇଁ order। କେଉଁ product?",
    "order.add_new_dealer": (
        "ମୋ ପାଖରେ '{dealer}' dealer ହିସାବରେ ନାହିଁ। ସେମାନଙ୍କୁ ନୂଆ dealer add କରିବେ? yes/no"
    ),
    "order.new_dealer_added": "ଠିକ୍ ଅଛି, {dealer} କୁ ନୂଆ dealer add ହେବ। କେଉଁ product?",
    "order.need_one_product": "ପ୍ରଥମେ ଅନ୍ତତଃ ଗୋଟିଏ product add କରନ୍ତୁ, କିମ୍ବା 'cancel'।",
    "order.need_product": "ଦୟାକରି product ନାମ କୁହନ୍ତୁ, କିମ୍ବା 'done' ଯଦି ସରିଗଲା।",
    "order.quantity_ask": "{product} ର କେତେ {unit}?",
    "order.price_ask": "{product} ର selling price କେତେ?",
    "order.add_new_product": "ମୋ ପାଖରେ '{product}' catalogue ରେ ନାହିଁ। Add କରିବେ? yes/no",
    "order.new_product_declined": "ଠିକ୍ ଅଛି। କେଉଁ product? (କିମ୍ବା 'done')",
    "order.price_invalid": "ଦୟାକରି ଗୋଟିଏ price ପଠାନ୍ତୁ, ଯେମିତି 55।",
    "order.price_positive": "ଦୟାକରି zero ଠାରୁ ଅଧିକ price ପଠାନ୍ତୁ।",
    "order.quantity_invalid": "ଦୟାକରି ଗୋଟିଏ quantity ପଠାନ୍ତୁ, ଯେମିତି 10।",
    "order.quantity_positive": "ଦୟାକରି zero ଠାରୁ ଅଧିକ quantity ପଠାନ୍ତୁ।",
    "order.item_added": (
        "{quantity} x {product} add ହେଲା। ଆଉ product add କରନ୍ତୁ, କିମ୍ବା 'done' reply କରନ୍ତୁ।"
    ),
    "order.line": "- {quantity} x {product} @ {price} = {total}",
    "order.subtotal": "Subtotal: {amount}",
    "order.gst": "GST{rate_label}: {amount}",
    "order.total": "Total: {amount}",
    "order.preview_header": "{dealer} ପାଇଁ order confirm କରନ୍ତୁ:",
    "order.preview_footer": "Reply YES ତିଆରି କରିବାକୁ, NO cancel କରିବାକୁ।",
    # ── Edit invoice / edit payment (safe cases only) ───────────────────────
    "edit.invoice_number_ask": "କେଉଁ invoice? ଏହାର invoice number ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।",
    "edit.invoice_not_found": (
        "ମୋତେ '{number}' ନାମର invoice ମିଳିଲା ନାହିଁ। ଯାଞ୍ଚ କରି ପୁଣି ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "edit.invoice_has_payment": (
        "Invoice {number} ରେ ପୂର୍ବରୁ payment record ଅଛି — ପ୍ରଥମେ ଏହାକୁ void କରନ୍ତୁ "
        "ଏବଂ ପୁଣି ତିଆରି କରନ୍ତୁ।"
    ),
    "edit.field_ask_invoice": (
        "କଣ edit କରିବେ — amount, date, କିମ୍ବା party? "
        "Reply କରନ୍ତୁ 'amount', 'date', କିମ୍ବା 'party'।"
    ),
    "edit.field_invalid_invoice": (
        "ଦୟାକରି reply କରନ୍ତୁ 'amount', 'date', କିମ୍ବା 'party' — କିମ୍ବା 'cancel'।"
    ),
    "edit.amount_ask": "ବର୍ତ୍ତମାନର amount {current}। ନୂଆ amount କଣ ହେବ? (ଯେମିତି 1200)",
    "edit.date_ask": "ବର୍ତ୍ତମାନର date {current}। ନୂଆ date କଣ ହେବ? (ଯେମିତି 2026-01-15)",
    "edit.invoice_party_ask_dealer": "ବର୍ତ୍ତମାନର dealer {current}। ନୂଆ dealer ର ନାମ ପଠାନ୍ତୁ।",
    "edit.invoice_party_ask_supplier": "ବର୍ତ୍ତମାନର supplier {current}। ନୂଆ supplier ର ନାମ ପଠାନ୍ତୁ।",
    "edit.amount_invalid": "ଦୟାକରି ଶୂନ୍ୟରୁ ବଡ଼ ଏକ number ପଠାନ୍ତୁ, ଯେମିତି 1200।",
    "edit.date_invalid": "ଦୟାକରି 2026-01-15 ପରି ଏକ date ପଠାନ୍ତୁ।",
    "edit.party_not_found": (
        "ମୋତେ '{name}' ମିଳିଲା ନାହିଁ। spelling ଯାଞ୍ଚ କରି ପୁଣି ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "edit.value_preview": "{target} ର {field} ବଦଳାଇ {new} କରିବେ?",
    "edit.target_invoice": "invoice {number}",
    "edit.target_payment": "invoice {number} ର payment",
    "edit.reason_ask": "{preview}\nକାହିଁକି? ଏକ ଛୋଟ reason ପଠାନ୍ତୁ, କିମ୍ବା 'skip'।",
    "edit.confirm_prompt": "{preview}\nConfirm କରିବାକୁ YES ପଠାନ୍ତୁ, କିମ୍ବା cancel କରିବାକୁ NO।",
    "edit.party_name_ask": (
        "କେଉଁ dealer କିମ୍ବା supplier ର payment edit କରିବେ? ସେମାନଙ୍କ ନାମ ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "edit.no_payments_for_party": "{name} ପାଇଁ କୌଣସି payment ମିଳିଲା ନାହିଁ।",
    "edit.payment_pick_ask": (
        "{name} ପାଇଁ {count} ସାମ୍ପ୍ରତିକ payments ମିଳିଲା:\n{listing}\n"
        "Number ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "edit.payment_pick_invalid": "ଦୟାକରି 1 ରୁ {count} ମଧ୍ୟରେ ଏକ number ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।",
    "edit.payment_gone": "ସେ payment ଆଉ ଉପଲବ୍ଧ ନାହିଁ। 'edit payment' କହି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    "edit.field_ask_payment": (
        "କଣ edit କରିବେ — amount କିମ୍ବା date? Reply କରନ୍ତୁ 'amount' କିମ୍ବା 'date'।"
    ),
    "edit.field_invalid_payment": "ଦୟାକରି reply କରନ୍ତୁ 'amount' କିମ୍ବା 'date' — କିମ୍ବା 'cancel'।",
    # ── Update GST ─────────────────────────────────────────────────────────
    "gst.scope_prompt": (
        "ସମସ୍ତ products (company default) ର GST update କରନ୍ତୁ, କିମ୍ବା ଗୋଟିଏ product ର? "
        "Reply 'all' କିମ୍ବା product ନାମ।"
    ),
    "gst.rate_ask_all": "{target} ପାଇଁ ନୂଆ default GST rate କେତେ? (0-100, କିମ୍ବା 'cancel')",
    "gst.rate_ask_product": (
        "{target} ପାଇଁ ନୂଆ GST rate କେତେ? (0-100, 'clear' override ହଟାଇ company default "
        "use କରିବାକୁ, କିମ୍ବା 'cancel')"
    ),
    "gst.not_found": (
        "'{name}' ନାମ ର product ମିଳିଲା ନାହିଁ। Reply 'all', ଅନ୍ୟ product ନାମ, କିମ୍ବା 'cancel'।"
    ),
    "gst.rate_invalid": "ଦୟାକରି 0 ରୁ 100 ମଧ୍ୟରେ number ପଠାନ୍ତୁ, ଯେମିତି 18।",
    "gst.all_products": "ସମସ୍ତ products",
    "gst.no_override": "କୌଣସି override ନାହିଁ (company default use କରନ୍ତୁ)",
    "gst.rate_pct": "{rate}%",
    "gst.preview": "{target} ର GST {rate_text} set କରନ୍ତୁ। Reply YES confirm, NO cancel।",
    # ── Product ────────────────────────────────────────────────────────────
    "product.mode_prompt": (
        "ଚାଲନ୍ତୁ products add କରନ୍ତୁ। Reply 'one by one' ଗୋଟିଏ ଗୋଟିଏ, କିମ୍ବା 'bulk' ସବୁ ଏକାଠି "
        "ପୂରା details ସହ (ଯେମିତି Rice, 300, 400, kg, 100, 5)। ଯେକୌଣସି ସମୟରେ 'done' ରୋକିବାକୁ।"
    ),
    "product.no_products_added": "OK, କୌଣସି product add ହେଲା ନାହିଁ।",
    "product.all_done": "Products add କରିବା ସରିଗଲା।",
    "product.name_or_done": "Product ନାମ ପଠାନ୍ତୁ (ଯେମିତି Rice), କିମ୍ବା 'done' ରୋକିବାକୁ।",
    "product.mode_invalid": (
        "ଦୟାକରି reply କରନ୍ତୁ 'one by one' କିମ୍ବା 'bulk' — କିମ୍ବା 'done' ରୋକିବାକୁ।"
    ),
    "product.not_found_retry": (
        "'{name}' ନାମ ର product ମିଳିଲା ନାହିଁ। Spelling check କରି ପୁଣି try କରନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "product.disambiguation": (
        "'{name}' ନାମ ର {count} products ମିଳିଲା:\n{listing}\n"
        "{action} କରିବାକୁ number reply କରନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "product.disambiguation_invalid": (
        "ଦୟାକରି 1 ରୁ {count} ମଧ୍ୟରେ number reply କରନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "product.candidate_line": "{index}. {description}",
    "product.candidate_desc": "{name} ({details})",
    "product.candidate_stock": "{stock} stock ରେ",
    "product.gone": (
        "ସେ product ଏବେ available ନାହିଁ। ଦୟାକରି ପୁଣି '{trigger}' କହି ଆରମ୍ଭ କରନ୍ତୁ।"
    ),
    "product.delete_name_prompt": "କେଉଁ product delete କରିବାକୁ? ନାମ ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।",
    "product.delete_confirm": (
        "{description} delete କରିବେ? ଏହା undo ହେବ ନାହିଁ। Reply YES delete, NO cancel।"
    ),
    "product.delete_no": "OK, delete ହେଲା ନାହିଁ।",
    "product.delete_confirm_invalid": "ଦୟାକରି YES delete ପାଇଁ, କିମ୍ବା NO cancel ପାଇଁ reply କରନ୍ତୁ।",
    "product.delete_already_gone": "{name} ଆଗରୁ ହଟାଯାଇଥିଲା।",
    "product.deleted": "{name} delete ହେଲା।",
    "product.field_prompt": (
        "କଣ update କରିବାକୁ — price, purchase price, କିମ୍ବା stock? "
        "Reply 'price', 'purchase price', କିମ୍ବା 'stock'।"
    ),
    "product.action_update": "update",
    "product.action_delete": "delete",
    "product.label_price": "price",
    "product.label_purchase": "purchase price",
    "product.label_stock": "stock",
    "product.update_name_prompt": (
        "କେଉଁ product ର {label} update କରିବାକୁ? ନାମ ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "product.current_price": (
        "{name} ର ଏବେ price {current}। ନୂଆ price କେତେ ହେବ? (ଯେମିତି 450)"
    ),
    "product.current_purchase": (
        "{name} ର ଏବେ purchase price {current}। "
        "ନୂଆ purchase price କେତେ ହେବ? (ଯେମିତି 300)"
    ),
    "product.current_stock": (
        "{name} ର ଏବେ stock {current}। ନୂଆ stock କେତେ ହେବ? (ଯେମିତି 100)"
    ),
    "product.value_invalid": "ଦୟାକରି ଗୋଟିଏ number ପଠାନ୍ତୁ, ଯେମିତି 450।",
    "product.value_nonneg": "ଦୟାକରି zero କିମ୍ବା ତାଠାରୁ ଅଧିକ number ପଠାନ୍ତୁ।",
    "product.gone_value": "ସେ product ଏବେ available ନାହିଁ।",
    "product.not_set": "set ନାହିଁ",
    "product.updated_price": "{name} ର price {new} କଲା (ଆଗେ {old} ଥିଲା)।",
    "product.updated_purchase": "{name} ର purchase price {new} କଲା (ଆଗେ {old} ଥିଲା)।",
    "product.updated_stock": "{name} ର stock {new} କଲା (ଆଗେ {old} ଥିଲା)।",
    # ── Stock take (bulk stock recount/adjustment) ──────────────────────────
    "stock_take.start_prompt": (
        "ଆସନ୍ତୁ stock take କରିବା। ପ୍ରତ୍ୟେକ product ପାଇଁ, ଏହାର ନାମ ପଠାନ୍ତୁ, ତାପରେ ନୂଆ "
        "count (ଯେମିତି 40) କିମ୍ବା adjustment (ଯେମିତି +15 ମିଳିଲା, -3 ଖରାପ ହେଲା)। ସାରିବା "
        "ପରେ 'done' ପଠାନ୍ତୁ, କିମ୍ବା ଯେକୌଣସି ସମୟରେ 'cancel'।"
    ),
    "stock_take.line_prompt": "ଏକ product ର ନାମ ପଠାନ୍ତୁ, କିମ୍ବା ସାରିବାକୁ 'done'।",
    "stock_take.value_ask": (
        "{name} — ନୂଆ count ପଠାନ୍ତୁ (ଯେମିତି 40) କିମ୍ବା adjustment (ଯେମିତି +15, -3)।"
    ),
    "stock_take.value_invalid": "ଦୟାକରି ଏକ number ପଠାନ୍ତୁ, ଯେମିତି 40, +15, କିମ୍ବା -3।",
    "stock_take.line_added": "{name}: {old} → {new}। ପରବର୍ତ୍ତୀ product ପଠାନ୍ତୁ, କିମ୍ବା 'done'।",
    "stock_take.nothing_to_apply": "ଠିକ୍ ଅଛି, କୌଣସି ପରିବର୍ତ୍ତନ ହେଲା ନାହିଁ।",
    "stock_take.reason_ask": "କାହିଁକି? ଏକ ଛୋଟ reason ପଠାନ୍ତୁ, କିମ୍ବା 'skip'।",
    "stock_take.confirm_prompt": "{summary}\nApply କରିବାକୁ YES ପଠାନ୍ତୁ, କିମ୍ବା cancel କରିବାକୁ NO।",
    "stock_take.failed": "Stock take apply ହେଲା ନାହିଁ: {error}। ଦୟାକରି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    "stock_take.result_line": "- {name}: {new}",
    "stock_take.success": "✅ {count} product(s) ର stock update ହେଲା:\n{lines}{warning}",
    "party.dealer.mode_prompt": (
        "ଆପଣଙ୍କ dealers add କରନ୍ତୁ। Reply 'one by one' ଗୋଟିଏ ଗୋଟିଏ add କରିବାକୁ, "
        "କିମ୍ବା 'bulk' ସବୁ ଏକାଠି ପଠାଇବାକୁ (ଯେମିତି Ram Traders, 9876543210, 15)। "
        "ଯେକୌଣସି ସମୟରେ ରହିବାକୁ 'done'।"
    ),
    "party.dealer.no_added": "ଠିକ୍ ଅଛି, କୌଣସି dealer add ହେଲା ନାହିଁ।",
    "party.dealer.all_done": "ସବୁ dealers add ହୋଇଗଲା।",
    "party.dealer.name_or_done": (
        "Dealer ର ନାମ ପଠାନ୍ତୁ (ଯେମିତି Ram Traders), କିମ୍ବା ରହିବାକୁ 'done'।"
    ),
    "party.dealer.mode_invalid": (
        "ଦୟାକରି reply କରନ୍ତୁ 'one by one' କିମ୍ବା 'bulk' — କିମ୍ବା ରହିବାକୁ 'done'।"
    ),
    "party.supplier.mode_prompt": (
        "ଆପଣଙ୍କ suppliers add କରନ୍ତୁ। Reply 'one by one' ଗୋଟିଏ ଗୋଟିଏ add କରିବାକୁ, "
        "କିମ୍ବା 'bulk' ସବୁ ଏକାଠି ପଠାଇବାକୁ (ଯେମିତି Metro Distributors, 9988776655, 30)। "
        "ଯେକୌଣସି ସମୟରେ ରହିବାକୁ 'done'।"
    ),
    "party.supplier.no_added": "ଠିକ୍ ଅଛି, କୌଣସି supplier add ହେଲା ନାହିଁ।",
    "party.supplier.all_done": "ସବୁ suppliers add ହୋଇଗଲା।",
    "party.supplier.name_or_done": (
        "Supplier ର ନାମ ପଠାନ୍ତୁ (ଯେମିତି Metro Distributors), କିମ୍ବା ରହିବାକୁ 'done'।"
    ),
    "party.supplier.mode_invalid": (
        "ଦୟାକରି reply କରନ୍ତୁ 'one by one' କିମ୍ବା 'bulk' — କିମ୍ବା ରହିବାକୁ 'done'।"
    ),
    # ── Edit dealer / edit supplier (phone, credit limit, terms, GSTIN) ─────
    "party.edit.field_prompt": (
        "କଣ edit କରିବେ — phone, credit limit, payment terms, କିମ୍ବା GSTIN? "
        "Reply କରନ୍ତୁ 'phone', 'credit limit', 'payment terms', କିମ୍ବା 'gstin'।"
    ),
    "party.edit.field_invalid": (
        "ଦୟାକରି reply କରନ୍ତୁ 'phone', 'credit limit', 'payment terms', କିମ୍ବା 'gstin' — "
        "କିମ୍ବା 'cancel'।"
    ),
    "party.edit.name_ask_dealer": "କେଉଁ dealer? ସେମାନଙ୍କ ନାମ ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।",
    "party.edit.name_ask_supplier": "କେଉଁ supplier? ସେମାନଙ୍କ ନାମ ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।",
    "party.edit.not_found": (
        "ମୋତେ '{name}' ମିଳିଲା ନାହିଁ। spelling ଯାଞ୍ଚ କରି ପୁଣି ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "party.edit.disambiguation": (
        "'{name}' ନାମରେ {count} matches ମିଳିଲା:\n{listing}\n"
        "Edit କରିବାକୁ number ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "party.edit.disambiguation_invalid": (
        "ଦୟାକରି 1 ରୁ {count} ମଧ୍ୟରେ ଏକ number ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "party.edit.gone": "ସେ record ଆଉ ଉପଲବ୍ଧ ନାହିଁ। '{trigger}' କହି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    "party.edit.gone_value": "ସେ record ଆଉ ଉପଲବ୍ଧ ନାହିଁ।",
    "party.edit.phone_ask": "{name} ର ବର୍ତ୍ତମାନର phone {current}। ନୂଆ phone କଣ ହେବ?",
    "party.edit.credit_limit_ask": (
        "{name} ର ବର୍ତ୍ତମାନର credit limit {current}। ନୂଆ credit limit କଣ ହେବ? (ଯେମିତି 50000)"
    ),
    "party.edit.payment_terms_ask": (
        "{name} ର ବର୍ତ୍ତମାନର payment terms {current} days। ନୂଆ terms ଦିନରେ କଣ ହେବ? "
        "(ଯେମିତି 30)"
    ),
    "party.edit.gstin_ask": "{name} ର ବର୍ତ୍ତମାନର GSTIN {current}। ନୂଆ GSTIN କଣ ହେବ?",
    "party.edit.days_invalid": "ଦୟାକରି ଦିନର ଏକ ପୂର୍ଣ୍ଣ ସଂଖ୍ୟା ପଠାନ୍ତୁ, ଯେମିତି 30।",
    "party.edit.gstin_invalid": (
        "ତାହା ଠିକ୍ GSTIN ପରି ଲାଗୁନାହିଁ। ଦୟାକରି ଯାଞ୍ଚ କରି ପୁଣି ପଠାନ୍ତୁ, କିମ୍ବା 'cancel'।"
    ),
    "party.edit.value_preview": "{name} ର {field} ବଦଳାଇ {new} କରିବେ?",
    "party.edit.success": "✅ {name} ର {field} {new} ହେଲା (ପୂର୍ବରୁ {old} ଥିଲା)।",
    # ── Void payment / void order ───────────────────────────────────────────
    "void.payment_none": "Undo କରିବାକୁ କୌଣସି WhatsApp payment ମିଳିଲା ନାହିଁ।",
    "void.payment_preview": "Invoice {invoice_number} ପାଇଁ {party} ର {amount} payment void କରିବେ?",
    "void.order_none": "Undo କରିବାକୁ କୌଣସି WhatsApp order ମିଳିଲା ନାହିଁ।",
    "void.order_has_payment": (
        "Order {invoice_number} ରେ ପୂର୍ବରୁ payment record ଅଛି — ପ୍ରଥମେ payment void "
        "କରନ୍ତୁ, ତାପରେ ପୁଣି ଚେଷ୍ଟା କରନ୍ତୁ।"
    ),
    "void.order_preview": "{dealer} ର order {invoice_number} void କରିବେ (total {total})?",
    "void.reason_ask": "{preview}\nକାହିଁକି? ଏକ ଛୋଟ reason ପଠାନ୍ତୁ, କିମ୍ବା 'skip'।",
    "void.confirm_prompt": "{preview}\nVoid କରିବାକୁ YES ପଠାନ୍ତୁ, କିମ୍ବା cancel କରିବାକୁ NO।",
    # ── Pending-operation results ──────────────────────────────────────────
    "pending.reply_yes_no": "Reply YES confirm କରିବାକୁ କିମ୍ବା NO cancel କରିବାକୁ।",
    "pending.payment_failed": "ସେ payment record ହେଲା ନାହିଁ: {error}। ଦୟାକରି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    "pending.payment_success": (
        "✅ {amount} {party} {verb} record ହେଲା।\n"
        "Invoices update ହେଲା: {invoices}\n"
        "ବାକି outstanding: {outstanding}"
    ),
    "pending.order_failed": "ସେ order ତିଆରି ହେଲା ନାହିଁ: {error}। ଦୟାକରି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    "pending.order_line": "- {quantity} x {product} = {total}",
    "pending.order_stock_warning": "\n⚠️ ଏବେ stock negative: {products}",
    "pending.order_pdf_sent": "\nPDF {dealer} କୁ ପଠାଗଲା।",
    "pending.order_pdf_not_sent": (
        "\n(PDF {dealer} କୁ ପଠାଗଲା ନାହିଁ — phone ନାହିଁ କିମ୍ବା WhatsApp delivery ଏବେ set ନାହିଁ।)"
    ),
    "pending.order_success": (
        "✅ Order {number} {dealer} ପାଇଁ ତିଆରି ହେଲା।\n{lines}\n"
        "Subtotal: {subtotal}\nGST: {gst}\nTotal: {total}{warning}{pdf_note}"
    ),
    "pending.gst_failed": "GST update ହେଲା ନାହିଁ: {error}। ଦୟାକରି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    "pending.gst_success": "✅ {target} ର GST {rate} set ହେଲା।",
    "pending.gst_rate_default": "company default",
    "pending.void_payment_failed": "ସେ payment void ହେଲା ନାହିଁ: {error}। ଦୟାକରି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    "pending.void_payment_success": (
        "✅ Invoice {invoice_number} ପାଇଁ {party} ର {amount} payment void ହେଲା।"
    ),
    "pending.void_order_failed": "ସେ order void ହେଲା ନାହିଁ: {error}। ଦୟାକରି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    "pending.void_order_success": "✅ {dealer} ର order {invoice_number} void ହେଲା (total {total})।",
    "pending.edit_invoice_failed": "ସେ invoice edit ହେଲା ନାହିଁ: {error}। ଦୟାକରି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    "pending.edit_invoice_success": (
        "✅ Invoice {number} ର {field} {new} ହେଲା (ପୂର୍ବରୁ {old} ଥିଲା)।"
    ),
    "pending.edit_payment_failed": "ସେ payment edit ହେଲା ନାହିଁ: {error}। ଦୟାକରି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    "pending.edit_payment_success": (
        "✅ Invoice {number} ର payment ର {field} {new} ହେଲା (ପୂର୍ବରୁ {old} ଥିଲା)।"
    ),
    "pending.unknown": "ସେ confirmation ରେ କିଛି ଭୁଲ୍ ହୋଇଗଲା। ଦୟାକରି ପୁଣି ଆରମ୍ଭ କରନ୍ତୁ।",
    # ── Menu prompt / follow-up / notifications / evening ──────────────────
    "menu.prompt": "Reply କରନ୍ତୁ 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk",
    "followup.message": (
        "📋 Payment Follow-Up\n\n"
        "{number} — {dealer} — {amount}\n"
        "Due date: ଆଜି\n\n"
        "Payment ମିଳିଲା କି?\n"
        "1. ହଁ — ପୂରା amount\n"
        "2. Partial payment\n"
        "3. ଏବେ ଯାଏ ନାହିଁ"
    ),
    "followup.recorded_full": (
        "{amount} payment {dealer} ଠାରୁ record ହେଲା।\n"
        "{number} ବନ୍ଦ ହେଲା।\n"
        "ବାକି: ₹0।\n"
        "Cash ଓ କାଲିର briefing update ହେଲା।"
    ),
    "followup.recorded_partial": (
        "{amount} partial payment record ହେଲା।\n"
        "{number} — {remaining} ଏବେ ବାକି।\n"
        "Cash ଓ କାଲିର briefing update ହେଲା।"
    ),
    "followup.invoice_gone": "ସେ invoice ଏବେ available ନାହିଁ। {menu_prompt}",
    "followup.ask_partial": "କେତେ ମିଳିଲା?",
    "followup.ask_expected_date": (
        "{dealer} ଠାରୁ payment କେବେ expect କରନ୍ତି?\nExample: Friday, 3 days, next week"
    ),
    "followup.confirm_invalid": "ବୁଝି ହେଲା ନାହିଁ। Reply 1, 2, କିମ୍ବା 3।",
    "followup.amount_invalid": (
        "ସେ amount ବୁଝି ହେଲା ନାହିଁ। ଦୟାକରି ଗୋଟିଏ number ପଠାନ୍ତୁ, ଯେମିତି 25000।"
    ),
    "followup.date_invalid": "ସେ date ବୁଝି ହେଲା ନାହିଁ।\nExample: Friday, 3 days, next week",
    "followup.rescheduled": (
        "ନୋଟ୍ କରାଗଲା। {number} follow-up {when} ପାଇଁ schedule ହେଲା।\n"
        "{dealer} କାଲିର briefing ରେ flag ଅଛି।"
    ),
    "followup.error": "ସେ follow-up ରେ କିଛି ଭୁଲ୍ ହୋଇଗଲା। {menu_prompt}",
    "notify.supplier_reminder": (
        "⏰ Payment Reminder\n\n"
        "{supplier} ର {amount} payment {when} due ଅଛି।\n"
        "{cash_line}\n"
        "Cash position ନ ବଦଳିଲେ କୌଣସି action ଦରକାର ନାହିଁ।"
    ),
    "notify.when_today": "ଆଜି",
    "notify.when_tomorrow": "କାଲି",
    "notify.cash_line": "ଏବେ available cash: {amount} — {sufficiency}",
    "notify.cash_sufficient": "ଯଥେଷ୍ଟ ଅଛି।",
    "notify.cash_insufficient": "କମ ପଡ଼ିପାରେ।",
    "notify.dealer_alert": (
        "⚠ Collection Alert\n\n"
        "{dealer} — {amount} — ଏବେ {days} ଦିନ overdue।\n"
        "3 ଦିନ ରୁ କୌଣସି follow-up ନାହିଁ।\n"
        "Suggestion: ନୂଆ order ଦେବା ଆଗେ ଆଜି call କରନ୍ତୁ।"
    ),
    "evening.header": "🌙 ସନ୍ଧ୍ୟା Business Summary",
    "evening.counts": (
        "Invoices ତିଆରି: {invoices} · WhatsApp ରୁ Orders: {orders} · Payments record: {payments}"
    ),
    "evening.sales": "ଆଜିର Sales: {amount}",
    "evening.margin": "Sales Margin: {amount}",
    "evening.margin_excluded": " ({items} items, {amount} exclude — cost price ନାହିଁ)",
    "evening.collections": "Collections: {amount}",
    "evening.supplier_payments": "Supplier Payments: {amount}",
    "evening.net_cash": "Net Cash Movement: {amount}",
    "evening.outstanding": "Outstanding Receivables: {amount}",
    "evening.priority_header": "Priority Actions:",
}
