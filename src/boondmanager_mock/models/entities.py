"""BoondManager entities — aligned with the REAL API.

Dual provenance: the official RAML schemas
(https://doc.boondmanager.com/api-externe/raml-build/, pulled 2026-07-30)
CONFRONTED with the real responses of a tenant on 9.1.78.1 (probes from
2026-07-30/31, with an *owner* user token). When the RAML documents a field
that the real API never returns (`creationSource` on search,
`numberbOfActiveOpportunity`…), the OBSERVED wins — the gap matrix lives in
docs/UNVERIFIED-FIELDS.md.

Searches and profiles are DIFFERENT shapes at the vendor: the `*Attributes`
models describe searches; `ResourceProfile` and `ProjectProfile` describe the
details observed for real.

`extra="allow"` everywhere: these models document what the mock emits, they
forbid nothing — a strict mock would break on every evolution of the dialect.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import DataRef, Permissive, Relation, unverified


class BaseAttributes(Permissive):
    """The only cross-cutting field added by the mock — and it is ABSENT by default.

    ┌─ `isDeleted` IS NOT A VENDOR FIELD, AND NOW THE MOCK SAYS SO ────────────┐
    │ It was emitted on every record, always `False`. A probe of the eighteen  │
    │ production collections on 2026-08-12 found it in NONE of them: the       │
    │ vendor simply does not expose it.                                        │
    │                                                                          │
    │ Emitting it by default was the costliest kind of fiction — the           │
    │ believable kind. insights360 built seventeen staging models on           │
    │ `where not is_deleted`, all green against this mock, all broken on the   │
    │ first production run with « column is_deleted does not exist ».          │
    │                                                                          │
    │ The field keeps its PURPOSE: an incremental pipeline running a `merge`   │
    │ strategy cannot observe a physical deletion, and `/__admin/delete` needs │
    │ a way to express one. So the flag still exists — but only once an        │
    │ operator has DELIBERATELY created that scenario. Absent by default, it   │
    │ now matches the vendor; present after an explicit admin call, it still   │
    │ exercises the consumer's deletion handling.                              │
    │                                                                          │
    │ That distinction is the whole point: the mock may offer affordances the  │
    │ vendor lacks, but it must not put them in the default payload, where     │
    │ they read as vendor behaviour.                                           │
    └──────────────────────────────────────────────────────────────────────────┘
    """

    isDeleted: bool | None = Field(
        default=None,
        json_schema_extra=unverified(
            "LOGICAL deletion — mock affordance, NEVER emitted by the vendor "
            "(probed across all eighteen collections, 2026-08-12). Absent from "
            "every default payload; only /__admin/delete sets it. A consumer "
            "MUST treat its absence as « not deleted » — reading `not "
            "is_deleted` on a NULL column yields NULL, hence an empty result "
            "set with no error at all."
        ),
    )


class RelationList(Permissive):
    """A to-many relationship: `{"data": [{id, type}, …]}`."""

    data: list[DataRef] = Field(default_factory=list)


# ── Shared sub-objects (nested shapes of the dialect) ────────────────────────


class WorkUnit(Permissive):
    """`workUnitType` — the work-unit type of an activity row."""

    reference: int
    activityType: str = Field(
        description="production | absence | internal | exceptionalTime | exceptionalCalendar"
    )
    name: str


class SocialNetwork(Permissive):
    network: str = Field(description="facebook | viadeo | linkedin | x")
    url: str


class RatingTool(Permissive):
    tool: str
    level: int = Field(ge=1, le=5)


class SpokenLanguage(Permissive):
    language: str
    level: str


class SourceOrOrigin(Permissive):
    """`source` (candidates) and `origin` (opportunities): {typeOf, detail}."""

    typeOf: int
    detail: str = ""


class StateReason(Permissive):
    """The opportunities' `stateReason`."""

    typeOf: int
    detail: str = ""


class SummarizedReference(Permissive):
    """A résumé experience, summarized (resources search)."""

    id: str
    title: str
    description: str = ""


class NestedAgency(Permissive):
    id: str
    name: str
    workUnitRate: float | None = None


class NestedResource(Permissive):
    id: str
    lastName: str
    firstName: str
    workUnitRate: float | None = None


class AbsencesReport(Permissive):
    """The absences report EMBEDDED in every /absences row."""

    id: str
    creationDate: str
    state: str = Field(
        description="savedAndNoValidation | waitingForValidation | validated | rejected"
    )
    agency: NestedAgency
    resource: NestedResource


class ExpenseType(Permissive):
    reference: int
    taxRate: float | None = None
    name: str


class MileageRate(Permissive):
    reference: int
    name: str
    amount: float


class ExpensesReport(Permissive):
    """The expenses report EMBEDDED in every /expenses row."""

    id: str
    term: str = Field(description="YYYY-MM")
    state: str
    ratePerKilometerType: MileageRate | None = None
    advance: float = 0.0
    agency: NestedAgency | None = None
    resource: NestedResource | None = None


class NestedDelivery(Permissive):
    id: str
    title: str = ""
    startDate: str = ""
    endDate: str = ""


class NestedProject(Permissive):
    id: str
    reference: str = ""


class ExpenseGuest(Permissive):
    id: str
    lastName: str
    firstName: str
    thumbnail: str = ""


class CandidateResumeReference(Permissive):
    """A candidate's detailed experience — months/years as STRINGS, like the API."""

    id: str
    title: str = ""
    company: str = ""
    location: str = ""
    startMonth: str = ""
    startYear: str = ""
    endMonth: str = ""
    endYear: str = ""
    skills: str = ""
    description: str = ""
    startDate: str = ""
    endDate: str = ""
    row: int = 0


