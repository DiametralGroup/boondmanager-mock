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
   The 2026-09-29 probe (version 9.1.97.2) measured BEHAVIOURS rather than
   shapes — pagination, sorting, filters — on the same questions put to the
   real API and to the mock, and corrected two earlier readings (`/actions`
   and `/times`, below): [comparisons/2026-09-29.md](comparisons/2026-09-29.md).
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
- ordering (2026-09-29): without `sort`, a DESCENDING DATE — `updateDate` on
  resources and companies, `startDate` on actions — stable between two
  identical calls; a `sort` key outside the module's official `sortList`
  (`sort=id` included) is ignored with a 200;
- filters (2026-09-29): `period=updated` honoured on the 11 modules that
  document it, `/orders` included; `period=inProgress` honoured on `/times`;
  `updatedSince` ignored everywhere;
- pagination (2026-09-29): maximum 500, 100 on `/actions`, and above the
  maximum a silent fall-back to the default 30 rows; `agencies`, `poles` and
  `business-units` ignore `page`/`maxResults` and return everything.

## Behaviour DOCUMENTED but not implemented by the provider

Distinct from the field matrix below: here the API *accepts* something and does
not act on it. Silent, and therefore expensive — a rejected parameter at least
tells the caller something.

| Endpoint | Documented | Observed | Measured |
|---|---|---|---|
| every paginated module | `maxResults` maximum 500 | above the maximum, the API **falls back to the default 30 rows** — no cap, no error (`/companies?maxResults=501` → 30) | 2026-09-29 |
| `/actions` | `maxResults` maximum 500 | maximum **100**: 100 → 100 rows, 101 → 30 | 2026-09-29 — supersedes the 2026-08-12 reading « ignores `maxResults` » |
| `/resources` | `creationDate` in the `sortList`; `order=asc\|desc` | `sort=creationDate` ignored (default order, asc and desc); `sort=updateDate&order=asc` returns DESCENDING order | 2026-09-29 |
| `/orders` | `creationDate` and `updateDate` in the schema | never returned — while `period=updated` does filter the module, on a date the vendor keeps to itself. The mock has no such hidden date: any `period=updated` window on `/orders` returns nothing here | 2026-08-12, re-verified 2026-09-29 |

The mock reproduces each row (`PLAFONDS_MAXRESULTS`, `TRIS_IGNORES`,
`TRIS_TOUJOURS_DECROISSANTS` in `envelope.py`) and locks them in
`tests/test_dialecte.py` and `tests/test_ecarts_mesures_en_production.py`.
None is turned into a `422`: the real API rejects nothing, and a consumer
seeing an error would fix a problem that does not exist.

**Corrected on 2026-09-29: `/times` no longer belongs here.** It was listed on
the strength of the 2026-08-04 probe, where three filter shapes were accepted
and ignored — bare dates, `startMonth/endMonth`, `period=updated`. None of them
is the contract's: the RAML documents a single value on `/times`,
`period=inProgress` + `startDate`/`endDate`, on the date of the time row. It
works — 111 745 rows unfiltered, 2 716 for September 2026. The mock honours it
since 0.11.0 (`CollectionSpec(..., periodes=("inProgress",))`) and keeps
ignoring the three other shapes, as the vendor does. `times` still has no
`updateDate`: a consumer can window by row date, not by modification date.

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
| times | `endDate` |

*Corrected on 2026-09-29: this matrix used to list `updateDate` as documented
on times, absences, roles, times-reports, agencies, poles, business-units,
banking-transactions and expenses. The official search schemas downloaded that
day document it on none of them — it is absent from both sides, not a gap.*

Gaps the mock KEEPS deliberately (tolerated by `compare_real.py`):

| Gap | Why |
|---|---|
| `orders.updateDate` | **SETTLED on 2026-08-12 — the mock no longer emits it.** The RAML documents it and the official `period=updated` cursor on orders needs it, yet two probes eleven days apart found it absent from the tenant. The « version? » hypothesis of 2026-08-01 does not hold: it is the only one of the eighteen collections to lack the field, and the mock now matches. Consumers must extract `/orders` in full refresh. |
| `orders.creationDate` | **SETTLED on 2026-08-12 — no longer emitted either.** 0.6.0 kept it on the grounds that « it drives no extraction strategy, so serving it costs nothing ». That was wrong: a model which READS a column needs the column to EXIST, and `stg_commande` broke on « column o.creation_date does not exist » on the very next run. There is no such thing as a harmless invented field. `date` (the order date) IS returned by the vendor and stays. |
| `expenses`: `row`, `numberOfKilometers`, `delivery`, `project` always emitted | the real API OMITS empty keys item by item (sparse emission); the mock emits the full RAML shape whenever the value exists |
| `expensesDetails`, `dailyExpenses`, `monthlyExpenses`, `calendar`, `activityRate` | **SETTLED on 2026-09-10 — the mock no longer fills them.** All five are SERVED by the vendor and filled on **0 of 18** contracts. The mock filled all five (38/38, « Titres restaurant », `calendar: "Standard"`, `activityRate: 100`). `activityRate` had already cost a consumer 800 salary rows at zero; `expensesDetails` was on course to repeat it. The keys stay emitted, with the vendor's value: empty. |
| `contractAverageDailyCost` derivable from the gross | **SETTLED on 2026-09-10 — the mock no longer makes it derivable.** It served `monthlySalary * 12 * chargeFactor / numberOfWorkingDays`. Of 25 production contracts, **1** verifies within 1 % and 24 do not (median error 11.7 %, worst 44.2 %). A relation that holds in the mock and not at the vendor is worse than a missing field: every value looks right, and the consumer recomputes instead of reading. |
| contract `agency` always equal to the resource's | **SETTLED on 2026-09-11 — the mock now diverges on a minority of contracts.** This is how BoondManager expresses MULTI-ENTITY affiliation: one person, several contracts, several agencies. Measured on a production tenant (70 multi-contract resources, 388 contracts): **18 contracts (4.6 %) carry an agency different from their resource's**, and 3 people span several — including the chief executive, spread over three entities. Giving every contract its resource's agency made a consumer green here and attached 4.6 % of contracts to the wrong RLS perimeter in production. Frequency is denser than real (≈16 %) so the case is actually exercised on a 38-contract dataset; the SHAPE is faithful, the rate is not. |
| `isDeleted` | mock affordance, **no longer in the default payload** (see below) |
| `/actions` caps `maxResults` at 100 | reproduced since 0.11.0 (0.6.0 to 0.10.0 served 30 rows whatever the request) — see below |
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

