---
type: features
description: Pagination ordering as measured on the real API — descending dates by default, sort keys outside the official sortList ignored — with opt-in instability, and the `sort=id` advice it replaces.
sources_of_truth:
  - src/boondmanager_mock/envelope.py
review_triggers:
  - src/boondmanager_mock/envelope.py
  - src/boondmanager_mock/dataset/**
update_policy: auto
last_verified: 2026-09-29
---

# Pagination ordering

## What the mock does

Every row below was measured on the real API on 2026-09-29, except where it
says otherwise.

| Situation | Order |
|---|---|
| `sort=<key>`, key in the module's official `sortList` | sorted on that key, `order=asc\|desc`; numbers sort as numbers, dotted paths accepted (`workUnitType.reference`) |
| `sort=<key>`, key outside the `sortList` — `sort=id` included | **ignored**: default order, status 200 |
| `/resources?sort=creationDate` | ignored — the key is in the `sortList`, the vendor ignores it anyway |
| `/resources?sort=updateDate` | always descending, `order=asc` included |
| no `sort` | **descending date**: `updateDate` on resources and companies, `startDate` on actions; insertion order on the other collections (not measured). Two identical calls return the same sequence. |
| `BOOND_MOCK_STABLE_ORDER=false` | unstable — pagination chaos, as an opt-in |
| injection `{"kind": "unstable_order"}` | unstable, for the duration of a test |

Instability is deterministic within a given test — `hash((request rank, id))`
— hence reproducible, while genuinely varying from one request to the next.

## Why the default order matters

On a list sorted by modification date, a record modified while a consumer
pages through it jumps to the head. Every following page shifts by one, and a
record is served twice. A deletion does the reverse: everything moves up by
one, and a record is never served. Neither case raises an error or a warning.

Up to 0.10.0 the mock served ascending identifiers by default, so no test here
could show this.

## The `sort=id` advice was wrong

Up to 0.10.0 this page told consumers to always send
`sort=id&order=asc`, as the stable key « present everywhere ». It is present
nowhere: `id` is in no module's `sortList`, and the vendor ignores it — asc,
desc and no sort return the same sequence. The mock ignored it too, by
accident (the identifier is not an attribute, so every key compared equal),
and its default order happened to be ascending identifiers. The advice looked
right here and did nothing in production.

The history that led to it still holds as a lesson. When the mock was first
extracted from its original repository, a client that paginated without any
sort lost six records out of twenty-four against an unstable mock:

```
assert len({item["id"] for item in items}) == 24
E   AssertionError: assert 18 == 24
```

An API that does not guarantee its order between two requests can do exactly
that. The fix was right in spirit, wrong in its choice of key.

## What a correct consumer does

- **Keep answers small.** Use the official incremental filter,
  `period=updated&startDate&endDate` (day granularity, 11 modules), with a
  one-day overlap. An answer that fits in one page cannot drift.
- **Deduplicate on the identifier within a scan.** A record served twice must
  not be loaded twice — critical for tables loaded in full refresh, where
  nothing downstream deduplicates.
- **Plan full reads.** A deletion during a long scan can hide one record until
  the next complete read.
- **Check what is really sent**, server-side: `GET /__admin/state` →
  `query_params_by_path`.

## Official sort keys

The `sortList` of every module is transcribed from the RAML into `SORT_LISTS`
(`envelope.py`). `updateDate` is official on resources, candidates, companies,
contacts and opportunities; on resources the vendor honours it in descending
order only.
