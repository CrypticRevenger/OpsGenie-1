// Delete-confirm helper for the OpsGenie dashboard.
//
// Two opt-in behaviors, both triggered by data attributes on a <form>:
//   data-confirm="..."              plain confirm() before submitting
//   data-delete-preview-url="..."   fetch the real cascade-delete impact
//                                    (dealers/suppliers) and fold it into
//                                    the confirm() text before submitting
//
// Every delete form on the page is a real HTML <form method="post">, so
// this is a progressive-enhancement layer — nothing here is required for
// the delete to work, only for the extra confirmation step.
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;

  const previewUrl = form.getAttribute("data-delete-preview-url");
  const plainConfirm = form.getAttribute("data-confirm");

  if (previewUrl) {
    event.preventDefault();
    if (form.dataset.confirmed === "true") {
      form.submit();
      return;
    }
    const subject = form.getAttribute("data-confirm-subject") || "this record";
    let message = `Delete ${subject}?`;
    try {
      const resp = await fetch(previewUrl, { credentials: "same-origin" });
      if (resp.ok) {
        const data = await resp.json();
        if (data.invoice_count > 0) {
          message =
            `Delete ${subject}? This will also permanently delete ` +
            `${data.invoice_count} invoice(s) totaling ₹${data.total_amount}.`;
        } else {
          message = `Delete ${subject}? It has no invoices.`;
        }
      }
    } catch (err) {
      // Network hiccup fetching the preview — fall back to the generic
      // message rather than blocking the delete entirely.
    }
    if (window.confirm(message)) {
      form.dataset.confirmed = "true";
      form.submit();
    }
    return;
  }

  if (plainConfirm && form.dataset.confirmed !== "true") {
    event.preventDefault();
    if (window.confirm(plainConfirm)) {
      form.dataset.confirmed = "true";
      form.submit();
    }
  }
});
