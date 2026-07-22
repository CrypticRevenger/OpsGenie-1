# OpsGenie API Reference
**Version 0.0.0 · Phase 2 · `b49a372`**

> Interactive docs available at `http://localhost:8000/docs` when the server is running.

---

## Overview

Base URL: `http://localhost:8000` (development)

All endpoints accept and return `application/json`.
Monetary values (`opening_balance`, `credit_limit`) are strings in decimal notation — never floating-point — to avoid rounding errors.
Timestamps are ISO 8601 with timezone (`2026-07-01T14:00:00Z`).

### Authentication
Every `/admin/*` route requires a shared secret via the `X-API-Key` header, checked against
`ADMIN_API_KEY` in the server's environment. `/health` is intentionally unauthenticated (for
infra probes). There is no per-user login — this is still a single-founder tool, per SPEC.md:
"Authentication / API keys | When external users are onboarded." A missing/wrong key, or a
server with `ADMIN_API_KEY` unset, all return the same generic response:

```json
{ "detail": "Unauthorized" }
```

with status `401`. The reason is intentionally not distinguished in the response — logged
server-side only.

**Example request**
```
GET /admin/companies
X-API-Key: <your ADMIN_API_KEY>
```

### Pagination
Every list endpoint (`GET /admin/companies`, `.../dealers`, `.../suppliers`, `.../invoices`,
`.../payments`) accepts `?page=&limit=` (`page` 1-indexed, default `1`; `limit` default `50`,
max `200`) and returns a wrapped response instead of a bare array:

```json
{
  "items": [ ... ],
  "total": 127,
  "page": 2,
  "limit": 50,
  "pages": 3
}
```

`total`/`pages` reflect whatever filters were applied to that request (e.g. `direction`/`status`
on invoices) — not the company's full unfiltered count.

---

## Health

### `GET /health`

Returns the application and database health status.

**Response 200**
```json
{
  "status": "ok",
  "version": "0.0.0",
  "database": "connected"
}
```

---

## Admin — Companies

### `POST /admin/companies`

Create a new B2B distributor company.

**Request body** — all fields unless marked optional are required.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `business_name` | string | ✅ | Trading name of the distributor |
| `owner_name` | string | ✅ | Full name of the owner |
| `whatsapp_number` | string | ✅ | E.164 format — must start with `+` followed by digits only, e.g. `+919876543210` |
| `email` | string | optional | |
| `business_type` | string | optional | e.g. `"FMCG"`, `"Pharma"` |
| `preferred_language` | string | optional | Default `"en"` |
| `opening_balance` | decimal string | optional | Default `"0"`. Must be ≥ 0. |

**Example request**
```json
{
  "business_name": "Sharma Distributors",
  "owner_name": "Rajesh Sharma",
  "whatsapp_number": "+919876543210",
  "email": "rajesh@sharma.com",
  "business_type": "FMCG",
  "opening_balance": "150000.00"
}
```

**Response 201 — created**
```json
{
  "id": "018f3b2a-1c4d-7e8f-9a0b-1c2d3e4f5a6b",
  "business_name": "Sharma Distributors",
  "owner_name": "Rajesh Sharma",
  "whatsapp_number": "+919876543210",
  "email": "rajesh@sharma.com",
  "business_type": "FMCG",
  "preferred_language": "en",
  "subscription_active": true,
  "opening_balance": "150000.00",
  "created_at": "2026-07-01T14:00:00Z"
}
```

**Error responses**

| Status | When |
|--------|------|
| `409 Conflict` | A company with that `whatsapp_number` already exists |
| `422 Unprocessable Entity` | Validation failed (e.g. `whatsapp_number` not in E.164 format, `opening_balance` negative) |

**409 example**
```json
{
  "detail": "A company with WhatsApp number '+919876543210' already exists."
}
```

**422 example** (bad phone format)
```json
{
  "detail": [
    {
      "loc": ["body", "whatsapp_number"],
      "msg": "Value error, whatsapp_number must be in E.164 format, e.g. +919876543210",
      "type": "value_error"
    }
  ]
}
```

---

### `GET /admin/companies`

List all companies, ordered by `created_at` descending (newest first).

**Query parameters**

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `page` | integer | `1` | 1-indexed |
| `limit` | integer | `50` | Max `200` |

**Response 200** — `Page<CompanyResponse>`
```json
{
  "items": [
    {
      "id": "018f3b2a-...",
      "business_name": "Sharma Distributors",
      ...
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 50,
  "pages": 1
}
```

---

### `GET /admin/companies/{company_id}`

Get a single company by UUID.

**Path parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `company_id` | UUID | The company's `id` |

**Response 200** — `CompanyResponse`

**Error responses**

| Status | When |
|--------|------|
| `404 Not Found` | No company with that ID |

---

## Admin — Dealers

Dealers are customers of the distributor. All dealer operations are scoped to a parent company.

### `POST /admin/companies/{company_id}/dealers`

Add a dealer to a company.

**Path parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `company_id` | UUID | The parent company's `id` |

**Request body**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | ✅ | |
| `phone` | string | optional | |
| `address` | string | optional | |
| `gst_number` | string | optional | GST registration number |
| `payment_terms_days` | integer | optional | Must be > 0, e.g. `30` |
| `credit_limit` | decimal string | optional | Must be ≥ 0 |
| `notes` | string | optional | |

**Example request**
```json
{
  "name": "Kapoor Retail",
  "phone": "+919988776655",
  "payment_terms_days": 30,
  "credit_limit": "50000.00",
  "gst_number": "29ABCDE1234F1Z5"
}
```