class RatingCriterion(Permissive):
    criteria: int
    evaluation: str


class NestedManager(Permissive):
    id: str
    firstName: str
    lastName: str


class CandidateEvaluation(Permissive):
    id: str
    notations: list[RatingCriterion] = Field(default_factory=list)
    date: str = ""
    comments: str = ""
    manager: NestedManager | None = None


class ContractExpenseDetail(Permissive):
    """⚠️ SERVED, NEVER FILLED — measured 2026-09-10, 0 of 18 contracts.

    The key IS emitted on the contract profile; the array is always empty on
    the tenant probed. The mock filled it on 38 of 38 contracts, which made it
    the most believable kind of fiction: a consumer building on it was green in
    CI and would have found an empty column in production. Same family as
    `isDeleted`. The model stays — the vendor does serve the key — the dataset
    no longer fills it.
    """

    id: str
    expenseType: dict[str, Any] = Field(default_factory=dict)
    periodicity: str = Field(default="monthly", description="daily | monthly")
    netAmount: float = 0.0


class ContractAdvantageType(Permissive):
    """A contractual benefit entitlement — shape OBSERVED 2026-09-10.

    Filled on 16 of 18 probed contracts, 55 lines. The mock used to serve
    `advantageTypes` as an always-empty array, so this shape had never been
    seen: it is NOT the `ContractExpenseDetail` shape it was assumed to share.

    Three traps a consumer must know, all measured:

    * `reference` is NOT a global code. The same `21` is « Health Insurance »
      on one contract and « Variable » on another; `5` is « Life Insurance »
      here and « Lunch allowance » there. It is agency configuration.
    * `category` does NOT say what is vested. « Variable » is `fixedAmount`
      while « Prime de vacances » is `variableSalaryBasis`; it describes how
      the amount is expressed, not whether it is owed.
    * none of the three quotas is « the amount ». Depending on the line only
      the employee one is set, or employee + agency, or participation +
      employee. The amount actually PAID lives on `/resources/{id}/advantages`.
    """

    reference: int | None = None
    name: str | None = None
    frequency: str | None = Field(default=None, description="daily | monthly | semiAnnual | annual")
    category: str | None = Field(
        default=None, description="variableSalaryBasis | package | fixedAmount"
    )
    participationQuota: float | None = None
    employeeQuota: float | None = None
    agencyQuota: float | None = None


# ═════════════════════════════════════════════════════════════════════════════
#  Resource (employee)
# ═════════════════════════════════════════════════════════════════════════════


class ResourceRelations(Permissive):
    mainManager: Relation | None = None
    hrManager: Relation | None = None
    agency: Relation | None = None
    pole: Relation | None = None


class ResourceAttributes(BaseAttributes):
    creationDate: str | None = None
    civility: int | None = None
    thumbnail: str | None = None
    firstName: str
    lastName: str
    reference: str | None = Field(default=None, description="Internal employee reference.")
    typeOf: int | None = Field(
        default=None, description="Instance dictionary (0 = employee, 1 = subcontractor…)."
    )
    state: int | None = Field(default=None, description="Instance dictionary.")
    isVisible: bool | None = None
    skills: str | None = None
    mobilityAreas: list[str] = Field(default_factory=list)
    title: str | None = None
    availability: str | None = Field(default=None, description="YYYY-MM-DD date or `immediate`.")
    forceAvailability: bool | None = None
    realAvailability: str | None = None
    averageDailyPriceExcludingTax: float | None = Field(
        default=None,
        description="Daily SELLING rate. Not a compensation figure.",
    )
    email1: str | None = None
    email2: str | None = None
    email3: str | None = None
    phone1: str | None = None
    phone2: str | None = None
    currency: int | None = None
    exchangeRate: float | None = None
    currencyAgency: int | None = None
    exchangeRateAgency: float | None = None
    numberOfResumes: int | None = None
    numberOfActivePositionings: int | None = None
    updateDate: str | None = None
    tools: list[RatingTool] = Field(default_factory=list)
    expertiseAreas: list[str] = Field(default_factory=list)
    activityAreas: list[str] = Field(default_factory=list)
    diplomas: list[str] = Field(default_factory=list)
    experience: int | None = None
    references: list[SummarizedReference] = Field(default_factory=list)
    languages: list[SpokenLanguage] = Field(default_factory=list)
    canShowTechnicalData: bool | None = None
    canShowActions: bool | None = None
    socialNetworks: list[SocialNetwork] = Field(default_factory=list)


class Resource(Permissive):
    id: str
    type: str = "resource"
    attributes: ResourceAttributes
    relationships: ResourceRelations | None = None


# ═════════════════════════════════════════════════════════════════════════════
#  Candidate
# ═════════════════════════════════════════════════════════════════════════════


class CandidateRelations(Permissive):
    mainManager: Relation | None = None
    agency: Relation | None = None
    pole: Relation | None = None


