"""The dataset: « Boréal Conseil », a French IT consulting firm of 34 people.

A SINGLE dataset, complete and coherent — the old `ophelie` and `insights360`
profiles are removed. Every collection follows the response shape of the
OFFICIAL BoondManager documentation (RAML + JSON schemas from
https://doc.boondmanager.com/api-externe/, pulled 2026-07-30):

  • the JSON:API `type`s are the vendor's, lowercase (`timesreport`,
    `bankingtransaction`, `businessunit`…);
  • attribute names come from each module's `search.json` schemas — including
    the official typo `numberbOfActiveOpportunity` on companies;
  • timestamps follow the vendor's format (`2026-03-12T09:24:00+0100`, offset
    WITHOUT a colon);
  • `/absences`, `/expenses` and `/times` carry their context EMBEDDED in
    `attributes` (report, agency, resource) — that is the real dialect, not a
    JSON:API relationship.

COHERENCE is the central property, because it is what makes the mock
comparable to a real instance:

  resources ← contracts; clients ← contacts; won opportunities → projects
  → deliveries → orders → monthly invoices (worked days x the delivery's
  daily rate) → banking transactions for the settlements; purchases →
  supplier payments; timesheets ← time rows for the same worked days as the
  invoices; absences and expenses attached to their reports.

What remains DELIBERATELY approximate, and documented in
docs/UNVERIFIED-FIELDS.md: the semantics of dictionary integers (`typeOf`,
`state`…), specific to each BoondManager instance — the values chosen here
are plausible, not attested.

Determinism: `random.Random(seed)` and a FIXED time anchor (July 15, 2026).
Never `datetime.now()` — two runs produce the same dataset byte for byte,
which is what makes downstream tests reproducible.
"""

from __future__ import annotations

import calendar
import random
from datetime import date, timedelta
from typing import Any

# ── Time anchor ───────────────────────────────────────────────────────────────

TODAY = date(2026, 7, 15)
#: Months covered by detailed timesheets, time rows, expenses and absences.
ACTIVITY_MONTHS: tuple[tuple[int, int], ...] = ((2026, 5), (2026, 6), (2026, 7))
#: First billed month of the current fiscal year.
BILLING_START = date(2026, 1, 1)
#: Cap of every `updateDate` — a later incremental cursor must return zero
#: rows (see the incrementality tests).
LAST_UPDATE = date(2026, 7, 12)

VAT_RATE = 0.20


def _tz(month: int) -> str:
    """Europe/Paris offset, WITHOUT a colon — the vendor's format."""
    return "+0200" if 4 <= month <= 10 else "+0100"


def _dt(d: date, h: int = 9, mn: int = 0, s: int = 0) -> str:
    return f"{d:%Y-%m-%d}T{h:02d}:{mn:02d}:{s:02d}{_tz(d.month)}"


def _d(d: date) -> str:
    return f"{d:%Y-%m-%d}"


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _working_days(year: int, month: int) -> int:
    """Working days of the month (excluding weekends; holidays are ignored — mock)."""
    last = calendar.monthrange(year, month)[1]
    return sum(1 for d in range(1, last + 1) if date(year, month, d).weekday() < 5)


def _plausible_update(rng: random.Random, after: date) -> str:
    """A plausible `updateDate`: later than creation, never after the anchor."""
    if after >= LAST_UPDATE:
        return _dt(LAST_UPDATE, 8, 30)
    delta = (LAST_UPDATE - after).days
    day = after + timedelta(days=rng.randint(0, delta))
    return _dt(day, rng.randint(8, 18), rng.randint(0, 59), rng.randint(0, 59))


def _rel(type_: str, ident: Any) -> dict[str, Any]:
    """A JSON:API relationship. `ident` of None renders `{"data": null}` — the
    real dialect."""
    if ident is None:
        return {"data": None}
    return {"data": {"id": str(ident), "type": type_}}


# ── Catalogs ─────────────────────────────────────────────────────────────────

_FIRST_NAMES = [
    "Camille",
    "Jules",
    "Sofia",
    "Hugo",
    "Amara",
    "Louis",
    "Priya",
    "Arthur",
    "Emma",
    "Mateo",
    "Lina",
    "Gabriel",
    "Aïcha",
    "Rafael",
    "Yuki",
    "Nathan",
    "Olivia",
    "Diego",
    "Nina",
    "Youssef",
    "Ana",
    "Lars",
    "Wei",
    "Adam",
    "Chloé",
    "Théo",
    "Inès",
    "Maxime",
    "Sarah",
    "Paul",
    "Alice",
    "Antoine",
    "Clara",
    "Romain",
    "Léa",
    "Bastien",
    "Manon",
    "Kevin",
    "Julie",
    "Thomas",
]
_LAST_NAMES = [
    "Martin",
    "Silva",
    "Nakamura",
    "Okafor",
    "Rossi",
    "Muller",
    "Santos",
    "Dubois",
    "Moreau",
    "Laurent",
    "Kim",
    "Ivanov",
    "Fernandez",
    "Andersson",
    "Nguyen",
    "Costa",
    "Bertrand",
    "Haddad",
    "Meyer",
    "Garcia",
    "Patel",
    "Schmidt",
    "Lambert",
    "Oliveira",
    "Roux",
    "Fontaine",
    "Girard",
    "Blanc",
    "Perrin",
    "Chevalier",
    "Lemoine",
    "Renard",
    "Colin",
    "Marchand",
    "Dupuis",
    "Gauthier",
    "Meunier",
    "Brunet",
    "Faure",
    "Bourgeois",
]
#: SUPPORT job titles, by resource id.
#:
#: The dataset used to only produce consultants and managers: the sixteen
#: types of the INDEX sheet only saw three of them. The mappings file
#: nonetheless describes an organization where STAFF accounts for a third of
#: headcount — recruiting, HR, finance, marketing, administration.
#:
#: The TITLES are those of the `ref_type_collaborateur` reference table on the
#: insights360 side: it is what maps a job title to its type, and the match is
#: done on the STRING. Changing a label here without changing it there breaks
#: the mapping silently — the employee comes out with a null type, and
#: nothing signals it.
#:
#: ⚠️ IDENTIFIERS CHOSEN OUTSIDE OF ANY FIXTURE. 11 is `kevin.silva` on the
#: insights360 side, 12 and 17 carry specific states, 1 and 2-6 are
#: leadership and managers, 22-34 are reserved on the mock side. 0.5.3 had put
#: a state on 11 and broken an unrelated negative test: the inventory gets
#: redone with every patch.
_SUPPORT_TITLES = {
    8: "Talent Acquisition Lead",
    10: "Recruiting Officer",
    13: "HR Manager",
    16: "Finance Controller",
    19: "Communications Officer",
    20: "Administrative Assistant",
}

_CONSULTANT_TITLES = [
    "Data Engineer",
    "Senior Data Engineer",
    "Data Scientist",
    "ML Engineer",
    "Cloud Architect",
    "DevOps Consultant",
    "Full-Stack Developer",
    "Tech Lead",
    "Cybersecurity Consultant",
    "Product Owner",
    "Data Governance Consultant",
    "Platform Engineer",
]
_SKILLS = [
    "Python",
    "Spark",
    "dbt",
    "Snowflake",
    "Kafka",
    "Airflow",
    "Terraform",
    "Kubernetes",
    "AWS",
    "Azure",
    "GCP",
    "React",
    "FastAPI",
    "Power BI",
    "SQL",
    "Databricks",
]
_EXPERTISE_AREAS = [
    "Data Engineering",
    "Data Science",
    "Cloud & Infrastructure",
    "Cybersecurity",
    "Product & Agility",
    "Data Governance",
]
_INDUSTRIES = [
    "Banking & Insurance",
    "Retail & Distribution",
    "Energy & Utilities",
    "Industry",
    "Telecoms & Media",
    "Transport & Logistics",
    "Public Sector",
    "Health & Pharma",
]
_DIPLOMAS = [
    "Engineering degree — CentraleSupélec (2017)",
    "Master's in Computer Science — Université de Nantes (2019)",
    "Master's in Data Science — Université Paris-Saclay (2020)",
    "Engineering degree — INSA Lyon (2016)",
    "Master's in MIAGE — Université Lyon 1 (2018)",
    "MSc Computer Science — EPFL (2015)",
]
_LANGUAGES = [
    ("FR", "Native"),
    ("EN", "Fluent"),
    ("ES", "Intermediate"),
    ("DE", "Basic"),
]

#: (name, city, postcode, address, SIREN+NIC, VAT, headcount)
_AGENCIES = [
    (
        "Boréal Conseil Paris",
        "Paris",
        "75009",
        "24 rue de Châteaudun",
        "482 154 796 00031",
        "FR 62 482154796",
        21,
    ),
    (
        "Boréal Conseil Lyon",
        "Lyon",
        "69002",
        "18 quai Saint-Antoine",
        "482 154 796 00049",
        "FR 62 482154796",
        8,
    ),
    (
        "Boréal Conseil Nantes",
        "Nantes",
        "44000",
        "5 allée Duguay-Trouin",
        "482 154 796 00056",
        "FR 62 482154796",
        5,
    ),
    # ── The two foreign entities, and the DELIBERATE duplicate ───────────────
    #
    # ⚠️ THESE FIRST TWO ROWS ARE A TEST CASE, NOT FILLER. The mappings file
    # shows the same mechanics on the real organization: a major entity and
    # its minority alias, separated by a legal suffix. `acl_role_perimetre`
    # targets the entity BY ITS LABEL, so a rule written against one silently
    # excludes people from the other — they see nothing, nobody sees them,
    # and no counter moves.
    #
    # `obs_entites_similaires` exists to catch this and used to find ZERO
    # pairs, for lack of a duplicate in the dataset. It has one now.
    #
    # The NAMES are those of the fictional world: DATA-01 forbids a real
    # legal entity's name in the repository. Only the MECHANICS is reused.
    (
        "Boreal Conseil Bogota S.A.S",
        "Bogota",
        "110111",
        "Carrera 11 #93-46",
        "901 254 883-1",
        "CO 901254883",
        6,
    ),
    (
        "Boreal Conseil Bogota",
        "Bogota",
        "110111",
        "Carrera 11 #93-46",
        "901 254 883-1",
        "CO 901254883",
        2,
    ),
    # A third zone, so that isolation between COUNTRIES stops being vacant:
    # with only one country, no geographic isolation test proves anything —
    # it passes for lack of a counter-example.
    (
        "Boreal Conseil Montreal",
        "Montreal",
        "H3B 2S2",
        "1250 boulevard Rene-Levesque O",
        "1148765432 RC0001",
        "CA 114876543",
        4,
    ),
]
_BUSINESS_UNITS = ["Data & AI", "Cloud & Platforms", "Cybersecurity", "Digital Transformation"]
_POLES = [
    "Data Engineering Pole",
    "Data Science & AI Pole",
    "Cloud & SRE Pole",
    "Operational Security Pole",
    "Product & Design Pole",
    "Planning & PMO Pole",
]

#: (name, city, industry, site, prospect) — 10 clients then 3 suppliers.
_CLIENTS = [
    ("Lumina Retail", "Paris", "Retail & Distribution", "https://lumina-retail.example", False),
    ("Banque Hexagone", "Paris", "Banking & Insurance", "https://banque-hexagone.example", False),
    ("Voltalis Énergie", "Lyon", "Energy & Utilities", "https://voltalis-energie.example", False),
    ("Mutuelle Armor", "Nantes", "Banking & Insurance", "https://mutuelle-armor.example", False),
    (
        "TransEuropa Fret",
        "Lille",
        "Transport & Logistics",
        "https://transeuropa-fret.example",
        False,
    ),
    ("Pharmadis", "Lyon", "Health & Pharma", "https://pharmadis.example", False),
    ("Citymob", "Bordeaux", "Transport & Logistics", "https://citymob.example", False),
    ("Assurial", "Bruxelles", "Banking & Insurance", "https://assurial.example", False),
    ("Groupe Ardentes", "Nantes", "Industry", "https://groupe-ardentes.example", False),
    ("MediaQuartz", "Paris", "Telecoms & Media", "https://mediaquartz.example", True),
    (
        "Fivetech Partners",
        "Paris",
        "Digital Consulting & Services",
        "https://fivetech-partners.example",
        False,
    ),
    ("Softalliance", "Paris", "Software Vendor", "https://softalliance.example", False),
    ("Foncière Beaumont", "Paris", "Real Estate", "https://fonciere-beaumont.example", False),
]
#: ┌─ THE GROUP LINKAGE — subsidiary → parent ────────────────────────────────┐
#: │ Observed in production on 2026-09-13 (read-only probe, names only):     │
#: │ the group is ONLY served by `GET /companies/{id}/information`, via      │
#: │ `parentCompany` (set on ~6 of 20 profiles) and `subsidiaries`.          │
#: │ Neither the `/companies` list nor the profile carries it.               │
#: │                                                                          │
#: │ It therefore lives HERE, outside the items' `relationships`: putting it │
#: │ there would have leaked it into search, where the vendor does not serve │
#: │ it. `subsidiaries` is never stored — it is DERIVED from this table,    │
#: │ which guarantees the two-way consistency measured for real (a group    │
#: │ with 16 subsidiaries, each pointing back to it).                        │
#: └──────────────────────────────────────────────────────────────────────────┘
_COMPANY_PARENTS: dict[int, int] = {
    3: 9,  # Voltalis Énergie  → Groupe Ardentes
    5: 9,  # TransEuropa Fret  → Groupe Ardentes
}
_SUPPLIER_ID_SUBCONTRACTING = 11  # Fivetech Partners
_SUPPLIER_ID_LICENSES = 12  # Softalliance
_SUPPLIER_ID_RENT = 13  # Foncière Beaumont

_CONTACT_FUNCTIONS = [
    "CIO",
    "CTO",
    "Data Director",
    "Head of Data",
    "BI Manager",
    "Transformation Director",
    "IT Procurement Manager",
    "CISO",
    "CFO",
    "MOA Project Manager",
]
_CONTACT_DEPARTMENTS = [
    "Information Systems Department",
    "Data Department",
    "Finance Department",
    "Digital Department",
    "Procurement",
    "General Management",
]

#: (delivery-type title, dominant tools)
_DELIVERY_SUBJECTS = [
    ("Data platform overhaul", ["Snowflake", "dbt", "Airflow"]),
    ("Cloud migration of business applications", ["AWS", "Terraform", "Kubernetes"]),
    ("MLOps foundation rollout", ["Databricks", "Python", "Kubernetes"]),
    ("Finance reporting dashboard", ["Power BI", "SQL", "dbt"]),
    ("Data pipeline industrialization", ["Spark", "Kafka", "Airflow"]),
    ("Security audit and remediation", ["Kubernetes", "Terraform", "AWS"]),
    ("Data mesh — client domain pilot", ["Snowflake", "dbt", "Kafka"]),
    ("E-commerce system modernization", ["React", "FastAPI", "GCP"]),
]

_ABSENCE_TYPES = [
    (20, "Paid leave"),
    (21, "RTT"),
    (22, "Sick leave"),
    (23, "Exceptional leave"),
]
_EXPENSE_TYPES = [
    (1, "Meals", 10.0),
    (2, "Transport", 10.0),
    (3, "Accommodation", 10.0),
    (4, "Toll & fuel", 20.0),
]

