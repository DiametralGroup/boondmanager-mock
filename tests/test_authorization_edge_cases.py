"""The edge cases the `realistic` dataset carries for authorization models.

These three properties do not serve the dataset's realism: they serve the
fact that an authorization model built on it CAN fail. A uniform dataset
makes a visibility test true by vacuity — it passes just as well with a
correct model as with a broken one.

They are therefore asserted HERE, in the mock's repository, and not only at
the consumer: a refactor of the generator that made them disappear must break
a visible test, not silently degrade another repository's coverage.
"""

from __future__ import annotations

import random
from collections import Counter

from boondmanager_mock.dataset.realistic import (
    _AGENCY_BEFORE_TRANSFER,
    _DEPARTED_IDS,
    _DEPARTURE_MONTH,
    _HOMONYM_IDS,
    _TRANSFER_ID,
    _TRANSFER_MONTH,
    ACTIVITY_MONTHS,
    _build_resources,
    _build_timesreports,
)


def _dataset() -> tuple[list[dict], list[dict]]:
    resources = _build_resources(random.Random(42))
    timesreports, _ = _build_timesreports(resources, random.Random(42))
    return resources, timesreports


def test_two_homonyms_with_distinct_addresses() -> None:
    """Same first name + same last name, DIFFERENT addresses, DIFFERENT agencies.

    This is the most dangerous edge case of the lot. A consumer who derives a
    directory identifier from "firstname.lastname" alone assigns them the
    same identity and MERGES their visibility perimeters — a silent privilege
    escalation, not a cosmetic defect.

    The distinct agencies are not a detail: homonyms in the same agency, an
    identity merge would change no perimeter and the consumer's test would
    stay green by mistake.
    """
    resources, _ = _dataset()
    by_id = {r["id"]: r for r in resources}
    a, b = (by_id[str(i)] for i in _HOMONYM_IDS)

    assert (a["attributes"]["firstName"], a["attributes"]["lastName"]) == (
        b["attributes"]["firstName"],
        b["attributes"]["lastName"],
    ), "homonyms must carry EXACTLY the same full name"

    assert a["attributes"]["email1"] != b["attributes"]["email1"], (
        "identical addresses would turn the case into a duplicate, not a homonym"
    )
    assert (
        a["relationships"]["agency"]["data"]["id"] != b["relationships"]["agency"]["data"]["id"]
    ), "without distinct agencies, the case discriminates nothing"

    # …and they must remain the ONLY ones: an unintentional second homonym
    # pair would make any diagnosis ambiguous at the consumer.
    names = Counter((r["attributes"]["firstName"], r["attributes"]["lastName"]) for r in resources)
    assert [n for n, c in names.items() if c > 1] == [
        (a["attributes"]["firstName"], a["attributes"]["lastName"])
    ]


def test_a_transfer_leaves_prior_facts_on_the_old_agency() -> None:
    """Timesheets prior to the transfer carry the OLD agency.

    A model that attaches facts to the employee rather than to the fact row
    retroactively rewrites history — and it stays invisible as long as no
    employee moves.
    """
    resources, timesreports = _dataset()
    current = next(r for r in resources if r["id"] == str(_TRANSFER_ID))
    current_agency = current["relationships"]["agency"]["data"]["id"]

    by_term = {
        c["attributes"]["term"]: c["relationships"]["agency"]["data"]["id"]
        for c in timesreports
        if c["relationships"]["resource"]["data"]["id"] == str(_TRANSFER_ID)
    }
    assert by_term, "the transferred resource must have timesheets"

    before = {t: a for t, a in by_term.items() if int(t.split("-")[1]) < _TRANSFER_MONTH}
    after = {t: a for t, a in by_term.items() if int(t.split("-")[1]) >= _TRANSFER_MONTH}
    assert before and after, (
        "the transfer must fall WITHIN ACTIVITY_MONTHS, otherwise one side is "
        "empty and the case does not exist"
    )
    assert set(before.values()) == {str(_AGENCY_BEFORE_TRANSFER)}
    assert set(after.values()) == {current_agency}
    assert str(_AGENCY_BEFORE_TRANSFER) != current_agency


def test_a_departed_resource_keeps_history_and_produces_nothing_after() -> None:
    """A leaver keeps their produced facts, and produces none afterward.

    Two distinct properties, and conflating them is exactly what makes a
    leaver keep access rights — or lose the trace of what they produced.
    With no timesheet at all, the second risk becomes unverifiable at the
    consumer.
    """
    _, timesreports = _dataset()
    max_month = max(m for _, m in ACTIVITY_MONTHS)
    assert max_month > _DEPARTURE_MONTH, (
        "a departure in the last activity month proves nothing: there would "
        "be no month AFTER it to observe the absence"
    )

    for rid in _DEPARTED_IDS:
        terms = sorted(
            c["attributes"]["term"]
            for c in timesreports
            if c["relationships"]["resource"]["data"]["id"] == str(rid)
        )
        assert terms, f"departed resource {rid} must keep a history"
        assert all(int(t.split("-")[1]) <= _DEPARTURE_MONTH for t in terms), (
            f"departed resource {rid} produces facts AFTER leaving: {terms}"
        )