class CandidateAttributes(BaseAttributes):
    creationDate: str | None = None
    updateDate: str | None = None
    civility: int | None = None
    thumbnail: str | None = None
    firstName: str
    lastName: str
    typeOf: int | None = None
    state: int | None = Field(default=None, description="Instance dictionary.")
    isVisible: bool | None = None
    skills: str | None = None
    mobilityAreas: list[str] = Field(default_factory=list)
    title: str | None = None
    availability: int | None = Field(
        default=None,
        description=(
            "CODE, not a date — unlike a resource's `availability`. Probed on "
            "26 814 production candidates (2026-08-12): integers, `-1` on "
            "24 289 of them. The code→label mapping lives in the instance "
            "dictionary, family `availability`."
        ),
    )
    email1: str | None = None
    email2: str | None = None
    email3: str | None = None
    phone1: str | None = None
    phone2: str | None = None
    town: str | None = None
    country: str | None = None
    source: SourceOrOrigin | None = None
    numberOfResumes: int | None = None
    numberOfActivePositionings: int | None = None
    socialNetworks: list[SocialNetwork] = Field(default_factory=list)
    diplomas: list[str] = Field(default_factory=list)
    activityAreas: list[str] = Field(default_factory=list)
    globalEvaluation: str | None = None
    languages: list[SpokenLanguage] = Field(default_factory=list)
    expertiseAreas: list[str] = Field(default_factory=list)
    experience: int | None = None
    references: list[CandidateResumeReference] = Field(default_factory=list)
    evaluations: list[CandidateEvaluation] = Field(default_factory=list)
    tools: list[RatingTool] = Field(default_factory=list)
    canShowTechnicalData: bool | None = None
    canShowActions: bool | None = None


class Candidate(Permissive):
    id: str
    type: str = "candidate"
    attributes: CandidateAttributes
    relationships: CandidateRelations | None = None


# ═════════════════════════════════════════════════════════════════════════════
#  Agency, business unit, pole, role
# ═════════════════════════════════════════════════════════════════════════════


class AgencyAttributes(BaseAttributes):
    name: str
    calendar: str | None = None
    currency: int | None = None
    numberOfWorkingDays: float | None = None
    chargeFactor: float | None = None
    vatNumber: str | None = None
    registrationNumber: str | None = None
    address: str | None = None
    postcode: str | None = None
    town: str | None = None
    country: str | None = None
    staff: int | None = None
    state: bool | None = None
    workUnitRate: float | None = None
    workUnitRateOnProjectsAndOpportunities: float | None = None
    subDivision: str | None = None


class Agency(Permissive):
    id: str
    type: str = "agency"
    attributes: AgencyAttributes


class BusinessUnitRelations(Permissive):
    includedManagers: RelationList | None = None


class BusinessUnitAttributes(BaseAttributes):
    name: str


class BusinessUnit(Permissive):
    id: str
    type: str = "businessunit"
    attributes: BusinessUnitAttributes
    relationships: BusinessUnitRelations | None = None


class PoleAttributes(BaseAttributes):
    name: str
    state: bool | None = None


class Pole(Permissive):
    id: str
    type: str = "pole"
    attributes: PoleAttributes


class RoleAttributes(BaseAttributes):
    name: str
    numberOfAccounts: float | None = None
    numberOfActiveAccounts: float | None = None
    isSecondaryAgenciesAllowed: bool | None = None
    isSecondaryPolesAllowed: bool | None = None
    typeOf: str | None = Field(default=None, description="manager | intranet")
    isSystem: bool | None = None


class Role(Permissive):
    id: str
    type: str = "role"
    attributes: RoleAttributes


# ═════════════════════════════════════════════════════════════════════════════
#  CRM: company, contact, opportunity, action
# ═════════════════════════════════════════════════════════════════════════════


class CompanyRelations(Permissive):
    mainManager: Relation | None = None
    agency: Relation | None = None
    pole: Relation | None = None


class CompanyAttributes(BaseAttributes):
    name: str
    expertiseArea: str | None = None
    state: int | None = None
    informationComments: str | None = None
    thumbnail: str | None = None
    website: str | None = None
    phone1: str | None = None
    town: str | None = None
    country: str | None = None
    creationDate: str | None = None
    updateDate: str | None = None
    socialNetworks: list[SocialNetwork] = Field(default_factory=list)


class Company(Permissive):
    id: str
    type: str = "company"
    attributes: CompanyAttributes
    relationships: CompanyRelations | None = None


# ── A company's "information" tab — where the group linkage lives ───────────


def _unobserved_type(name: str) -> dict[str, Any]:
    """The NAME is observed in production, the TYPE and value are not."""
    return unverified(
        f"`{name}`: attribute name OBSERVED on /companies/{{id}}/information "
        "(2026-09-13, names only). Type and values NOT observed — the mock's "
        "are plausible, not attested."
    )


class CompanyInformationRelations(Permissive):
    """The EIGHT relationships observed live on 2026-09-13 — no more, no less.

    ┌─ THE GROUP IS ONLY SERVED HERE ────────────────────────────────────────────┐
    │ Read-only probe from 2026-09-13: `GET /companies` (list) and               │
    │ `GET /companies/{id}` (profile) carry ONLY `agency`, `mainManager`,        │
    │ `pole`. The company → group linkage only exists on this tab.               │
    │                                                                            │
    │   parentCompany : `null`, or `{id, type: "company"}` — set on ~6          │
    │                   profiles out of 20 sampled;                              │
    │   subsidiaries  : LIST of `{id, type: "company"}`, empty when none.       │
    │                                                                            │
    │ Both directions are CONSISTENT in reality: one group's profile listed 16   │
    │ subsidiaries, and each pointed back to it via `parentCompany`. The mock    │
    │ DERIVES `subsidiaries` from `parentCompany` to guarantee the same         │
    │ property.                                                                  │
    └────────────────────────────────────────────────────────────────────────────┘
    """

    agency: Relation | None = None
    createdBy: Relation | None = None
    files: RelationList | None = None
    influencers: RelationList | None = None
    mainManager: Relation | None = None
    parentCompany: Relation | None = Field(
        default=None,
        description="The group this company belongs to — `data: null` when none.",
    )
    pole: Relation | None = None
    subsidiaries: RelationList | None = Field(
        default=None,
        description="Companies whose `parentCompany` is this one — empty list when none.",
    )


