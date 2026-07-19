// Onboarding wizard: 3 form steps + a personalized success view, all in one
// page. Step 2's "Continue" is the only call that creates the company
// (POST /onboard); step 3's "Activate Account" is the only call that turns
// it on (POST /onboard/{id}/activate). Everything else is client-side.
(function () {
  const LANGUAGE_LABELS = { en: "English", hi: "Hindi" };

  const card = document.getElementById("wizardCard");
  const waNumber = (card.dataset.waNumber || "").trim();
  const form = document.getElementById("wizardForm");
  const progress = document.getElementById("wizardProgress");

  const state = { step: 1, companyId: null };

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
            "This WhatsApp number is already registered — continuing to activation for that account.",
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

  async function activateAccount() {
    showBanner("step3Banner", "");
    const btn = document.getElementById("activateBtn");
    btn.disabled = true;
    btn.textContent = "Activating…";
    try {
      const resp = await fetch(`/onboard/${state.companyId}/activate`, { method: "POST" });
      const data = await resp.json();
      if (resp.ok) {
        renderSuccess();
        showStep(4);
      } else {
        showBanner("step3Banner", data.detail || "Something went wrong. Please try again.");
        btn.disabled = false;
        btn.textContent = "Activate Account";
      }
    } catch (err) {
      showBanner("step3Banner", "Network error. Please try again.");
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
    } else if (action === "activate") {
      activateAccount();
    }
  });

  showStep(1);
})();
