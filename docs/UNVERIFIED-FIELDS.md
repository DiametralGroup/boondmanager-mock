---
type: reference
description: The registry of gaps between this mock, the official BoondManager documentation, and the real API as observed — what is attested, what is added, what is approximated.
sources_of_truth:
  - src/boondmanager_mock/models/entities.py
  - src/boondmanager_mock/dataset/realiste.py
  - src/boondmanager_mock/envelope.py
  - src/boondmanager_mock/errors.py
  - src/boondmanager_mock/included.py
review_triggers:
  - contracts/boondmanager.openapi.yaml
  - docs/comparisons/
update_policy: propose
last_verified: 2026-07-31
---

# Gap registry — official RAML × real API × mock

Repository rule: *do not invent BoondManager fields*. Every field flagged
`x-boond-confidence: unverified` or `invented` in the contract **must** appear
here — a test enforces it.

## The hierarchy of evidence

Since v0.3.0 the reference is TWOFOLD, and observation wins:

1. **Observed on the real API** — a tenant running 9.1.78.1, probed on
   2026-07-30/31 with an *owner* user token (replayable report:
   `scripts/compare_real.py`; latest committed run in
   [`docs/comparisons/`](comparisons/)). The 2026-07-31 report shows **zero
   structural difference** across the 19 comparable modules, the error dialect
   and the four profile endpoints.

   ⚠️ « Zero structural difference » meant *the shapes match where both sides
   emit something*. It did NOT mean the VALUES match, and that gap cost a
   consumer real time: `advantageTypes` was compared as an empty array against
   an empty array and passed, while the vendor fills it on 16 contracts out of
   18. A field the mock always leaves empty is a field nobody has ever seen.
   The 2026-09-10 probe exists because of that blind spot —
   [comparisons/2026-09-10.md](comparisons/2026-09-10.md).
2. **Documented in the official RAML** (https://doc.boondmanager.com/api-externe/,
   `raml-build/`) — used where the real API showed nothing (module empty on
   the tenant, permissions).

## Attested by OBSERVATION (the bulk of the mock)

- paths, methods and cardinalities: 20 searchable collections; `/absences`,
  `/expenses`, `/times` without a profile endpoint; **`GET /contracts` and
  `GET /deliveries` answering 405** (observed);
- the envelope: full `meta` (`version`, `androidMinVersion`, `iosMinVersion`,
  `isLogged`, `language`, `timestamp`, `login`, `customer`, `totals.rows`) +
  PER-MODULE keys (`solr`, `conditionalFields`, `resetCache`,
  `hasOpportunityAlerts`); per-module `included` reduced shapes as observed;
- **the entire error dialect**: `meta` present even on errors (outside a
  session: `isLogged:false`/`"en"`), entries `{status, code, detail,
  title|source}`, `HTTP {code} ({method} {path})` messages,
  `422 - Signature verification failed` + `source.parameter: xJwtClient`,
  1017 + `source.parameter` per missing parameter on `times-reports`;
- identifiers: numeric strings everywhere, **composite on `/times`**
  (`regular_1`, `exceptional_…`);
- `times-reports`: the `startMonth`/`endMonth` window is REQUIRED;
- the profile endpoints `resources/{id}` (18 attributes, `contracts`
  relationship), `contracts/{id}`, `resources/{id}/administrative`,
  `resources/{id}/technical-data` (type `resource`) — all at zero difference;
- default ordering is STABLE; `sort=updateDate` and `period=updated|created`.

## Behaviour DOCUMENTED but not implemented by the provider

Distinct from the field matrix below: here the API *accepts* something and does
not act on it. Silent, and therefore expensive — a rejected parameter at least
tells the caller something.

| Endpoint | Documented | Observed | Measured |
|---|---|---|---|
| `/times` | `period=updated\|created` + `startDate`/`endDate` filters the collection | **accepted and ignored** — all three filter shapes return the full set (106 976 rows on a production tenant) | 2026-08-04, [comparisons/2026-08-04.md](comparisons/2026-08-04.md) |

The mock reproduces this via `CollectionSpec(..., filtre_periode=False)` and
locks it with `tests/test_ecarts_api_documentation.py`. It is NOT turned into a
`422`: the real API does not reject these parameters, and a consumer seeing an
error would fix a problem that does not exist.

Compounding gap: `times` also has no `updateDate` (see the matrix below). No
timestamp to filter on, and no filter that works — a consumer has **no
incremental path at all** on this collection, and must size its cadence
accordingly.

## The RAML × observed matrix

Fields DOCUMENTED in the RAML that the real API never returned (even with the
owner token) — the mock no longer emits them:

