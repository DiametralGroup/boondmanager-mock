---
type: reference
description: Where to fetch contracts from the real BoondManager API, and which entities are worth extracting next for ophelie and insights360.
sources_of_truth:
  - https://doc.boondmanager.com/api-externe/ (RAML + JSON schemas, retrieved 2026-07-30)
  - docs/comparisons/ (live probes against a real tenant, 2026-07-30/31)
update_policy: propose
last_verified: 2026-07-31
---

# BoondManager extraction — contracts and candidate entities

## Where to fetch contracts — VALIDATED on the real API (2026-07-31)

`GET /contracts` search does not exist (405 in production, WAF on some
fronts). The flow below was REPLAYED successfully on the real tenant with an
*owner* user token: `resources/{id}` → contract refs → `contracts/{id}`
(200, salaries and the fixed-term → permanent chain). The options, simplest
first:

| # | Path | Auth | What you get | In the mock |
|---|---|---|---|---|
| 1 | `GET /resources/{id}/administrative` | standard (client JWT / basic) | the administrative tab: `contracts` relationship (all of the resource's contracts) + reduced `included`, seniority, civil status | ✅ implemented |
| 2 | `GET /resources/{id}` (profile) | standard | `contracts` relationship + `included` — lighter than the administrative tab | ✅ implemented |
| 3 | `GET /contracts/{id}` | standard | the FULL contract: `monthlySalary`, `hourlySalary`, daily costs, working time, `parentContract`/`childContract` chain | ✅ implemented |
| 4 | `GET /apps/extract-payroll/contracts` and `GET /apps/accounting-payroll/contracts` | **the ORDINARY client JWT — corrected 2026-09-10**, no app JWT needed; `month=YYYY-MM` is REQUIRED (422, code 1017, `source.parameter: month`) | BULK contract search — 148 rows for one month on the tenant probed — plus payroll aggregates (`productionTimes`, `internalTimes`, `absencesTimes`, `expensesToPay`, `expensesAlreadyAdvanced`, `payrollTerm`). ⚠️ Its `advantagesToPay` relationship is EMPTY on all 148: a « to pay » queue, not a history — it does **not** replace `/resources/{id}/advantages` | ❌ not served by the mock |

**Recommended flow for an extractor without an app**:
`GET /resources?maxResults=500` → for each resource,
`GET /resources/{id}/administrative` → contract refs →
`GET /contracts/{id}`. This is exactly the journey the mock serves, covered by
`tests/test_dialecte.py::test_administrative_liste_les_contrats_et_contracts_id_les_detaille`.

⚠️ **Take the profile, not the `included`.** The reduced contract shape carried
in `administrative`'s `included` is missing seventeen attributes that only
`GET /contracts/{id}` returns — among them `chargeFactor` (the charge
coefficient, so any loaded cost), `numberOfWorkingDays`, `hourlySalary`, and
`updateDate`, the cursor that lets a consumer merge instead of replacing.

**For the salary PACKAGE, that flow is not enough.** Contractual entitlements
live on the contract profile (`advantageTypes`); amounts actually PAID — the
variable, the bonuses, the benefits in kind — live on a separate route,
`GET /resources/{id}/advantages`. One call per resource, no cursor, no bulk
collection. See [comparisons/2026-09-10.md](comparisons/2026-09-10.md).

**Findings from the live probes**: `GET /contracts` (search) is blocked
(WAF / 405) — the mock answers 405 the same way since v0.3.0. **Mind the
permissions**: with a narrow-perimeter user token, PROFILE routes answer
`403 "Potential missing contractual feature(s): appsNoCode"` — a token with
sufficient rights is required (the owner token passes everywhere).
Reproducible on the mock with `BOOND_MOCK_FORBIDDEN_COLLECTIONS`.

**Delivery ids**: since the search is a 405, ids are discovered through
relationships — the `included` of `/times` (delivery), the rels of
`/purchases`, then `GET /deliveries/{id}`.

## Candidate entities for the next wave

Found in the official RAML, not served by the mock today. Suggested priority
by value for each consumer:

| Entity (official module) | For ophelie (staffing/CRM) | For insights360 (BI) | Priority |
|---|---|---|---|
| **`/positionings`** — candidate/resource ↔ opportunity positionings (`state`, `stateReason`, dates, `dependsOn`/`opportunity` rels) | the HEART of the staffing pipeline: who is proposed where, at which stage | conversion rates, pre-sales velocity, recruitment funnel | **high** |
| **`/provider-invoices`** — supplier invoices (`amountExcludingTax`, `paymentState`, `resource`, `providerCompany` rels) | subcontractor follow-up | ACTUAL purchase costs vs committed, net subcontracting margin | **high** |
| **`/billing-monthly-balance`**, `/billing-projects-balance`, `/billing-deliveries-purchases-balance`, `/billing-schedules-balance` — PRE-AGGREGATED production/invoiced/ordered balances | — | produced vs invoiced revenue per month and per project WITHOUT pipeline-side recomputation; instant remaining-to-invoice | **high** |
| **`/absences-reports`**, `/expenses-reports` — the REPORTS (`waitingForValidation`… state, `paid`, `closed`) | managers' validation to-do | validation lead times, reimbursement backlog | medium |
| **`/validations`** — the cross-cutting workflow (expected/actual validators, `dependsOn` timesheet/absence/expense) | validation queue | validation SLAs, managerial bottlenecks | medium |
| **`/accounts`** — user accounts (`login`, `level`, `role` rel) | identity ↔ directory reconciliation, access perimeters | entitlement audits | medium |
| **`/documents`** — attachments (résumés!) | résumé display/download | — | low (product, not data) |
| `/targets`, `/inactivities` | sales targets; inactivity planning | sales dashboards; capacity | to explore — search schemas not published in the external RAML |

Already served by the mock and covering the rest of the need: resources,
contracts, deliveries, times, times-reports, absences, expenses, invoices,
orders, payments, purchases, banking-transactions, opportunities, projects,
companies, contacts, candidates, actions, agencies, business-units, poles,
roles.

**Recommended next wave**: `positionings` + `provider-invoices` +
`billing-monthly-balance` — respectively unlocking ophelie's staffing
pipeline, subcontracting margin and insights360's pre-aggregated revenue, with
complete official search schemas (same conventions as the current 22
collections: adding one follows the `CollectionSpec` + generator pattern).
