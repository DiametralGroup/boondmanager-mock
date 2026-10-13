"""Time evolution of the dataset — to exercise incremental extraction.

An incremental extractor cannot be tested against a frozen dataset: records
must CHANGE between two runs, otherwise the cursor (`period=updated`,
`sort=updateDate`, `updatedSince`) passes every test without having filtered
anything. This module makes the firm live between two requests:

  cadence     one event every `BOOND_MOCK_EVOLUTION_INTERVAL` seconds
              (60 by default; 0 or BOOND_MOCK_EVOLUTION=false to freeze it);
  events      new CRM actions, profile updates, consultant STAFFING and
              DESTAFFING (delivery created or ended, `icStatus` flipped),
              invoices settled (+ the matching banking transaction),
              opportunities progressing, timesheets validated, new contacts;
  clock       `engine.now()` — so `POST /__admin/clock {advance_seconds}`
              fast-forwards the company's life without waiting, exactly like
              for rate-limit windows.

DETERMINISM: the event SEQUENCE depends only on the seed — event k draws its
randomness from `Random(f"{seed}:{k}")` and its timestamp is always EPOCH +
(k+1) x interval. Two servers started with the same seed therefore serve the
same data at the same age. What depends on real time is how many events have
already been applied — that is the point: two successive extractions see a
delta, and `meta.totals.rows` moves just like at the vendor.

Each event bumps the affected records' `updateDate` to its own timestamp
(later than the base dataset's cap): an incremental cursor placed after
construction sees ONLY what has changed.
"""

from __future__ import annotations

import copy
import random
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from .dataset.realistic import (
    RESOURCE_STATE_ACTIVE,
    RESOURCE_STATE_BENCH,
    RESOURCE_STATE_NOTICE_PERIOD,
    RESOURCE_STATE_ONBOARDING,
)
from .settings import settings

#: The events' epoch: the dataset's anchor, 9 AM Paris time. Every evolution
#: timestamp is STRICTLY later than the base dataset's `updateDate` cap
#: (2026-07-12) — that is what keeps the incremental delta clean.
EPOCH = datetime(2026, 7, 15, 9, 0, 0, tzinfo=timezone(timedelta(hours=2)))

#: The event cycle. `staffing` alternates on its own between "staffed" and
#: "destaffed" depending on the bench's state when it fires.
CYCLE = (
    "action",
    "profile",
    "staffing",
    "invoice",
    "action",
    "opportunity",
    "timesreport",
    "contact",
)

_ACTION_TEXTS = (
    "Follow-up call — upcoming milestones reviewed.",
    "Weekly sync with the client, workload plan confirmed.",
    "Sent workshop minutes and next steps.",
    "Qualified a new need expressed by the client.",
    "Followed up on the proposal awaiting a decision.",
)

_EVOLUTION_SKILLS = ("DuckDB", "Rust", "LangChain", "OpenTelemetry", "Iceberg", "Dagster")

_CONTACT_FIRST_NAMES = ("Margaux", "Étienne", "Salomé", "Corentin", "Awa", "Baptiste")
_CONTACT_LAST_NAMES = ("Vasseur", "Lefevre", "Nguyen", "Da Silva", "Kaddour", "Petit")


