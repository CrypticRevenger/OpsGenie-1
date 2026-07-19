// Onboarding wizard: 5 steps in one page (Account, Business, Import, Activate,
// Success). Step 2's "Continue" is the only call that creates the company
// (POST /onboard); step 3's "Import & Continue" optionally uploads a
// dealer-invoices and/or supplier-invoices file (POST /onboard/{id}/import,
// once per file present) and shows a reconciliation summary before letting
// the distributor move on; step 4's "Activate Account" is the only call that
// turns the company on (POST /onboard/{id}/activate). Everything else is
// client-side.
(function () {
  const LANGUAGE_LABELS = { en: "English", hi: "Hindi" };

  const card = document.getElementById("wizardCard");
  const waNumber = (card.dataset.waNumber || "").trim();
  const form = document.getElementById("wizardForm");
  const progress = document.getElementById("wizardProgress");

  const state = { step: 1, companyId: null, importSummaryShown: false, importSummary: null };

  function showStep(step) {
    state.step = step;
    form.querySelectorAll(".wizard-step").forEach((el) => {
      el.classList.toggle("is-active", Number(el.dataset.step) === step);
    });
    progress.querySelectorAll(".dot").forEach((dot) => {
      const dotStep = Number(dot.dataset.step);
      dot.classList.toggle("is-active", dotStep === step);
      dot.classList.toggle("is-done", dotStep < step);
    });
  }

  function setFieldError(fieldId, message) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    const errorEl = field.querySelector(".field-error");
    if (message) {
      field.classList.add("has-error");
      if (errorEl) errorEl.textContent = message;
    } else {
      field.classList.remove("has-error");
      if (errorEl) errorEl.textContent = "";
    }
  }

  function showBanner(bannerId, message, variant) {
    const banner = document.getElementById(bannerId);
    if (!banner) return;
    banner.classList.remove("is-error", "is-warning");
    if (message) {
      banner.textContent = message;
      banner.classList.add("is-visible", variant === "warning" ? "is-warning" : "is-error");
    } else {
      banner.classList.remove("is-visible");
    }
  }

  function val(name) {
    const el = form.elements[name];
    return el ? el.value.trim() : "";
  }

  // Indian digit grouping (lakhs/crores), mirroring app/services/money_format.py's
  // format_inr — paise shown only when non-zero.
  function formatINR(amount) {
    const num = Number(amount) || 0;
    const sign = num < 0 ? "-" : "";
    const [intPart, fracPart] = Math.abs(num).toFixed(2).split(".");
    let rest = intPart;
    const groups = [];
    if (rest.length > 3) {
      groups.unshift(rest.slice(-3));
      rest = rest.slice(0, -3);
      while (rest.length > 2) {
        groups.unshift(rest.slice(-2));
        rest = rest.slice(0, -2);
      }
      if (rest) groups.unshift(rest);
    } else {
      groups.unshift(rest);
    }
    const suffix = fracPart === "00" ? "" : `.${fracPart}`;
    return `${sign}₹${groups.join(",")}${suffix}`;
  }

  function validateStep1() {
    setFieldError("field_whatsapp_number", "");
    const required = ["business_name", "owner_name", "whatsapp_number"];
    for (const name of required) {
      if (!val(name)) {
        form.elements[name].focus();
        return false;
      }
    }
    return true;
  }

  async function registerCompany() {
    showBanner("step2Banner", "");
    const btn = form.querySelector('[data-action="register"]');
    btn.disabled = true;
    const body = {
      business_name: val("business_name"),
      owner_name: val("owner_name"),
      whatsapp_number: val("whatsapp_number"),
      email: val("email") || null,
      business_type: val("business_type") || null,
      preferred_language: val("preferred_language") || "en",
      city: val("city") || null,
      gst_number: val("gst_number") || null,
    };
    try {
      const resp = await fetch("/onboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (resp.ok) {
        state.companyId = data.company_id;
        if (data.status === "already_registered") {
          showBanner(
            "step3Banner",
            "This WhatsApp number is already registered — continuing for that account.",
            "warning"
          );
        }
        showStep(3);
      } else if (resp.status === 422) {
        // Almost always the WhatsApp number — send the user back to fix it.
        setFieldError("field_whatsapp_number", data.detail || "That number doesn't look right.");
        showStep(1);
      } else if (resp.status === 503) {
        showBanner("step2Banner", data.detail || "Onboarding is not available right now.");
      } else if (resp.status === 409) {
        // Founder-number collision (app/services/onboarding.py's
        // FounderNumberConflictError) — a deliberate rejection with a real
        // reason, not a generic failure. Send the user back to fix the
        // number instead of leaving them stuck on step 2.
        setFieldError("field_whatsapp_number", data.detail || "That number can't be used.");
        showStep(1);
      } else {
        showBanner("step2Banner", "Something went wrong. Please try again.");
      }
    } catch (err) {
      showBanner("step2Banner", "Network error. Please try again.");
    } finally {
      btn.disabled = false;
    }
  }

  async function uploadImportFile(direction, file) {
    const resp = await fetch(`/onboard/${state.companyId}/import?direction=${direction}`, {
      method: "POST",
      body: (() => {
        const formData = new FormData();
        formData.append("file", file);
        return formData;
      })(),
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || "Something went wrong importing that file.");
    }
    return data; // OnboardImportResponse: { import_result, summary }
  }

  function renderImportSummary(summary, rowProblems) {
    const totalInvoices = summary.receivable_invoice_count + summary.payable_invoice_count;
    const rows = [
      ["Invoices imported", totalInvoices],
      ["Dealers", summary.dealer_count],
      ["Suppliers", summary.supplier_count],
      ["Receivable (owed to you)", formatINR(summary.receivable_total)],
      ["Payable (you owe)", formatINR(summary.payable_total)],
    ];
    const summaryEl = document.getElementById("importSummary");
    summaryEl.innerHTML = rows
      .map(([label, value]) => `<div class="row"><span>${label}</span><span>${value}</span></div>`)
      .join("");
    summaryEl.style.display = "";
    document.getElementById("importUploadFields").style.display = "none";

    if (rowProblems.length > 0) {
      showBanner(
        "step3Banner",
        `${rowProblems.length} row(s) couldn't be imported and were skipped — you can add those individually later.`,
        "warning"
      );
    } else {
      showBanner("step3Banner", "");
    }

    state.importSummaryShown = true;
    state.importSummary = summary;
    const btn = document.getElementById("importBtn");
    btn.textContent = "Looks good — Continue";
  }

  async function handleImportAction() {
    if (state.importSummaryShown) {
      showStep(4);
      return;
    }
    const receivableFile = form.elements["import_receivable_file"].files[0];
    const payableFile = form.elements["import_payable_file"].files[0];
    if (!receivableFile && !payableFile) {
      showStep(4);
      return;
    }
    showBanner("step3Banner", "");
    const btn = document.getElementById("importBtn");
    btn.disabled = true;
    btn.textContent = "Importing…";
    try {
      let lastResponse = null;
      const rowProblems = [];
      if (receivableFile) {
        lastResponse = await uploadImportFile("receivable", receivableFile);
        rowProblems.push(...lastResponse.import_result.errors);
      }
      if (payableFile) {
        lastResponse = await uploadImportFile("payable", payableFile);
        rowProblems.push(...lastResponse.import_result.errors);
      }
      renderImportSummary(lastResponse.summary, rowProblems);
    } catch (err) {
      showBanner("step3Banner", err.message || "Network error. Please try again.");
      btn.textContent = "Import & Continue";
    } finally {
      btn.disabled = false;
    }
  }

  function skipImport() {
    showBanner("step3Banner", "");
    showStep(4);
  }

  async function activateAccount() {
    showBanner("step4Banner", "");
    const btn = document.getElementById("activateBtn");
    btn.disabled = true;
    btn.textContent = "Activating…";
    try {
      const resp = await fetch(`/onboard/${state.companyId}/activate`, { method: "POST" });
      const data = await resp.json();
      if (resp.ok) {
        renderSuccess();
        showStep(5);
      } else {
        showBanner("step4Banner", data.detail || "Something went wrong. Please try again.");
        btn.disabled = false;
        btn.textContent = "Activate Account";
      }
    } catch (err) {
      showBanner("step4Banner", "Network error. Please try again.");
      btn.disabled = false;
      btn.textContent = "Activate Account";
    }
  }

  function renderSuccess() {
    const ownerFirstName = (val("owner_name") || "").split(" ")[0] || "there";
    document.getElementById("successTitle").textContent = `Welcome, ${ownerFirstName}.`;

    const rows = [];
    const businessType = val("business_type");
    const language = LANGUAGE_LABELS[val("preferred_language")] || val("preferred_language");
    const city = val("city");
    if (businessType) rows.push(["Business", businessType]);
    if (language) rows.push(["Language", language]);
    if (city) rows.push(["City", city]);
    if (state.importSummary) {
      const totalInvoices =
        state.importSummary.receivable_invoice_count + state.importSummary.payable_invoice_count;
      if (totalInvoices > 0) rows.push(["Imported", `${totalInvoices} invoices`]);
    }
    document.getElementById("successSummary").innerHTML = rows
      .map(([label, value]) => `<div class="row"><span>${label}</span><span>${value}</span></div>`)
      .join("");

    const waBtn = document.getElementById("waContinueBtn");
    if (waNumber) {
      const digits = waNumber.replace(/[^\d]/g, "");
      waBtn.href = `https://wa.me/${digits}?text=${encodeURIComponent("Hi")}`;
      waBtn.style.display = "";
    }
  }

  form.addEventListener("click", (event) => {
    const action = event.target.dataset.action;
    if (!action) return;
    event.preventDefault();
    if (action === "next") {
      if (validateStep1()) showStep(2);
    } else if (action === "back") {
      showStep(state.step - 1);
    } else if (action === "register") {
      if (validateStep1()) registerCompany();
      else showStep(1);
    } else if (action === "import") {
      handleImportAction();
    } else if (action === "skip-import") {
      skipImport();
    } else if (action === "activate") {
      activateAccount();
    }
  });

  showStep(1);
})();
