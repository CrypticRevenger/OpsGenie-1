"""Hindi (Devanagari) message catalog.

DRAFT — needs a native Hindi speaker's review before production go-live.
Widely-used English business terms/acronyms (GST, Excel, FAQ) are kept as-is,
matching how they appear in real Hindi WhatsApp business chat. Mirrors the
exact keys in en.py (enforced by tests/test_i18n.py); English is the safe
fallback for any key missing here.
"""

from __future__ import annotations

# Full "help" block — DRAFT. Command keywords stay English (they're the literal
# triggers); only prose/descriptions are Hindi.
_HELP_TEXT = """*OpsGenie Help*

*नकद और अवलोकन*
• cash / cash position — अभी का नकद, 7-दिन इन/आउट, नेट पोज़िशन (या 1 / /cash)
• summary / business summary — नकद, नेट पोज़िशन, 7-दिन कलेक्शन/पेमेंट, ओवरड्यू डीलर
• priorities / what should I do — प्राथमिकता वाले काम: नकद चेतावनी, किसे कॉल करें, सप्लायर बकाया

*डीलर (जो आपको देते हैं)*
• dealers / all dealers — हर डीलर फ़ोन और बकाया के साथ
• top debtors / who owes most — सबसे ज़्यादा बकाया वाले डीलर
• overdue / overdue dealers — कितने दिन लेट और रिस्क लेवल (या 4 / /dealer_risk)
• balance <name> — एक डीलर का बकाया, जैसे balance Ram Traders

*सप्लायर (जिन्हें आप देते हैं)*
• suppliers / all suppliers — हर सप्लायर फ़ोन और बकाया के साथ
• top creditors — जिन्हें आप सबसे ज़्यादा देते हैं
• balance <name> — एक सप्लायर का बकाया

*आने वाला कैश फ़्लो*
• collections / upcoming collections — डीलरों से आने वाला, अगले 7 दिन (या 2 / /collections)
• payments / upcoming payments — सप्लायरों को देना, अगले 7 दिन (या 3 / /suppliers)

*इन्वेंटरी*
• inventory / products / stock — नए जोड़े प्रोडक्ट (स्टॉक qty, बिक्री कीमत)
• all inventory — हर प्रोडक्ट, सिर्फ़ नए नहीं
• stock <product> — एक आइटम चेक करें, जैसे stock Rice

*ट्रांज़ैक्शन*
• invoices / recent invoices — नए इनवॉइस (number, party, total, status, dates)
• all invoices — हर इनवॉइस, सिर्फ़ नए नहीं
• payments / recent payments — नए दर्ज पेमेंट
• all payments / all time payments — हर पेमेंट, सिर्फ़ नए नहीं
• faq / policy — आपकी सेव की गई बिज़नेस पॉलिसी (delivery days, returns, minimum order)

*प्रोडक्ट्स मैनेज करें* (guided, एक-एक सवाल)
• add product (या /add_product) — नया आइटम: name, stock, unit, बिक्री कीमत, खरीद कीमत
• update stock (या /update_stock) — प्रोडक्ट का स्टॉक बदलें
• update price (या /update_price) — प्रोडक्ट की बिक्री कीमत बदलें
• update purchase price (या /update_purchase_price) — सप्लायर को जो देते हैं वो बदलें
• update product (या /update_product) — कीमत, खरीद कीमत, या स्टॉक चुनें
• update gst (या /update_gst) — सभी या एक प्रोडक्ट का GST बदलें
• delete product (या /delete_product) — catalogue से आइटम हटाएँ

*ऑर्डर और पेमेंट*
• new order (या /create_order, या "new invoice") — डीलर को सेल दर्ज करें, प्रोडक्ट दर प्रोडक्ट
• record payment (या /record_payment) — डीलर से आया या सप्लायर को दिया पेमेंट लॉग करें

*आपका डेटा*
• export data (या /export_data) — पूरा बिज़नेस डेटा Excel में download link
• morning briefing (या /morning_briefing) — आज की ब्रीफ़िंग दोबारा भेजें

*Quick Access*
• menu — टाइप करने की जगह options tap करें
• help (या /help) — यह लिस्ट कभी भी दोबारा देखें"""