# PLAUSIBLE dictionary semantics (instance-specific, not attested): the SIX
# instance states (INDEX sheet of the mappings file, IN/OUT/NEW column). Only
# one is outgoing — "OFF": an employee on long-term leave or on notice still
# counts in headcount.
#
# ⚠️ THE INTEGERS REMAIN THE MOCK'S OWN, AND THEY ARE NOT ATTESTED — no more
# than before. What this block brings is the NUMBER of states and their
# SEMANTICS, both sourced from the INDEX sheet. The code ↔ label mapping, for
# its part, is only readable from `GET /application/dictionary`.
#
# The temptation was to align on the labels' prefix ("06 - OFF" → 6), as was
# done for opportunities. It is rejected: `stg_collaborateur.sql` has already
# decided that this prefix is a DISPLAY convention. For opportunities, two
# independent sources agreed — the Confluence process AND the export; here
# there is only the prefix, and one match does not make a rule.
#
# What matters for a mock: being consistent with its own dictionary. It is —
# block ② declares exactly these six integers.
RESOURCE_STATE_OUT = 0  # OFF                      -> OUT
RESOURCE_STATE_ACTIVE = 1  # STAFFED                  -> IN
RESOURCE_STATE_ONBOARDING = 2  # HIRED - ONBOADING PHASE  -> NEW
RESOURCE_STATE_BENCH = 3  # UN/IC - UNASIGNED [8 W]  -> IN
RESOURCE_STATE_LONG_LEAVE = 4  # LONG TERM LEAVE          -> IN
RESOURCE_STATE_NOTICE_PERIOD = 5  # LEAVING COMPANY          -> IN

#: The INDEX sheet's IN grouping: everything except OFF. This is the
#: population that produces facts — time, absences, expenses. Distinct from
#: `STAFFABLE_STATES` (evolution.py), which also excludes long-term leave: a
#: person on leave is not staffed, but they do have an absence.
STATES_IN_HEADCOUNT = (
    RESOURCE_STATE_ACTIVE,
    RESOURCE_STATE_ONBOARDING,
    RESOURCE_STATE_BENCH,
    RESOURCE_STATE_LONG_LEAVE,
    RESOURCE_STATE_NOTICE_PERIOD,
)

#: Who carries a delivery at dataset construction. Distinct from the other two
#: groupings, and all three are needed:
#:   STATES_IN_HEADCOUNT     produces facts (time, absences, expenses)
#:   STAFFABLE_STATES        can be staffed by evolution (evolution.py)
#:   STATES_WITH_DELIVERY    already carries a delivery in the starting dataset
#:
#: Long-term leave is excluded — someone on leave is not staffed. NOTICE
#: PERIOD is not: they work until their term ends, and that is what
#: `STAFFABLE_STATES` already asserted. The bench keeps its explicit exclusion
#: further below: it is ON THE BENCH, that is its definition.
STATES_WITH_DELIVERY = (RESOURCE_STATE_ACTIVE, RESOURCE_STATE_NOTICE_PERIOD)


# ═════════════════════════════════════════════════════════════════════════════
#  Reference data: agencies, BUs, poles, roles
# ═════════════════════════════════════════════════════════════════════════════


def _build_agencies() -> list[dict[str, Any]]:
    agencies: list[dict[str, Any]] = []
    for i, (name, city, postcode, address, reg, vat, staff) in enumerate(_AGENCIES, start=1):
        agencies.append(
            {
                "id": str(i),
                "type": "agency",
                "attributes": {
                    "name": name,
                    "calendar": "Standard",
                    "currency": 0,
                    "numberOfWorkingDays": 218,
                    "chargeFactor": 1.47,
                    "vatNumber": vat,
                    "registrationNumber": reg,
                    "address": address,
                    "postcode": postcode,
                    "town": city,
                    "country": "France",
                    "staff": staff,
                    "state": True,
                    "workUnitRate": 1,
                    "workUnitRateOnProjectsAndOpportunities": 1,
                    "subDivision": "",
                },
            }
        )
    return agencies