| Module | RAML fields never observed |
|---|---|
| CRM searches (resources, candidates, companies, contacts, opportunities) | `creationSource` (present only on the resources PROFILE) |
| companies | `numberbOfActiveOpportunity` (documented typo field, never served) |
| resources (search) | `icSince`, `icStatus` — the bench is read through `availability: "immediate"` |
| orders | `billableItemTypes`, `requestTimesheetsSignature` |
| contracts (profile) | `exceptionalScales`, `forceContractAverageDailyProductionCost` — **corrected 2026-09-10**: `probationEndDate` (12/18), `renewalProbationEndDate` (12/18) and `contractAverageDailyProductionCost` (1/18) ARE returned, sparsely. See [comparisons/2026-09-10.md](comparisons/2026-09-10.md) |
| times | `endDate`, `updateDate` |
| absences, roles, times-reports, agencies, poles, business-units, banking-transactions, expenses | `updateDate` |

Gaps the mock KEEPS deliberately (tolerated by `compare_real.py`):

| Gap | Why |
|---|---|
| `orders.updateDate` | **SETTLED on 2026-08-12 — the mock no longer emits it.** The RAML documents it and the official `period=updated` cursor on orders needs it, yet two probes eleven days apart found it absent from the tenant. The « version? » hypothesis of 2026-08-01 does not hold: it is the only one of the eighteen collections to lack the field, and the mock now matches. Consumers must extract `/orders` in full refresh. |
| `orders.creationDate` | **SETTLED on 2026-08-12 — no longer emitted either.** 0.6.0 kept it on the grounds that « it drives no extraction strategy, so serving it costs nothing ». That was wrong: a model which READS a column needs the column to EXIST, and `stg_commande` broke on « column o.creation_date does not exist » on the very next run. There is no such thing as a harmless invented field. `date` (the order date) IS returned by the vendor and stays. |
| `expenses`: `row`, `numberOfKilometers`, `delivery`, `project` always emitted | the real API OMITS empty keys item by item (sparse emission); the mock emits the full RAML shape whenever the value exists |
| `expensesDetails`, `dailyExpenses`, `monthlyExpenses`, `calendar`, `activityRate` | **SETTLED on 2026-09-10 — the mock no longer fills them.** All five are SERVED by the vendor and filled on **0 of 18** contracts. The mock filled all five (38/38, « Titres restaurant », `calendar: "Standard"`, `activityRate: 100`). `activityRate` had already cost a consumer 800 salary rows at zero; `expensesDetails` was on course to repeat it. The keys stay emitted, with the vendor's value: empty. |
| `contractAverageDailyCost` derivable from the gross | **SETTLED on 2026-09-10 — the mock no longer makes it derivable.** It served `monthlySalary * 12 * chargeFactor / numberOfWorkingDays`. Of 25 production contracts, **1** verifies within 1 % and 24 do not (median error 11.7 %, worst 44.2 %). A relation that holds in the mock and not at the vendor is worse than a missing field: every value looks right, and the consumer recomputes instead of reading. |
| `isDeleted` | mock affordance, **no longer in the default payload** (see below) |
| `/actions` ignores `maxResults` | reproduced since 0.6.0 — see below |
| `candidates.availability` as an integer code | reproduced since 0.6.0 — see below |

## Still unattested

### 1. `isDeleted` — **mock affordance, ABSENT by default since 0.6.0**

A probe of the **eighteen** production collections on 2026-08-12 found the field
in NONE of them. It was previously emitted on every item, always `false`.

That default was the costliest kind of fiction — the believable kind.
insights360 built seventeen staging models on `where not is_deleted`, all green
against this mock, all broken on the first production run with *« column
is_deleted does not exist »*.

The affordance itself is kept: an incremental pipeline running a `merge`
strategy cannot observe a physical deletion, and `POST /__admin/delete` still
sets the flag. What changed is that it takes a DELIBERATE act to see it. Absent
by default, the payload now matches the vendor; present after an explicit admin
call, it still exercises the consumer's deletion handling.

⚠️ A consumer must read the ABSENCE as « not deleted ». `not is_deleted` over a
NULL column yields NULL — hence an empty result set, with no error at all.

*General lesson, and the reason this section is worth its length: a mock may
offer affordances the vendor lacks, but it must not put them in the default
payload, where they read as vendor behaviour.*

### 1.b `/actions` ignores `maxResults` — **reproduced since 0.6.0**

`GET /actions?maxResults=500` returns **30** rows — not 500, and not a cap at
100: exactly the default page size, whatever value is sent. The parameter is
accepted, never rejected. The ten other collections probed the same day honour
500.