MESSAGES: dict[str, str] = {
    # ── Errors / fallbacks ────────────────────────────────────────────────
    "errors.something_wrong": "कुछ गड़बड़ हो गई। कृपया फिर से कोशिश करें।",
    "errors.assistant_fallback": (
        "माफ़ करें, मैं अभी इसका जवाब नहीं दे पाया। जवाब दें 1 Cash · 2 Collections · "
        "3 Suppliers · 4 Dealer Risk, या दोबारा लिखें।"
    ),
    "onboarding.language_changed": "✅ हो गया — अब से मैं आपको {language} में मैसेज करूँगा।",
    # ── Cash Position report ───────────────────────────────────────────────
    "reports.cash.header": "💰 नकद स्थिति",
    "reports.cash.available_now": "अभी उपलब्ध: {amount}",
    "reports.cash.expected_in": "आने वाला (7 दिन): {amount}",
    "reports.cash.due_out": "देना है (7 दिन): {amount}",
    "reports.cash.net_expected": "नेट अपेक्षित: {amount}",
    "reports.cash.shortage": "इस हफ्ते नकद की कमी हो सकती है।",
    "reports.cash.no_shortage": "इस हफ्ते नकद की कमी नहीं होगी।",
    # ── Collections report ─────────────────────────────────────────────────
    "reports.collections.header": "📥 बकाया कलेक्शन",
    "reports.collections.none": "अगले 7 दिन में कोई कलेक्शन नहीं आने वाला।",
    "reports.collections.total": "इस हफ्ते कुल अपेक्षित: {amount}",
    # ── Supplier payments report ───────────────────────────────────────────
    "reports.suppliers.header": "📤 सप्लायर पेमेंट बाकी",
    "reports.suppliers.none": "अगले 7 दिन में कोई सप्लायर पेमेंट बाकी नहीं।",
    "reports.suppliers.total": "इस हफ्ते कुल देना: {amount}",
    "reports.suppliers.cash_ok": "नकद पर्याप्त है",
    "reports.suppliers.cash_short": "नकद कम पड़ सकता है",
    # ── Dealer risk report ─────────────────────────────────────────────────
    "reports.risk.header": "⚠ डीलर रिस्क सारांश",
    "reports.risk.none": "अभी कोई ओवरड्यू डीलर नहीं।",
    "reports.risk.high": "हाई रिस्क:",
    "reports.risk.medium": "मीडियम रिस्क:",
    "reports.risk.low": "लो रिस्क:",
    "reports.risk.dealer_line": "{name} — {amount} ओवरड्यू ({days}d) — {late}",
    # ── Shared phrases ─────────────────────────────────────────────────────
    "reports.due.today": "आज देय",
    "reports.due.weekday": "{day} को देय",
    "reports.due.date": "{date} को देय",
    "reports.late.none": "समय पर भुगतान करता है",
    "reports.late.one": "6 महीने में 1 लेट पेमेंट",
    "reports.late.many": "6 महीने में {count} लेट पेमेंट",
    # ── Business summary ───────────────────────────────────────────────────
    "reports.summary.header": "📊 बिज़नेस सारांश",
    "reports.summary.cash_now": "अभी उपलब्ध नकद: {amount}",
    "reports.summary.net_7d": "नेट नकद पोज़िशन (7d): {amount}",
    "reports.summary.expected_in": "आने वाला (7d): {amount}",
    "reports.summary.expected_out": "जाने वाला (7d): {amount}",
    "reports.summary.shortage": "इस हफ्ते नकद की कमी हो सकती है।",
    "reports.summary.no_shortage": "नकद की कमी नहीं होगी।",
    "reports.summary.overdue_count": "ओवरड्यू डीलर: {count}",
    "reports.summary.overdue_hint": " — विवरण के लिए 'overdue' भेजें।",
    # ── Priorities ─────────────────────────────────────────────────────────
    "reports.priorities.none": "🎯 अभी कुछ ज़रूरी नहीं — कोई प्राथमिकता नहीं।",
    "reports.priorities.header": "🎯 प्राथमिकताएँ",
    # ── Dealer / supplier lists ────────────────────────────────────────────
    "reports.dealers.none": "आपके पास अभी कोई डीलर नहीं है।",
    "reports.dealers.header": "👥 डीलर ({count}):",
    "reports.suppliers_list.none": "आपके पास अभी कोई सप्लायर नहीं है।",
    "reports.suppliers_list.header": "🚚 सप्लायर ({count}):",
    "reports.party.no_phone": "फ़ोन नहीं",
    "reports.party.line": "{name} — {phone} — बकाया {amount}",
    "reports.top_debtors.none": "अभी किसी डीलर पर आपका कुछ बकाया नहीं।",
    "reports.top_debtors.header": "💰 टॉप देनदार",
    "reports.top_creditors.none": "अभी आप किसी सप्लायर को कुछ नहीं देते।",
    "reports.top_creditors.header": "💸 टॉप लेनदार",
    # ── Inventory ──────────────────────────────────────────────────────────
    "reports.inventory.none": "आपके catalogue में अभी कोई प्रोडक्ट नहीं।",
    "reports.inventory.label_recent": "हाल की इन्वेंटरी",
    "reports.inventory.label_all": "पूरी इन्वेंटरी",
    "reports.inventory.header_partial": "📦 {label} ({count} of {total}):",
    "reports.inventory.header_full": "📦 {label} ({count}):",
    "reports.inventory.more": "\n\n…और {remaining} ज़्यादा — पूरी लिस्ट के लिए 'all inventory' भेजें।",
    "reports.product.price_not_set": "कीमत सेट नहीं",
    # ── FAQs ───────────────────────────────────────────────────────────────
    "reports.faq.none": "आपके पास अभी कोई सेव की गई पॉलिसी नहीं।",
    "reports.faq.header": "❓ FAQs ({count}):",
    "reports.faq.qa": "Q: {question}\nA: {answer}",
    # ── Invoices ───────────────────────────────────────────────────────────
    "reports.invoices.none": "आपके पास अभी कोई इनवॉइस नहीं।",
    "reports.invoices.label_recent": "हाल के इनवॉइस",
    "reports.invoices.label_all": "सभी इनवॉइस",
    "reports.invoices.header_partial": "📄 {label} ({count} of {total}):",
    "reports.invoices.header_full": "📄 {label} ({count}):",
    "reports.invoices.more": "\n\n…और {remaining} ज़्यादा — पूरी लिस्ट के लिए 'all invoices' भेजें।",
    "reports.invoices.line": "{number} — {party} — {amount} — {status} — {due}",
    "reports.unknown_party": "अज्ञात party",
    # ── Payments ───────────────────────────────────────────────────────────
    "reports.payments.none": "आपके पास अभी कोई पेमेंट दर्ज नहीं।",
    "reports.payments.label_recent": "हाल के पेमेंट",
    "reports.payments.label_all": "सभी पेमेंट",
    "reports.payments.header_partial": "💵 {label} ({count} of {total}):",
    "reports.payments.header_full": "💵 {label} ({count}):",
    "reports.payments.more": "\n\n…और {remaining} ज़्यादा — पूरी लिस्ट के लिए 'all payments' भेजें।",
    "reports.payments.from": "से",
    "reports.payments.to": "को",
    "reports.payments.line": "{amount} — invoice {number} {direction} — {date}",
    # ── Party balance ──────────────────────────────────────────────────────
    "reports.balance.dealer_owes": "{party} को आपको {amount} देना है।",
    "reports.balance.you_owe": "आपको {party} को {amount} देना है।",
    # ── Stock item ─────────────────────────────────────────────────────────
    "reports.stock.not_found": "'{name}' से मिलता कोई प्रोडक्ट नहीं मिला।",
    "reports.stock.line": "{name} — {stock} स्टॉक में — {price}",
    # ── Sales impact ───────────────────────────────────────────────────────
    "reports.sales.revenue": "revenue {amount}",
    "reports.sales.profit": "profit {amount}",
    "reports.sales.left": "{qty} स्टॉक में बचा",
    "reports.sales.total_revenue": "कुल revenue: {amount}",
    "reports.sales.total_profit": "कुल profit: {amount}",
    "reports.sales.no_cost": "({missing} की खरीद कीमत नहीं है — profit से हटाया)",
    # ── Excel export link ──────────────────────────────────────────────────
    "reports.export.not_configured": (
        "Data export link अभी सेटअप नहीं है — अपने OpsGenie admin से configure करवाएँ।"
    ),
    "reports.export.ready": "आपका latest Excel export तैयार है।\nDownload ({ttl} min valid): {link}",
    # ── Help text ──────────────────────────────────────────────────────────
    "menu.help_text": _HELP_TEXT,
    # ── Interactive menu ───────────────────────────────────────────────────
    "menu.fallback": "नीचे से एक विकल्प चुनें, या पूरी सूची के लिए /help भेजें।",
    "menu.msg.reports.body": "रिपोर्ट्स और अवलोकन — एक चुनें:",
    "menu.msg.reports.button": "रिपोर्ट चुनें",
    "menu.msg.inventory.body": "इन्वेंटरी, लेनदेन और प्रोडक्ट्स — एक चुनें:",
    "menu.msg.inventory.button": "एक विकल्प चुनें",
    "menu.msg.orders.body": "ऑर्डर, पेमेंट और आपका डेटा — एक चुनें:",
    "menu.msg.orders.button": "एक विकल्प चुनें",
    "menu.section.cash_overview": "नकद और अवलोकन",
    "menu.section.money_flow": "पैसे का प्रवाह",
    "menu.section.dealers_suppliers": "डीलर और सप्लायर",
    "menu.section.inventory_transactions": "इन्वेंटरी व लेनदेन",
    "menu.section.manage_products": "प्रोडक्ट्स मैनेज करें",
    "menu.section.orders_payments": "ऑर्डर और पेमेंट",
    "menu.section.your_data": "आपका डेटा",
    "menu.section.full_lists": "पूरी सूचियाँ",
    "menu.row.cash.title": "नकद स्थिति",
    "menu.row.cash.desc": "अभी नकद और 7-दिन इन/आउट",
    "menu.row.summary.title": "बिज़नेस सारांश",
    "menu.row.summary.desc": "पूरा स्नैपशॉट",
    "menu.row.priorities.title": "प्राथमिकताएँ",
    "menu.row.priorities.desc": "आज क्या करूँ",
    "menu.row.overdue.title": "ओवरड्यू डीलर",
    "menu.row.overdue.desc": "कितने दिन लेट और रिस्क लेवल",
    "menu.row.collections.title": "कलेक्शन बाकी",
    "menu.row.collections.desc": "अगले 7 दिन में आने वाला",
    "menu.row.payments.title": "पेमेंट बाकी",
    "menu.row.payments.desc": "सप्लायर को देना, 7 दिन",
    "menu.row.all_dealers.title": "सभी डीलर",
    "menu.row.all_dealers.desc": "हर डीलर, फ़ोन और बकाया",
    "menu.row.all_suppliers.title": "सभी सप्लायर",
    "menu.row.all_suppliers.desc": "हर सप्लायर, फ़ोन और बकाया",
    "menu.row.top_debtors.title": "टॉप देनदार",
    "menu.row.top_debtors.desc": "जिन्हें आपको सबसे ज़्यादा देना है",
    "menu.row.top_creditors.title": "टॉप लेनदार",
    "menu.row.top_creditors.desc": "जिन्हें आप सबसे ज़्यादा देते हैं",
    "menu.row.inventory.title": "हाल की इन्वेंटरी",
    "menu.row.inventory.desc": "नए प्रोडक्ट, स्टॉक और कीमत",
    "menu.row.invoices.title": "हाल के इनवॉइस",
    "menu.row.invoices.desc": "नए इनवॉइस, नवीनतम पहले",
    "menu.row.recent_payments.title": "हाल के पेमेंट",
    "menu.row.recent_payments.desc": "हाल में दर्ज पेमेंट",
    "menu.row.faq.title": "FAQs",
    "menu.row.faq.desc": "आपकी सेव की गई बिज़नेस पॉलिसी",
    "menu.row.add_product.title": "प्रोडक्ट जोड़ें",
    "menu.row.add_product.desc": "नया आइटम जोड़ें",
    "menu.row.update_stock.title": "स्टॉक अपडेट करें",
    "menu.row.update_stock.desc": "प्रोडक्ट का स्टॉक बदलें",
    "menu.row.update_price.title": "कीमत अपडेट करें",
    "menu.row.update_price.desc": "प्रोडक्ट की बिक्री कीमत बदलें",
    "menu.row.update_cost.title": "लागत कीमत अपडेट करें",
    "menu.row.update_cost.desc": "सप्लायर को जो देते हैं वो बदलें",
    "menu.row.delete_product.title": "प्रोडक्ट हटाएँ",
    "menu.row.delete_product.desc": "कैटलॉग से आइटम हटाएँ",
    "menu.row.update_product.title": "प्रोडक्ट अपडेट करें",
    "menu.row.update_product.desc": "कीमत, लागत, या स्टॉक चुनें",
    "menu.row.create_order.title": "ऑर्डर बनाएँ",
    "menu.row.create_order.desc": "डीलर को बिक्री दर्ज करें",
    "menu.row.record_payment.title": "पेमेंट दर्ज करें",
    "menu.row.record_payment.desc": "आया या दिया पेमेंट लॉग करें",
    "menu.row.update_gst.title": "GST अपडेट करें",
    "menu.row.update_gst.desc": "सभी या एक प्रोडक्ट का GST बदलें",
    "menu.row.export_data.title": "डेटा एक्सपोर्ट करें",
    "menu.row.export_data.desc": "अपना Excel डेटा डाउनलोड करें",
    "menu.row.morning_briefing.title": "मॉर्निंग ब्रीफ़िंग",
    "menu.row.morning_briefing.desc": "आज की ब्रीफ़िंग दोबारा भेजें",
    "menu.row.all_inventory.title": "पूरी इन्वेंटरी",
    "menu.row.all_inventory.desc": "हर प्रोडक्ट, सिर्फ़ नए नहीं",
    "menu.row.all_invoices.title": "सभी इनवॉइस",
    "menu.row.all_invoices.desc": "हर इनवॉइस, सिर्फ़ नए नहीं",
    "menu.row.all_payments.title": "सभी पेमेंट",
    "menu.row.all_payments.desc": "हर पेमेंट, सिर्फ़ नए नहीं",
}