### 1.b `/actions` caps `maxResults` at 100 — **reproduced since 0.11.0**

`GET /actions?maxResults=500` returns **30** rows. The 2026-08-12 probe read
this as « the parameter is ignored », and 0.6.0 served 30 rows whatever the
request. The 2026-09-29 probe tried more values: 2 → 2, 30 → 30, 100 → 100,
101 → 30, 500 → 30. `/actions` honours `maxResults` up to **100** and, above
that, falls back to its default page size — the same fall-back every module
applies above 500.

This is not a comfort detail. A consumer sizing its pagination budget on 500
under-counts pages by a factor of 17: 50 777 actions are 102 pages at 500, 508
at 100, and **1 693** at 30. insights360 first stopped at its 1 000-page guard
while blaming the API for « always returning a full page », then paid 1 693
calls per run — when asking for 100 would have cost 508.

A limit applied silently is worse than one rejected, because nothing signals
it: the answer looks like an ordinary page.

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

### 2. `updatedSince` / `filter[updateDate][gte]` — **mock affordance, OFF by default since 0.11.0**

The official way is `period=updated` (DAY granularity). These two parameters
offer a finer cursor that no documentation attests — and the vendor IGNORES
them: probed on 2026-09-29 on the 11 modules that document `period=updated`,
`updatedSince=2099-01-01T00:00:00Z` left every total unchanged.

Until 0.10.0 the mock applied them by default. A consumer built its
incremental extraction on `updatedSince`, passed every test here, and re-read
every collection on every production run. The affordance now takes
`BOOND_MOCK_UPDATED_SINCE=true`; by default the mock ignores it, like the
vendor.

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

### 5.b `companies/{id}/information` — names observed, types NOT observed

Probed read-only on a production tenant on 2026-09-13, **field names only**.
The route, `data.type = "company"`, its eight relationships and the `included`
types (`agency`, `company`, `resource`) are attested. So is the group
linkage: `parentCompany` is `null` or `{id, type: "company"}` (set on ~6 of 20
sampled companies), `subsidiaries` a list of `{id, type: "company"}`, and both
directions agree (one group listed 16 subsidiaries, each pointing back). Neither
`GET /companies` nor `GET /companies/{id}` serves either relationship.

The 27 attribute NAMES are attested. Those the search already serves keep the
search types (`name`, `expertiseArea`, `state`, `informationComments`,
`thumbnail`, `website`, `phone1`, `town`, `country`, `creationDate`,
`updateDate`, `socialNetworks`). The fifteen below carry
`x-boond-confidence: unverified` — the TYPE and the VALUE served are guesses:

| Attribute | Type served by the mock | Value served |
|---|---|---|
| `address` | string | synthetic street |
| `apeCode` | string | plausible NAF code |
| `billingDetails` | array of objects | always `[]` |
| `creationSource` | string or null | always `null` |
| `departments` | array of strings | always `[]` |
| `fax` | string | always `""` |
| `legalStatus` | string | `SAS`, `SA`, `SARL`, `SE` |
| `number` | string | `CLI-000NN` |
| `origin` | `{typeOf, detail}` (shape borrowed from opportunities) | `{typeOf: 0, detail: ""}` |
| `postcode` | string | derived from the town |
| `registeredOffice` | boolean | always `true` |
| `registrationNumber` | string | synthetic 9-digit SIREN |
| `staff` | integer | synthetic |
| `subDivision` | string | always `""` |
| `vatNumber` | string | synthetic FR VAT number |

⚠️ Empty-by-default fields (`billingDetails`, `departments`, `fax`,
`subDivision`) have never been SEEN filled: the exact trap `advantageTypes`
set. To lift the doubt: a probe sampling VALUES on a few company information
tabs, then align types and fill rates.

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