def _business_units(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Business units. `includedManagers`: the attached managers (official relation)."""
    units: list[dict[str, Any]] = []
    for i, name in enumerate(_BUSINESS_UNITS, start=1):
        managers = [r for r in resources if r["attributes"]["_bu"] == i and int(r["id"]) <= 6]
        units.append(
            {
                "id": str(i),
                "type": "businessunit",
                "attributes": {
                    "name": name,
                },
                "relationships": {
                    "includedManagers": {
                        "data": [{"id": m["id"], "type": "resource"} for m in managers]
                    }
                },
            }
        )
    return units


def _build_poles() -> list[dict[str, Any]]:
    return [
        {
            "id": str(i),
            "type": "pole",
            "attributes": {
                "name": name,
                "state": True,
            },
        }
        for i, name in enumerate(_POLES, start=1)
    ]


def _build_roles() -> list[dict[str, Any]]:
    rows = [
        # (name, accounts, active, secondary agencies, secondary poles, typeOf, system)
        ("Administrator", 2, 2, True, True, "manager", True),
        ("Leadership", 3, 3, True, True, "manager", False),
        ("Agency Manager", 5, 5, False, True, "manager", False),
        ("HR Manager", 2, 2, False, False, "manager", False),
        ("Intranet Consultant", 28, 26, False, False, "intranet", True),
    ]
    return [
        {
            "id": str(i),
            "type": "role",
            "attributes": {
                "name": name,
                "numberOfAccounts": accounts,
                "numberOfActiveAccounts": active,
                "isSecondaryAgenciesAllowed": ag,
                "isSecondaryPolesAllowed": po,
                "typeOf": type_of,
                "isSystem": system,
            },
        }
        for i, (name, accounts, active, ag, po, type_of, system) in enumerate(rows, start=1)
    ]


# ═════════════════════════════════════════════════════════════════════════════
#  Resources and contracts
# ═════════════════════════════════════════════════════════════════════════════

#: ids 1-6: leadership and managers; 7-30 consultants; 31-32 onboarding;
#: 33-34 departed. Subcontractors carry typeOf 1.
_RESOURCE_COUNT = 34
_MANAGER_IDS = (2, 3, 4, 5, 6)
_SUBCONTRACTOR_IDS = (23, 24)
_ONBOARDING_IDS = (31, 32)
_DEPARTED_IDS = (33, 34)

#: ┌─ AUTHORIZATION EDGE CASES ──────────────────────────────────────────────────┐
#: │ These cohorts do not serve the dataset's realism: they serve the fact      │
#: │ that an authorization model built on it CAN fail. A uniform dataset makes  │
#: │ a visibility test true by vacuity — it passes just as well with a correct  │
#: │ model as with a broken one.                                                │
#: └──────────────────────────────────────────────────────────────────────────────┘

#: Two people with the SAME first name AND SAME last name, in two different
#: agencies. This is the most dangerous edge case of the lot: a consumer who
#: derives a directory identifier (UPN, email) from "firstname.lastname" alone
#: assigns them the same identity, and MERGES their visibility perimeters.
#: This is not a cosmetic defect, it is a silent privilege escalation. Their
#: addresses are therefore deliberately distinct — the ordinal collision
#: resolution is what the consumer must reproduce.
_HOMONYM_IDS = (27, 28)

#: A person whose agency changed during the year. Their facts (time,
#: deliveries) stay attached to the agency where they were produced, not to
#: their current agency. A model that attaches facts to the employee rather
#: than to the fact row retroactively rewrites history — invisible as long as
#: no employee moves.
_TRANSFER_ID = 22
_AGENCY_BEFORE_TRANSFER = 2
#: Month of the transfer: the PRIOR timesheets carry the old agency.
#: Chosen WITHIN the ACTIVITY_MONTHS window (May-July 2026), without which
#: the case does not exist: no timesheet would fall on the right side of the
#: switch.
_TRANSFER_MONTH = 6

#: Month the departed resources leave. They keep their history UP TO this
#: month, and nothing after. Also chosen within ACTIVITY_MONTHS, so that
#: "produced then left" is observable and not merely declared.
_DEPARTURE_MONTH = 5


def _resource_state(i: int, *, departed: bool, onboarding: bool) -> int:
    """A resource's state, in the instance's SIX-value nomenclature.

    Only one state is outgoing. An employee on the bench, on long-term leave
    or on notice always counts in headcount — the IN/OUT/NEW grouping of the
    INDEX sheet.

    The bench identifiers are the ones `in_bench` is already computed on
    further below: the information existed in the dataset without the API
    ever rendering it.
    """
    if departed:
        return RESOURCE_STATE_OUT
    if onboarding:
        return RESOURCE_STATE_ONBOARDING
    if i in (25, 26, 29, 30):
        return RESOURCE_STATE_BENCH
    # 17 and not 11: identifier 11 is `kevin.silva`, the fixture "known to
    # the HRIS, in no Entra group" from insights360's authorization tests.
    # Giving it a specific state would break an unrelated edge case. 12 and
    # 17 carry no fixture, on either side.
    if i == 17:
        return RESOURCE_STATE_LONG_LEAVE
    if i == 12:
        return RESOURCE_STATE_NOTICE_PERIOD
    return RESOURCE_STATE_ACTIVE


def _build_resources(rng: random.Random) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for i in range(1, _RESOURCE_COUNT + 1):
        if i in _HOMONYM_IDS:
            # Same first AND last name for both: see _HOMONYM_IDS.
            first_name, last_name = "Camille", "Fontaine"
        else:
            first_name = _FIRST_NAMES[(i * 7) % len(_FIRST_NAMES)]
            last_name = _LAST_NAMES[(i * 11) % len(_LAST_NAMES)]
        is_leadership = i == 1
        is_manager = i in _MANAGER_IDS
        departed = i in _DEPARTED_IDS
        onboarding = i in _ONBOARDING_IDS
        subcontractor = i in _SUBCONTRACTOR_IDS

        agency = 1 if i in (1, 2, 3) else (2 if i % 3 == 0 else (3 if i % 7 == 0 else 1))
        if i in _HOMONYM_IDS:
            # Two distinct agencies: this is what makes the case discriminant.
            # Homonyms in the same agency, an identity merge would change no
            # perimeter and the test would stay green by mistake.
            agency = 1 if i == _HOMONYM_IDS[0] else 3
        pole = ((i - 1) % len(_POLES)) + 1
        bu = ((i - 1) % len(_BUSINESS_UNITS)) + 1
        if is_leadership:
            title = "Chief Executive Officer"
        elif is_manager:
            title = rng.choice(["Agency Director", "BU Manager", "Operations Director"])
        else:
            # STAFF first, consultant as fallback. Written as a TERNARY and
            # not as `elif`: the extra branch pushed the function to 13
            # branches, above the repo's PLR0912 threshold. The `if` keeps
            # the call to rng.choice off the support path — calling it for
            # nothing would shift the random sequence and change the titles
            # of EVERY other consultant.
            title = _SUPPORT_TITLES[i] if i in _SUPPORT_TITLES else rng.choice(_CONSULTANT_TITLES)

        if onboarding:
            hired = date(2026, 7, 1)
        elif departed:
            hired = date(2019 + i % 4, rng.randint(1, 12), 1)
        else:
            hired = date(rng.randint(2016, 2025), rng.randint(1, 12), 1)
        experience = max(1, 2026 - hired.year + rng.randint(0, 6))

        daily_rate = 0.0
        if not is_leadership and not is_manager:
            senior = "Senior" in title or "Lead" in title or experience >= 8
            daily_rate = float(rng.choice([780, 850, 920] if senior else [520, 580, 640, 700]))

        state = _resource_state(i, departed=departed, onboarding=onboarding)
        email = f"{first_name.lower()}.{last_name.lower()}@boreal-conseil.example"
        if i == _HOMONYM_IDS[1]:
            # Collision resolution by ordinal. The SECOND carries the suffix:
            # that is the directory convention, and it makes the case
            # asymmetric — a consumer that suffixed both would still pass.
            email = f"{first_name.lower()}.{last_name.lower()}2@boreal-conseil.example"
        skills = rng.sample(_SKILLS, k=rng.randint(4, 6))
        on_bench = i in (25, 26, 29, 30)

        resources.append(
            {
                "id": str(i),
                "type": "resource",
                "attributes": {
                    "creationDate": _dt(hired - timedelta(days=rng.randint(20, 90)), 11, 5),
                    "civility": i % 2,
                    "thumbnail": "",
                    "firstName": first_name,
                    "lastName": last_name,
                    "reference": f"BC-{i:04d}",
                    "typeOf": 1 if subcontractor else 0,
                    "state": state,
                    "isVisible": not departed,
                    "skills": ", ".join(skills),
                    "mobilityAreas": rng.choice(
                        [
                            ["Île-de-France"],
                            ["Île-de-France", "Full remote"],
                            ["Auvergne-Rhône-Alpes"],
                            ["Pays de la Loire", "Bretagne"],
                        ]
                    ),
                    "title": title,
                    "availability": "immediate" if on_bench else _d(date(2026, 9, 1)),
                    "forceAvailability": False,
                    "realAvailability": _d(TODAY) if on_bench else "",
                    "averageDailyPriceExcludingTax": daily_rate,
                    "email1": email,
                    "email2": f"{first_name.lower()}.{last_name.lower()}@courriel.example",
                    "email3": "",
                    "phone1": f"+33 6 {rng.randint(10, 99)} {rng.randint(10, 99)} "
                    f"{rng.randint(10, 99)} {rng.randint(10, 99)}",
                    "phone2": "",
                    "currency": 0,
                    "exchangeRate": 1.0,
                    "currencyAgency": 0,
                    "exchangeRateAgency": 1.0,
                    "numberOfResumes": rng.randint(1, 3),
                    "numberOfActivePositionings": rng.randint(1, 3) if on_bench else 0,
                    "updateDate": _plausible_update(
                        rng, date(2026, rng.randint(1, 6), rng.randint(1, 28))
                    ),
                    "tools": [{"tool": c, "level": rng.randint(3, 5)} for c in skills[:4]],
                    "expertiseAreas": rng.sample(_EXPERTISE_AREAS, k=2),
                    "activityAreas": rng.sample(_INDUSTRIES, k=2),
                    "diplomas": [rng.choice(_DIPLOMAS)],
                    "experience": experience,
                    "references": [],  # filled in after project creation
                    "languages": [
                        {"language": code, "level": level}
                        for code, level in rng.sample(_LANGUAGES, k=2)
                    ],
                    "canShowTechnicalData": True,
                    "canShowActions": True,
                    "socialNetworks": [
                        {
                            "network": "linkedin",
                            "url": (
                                "https://www.linkedin.com/in/"
                                f"{first_name.lower()}-{last_name.lower()}"
                            ),
                        }
                    ],
                    # Key INTERNAL to the generator (removed before publication).
                    "_bu": bu,
                },
                "relationships": {
                    "mainManager": _rel(
                        "resource",
                        None if is_leadership else (1 if is_manager else rng.choice(_MANAGER_IDS)),
                    ),
                    # The real API always emits the hrManager key; HR (id 4)
                    # follows the consultants, leadership has none.
                    "hrManager": _rel("resource", 4 if i >= 7 else None),
                    "agency": _rel("agency", agency),
                    "pole": _rel("pole", pole),
                },
            }
        )
    return resources


def _build_contracts(
    resources: list[dict[str, Any]], rng: random.Random, seed: int
) -> list[dict[str, Any]]:
    """One contract per employee, plus six chained fixed-term → permanent histories."""
    contracts: list[dict[str, Any]] = []
    ident = 1

    def _salary(res: dict[str, Any]) -> float:
        daily_rate = res["attributes"]["averageDailyPriceExcludingTax"]
        if res["attributes"]["title"] == "Chief Executive Officer":
            return 9800.0
        if int(res["id"]) in _MANAGER_IDS:
            return float(rng.choice([6200, 6800, 7400]))
        return round((daily_rate or 600) * 4.6 + rng.randint(-150, 150), 0)

    with_fixed_term = {7, 9, 12, 15, 18, 21}
    for res in resources:
        if res["attributes"]["typeOf"] == 1:
            continue  # subcontractors have no employment contract here
        rid = int(res["id"])
        hired = date.fromisoformat(res["attributes"]["creationDate"][:10]) + timedelta(days=30)
        departed = rid in _DEPARTED_IDS
        monthly = _salary(res)

        previous: int | None = None
        if rid in with_fixed_term:
            fixed_term_end = hired + timedelta(days=180)
            contracts.append(
                _build_contract(
                    ident,
                    res,
                    "fixed-term",
                    hired,
                    fixed_term_end,
                    monthly=monthly * 0.92,
                    rng=rng,
                    seed=seed,
                    child=ident + 1,
                )
            )
            previous = ident
            ident += 1
            hired = fixed_term_end + timedelta(days=1)

        end = _month_end(2026, 5) if departed else None
        contracts.append(
            _build_contract(
                ident,
                res,
                "permanent",
                hired,
                end,
                monthly=monthly,
                rng=rng,
                seed=seed,
                parent=previous,
            )
        )
        ident += 1
    return contracts


def _build_contract(
    ident: int,
    res: dict[str, Any],
    nature: str,
    start: date,
    end: date | None,
    *,
    monthly: float,
    rng: random.Random,
    seed: int,
    parent: int | None = None,
    child: int | None = None,
) -> dict[str, Any]:
    # ┌─ THE DAILY COST IS NOT DERIVABLE FROM THE GROSS SALARY ─────────────────┐
    # │ It used to be `monthly * 12 * 1.47 / 218` — the loaded annual gross,    │
    # │ spread over worked days. The formula is plausible, and it is WRONG.      │
    # │                                                                          │
    # │ Tested 2026-09-10 against 25 production contracts:                      │
    # │   1 checks out within 1 %, 24 do not. Median relative gap 11.7 %,        │
    # │   maximum 44.2 %.                                                        │
    # │                                                                          │
    # │ The vendor computes something else — likely real employer contributions │
    # │ and benefits included. Serving a value that derives EXACTLY from the     │
    # │ gross would invite a consumer to "rediscover" a relationship that does   │
    # │ not exist, then recompute the cost themselves instead of reading the     │
    # │ field. The offset below is DETERMINISTIC (derived from the identifier)   │
    # │ and sufficient to break the formula.                                     │
    # └──────────────────────────────────────────────────────────────────────────┘
    daily_cost = round(monthly * 12 * 1.47 / 218 * (0.88 + (ident * 37 % 45) / 100), 2)
    # ┌─ THE CONTRACT'S AGENCY IS NOT ALWAYS THE PROFILE'S ─────────────────────┐
    # │ This is how BoondManager expresses MULTI-AFFILIATION: a person can      │
    # │ have contracts in several agencies, with different roles. The profile   │
    # │ only carries the primary affiliation agency.                            │
    # │                                                                          │
    # │ Measured 2026-09-11 on a production tenant, 70 multi-contract profiles  │
    # │ and 388 contracts: 18 (4.6 %) carry an agency different from their       │
    # │ profile's, and 3 people have contracts across several agencies —        │
    # │ including the CEO, spread across three entities.                        │
    # │                                                                          │
    # │ The dataset used to give EVERY contract its resource's agency. A        │
    # │ consumer taking the entity from the profile was therefore green here    │
    # │ and attached 4.6 % of contracts to the wrong perimeter in production —   │
    # │ readable by some, invisible to others. It happened.                     │
    # │                                                                          │
    # │ The offset is DETERMINISTIC (derived from the identifier) and a         │
    # │ minority.                                                                │
    # │                                                                          │
    # │ ⚠️ IT IS DENSER THAN REALITY, AND THAT IS DELIBERATE: 6 contracts out of │
    # │    38 (15.8 %) versus 4.6 % in production. On a 38-contract dataset,    │
    # │    the real proportion would give one or two rows — too few for a       │
    # │    consumer to ever hit the case, and a fixture that does not carry it  │
    # │    passes green by vacuity. The SHAPE is faithful, the frequency is not. │
    # │                                                                          │
    # │ `test_l_agence_du_contrat_diverge_parfois_de_celle_de_la_fiche` locks    │
    # │ this in.                                                                 │
    # └──────────────────────────────────────────────────────────────────────────┘
    profile_agency = res["relationships"]["agency"]
    other = (ident * 7) % 6 + 1
    contract_agency = (
        _rel("agency", other)
        if ident % 5 == 0 and str(other) != (profile_agency.get("data") or {}).get("id")
        else profile_agency
    )
    # The real API ALWAYS emits the parentContract/childContract keys (data null).
    rels: dict[str, Any] = {
        "dependsOn": _rel("resource", res["id"]),
        "createdBy": _rel("resource", 4),
        "agency": contract_agency,
        "parentContract": _rel("contract", parent),
        "childContract": _rel("contract", child),
        "files": {"data": []},
    }
    return {
        "id": str(ident),
        "type": "contract",
        "attributes": {
            "typeOf": 0 if nature == "permanent" else 1,
            "creationDate": _dt(start - timedelta(days=15), 14, 30),
            "updateDate": _plausible_update(rng, start),
            "employeeType": 0,
            "workingTimeType": 0,
            "numberOfHoursPerWeek": 38.5,
            "classification": rng.choice(
                ["Syntec 2.1 coef 115", "Syntec 2.2 coef 130", "Syntec 3.1 coef 170"]
            ),
            "startDate": _d(start),
            "endDate": _d(end) if end else "",
            "endReason": 3 if end and nature == "permanent" else 0,
            "probationState": 2,
            "monthlySalary": monthly,
            "hourlySalary": round(monthly / 151.67, 2),
            "forceHourlySalary": False,
            "contractAverageDailyCost": daily_cost,
            # ┌─ THREE FIELDS THE MOCK FILLED AND PRODUCTION LEAVES EMPTY ──┐
            # │ Measured 2026-09-10 on 18 contracts: `dailyExpenses`,        │
            # │ `monthlyExpenses`, `expensesDetails` and `calendar` are      │
            # │ SERVED but filled ZERO times. The mock filled them on 38 of  │
            # │ 38 — the most credible fiction there is, and therefore the   │
            # │ costliest: a consumer building on it was green in CI and     │
            # │ found an empty column in production. Same family as         │
            # │ `isDeleted`.                                                 │
            # │                                                              │
            # │ The keys stay emitted — the vendor emits them — with the     │
            # │ value it gives them: empty.                                 │
            # └──────────────────────────────────────────────────────────────┘
            "dailyExpenses": 0,
            "monthlyExpenses": 0,
            "numberOfWorkingDays": 218,
            "chargeFactor": 1.47,
            "expensesDetails": [],
            "advantageTypes": _advantage_types(res, seed),
            "informationComments": "",
            "currency": 0,
            "currencyAgency": 0,
            "exchangeRate": 1.0,
            "exchangeRateAgency": 1.0,
            "calendar": "",
            # Filled ZERO times out of 18 in production. Serving it at 100
            # suggested a gross salary could be weighted by this rate — which
            # cost a consumer 800 compensation rows at zero.
            "activityRate": 0,
            "partialWorkTimes": [],
            "isPartialWorkTimeEvenOdd": False,
            # SPARSE emission, like reality: the key is absent on a third of
            # contracts, it is not null. A consumer that assumes the present
            # key falls here, not in production.
            **(
                {
                    "probationEndDate": _d(start + timedelta(days=120)),
                    "renewalProbationEndDate": "",
                }
                if ident % 3
                else {}
            ),
        },
        "relationships": rels,
    }


#: Boréal Conseil's benefits catalog — instance configuration, hence specific
#: to the fictional world of the mock. Its SHAPE, however, is the one observed
#: in production on 2026-09-10, traps included:
#:
#:   • `reference` is NOT a global code — the same 21 serves two different
#:     labels here, exactly like at the vendor;
#:   • `category` does not say what is vested: "Variable" is `fixedAmount`
#:     while "Prime de vacances" is `variableSalaryBasis`;
#:   • the three quotas are not interchangeable, and none is "the amount" —
#:     depending on the row, only one is set, or two.
#:
#: (reference, name, frequency, category, participation, employee, agency)
ADVANTAGE_CATALOG: tuple[tuple[int, str, str, str, float, float, float], ...] = (
    (7, "Titre restaurant", "daily", "package", 5.83, 5.83, 0.0),
    (6, "Abonnement transport", "monthly", "package", 0.0, 45.4, 0.0),
    (8, "Prime de vacances", "semiAnnual", "variableSalaryBasis", 0.0, 800.0, 12.0),
    (21, "Variable", "annual", "fixedAmount", 0.0, 3000.0, 1.5),
    (21, "Mutuelle", "monthly", "fixedAmount", 0.0, 38.5, 38.5),
    (4, "Prime exceptionnelle", "annual", "fixedAmount", 0.0, 500.0, 0.0),
)


#: Seed offset for AUXILIARY streams.
#:
#: ┌─ WHY THESE GENERATORS DO NOT DRAW FROM `rng` ────────────────────────────┐
#: │ The dataset is deterministic by construction: `random.Random(42)` and a  │
#: │ fixed time anchor. But determinism is not the only property that        │
#: │ matters — STABILITY between two mock versions is another, and it is      │
#: │ more fragile.                                                            │
#: │                                                                           │
#: │ A draw added in the MIDDLE of the shared stream shifts everything        │
#: │ generated after it. Measured when adding advantages: time rows went      │
#: │ from 61 to 60, with not a single row of their own generator having       │
#: │ moved, and a pagination test failed at the other end of the repo. For    │
#: │ the consumer, it is worse: insights360 compares SETS OF IDENTIFIERS (the │
#: │ `inner ⊆ outer` gate), which make no sense if the world shifts under     │
#: │ them.                                                                    │
#: │                                                                           │
#: │ Generators added after the fact therefore draw from a stream DERIVED     │
#: │ from the seed, never from the main stream. Everything that already       │
#: │ existed stays byte for byte identical.                                   │
#: └───────────────────────────────────────────────────────────────────────────┘
ADVANTAGE_SEED_OFFSET = 1_000_003


def _advantage_types(res: dict[str, Any], seed: int) -> list[dict[str, Any]]:
    """A resource's contractual package — from zero to four lines.

    The cardinality is VARIABLE because it is in production (0 to 5 on the
    sample): a dataset where every contract carries exactly one line would
    let a model that only handles that case pass green.
    """
    ident = int(res["id"])
    rng = random.Random(seed * ADVANTAGE_SEED_OFFSET + ident)
    # ┌─ DO NOT SELECT BY MODULO ON THE IDENTIFIER ─────────────────────────────┐
    # │ This test used to read `ident % 7 == 0`, and `_paid_advantages` kept    │
    # │ `ident % 3 == 0`. Both excluded EXACTLY the same cohort: resources 7,   │
    # │ 14 and 28 — that is, the whole Nantes agency, the only entity that     │
    # │ distinguishes two BI roles at the consumer.                            │
    # │                                                                          │
    # │ Consequence: its perimeter-isolation gate saw both roles count the same │
    # │ number of rows and could prove nothing. A dataset that leaves a         │
    # │ business axis empty makes the test GREEN BY VACUITY.                    │
    # │                                                                          │
    # │ An identifier is not a random variable: here it is assigned per agency, │
    # │ so any modulo correlates with the agency. The draw therefore goes       │
    # │ through the dedicated stream, and                                       │
    # │ `test_chaque_agence_porte_du_package` guarantees coverage instead of    │
    # │ hoping for it.                                                          │
    # └──────────────────────────────────────────────────────────────────────────┘
    if rng.random() < 0.15:  # a few contracts have no advantage at all
        return []
    how_many = rng.randint(1, 4)
    return [
        {
            "reference": reference,
            "name": name,
            "frequency": frequency,
            "category": category,
            "participationQuota": participation,
            "employeeQuota": employee,
            "agencyQuota": agency,
        }
        for reference, name, frequency, category, participation, employee, agency in rng.sample(
            ADVANTAGE_CATALOG, how_many
        )
    ]


def _paid_advantages(
    resources: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    seed: int,
) -> list[dict[str, Any]]:
    """The "Avantages versés" tab — one row per payment, dated.

    ┌─ THIS IS WHERE VARIABLE PAY LIVES ──────────────────────────────────────┐
    │ Observed in production on 2026-09-10: `GET /resources/{id}/advantages`  │
    │ renders 200 and `meta.totals.rows` = 54 on one resource, with a         │
    │ 2020 → 2026 history. It carries « Prime sur lettre d'Objectifs »,       │
    │ « Prime exceptionnelle », « Prime de vacances ».                        │
    │                                                                          │
    │ Three properties the dataset REPRODUCES, because they decide a          │
    │ consumer's strategy:                                                    │
    │   1. SPARSE — six of eight resources have no row at all. This is the   │
    │      normal case, not the degraded one.                                 │
    │   2. VERY UNEVEN — a handful of people concentrate dozens of rows. A    │
    │      uniform dataset would hide pagination's cost.                      │
    │   3. ATTACHED TO THE CONTRACT in force ON THE PAYMENT'S DATE, not to    │
    │      the current contract: a person can have had eight successive       │
    │      ones, and a 2020 payment does not attach to the 2026 contract.     │
    └──────────────────────────────────────────────────────────────────────────┘

    No `updateDate`: the vendor renders none, so no cursor is possible.
    Serving one here would invite building an incremental extraction that
    would fetch nothing in production.
    """
    # DEDICATED stream — see the `ADVANTAGE_SEED_OFFSET` box: drawing from
    # the shared stream would shift everything generated afterward.
    rng = random.Random(seed * ADVANTAGE_SEED_OFFSET + 7)

    by_resource: dict[str, list[dict[str, Any]]] = {}
    for contract in contracts:
        rid = contract["relationships"]["dependsOn"]["data"]["id"]
        by_resource.setdefault(rid, []).append(contract)

    # ┌─ EVERY AGENCY CARRIES PAYMENTS, BY CONSTRUCTION ───────────────────────┐
    # │ The draw used to be `ident % 3 == 0`, and it emptied the whole Nantes   │
    # │ agency (7, 14, 28) — see the `_advantage_types` box. At least one       │
    # │ beneficiary per agency is therefore forced BEFORE the random draw: a   │
    # │ business axis's coverage is not left to chance.                        │
    # └───────────────────────────────────────────────────────────────────────────┘
    # The WITNESS: the resource with the long history, analogous to profile
    # 583 in production (54 payments, 2020 → 2026). It is the one that
    # exercises pagination at the consumer — a random draw must not be able
    # to make it disappear.
    required: set[str] = {"3"}
    covered_agencies: set[str] = set()
    for res in resources:
        if not by_resource.get(res["id"]):
            continue
        agency = ((res["relationships"].get("agency") or {}).get("data") or {}).get("id")
        if agency is not None and agency not in covered_agencies:
            covered_agencies.add(agency)
            required.add(res["id"])

    advantages: list[dict[str, Any]] = []
    next_id = 9000
    for res in resources:
        rid = res["id"]
        own = by_resource.get(rid) or []
        if not own:
            continue
        ident = int(rid)
        # About a third gets something, plus the required ones. The witness
        # — resource 3 — concentrates several dozen, like profile 583 in
        # production.
        if rid not in required and rng.random() >= 0.35:
            continue
        how_many = 42 if ident == 3 else rng.randint(1, 6)

        for _ in range(how_many):
            carrier = rng.choice(own)
            start = date.fromisoformat(carrier["attributes"]["startDate"])
            end_text = carrier["attributes"]["endDate"]
            end = date.fromisoformat(end_text) if end_text else TODAY
            if end <= start:
                continue
            # Paid DURING the carrying contract: this is what makes the
            # `contract` relationship verifiable rather than decorative.
            paid_on = start + timedelta(days=rng.randint(0, (end - start).days))
            reference, name, _freq, _cat, _p, employee, _a = rng.choice(ADVANTAGE_CATALOG)
            quantity = rng.choice([1, 1, 1, 1, 15, 20, 21, 23])
            next_id += 1
            advantages.append(
                {
                    "id": str(next_id),
                    "type": "advantage",
                    "attributes": {
                        "date": _d(paid_on),
                        "quantity": quantity,
                        "costPaid": round(employee * quantity, 2),
                        # Empty across the whole production sample.
                        "returnDate": "",
                        "currency": 0,
                        "currencyAgency": 0,
                        "exchangeRate": 1,
                        "exchangeRateAgency": 1,
                        "canReadAdvantage": True,
                        "canWriteAdvantage": True,
                        "advantageType": {"reference": reference, "name": name},
                    },
                    "relationships": {
                        "contract": _rel("contract", int(carrier["id"])),
                        "agency": res["relationships"]["agency"],
                    },
                }
            )
    return advantages


# ═════════════════════════════════════════════════════════════════════════════
#  Candidates
# ═════════════════════════════════════════════════════════════════════════════


def _build_candidates(rng: random.Random) -> list[dict[str, Any]]:
    sources = [
        (1, "LinkedIn"),
        (2, "Referral"),
        (3, "Careers site"),
        (4, "Headhunting"),
        (5, "Big Data Paris trade show"),
    ]
    candidates: list[dict[str, Any]] = []
    for i in range(1, 13):
        first_name = _FIRST_NAMES[(i * 13 + 3) % len(_FIRST_NAMES)]
        last_name = _LAST_NAMES[(i * 17 + 5) % len(_LAST_NAMES)]
        creation = date(2026, rng.randint(1, 6), rng.randint(1, 28))
        state = [0, 1, 1, 2, 2, 3, 4, 5][i % 8]
        title = rng.choice(_CONSULTANT_TITLES)
        skills = rng.sample(_SKILLS, k=4)
        source_type, source_detail = rng.choice(sources)
        candidates.append(
            {
                "id": str(i),
                "type": "candidate",
                "attributes": {
                    "creationDate": _dt(creation, 10, 12),
                    "updateDate": _plausible_update(rng, creation),
                    "civility": i % 2,
                    "thumbnail": "",
                    "firstName": first_name,
                    "lastName": last_name,
                    "typeOf": 0,
                    "state": state,
                    "isVisible": True,
                    "skills": ", ".join(skills),
                    "mobilityAreas": rng.choice(
                        [["Île-de-France"], ["Full remote"], ["Auvergne-Rhône-Alpes"]]
                    ),
                    "title": title,
                    # ┌─ ON A CANDIDATE, `availability` IS A CODE ─────────────┐
                    # │ Not a date. Observed 2026-08-12 on 26 814 production    │
                    # │ candidates: INTEGERS, `-1` on 24 289 of them, then 0,   │
                    # │ 1, 3, 4… The mock served an ISO date, and               │
                    # │ `stg_candidat` cast it to a date — hence, on the first  │
                    # │ real run, « invalid input syntax for type bigint: "" ». │
                    # │                                                         │
                    # │ ⚠️ Do not confuse with a RESOURCE's `availability`,    │
                    # │    which IS a date. Same name, two types, two entities:│
                    # │    this is precisely the kind of gap a mock must carry │
                    # │    rather than smooth over.                            │
                    # │                                                         │
                    # │ The code → label mapping is NOT established: it lives  │
                    # │ in the instance dictionary, family `availability`. The │
                    # │ mock therefore renders raw codes, and the consumer who  │
                    # │ wants a label goes through it.                         │
                    # └─────────────────────────────────────────────────────────┘
                    "availability": rng.choice([-1, -1, -1, -1, 0, 1, 3, 4]),
                    "email1": f"{first_name.lower()}.{last_name.lower()}@courriel.example",
                    "email2": "",
                    "email3": "",
                    "phone1": f"+33 7 {rng.randint(10, 99)} {rng.randint(10, 99)} "
                    f"{rng.randint(10, 99)} {rng.randint(10, 99)}",
                    "phone2": "",
                    "town": rng.choice(["Paris", "Lyon", "Nantes", "Bordeaux"]),
                    "country": "France",
                    "source": {"typeOf": source_type, "detail": source_detail},
                    "numberOfResumes": rng.randint(1, 2),
                    "numberOfActivePositionings": 1 if state in (2, 3) else 0,
                    "socialNetworks": [
                        {
                            "network": "linkedin",
                            "url": (
                                "https://www.linkedin.com/in/"
                                f"{first_name.lower()}-{last_name.lower()}"
                            ),
                        }
                    ],
                    "diplomas": [rng.choice(_DIPLOMAS)],
                    "activityAreas": rng.sample(_INDUSTRIES, k=2),
                    # The user guide reports FEWER THAN 2% of candidates rated
                    # in production. An empty string is NOT a null: it counts
                    # as a rating for anyone testing presence, and masks the
                    # quality gap the model must expose.
                    "globalEvaluation": "4.0" if i == 1 else ("3.5" if i == 5 else None),
                    "languages": [
                        {"language": code, "level": level}
                        for code, level in rng.sample(_LANGUAGES, k=2)
                    ],
                    "expertiseAreas": rng.sample(_EXPERTISE_AREAS, k=1),
                    "experience": rng.randint(2, 12),
                    "references": [
                        {
                            "id": str(i * 10 + n),
                            "title": rng.choice(_CONSULTANT_TITLES),
                            "company": rng.choice(_CLIENTS)[0],
                            "location": rng.choice(["Paris", "Lyon", "Remote"]),
                            "startMonth": f"{rng.randint(1, 12):02d}",
                            "startYear": str(2020 + n),
                            "endMonth": f"{rng.randint(1, 12):02d}",
                            "endYear": str(2021 + n),
                            "skills": ", ".join(rng.sample(_SKILLS, k=3)),
                            "description": "Consulting and implementation delivery.",
                            "startDate": "",
                            "endDate": "",
                            "row": n,
                        }
                        for n in range(1, rng.randint(2, 3))
                    ],
                    "evaluations": (
                        [
                            {
                                "id": str(i),
                                "notations": [
                                    {"criteria": 1, "evaluation": str(rng.randint(3, 5))},
                                    {"criteria": 2, "evaluation": str(rng.randint(3, 5))},
                                ],
                                "date": _d(creation + timedelta(days=10)),
                                "comments": "Good technical interview, to follow up.",
                                "manager": {"id": "4", "firstName": "Hugo", "lastName": "Dubois"},
                            }
                        ]
                        if state >= 2
                        else []
                    ),
                    "tools": [{"tool": c, "level": rng.randint(2, 5)} for c in skills[:3]],
                    "canShowTechnicalData": True,
                    "canShowActions": True,
                },
                "relationships": {
                    "mainManager": _rel("resource", rng.choice((2, 4, 6))),
                    "agency": _rel("agency", rng.randint(1, 3)),
                    "pole": _rel("pole", rng.randint(1, len(_POLES))),
                },
            }
        )
    return candidates


# ═════════════════════════════════════════════════════════════════════════════
#  CRM: companies, contacts, opportunities
# ═════════════════════════════════════════════════════════════════════════════


def _build_companies(rng: random.Random) -> list[dict[str, Any]]:
    companies: list[dict[str, Any]] = []
    for i, (name, city, industry, site, prospect) in enumerate(_CLIENTS, start=1):
        creation = date(2022 + i % 3, ((i * 5) % 12) + 1, 15)
        companies.append(
            {
                "id": str(i),
                "type": "company",
                "attributes": {
                    "name": name,
                    "expertiseArea": industry,
                    "state": 0 if prospect else 1,
                    "informationComments": (
                        "Qualified prospect — first proposal in progress."
                        if prospect
                        else "Active client."
                    ),
                    "thumbnail": "",
                    "website": site,
                    "phone1": f"+33 {rng.randint(1, 5)} {rng.randint(10, 99)} "
                    f"{rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)}",
                    "town": city,
                    "country": "Belgium" if city == "Bruxelles" else "France",
                    "creationDate": _dt(creation, 9, 45),
                    "updateDate": _plausible_update(rng, date(2026, 1, 10)),
                    "socialNetworks": [
                        {
                            "network": "linkedin",
                            "url": "https://www.linkedin.com/company/"
                            f"{name.lower().replace(' ', '-')}",
                        }
                    ],
                },
                "relationships": {
                    "mainManager": _rel("resource", rng.choice((2, 3, 5))),
                    "agency": _rel(
                        "agency", 2 if city == "Lyon" else (3 if city == "Nantes" else 1)
                    ),
                    "pole": _rel("pole", rng.randint(1, len(_POLES))),
                },
            }
        )
    return companies


def _build_contacts(companies: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    ident = 1
    for company in companies[:10]:  # contacts live at clients
        for _ in range(2 if int(company["id"]) % 2 == 0 else 3):
            if ident > 22:
                break
            first_name = _FIRST_NAMES[(ident * 19 + 7) % len(_FIRST_NAMES)]
            last_name = _LAST_NAMES[(ident * 23 + 2) % len(_LAST_NAMES)]
            domain = company["attributes"]["website"].removeprefix("https://")
            creation = date(2024 + ident % 2, ((ident * 3) % 12) + 1, 10)
            contacts.append(
                {
                    "id": str(ident),
                    "type": "contact",
                    "attributes": {
                        "creationDate": _dt(creation, 11, 20),
                        "civility": ident % 2,
                        "thumbnail": "",
                        "firstName": first_name,
                        "lastName": last_name,
                        "state": 1,
                        "function": rng.choice(_CONTACT_FUNCTIONS),
                        "department": rng.choice(_CONTACT_DEPARTMENTS),
                        "email1": f"{first_name.lower()}.{last_name.lower()}@{domain}",
                        "email2": "",
                        "email3": "",
                        "phone1": f"+33 6 {rng.randint(10, 99)} {rng.randint(10, 99)} "
                        f"{rng.randint(10, 99)} {rng.randint(10, 99)}",
                        "phone2": "",
                        "town": company["attributes"]["town"],
                        "country": company["attributes"]["country"],
                        "canReadContact": True,
                        "canWriteContact": True,
                        "canShowAction": True,
                        "typesOf": [],
                        "socialNetworks": [],
                        "updateDate": _plausible_update(rng, creation),
                    },
                    "relationships": {
                        "mainManager": company["relationships"]["mainManager"],
                        "company": _rel("company", company["id"]),
                        "agency": company["relationships"]["agency"],
                        "pole": company["relationships"]["pole"],
                    },
                }
            )
            ident += 1
    return contacts


def _build_opportunities(
    companies: list[dict[str, Any]],
    contacts: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """15 opportunities: 6 won (→ projects), 5 ongoing, 3 lost, 1 on hold.

    States aligned with the REAL INSTANCE, observed in the mappings file's
    "Besoins" export (08 - LOST, 09 - POSTPONED / ABANDONED) and consistent
    with the Confluence process "BOOND - Need creation & Management":
    1 Open · 2 Qualified · 3 Proposed solution · 7 WON · 8 LOST · 9 POSTPONED.

    The mock used to code 4/5/6, which exist nowhere in the instance: a
    consumer who wrote "state = 4 → won" produced a figure that was correct
    in dev and wrong in production, with nothing signaling it.
    """
    plan = [7, 7, 7, 7, 7, 7, 1, 2, 2, 3, 1, 8, 8, 8, 9]
    opportunities: list[dict[str, Any]] = []
    for i, state in enumerate(plan, start=1):
        company = companies[(i * 3) % 10]
        company_contacts = [
            c for c in contacts if c["relationships"]["company"]["data"]["id"] == company["id"]
        ]
        contact = rng.choice(company_contacts) if company_contacts else None
        subject, tools = _DELIVERY_SUBJECTS[(i * 5) % len(_DELIVERY_SUBJECTS)]
        creation = date(2025, ((i * 7) % 12) + 1, rng.randint(2, 26))
        lost = state == 8
        mode = 1 if i % 3 else 2  # 1 = technical assistance, 2 = fixed price
        days = rng.choice([120, 180, 240, 300])
        average_daily_rate = rng.choice([620, 680, 750, 820])
        estimate = float(days * average_daily_rate)
        probability = {1: 0.3, 2: 0.5, 3: 0.7, 7: 1.0, 8: 0.0, 9: 0.1}[state]
        closing = creation + timedelta(days=rng.randint(30, 120))
        opportunities.append(
            {
                "id": str(i),
                "type": "opportunity",
                "attributes": {
                    "creationDate": _dt(creation, 9, 30),
                    "title": f"{subject} — {company['attributes']['name']}",
                    "reference": f"AO-{creation.year}-{i:03d}",
                    "typeOf": 1,
                    "mode": mode,
                    "state": state,
                    "place": company["attributes"]["town"],
                    "isVisible": True,
                    # ┌─ `startDate` IS NOT ALWAYS A DATE ──────────────────┐
                    # │ On a NEED, the vendor renders the literal string     │
                    # │ "immediate" when the start is immediate. And it is   │
                    # │ not an edge case: 1 523 of the 1 850 production      │
                    # │ needs, i.e. 82 %.                                    │
                    # │                                                      │
                    # │ The mock only ever served dates, so                  │
                    # │ `stg_opportunite` cast with no safety net and hit    │
                    # │ « invalid input syntax for type date: "immediate" ». │
                    # │                                                      │
                    # │ Same value, same meaning as a RESOURCE's             │
                    # │ `availability` — the dialect reuses this literal for │
                    # │ "right away" everywhere a date is expected. A        │
                    # │ consumer must therefore anticipate it on ANY start-  │
                    # │ date field, not just here.                           │
                    # │                                                      │
                    # │ Deliberately majority proportion: a dataset where the│
                    # │ dominant case is a minority lets models that do not  │
                    # │ handle it pass.                                      │
                    # └──────────────────────────────────────────────────────┘
                    "startDate": (
                        "" if lost else ("immediate" if i % 5 else _d(closing + timedelta(days=30)))
                    ),
                    "endDate": _d(closing + timedelta(days=30 + days)) if not lost else "",
                    "closingDate": _d(closing) if state in (4, 5) else "",
                    "answerDate": _d(creation + timedelta(days=21)),
                    "duration": days,
                    "currency": 0,
                    "exchangeRate": 1.0,
                    "currencyAgency": 0,
                    "exchangeRateAgency": 1.0,
                    "turnoverWeightedExcludingTax": round(estimate * probability, 2),
                    "estimatesExcludingTax": estimate,
                    "turnoverEstimatedExcludingTax": estimate,
                    "expertiseArea": rng.choice(_EXPERTISE_AREAS),
                    "activityAreas": [company["attributes"]["expertiseArea"]],
                    "origin": {
                        "typeOf": rng.randint(1, 4),
                        "detail": rng.choice(
                            [
                                "Inbound call",
                                "Referral",
                                "Framework consultation",
                                "RFP response",
                            ]
                        ),
                    },
                    "tools": tools,
                    "numberOfActivePositionings": 0 if state in (4, 5, 6) else rng.randint(1, 3),
                    "canShowContact": True,
                    "canShowCompany": True,
                    "stateReason": (
                        {
                            "typeOf": 2,
                            "detail": rng.choice(
                                ["Price", "Competitor selected", "Project deferred"]
                            ),
                        }
                        if lost
                        else {"typeOf": 0, "detail": ""}
                    ),
                    "updateDate": _plausible_update(rng, closing if state in (4, 5) else creation),
                },
                "relationships": {
                    "mainManager": company["relationships"]["mainManager"],
                    "agency": company["relationships"]["agency"],
                    "pole": company["relationships"]["pole"],
                    "contact": _rel("contact", contact["id"] if contact else None),
                    "company": _rel("company", company["id"]),
                    "parsingJob": _rel("opportunityparsingjob", None),
                },
            }
        )
    return opportunities


# ═════════════════════════════════════════════════════════════════════════════
#  Production: projects, deliveries, worked days
# ═════════════════════════════════════════════════════════════════════════════


def _need_start_date(attributes: dict[str, Any]) -> date:
    """A need's start date, `immediate` resolved.

    The vendor renders either a date or the literal string "immediate" — the
    latter on 82% of production needs. Any read of this field must therefore
    anticipate both shapes; this helper exists so the mock itself does not
    forget it in its own internal derivations.
    """
    value = attributes.get("startDate") or ""
    if value and value != "immediate":
        return date.fromisoformat(value)
    # "immediate": the start follows the need's creation with no delay.
    return date.fromisoformat(str(attributes["creationDate"])[:10])


def _build_projects(
    opportunities: list[dict[str, Any]],
    companies: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """12 projects: 6 from won opportunities, 6 historical (2025).

    8 are ongoing at the anchor (July 2026), 4 are finished — their bounds
    drive deliveries, timesheets and invoices.
    """
    projects = []
    won = [o for o in opportunities if o["attributes"]["state"] == 7]
    for i in range(1, 13):
        if i <= len(won):
            opp = won[i - 1]
            company_id = opp["relationships"]["company"]["data"]["id"]
            company = companies[int(company_id) - 1]
            # `startDate` is "immediate" on the majority of needs: the
            # project then starts right away, and the closest anchor
            # available here is the need's creation date. This is exactly
            # the call a consumer has to make — the mock makes it too,
            # rather than excluding these needs and making the literal
            # unreachable downstream.
            start = _need_start_date(opp["attributes"])
            mode = opp["attributes"]["mode"]
            reference_year = start.year
        else:
            opp = None
            company = companies[(i * 7) % 10]
            start = date(2025, ((i * 5) % 10) + 1, 1)
            mode = 1 if i % 2 else 2
            reference_year = start.year
        ongoing = i <= 8
        end = date(2026, 12, 31) if ongoing else _month_end(2026, (i % 4) + 1)
        if not ongoing and end <= start:
            end = _month_end(start.year, min(12, start.month + 6))
        projects.append(
            {
                "id": str(i),
                "type": "project",
                "attributes": {
                    "startDate": _d(start),
                    "endDate": _d(end),
                    "typeOf": mode,
                    "mode": mode,
                    "reference": f"PRJ-{reference_year}-{i:03d}",
                    "currency": 0,
                    "exchangeRate": 1.0,
                    "currencyAgency": 0,
                    "exchangeRateAgency": 1.0,
                    # Recalculated from deliveries right after.
                    "turnoverSimulatedExcludingTax": 0.0,
                    "marginSimulatedExcludingTax": 0.0,
                    "profitabilitySimulated": 0.0,
                    "canReadProject": True,
                    "canShowContact": True,
                    "canShowCompany": True,
                    "canShowIntermediaryContact": True,
                    "canShowIntermediaryCompany": True,
                    "canShowCurrency": True,
                    "canShowCurrencyAgency": True,
                    "canShowExchangeRate": True,
                    "canShowExchangeRateAgency": True,
                    "canShowProfitabilitySimulated": True,
                    "canShowTurnoverSimulatedExcludingTax": True,
                    "canShowMarginSimulatedExcludingTax": True,
                    "creationDate": _dt(start - timedelta(days=20), 15, 10),
                    "updateDate": _plausible_update(rng, start),
                },
                "relationships": {
                    "mainManager": company["relationships"]["mainManager"],
                    "opportunity": _rel("opportunity", opp["id"] if opp else None),
                    "contact": (opp["relationships"]["contact"] if opp else _rel("contact", None)),
                    "company": _rel("company", company["id"]),
                    "agency": company["relationships"]["agency"],
                    "pole": company["relationships"]["pole"],
                    "intermediaryCompany": _rel("company", None),
                    "intermediaryContact": _rel("contact", None),
                },
            }
        )
    return projects


def _build_deliveries(
    projects: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """20 deliveries — the consultant ↔ project link.

    `GET /deliveries` search is not documented in the external RAML (POST
    only): items follow the official PROFILE schema shape, stripped of the
    rate scales (empty arrays, like a young instance).
    """
    consultants = [
        r
        for r in resources
        if int(r["id"]) >= 7
        and r["attributes"]["state"] in STATES_WITH_DELIVERY
        and int(r["id"]) not in (25, 26, 29, 30)  # the bench stays on the bench
    ]
    deliveries: list[dict[str, Any]] = []
    ident = 1
    consultant_queue = consultants.copy()
    for project in projects:
        count = 2 if int(project["id"]) % 2 == 0 else 1
        if project["id"] in ("1", "2"):
            count = 3
        for _ in range(count):
            if not consultant_queue:
                consultant_queue = consultants.copy()
            consultant = consultant_queue.pop(0)
            if ident > 20:
                break
            project_start = date.fromisoformat(project["attributes"]["startDate"])
            project_end = date.fromisoformat(project["attributes"]["endDate"])
            daily_rate = consultant["attributes"]["averageDailyPriceExcludingTax"] or 650.0
            cost = round(daily_rate * 0.58, 2)
            planned_days = max(20, min(((project_end - project_start).days * 5) // 7 - 10, 220))
            turnover = round(daily_rate * planned_days, 2)
            costs = round(cost * planned_days, 2)
            subcontracted = int(consultant["id"]) in _SUBCONTRACTOR_IDS
            deliveries.append(
                {
                    "id": str(ident),
                    "type": "delivery",
                    "attributes": {
                        "startDate": _d(project_start),
                        "endDate": _d(project_end),
                        "title": consultant["attributes"]["title"],
                        "typeOf": 1 if subcontracted else 0,
                        "state": 1 if project_end >= TODAY else 2,
                        "canShowAverageDailyContractCost": True,
                        "averageDailyPriceExcludingTax": daily_rate,
                        "forceAverageDailyPriceExcludingTax": False,
                        "subscriptionQuantityCharged": 0,
                        "subscriptionQuantityFree": 0,
                        "subscriptionPriceExcludingTax": 0.0,
                        "averageDailyCost": cost,
                        "averageDailyContractCost": cost,
                        "numberOfDaysInvoicedOrQuantity": float(planned_days),
                        "numberOfDaysFree": 0,
                        "informationComments": "",
                        "conditions": "",
                        "turnoverSimulatedExcludingTax": turnover,
                        "costsSimulatedExcludingTax": costs,
                        "marginSimulatedExcludingTax": round(turnover - costs, 2),
                        "profitabilitySimulated": (
                            round((turnover - costs) / turnover * 100, 2) if turnover else 0.0
                        ),
                        "occupationRate": 100.0,
                        "dailyExpenses": 9.05,
                        "monthlyExpenses": 75.0,
                        "numberOfWorkingDays": 218,
                        "weeklyWorkingHours": 38.5,
                        "averageHourlyPriceExcludingTax": 0.0,
                        "forceAverageHourlyPriceExcludingTax": False,
                        "additionalTurnoverAndCosts": [],
                        "expensesDetails": [],
                        "advantageTypes": [],
                        "exceptionalScales": [],
                        "creationDate": _dt(project_start - timedelta(days=12), 16, 40),
                        "updateDate": _plausible_update(rng, project_start),
                        "calendar": "Standard",
                        "isTurnoverProductionIncluded": True,
                    },
                    "relationships": {
                        "project": _rel("project", project["id"]),
                        "dependsOn": _rel("resource", consultant["id"]),
                        "purchase": _rel("purchase", None),  # set for subcontracting
                    },
                }
            )
            ident += 1
    return deliveries


def _worked_days(
    deliveries: list[dict[str, Any]], rng: random.Random
) -> dict[tuple[str, int, int], float]:
    """Worked days per (delivery, year, month) — the matrix that keeps
    invoices and time rows CONSISTENT: both consume it as-is."""
    matrix: dict[tuple[str, int, int], float] = {}
    for delivery in deliveries:
        start = date.fromisoformat(delivery["attributes"]["startDate"])
        end = date.fromisoformat(delivery["attributes"]["endDate"])
        current_month = date(2026, 1, 1)
        while current_month <= min(end, date(2026, 7, 31)):
            year, month = current_month.year, current_month.month
            if _month_end(year, month) >= start:
                working = _working_days(year, month)
                if (year, month) == (2026, 7):
                    worked = 9.0  # month in progress at the July 15 anchor
                else:
                    worked = float(working - rng.choice([0, 0, 1, 1, 2]))
                matrix[(delivery["id"], year, month)] = worked
            current_month = _month_end(year, month) + timedelta(days=1)
    return matrix


# ═════════════════════════════════════════════════════════════════════════════
#  Billing: orders, invoices, banking transactions
# ═════════════════════════════════════════════════════════════════════════════


def _build_orders(
    projects: list[dict[str, Any]],
    deliveries: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    ident = 1
    for project in projects:
        project_deliveries = [
            m for m in deliveries if m["relationships"]["project"]["data"]["id"] == project["id"]
        ]
        if not project_deliveries:
            continue
        order_turnover = round(
            sum(m["attributes"]["turnoverSimulatedExcludingTax"] for m in project_deliveries), 2
        )
        start = date.fromisoformat(project["attributes"]["startDate"])
        orders.append(
            {
                "id": str(ident),
                "type": "order",
                "attributes": {
                    "date": _d(start - timedelta(days=5)),
                    "number": f"CMD-{start.year}-{ident:03d}",
                    "reference": f"PO-{rng.randint(40000, 99999)}",
                    "customerAgreement": True,
                    # turnoverInvoiced/delta recalculated after invoices.
                    "turnoverInvoicedExcludingTax": 0.0,
                    "turnoverOrderedExcludingTax": order_turnover,
                    "deltaInvoicedExcludingTax": order_turnover,
                    "state": 1,
                    # ┌─ NEITHER `creationDate` NOR `updateDate` ON ORDERS ────┐
                    # │ The vendor renders NEITHER of the two. Probed           │
                    # │ 2026-08-12: `/orders` is the only one of the eighteen   │
                    # │ collections missing `updateDate`, and its dlt landing   │
                    # │ in production does not carry `creation_date` either.    │
                    # │                                                         │
                    # │ `updateDate` first: it drives the extraction STRATEGY. │
                    # │ Seeing it here, insights360 declared the collection     │
                    # │ incremental, and dlt raised                             │
                    # │ `IncrementalCursorPathMissing` on the first real run —  │
                    # │ taking down the six collections declared after it.      │
                    # │                                                         │
                    # │ `creationDate` next, and it is a mistake worth naming:  │
                    # │ the gap registry already listed it as absent from the   │
                    # │ tenant, and 0.6.0 chose to serve it anyway on the        │
                    # │ grounds that "it drives no strategy, so serving it      │
                    # │ costs nothing". That was false. A model that READS a    │
                    # │ column needs it to EXIST: `stg_commande` hit             │
                    # │ "column o.creation_date does not exist" on the next     │
                    # │ run.                                                    │
                    # │                                                         │
                    # │ The rule therefore admits no "harmless" exception.      │
                    # │ `date` stays: it is the order date, and it is indeed    │
                    # │ rendered for real.                                      │
                    # └──────────────────────────────────────────────────────────┘
                },
                "relationships": {
                    "mainManager": project["relationships"]["mainManager"],
                    "project": _rel("project", project["id"]),
                },
            }
        )
        ident += 1
    return orders


def _build_invoices(
    orders: list[dict[str, Any]],
    deliveries: list[dict[str, Any]],
    matrix: dict[tuple[str, int, int], float],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """One invoice per order and per elapsed month — amount = sum of days x daily rate.

    May and before: settled. June: sent, due in 30 days. July: a draft. A
    credit note (`isCreditNote`) corrects an over-billing.
    """
    invoices: list[dict[str, Any]] = []
    ident = 1
    for order in orders:
        project_id = order["relationships"]["project"]["data"]["id"]
        project_deliveries = [
            m for m in deliveries if m["relationships"]["project"]["data"]["id"] == project_id
        ]
        for year, month in [(2026, m) for m in range(1, 8)]:
            amount = sum(
                matrix.get((m["id"], year, month), 0.0)
                * m["attributes"]["averageDailyPriceExcludingTax"]
                for m in project_deliveries
            )
            if amount <= 0:
                continue
            issued = _month_end(year, month) + timedelta(days=2)
            if issued > TODAY:
                if month != 7 or int(order["id"]) % 4 != 1:
                    continue
                issued = TODAY  # draft for the current month
                state, sending, paid_on = 0, 0, None
            elif month <= 5:
                state, sending = 2, 2
                paid_on = issued + timedelta(days=rng.randint(18, 32))
            else:
                state, sending, paid_on = 1, 1, None
            amount = round(amount, 2)
            including_tax = round(amount * (1 + VAT_RATE), 2)
            invoices.append(
                {
                    "id": str(ident),
                    "type": "invoice",
                    "attributes": {
                        "date": _d(issued),
                        "expectedPaymentDate": _d(issued + timedelta(days=30)),
                        "turnoverInvoicedExcludingTax": amount,
                        "turnoverInvoicedIncludingTax": including_tax,
                        "isCreditNote": False,
                        "reference": f"FAC-{year}-{ident:04d}",
                        "state": state,
                        "selfBilling": False,
                        "sendingState": sending,
                        "refuseReason": "",
                        "providerId": "",
                        "providerUrl": "",
                        "taxReportState": 0,
                        "currency": 0,
                        "exchangeRate": 1.0,
                        "currencyAgency": 0,
                        "exchangeRateAgency": 1.0,
                        "paymentMethod": 1,
                        "closed": state == 2,
                        "totalPayableIncludingTax": including_tax,
                        "creationDate": _dt(issued, 8, 5),
                        "updateDate": _dt(min(paid_on or issued, LAST_UPDATE), 14, 10),
                        "startDate": _d(date(year, month, 1)),
                        "endDate": _d(_month_end(year, month)),
                        "performedPaymentDate": _d(paid_on) if paid_on else "",
                        "canSendWithPeppol": True,
                        "canSendWithDgfip": False,
                        "canSendWithPennylane": False,
                    },
                    "relationships": {
                        "order": _rel("order", order["id"]),
                        "schedule": _rel("schedule", None),
                    },
                }
            )
            ident += 1

    # The credit note: correcting an over-billing on the first settled invoice.
    settled = [f for f in invoices if f["attributes"]["state"] == 2]
    if settled:
        origin = settled[0]
        amount = round(-0.1 * origin["attributes"]["turnoverInvoicedExcludingTax"], 2)
        credit_date = date.fromisoformat(origin["attributes"]["date"]) + timedelta(days=14)
        invoices.append(
            {
                "id": str(ident),
                "type": "invoice",
                "attributes": {
                    **origin["attributes"],
                    "date": _d(credit_date),
                    "expectedPaymentDate": _d(credit_date),
                    "turnoverInvoicedExcludingTax": amount,
                    "turnoverInvoicedIncludingTax": round(amount * (1 + VAT_RATE), 2),
                    "totalPayableIncludingTax": round(amount * (1 + VAT_RATE), 2),
                    "isCreditNote": True,
                    "reference": f"AV-2026-{ident:04d}",
                    "performedPaymentDate": "",
                    "closed": False,
                    "state": 1,
                    "sendingState": 1,
                    "creationDate": _dt(credit_date, 9, 55),
                    "updateDate": _dt(credit_date, 9, 55),
                },
                "relationships": dict(origin["relationships"]),
            }
        )

    # Realigning order cumulatives — the coherence visible on the first diff.
    for order in orders:
        invoice_total = round(
            sum(
                f["attributes"]["turnoverInvoicedExcludingTax"]
                for f in invoices
                if f["relationships"]["order"]["data"]["id"] == order["id"]
                and f["attributes"]["state"] > 0
            ),
            2,
        )
        order["attributes"]["turnoverInvoicedExcludingTax"] = invoice_total
        order["attributes"]["deltaInvoicedExcludingTax"] = round(
            order["attributes"]["turnoverOrderedExcludingTax"] - invoice_total, 2
        )
    return invoices


def _build_banking(
    invoices: list[dict[str, Any]],
    companies: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Accounts, connections and transactions: the settled invoices' receipts."""
    connections = [
        {"id": "1", "type": "bankingconnection", "attributes": {"bankName": "BNP Paribas"}},
        {"id": "2", "type": "bankingconnection", "attributes": {"bankName": "Qonto"}},
    ]
    accounts = [
        {
            "id": "1",
            "type": "bankingaccount",
            "attributes": {
                "name": "Main checking account",
                "title": "FR76 3000 4028 3700 0104 5678 921",
            },
            "relationships": {"connection": _rel("bankingconnection", 1)},
        },
        {
            "id": "2",
            "type": "bankingaccount",
            "attributes": {
                "name": "Expenses account",
                "title": "FR76 1695 8000 0187 6543 2109 876",
            },
            "relationships": {"connection": _rel("bankingconnection", 2)},
        },
    ]

    def _company_of(invoice: dict[str, Any]) -> str:
        order = next(
            c for c in orders if c["id"] == invoice["relationships"]["order"]["data"]["id"]
        )
        project = next(
            p for p in projects if p["id"] == order["relationships"]["project"]["data"]["id"]
        )
        company = next(
            s for s in companies if s["id"] == project["relationships"]["company"]["data"]["id"]
        )
        return str(company["attributes"]["name"])

    transactions: list[dict[str, Any]] = []
    settled = [f for f in invoices if f["attributes"]["performedPaymentDate"]]
    for i, invoice in enumerate(settled[:14], start=1):
        attrs = invoice["attributes"]
        day = date.fromisoformat(attrs["performedPaymentDate"])
        reconciled = i <= 11
        transactions.append(
            {
                "id": str(i),
                "type": "bankingtransaction",
                "attributes": {
                    "amount": attrs["totalPayableIncludingTax"],
                    "currency": 0,
                    "date": _dt(day, rng.randint(3, 7), rng.randint(0, 59)),
                    "numberOfInvoices": 1 if reconciled else 0,
                    "title": f"VIR SEPA {_company_of(invoice).upper()} {attrs['reference']}",
                    "state": 2 if reconciled else 0,
                    "totalAmountToReconcile": 0.0
                    if reconciled
                    else attrs["totalPayableIncludingTax"],
                    "canReadTransaction": True,
                    "canWriteTransaction": True,
                    "canReconcile": True,
                },
                "relationships": {"account": _rel("bankingaccount", 1)},
            }
        )
    # Two supplier debits on the second account, unreconciled.
    for n, (label, amount) in enumerate(
        [
            ("PRLV SEPA SOFTALLIANCE ABONNEMENT DATA-2026-07", 1068.0),
            ("PRLV SEPA FONCIERE BEAUMONT LOYER 2026-07", 9960.0),
        ],
        start=len(transactions) + 1,
    ):
        transactions.append(
            {
                "id": str(n),
                "type": "bankingtransaction",
                "attributes": {
                    "amount": amount,
                    "currency": 0,
                    "date": _dt(date(2026, 7, 5), 4, 45),
                    "numberOfInvoices": 0,
                    "title": label,
                    "state": 0,
                    "totalAmountToReconcile": amount,
                    "canReadTransaction": True,
                    "canWriteTransaction": True,
                    "canReconcile": True,
                },
                "relationships": {"account": _rel("bankingaccount", 2)},
            }
        )
    return accounts, connections, transactions


# ═════════════════════════════════════════════════════════════════════════════
#  Purchases and supplier payments
# ═════════════════════════════════════════════════════════════════════════════


def _build_purchases(
    deliveries: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """8 purchases: subcontracting attached to deliveries, licenses, rent, equipment."""
    purchases: list[dict[str, Any]] = []
    ident = 1

    subcontracted_deliveries = [
        m
        for m in deliveries
        if int(m["relationships"]["dependsOn"]["data"]["id"]) in _SUBCONTRACTOR_IDS
    ][:2]
    for delivery in subcontracted_deliveries:
        consultant = next(
            r for r in resources if r["id"] == delivery["relationships"]["dependsOn"]["data"]["id"]
        )
        purchase_rate = round(delivery["attributes"]["averageDailyPriceExcludingTax"] * 0.72, 2)
        days = delivery["attributes"]["numberOfDaysInvoicedOrQuantity"]
        start = date.fromisoformat(delivery["attributes"]["startDate"])
        purchases.append(
            {
                "id": str(ident),
                "type": "purchase",
                "attributes": {
                    "date": _d(start - timedelta(days=8)),
                    "title": f"Subcontracting {consultant['attributes']['firstName']} "
                    f"{consultant['attributes']['lastName']} — Fivetech Partners",
                    "subscription": 0,
                    "typeOf": 0,
                    "reference": f"ACH-2026-{ident:03d}",
                    "state": 1,
                    "taxRate": 20.0,
                    "currency": 0,
                    "exchangeRate": 1.0,
                    "currencyAgency": 0,
                    "exchangeRateAgency": 1.0,
                    "amountExcludingTax": purchase_rate,
                    "quantity": days,
                    "totalAmountExcludingTax": round(purchase_rate * days, 2),
                    "deltaExcludingTax": 0.0,  # recalculated after payments
                    "engagedPaymentsAmountExcludingTax": 0.0,
                    "creationDate": _dt(start - timedelta(days=8), 11, 45),
                    "updateDate": _plausible_update(rng, start),
                },
                "relationships": {
                    "mainManager": _rel("resource", 2),
                    "project": delivery["relationships"]["project"],
                    "delivery": _rel("delivery", delivery["id"]),
                    "contact": _rel("contact", None),
                    "company": _rel("company", _SUPPLIER_ID_SUBCONTRACTING),
                    "agency": _rel("agency", 1),
                    "pole": _rel("pole", None),
                },
            }
        )
        delivery["relationships"]["purchase"] = _rel("purchase", ident)
        ident += 1

    general = [
        ("Data platform licenses — Softalliance", 1, 2, 890.0, 12, _SUPPLIER_ID_LICENSES),
        ("Observability subscription — Softalliance", 1, 2, 340.0, 12, _SUPPLIER_ID_LICENSES),
        ("Consultant workstations", 0, 4, 1650.0, 6, _SUPPLIER_ID_LICENSES),
        ("Paris agency rent", 1, 3, 8300.0, 12, _SUPPLIER_ID_RENT),
        ("Lyon agency rent", 1, 3, 2900.0, 12, _SUPPLIER_ID_RENT),
        ("Nantes project room furniture", 0, 4, 4200.0, 1, _SUPPLIER_ID_RENT),
    ]
    for title, subscription, type_of, amount, quantity, supplier in general:
        day = date(2026, 1, rng.randint(3, 20))
        purchases.append(
            {
                "id": str(ident),
                "type": "purchase",
                "attributes": {
                    "date": _d(day),
                    "title": title,
                    "subscription": subscription,
                    "typeOf": type_of,
                    "reference": f"ACH-2026-{ident:03d}",
                    "state": 1,
                    "taxRate": 20.0,
                    "currency": 0,
                    "exchangeRate": 1.0,
                    "currencyAgency": 0,
                    "exchangeRateAgency": 1.0,
                    "amountExcludingTax": amount,
                    "quantity": float(quantity),
                    "totalAmountExcludingTax": round(amount * quantity, 2),
                    "deltaExcludingTax": 0.0,
                    "engagedPaymentsAmountExcludingTax": 0.0,
                    "creationDate": _dt(day, 10, 25),
                    "updateDate": _plausible_update(rng, day),
                },
                "relationships": {
                    "mainManager": _rel("resource", 1),
                    "project": _rel("project", None),
                    "delivery": _rel("delivery", None),
                    "contact": _rel("contact", None),
                    "company": _rel("company", supplier),
                    "agency": _rel("agency", 1),
                    "pole": _rel("pole", None),
                },
            }
        )
        ident += 1
    return purchases


def _build_payments(purchases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Purchase payment schedules — past ones settled, upcoming ones planned."""
    payments: list[dict[str, Any]] = []
    ident = 1
    for purchase in purchases:
        attrs = purchase["attributes"]
        if attrs["subscription"] == 1:
            installments = [
                (date(2026, month, 5), attrs["amountExcludingTax"]) for month in (5, 6, 7)
            ]
        else:
            total = attrs["totalAmountExcludingTax"]
            installments = [
                (date(2026, 4, 15), round(total * 0.4, 2)),
                (date(2026, 7, 25), round(total * 0.6, 2)),
            ]
        for day, amount in installments:
            done = day <= TODAY
            payments.append(
                {
                    "id": str(ident),
                    "type": "payment",
                    "attributes": {
                        "date": _d(day),
                        "performedDate": _d(day + timedelta(days=1)) if done else "",
                        "expectedDate": _d(day),
                        "state": 1 if done else 0,
                        "number": f"VIR-2026-{ident:03d}",
                        "amountExcludingTax": amount,
                        "amountIncludingTax": round(amount * (1 + VAT_RATE), 2),
                        "numberOfFiles": 0,
                        "canWritePayment": True,
                        "creationDate": _dt(day - timedelta(days=10), 9, 20),
                        "updateDate": _dt(min(day, LAST_UPDATE), 15, 40),
                    },
                    "relationships": {"purchase": _rel("purchase", purchase["id"])},
                }
            )
            ident += 1
        engaged = round(
            sum(
                p["attributes"]["amountExcludingTax"]
                for p in payments
                if p["relationships"]["purchase"]["data"]["id"] == purchase["id"]
            ),
            2,
        )
        attrs["engagedPaymentsAmountExcludingTax"] = engaged
        attrs["deltaExcludingTax"] = round(attrs["totalAmountExcludingTax"] - engaged, 2)
    return payments


# ═════════════════════════════════════════════════════════════════════════════
#  Activity: timesheets, time, absences, expenses
# ═════════════════════════════════════════════════════════════════════════════


def _build_timesreports(
    resources: list[dict[str, Any]], rng: random.Random
) -> tuple[list[dict[str, Any]], dict[tuple[str, int, int], str]]:
    """One timesheet per active consultant and per activity month. Also
    returns the (resource_id, year, month) → timesreport_id index that time
    rows consume."""
    timesreports: list[dict[str, Any]] = []
    index: dict[tuple[str, int, int], str] = {}
    ident = 1
    for res in resources:
        rid = int(res["id"])
        if rid <= 6:
            continue
        departed = res["attributes"]["state"] == RESOURCE_STATE_OUT
        for year, month in ACTIVITY_MONTHS:
            if rid in _ONBOARDING_IDS and month < 7:
                continue
            # A DEPARTED resource keeps its history up to its departure, and
            # nothing after. Giving it NO timesheet at all would erase the
            # past: a former employee must stay visible in historical facts
            # (compensation, worked time) while having no application
            # visibility left. These are two distinct properties, and
            # conflating them is what makes a leaver keep access rights — or
            # lose the trace of what they produced.
            if departed and month > _DEPARTURE_MONTH:
                continue
            if month == 7:
                state = rng.choice(["waitingForValidation", "savedAndNoValidation"])
                closed = False
            else:
                state = "validated"
                closed = True
            timesreports.append(
                {
                    "id": str(ident),
                    "type": "timesreport",
                    "attributes": {
                        "term": f"{year:04d}-{month:02d}",
                        "state": state,
                        "closed": closed,
                    },
                    "relationships": {
                        # The agency comes from the FACT ROW, not from the
                        # employee: see _TRANSFER_ID. A transferred person
                        # keeps their prior timesheets under their old agency.
                        "agency": (
                            _rel("agency", _AGENCY_BEFORE_TRANSFER)
                            if rid == _TRANSFER_ID and month < _TRANSFER_MONTH
                            else res["relationships"]["agency"]
                        ),
                        "resource": _rel("resource", res["id"]),
                    },
                }
            )
            index[(res["id"], year, month)] = str(ident)
            ident += 1
    return timesreports, index


def _build_times(
    deliveries: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    matrix: dict[tuple[str, int, int], float],
    timesreport_index: dict[tuple[str, int, int], str],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Time rows: production per delivery (the SAME days as invoices),
    intercontract for the bench, and a few on-call rows."""
    times: list[dict[str, Any]] = []
    # Real ids are composite and sequential PER CATEGORY: `regular_1`,
    # `exceptional_1`… (observed on tenant: first id `regular_1`).
    counters = {"regular": 0, "exceptional": 0}

    def _time_id(category: str) -> str:
        counters[category] += 1
        return f"{category}_{counters[category]}"

    for delivery in deliveries:
        res_id = delivery["relationships"]["dependsOn"]["data"]["id"]
        for year, month in ACTIVITY_MONTHS:
            days = matrix.get((delivery["id"], year, month))
            timesreport_id = timesreport_index.get((res_id, year, month))
            if not days or timesreport_id is None:
                continue
            times.append(
                {
                    "id": _time_id("regular"),
                    "type": "time",
                    "attributes": {
                        "category": "regular",
                        "workUnitType": {
                            "reference": 1,
                            "activityType": "production",
                            "name": "Production day",
                        },
                        "row": 1,
                        "startDate": _d(date(year, month, 1)),
                        "duration": days,
                    },
                    "relationships": {
                        "timesReport": _rel("timesreport", timesreport_id),
                        "delivery": _rel("delivery", delivery["id"]),
                        "batch": _rel("batch", None),
                        "project": delivery["relationships"]["project"],
                    },
                }
            )
            if rng.random() < 0.12:
                times.append(
                    {
                        "id": _time_id("exceptional"),
                        "type": "time",
                        "attributes": {
                            "category": "exceptional",
                            "workUnitType": {
                                "reference": 40,
                                "activityType": "exceptionalTime",
                                "name": "Weekend on-call",
                            },
                            "row": 2,
                            "startDate": _d(date(year, month, rng.choice([7, 14, 21]))),
                            "duration": 1.0,
                        },
                        "relationships": {
                            "timesReport": _rel("timesreport", timesreport_id),
                            "delivery": _rel("delivery", delivery["id"]),
                            "batch": _rel("batch", None),
                            "project": delivery["relationships"]["project"],
                        },
                    }
                )

    # The bench logs intercontract time — no delivery nor project, the real dialect.
    for res in resources:
        if res["attributes"]["availability"] != "immediate":
            continue
        for year, month in ACTIVITY_MONTHS:
            timesreport_id = timesreport_index.get((res["id"], year, month))
            if timesreport_id is None or month < 6:
                continue
            times.append(
                {
                    "id": _time_id("regular"),
                    "type": "time",
                    "attributes": {
                        "category": "regular",
                        "workUnitType": {
                            "reference": 10,
                            "activityType": "internal",
                            "name": "Intercontract",
                        },
                        "row": 1,
                        "startDate": _d(date(year, month, 1)),
                        "duration": 9.0 if month == 7 else float(_working_days(year, month)),
                    },
                    "relationships": {
                        "timesReport": _rel("timesreport", timesreport_id),
                        "delivery": _rel("delivery", None),
                        "batch": _rel("batch", None),
                        "project": _rel("project", None),
                    },
                }
            )
    return times


def _build_absences(
    resources: list[dict[str, Any]],
    agencies: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Absence rows, context EMBEDDED (report, agency, resource) — the real
    /absences dialect: everything lives in `attributes`, no relationships."""
    absences: list[dict[str, Any]] = []
    ident = 1
    report_id = 1
    for res in resources:
        rid = int(res["id"])
        # Facts follow HEADCOUNT, not just the STAFFED state alone. A person
        # on the bench still takes leave and incurs expenses; a person on
        # long-term leave has, by definition, an absence. Filtering on
        # `state == 1` deprived them of any fact — same defect as the bench.
        if rid <= 2 or res["attributes"]["state"] not in STATES_IN_HEADCOUNT:
            continue
        agency = next(
            a for a in agencies if a["id"] == res["relationships"]["agency"]["data"]["id"]
        )
        ranges: list[tuple[date, date, tuple[int, str]]] = [
            # Summer vacation, booked ahead — report pending.
            (date(2026, 8, 3), date(2026, 8, 14), _ABSENCE_TYPES[0]),
        ]
        if rid % 2 == 0:
            rtt = date(2026, 5, rng.choice([15, 22]))  # two Fridays in May
            ranges.append((rtt, rtt, _ABSENCE_TYPES[1]))
        if rid % 5 == 0:
            # Two consecutive working days: step back to a Monday-Thursday pair.
            sick_start = date(2026, 6, rng.randint(8, 18))
            while sick_start.weekday() > 3:
                sick_start -= timedelta(days=1)
            ranges.append((sick_start, sick_start + timedelta(days=1), _ABSENCE_TYPES[2]))
        if rid % 9 == 0:
            day = date(2026, 6, 26)
            ranges.append((day, day, _ABSENCE_TYPES[3]))

        for start, end, (reference, label) in ranges:
            days = sum(
                1
                for n in range((end - start).days + 1)
                if (start + timedelta(days=n)).weekday() < 5
            )
            future = start > TODAY
            creation = start - timedelta(days=rng.randint(15, 45))
            absences.append(
                {
                    "id": str(ident),
                    "type": "absence",
                    "attributes": {
                        "startDate": _d(start),
                        "endDate": _d(end),
                        "duration": float(days),
                        "title": label,
                        "workUnitType": {
                            "reference": reference,
                            "activityType": "absence",
                            "name": label,
                        },
                        "absencesReport": {
                            "id": str(report_id),
                            "creationDate": _dt(creation, 8, 40),
                            "state": "waitingForValidation" if future else "validated",
                            "agency": {
                                "id": agency["id"],
                                "name": agency["attributes"]["name"],
                                "workUnitRate": 1,
                            },
                            "resource": {
                                "id": res["id"],
                                "lastName": res["attributes"]["lastName"],
                                "firstName": res["attributes"]["firstName"],
                                "workUnitRate": 1,
                            },
                        },
                    },
                }
            )
            ident += 1
            report_id += 1
    return absences


def _build_expenses(
    deliveries: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    agencies: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Expense reports — embedded context (report, delivery, project), like
    /absences. One report per (consultant, month), mileage and real expenses mixed."""
    expenses: list[dict[str, Any]] = []
    ident = 1
    report_id = 1
    expense_deliveries = [m for m in deliveries if int(m["id"]) % 2 == 1][:10]
    for delivery in expense_deliveries:
        res = next(
            r for r in resources if r["id"] == delivery["relationships"]["dependsOn"]["data"]["id"]
        )
        project = next(
            p for p in projects if p["id"] == delivery["relationships"]["project"]["data"]["id"]
        )
        agency = next(
            a for a in agencies if a["id"] == res["relationships"]["agency"]["data"]["id"]
        )
        for year, month in ACTIVITY_MONTHS:
            if month == 7 and int(res["id"]) % 3 == 0:
                continue
            report = {
                "id": str(report_id),
                "term": f"{year:04d}-{month:02d}",
                "state": "validated" if month < 7 else "waitingForValidation",
                "ratePerKilometerType": {"reference": 3, "name": "Barème 5 CV", "amount": 0.548},
                "advance": 0.0,
                "agency": {"id": agency["id"], "name": agency["attributes"]["name"]},
                "resource": {
                    "id": res["id"],
                    "lastName": res["attributes"]["lastName"],
                    "firstName": res["attributes"]["firstName"],
                },
            }
            report_id += 1
            rows: list[tuple[tuple[int, str, float], float, bool, int]] = [
                (_EXPENSE_TYPES[0][:3], round(rng.uniform(18, 52), 2), False, 0),
                (_EXPENSE_TYPES[1][:3], round(rng.uniform(30, 120), 2), True, 0),
            ]
            if int(res["id"]) % 4 == 0:
                rows.append((_EXPENSE_TYPES[3][:3], 0.0, False, rng.choice([180, 240, 320])))
            for row, ((type_ref, type_name, rate), base_amount, reinvoiced, km) in enumerate(
                rows, start=1
            ):
                mileage = km > 0
                total_tax = round(km * 0.548, 2) if mileage else base_amount
                day = date(year, month, rng.randint(2, 26))
                expenses.append(
                    {
                        "id": str(ident),
                        "type": "expense",
                        "attributes": {
                            "category": "actual",
                            "activityType": "production",
                            "expenseType": {
                                "reference": type_ref,
                                "taxRate": rate,
                                "name": type_name,
                            },
                            "row": row,
                            "startDate": _d(day),
                            "reinvoiced": reinvoiced,
                            "amountIncludingTax": total_tax,
                            "tax": 0.0
                            if mileage
                            else round(total_tax - total_tax / (1 + rate / 100), 2),
                            "numberOfKilometers": float(km),
                            "number": 1,
                            "title": f"{type_name} — {project['attributes']['reference']}",
                            "currency": 0,
                            "exchangeRate": 1.0,
                            "isKilometricExpense": mileage,
                            "expensesReport": report,
                            "delivery": {
                                "id": delivery["id"],
                                "title": delivery["attributes"]["title"],
                                "startDate": delivery["attributes"]["startDate"],
                                "endDate": delivery["attributes"]["endDate"],
                            },
                            "project": {
                                "id": project["id"],
                                "reference": project["attributes"]["reference"],
                            },
                        },
                    }
                )
                ident += 1
    return expenses


# ═════════════════════════════════════════════════════════════════════════════
#  CRM actions
# ═════════════════════════════════════════════════════════════════════════════


def _build_actions(
    candidates: list[dict[str, Any]],
    contacts: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    *,
    resources: list[dict[str, Any]],
    invoices: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """~45 actions attached to their entities via `dependsOn` — the real dialect."""
    actions: list[dict[str, Any]] = []
    ident = 1

    def _add_action(
        target_type: str,
        target_id: str,
        type_of: int,
        text: str,
        *,
        day: date,
        manager: int,
        company_id: str | None,
    ) -> None:
        nonlocal ident
        actions.append(
            {
                "id": str(ident),
                "type": "action",
                "attributes": {
                    "startDate": _dt(day, rng.randint(9, 18), rng.choice([0, 15, 30, 45])),
                    "creationDate": _dt(day, 8, 5),
                    "typeOf": type_of,
                    "text": text,
                    "numberOfFiles": 0,
                    "canReadAction": True,
                    "canWriteAction": True,
                    "updateDate": _dt(min(day, LAST_UPDATE), 18, 55),
                },
                "relationships": {
                    "mainManager": _rel("resource", manager),
                    "dependsOn": _rel(target_type, target_id),
                    "company": _rel("company", company_id),
                    "relatedActions": {"data": []},
                },
            }
        )
        ident += 1

    # A single action per candidate, always the same type, leaves NOTHING to
    # reconstruct: no step dates, no durations, no "time to hire". A consumer
    # then computes a zero-day pipeline duration for every candidate — and a
    # column full of zeros reads as data, not as a gap.
    #
    # Paces VARY deliberately: identical delays would make any average
    # artificial. It is dispersion that makes a test dataset useful.
    _STEPS = [
        (1, "Phone prequalification — profile consistent with the need."),
        (2, "Interview 1 — background and motivation, positive feedback."),
        (3, "Technical interview 2 — hands-on data exercise."),
        (4, "Reference check with the former manager."),
        (5, "Interview 3 with practice leadership."),
        (6, "Proposal sent."),
    ]
    # Delays in days since creation. The LENGTH of the list decides where the
    # pipeline stops: 3 complete, 2 stopped at interview 2, 2 in progress, 1
    # sourced only.
    _PACES = {
        1: [7, 14, 22, 30, 38, 52],
        2: [5, 19, 33, 47, 61, 90],
        3: [9, 16, 24, 31, 40, 55],
        4: [6, 13, 21],
        5: [11, 25, 38],
        6: [8, 20],
        7: [12],
        8: [7, 15, 23, 29],
    }
    for candidate in candidates:
        cid = int(candidate["id"])
        creation = date.fromisoformat(candidate["attributes"]["creationDate"][:10])
        pace = _PACES.get(cid)
        if pace is None:
            # The others keep a single action: a dataset where ALL have a
            # complete pipeline would be just as unrealistic as one where
            # none do.
            _add_action(
                "candidate",
                candidate["id"],
                1,
                "Phone prequalification — to follow up.",
                day=creation + timedelta(days=7),
                manager=rng.choice((2, 4, 6)),
                company_id=None,
            )
            continue
        for (type_of, text), delay in zip(_STEPS, pace, strict=False):
            _add_action(
                "candidate",
                candidate["id"],
                type_of,
                text,
                day=creation + timedelta(days=delay),
                manager=rng.choice((2, 4, 6)),
                company_id=None,
            )
    for contact in contacts[:12]:
        day = date(2026, rng.randint(2, 7), rng.randint(1, 26))
        _add_action(
            "contact",
            contact["id"],
            rng.choice([1, 2, 3]),
            rng.choice(
                [
                    "Follow-up call — budget concerns discussed.",
                    "Account review lunch, upcoming milestones reviewed.",
                    "Sent the data & AI offerings brochure.",
                ]
            ),
            day=min(day, TODAY),
            manager=rng.choice((2, 3, 5)),
            company_id=contact["relationships"]["company"]["data"]["id"],
        )
    for opportunity in opportunities[:10]:
        day = date.fromisoformat(opportunity["attributes"]["creationDate"][:10]) + timedelta(
            days=rng.randint(5, 40)
        )
        _add_action(
            "opportunity",
            opportunity["id"],
            rng.choice([3, 5]),
            rng.choice(
                [
                    "Proposal defense in front of the selection committee.",
                    "Follow-up on the proposal sent — decision expected within two weeks.",
                    "Scoping the need with the business team.",
                ]
            ),
            day=day,
            manager=rng.choice((2, 3, 5)),
            company_id=opportunity["relationships"]["company"]["data"]["id"],
        )
    for project in projects[:8]:
        day = date(2026, rng.randint(4, 7), rng.randint(1, 26))
        _add_action(
            "project",
            project["id"],
            6,
            "Monthly steering committee — progress in line with the plan.",
            day=min(day, TODAY),
            manager=rng.choice((2, 3, 5)),
            company_id=project["relationships"]["company"]["data"]["id"],
        )
    for res in [r for r in resources if 7 <= int(r["id"]) <= 14]:
        day = date(2026, rng.randint(1, 6), rng.randint(2, 26))
        _add_action(
            "resource",
            res["id"],
            7,
            "Annual review — objectives and training plan updated.",
            day=day,
            manager=4,
            company_id=None,
        )
    overdue = [
        f for f in invoices if f["attributes"]["state"] == 1 and not f["attributes"]["isCreditNote"]
    ][:3]
    for invoice in overdue:
        day = date.fromisoformat(invoice["attributes"]["expectedPaymentDate"])
        _add_action(
            "invoice",
            invoice["id"],
            2,
            f"Payment follow-up {invoice['attributes']['reference']} with accounting.",
            day=min(day, TODAY),
            manager=2,
            company_id=None,
        )
    return actions


# ═════════════════════════════════════════════════════════════════════════════
#  Technical data and compensation (affordances kept)
# ═════════════════════════════════════════════════════════════════════════════


def _build_technical_data(
    resources: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    companies: list[dict[str, Any]],
    rng: random.Random,
) -> dict[str, dict[str, Any]]:
    technical_data = {}
    for res in resources:
        attrs = res["attributes"]
        count = rng.randint(1, 3)
        references: list[dict[str, Any]] = []
        for n in range(count):
            project = rng.choice(projects)
            company = next(
                s for s in companies if s["id"] == project["relationships"]["company"]["data"]["id"]
            )
            start = date.fromisoformat(project["attributes"]["startDate"])
            skills = rng.sample(_SKILLS, k=3)
            references.append(
                {
                    "id": f"{int(res['id']) * 100 + n + 1}",
                    "title": attrs["title"],
                    "company": company["attributes"]["name"],
                    "description": (
                        f"{attrs['title']} engagement for {company['attributes']['name']}: "
                        "scoping, delivery, and industrialization of the target solution."
                    ),
                    "location": company["attributes"]["town"],
                    "startMonth": start.month,
                    "startYear": start.year,
                    "endMonth": min(12, start.month + 6),
                    "endYear": start.year,
                    "skills": skills,
                }
            )
        technical_data[res["id"]] = {
            "id": res["id"],
            "type": "resource",
            "attributes": {
                "description": (
                    f"{attrs['title']} — {attrs['experience']} years of experience, "
                    f"engagements in {', '.join(attrs['expertiseAreas'])}."
                ),
                "summary": f"{attrs['title']}, {attrs['experience']} years of experience.",
                "references": references,
            },
        }
    return technical_data


def _build_remuneration(
    resources: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    agencies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The CSV fixture outside /api — now DERIVED from the official contracts."""
    rows: list[dict[str, Any]] = []
    for contract in contracts:
        if contract["attributes"]["typeOf"] != 0:  # permanent contracts only
            continue
        res = next(
            r for r in resources if r["id"] == contract["relationships"]["dependsOn"]["data"]["id"]
        )
        agency = next(
            a for a in agencies if a["id"] == res["relationships"]["agency"]["data"]["id"]
        )
        rows.append(
            {
                "collaborateur_id": res["id"],
                "upn": res["attributes"]["email1"],
                "entite": agency["attributes"]["name"],
                "periode": contract["attributes"]["startDate"],
                "montant_brut_annuel": int(contract["attributes"]["monthlySalary"] * 12),
            }
        )
    return rows


# ═════════════════════════════════════════════════════════════════════════════
#  Assembly
# ═════════════════════════════════════════════════════════════════════════════


def _build_dictionary() -> dict[str, Any]:
    """The INSTANCE-CONFIGURED enumeration labels.

    The API renders integers; labels are not product constants.
    `GET /application/dictionary` is the only place that gives them, and
    without it no consumer can translate a code.

    Two shapes coexist deliberately — a dict of sub-domains for `state`, a
    list for everything else. That is what the vendor's documentation
    describes.

    ⚠️ `action` and `actionOnOpportunity` are TWO distinct keys. The instance
    carries two action nomenclatures that share labels under different codes
    (« TOUCH POINT » exists as 01 and as 09, with two meanings): merging them
    would translate a need's action type with a general label.

    The values describe the codes the mock RENDERS — a dictionary that does
    not match the dataset would pass tests with wrong translations, which is
    worse than a mute mock. The coverage test ensures this.
    """
    return {
        "state": {
            "opportunity": [
                {"id": 1, "value": "Open"},
                {"id": 2, "value": "Qualified (working on solution)"},
                {"id": 3, "value": "Proposed solution"},
                {"id": 7, "value": "WON"},
                {"id": 8, "value": "LOST"},
                {"id": 9, "value": "POSTPONED / ABANDONED"},
            ],
            "candidate": [
                {"id": 0, "value": "SOURCED"},
                {"id": 1, "value": "PREQUAL [1ST CONTACT]"},
                {"id": 2, "value": "ITW 1 [TA/BM]"},
                {"id": 3, "value": "ITW 2 [TECH/BUSINESS]"},
                {"id": 4, "value": "REFERENCE CHECK"},
                {"id": 5, "value": "ITW 3 [DIR/PARTNER]"},
            ],
            # THE SIX STATES, because the dataset renders six since block ③.
            # It used to declare only three: a dictionary that does not
            # cover its own dataset passes tests with missing translations —
            # the defect this docstring forbids two lines above.
            #
            # ⚠️ THE NUMBERING REMAINS THE MOCK'S OWN, AND IT IS NOT
            # ATTESTED. The INDEX sheet numbers the labels from 01 to 06, but
            # `stg_collaborateur.sql` has already decided this prefix is a
            # DISPLAY CONVENTION of the instance, not the integer the API
            # renders. For opportunities, two independent sources agreed —
            # the Confluence process AND the export. Here there is only the
            # prefix: one match does not make a rule.
            #
            # This route is precisely what will settle the question the day
            # it queries the real instance. Until then, the mock is
            # consistent with itself, and that is all a mock must guarantee.
            "resource": [
                {"id": 0, "value": "OFF"},
                {"id": 1, "value": "STAFFED"},
                {"id": 2, "value": "HIRED - ONBOADING PHASE"},
                {"id": 3, "value": "UN/IC - UNASIGNED [From 8 W to now]"},
                {"id": 4, "value": "LONG TERM LEAVE"},
                {"id": 5, "value": "LEAVING COMPANY"},
            ],
            # ── Sub-domains added in 0.5.5 ────────────────────────────────
            # The mock used to render these integers with nothing able to
            # translate them. Each label comes from a dataset branch, cited
            # in the comment.
            #
            # `"state": 0 if prospect else 1` in _build_companies.
            "company": [
                {"id": 0, "value": "Prospect"},
                {"id": 1, "value": "Client"},
            ],
            # ⚠️ SILENT CONSTANT. _build_contacts sets `"state": 1` on every
            # contact, with no branch that gives it meaning. The label is of
            # our own making: it makes the code translatable, it does not
            # attest it. The Boond guide describes a contact qualification
            # (Decision maker / Influencer / Buyer / Inactive) but gives NO
            # code — the fallback reference table's `code` column is empty,
            # and staying that way is deliberate.
            "contact": [
                {"id": 1, "value": "Active"},
            ],
            # ⚠️ SILENT CONSTANT — _build_orders sets `"state": 1` everywhere.
            "order": [
                {"id": 1, "value": "Validated"},
            ],
            # ⚠️ SILENT CONSTANT — _build_purchases sets `"state": 1` on both
            # purchase families, those attached to a delivery and the
            # general ones.
            "purchase": [
                {"id": 1, "value": "Validated"},
            ],
            # `settled = [f for f in invoices if f["attributes"]["state"] == 2]`
            # and `"closed": state == 2` in _build_invoices: 2 is the terminal
            # state. 0 is the state of invoices neither sent nor paid, 1 that
            # of sent invoices awaiting settlement.
            "invoice": [
                {"id": 0, "value": "Draft"},
                {"id": 1, "value": "Sent"},
                {"id": 2, "value": "Paid"},
            ],
            # `"state": 1 if done else 0` in _build_payments.
            "payment": [
                {"id": 0, "value": "Pending"},
                {"id": 1, "value": "Executed"},
            ],
            # `"state": 2 if reconciled else 0` in _build_banking. 1 is
            # never rendered: it is therefore not declared. A dictionary that
            # announces codes the dataset does not produce is just as
            # misleading as the reverse — it suggests coverage that does not
            # exist.
            "bankingTransaction": [
                {"id": 0, "value": "Not reconciled"},
                {"id": 2, "value": "Reconciled"},
            ],
            # `"state": 1 if project_end >= TODAY else 2` in _build_deliveries.
            # The delivery list ROUTE answers 405 at the vendor — only the
            # detail exists — but the object does carry this state, and the
            # marts consume it via the project.
            "delivery": [
                {"id": 1, "value": "In progress"},
                {"id": 2, "value": "Completed"},
            ],
        },
        # ── `typeOf`, symmetric to `state` ───────────────────────────────────
        #
        # ⚠️ THE SHAPE IS OF OUR OWN MAKING, like `state` before it. What is
        # attested: the API renders an integer `typeOf` on five object
        # families and gives its label nowhere else. Marked `invented` in the
        # model and in docs/UNVERIFIED-FIELDS.md.
        "typeOf": {
            # PROVEN, and the only one of this block to be: six mock tests
            # establish that `typeOf` carries employee/subcontractor and
            # drives contract generation. This is NOT the sixteen-type
            # nomenclature of the INDEX sheet — an earlier version of this
            # patch assumed it was, the tests disproved it.
            "resource": [
                {"id": 0, "value": "Employee"},
                {"id": 1, "value": "Subcontractor"},
            ],
            # ⚠️ SILENT CONSTANT — _build_candidates sets `"typeOf": 0` everywhere.
            "candidate": [
                {"id": 0, "value": "Default"},
            ],
            # ⚠️ SILENT CONSTANT — _build_opportunities sets `"typeOf": 1` on
            # the list route.
            "opportunity": [
                {"id": 1, "value": "Default"},
            ],
            # `mode = 1 if i % 3 else 2` and the dataset's comment, word for
            # word: "1 = technical assistance, 2 = fixed price". _build_projects
            # copies this mode into `typeOf`.
            "project": [
                {"id": 1, "value": "Technical assistance"},
                {"id": 2, "value": "Fixed price"},
            ],
            # _build_purchases' `general` table carries the type in its 3rd
            # column: licenses and subscriptions at 2, rent at 3, equipment
            # at 4. 0 is for purchases attached to a delivery, i.e.
            # subcontracting.
            "purchase": [
                {"id": 0, "value": "Subcontracting"},
                {"id": 2, "value": "Software and licenses"},
                {"id": 3, "value": "Premises"},
                {"id": 4, "value": "Equipment"},
            ],
        },
        "action": [
            {"id": 1, "value": "TODO / Reminder"},
            {"id": 2, "value": "Touch point"},
            {"id": 3, "value": "1st Prospection meeting"},
            {"id": 4, "value": "DVP"},
            {"id": 5, "value": "Project review meeting"},
            {"id": 6, "value": "Client presentation / defense"},
            {"id": 7, "value": "Manifesto client"},
        ],
        # ⚠️ INFERRED KEY, and it must be known. `action` and
        # `actionOnOpportunity` are attested; this one is not — it is the
        # name the other two's convention suggests. What IS attested is that
        # an action nomenclature on candidates exists in the instance: the
        # mappings file's `Dashb` sheet counts its volumes over 31 weeks
        # (1 006 ITW1, 260 ITW2, 54 ITW3, 248 PREQUAL).
        #
        # It is declared because block ④ makes these six types get emitted:
        # a dictionary silent on what its own dataset produces is the defect
        # this docstring forbids. If the instance names the key differently,
        # that is a rename, not a redo of the reasoning.
        "actionOnCandidate": [
            {"id": 1, "value": "PREQUAL [1ST CONTACT]"},
            {"id": 2, "value": "ITW 1 [TA/BM]"},
            {"id": 3, "value": "ITW 2 [TECH/BUSINESS]"},
            {"id": 4, "value": "REFERENCE CHECK"},
            {"id": 5, "value": "ITW 3 [DIR/PARTNER]"},
            {"id": 6, "value": "PROPOSITION"},
        ],
        "actionOnOpportunity": [
            {"id": 1, "value": "NEED STUDY / QUALIFICATION"},
            {"id": 2, "value": "CLIENT PRESENTATION / DEFENSE"},
            {"id": 3, "value": "CLOSING"},
            {"id": 4, "value": "TODO"},
        ],
        "origin": [
            {"id": 1, "value": "Careers site"},
            {"id": 2, "value": "LinkedIn"},
            {"id": 3, "value": "Referral"},
            {"id": 4, "value": "Headhunting"},
            {"id": 5, "value": "Big Data Paris trade show"},
        ],
    }


def build_realistic_dataset(seed: int = 42) -> dict[str, Any]:
    rng = random.Random(seed)

    agencies = _build_agencies()
    poles = _build_poles()
    roles = _build_roles()
    resources = _build_resources(rng)
    business_units = _business_units(resources)
    contracts = _build_contracts(resources, rng, seed)
    candidates = _build_candidates(rng)
    companies = _build_companies(rng)
    contacts = _build_contacts(companies, rng)
    opportunities = _build_opportunities(companies, contacts, rng)
    projects = _build_projects(opportunities, companies, rng)
    deliveries = _build_deliveries(projects, resources, rng)
    matrix = _worked_days(deliveries, rng)
    orders = _build_orders(projects, deliveries, rng)
    invoices = _build_invoices(orders, deliveries, matrix, rng)
    purchases = _build_purchases(deliveries, resources, rng)
    payments = _build_payments(purchases)
    accounts, connections, transactions = _build_banking(invoices, companies, orders, projects, rng)
    timesreports, timesreport_index = _build_timesreports(resources, rng)
    times = _build_times(deliveries, resources, matrix, timesreport_index, rng)
    absences = _build_absences(resources, agencies, rng)
    expenses = _build_expenses(deliveries, resources, projects, agencies, rng)
    actions = _build_actions(
        candidates,
        contacts,
        opportunities,
        projects,
        resources=resources,
        invoices=invoices,
        rng=rng,
    )

    # Consolidating projects ← deliveries (simulated turnover, margin, profitability).
    for project in projects:
        project_deliveries = [
            m for m in deliveries if m["relationships"]["project"]["data"]["id"] == project["id"]
        ]
        turnover = round(
            sum(m["attributes"]["turnoverSimulatedExcludingTax"] for m in project_deliveries), 2
        )
        costs = round(
            sum(m["attributes"]["costsSimulatedExcludingTax"] for m in project_deliveries), 2
        )
        project["attributes"]["turnoverSimulatedExcludingTax"] = turnover
        project["attributes"]["marginSimulatedExcludingTax"] = round(turnover - costs, 2)
        project["attributes"]["profitabilitySimulated"] = (
            round((turnover - costs) / turnover * 100, 2) if turnover else 0.0
        )

    # Resources' summary resume points at real references from the technical file.
    technical_data = _build_technical_data(resources, projects, companies, rng)
    for res in resources:
        res["attributes"]["references"] = [
            {"id": ref["id"], "title": ref["title"], "description": ref["description"]}
            for ref in technical_data[res["id"]]["attributes"]["references"]
        ]
        del res["attributes"]["_bu"]  # key internal to the generator

    return {
        "absences": absences,
        "actions": actions,
        # The PAID advantages: variable pay, bonuses, benefits in kind
        # actually paid. Indexed by RESOURCE, like the route.
        "advantages": _paid_advantages(resources, contracts, seed),
        "agencies": agencies,
        "banking_accounts": accounts,
        "banking_connections": connections,
        "banking_transactions": transactions,
        "business_units": business_units,
        "candidates": candidates,
        "companies": companies,
        # Subsidiary → parent, by id. A DICT, not a list: it enters neither
        # the entity index nor the collection counters.
        "company_parents": {str(f): str(m) for f, m in _COMPANY_PARENTS.items()},
        "contacts": contacts,
        "contracts": contracts,
        "deliveries": deliveries,
        "expenses": expenses,
        "invoices": invoices,
        "opportunities": opportunities,
        "orders": orders,
        "payments": payments,
        "poles": poles,
        "projects": projects,
        "purchases": purchases,
        "resources": resources,
        "roles": roles,
        "times": times,
        "times_reports": timesreports,
        "technical_data": technical_data,
        "remuneration": _build_remuneration(resources, contracts, agencies),
        "dictionary": _build_dictionary(),
    }