This is not a comfort detail. A consumer sizing its pagination budget on 500
under-counts pages by a factor of 16: 46 933 actions are 94 pages at 500, but
**1 565** at 30. insights360 stopped at its 1 000-page guard while blaming the
API for « always returning a full page » — the API was paginating correctly.

Same family as the period filter ignored on `/times`: a parameter accepted and
silently dropped is worse than one rejected, because nothing signals it.

### 1.bis `opportunities.startDate` may be the literal `immediate`

Not an edge case: **1 523 of the 1 850** production opportunities (82 %) carry
the string instead of a date. The mock only ever served dates, so
`stg_opportunite` cast the column unguarded and broke on *« invalid input syntax
for type date: "immediate" »*.

The dialect reuses that same literal for a **resource**'s `availability` (105 of
364 in production). Treat it as a general rule: any start-date field may carry
it, and nulling it silently would discard the dominant value of the field —
an immediate need is a signal, not a missing date.

### 1.c `candidates.availability` is a CODE — **corrected in 0.6.0**

On a **candidate**, `availability` is an integer: probed over 26 814 production
candidates, `-1` on 24 289 of them, then 0, 1, 3, 4… The mock served an ISO
date, so the consumer cast it to a date and broke on *« invalid input syntax for
type bigint »*.

⚠️ Not to be confused with a **resource**'s `availability`, which really is an
availability date (or `"immediate"`). Same name, two types, two entities — the
kind of gap a mock must carry rather than smooth over.

The code→label mapping is not established: it lives in the instance dictionary,
family `availability`, which `DOMAINES_DICTIONNAIRE` does not yet consume.

### 2. `updatedSince` / `filter[updateDate][gte]` — **mock affordance**

The official way is `period=updated` (DAY granularity). These two parameters
offer a finer cursor that no documentation attests — they only apply to
modules that expose `updateDate`.

### 3. Values of per-module meta keys and of included-only attributes

`solr`, `conditionalFields`, `resetCache`, `hasOpportunityAlerts` (meta) and
`canReadCompany`, `canReadContact`, `invoicesLockingStates`, `workUnitRate`
(included): the KEYS are observed, the VALUES served are plausible (`true`,
`[]`, `1`…) — the exact content is not documented.

### 4. Dictionary integer semantics

`typeOf`, `state`, `civility`, `currency`…: their meaning is per-instance
(`/application/dictionary`). Values are plausible; the exact mapping is not
attested. Never encode a business rule on these integers without the target
tenant's dictionary.

### 5. Profile endpoints of secondary modules

Only resources, projects, contracts, administrative and technical-data have a
profile projection VERIFIED against the real API. The other profile endpoints
(`/invoices/{id}`, `/candidates/{id}`…) serve the search shape — verify them
if a consumer starts relying on them.

### 6. Synthetic civil status

`dateOfBirth`, `nationality`, seniority… in the administrative tab and the
resource profile: official keys, FABRICATED deterministic values.

### 7. Compensation outside `/api`

`/__fixtures/remuneration.csv` — a convenience view derived from the official
`monthlySalary` field of `/contracts/{id}`.

### 8. Time evolution — a mock affordance, not vendor behaviour

The dataset evolves (see `evolution.py`). `BOOND_MOCK_EVOLUTION=false`
freezes everything. The real API moves because humans are working.


### 6. `GET /application/dictionary` — route ajoutée, forme inventée

`state`, `actionOnCandidate`, `typeOf` (`invented`).

`typeOf` was added in 0.5.5, mirroring `state`. What is attested: the API
returns an integer `typeOf` on resource, candidate, opportunity, project and
purchase, and gives its label nowhere else. The SHAPE is ours, exactly like
`state`. Its `resource` sub-domain is the one entry of the whole route that is
proven rather than inferred: six mock tests establish that `typeOf` carries
employee/subcontractor and drives contract generation.

The endpoint is **not attested by any comparison report** (2026-07-31,
2026-08-04 probed 19 modules; this route was not among them). Its existence is
plausible — this very document already points to it as the source of
per-instance semantics (§4) — but the **shape of the response is ours**, and the
`actionOnCandidate` key is inferred from the convention of `action` and
`actionOnOpportunity`.

What IS attested: an action nomenclature for candidates exists in the tenant —
the `Dashb` sheet of the mappings file counts its volumes over 31 weeks
(PREQUAL, ITW1, ITW2, ITW3).

Consumers must treat the shape as provisional until a comparison run covers it.
The codes served match the dataset by construction — a static control enforces
it (`controler_dictionnaire_mock.py` on the insights360 side).