class CompanyInformationAttributes(Permissive):
    """`GET /companies/{id}/information` — the TWENTY-SEVEN attributes observed
    live on 2026-09-13 (JSON:API type `company`).

    Only the NAMES have been observed. The types of attributes already served
    by search (`CompanyAttributes`) are reused; all others are marked
    `unverified` and registered in docs/UNVERIFIED-FIELDS.md.
    """

    address: str | None = Field(default=None, json_schema_extra=_unobserved_type("address"))
    apeCode: str | None = Field(default=None, json_schema_extra=_unobserved_type("apeCode"))
    billingDetails: list[dict[str, Any]] = Field(
        default_factory=list, json_schema_extra=_unobserved_type("billingDetails")
    )
    country: str | None = None
    creationDate: str | None = None
    creationSource: str | None = Field(
        default=None, json_schema_extra=_unobserved_type("creationSource")
    )
    departments: list[str] = Field(
        default_factory=list, json_schema_extra=_unobserved_type("departments")
    )
    expertiseArea: str | None = None
    fax: str | None = Field(default=None, json_schema_extra=_unobserved_type("fax"))
    informationComments: str | None = None
    legalStatus: str | None = Field(default=None, json_schema_extra=_unobserved_type("legalStatus"))
    name: str
    number: str | None = Field(default=None, json_schema_extra=_unobserved_type("number"))
    origin: SourceOrOrigin | None = Field(
        default=None, json_schema_extra=_unobserved_type("origin")
    )
    phone1: str | None = None
    postcode: str | None = Field(default=None, json_schema_extra=_unobserved_type("postcode"))
    registeredOffice: bool | None = Field(
        default=None, json_schema_extra=_unobserved_type("registeredOffice")
    )
    registrationNumber: str | None = Field(
        default=None, json_schema_extra=_unobserved_type("registrationNumber")
    )
    socialNetworks: list[SocialNetwork] = Field(default_factory=list)
    staff: int | None = Field(default=None, json_schema_extra=_unobserved_type("staff"))
    state: int | None = None
    subDivision: str | None = Field(default=None, json_schema_extra=_unobserved_type("subDivision"))
    thumbnail: str | None = None
    town: str | None = None
    updateDate: str | None = None
    vatNumber: str | None = Field(default=None, json_schema_extra=_unobserved_type("vatNumber"))
    website: str | None = None


class CompanyInformation(Permissive):
    id: str
    type: str = "company"
    attributes: CompanyInformationAttributes
    relationships: CompanyInformationRelations | None = None


class ContactRelations(Permissive):
    mainManager: Relation | None = None
    company: Relation | None = None
    agency: Relation | None = None
    pole: Relation | None = None


class ContactAttributes(BaseAttributes):
    creationDate: str | None = None
    civility: int | None = None
    thumbnail: str | None = None
    firstName: str
    lastName: str
    state: int | None = None
    function: str | None = None
    department: str | None = None
    email1: str | None = None
    email2: str | None = None
    email3: str | None = None
    phone1: str | None = None
    phone2: str | None = None
    town: str | None = None
    country: str | None = None
    canReadContact: bool | None = None
    canWriteContact: bool | None = None
    canShowAction: bool | None = None
    typesOf: list[str] = Field(default_factory=list)
    socialNetworks: list[SocialNetwork] = Field(default_factory=list)
    updateDate: str | None = None


class Contact(Permissive):
    id: str
    type: str = "contact"
    attributes: ContactAttributes
    relationships: ContactRelations | None = None


class OpportunityRelations(Permissive):
    mainManager: Relation | None = None
    agency: Relation | None = None
    pole: Relation | None = None
    contact: Relation | None = None
    company: Relation | None = None
    parsingJob: Relation | None = None


class OpportunityAttributes(BaseAttributes):
    creationDate: str | None = None
    title: str
    reference: str | None = None
    typeOf: int | None = None
    mode: int | None = Field(default=None, description="1 | 2 | 3 | 4 (instance dictionary).")
    state: int | None = None
    place: str | None = None
    isVisible: bool | None = None
    startDate: str | None = Field(
        default=None,
        description=(
            "A DATE **or** the literal string `immediate` — 1 523 of the "
            "1 850 production opportunities (82 %) carry the latter. Casting "
            "this field to a date without guarding the literal fails on « "
            "invalid input syntax for type date ». The dialect reuses the same "
            "literal for a resource's `availability`."
        ),
    )
    endDate: str | None = None
    closingDate: str | None = None
    answerDate: str | None = None
    duration: int | None = None
    currency: int | None = None
    exchangeRate: float | None = None
    currencyAgency: int | None = None
    exchangeRateAgency: float | None = None
    turnoverWeightedExcludingTax: float | None = None
    estimatesExcludingTax: float | None = None
    turnoverEstimatedExcludingTax: float | None = None
    expertiseArea: str | None = None
    activityAreas: list[str] = Field(default_factory=list)
    origin: SourceOrOrigin | None = None
    tools: list[str] = Field(default_factory=list)
    numberOfActivePositionings: int | None = None
    canShowContact: bool | None = None
    canShowCompany: bool | None = None
    stateReason: StateReason | None = None
    updateDate: str | None = None


class Opportunity(Permissive):
    id: str
    type: str = "opportunity"
    attributes: OpportunityAttributes
    relationships: OpportunityRelations | None = None


