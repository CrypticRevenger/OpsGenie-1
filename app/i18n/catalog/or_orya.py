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

*ସପ୍ଲାୟର (ଯେଉଁମାନଙ୍କୁ ଆପଣ ଦିଅନ୍ତି)*
• suppliers / all suppliers — ପ୍ରତ୍ୟେକ ସପ୍ଲାୟର ଫୋନ୍ ଓ ବାକି ସହ
• top creditors — ଯେଉଁମାନଙ୍କୁ ଆପଣ ସବୁଠୁ ଅଧିକ ଦିଅନ୍ତି
• balance <name> — ଗୋଟିଏ ସପ୍ଲାୟରର ବାକି

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

*ଅର୍ଡର ଓ ପେମେଣ୍ଟ*
• new order (କିମ୍ବା /create_order, କିମ୍ବା "new invoice") — ଡିଲରକୁ ସେଲ ରେକର୍ଡ କରନ୍ତୁ
• record payment (କିମ୍ବା /record_payment) — ଡିଲରଠାରୁ ଆସିଥିବା କିମ୍ବା ସପ୍ଲାୟରକୁ ଦେଇଥିବା ପେମେଣ୍ଟ ଲଗ୍

*ଆପଣଙ୍କ ଡାଟା*
• export data (କିମ୍ବା /export_data) — ପୂରା ବ୍ୟବସାୟ ଡାଟା Excel ରେ download link
• morning briefing (କିମ୍ବା /morning_briefing) — ଆଜିର ବ୍ରିଫିଂ ପୁଣି ପଠାନ୍ତୁ

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
    "onboarding.product.first_name": (
        "ଆପଣଙ୍କ ପ୍ରଥମ product ର ନାମ ପଠାନ୍ତୁ (ଯେମିତି Rice), କିମ୍ବା 'done' skip କରିବାକୁ।"
    ),
    "onboarding.product.mode_invalid": (
        "ଦୟାକରି reply କରନ୍ତୁ 'one by one' କିମ୍ବା 'bulk' — କିମ୍ବା 'done' products skip କରିବାକୁ।"
    ),
    "onboarding.product.bulk_error": "ଏହା ବୁଝି ହେଲା ନାହିଁ: {error}",
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
        "ଏବେ ଆପଣଙ୍କ dealers (customers) add କରନ୍ତୁ। ପ୍ରଥମ dealer ର ନାମ ପଠାନ୍ତୁ, କିମ୍ବା 'done'।"
    ),
    "onboarding.dealer.credit_ask": (
        "{name} କୁ ଆପଣ କେତେ credit ଦିନ ଦିଅନ୍ତି? (ଯେମିତି 15, କିମ୍ବା 'skip')"
    ),
    "onboarding.dealer.added": "Dealer {name} add ହେଲା। ପରବର୍ତ୍ତୀ dealer ର ନାମ, କିମ୍ବା 'done'।",
    "onboarding.suppliers.intro": (
        "ଏବେ ଆପଣଙ୍କ suppliers। ପ୍ରଥମ supplier ର ନାମ ପଠାନ୍ତୁ, କିମ୍ବା 'done'।"
    ),
    "onboarding.supplier.credit_ask": (
        "{name} ଆପଣଙ୍କୁ pay କରିବାକୁ କେତେ ଦିନ ଦିଏ? (ଯେମିତି 15/'skip')"
    ),
    "onboarding.supplier.added": (
        "Supplier {name} add ହେଲା। ପରବର୍ତ୍ତୀ supplier ର ନାମ, କିମ୍ବା 'done'।"
    ),
    "onboarding.party.phone_ask": "{name} ର phone number? (କିମ୍ବା 'skip')",
    "onboarding.party.credit_invalid": "ଦୟାକରି ଦିନର number ପଠାନ୍ତୁ, ଯେମିତି 15 (କିମ୍ବା 'skip')।",
    "onboarding.opening.ask": "ଏବେ ଆପଣଙ୍କ ବ୍ୟବସାୟରେ କେତେ cash ଅଛି? (ଯେମିତି 320000)",
    "onboarding.opening.invalid": "ଦୟାକରି ଗୋଟିଏ amount ପଠାନ୍ତୁ, ଯେମିତି 320000।",
    "onboarding.receivable.ask": "କୌଣସି dealer ପାଖରେ ଏବେ ଆପଣଙ୍କ ପଇସା ବାକି ଅଛି କି? (yes/no)",
    "onboarding.receivable.which": "କେଉଁ dealer ଆପଣଙ୍କୁ ଦେବ? (ନାମ)",
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
    # ── Interactive menu ───────────────────────────────────────────────────
    "menu.fallback": "ତଳେ ଗୋଟିଏ ବିକଳ୍ପ ଟାପ୍ କରନ୍ତୁ, କିମ୍ବା ପୂରା ତାଲିକା ପାଇଁ /help ପଠାନ୍ତୁ।",
    "menu.msg.reports.body": "ରିପୋର୍ଟ ଓ ସାରାଂଶ — ଗୋଟିଏ ବାଛନ୍ତୁ:",
    "menu.msg.reports.button": "ରିପୋର୍ଟ ବାଛନ୍ତୁ",
    "menu.msg.inventory.body": "ଇନଭେଣ୍ଟୋରୀ, ଲେଣଦେଣ ଓ ପ୍ରୋଡକ୍ଟ — ଗୋଟିଏ ବାଛନ୍ତୁ:",
    "menu.msg.inventory.button": "ଗୋଟିଏ ବିକଳ୍ପ ବାଛନ୍ତୁ",
    "menu.msg.orders.body": "ଅର୍ଡର, ପେମେଣ୍ଟ ଓ ଆପଣଙ୍କ ଡାଟା — ଗୋଟିଏ ବାଛନ୍ତୁ:",
    "menu.msg.orders.button": "ଗୋଟିଏ ବିକଳ୍ପ ବାଛନ୍ତୁ",
    "menu.section.cash_overview": "ନଗଦ ଓ ସାରାଂଶ",
    "menu.section.money_flow": "ପଇସା ପ୍ରବାହ",
    "menu.section.dealers_suppliers": "ଡିଲର ଓ ସପ୍ଲାୟର",
    "menu.section.inventory_transactions": "ଇନଭେଣ୍ଟୋରୀ ଓ ଲେଣଦେଣ",
    "menu.section.manage_products": "ପ୍ରୋଡକ୍ଟ ପରିଚାଳନା",
    "menu.section.orders_payments": "ଅର୍ଡର ଓ ପେମେଣ୍ଟ",
    "menu.section.your_data": "ଆପଣଙ୍କ ଡାଟା",
    "menu.section.full_lists": "ପୂର୍ଣ୍ଣ ତାଲିକା",
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
}
