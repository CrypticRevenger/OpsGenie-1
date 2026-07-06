Here is a draft plan to refine:
Code review pass + commit/push
# Password-gated Admin Dashboard

## Context

The founder currently manages OpsGenie entirely through curl calls against the
`X-API-Key`-gated JSON admin API. That's fine for spot-checks but painful for
routine operations (pausing a company, checking a dealer's outstanding
balance, cleaning up test data). The ask: a browser-based dashboard, gated by
a simple password login, that can do everything the admin API can do —
create/view/pause/delete companies, and full CRUD on dealers/suppliers/
products/FAQs — plus safe view+delete for invoices/payments (never create/edit
those directly, since real invoice/payment writes must stay on the FIFO-aware
guided-workflow/import paths per this project's own "writes are workflows"
principle).

Key decisions already made with the user:
- Password lives in `.env` as `DASHBOARD_PASSWORD` (not hardcoded in source —
  this repo is public on GitHub; a literal password in a committed .py file
  would be permanently visible in git history).
- Company page has three distinct actions: **Activate**, **Pause**
  (deactivate — reversible, keeps data), **Delete** (irreversible, wipes
  everything) — the first two endpoints already exist; delete already exists too.
- Dealers/suppliers/products/FAQs get full CRUD in the dashboard. FAQs and
  product-edit already exist; dealer/supplier PATCH+DELETE and product DELETE
  are new.
- Invoices/payments are view + delete only — no create/edit forms, ever.
- Dealer/supplier delete has a real DB landmine to handle (see below).

## The dealer/supplier delete landmine

`invoices` has `CheckConstraint("dealer_id IS NOT NULL OR supplier_id IS NOT
NULL")`, and `invoices.dealer_id`/`invoices.supplier_id` are both
`ForeignKey(..., ondelete="SET NULL")` (`app/models/invoice.py`). A plain
`DELETE FROM dealers WHERE id=...` makes Postgres try to `SET NULL` on that
dealer's invoices — which then violates the CHECK constraint (since
`supplier_id` is also null on those rows) and the delete fails for any dealer
that has invoices (i.e. almost always). `invoice_items.invoice_id` and
`payments.invoice_id` are `ondelete="CASCADE"` from `invoices`, so the fix is:
delete that dealer's invoices first (`DELETE FROM invoices WHERE dealer_id =
:id` — cascades to items+payments automatically), then delete the dealer, one
commit. Products have no such issue (`invoice_items.product_id` is a plain
`SET NULL`, no CHECK) — product delete is a plain row delete.

## Backend: new JSON admin endpoints

Mirror `app/api/admin/faq.py`'s existing PATCH/DELETE shape exactly
(`_get_company_or_404` + a small `_get_X_or_404` helper, `model_dump
(exclude_unset=True)` + `setattr` loop for PATCH, `db.delete` + commit for
plain deletes).

1. **`app/schemas/dealer.py`** — add `DealerUpdate` (all `DealerCreate` fields
   as `X | None = None`, same validators guarded with `if v is not None`).
   **`app/schemas/supplier.py`** — add `SupplierUpdate` analogously.

2. **`app/api/admin/dealers.py`** — add:
   - `PATCH /{dealer_id}` — standard partial update.
   - `DELETE /{dealer_id}` — delete `Invoice` rows where `dealer_id == :id`
     first, then the dealer, in one commit (see landmine above). Log a line
     noting how many invoices were cascade-removed.
   - `GET /{dealer_id}/delete-preview` — returns `{"invoice_count": int,
     "total_amount": Decimal}` so the dashboard can show a real confirm
     message ("this dealer has 12 invoices totaling ₹45,000") before
     submitting the delete. Small dedicated endpoint rather than bloating
     `DealerResponse` for every other caller.

3. **`app/api/admin/suppliers.py`** — identical shape (PATCH, DELETE with the
   same invoice-cascade-first logic keyed on `supplier_id`, delete-preview).

4. **`app/api/admin/products.py`** — add `DELETE /{product_id}` (plain
   `db.delete` + commit, no cascade concern).

5. **`app/api/admin/invoices.py`** — add `DELETE /{invoice_id}` (plain
   `db.delete` — cascades to items+payments via existing FKs). Log a warning
   that this doesn't re-run FIFO reconciliation and outstanding balances on
   other invoices should be spot-checked afterward (accepted risk).

6. **`app/api/admin/payments.py`** — add `DELETE /{payment_id}` (plain
   delete, no dependents, same warning-log convention).

## Backend: dashboard auth

**`app/core/config.py`** — add `dashboard_password: str | None =
Field(default=None, alias="DASHBOARD_PASSWORD")`, same fail-closed convention
as `admin_api_key` (unset → login always rejects).

**`app/core/dashboard_auth.py`** (new) — a deliberately simple single-shared-
secret cookie session, same trust model as `ADMIN_API_KEY` itself (no
rotation/expiry-by-design, acceptable for a solo-founder internal tool; easy
to harden later):
- `DashboardAuthRequired(Exception)` — raised when the session cookie is
  missing/wrong.
- `verify_password(password) -> bool` — `secrets.compare_digest` against
  `settings.dashboard_password` (`False` if unset — fails closed).
- `issue_session_cookie(response, is_development)` — sets `HttpOnly`,
  `SameSite=Lax`, `secure=not is_development`, `max_age=14 days`, cookie
  named `opsgenie_dashboard_session`, value = `sha256(dashboard_password)`.
- `require_dashboard_session(request) -> None` — FastAPI dependency; compares
  the cookie to the same hash via `compare_digest`; raises
  `DashboardAuthRequired` on any mismatch/missing/unset-password.

**`app/core/exceptions.py`** — register a handler for `DashboardAuthRequired`
that returns `RedirectResponse("/dashboard/login", status_code=303)` instead
of the generic JSON error response (this is a browser flow, not an API
caller). FastAPI dispatches by exact exception type first, so this coexists
safely with the existing catch-all `Exception` handler regardless of
registration order.

## Backend: dashboard routes

New `app/api/dashboard/` package, one file per resource (mirrors
`app/api/admin/`'s split):

```
app/api/dashboard/__init__.py   # prefix="/dashboard", aggregates sub-routers
  auth.py         # GET/POST /login (no auth dep), POST /logout
  companies.py    # list, create form, detail hub, activate/pause/delete
  dealers.py      # create/edit/delete (+ delete-preview passthrough)
  suppliers.py    # same shape
  products.py     # create/edit/delete
  faqs.py         # create/edit/delete
  invoices.py     # list (filtered), delete
  payments.py     # list, delete
  briefing.py     # generate, view latest
  cashflow.py     # view snapshot
  followup.py     # trigger send-due-today
  imports.py      # CSV/Excel upload form