class ActionRelations(Permissive):
    mainManager: Relation | None = None
    dependsOn: Relation | None = Field(
        default=None,
        description="The carrying entity: candidate, company, contact, opportunity, "
        "project, resource, invoice…",
    )
    company: Relation | None = None
    relatedActions: RelationList | None = None


class ActionAttributes(BaseAttributes):
    startDate: str | None = None
    creationDate: str | None = None
    typeOf: int | None = Field(default=None, description="Per-entity instance dictionary.")
    text: str | None = None
    numberOfFiles: int | None = None
    canReadAction: bool | None = None
    canWriteAction: bool | None = None
    updateDate: str | None = None


class CrmAction(Permissive):
    id: str
    type: str = "action"
    attributes: ActionAttributes
    relationships: ActionRelations | None = None


# ═════════════════════════════════════════════════════════════════════════════
#  Production: project, delivery
# ═════════════════════════════════════════════════════════════════════════════


class ProjectRelations(Permissive):
    mainManager: Relation | None = None
    opportunity: Relation | None = None
    contact: Relation | None = None
    company: Relation | None = None
    agency: Relation | None = None
    pole: Relation | None = None
    intermediaryCompany: Relation | None = None
    intermediaryContact: Relation | None = None


class ProjectAttributes(BaseAttributes):
    startDate: str | None = None
    endDate: str | None = None
    typeOf: int | None = None
    mode: int | None = None
    reference: str | None = None
    currency: int | None = None
    exchangeRate: float | None = None
    currencyAgency: int | None = None
    exchangeRateAgency: float | None = None
    turnoverSimulatedExcludingTax: float | None = None
    marginSimulatedExcludingTax: float | None = None
    profitabilitySimulated: float | None = None
    canReadProject: bool | None = None
    canShowContact: bool | None = None
    canShowCompany: bool | None = None
    canShowIntermediaryContact: bool | None = None
    canShowIntermediaryCompany: bool | None = None
    canShowCurrency: bool | None = None
    canShowCurrencyAgency: bool | None = None
    canShowExchangeRate: bool | None = None
    canShowExchangeRateAgency: bool | None = None
    canShowProfitabilitySimulated: bool | None = None
    canShowTurnoverSimulatedExcludingTax: bool | None = None
    canShowMarginSimulatedExcludingTax: bool | None = None
    creationDate: str | None = None
    updateDate: str | None = None


class Project(Permissive):
    id: str
    type: str = "project"
    attributes: ProjectAttributes
    relationships: ProjectRelations | None = None


class DeliveryRelations(Permissive):
    project: Relation | None = None
    dependsOn: Relation | None = Field(
        default=None, description="The resource (or product) staffed on the delivery."
    )
    purchase: Relation | None = None


class DeliveryAttributes(BaseAttributes):
    """GET /deliveries search does not exist (405 observed): these attributes
    follow the official delivery PROFILE schema, served on /deliveries/{id}."""

    startDate: str | None = None
    endDate: str | None = None
    title: str | None = None
    typeOf: int | None = None
    state: int | None = None
    canShowAverageDailyContractCost: bool | None = None
    averageDailyPriceExcludingTax: float | None = None
    forceAverageDailyPriceExcludingTax: bool | None = None
    subscriptionQuantityCharged: float | None = None
    subscriptionQuantityFree: float | None = None
    subscriptionPriceExcludingTax: float | None = None
    averageDailyCost: float | None = None
    averageDailyContractCost: float | None = None
    numberOfDaysInvoicedOrQuantity: float | None = None
    numberOfDaysFree: float | None = None
    informationComments: str | None = None
    conditions: str | None = None
    turnoverSimulatedExcludingTax: float | None = None
    costsSimulatedExcludingTax: float | None = None
    marginSimulatedExcludingTax: float | None = None
    profitabilitySimulated: float | None = None
    occupationRate: float | None = None
    dailyExpenses: float | None = None
    monthlyExpenses: float | None = None
    numberOfWorkingDays: float | None = None
    weeklyWorkingHours: float | None = None
    averageHourlyPriceExcludingTax: float | None = None
    forceAverageHourlyPriceExcludingTax: bool | None = None
    additionalTurnoverAndCosts: list[dict[str, Any]] = Field(default_factory=list)
    expensesDetails: list[dict[str, Any]] = Field(default_factory=list)
    advantageTypes: list[dict[str, Any]] = Field(default_factory=list)
    exceptionalScales: list[dict[str, Any]] = Field(default_factory=list)
    creationDate: str | None = None
    updateDate: str | None = None
    calendar: str | None = None
    isTurnoverProductionIncluded: bool | None = None


class Delivery(Permissive):
    id: str
    type: str = "delivery"
    attributes: DeliveryAttributes
    relationships: DeliveryRelations | None = None


# ═════════════════════════════════════════════════════════════════════════════
#  Billing: order, invoice, purchase, payment, bank
# ═════════════════════════════════════════════════════════════════════════════


class OrderRelations(Permissive):
    mainManager: Relation | None = None
    project: Relation | None = None


