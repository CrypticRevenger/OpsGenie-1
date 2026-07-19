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
• add dealer (या /add_dealer) — नया dealer add करें: नाम, फ़ोन, credit दिन
• edit dealer (या /edit_dealer) — dealer का phone, credit limit, terms, या GSTIN बदलें

*सप्लायर (जिन्हें आप देते हैं)*
• suppliers / all suppliers — हर सप्लायर फ़ोन और बकाया के साथ
• top creditors — जिन्हें आप सबसे ज़्यादा देते हैं
• balance <name> — एक सप्लायर का बकाया
• add supplier (या /add_supplier) — नया supplier add करें: नाम, फ़ोन, credit दिन
• edit supplier (या /edit_supplier) — supplier का phone, credit limit, terms, या GSTIN बदलें

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
• stock take (या /stock_take) — कई प्रोडक्ट का stock एक साथ recount या adjust करें

*ऑर्डर और पेमेंट*
• new order (या /create_order, या "new invoice") — डीलर को सेल दर्ज करें, प्रोडक्ट दर प्रोडक्ट
• record payment (या /record_payment) — डीलर से आया या सप्लायर को दिया पेमेंट लॉग करें

*सुधार (Corrections)*
• undo payment (या /undo_payment) — अभी record किया payment void करें
• undo order (या /undo_order) — अभी बनाया order void करें (सिर्फ़ अगर unpaid है)
• edit invoice (या /edit_invoice) — invoice का amount, date, या party सुधारें (सिर्फ़ unpaid पर)
• edit payment (या /edit_payment) — दर्ज किए payment का amount या date सुधारें

*आपका डेटा*
• export data (या /export_data) — पूरा बिज़नेस डेटा Excel में download link
• morning briefing (या /morning_briefing) — आज की ब्रीफ़िंग दोबारा भेजें