def _ts(seconds: float) -> str:
    return (EPOCH + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S%z")


def _day(seconds: float) -> str:
    return (EPOCH + timedelta(seconds=seconds)).strftime("%Y-%m-%d")


def _next_id(items: list[dict[str, Any]]) -> str:
    return str(max((int(i["id"]) for i in items), default=0) + 1)


#: The IN side of the instance nomenclature, excluding long-term leave.
#: ⚠️ THIS IS NOT AN OPTIMIZATION, IT IS A CONSEQUENCE. As long as the dataset
#: only rendered three states, "active" was conflated with `state == 1` and
#: the intercontract bench necessarily fell into it. Now that the bench has
#: ITS OWN state (3, UN/IC - UNASIGNED), filtering on 1 alone EMPTIES the
#: bench: the four available consultants are no longer in it, `_staffing`
#: falls back to destaffing, and no delivery gets created. That is exactly
#: what test_staffing_puis_destaffing_visibles_sur_le_profil showed.
#:
#: 4 (LONG TERM LEAVE) is deliberately excluded: the person counts in
#: headcount but is not staffable. 0 (OFF) is departed. 5 (LEAVING COMPANY)
#: stays staffable — someone on notice works until their term ends.
STAFFABLE_STATES = (
    RESOURCE_STATE_ACTIVE,
    RESOURCE_STATE_ONBOARDING,
    RESOURCE_STATE_BENCH,
    RESOURCE_STATE_NOTICE_PERIOD,
)


def _active(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """Present, staffable consultants (neither leadership, nor managers, nor departed)."""
    return [
        r
        for r in dataset["resources"]
        if int(r["id"]) >= 7 and r["attributes"].get("state") in STAFFABLE_STATES
    ]


def _on_bench(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """The intercontract bench — `availability: "immediate"`, a field OBSERVED
    for real (the RAML's icStatus/icSince are never returned)."""
    return [r for r in _active(dataset) if r["attributes"].get("availability") == "immediate"]


#: The instance nomenclature's "WON" state. The mock used to code 4, which
#: exists nowhere: two independent sources — the Confluence process and the
#: business export — give 7 (see patch 0.5.1).
OPPORTUNITY_STATE_WON = 7

#: How a deal moves forward. Explicit rather than arithmetic: the nomenclature
#: jumps from 3 to 7, and any integer arithmetic on it misses that.
OPPORTUNITY_TRANSITION = {
    1: 2,  # Open                      -> Qualified (working on solution)
    2: 3,  # Qualified                 -> Proposed solution
    3: OPPORTUNITY_STATE_WON,  # Proposed solution -> WON
}


class Evolution:
    """An instance's event timeline, rearmed on every reset."""

    def __init__(self, seed: int, started_at: float) -> None:
        self.seed = seed
        self.started_at = started_at
        self.applied = 0
        self.journal: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    # ── Control ──────────────────────────────────────────────────────────────

    def advance(self, dataset: dict[str, Any], now: float) -> int:
        """Applies every event that has become due; returns their COUNT (for
        cache invalidation). Idempotent and locked — FastAPI handlers run in a
        thread pool."""
        if not settings.evolution_enabled or settings.evolution_interval <= 0:
            return 0
        due = int((now - self.started_at) // settings.evolution_interval)
        if due <= self.applied:
            return 0
        applied_here = 0
        with self._lock:
            while self.applied < due:
                k = self.applied
                age = (k + 1) * settings.evolution_interval
                detail = self._apply(dataset, k, age)
                self.journal.append(
                    {"index": k, "at": _ts(age), "kind": CYCLE[k % len(CYCLE)], "detail": detail}
                )
                del self.journal[:-50]
                self.applied += 1
                applied_here += 1
        return applied_here

    def overview(self) -> dict[str, Any]:
        """What /__admin/state exposes — the delta's observability."""
        return {
            "enabled": settings.evolution_enabled and settings.evolution_interval > 0,
            "interval_seconds": settings.evolution_interval,
            "applied": self.applied,
            "journal": self.journal[-20:],
        }

    # ── The events ───────────────────────────────────────────────────────────

    def _apply(self, dataset: dict[str, Any], k: int, age: float) -> str:
        rng = random.Random(f"{self.seed}:{k}")
        kind = CYCLE[k % len(CYCLE)]
        handlers = {
            "action": self._action,
            "profile": self._profile,
            "staffing": self._staffing,
            "invoice": self._invoice,
            "opportunity": self._opportunity,
            "timesreport": self._timesreport,
            "contact": self._contact,
        }
        detail = handlers[kind](dataset, rng, k, age)
        # A handler with nothing to do (no more invoice to settle, no more
        # timesheet to validate…) falls back to the most neutral event: a CRM
        # action.
        return detail or self._action(dataset, rng, k, age)

    def _new_action(
        self,
        dataset: dict[str, Any],
        rng: random.Random,
        age: float,
        *,
        target_type: str,
        target_id: str,
        text: str,
        company_id: str | None,
    ) -> str:
        ident = _next_id(dataset["actions"])
        dataset["actions"].append(
            {
                "id": ident,
                "type": "action",
                "attributes": {
                    "startDate": _ts(age),
                    "creationDate": _ts(age),
                    "typeOf": rng.choice([1, 2, 3, 5]),
                    "text": text,
                    "numberOfFiles": 0,
                    "canReadAction": True,
                    "canWriteAction": True,
                    "updateDate": _ts(age),
                },
                "relationships": {
                    "mainManager": {"data": {"id": str(rng.choice((2, 3, 5))), "type": "resource"}},
                    "dependsOn": {"data": {"id": target_id, "type": target_type}},
                    "company": {
                        "data": {"id": company_id, "type": "company"} if company_id else None
                    },
                    "relatedActions": {"data": []},
                },
            }
        )
        return f"action {ident} ({target_type} {target_id})"

    def _action(self, dataset: dict[str, Any], rng: random.Random, k: int, age: float) -> str:
        contacts = dataset["contacts"]
        if not contacts:
            return "no target"
        contact = contacts[k % len(contacts)]
        return self._new_action(
            dataset,
            rng,
            age,
            target_type="contact",
            target_id=contact["id"],
            text=rng.choice(_ACTION_TEXTS),
            company_id=contact["relationships"]["company"]["data"]["id"],
        )

    def _profile(self, dataset: dict[str, Any], rng: random.Random, k: int, age: float) -> str:
        active = _active(dataset)
        if not active:
            return ""
        res = active[k % len(active)]
        attrs = res["attributes"]
        new_skill = rng.choice(_EVOLUTION_SKILLS)
        if new_skill not in attrs.get("skills", ""):
            attrs["skills"] = (
                f"{attrs['skills']}, {new_skill}" if attrs.get("skills") else new_skill
            )
            attrs["tools"] = [
                *attrs.get("tools", []),
                {"tool": new_skill, "level": rng.randint(2, 4)},
            ]
        attrs["numberOfResumes"] = (attrs.get("numberOfResumes") or 0) + 1
        attrs["updateDate"] = _ts(age)
        return f"resource profile {res['id']} ({new_skill})"

    def _staffing(self, dataset: dict[str, Any], rng: random.Random, _k: int, age: float) -> str:
        """The core of incremental realism: the bench moves both ways."""
        day = _day(age)
        bench = _on_bench(dataset)
        if bench:
            return self._staff(dataset, rng, bench[0], day, age)
        return self._destaff(dataset, rng, day, age)

    def _staff(
        self,
        dataset: dict[str, Any],
        rng: random.Random,
        res: dict[str, Any],
        day: str,
        age: float,
    ) -> str:
        ongoing = [
            p
            for p in dataset["projects"]
            if p["attributes"]["startDate"] <= day <= p["attributes"]["endDate"]
        ]
        if not ongoing:
            return ""
        project = rng.choice(ongoing)
        template = next(
            (
                m
                for m in dataset["deliveries"]
                if m["relationships"]["project"]["data"]["id"] == project["id"]
            ),
            dataset["deliveries"][0],
        )
        delivery = copy.deepcopy(template)
        delivery["id"] = _next_id(dataset["deliveries"])
        daily_rate = res["attributes"].get("averageDailyPriceExcludingTax") or 650.0
        end = project["attributes"]["endDate"]
        planned_days = 40.0
        attrs = delivery["attributes"]
        attrs.update(
            {
                "startDate": day,
                "endDate": end,
                "title": res["attributes"]["title"],
                "state": 1,
                "averageDailyPriceExcludingTax": daily_rate,
                "averageDailyCost": round(daily_rate * 0.58, 2),
                "averageDailyContractCost": round(daily_rate * 0.58, 2),
                "numberOfDaysInvoicedOrQuantity": planned_days,
                "turnoverSimulatedExcludingTax": round(daily_rate * planned_days, 2),
                "costsSimulatedExcludingTax": round(daily_rate * 0.58 * planned_days, 2),
                "marginSimulatedExcludingTax": round(daily_rate * 0.42 * planned_days, 2),
                "creationDate": _ts(age),
                "updateDate": _ts(age),
            }
        )
        delivery["relationships"] = {
            "project": {"data": {"id": project["id"], "type": "project"}},
            "dependsOn": {"data": {"id": res["id"], "type": "resource"}},
            "purchase": {"data": None},
        }
        dataset["deliveries"].append(delivery)

        res["attributes"].update(
            {
                "availability": end,
                "realAvailability": "",
                "numberOfActivePositionings": 0,
                "updateDate": _ts(age),
            }
        )
        self._new_action(
            dataset,
            rng,
            age,
            target_type="resource",
            target_id=res["id"],
            text=f"Staffing confirmed — starting on {project['attributes']['reference']}.",
            company_id=project["relationships"]["company"]["data"]["id"],
        )
        return (
            f"resource {res['id']} staffed on project {project['id']} (delivery {delivery['id']})"
        )

    def _destaff(self, dataset: dict[str, Any], rng: random.Random, day: str, age: float) -> str:
        candidates = [
            m
            for m in dataset["deliveries"]
            if m["attributes"]["state"] == 1
            and m["attributes"]["endDate"] > day
            and m["relationships"]["dependsOn"]["data"] is not None
            and m["relationships"]["dependsOn"]["data"]["type"] == "resource"
        ]
        if not candidates:
            return ""
        delivery = rng.choice(candidates)
        res_id = delivery["relationships"]["dependsOn"]["data"]["id"]
        res = next(r for r in dataset["resources"] if r["id"] == res_id)
        delivery["attributes"].update({"endDate": day, "state": 2, "updateDate": _ts(age)})
        res["attributes"].update(
            {
                "availability": "immediate",
                "realAvailability": day,
                "numberOfActivePositionings": rng.randint(1, 2),
                "updateDate": _ts(age),
            }
        )
        self._new_action(
            dataset,
            rng,
            age,
            target_type="resource",
            target_id=res["id"],
            text="Delivery ended early — back on the bench, looking for staffing.",
            company_id=None,
        )
        return f"resource {res_id} destaffed (delivery {delivery['id']} closed)"

    def _invoice(self, dataset: dict[str, Any], _rng: random.Random, _k: int, age: float) -> str:
        pending = [
            f
            for f in dataset["invoices"]
            if f["attributes"]["state"] == 1 and not f["attributes"]["isCreditNote"]
        ]
        if not pending:
            return ""
        invoice = pending[0]
        attrs = invoice["attributes"]
        attrs.update(
            {
                "state": 2,
                "sendingState": 2,
                "closed": True,
                "performedPaymentDate": _day(age),
                "updateDate": _ts(age),
            }
        )
        ident = _next_id(dataset["banking_transactions"])
        dataset["banking_transactions"].append(
            {
                "id": ident,
                "type": "bankingtransaction",
                "attributes": {
                    "amount": attrs["totalPayableIncludingTax"],
                    "currency": 0,
                    "date": _ts(age),
                    "numberOfInvoices": 0,
                    "title": f"VIR SEPA {attrs['reference']}",
                    "state": 0,
                    "totalAmountToReconcile": attrs["totalPayableIncludingTax"],
                    "canReadTransaction": True,
                    "canWriteTransaction": True,
                    "canReconcile": True,
                },
                "relationships": {"account": {"data": {"id": "1", "type": "bankingaccount"}}},
            }
        )
        return f"invoice {invoice['id']} settled (transaction {ident})"

    def _opportunity(self, dataset: dict[str, Any], _rng: random.Random, k: int, age: float) -> str:
        open_ones = [o for o in dataset["opportunities"] if o["attributes"]["state"] in (1, 2, 3)]
        if not open_ones:
            return ""
        opp = open_ones[k % len(open_ones)]
        attrs = opp["attributes"]
        # THE NOMENCLATURE IS NOT CONTIGUOUS, and `+= 1` assumed it was. After
        # 3 (Proposed solution) comes 7 (WON): incrementing produced a state 4
        # the instance does not know, that the dictionary does not declare,
        # and that fct_opportunite sorts into neither won, lost, nor ongoing.
        # The transition is therefore NAMED, and it fails loudly if an
        # unexpected state shows up — a KeyError is visible, a wrong count is
        # not.
        attrs["state"] = OPPORTUNITY_TRANSITION[attrs["state"]]
        attrs["updateDate"] = _ts(age)
        if attrs["state"] == OPPORTUNITY_STATE_WON:
            attrs["closingDate"] = _day(age)
            attrs["turnoverWeightedExcludingTax"] = attrs["turnoverEstimatedExcludingTax"]
            company_id = opp["relationships"]["company"]["data"]["id"]
            company = next(s for s in dataset["companies"] if s["id"] == company_id)
            company["attributes"]["updateDate"] = _ts(age)
            return f"opportunity {opp['id']} won"
        return f"opportunity {opp['id']} progressing (state {attrs['state']})"

    def _timesreport(
        self, dataset: dict[str, Any], _rng: random.Random, _k: int, _age: float
    ) -> str:
        pending = [
            t
            for t in dataset["times_reports"]
            if t["attributes"]["state"] in ("waitingForValidation", "savedAndNoValidation")
        ]
        if not pending:
            return ""
        report = pending[0]
        report["attributes"]["state"] = "validated"
        return f"timesheet {report['id']} validated ({report['attributes']['term']})"

    def _contact(self, dataset: dict[str, Any], rng: random.Random, k: int, age: float) -> str:
        clients = [s for s in dataset["companies"] if int(s["id"]) <= 10]
        if not clients:
            return ""
        company = clients[k % len(clients)]
        first_name = rng.choice(_CONTACT_FIRST_NAMES)
        last_name = rng.choice(_CONTACT_LAST_NAMES)
        domain = company["attributes"]["website"].removeprefix("https://")
        ident = _next_id(dataset["contacts"])
        dataset["contacts"].append(
            {
                "id": ident,
                "type": "contact",
                "attributes": {
                    "creationDate": _ts(age),
                    "civility": rng.randint(0, 1),
                    "thumbnail": "",
                    "firstName": first_name,
                    "lastName": last_name,
                    "state": 1,
                    "function": rng.choice(["Product Manager", "BI Lead", "Solutions Architect"]),
                    "department": "Information Systems Department",
                    "email1": f"{first_name.lower()}.{last_name.lower().replace(' ', '')}@{domain}",
                    "email2": "",
                    "email3": "",
                    "phone1": "",
                    "phone2": "",
                    "town": company["attributes"]["town"],
                    "country": company["attributes"]["country"],
                    "canReadContact": True,
                    "canWriteContact": True,
                    "canShowAction": True,
                    "typesOf": [],
                    "socialNetworks": [],
                    "updateDate": _ts(age),
                },
                "relationships": {
                    "mainManager": company["relationships"]["mainManager"],
                    "company": {"data": {"id": company["id"], "type": "company"}},
                    "agency": company["relationships"]["agency"],
                    "pole": company["relationships"]["pole"],
                },
            }
        )
        return f"contact {ident} created at {company['attributes']['name']}"