class OrderAttributes(BaseAttributes):
    date: str | None = None
    number: str | None = None
    reference: str | None = None
    customerAgreement: bool | None = None
    turnoverInvoicedExcludingTax: float | None = None
    turnoverOrderedExcludingTax: float | None = None
    deltaInvoicedExcludingTax: float | None = None
    state: int | None = None
    # NEITHER `creationDate` NOR `updateDate`: the vendor renders NEITHER of
    # the two. Probed 2026-08-12 — `/orders` is the only one of the eighteen
    # collections missing `updateDate`, and its dlt landing in production does
    # not carry `creation_date` either.
    #
    # `updateDate` drives the consumer's extraction strategy: serving it here
    # made it declare the collection incremental, and dlt raised
    # `IncrementalCursorPathMissing` on the first real run.
    #
    # `creationDate` was kept in 0.6.0 on the grounds that "it drives no
    # strategy, so serving it costs nothing". That was false: a model that
    # READS a column needs it to EXIST, and `stg_commande` hit
    # "column o.creation_date does not exist" on the next run. The rule
    # therefore admits no "harmless" exception.
    #
    # `date` stays: it is the order date, and it is indeed rendered for real.


class Order(Permissive):
    id: str
    type: str = "order"
    attributes: OrderAttributes
    relationships: OrderRelations | None = None


class InvoiceRelations(Permissive):
    order: Relation | None = None
    schedule: Relation | None = None


class InvoiceAttributes(BaseAttributes):
    date: str | None = None
    expectedPaymentDate: str | None = None
    turnoverInvoicedExcludingTax: float | None = None
    turnoverInvoicedIncludingTax: float | None = None
    isCreditNote: bool | None = None
    reference: str | None = None
    state: int | None = None
    selfBilling: bool | None = None
    sendingState: int | None = None
    refuseReason: str | None = None
    providerId: str | None = None
    providerUrl: str | None = None
    taxReportState: int | None = None
    currency: int | None = None
    exchangeRate: float | None = None
    currencyAgency: int | None = None
    exchangeRateAgency: float | None = None
    paymentMethod: int | None = None
    closed: bool | None = None
    totalPayableIncludingTax: float | None = None
    creationDate: str | None = None
    updateDate: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    performedPaymentDate: str | None = None
    canSendWithPeppol: bool | None = None
    canSendWithDgfip: bool | None = None
    canSendWithPennylane: bool | None = None


class Invoice(Permissive):
    id: str
    type: str = "invoice"
    attributes: InvoiceAttributes
    relationships: InvoiceRelations | None = None


class PurchaseRelations(Permissive):
    mainManager: Relation | None = None
    project: Relation | None = None
    delivery: Relation | None = None
    contact: Relation | None = None
    company: Relation | None = None
    agency: Relation | None = None
    pole: Relation | None = None


class PurchaseAttributes(BaseAttributes):
    date: str | None = None
    title: str | None = None
    subscription: int | None = None
    typeOf: int | None = None
    reference: str | None = None
    state: int | None = None
    taxRate: float | None = None
    currency: int | None = None
    exchangeRate: float | None = None
    currencyAgency: int | None = None
    exchangeRateAgency: float | None = None
    amountExcludingTax: float | None = None
    quantity: float | None = None
    totalAmountExcludingTax: float | None = None
    deltaExcludingTax: float | None = None
    engagedPaymentsAmountExcludingTax: float | None = None
    creationDate: str | None = None
    updateDate: str | None = None


class Purchase(Permissive):
    id: str
    type: str = "purchase"
    attributes: PurchaseAttributes
    relationships: PurchaseRelations | None = None


class PaymentRelations(Permissive):
    purchase: Relation | None = None


class PaymentAttributes(BaseAttributes):
    date: str | None = None
    performedDate: str | None = None
    expectedDate: str | None = None
    state: int | None = None
    number: str | None = None
    amountExcludingTax: float | None = None
    amountIncludingTax: float | None = None
    numberOfFiles: float | None = None
    canWritePayment: bool | None = None
    creationDate: str | None = None
    updateDate: str | None = None


class Payment(Permissive):
    id: str
    type: str = "payment"
    attributes: PaymentAttributes
    relationships: PaymentRelations | None = None


class BankingTransactionRelations(Permissive):
    account: Relation | None = None


class BankingTransactionAttributes(BaseAttributes):
    amount: float | None = None
    currency: int | None = None
    date: str | None = None
    numberOfInvoices: int | None = None
    title: str | None = None
    state: int | None = Field(default=None, description="0 | 1 | 2 | 3 (reconciliation).")
    totalAmountToReconcile: float | None = None
    canReadTransaction: bool | None = None
    canWriteTransaction: bool | None = None
    canReconcile: bool | None = None


class BankingTransaction(Permissive):
    id: str
    type: str = "bankingtransaction"
    attributes: BankingTransactionAttributes
    relationships: BankingTransactionRelations | None = None


# ═════════════════════════════════════════════════════════════════════════════
#  HR: contract
# ═════════════════════════════════════════════════════════════════════════════


class ContractRelations(Permissive):
    dependsOn: Relation | None = Field(
        default=None, description="The resource (or candidate) holding the contract."
    )
    createdBy: Relation | None = None
    agency: Relation | None = None
    parentContract: Relation | None = None
    childContract: Relation | None = None
    files: RelationList | None = None