*रिपोर्ट्स और स्टेटमेंट्स* (इस महीने की, Excel + PDF जहाँ बताया गया है)
• ledger <name> — एक डीलर/सप्लायर का running-balance स्टेटमेंट, Excel + PDF, जैसे ledger Ram Traders
• sales register / purchase register (या दोनों के लिए "gst report") — GST register + summary
• payment register (या receipt register) — इस महीने की receipts & payments
• day book — इस महीने के सभी invoice और payment, एक ही लिस्ट में
• outstanding report (या aging report) — 0-30/31-60/61-90/90+ दिन के buckets, Excel + PDF

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
    "reports.inventory.more": (
        "\n\n…और {remaining} ज़्यादा — पूरी लिस्ट के लिए 'all inventory' भेजें।"
    ),
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
    "reports.invoices.more": (
        "\n\n…और {remaining} ज़्यादा — पूरी लिस्ट के लिए 'all invoices' भेजें।"
    ),
    "reports.invoices.line": "{number} — {party} — {amount} — {status} — {due}",
    "reports.unknown_party": "अज्ञात party",
    # ── Payments ───────────────────────────────────────────────────────────
    "reports.payments.none": "आपके पास अभी कोई पेमेंट दर्ज नहीं।",
    "reports.payments.label_recent": "हाल के पेमेंट",
    "reports.payments.label_all": "सभी पेमेंट",
    "reports.payments.header_partial": "💵 {label} ({count} of {total}):",
    "reports.payments.header_full": "💵 {label} ({count}):",
    "reports.payments.more": (
        "\n\n…और {remaining} ज़्यादा — पूरी लिस्ट के लिए 'all payments' भेजें।"
    ),
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
    "reports.export.ready": (
        "आपका latest Excel export तैयार है।\nDownload ({ttl} min valid): {link}"
    ),
    "reports.download.ready": (
        "आपका {report_name} ({period}) तैयार है।\nDownload ({ttl} min valid):\n{links}"
    ),
    "reports.ledger.not_found": "'{name}' से मिलता कोई डीलर या सप्लायर नहीं मिला।",
    # ── Help text ──────────────────────────────────────────────────────────
    "menu.help_text": _HELP_TEXT,
    # ── Onboarding ─────────────────────────────────────────────────────────
    "onboarding.intro": (
        "👋 OpsGenie में स्वागत है! चलिए आपका बिज़नेस सेट अप करें — 5 मिनट लगेंगे, "
        "और आप कभी भी रुककर जारी रख सकते हैं।\n\n"
        "सबसे पहले: आप किस तरह का बिज़नेस चलाते हैं? (जैसे FMCG Distributor, Pharma Distributor)"
    ),
    "onboarding.progress": "✅ Step {step}/{total} हो गया।",
    "onboarding.finish": (
        "🎉 सेटअप पूरा हो गया!\n\n"
        "कल सुबह से मैं आपको रोज़ की ब्रीफ़िंग भेजूँगा। आप मुझसे कुछ भी पूछ सकते हैं, जैसे:\n"
        "• Cash position\n"
        "• Ram को कितना देना है?\n"
        "• Supplier dues\n"
        "• Dealer risk\n\n"
        "कभी भी menu भेजें options tap करने के लिए, या /help पूरी लिस्ट देखने के लिए।"
    ),
    "onboarding.gst.mode_ask": (
        "क्या आपके सभी products का GST rate same है, या product के हिसाब से अलग? "
        "Reply करें 'same', 'varies', या 'not sure' बाद में तय करने के लिए।"
    ),
    "onboarding.gst.rate_ask": "आपका GST rate क्या है? (जैसे 5, 12, 18, या 0 अगर exempt)",
    "onboarding.gst.mode_invalid": "कृपया reply करें 'same', 'varies', या 'not sure'।",
    "onboarding.gst.rate_invalid": (
        "कृपया 0 से 100 के बीच number भेजें, जैसे 18 (या 'not sure' बाद में तय करने के लिए)।"
    ),
    "onboarding.product.intro": (
        "अब अपने products add करें। Reply 'one by one' एक-एक करके, या 'bulk' सब एक साथ "
        "पूरे details के साथ (जैसे Rice, 300, 400, kg, 100, 5)। 'done' skip करने के लिए।"
    ),
    "onboarding.product.bulk_format": (
        "अपने products एक line में एक, इस format में भेजें:\n"
        "Name, Purchase Price, Selling Price, Unit, Stock, GST%\n"
        "जैसे\n"
        "Rice, 300, 400, kg, 100, 5\n"
        "Dal, 320, 450, kg, 50, 12\n"
        "जो field सेट नहीं करनी उसके लिए 'skip' लिखें "
        "(जैसे Rice, skip, 400, kg, 100, skip)। हो जाए तो 'done' भेजें।"
    ),
    "onboarding.product.bulk_format_no_gst": (
        "अपने products एक line में एक, इस format में भेजें:\n"
        "Name, Purchase Price, Selling Price, Unit, Stock\n"
        "जैसे\n"
        "Rice, 300, 400, kg, 100\n"
        "Dal, 320, 450, kg, 50\n"
        "जो field सेट नहीं करनी उसके लिए 'skip' लिखें "
        "(जैसे Rice, skip, 400, kg, 100)। हो जाए तो 'done' भेजें।"
    ),
    "onboarding.product.first_name": (
        "अपने पहले product का नाम भेजें (जैसे Rice), या 'done' skip करने के लिए।"
    ),
    "onboarding.product.mode_invalid": (
        "कृपया reply करें 'one by one' या 'bulk' — या 'done' products skip करने के लिए।"
    ),
    "onboarding.product.bulk_added": (
        "{count} product add किए: {names}। और भेजें, या हो जाए तो 'done' भेजें।"
    ),
    "onboarding.product.quantity_ask": (
        "अभी आपके पास कितना {name} stock में है? (जैसे 100, या 'skip')"
    ),
    "onboarding.product.quantity_invalid": "कृपया एक number भेजें, जैसे 100 (या 'skip')।",
    "onboarding.product.unit": "यह किस unit में है? (जैसे kg, pcs, box, litre, या 'skip')",
    "onboarding.product.price_ask": "{name} की selling price क्या है? (जैसे 400, या 'skip')",
    "onboarding.product.price_invalid": "कृपया एक number भेजें, जैसे 400 (या 'skip')।",
    "onboarding.product.purchase_ask": (
        "{name} की purchase price (cost price) क्या है? (जैसे 300, या 'skip')"
    ),
    "onboarding.product.purchase_invalid": "कृपया एक number भेजें, जैसे 300 (या 'skip')।",
    "onboarding.product.gst_ask": (
        "{name} का GST% क्या है? (जैसे 5, 12, 18, या 'skip' बाद में तय करने के लिए)"
    ),
    "onboarding.product.gst_invalid": (
        "कृपया 0 से 100 के बीच number भेजें, जैसे 18 (या 'skip' बाद में तय करने के लिए)।"
    ),
    "onboarding.product.added": (
        "Product add किया: {name} ({stock} stock में)। और भेजें, या 'done'।"
    ),
    "onboarding.dealers.intro": (
        "अब अपने dealers (customers) add करें। Reply 'one by one' एक-एक करके add करने के लिए, "
        "या 'bulk' सबको एक साथ भेजने के लिए (जैसे Ram Traders, 9876543210, 15)। "
        "'done' skip करने के लिए।"
    ),
    "onboarding.dealer.bulk_format": (
        "अपने dealers एक line में एक, इस format में भेजें:\n"
        "Name, Phone, Credit Days\n"
        "जैसे\n"
        "Ram Traders, 9876543210, 15\n"
        "Shree Enterprises, 9123456780, 30\n"
        "जो field सेट नहीं करनी उसके लिए 'skip' लिखें "
        "(जैसे Ram Traders, skip, 15)। हो जाए तो 'done' भेजें।"
    ),
    "onboarding.dealer.first_name": (
        "अपने पहले dealer का नाम भेजें (जैसे Ram Traders), या 'done' skip करने के लिए।"
    ),
    "onboarding.dealer.mode_invalid": (
        "कृपया reply करें 'one by one' या 'bulk' — या 'done' dealers skip करने के लिए।"
    ),
    "onboarding.dealer.bulk_added": (
        "{count} dealer add किए: {names}। और भेजें, या हो जाए तो 'done' भेजें।"
    ),
    "onboarding.dealer.credit_ask": "{name} को आप कितने credit दिन देते हैं? (जैसे 15, या 'skip')",
    "onboarding.dealer.added": "Dealer {name} add किया। अगले dealer का नाम, या 'done'।",
    "onboarding.suppliers.intro": (
        "अब आपके suppliers। Reply 'one by one' एक-एक करके add करने के लिए, "
        "या 'bulk' सबको एक साथ भेजने के लिए (जैसे Metro Distributors, 9988776655, 30)। "
        "'done' skip करने के लिए।"
    ),
    "onboarding.supplier.bulk_format": (
        "अपने suppliers एक line में एक, इस format में भेजें:\n"
        "Name, Phone, Credit Days\n"
        "जैसे\n"
        "Metro Distributors, 9988776655, 30\n"
        "Suresh Wholesale, 9871234560, 15\n"
        "जो field सेट नहीं करनी उसके लिए 'skip' लिखें "
        "(जैसे Metro Distributors, skip, 30)। हो जाए तो 'done' भेजें।"
    ),
    "onboarding.supplier.first_name": (
        "अपने पहले supplier का नाम भेजें (जैसे Metro Distributors), या 'done' skip करने के लिए।"
    ),
    "onboarding.supplier.mode_invalid": (
        "कृपया reply करें 'one by one' या 'bulk' — या 'done' suppliers skip करने के लिए।"
    ),
    "onboarding.supplier.bulk_added": (
        "{count} supplier add किए: {names}। और भेजें, या हो जाए तो 'done' भेजें।"
    ),
    "onboarding.supplier.credit_ask": (
        "{name} आपको pay करने के लिए कितने दिन देता है? (जैसे 15/'skip')"
    ),
    "onboarding.supplier.added": "Supplier {name} add किया। अगले supplier का नाम, या 'done'।",
    "onboarding.party.phone_ask": "{name} का phone number? (या 'skip')",
    "onboarding.party.credit_invalid": "कृपया दिनों का number भेजें, जैसे 15 (या 'skip')।",
    "onboarding.bulk_error": "यह समझ नहीं आया: {error}",
    "onboarding.opening.ask": "अभी आपके बिज़नेस में कितना cash है? (जैसे 320000)",
    "onboarding.opening.invalid": "कृपया एक amount भेजें, जैसे 320000।",
    "onboarding.receivable.ask": "क्या किसी dealer पर अभी आपका पैसा बाकी है? (yes/no)",
    "onboarding.receivable.which": "कौन सा dealer आपको देना है? (नाम)",
    "onboarding.receivable.confirm_new": (
        "मेरे पास '{name}' नाम का dealer अभी नहीं है — नए dealer के रूप में add करें? (yes/no)"
    ),
    "onboarding.receivable.amount_ask": "{party} को आपको कितना देना है? (जैसे 42000)",
    "onboarding.receivable.amount_invalid": "कृपया एक amount भेजें, जैसे 42000।",
    "onboarding.receivable.date_ask": (
        "{party} से payment कब expect करते हैं? (जैसे Friday, 15 days, या next week)"
    ),
    "onboarding.receivable.recorded": (
        "{amount} {party} से record किया। कोई और dealer देना है? (yes/no)"
    ),
    "onboarding.payable.ask": "क्या कोई supplier payment pending है? (yes/no)",
    "onboarding.payable.which": "किस supplier को आप देना है? (नाम)",
    "onboarding.payable.confirm_new": (
        "मेरे पास '{name}' नाम का supplier अभी नहीं है — नए supplier के रूप में add करें? (yes/no)"
    ),
    "onboarding.payable.amount_ask": "आपको {party} को कितना देना है? (जैसे 82000)",
    "onboarding.payable.amount_invalid": "कृपया एक amount भेजें, जैसे 82000।",
    "onboarding.payable.date_ask": (
        "{party} को payment कब due है? (जैसे Friday, 15 days, या next week)"
    ),
    "onboarding.payable.recorded": (
        "{amount} {party} को record किया। कोई और supplier pending? (yes/no)"
    ),
    "onboarding.yes_no_invalid": "कृपया yes या no reply करें।",
    "onboarding.date_invalid": (
        "माफ़ करें, वह date समझ नहीं आई। Try करें जैसे Friday, 15 days, या next week।"
    ),
    "onboarding.briefing.ask": (
        "आख़िरी step — मैं आपकी morning briefing कब भेजूँ? Reply 7, 8, या 9।"
    ),
    "onboarding.briefing.invalid": "कृपया एक घंटा reply करें, जैसे 7, 8, या 9।",
    "onboarding.briefing.range": "कृपया सुबह 5 से 11 के बीच का घंटा चुनें (जैसे 7, 8, या 9)।",
    # Resume: progress checklist ("progress"/"status") and restart ("restart")
    "onboarding.section.business_type": "बिज़नेस टाइप",
    "onboarding.section.products": "प्रोडक्ट्स",
    "onboarding.section.dealers": "डीलर",
    "onboarding.section.suppliers": "सप्लायर",
    "onboarding.section.opening_balance": "ओपनिंग बैलेंस",
    "onboarding.section.receivables": "डीलर बकाया",
    "onboarding.section.payables": "सप्लायर बकाया",
    "onboarding.section.briefing_hour": "ब्रीफिंग टाइम",
    "onboarding.status.title": "📋 Setup progress — {percent}% पूरा हो गया।",
    "onboarding.status.section_done": "✅ {name}",
    "onboarding.status.section_current": "▶️ {name} (आप यहाँ हैं)",
    "onboarding.status.section_pending": "⬜ {name}",
    "onboarding.status.footer_generic": "जारी रखने के लिए अपना अगला जवाब reply करें।",
    "onboarding.status.restart_hint": "सेटअप फिर से शुरू करने के लिए 'restart' भेजें।",
    "onboarding.restart.confirm": (
        "⚠️ इससे अब तक भरी गई सारी जानकारी (products, dealers, suppliers, opening balance) मिट "
        "जाएगी और सेटअप शुरुआत से फिर होगा। पक्का करना चाहते हैं? (yes/no)"
    ),
    "onboarding.restart.cancelled": (
        "ठीक है — आपका सेटअप जारी है। ऊपर वाले आख़िरी सवाल का जवाब भेजें।"
    ),
    "onboarding.restart.done": (
        "🔄 सब कुछ मिट गया। चलिए फिर से शुरुआत से आपका बिज़नेस सेट अप करते हैं।\n\n"
        "पहला सवाल: आप किस तरह का बिज़नेस चलाते हैं? (जैसे FMCG Distributor, Pharma Distributor)"
    ),
    # ── Interactive menu ───────────────────────────────────────────────────
    "menu.fallback": "नीचे से एक विकल्प चुनें, या पूरी सूची के लिए /help भेजें।",
    "menu.msg.reports.body": "रिपोर्ट्स और अवलोकन — एक चुनें:",
    "menu.msg.reports.button": "रिपोर्ट चुनें",
    "menu.msg.inventory.body": "इन्वेंटरी, लेनदेन और प्रोडक्ट्स — एक चुनें:",
    "menu.msg.inventory.button": "एक विकल्प चुनें",
    "menu.msg.orders.body": "ऑर्डर, पेमेंट और आपका डेटा — एक चुनें:",
    "menu.msg.orders.button": "एक विकल्प चुनें",
    "menu.msg.statements.body": "रिपोर्ट्स और स्टेटमेंट्स — एक चुनें:",
    "menu.msg.statements.button": "स्टेटमेंट चुनें",
    "menu.msg.corrections.body": "सुधार — पहले से record की चीज़ें undo या edit करें:",
    "menu.msg.corrections.button": "सुधार",
    "menu.section.cash_overview": "नकद और अवलोकन",
    "menu.section.money_flow": "पैसे का प्रवाह",
    "menu.section.dealers_suppliers": "डीलर और सप्लायर",
    "menu.section.inventory_transactions": "इन्वेंटरी व लेनदेन",
    "menu.section.manage_products": "प्रोडक्ट्स मैनेज करें",
    "menu.section.orders_payments": "ऑर्डर और पेमेंट",
    "menu.section.manage_parties": "पार्टी मैनेज करें",
    "menu.section.your_data": "आपका डेटा",
    "menu.section.full_lists": "पूरी सूचियाँ",
    "menu.section.reports_statements": "रिपोर्ट्स और स्टेटमेंट्स",
    "menu.section.corrections": "सुधार",
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
    "menu.row.add_dealer.title": "Dealer Add करें",
    "menu.row.add_dealer.desc": "नया dealer add करें",
    "menu.row.add_supplier.title": "Supplier Add करें",
    "menu.row.add_supplier.desc": "नया supplier add करें",
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
    "menu.row.gst_report.title": "GST रिपोर्ट",
    "menu.row.gst_report.desc": "सेल्स और परचेज़ रजिस्टर, दोनों साथ",
    "menu.row.sales_register.title": "सेल्स रजिस्टर",
    "menu.row.sales_register.desc": "GST रजिस्टर + रेट-वाइज़ सारांश",
    "menu.row.purchase_register.title": "परचेज़ रजिस्टर",
    "menu.row.purchase_register.desc": "GST रजिस्टर + रेट-वाइज़ सारांश",
    "menu.row.payment_register.title": "पेमेंट रजिस्टर",
    "menu.row.payment_register.desc": "इस महीने की रसीद और पेमेंट",
    "menu.row.day_book.title": "डे बुक",
    "menu.row.day_book.desc": "इस महीने के सभी इनवॉइस और पेमेंट",
    "menu.row.outstanding_report.title": "आउटस्टैंडिंग रिपोर्ट",
    "menu.row.outstanding_report.desc": "0-30/31-60/61-90/90+ दिन के बकेट",
    "menu.row.undo_payment.title": "Undo Payment",
    "menu.row.undo_payment.desc": "अभी record किया payment void करें",
    "menu.row.undo_order.title": "Undo Order",
    "menu.row.undo_order.desc": "अभी बनाया order void करें",
    "menu.row.edit_invoice.title": "Edit Invoice",
    "menu.row.edit_invoice.desc": "invoice का amount, date, या party सुधारें",
    "menu.row.edit_payment.title": "Edit Payment",
    "menu.row.edit_payment.desc": "payment का amount या date सुधारें",
    "menu.row.edit_dealer.title": "Edit Dealer",
    "menu.row.edit_dealer.desc": "dealer का phone, limit, terms, GSTIN बदलें",
    "menu.row.edit_supplier.title": "Edit Supplier",
    "menu.row.edit_supplier.desc": "supplier का phone, limit, terms, GSTIN बदलें",
    "menu.row.stock_take.title": "Stock Take",
    "menu.row.stock_take.desc": "कई products का stock एक साथ बदलें",
    # ── Workflows (shared) ─────────────────────────────────────────────────
    "workflow.cancelled": "OK, cancel कर दिया।",
    "workflow.yes_no": "कृपया yes या no reply करें।",
    "workflow.error_restart": (
        "कुछ गड़बड़ हो गई। कृपया दोबारा '{trigger}' बोलकर शुरू करें।"
    ),
    "workflow.kind_dealer": "dealer",
    "workflow.kind_supplier": "supplier",
    # ── Record payment ─────────────────────────────────────────────────────
    "payment.start": "किसने आपको pay किया, या आपने किसको pay किया? (party का नाम)",
    "payment.need_party": "कृपया party का नाम बताएं।",
    "payment.amount_receivable": "उन्होंने आपको कितना pay किया? (जैसे 25000)",
    "payment.amount_payable": "आपने उन्हें कितना pay किया? (जैसे 25000)",
    "payment.disambiguation": (
        "'{name}' dealer और supplier दोनों से match करता है। "
        "Reply 1 अगर वो dealer हैं (उन्होंने आपको pay किया), "
        "या 2 अगर supplier हैं (आपने उन्हें pay किया)।"
    ),
    "payment.dealer_or_supplier_invalid": "कृपया dealer के लिए 1 या supplier के लिए 2 reply करें।",
    "payment.invoice_selection_invalid": "कृपया 1 से {count} के बीच number reply करें, या 'all'।",
    "payment.open_invoices": (
        "{party} के {count} open invoices हैं:\n{listing}\n"
        "एक number reply करें, या 'all' सब पर apply करने के लिए (पुराने पहले)।"
    ),
    "payment.open_invoice_line": (
        "{index}. {number} — {total} total, {outstanding} बाकी, due {due}"
    ),
    "payment.new_party_type": (
        "मेरे पास '{name}' नहीं है। वो dealer (customer) हैं या supplier "
        "(जिनसे आप खरीदते हैं)? Reply 1 Dealer या 2 Supplier।"
    ),
    "payment.new_party_type_invalid": "कृपया 1 Dealer या 2 Supplier reply करें।",
    "payment.add_new_party": "'{name}' को नया {kind} add करें? yes/no",
    "payment.no_open_invoice": (
        "मैं सिर्फ़ किसी existing invoice के against payment record कर सकता हूँ, और {party} "
        "का {kind} के रूप में कोई open invoice नहीं है। पहले उनके लिए invoice बनाएं, फिर "
        "'record payment' दोबारा बोलें।"
    ),
    "payment.got_it_no_invoice": "ठीक है। {message}",
    "payment.amount_invalid": "कृपया एक amount भेजें, जैसे 25000।",
    "payment.amount_positive": "कृपया zero से ज़्यादा amount भेजें।",
    "payment.date_ask": (
        "यह कब pay हुआ? Reply 'today', 'yesterday', '3 days ago', या skip आज के लिए।"
    ),
    "payment.date_invalid": (
        "माफ़ करें, वह date समझ नहीं आई। Try 'today', 'yesterday', '3 days ago'।"
    ),
    "payment.verb_from": "से",
    "payment.verb_to": "को",
    "payment.target_invoice": " invoice {number} के against",
    "payment.preview": (
        "Confirm: {amount} {party}{target} {verb} {date} को।\n"
        "Reply YES record करने के लिए, NO cancel के लिए।"
    ),
    # ── Create order ───────────────────────────────────────────────────────
    "order.start": "यह order किसके लिए है? (dealer का नाम)",
    "order.need_dealer": "कृपया dealer का नाम बताएं।",
    "order.dealer_found": "{dealer} के लिए order। कौन सा product?",
    "order.add_new_dealer": (
        "मेरे पास '{dealer}' dealer के रूप में नहीं है। उन्हें नया dealer add करें? yes/no"
    ),
    "order.new_dealer_added": "ठीक है, {dealer} को नया dealer add किया जाएगा। कौन सा product?",
    "order.need_one_product": "पहले कम से कम एक product add करें, या 'cancel'।",
    "order.need_product": "कृपया product का नाम बताएं, या 'done' अगर हो गया।",
    "order.quantity_ask": "{product} के कितने {unit}?",
    "order.price_ask": "{product} की selling price क्या है?",
    "order.add_new_product": "मेरे पास '{product}' catalogue में नहीं है। Add करें? yes/no",
    "order.new_product_declined": "ठीक है। कौन सा product? (या 'done')",
    "order.price_invalid": "कृपया एक price भेजें, जैसे 55।",
    "order.price_positive": "कृपया zero से ज़्यादा price भेजें।",
    "order.quantity_invalid": "कृपया एक quantity भेजें, जैसे 10।",
    "order.quantity_positive": "कृपया zero से ज़्यादा quantity भेजें।",
    "order.item_added": (
        "{quantity} x {product} add किया। और product add करें, या 'done' reply करें।"
    ),
    "order.line": "- {quantity} x {product} @ {price} = {total}",
    "order.subtotal": "Subtotal: {amount}",
    "order.gst": "GST{rate_label}: {amount}",
    "order.total": "Total: {amount}",
    "order.preview_header": "{dealer} के लिए order confirm करें:",
    "order.preview_footer": "Reply YES बनाने के लिए, NO cancel के लिए।",
    # ── Edit invoice / edit payment (safe cases only) ───────────────────────
    "edit.invoice_number_ask": "कौन सा invoice? उसका invoice number भेजें, या 'cancel'।",
    "edit.invoice_not_found": (
        "मुझे '{number}' नाम का invoice नहीं मिला। जांच कर दोबारा भेजें, या 'cancel'।"
    ),
    "edit.invoice_has_payment": (
        "Invoice {number} पर पहले से payment record है — पहले उसे void करें और "
        "दोबारा बनाएं।"
    ),
    "edit.field_ask_invoice": (
        "क्या edit करना है — amount, date, या party? "
        "Reply करें 'amount', 'date', या 'party'।"
    ),
    "edit.field_invalid_invoice": "कृपया reply करें 'amount', 'date', या 'party' — या 'cancel'।",
    "edit.amount_ask": "अभी का amount {current} है। नया amount क्या हो? (जैसे 1200)",
    "edit.date_ask": "अभी की date {current} है। नई date क्या हो? (जैसे 2026-01-15)",
    "edit.invoice_party_ask_dealer": "अभी का dealer {current} है। नए dealer का नाम भेजें।",
    "edit.invoice_party_ask_supplier": "अभी का supplier {current} है। नए supplier का नाम भेजें।",
    "edit.amount_invalid": "कृपया शून्य से बड़ा एक number भेजें, जैसे 1200।",
    "edit.date_invalid": "कृपया 2026-01-15 जैसी date भेजें।",
    "edit.party_not_found": "मुझे '{name}' नहीं मिला। spelling जांच कर दोबारा भेजें, या 'cancel'।",
    "edit.value_preview": "{target} का {field} बदलकर {new} करें?",
    "edit.target_invoice": "invoice {number}",
    "edit.target_payment": "invoice {number} का payment",
    "edit.reason_ask": "{preview}\nक्यों? छोटा सा reason भेजें, या 'skip'।",
    "edit.confirm_prompt": "{preview}\nConfirm करने के लिए YES भेजें, या NO cancel के लिए।",
    "edit.party_name_ask": (
        "किस dealer या supplier का payment edit करना है? उनका नाम भेजें, या 'cancel'।"
    ),
    "edit.no_payments_for_party": "{name} के लिए कोई payment नहीं मिला।",
    "edit.payment_pick_ask": (
        "{name} के लिए {count} हाल के payments मिले:\n{listing}\n"
        "Number भेजें, या 'cancel'।"
    ),
    "edit.payment_pick_invalid": "कृपया 1 से {count} के बीच एक number भेजें, या 'cancel'।",
    "edit.payment_gone": "वह payment अब उपलब्ध नहीं है। 'edit payment' कहकर दोबारा शुरू करें।",
    "edit.field_ask_payment": "क्या edit करना है — amount या date? Reply करें 'amount' या 'date'।",
    "edit.field_invalid_payment": "कृपया reply करें 'amount' या 'date' — या 'cancel'।",
    # ── Update GST ─────────────────────────────────────────────────────────
    "gst.scope_prompt": (
        "सभी products (company default) का GST update करें, या एक product का? "
        "Reply 'all' या product का नाम।"
    ),
    "gst.rate_ask_all": "{target} के लिए नया default GST rate क्या है? (0-100, या 'cancel')",
    "gst.rate_ask_product": (
        "{target} के लिए नया GST rate क्या है? (0-100, 'clear' override हटाने और company "
        "default use करने के लिए, या 'cancel')"
    ),
    "gst.not_found": (
        "'{name}' नाम का product नहीं मिला। Reply 'all', दूसरा product नाम, या 'cancel'।"
    ),
    "gst.rate_invalid": "कृपया 0 से 100 के बीच number भेजें, जैसे 18।",
    "gst.all_products": "सभी products",
    "gst.no_override": "कोई override नहीं (company default use करें)",
    "gst.rate_pct": "{rate}%",
    "gst.preview": "{target} का GST {rate_text} set करें। Reply YES confirm, NO cancel।",
    # ── Product ────────────────────────────────────────────────────────────
    "product.mode_prompt": (
        "चलिए products add करें। Reply 'one by one' एक-एक करके, या 'bulk' सब एक साथ "
        "पूरे details के साथ (जैसे Rice, 300, 400, kg, 100, 5)। कभी भी 'done' रोकने के लिए।"
    ),
    "product.no_products_added": "OK, कोई product add नहीं किया।",
    "product.all_done": "Products add करना हो गया।",
    "product.name_or_done": "Product का नाम भेजें (जैसे Rice), या 'done' रोकने के लिए।",
    "product.mode_invalid": "कृपया reply करें 'one by one' या 'bulk' — या 'done' रोकने के लिए।",
    "product.not_found_retry": (
        "'{name}' नाम का product नहीं मिला। Spelling check करके दोबारा try करें, या 'cancel'।"
    ),
    "product.disambiguation": (
        "'{name}' नाम के {count} products मिले:\n{listing}\n"
        "{action} करने के लिए number reply करें, या 'cancel'।"
    ),
    "product.disambiguation_invalid": "कृपया 1 से {count} के बीच number reply करें, या 'cancel'।",
    "product.candidate_line": "{index}. {description}",
    "product.candidate_desc": "{name} ({details})",
    "product.candidate_stock": "{stock} stock में",
    "product.gone": (
        "वह product अब available नहीं है। कृपया दोबारा '{trigger}' बोलकर शुरू करें।"
    ),
    "product.delete_name_prompt": "कौन सा product delete करना है? नाम भेजें, या 'cancel'।",
    "product.delete_confirm": (
        "{description} delete करें? यह undo नहीं होगा। Reply YES delete, NO cancel।"
    ),
    "product.delete_no": "OK, delete नहीं किया।",
    "product.delete_confirm_invalid": "कृपया YES delete के लिए, या NO cancel के लिए reply करें।",
    "product.delete_already_gone": "{name} पहले ही हटा दिया गया था।",
    "product.deleted": "{name} delete किया।",
    "product.field_prompt": (
        "क्या update करना है — price, purchase price, या stock? "
        "Reply 'price', 'purchase price', या 'stock'।"
    ),
    "product.action_update": "update",
    "product.action_delete": "delete",
    "product.label_price": "price",
    "product.label_purchase": "purchase price",
    "product.label_stock": "stock",
    "product.update_name_prompt": (
        "किस product की {label} update करनी है? नाम भेजें, या 'cancel'।"
    ),
    "product.current_price": (
        "{name} की अभी price {current} है। नई price क्या होनी चाहिए? (जैसे 450)"
    ),
    "product.current_purchase": (
        "{name} की अभी purchase price {current} है। "
        "नई purchase price क्या होनी चाहिए? (जैसे 300)"
    ),
    "product.current_stock": (
        "{name} का अभी stock {current} है। नया stock क्या होना चाहिए? (जैसे 100)"
    ),
    "product.value_invalid": "कृपया एक number भेजें, जैसे 450।",
    "product.value_nonneg": "कृपया zero या उससे ज़्यादा number भेजें।",
    "product.gone_value": "वह product अब available नहीं है।",
    "product.not_set": "set नहीं",
    "product.updated_price": "{name} की price {new} की (पहले {old} थी)।",
    "product.updated_purchase": "{name} की purchase price {new} की (पहले {old} थी)।",
    "product.updated_stock": "{name} का stock {new} किया (पहले {old} था)।",
    # ── Stock take (bulk stock recount/adjustment) ──────────────────────────
    "stock_take.start_prompt": (
        "चलिए stock take करते हैं। हर product के लिए, उसका नाम भेजें, फिर नया count "
        "(जैसे 40) या adjustment (जैसे +15 मिला, -3 खराब हुआ)। खत्म होने पर 'done' भेजें, "
        "या कभी भी 'cancel'।"
    ),
    "stock_take.line_prompt": "एक product का नाम भेजें, या खत्म करने के लिए 'done'।",
    "stock_take.value_ask": "{name} — नया count भेजें (जैसे 40) या adjustment (जैसे +15, -3)।",
    "stock_take.value_invalid": "कृपया एक number भेजें, जैसे 40, +15, या -3।",
    "stock_take.line_added": "{name}: {old} → {new}। अगला product भेजें, या 'done'।",
    "stock_take.nothing_to_apply": "ठीक है, कोई बदलाव नहीं हुआ।",
    "stock_take.reason_ask": "क्यों? छोटा सा reason भेजें, या 'skip'।",
    "stock_take.confirm_prompt": "{summary}\nApply करने के लिए YES भेजें, या NO cancel के लिए।",
    "stock_take.failed": "Stock take apply नहीं हो पाया: {error}। कृपया दोबारा शुरू करें।",
    "stock_take.result_line": "- {name}: {new}",
    "stock_take.success": "✅ {count} product(s) का stock update हुआ:\n{lines}{warning}",
    "party.dealer.mode_prompt": (
        "अपने dealers add करें। Reply 'one by one' एक-एक करके add करने के लिए, "
        "या 'bulk' सबको एक साथ भेजने के लिए (जैसे Ram Traders, 9876543210, 15)। "
        "'done' कभी भी रुकने के लिए।"
    ),
    "party.dealer.no_added": "ठीक है, कोई dealer add नहीं किया।",
    "party.dealer.all_done": "सभी dealers add हो गए।",
    "party.dealer.name_or_done": "Dealer का नाम भेजें (जैसे Ram Traders), या रुकने के लिए 'done'।",
    "party.dealer.mode_invalid": "कृपया reply करें 'one by one' या 'bulk' — या रुकने के लिए 'done'।",
    "party.supplier.mode_prompt": (
        "अपने suppliers add करें। Reply 'one by one' एक-एक करके add करने के लिए, "
        "या 'bulk' सबको एक साथ भेजने के लिए (जैसे Metro Distributors, 9988776655, 30)। "
        "'done' कभी भी रुकने के लिए।"
    ),
    "party.supplier.no_added": "ठीक है, कोई supplier add नहीं किया।",
    "party.supplier.all_done": "सभी suppliers add हो गए।",
    "party.supplier.name_or_done": (
        "Supplier का नाम भेजें (जैसे Metro Distributors), या रुकने के लिए 'done'।"
    ),
    "party.supplier.mode_invalid": (
        "कृपया reply करें 'one by one' या 'bulk' — या रुकने के लिए 'done'।"
    ),
    # ── Edit dealer / edit supplier (phone, credit limit, terms, GSTIN) ─────
    "party.edit.field_prompt": (
        "क्या edit करना है — phone, credit limit, payment terms, या GSTIN? "
        "Reply करें 'phone', 'credit limit', 'payment terms', या 'gstin'।"
    ),
    "party.edit.field_invalid": (
        "कृपया reply करें 'phone', 'credit limit', 'payment terms', या 'gstin' — या 'cancel'।"
    ),
    "party.edit.name_ask_dealer": "कौन सा dealer? उनका नाम भेजें, या 'cancel'।",
    "party.edit.name_ask_supplier": "कौन सा supplier? उनका नाम भेजें, या 'cancel'।",
    "party.edit.not_found": "मुझे '{name}' नहीं मिला। spelling जांच कर दोबारा भेजें, या 'cancel'।",
    "party.edit.disambiguation": (
        "'{name}' नाम के {count} matches मिले:\n{listing}\n"
        "Edit करने के लिए number भेजें, या 'cancel'।"
    ),
    "party.edit.disambiguation_invalid": "कृपया 1 से {count} के बीच एक number भेजें, या 'cancel'।",
    "party.edit.gone": "वह record अब उपलब्ध नहीं है। '{trigger}' कहकर दोबारा शुरू करें।",
    "party.edit.gone_value": "वह record अब उपलब्ध नहीं है।",
    "party.edit.phone_ask": "{name} का अभी का phone {current} है। नया phone क्या हो?",
    "party.edit.credit_limit_ask": (
        "{name} की अभी की credit limit {current} है। नई credit limit क्या हो? (जैसे 50000)"
    ),
    "party.edit.payment_terms_ask": (
        "{name} के अभी के payment terms {current} days हैं। नए terms दिनों में क्या हों? "
        "(जैसे 30)"
    ),
    "party.edit.gstin_ask": "{name} का अभी का GSTIN {current} है। नया GSTIN क्या हो?",
    "party.edit.days_invalid": "कृपया दिनों की एक पूरी संख्या भेजें, जैसे 30।",
    "party.edit.gstin_invalid": "वह सही GSTIN नहीं लगता। कृपया जांच कर दोबारा भेजें, या 'cancel'।",
    "party.edit.value_preview": "{name} का {field} बदलकर {new} करें?",
    "party.edit.success": "✅ {name} का {field} {new} हो गया (पहले {old} था)।",
    # ── Void payment / void order ───────────────────────────────────────────
    "void.payment_none": "Undo करने के लिए कोई WhatsApp payment नहीं मिला।",
    "void.payment_preview": "Invoice {invoice_number} के लिए {party} का {amount} payment void करें?",
    "void.order_none": "Undo करने के लिए कोई WhatsApp order नहीं मिला।",
    "void.order_has_payment": (
        "Order {invoice_number} पर पहले से payment record है — पहले payment void करें, "
        "फिर दोबारा कोशिश करें।"
    ),
    "void.order_preview": "{dealer} का order {invoice_number} void करें (total {total})?",
    "void.reason_ask": "{preview}\nक्यों? छोटा सा reason भेजें, या 'skip'।",
    "void.confirm_prompt": "{preview}\nVoid करने के लिए YES भेजें, या cancel के लिए NO।",
    # ── Pending-operation results ──────────────────────────────────────────
    "pending.reply_yes_no": "Reply YES confirm करने के लिए या NO cancel के लिए।",
    "pending.payment_failed": "वह payment record नहीं हो पाया: {error}। कृपया दोबारा शुरू करें।",
    "pending.payment_success": (
        "✅ {amount} {party} {verb} record किया।\n"
        "Invoices update हुए: {invoices}\n"
        "बाकी outstanding: {outstanding}"
    ),
    "pending.order_failed": "वह order नहीं बन पाया: {error}। कृपया दोबारा शुरू करें।",
    "pending.order_line": "- {quantity} x {product} = {total}",
    "pending.order_stock_warning": "\n⚠️ अब stock negative है: {products}",
    "pending.order_pdf_sent": "\nPDF {dealer} को भेजा।",
    "pending.order_pdf_not_sent": (
        "\n(PDF {dealer} को नहीं भेजा — phone नहीं है या WhatsApp delivery अभी set नहीं है।)"
    ),
    "pending.order_success": (
        "✅ Order {number} {dealer} के लिए बना।\n{lines}\n"
        "Subtotal: {subtotal}\nGST: {gst}\nTotal: {total}{warning}{pdf_note}"
    ),
    "pending.gst_failed": "GST update नहीं हो पाया: {error}। कृपया दोबारा शुरू करें।",
    "pending.gst_success": "✅ {target} का GST {rate} set किया।",
    "pending.gst_rate_default": "company default",
    "pending.void_payment_failed": "वह payment void नहीं हो पाया: {error}। कृपया दोबारा शुरू करें।",
    "pending.void_payment_success": (
        "✅ Invoice {invoice_number} के लिए {party} का {amount} payment void हो गया।"
    ),
    "pending.void_order_failed": "वह order void नहीं हो पाया: {error}। कृपया दोबारा शुरू करें।",
    "pending.void_order_success": (
        "✅ {dealer} का order {invoice_number} void हो गया (total {total})।"
    ),
    "pending.edit_invoice_failed": "वह invoice edit नहीं हो पाया: {error}। कृपया दोबारा शुरू करें।",
    "pending.edit_invoice_success": "✅ Invoice {number} का {field} {new} हो गया (पहले {old} था)।",
    "pending.edit_payment_failed": "वह payment edit नहीं हो पाया: {error}। कृपया दोबारा शुरू करें।",
    "pending.edit_payment_success": (
        "✅ Invoice {number} के payment का {field} {new} हो गया (पहले {old} था)।"
    ),
    "pending.unknown": "उस confirmation में कुछ गड़बड़ हो गई। कृपया दोबारा शुरू करें।",
    # ── Menu prompt / follow-up / notifications / evening ──────────────────
    "menu.prompt": "Reply करें 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk",
    "followup.message": (
        "📋 Payment Follow-Up\n\n"
        "{number} — {dealer} — {amount}\n"
        "Due date: आज\n\n"
        "Payment मिल गया?\n"
        "1. हाँ — पूरा amount\n"
        "2. Partial payment\n"
        "3. अभी तक नहीं"
    ),
    "followup.recorded_full": (
        "{amount} payment {dealer} से record किया।\n"
        "{number} बंद हो गया।\n"
        "बाकी: ₹0।\n"
        "Cash और कल की briefing update हो गई।"
    ),
    "followup.recorded_partial": (
        "{amount} partial payment record किया।\n"
        "{number} — {remaining} अभी बाकी।\n"
        "Cash और कल की briefing update हो गई।"
    ),
    "followup.invoice_gone": "वह invoice अब available नहीं। {menu_prompt}",
    "followup.ask_partial": "कितना मिला?",
    "followup.ask_expected_date": (
        "{dealer} से payment कब expect करते हैं?\nExample: Friday, 3 days, next week"
    ),
    "followup.confirm_invalid": "समझ नहीं आया। Reply 1, 2, या 3।",
    "followup.amount_invalid": "वह amount समझ नहीं आया। कृपया एक number भेजें, जैसे 25000।",
    "followup.date_invalid": "वह date समझ नहीं आई।\nExample: Friday, 3 days, next week",
    "followup.rescheduled": (
        "नोट किया। {number} follow-up {when} के लिए schedule किया।\n"
        "{dealer} कल की briefing में flag है।"
    ),
    "followup.error": "उस follow-up में कुछ गड़बड़ हो गई। {menu_prompt}",
    "notify.supplier_reminder": (
        "⏰ Payment Reminder\n\n"
        "{supplier} का {amount} payment {when} due है।\n"
        "{cash_line}\n"
        "कोई action की ज़रूरत नहीं जब तक cash position न बदले।"
    ),
    "notify.when_today": "आज",
    "notify.when_tomorrow": "कल",
    "notify.cash_line": "अभी available cash: {amount} — {sufficiency}",
    "notify.cash_sufficient": "काफ़ी है।",
    "notify.cash_insufficient": "कम पड़ सकता है।",
    "notify.dealer_alert": (
        "⚠ Collection Alert\n\n"
        "{dealer} — {amount} — अब {days} दिन overdue।\n"
        "3 दिन से कोई follow-up नहीं।\n"
        "Suggestion: नया order देने से पहले आज call करें।"
    ),
    "evening.header": "🌙 शाम का Business Summary",
    "evening.counts": (
        "Invoices बने: {invoices} · WhatsApp से Orders: {orders} · Payments record: {payments}"
    ),
    "evening.sales": "आज की Sales: {amount}",
    "evening.margin": "Sales Margin: {amount}",
    "evening.margin_excluded": " ({items} items, {amount} exclude — cost price नहीं है)",
    "evening.collections": "Collections: {amount}",
    "evening.supplier_payments": "Supplier Payments: {amount}",
    "evening.net_cash": "Net Cash Movement: {amount}",
    "evening.outstanding": "Outstanding Receivables: {amount}",
    "evening.priority_header": "Priority Actions:",
}
