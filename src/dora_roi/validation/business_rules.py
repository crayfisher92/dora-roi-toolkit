"""Business and conditional-requirement rules (BUS-*)."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

from dora_roi.model import (
    ContractType,
    Criticality,
    HierarchyInGroup,
    IctThirdPartyProvider,
    RoIRecord,
)
from dora_roi.model.types import INDEFINITE_END_DATE
from dora_roi.validation.context import ValidationContext
from dora_roi.validation.findings import Category, Finding, Severity, rule

ANNEX = ("ITS Annex II",)


def _missing(record: RoIRecord, attr: str) -> bool:
    """True if the attribute is empty and was not already reported as invalid."""
    return getattr(record, attr) is None and attr not in record.invalid_fields


# ------------------------------------------------------------------------- contracts


@rule("BUS-001", "End date before start date", severity=Severity.ERROR,
      category=Category.BUSINESS, templates=("B_02.02",), references=ANNEX,
      description="The end date of a contractual arrangement cannot precede its start date.")
def check_contract_dates(ctx: ValidationContext) -> Iterator[Finding]:
    for s in ctx.register.b_02_02:
        if s.start_date and s.end_date and s.end_date < s.start_date:
            yield ctx.finding("BUS-001", f"End date {s.end_date} is before start date "
                              f"{s.start_date}", s, "end_date", value=s.end_date)


@rule("BUS-002", "Termination reason missing for an ended arrangement", severity=Severity.ERROR,
      category=Category.BUSINESS, templates=("B_02.02",),
      references=(*ANNEX, "DORA Art. 28(7)"),
      description="When the arrangement ended on or before the reference date, the reason of "
      "termination or ending (c0090) must be reported.")
def check_termination_reason(ctx: ValidationContext) -> Iterator[Finding]:
    for s in ctx.register.b_02_02:
        if s.end_date and s.end_date <= ctx.reference_date and _missing(s, "termination_reason"):
            yield ctx.finding("BUS-002", f"Arrangement ended on {s.end_date} but no termination "
                              "reason is reported", s, "termination_reason")


@rule("BUS-003", "Termination reason reported for an active arrangement",
      severity=Severity.WARNING, category=Category.BUSINESS, templates=("B_02.02",),
      references=ANNEX,
      description="A termination reason only applies to arrangements that have ended.")
def check_termination_active(ctx: ValidationContext) -> Iterator[Finding]:
    for s in ctx.register.b_02_02:
        if s.termination_reason and s.end_date and s.end_date > ctx.reference_date:
            yield ctx.finding("BUS-003", f"Termination reason given but end date {s.end_date} is "
                              "after the reference date", s, "termination_reason")


@rule("BUS-004", "Data storage location missing", severity=Severity.ERROR,
      category=Category.BUSINESS, templates=("B_02.02",),
      references=(*ANNEX, "DORA Art. 30(2)"),
      description="When the ICT service includes storage of data (c0140 = true), the country of "
      "the data at rest (c0150) must be reported.")
def check_storage_location(ctx: ValidationContext) -> Iterator[Finding]:
    for s in ctx.register.b_02_02:
        if s.data_storage and _missing(s, "data_location_storage"):
            yield ctx.finding("BUS-004", "Data is stored but the location of data at rest is "
                              "not reported", s, "data_location_storage")


@rule("BUS-005", "Data sensitivity missing", severity=Severity.ERROR,
      category=Category.BUSINESS, templates=("B_02.02",), references=ANNEX,
      description="When the ICT service includes storage of data, the sensitiveness of the data "
      "(c0170) must be reported.")
def check_sensitivity(ctx: ValidationContext) -> Iterator[Finding]:
    for s in ctx.register.b_02_02:
        if s.data_storage and _missing(s, "data_sensitivity"):
            yield ctx.finding("BUS-005", "Data is stored but its sensitiveness is not reported",
                              s, "data_sensitivity")


@rule("BUS-006", "Data processing location missing", severity=Severity.WARNING,
      category=Category.BUSINESS, templates=("B_02.02",),
      references=(*ANNEX, "DORA Art. 30(2)"),
      description="Where data is stored by the provider it is normally also processed; the "
      "location of management of the data (c0160) is expected.")
def check_processing_location(ctx: ValidationContext) -> Iterator[Finding]:
    for s in ctx.register.b_02_02:
        if s.data_storage and _missing(s, "data_location_processing"):
            yield ctx.finding("BUS-006", "Location of data processing is not reported", s,
                              "data_location_processing")


@rule("BUS-007", "Arrangement type inconsistent with overarching reference",
      severity=Severity.ERROR, category=Category.BUSINESS, templates=("B_02.01",),
      references=ANNEX,
      description="A subsequent/associated arrangement must reference its overarching "
      "arrangement (c0030); standalone and overarching arrangements must not.")
def check_contract_type(ctx: ValidationContext) -> Iterator[Finding]:
    for c in ctx.register.b_02_01:
        if c.contract_type is ContractType.SUBSEQUENT and _missing(c, "overarching_ref"):
            yield ctx.finding("BUS-007", "Subsequent arrangement without overarching "
                              "arrangement reference", c, "overarching_ref")
        elif c.contract_type in (ContractType.STANDALONE, ContractType.OVERARCHING) and \
                c.overarching_ref:
            yield ctx.finding("BUS-007", f"{c.contract_type.label} must not reference an "
                              "overarching arrangement", c, "overarching_ref",
                              value=c.overarching_ref)


@rule("BUS-008", "Currency differs from the reporting currency", severity=Severity.WARNING,
      category=Category.BUSINESS, templates=("B_02.01", "B_05.01"), references=ANNEX,
      description="Amounts are expected in the reporting currency of the entity maintaining "
      "the register so that they can be aggregated.")
def check_currency(ctx: ValidationContext) -> Iterator[Finding]:
    reporting = ctx.register.reporting_currency
    if reporting is None:
        return
    records: list[RoIRecord] = [*ctx.register.b_02_01, *ctx.register.b_05_01]
    for r in records:
        cur = getattr(r, "currency", None)
        if cur and cur != reporting:
            yield ctx.finding("BUS-008", f"Amount reported in {cur}, reporting currency is "
                              f"{reporting}", r, "currency", value=cur)


@rule("BUS-009", "Provider total cost lower than sum of its arrangements",
      severity=Severity.WARNING, category=Category.BUSINESS, templates=("B_05.01", "B_02.01"),
      references=ANNEX,
      description="The total annual expense of a provider (B_05.01 c0100) should be at least "
      "the sum of the annual cost of its arrangements (B_02.01 c0050), in the same currency.")
def check_provider_totals(ctx: ValidationContext) -> Iterator[Finding]:
    contracts = ctx.register.contracts_by_ref()
    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for ref, providers in ctx.providers_by_contract.items():
        contract = contracts.get(ref)
        if contract is None or contract.annual_cost is None or contract.currency is None:
            continue
        if len(providers) != 1:
            continue  # cost cannot be attributed unambiguously
        (code,) = providers
        totals[(code, contract.currency)] += contract.annual_cost
    for p in ctx.register.b_05_01:
        if not (p.provider_code and p.currency and p.total_annual_cost is not None):
            continue
        summed = totals.get((p.provider_code, p.currency))
        if summed is not None and p.total_annual_cost < summed:
            yield ctx.finding("BUS-009", f"Total annual cost {p.total_annual_cost} {p.currency} "
                              f"is lower than the sum of its arrangements ({summed})", p,
                              "total_annual_cost", value=p.total_annual_cost)


# ------------------------------------------------------------------------- entities


@rule("BUS-010", "Group hierarchy inconsistent with parent LEI", severity=Severity.ERROR,
      category=Category.BUSINESS, templates=("B_01.02",), references=ANNEX,
      description="Subsidiaries and intermediate parents must report the LEI of their direct "
      "parent (c0060); an ultimate parent or stand-alone entity must not.")
def check_hierarchy(ctx: ValidationContext) -> Iterator[Finding]:
    needs_parent = (HierarchyInGroup.SUBSIDIARY, HierarchyInGroup.PARENT)
    no_parent = (HierarchyInGroup.ULTIMATE_PARENT, HierarchyInGroup.NOT_IN_GROUP)
    for e in ctx.register.b_01_02:
        if e.hierarchy in needs_parent and _missing(e, "parent_lei"):
            yield ctx.finding("BUS-010", f"{e.hierarchy.label} without direct parent LEI", e,
                              "parent_lei")
        elif e.hierarchy in no_parent and e.parent_lei:
            yield ctx.finding("BUS-010", f"{e.hierarchy.label} should not report a parent LEI",
                              e, "parent_lei", value=e.parent_lei)
        if e.parent_lei and e.parent_lei == e.lei:
            yield ctx.finding("BUS-010", "Entity reports itself as its own parent", e,
                              "parent_lei", value=e.parent_lei)


@rule("BUS-011", "Deletion date before integration date", severity=Severity.ERROR,
      category=Category.BUSINESS, templates=("B_01.02",), references=ANNEX,
      description="An entity cannot leave the register before it was integrated.")
def check_entity_dates(ctx: ValidationContext) -> Iterator[Finding]:
    for e in ctx.register.b_01_02:
        if e.deletion_date and e.integration_date and e.deletion_date < e.integration_date:
            yield ctx.finding("BUS-011", f"Deletion date {e.deletion_date} precedes integration "
                              f"date {e.integration_date}", e, "deletion_date")


@rule("BUS-012", "Date after the reference date", severity=Severity.WARNING,
      category=Category.BUSINESS, templates=("B_01.02", "B_06.01", "B_07.01"), references=ANNEX,
      description="Last update, integration, assessment and audit dates are historical and "
      "should not lie after the reporting reference date.")
def check_future_dates(ctx: ValidationContext) -> Iterator[Finding]:
    checks: list[tuple[RoIRecord, str]] = []
    for e in ctx.register.b_01_02:
        checks += [(e, "last_update"), (e, "integration_date")]
    checks += [(f, "last_assessment_date") for f in ctx.register.b_06_01]
    checks += [(a, "last_audit_date") for a in ctx.register.b_07_01]
    for record, attr in checks:
        value: date | None = getattr(record, attr)
        if value and value > ctx.reference_date:
            yield ctx.finding("BUS-012", f"{type(record).column(attr).label} {value} is after the "
                              f"reference date {ctx.reference_date}", record, attr, value=value)


@rule("BUS-013", "Branch code missing for a branch", severity=Severity.ERROR,
      category=Category.BUSINESS, templates=("B_04.01",), references=ANNEX,
      description="When the entity making use of the services is a branch (c0030 = true), its "
      "identification code (c0040) is required.")
def check_branch_code(ctx: ValidationContext) -> Iterator[Finding]:
    for r in ctx.register.b_04_01:
        if r.is_branch and _missing(r, "branch_code"):
            yield ctx.finding("BUS-013", "Service user is a branch but no branch code is given",
                              r, "branch_code")
        elif r.is_branch is False and r.branch_code:
            yield ctx.finding("BUS-013", "Branch code given but c0030 says the user is not a "
                              "branch", r, "branch_code", value=r.branch_code)


@rule("BUS-014", "Additional identification code without type", severity=Severity.ERROR,
      category=Category.BUSINESS, templates=("B_05.01",), references=ANNEX,
      description="An additional provider code (c0030) requires its type (c0040) and vice versa.")
def check_additional_code(ctx: ValidationContext) -> Iterator[Finding]:
    for p in ctx.register.b_05_01:
        if p.additional_code and _missing(p, "additional_code_type"):
            yield ctx.finding("BUS-014", "Additional code given without its type", p,
                              "additional_code_type")
        elif p.additional_code_type and _missing(p, "additional_code"):
            yield ctx.finding("BUS-014", "Type of additional code given without the code", p,
                              "additional_code")


# ------------------------------------------------------------------------- functions


@rule("BUS-015", "Critical function lacks justification or recovery objectives",
      severity=Severity.ERROR, category=Category.BUSINESS, templates=("B_06.01",),
      references=(*ANNEX, "DORA Art. 3(22)", "DORA Art. 28(4)"),
      description="For critical or important functions the reasons for criticality (c0060), RTO "
      "(c0080) and RPO (c0090) must be reported.")
def check_critical_function_details(ctx: ValidationContext) -> Iterator[Finding]:
    for f in ctx.register.b_06_01:
        if not f.is_critical:
            continue
        for attr in ("criticality_reasons", "rto_hours", "rpo_hours"):
            if _missing(f, attr):
                yield ctx.finding("BUS-015", f"Critical function '{f.function_id}' is missing "
                                  f"{type(f).column(attr).label}", f, attr)


@rule("BUS-016", "Criticality assessment not performed", severity=Severity.WARNING,
      category=Category.BUSINESS, templates=("B_06.01",),
      references=("DORA Art. 28(4)", "DORA Art. 3(22)"),
      description="Every function supported by ICT third-party services should be assessed for "
      "criticality or importance.")
def check_not_assessed(ctx: ValidationContext) -> Iterator[Finding]:
    for f in ctx.register.b_06_01:
        if f.criticality is Criticality.NOT_ASSESSED:
            yield ctx.finding("BUS-016", f"Function '{f.function_id}' has not been assessed",
                              f, "criticality")


@rule("BUS-017", "Criticality assessment out of date", severity=Severity.WARNING,
      category=Category.BUSINESS, templates=("B_06.01",), references=("DORA Art. 28(4)",),
      description="The last criticality assessment is older than the configured maximum age "
      "(default 12 months) at the reference date.")
def check_assessment_age(ctx: ValidationContext) -> Iterator[Finding]:
    limit = ctx.config.max_assessment_age_days
    for f in ctx.register.b_06_01:
        if f.last_assessment_date and (ctx.reference_date - f.last_assessment_date).days > limit:
            yield ctx.finding("BUS-017", f"Last assessment {f.last_assessment_date} is more "
                              f"than {limit} days before the reference date", f,
                              "last_assessment_date", value=f.last_assessment_date)


# ------------------------------------------------------------------------- assessments / exit


@rule("BUS-018", "ICT service supporting a critical function not assessed in B_07.01",
      severity=Severity.ERROR, category=Category.BUSINESS, templates=("B_07.01", "B_02.02"),
      references=("DORA Art. 28(3)", "DORA Art. 29", "ITS Annex I"),
      description="Each ICT service supporting a critical or important function must have an "
      "assessment (substitutability, exit plan, reintegration) in B_07.01.")
def check_critical_assessed(ctx: ValidationContext) -> Iterator[Finding]:
    assessed = set(ctx.register.assessments_by_key())
    seen: set[tuple[object, ...]] = set()
    for s in ctx.critical_services:
        key = (s.contract_ref, s.provider_code, s.service_type)
        if key in assessed or key in seen:
            continue
        seen.add(key)
        yield ctx.finding("BUS-018", f"'{s.contract_ref}' supports critical function "
                          f"'{s.function_id}' but has no assessment in B_07.01", s,
                          "contract_ref")


@rule("BUS-019", "No exit plan for an ICT service supporting a critical function",
      severity=Severity.ERROR, category=Category.BUSINESS, templates=("B_07.01", "B_06.01"),
      references=("DORA Art. 28(8)", "DORA Art. 30(3)"),
      description="Financial entities must have exit strategies for ICT services supporting "
      "critical or important functions; B_07.01 c0080 must be true.")
def check_exit_plan(ctx: ValidationContext) -> Iterator[Finding]:
    assessments = ctx.register.assessments_by_key()
    seen: set[tuple[object, ...]] = set()
    for s in ctx.critical_services:
        key = (s.contract_ref, s.provider_code, s.service_type)
        a = assessments.get(key)
        if a is None or key in seen:
            continue
        seen.add(key)
        if a.exit_plan is False:
            yield ctx.finding("BUS-019", f"'{s.contract_ref}' supports critical function "
                              f"'{s.function_id}' but has no exit plan", a, "exit_plan",
                              value=a.exit_plan)


@rule("BUS-020", "Reason for non-substitutability missing", severity=Severity.ERROR,
      category=Category.BUSINESS, templates=("B_07.01",),
      references=(*ANNEX, "DORA Art. 29"),
      description="When the provider is not substitutable or highly complex to substitute, the "
      "reason (c0060) must be given.")
def check_substitutability_reason(ctx: ValidationContext) -> Iterator[Finding]:
    for a in ctx.register.b_07_01:
        if a.substitutability and a.substitutability.is_hard and \
                _missing(a, "non_substitutability_reason"):
            yield ctx.finding("BUS-020", f"Substitutability is '{a.substitutability.label}' but "
                              "no reason is given", a, "non_substitutability_reason")


@rule("BUS-021", "Alternative providers not identified", severity=Severity.ERROR,
      category=Category.BUSINESS, templates=("B_07.01",), references=(*ANNEX, "DORA Art. 28(8)"),
      description="When alternative providers are said to be identified (c0110 = true), they "
      "must be named (c0120).")
def check_alternatives(ctx: ValidationContext) -> Iterator[Finding]:
    for a in ctx.register.b_07_01:
        if a.alternatives_identified and _missing(a, "alternative_providers"):
            yield ctx.finding("BUS-021", "Alternatives identified but not named", a,
                              "alternative_providers")


@rule("BUS-022", "Provider supporting a critical function not audited recently",
      severity=Severity.WARNING, category=Category.BUSINESS, templates=("B_07.01",),
      references=("DORA Art. 28(6)",),
      description="Providers of ICT services supporting critical functions should be audited "
      "with a risk-based frequency; no audit date or an audit older than the configured "
      "threshold (default 3 years) is flagged.")
def check_audit(ctx: ValidationContext) -> Iterator[Finding]:
    assessments = ctx.register.assessments_by_key()
    limit = ctx.config.max_audit_age_days
    seen: set[tuple[object, ...]] = set()
    for s in ctx.critical_services:
        key = (s.contract_ref, s.provider_code, s.service_type)
        a = assessments.get(key)
        if a is None or key in seen or "last_audit_date" in a.invalid_fields:
            continue
        seen.add(key)
        if a.last_audit_date is None:
            yield ctx.finding("BUS-022", f"Provider '{a.provider_code}' supports a critical "
                              "function and has never been audited", a, "last_audit_date")
        elif (ctx.reference_date - a.last_audit_date).days > limit:
            yield ctx.finding("BUS-022", f"Last audit of '{a.provider_code}' on "
                              f"{a.last_audit_date} is older than {limit} days", a,
                              "last_audit_date", value=a.last_audit_date)


@rule("BUS-023", "Intra-group provider without B_03.03 entry", severity=Severity.WARNING,
      category=Category.BUSINESS, templates=("B_03.03", "B_02.02"), references=ANNEX,
      description="When the provider of an arrangement is itself an entity of the group "
      "(its LEI is in B_01.02), the providing entity is expected in B_03.03.")
def check_intragroup(ctx: ValidationContext) -> Iterator[Finding]:
    providing = {(r.contract_ref, r.entity_lei) for r in ctx.register.b_03_03}
    seen: set[tuple[str, str]] = set()
    for s in ctx.register.b_02_02:
        if not (s.contract_ref and s.provider_code) or s.provider_code not in ctx.entity_leis:
            continue
        key = (s.contract_ref, s.provider_code)
        if key not in providing and key not in seen:
            seen.add(key)
            yield ctx.finding("BUS-023", f"Provider '{s.provider_code}' is a group entity but "
                              f"'{s.contract_ref}' is not listed in B_03.03", s, "provider_code")


@rule("BUS-024", "Indefinite arrangement reported with an unusual end date",
      severity=Severity.INFO, category=Category.BUSINESS, templates=("B_02.02",),
      references=ANNEX,
      description="Arrangements without an end date are reported as 9999-12-31; end dates "
      "more than 30 years ahead are usually a placeholder that should be normalised.")
def check_placeholder_end_date(ctx: ValidationContext) -> Iterator[Finding]:
    ref = ctx.reference_date
    horizon = date(ref.year + 30, ref.month, 1)
    for s in ctx.register.b_02_02:
        if s.end_date and s.end_date != INDEFINITE_END_DATE and s.end_date > horizon:
            yield ctx.finding("BUS-024", f"End date {s.end_date} looks like a placeholder; use "
                              "9999-12-31 for indefinite arrangements", s, "end_date",
                              value=s.end_date)


_LEGAL_FORM_WORDS = sorted(
    ("ag", "gmbh", "se", "sa", "s a", "sas", "sarl", "s a r l", "spa", "s p a", "srl", "bv",
     "b v", "nv", "n v", "plc", "ltd", "limited", "inc", "llc", "corp", "corporation", "co",
     "kft", "sp z o o", "ab", "as", "oy", "kg", "ohg", "mbh", "holding"),
    key=len, reverse=True)  # longest first, so "s a r l" wins over "s a"
_LEGAL_FORMS = re.compile(r"\b(" + "|".join(re.escape(w) for w in _LEGAL_FORM_WORDS) + r")\b")


def _provider_name_key(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", _LEGAL_FORMS.sub(" ", text)).strip()


@rule("BUS-025", "Possible duplicate provider", severity=Severity.WARNING,
      category=Category.BUSINESS, templates=("B_05.01",),
      references=("DORA Art. 28(3)", "DORA Art. 29", "ITS Annex II"),
      description="Two providers with the same name (ignoring case, accents and legal form) "
      "but different identification codes are probably the same provider reported twice, "
      "which splits its concentration figures.")
def check_duplicate_providers(ctx: ValidationContext) -> Iterator[Finding]:
    seen: dict[str, IctThirdPartyProvider] = {}
    for p in ctx.register.b_05_01:
        if not (p.legal_name and p.provider_code):
            continue
        key = _provider_name_key(p.legal_name)
        if not key:
            continue
        first = seen.get(key)
        if first is None:
            seen[key] = p
        elif first.provider_code != p.provider_code:
            yield ctx.finding("BUS-025", f"'{p.legal_name}' ({p.provider_code}) looks like the "
                              f"same provider as '{first.legal_name}' ({first.provider_code})",
                              p, "legal_name", value=p.legal_name)