class ContractAttributes(BaseAttributes):
    """GET /contracts search does not exist (405/WAF observed): these
    attributes follow the contract PROFILE shape as observed on
    /contracts/{id} (30 attributes)."""

    typeOf: int | None = None
    creationDate: str | None = None
    updateDate: str | None = None
    employeeType: int | None = None
    workingTimeType: int | None = None
    numberOfHoursPerWeek: float | None = None
    classification: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    endReason: int | None = None
    probationState: int | None = None
    monthlySalary: float | None = None
    hourlySalary: float | None = None
    forceHourlySalary: bool | None = None
    contractAverageDailyCost: float | None = None
    dailyExpenses: float | None = None
    monthlyExpenses: float | None = None
    numberOfWorkingDays: float | None = None
    chargeFactor: float | None = None
    expensesDetails: list[ContractExpenseDetail] = Field(default_factory=list)
    advantageTypes: list[ContractAdvantageType] = Field(default_factory=list)
    informationComments: str | None = None
    # ── OBSERVED 2026-09-10, and previously listed as "never observed" ───────
    # UNVERIFIED-FIELDS put these three in the "documented in the RAML, never
    # returned" matrix. They ARE returned by the tenant probed: probationEndDate
    # on 12 of 18 contracts, renewalProbationEndDate on the same 12,
    # contractAverageDailyProductionCost on 1. Emission is SPARSE — the key is
    # absent item by item, not null — so the mock omits them the same way.
    probationEndDate: str | None = None
    renewalProbationEndDate: str | None = None
    contractAverageDailyProductionCost: float | None = None
    currency: int | None = None
    currencyAgency: int | None = None
    exchangeRate: float | None = None
    exchangeRateAgency: float | None = None
    calendar: str | None = None
    activityRate: float | None = None
    partialWorkTimes: list[str] = Field(default_factory=list)
    isPartialWorkTimeEvenOdd: bool | None = None


class Contract(Permissive):
    id: str
    type: str = "contract"
    attributes: ContractAttributes
    relationships: ContractRelations | None = None


class AdvantageRelations(Permissive):
    contract: Relation | None = Field(
        default=None, description="The contract the advantage was paid under."
    )
    agency: Relation | None = None


class AdvantageAttributes(Permissive):
    """A benefit actually PAID — shape OBSERVED on `/resources/{id}/advantages`.

    Probed 2026-09-10: 200 OK, `meta.totals.rows` = 54 on one resource, history
    running 2020 → 2026. This is the « Avantages versés » tab, and it is where
    the variable pay lives — « Prime sur lettre d'Objectifs », « Prime
    exceptionnelle », « Prime de vacances ».

    No `updateDate`: there is no cursor, consumers refresh in full. And no bulk
    collection — `/advantages` answers 403, `/resources-advantages` and
    `/contracts-advantages` 404 — so it costs one call per resource.

    SPARSE by nature: six of eight resources probed had none at all.
    """

    date: str | None = None
    quantity: float | None = None
    costPaid: float | None = None
    returnDate: str | None = None
    currency: int | None = None
    currencyAgency: int | None = None
    exchangeRate: float | None = None
    exchangeRateAgency: float | None = None
    canReadAdvantage: bool | None = None
    canWriteAdvantage: bool | None = None
    advantageType: dict[str, Any] = Field(
        default_factory=dict, description="{reference, name} — instance configuration."
    )


class Advantage(Permissive):
    id: str
    type: str = "advantage"
    attributes: AdvantageAttributes
    relationships: AdvantageRelations | None = None


# ═════════════════════════════════════════════════════════════════════════════
#  Activity: absence, time, timesheet, expense
# ═════════════════════════════════════════════════════════════════════════════


class AbsenceAttributes(BaseAttributes):
    """An absence's whole context is EMBEDDED here — no relationships;
    that is the real /absences dialect."""

    startDate: str | None = None
    endDate: str | None = None
    duration: float | None = None
    title: str | None = None
    workUnitType: WorkUnit | None = None
    absencesReport: AbsencesReport | None = None


class Absence(Permissive):
    id: str
    type: str = "absence"
    attributes: AbsenceAttributes


class TimeRelations(Permissive):
    timesReport: Relation | None = None
    delivery: Relation | None = None
    batch: Relation | None = None
    project: Relation | None = None


class TimeAttributes(BaseAttributes):
    category: str | None = Field(default=None, description="regular | exceptional")
    workUnitType: WorkUnit | None = None
    row: int | None = None
    startDate: str | None = None
    duration: float | None = None


class Time(Permissive):
    id: str
    type: str = "time"
    attributes: TimeAttributes
    relationships: TimeRelations | None = None


class TimesReportRelations(Permissive):
    agency: Relation | None = None
    resource: Relation | None = None


class TimesReportAttributes(BaseAttributes):
    term: str | None = Field(default=None, description="YYYY-MM")
    state: str | None = Field(
        default=None,
        description="savedAndNoValidation | waitingForValidation | validated | rejected",
    )
    closed: bool | None = None


class TimesReport(Permissive):
    id: str
    type: str = "timesreport"
    attributes: TimesReportAttributes
    relationships: TimesReportRelations | None = None


class ExpenseAttributes(BaseAttributes):
    """Like /absences: report, delivery and project EMBEDDED in attributes."""

    category: str | None = Field(default=None, description="actual | fixed")
    activityType: str | None = None
    expenseType: ExpenseType | None = None
    row: int | None = None
    startDate: str | None = None
    reinvoiced: bool | None = None
    amountIncludingTax: float | None = None
    tax: float | None = None
    numberOfKilometers: float | None = None
    number: int | None = None
    title: str | None = None
    currency: int | None = None
    exchangeRate: float | None = None
    isKilometricExpense: bool | None = None
    expensesReport: ExpensesReport | None = None
    delivery: NestedDelivery | None = None
    batch: dict[str, Any] | None = None
    project: NestedProject | None = None
    guestResources: list[ExpenseGuest] = Field(default_factory=list)


class Expense(Permissive):
    id: str
    type: str = "expense"
    attributes: ExpenseAttributes


# ═════════════════════════════════════════════════════════════════════════════
#  A resource's administrative tab — where contracts live
# ═════════════════════════════════════════════════════════════════════════════