```

Every sub-router except `auth.py` carries `dependencies=[Depends
(require_dashboard_session)]`. Each handler directly imports and awaits the
corresponding `app/api/admin/*.py` function in-process (plain async function
calls, not an HTTP round-trip — e.g. `from app.api.admin.dealers import
delete_dealer as api_delete_dealer`), catching `HTTPException` to re-render
the page with an inline error instead of letting JSON bubble up, then
`RedirectResponse(..., status_code=303)` on success. This reuses every bit of
existing business logic instead of duplicating it.

**`app/main.py`** — register `dashboard_router` normally (its own auth is
internal to its sub-routers) — deliberately **not** wrapped in
`Depends(require_api_key)`, since a browser can't attach a custom header on
normal navigation.

## Templates & static assets

Dashboard gets its own minimal layout, not the marketing site's `base.html`
(irrelevant nav/hero/footer for an internal tool):

- `app/templates/dashboard/_layout.html` — bare shell, small top bar
  (business context + logout link), links new `app/static/css/dashboard.css`.
- `login.html` — password field, error slot.
- `companies_list.html` — table + create form/link.
- `company_detail.html` — header with Activate/Pause/Delete buttons (delete
  always behind a JS `confirm()`), then stacked sections: dealers, suppliers,
  products, FAQs (each: table + inline create form + edit/delete per row),
  invoices (paginated, filterable, delete per row), payments (same),
  briefing (latest text + "Generate" button), cashflow snapshot, followup
  ("Send due today" button), imports (upload form).
- `app/static/js/dashboard.js` (new, small) — the delete-confirm helper:
  fetches `.../delete-preview` for dealers/suppliers and injects the real
  impact count into the `confirm()` text before submitting.

## `.env` / `.env.example`

- `.env`: add `DASHBOARD_PASSWORD=spandan`.
- `.env.example`: add `DASHBOARD_PASSWORD=` (empty, matching the existing
  convention for every other secret in that file).

## Build order

1. `dashboard_password` config + `.env`/`.env.example`.
2. `DealerUpdate`/`SupplierUpdate` schemas.
3. New admin endpoints (dealers, suppliers, products, invoices, payments) —
   one file at a time, tests immediately after each, full suite green before
   moving on.
4. `app/core/dashboard_auth.py` + exception handler + its own tests (a stub
   protected route is enough before templates exist).
5. `app/api/dashboard/auth.py` + minimal login template — get the full
   login round-trip working end to end.
6. `companies.py` dashboard routes + templates (list/detail/three actions) —
   the hub page everything else hangs off.
7. Remaining resource route files + template sections, one at a time:
   dealers, suppliers, products, faqs, invoices, payments, briefing,
   cashflow, followup, imports.
8. `dashboard.css`/`dashboard.js`.
9. Full pytest run; manual click-through of the whole dashboard against
   local dev DB.

## Tests (new, mirroring `tests/test_admin_faq.py`'s real-Postgres convention)

- `tests/test_admin_dealers.py` (new file — none exists yet): update, delete
  (no invoices), **delete cascades invoices+payments+items** (the important
  one — create a dealer with an invoice+payment, delete, assert all three
  child rows are gone), delete-preview counts, delete-nonexistent-404.
- `tests/test_admin_suppliers.py` (new) — same set, supplier-flavored.
- `tests/test_admin_products.py` — add delete, delete-with-invoice-items
  (asserts `invoice_item.product_id` goes null, invoice itself survives).
- `tests/test_admin_invoices.py` / `test_admin_payments.py` — add delete
  tests (cascade check for invoices).
- `tests/test_dashboard_auth.py` (new) — login success sets cookie, wrong
  password re-renders form, unset password fails closed, protected route
  redirects (303) when unauthenticated, company list renders 200 once
  authenticated.

## Verification

- `./.venv-uv/Scripts/python.exe -m pytest` full suite green, `ruff check .`
  clean.
- Manual click-through against local dev Postgres: log in, view company
  list, open the real AP-BIOCARE-style test data or a fresh test company,
  exercise activate/pause/delete, create+edit+delete a dealer with real
  invoices attached (confirm the cascade warning text and the actual
  cascade), delete a product/invoice/payment, generate a briefing, trigger
  a follow-up send, upload a CSV import.
- Structured code review (reuse project's standard multi-angle pass) before
  calling this done, given the size of the change and the destructive-delete
  surface area involved.