**Response 201 — created**
```json
{
  "id": "019a4c3b-2d5e-8f9a-0b1c-2d3e4f5a6b7c",
  "company_id": "018f3b2a-1c4d-7e8f-9a0b-1c2d3e4f5a6b",
  "name": "Kapoor Retail",
  "phone": "+919988776655",
  "address": null,
  "gst_number": "29ABCDE1234F1Z5",
  "payment_terms_days": 30,
  "credit_limit": "50000.00",
  "notes": null,
  "created_at": "2026-07-01T14:05:00Z"
}
```

**Error responses**

| Status | When |
|--------|------|
| `404 Not Found` | `company_id` does not exist |
| `422 Unprocessable Entity` | Validation failed (e.g. `payment_terms_days ≤ 0`) |

---

### `GET /admin/companies/{company_id}/dealers`

List all dealers for a company, ordered by `name` ascending. Accepts `?page=&limit=` (see
[Pagination](#pagination)).

**Response 200** — `Page<DealerResponse>`

**Error responses**

| Status | When |
|--------|------|
| `404 Not Found` | `company_id` does not exist |

---

### `GET /admin/companies/{company_id}/dealers/{dealer_id}`

Get a single dealer by UUID, scoped to the company.

**Path parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `company_id` | UUID | Parent company |
| `dealer_id` | UUID | The dealer's `id` |

**Response 200** — `DealerResponse`

**Error responses**

| Status | When |
|--------|------|
| `404 Not Found` | Company not found, or dealer not found in that company |

---

## Admin — Suppliers

Suppliers are vendors the distributor purchases from. All supplier operations are scoped to a parent company.

### `POST /admin/companies/{company_id}/suppliers`

Add a supplier to a company.

**Path parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `company_id` | UUID | The parent company's `id` |

**Request body**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | ✅ | |
| `phone` | string | optional | |
| `payment_terms_days` | integer | optional | Must be > 0 |
| `credit_limit` | decimal string | optional | Must be ≥ 0 |
| `notes` | string | optional | |

**Example request**
```json
{
  "name": "Hindustan Unilever",
  "phone": "+911122334455",
  "payment_terms_days": 15,
  "credit_limit": "200000.00"
}
```

**Response 201 — created**
```json
{
  "id": "01ab5d4c-3e6f-9a0b-1c2d-3e4f5a6b7c8d",
  "company_id": "018f3b2a-1c4d-7e8f-9a0b-1c2d3e4f5a6b",
  "name": "Hindustan Unilever",
  "phone": "+911122334455",
  "payment_terms_days": 15,
  "credit_limit": "200000.00",
  "notes": null,
  "created_at": "2026-07-01T14:10:00Z"
}
```

**Error responses**

| Status | When |
|--------|------|
| `404 Not Found` | `company_id` does not exist |
| `422 Unprocessable Entity` | Validation failed |

---

### `GET /admin/companies/{company_id}/suppliers`

List all suppliers for a company, ordered by `name` ascending. Accepts `?page=&limit=` (see
[Pagination](#pagination)).

**Response 200** — `Page<SupplierResponse>`

**Error responses**

| Status | When |
|--------|------|
| `404 Not Found` | `company_id` does not exist |

---

### `GET /admin/companies/{company_id}/suppliers/{supplier_id}`

Get a single supplier by UUID, scoped to the company.

**Path parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `company_id` | UUID | Parent company |
| `supplier_id` | UUID | The supplier's `id` |

**Response 200** — `SupplierResponse`

**Error responses**

| Status | When |
|--------|------|
| `404 Not Found` | Company not found, or supplier not found in that company |

---

## Schemas

### `CompanyResponse`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID string | |
| `business_name` | string | |
| `owner_name` | string | |
| `whatsapp_number` | string | E.164 |
| `email` | string \| null | |
| `business_type` | string \| null | |
| `preferred_language` | string | Default `"en"` |
| `subscription_active` | boolean | Default `true` |
| `opening_balance` | decimal string | e.g. `"150000.00"` |
| `created_at` | ISO 8601 datetime | |

### `DealerResponse`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID string | |
| `company_id` | UUID string | |
| `name` | string | |
| `phone` | string \| null | |
| `address` | string \| null | |
| `gst_number` | string \| null | |
| `payment_terms_days` | integer \| null | |
| `credit_limit` | decimal string \| null | |
| `notes` | string \| null | |
| `created_at` | ISO 8601 datetime | |

### `SupplierResponse`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID string | |
| `company_id` | UUID string | |
| `name` | string | |
| `phone` | string \| null | |
| `payment_terms_days` | integer \| null | |
| `credit_limit` | decimal string \| null | |
| `notes` | string \| null | |
| `created_at` | ISO 8601 datetime | |

---

## Error format

All errors follow FastAPI's standard format:

```json
{ "detail": "Human-readable message" }
```

Validation errors (422) use the expanded format:

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "Error description",
      "type": "error_type"
    }
  ]
}
```

---

## Roadmap notes

This document was last written at Phase 2 and hasn't tracked every endpoint added since — see
`SPEC.md` for the authoritative feature roadmap. Items below are resolved as of Phase 6:

| Item | Status |
|------|--------|
| `POST /admin/companies/{id}/import` | Done — Phase 3, CSV/Excel import; PDF (Tally voucher/invoice printouts) added later |
| `GET /admin/companies/{id}/invoices`, `.../payments` | Done — Phase 4, invoice/payment read APIs |
| `GET /admin/companies/{id}/cashflow` | Done — Phase 5A, cashflow engine |
| `POST`/`GET /admin/companies/{id}/briefing` | Done — Phase 5B, LLM-narrated morning briefing |
| Pagination (`?page=&limit=`) | Done — Phase 6, see [Pagination](#pagination) |
| Authentication / API keys | Done — Phase 6, see [Authentication](#authentication) |