class ResourceAdministrativeRelations(Permissive):
    agency: Relation | None = None
    candidate: Relation | None = None
    contracts: RelationList | None = Field(
        default=None,
        description="The resource's CONTRACTS — the official path to fetch them.",
    )
    providerContact: Relation | None = None
    providerCompany: Relation | None = Field(
        default=None, description="The supplying company, for a subcontractor."
    )
    files: RelationList | None = None


class ResourceAdministrativeAttributes(Permissive):
    """`GET /resources/{id}/administrative` — official schema
    `resources/administrative.json` (JSON:API type `resource`)."""

    reference: str | None = None
    dateOfBirth: str | None = None
    placeOfBirth: str | None = None
    nationality: str | None = None
    healthCareNumber: str | None = None
    address: str | None = None
    postcode: str | None = None
    town: str | None = None
    country: str | None = None
    subDivision: str | None = None
    situation: int | None = Field(default=None, description="Instance dictionary.")
    administrativeComments: str | None = None
    function: str | None = None
    seniorityDate: str | None = None
    originalSeniorityDate: str | None = None
    forceSeniorityDate: bool | None = None
    validitySeniorityDate: str | None = None


class ResourceAdministrative(Permissive):
    id: str
    type: str = "resource"
    attributes: ResourceAdministrativeAttributes
    relationships: ResourceAdministrativeRelations | None = None


# ═════════════════════════════════════════════════════════════════════════════
#  Affordances kept: technical data, identity
# ═════════════════════════════════════════════════════════════════════════════


class TechnicalDataAttributes(Permissive):
    """`GET /resources/{id}/technical-data` — REAL shape observed: type
    `resource`, fifteen attributes, no relationships nor included."""

    activityAreas: list[str] = Field(default_factory=list)
    description: str | None = None
    diplomas: list[str] = Field(default_factory=list)
    experience: int | None = None
    expertiseAreas: list[str] = Field(default_factory=list)
    languages: list[SpokenLanguage] = Field(default_factory=list)
    references: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The résumé experiences. The only place they live in detail.",
    )
    resourceCanModifyTechnicalData: bool | None = None
    skills: str | None = None
    summary: str | None = None
    tdId: str | None = None
    tdLink: str | None = None
    title: str | None = None
    tools: list[RatingTool] = Field(default_factory=list)
    training: list[dict[str, Any]] = Field(default_factory=list)


class TechnicalData(Permissive):
    id: str
    type: str = "resource"
    attributes: TechnicalDataAttributes


class CurrentUserAttributes(Permissive):
    """`GET /application/current-user` — real type `currentuser` (observed),
    the attribute subset consumers rely on."""

    firstName: str
    lastName: str
    login: str
    email1: str | None = None
    level: str | None = Field(default=None, description="manager | resource | administrator")
    isOwner: bool | None = None
    narrowPerimeter: bool | None = None
    language: str | None = None


class CurrentUserRelations(Permissive):
    agency: Relation | None = None
    role: Relation | None = None


class CurrentUser(Permissive):
    id: str
    type: str = "currentuser"
    attributes: CurrentUserAttributes
    relationships: CurrentUserRelations | None = None


# ═════════════════════════════════════════════════════════════════════════════
#  Profiles — the DETAIL shapes observed for real (≠ searches)
# ═════════════════════════════════════════════════════════════════════════════


class ResourceProfileAttributes(Permissive):
    """Real `GET /resources/{id}`: eighteen attributes, distinct from search."""

    creationDate: str | None = None
    updateDate: str | None = None
    civility: int | None = None
    thumbnail: str | None = None
    firstName: str
    lastName: str
    typeOf: int | None = None
    level: str | None = Field(default=None, description="manager | resource | administrator")
    title: str | None = None
    dateOfBirth: str | None = None
    numberOfResumes: int | None = None
    seniorityDate: str | None = None
    forceSeniorityDate: bool | None = None
    originalSeniorityDate: str | None = None
    validitySeniorityDate: str | None = None
    tdLink: str | None = None
    tdId: str | None = None
    creationSource: str | None = None


class ResourceProfileRelations(Permissive):
    mainManager: Relation | None = None
    hrManager: Relation | None = None
    agency: Relation | None = None
    pole: Relation | None = None
    contracts: RelationList | None = Field(
        default=None,
        description="The resource's CONTRACTS — the official path, validated in prod.",
    )


class ResourceProfile(Permissive):
    id: str
    type: str = "resource"
    attributes: ResourceProfileAttributes
    relationships: ResourceProfileRelations | None = None


class ProjectProfileAttributes(Permissive):
    """Real `GET /projects/{id}`: thirteen attributes — without `endDate`."""

    creationDate: str | None = None
    currency: int | None = None
    currencyAgency: int | None = None
    deliverySuggestFilters: list[dict[str, Any]] = Field(default_factory=list)
    exchangeRate: float | None = None
    exchangeRateAgency: float | None = None
    isProjectManager: bool | None = None
    mode: int | None = None
    reference: str | None = None
    startDate: str | None = None
    typeOf: int | None = None
    updateDate: str | None = None
    workUnitRate: float | None = None


class ProjectProfileRelations(Permissive):
    agency: Relation | None = None
    company: Relation | None = None
    mainManager: Relation | None = None
    opportunity: Relation | None = None
    pole: Relation | None = None


class ProjectProfile(Permissive):
    id: str
    type: str = "project"
    attributes: ProjectProfileAttributes
    relationships: ProjectProfileRelations | None = None
