"""Cross-template referential integrity rules (XRF-*)."""

from __future__ import annotations

from collections.abc import Iterator

from dora_roi.model import ContractType, RoIRecord
from dora_roi.validation.context import ValidationContext
from dora_roi.validation.findings import Category, Finding, Severity, rule

CONSISTENCY = ("ITS Art. – consistency", "ITS Annex II", "DORA Art. 28(3)")

#: (template attribute, field) pairs that reference a contract in B_02.01.
CONTRACT_REFS: tuple[tuple[str, str], ...] = (
    ("b_02_02", "contract_ref"),
    ("b_02_03", "contract_ref"),
    ("b_02_03", "linked_contract_ref"),
    ("b_03_01", "contract_ref"),
    ("b_03_02", "contract_ref"),
    ("b_03_03", "contract_ref"),
    ("b_04_01", "contract_ref"),
    ("b_05_02", "contract_ref"),
    ("b_07_01", "contract_ref"),
)

#: Fields that reference an entity in B_01.02.
ENTITY_REFS: tuple[tuple[str, str], ...] = (
    ("b_01_01", "lei"),
    ("b_01_03", "head_office_lei"),
    ("b_02_02", "entity_lei"),
    ("b_03_01", "entity_lei"),
    ("b_03_03", "entity_lei"),
    ("b_04_01", "entity_lei"),
    ("b_06_01", "entity_lei"),
)

#: Fields that reference a provider in B_05.01.
PROVIDER_REFS: tuple[tuple[str, str], ...] = (
    ("b_02_02", "provider_code"),
    ("b_03_02", "provider_code"),
    ("b_05_02", "provider_code"),
    ("b_05_02", "recipient_code"),
    ("b_07_01", "provider_code"),
)


def _refs(ctx: ValidationContext, refs: tuple[tuple[str, str], ...]
          ) -> Iterator[tuple[RoIRecord, str, str]]:
    for attr_name, field_name in refs:
        records: list[RoIRecord] = getattr(ctx.register, attr_name)
        for record in records:
            value = getattr(record, field_name)
            if value is not None:
                yield record, field_name, value


@rule("XRF-001", "Contractual arrangement not defined in B_02.01", severity=Severity.ERROR,
      category=Category.REFERENTIAL,
      templates=("B_02.02", "B_02.03", "B_03.01", "B_03.02", "B_03.03", "B_04.01", "B_05.02",
                 "B_07.01"),
      references=CONSISTENCY,
      description="Every contractual arrangement reference number used in another template "
      "must be reported in B_02.01.")
def check_contract_refs(ctx: ValidationContext) -> Iterator[Finding]:
    for record, attr, value in _refs(ctx, CONTRACT_REFS):
        if value not in ctx.contract_refs:
            yield ctx.finding("XRF-001", f"Contractual arrangement '{value}' is not reported "
                              "in B_02.01", record, attr, value=value)


@rule("XRF-002", "Entity not listed in B_01.02", severity=Severity.ERROR,
      category=Category.REFERENTIAL,
      templates=("B_01.01", "B_01.03", "B_02.02", "B_03.01", "B_03.03", "B_04.01", "B_06.01"),
      references=(*CONSISTENCY, "ITS Art. – identification"),
      description="Every entity LEI used in the register (maintainer, branch head office, "
      "service user, signatory, function owner) must be listed in B_01.02.")
def check_entity_refs(ctx: ValidationContext) -> Iterator[Finding]:
    for record, attr, value in _refs(ctx, ENTITY_REFS):
        if value not in ctx.entity_leis:
            yield ctx.finding("XRF-002", f"Entity LEI '{value}' is not listed in B_01.02",
                              record, attr, value=value)


@rule("XRF-003", "ICT third-party service provider not listed in B_05.01",
      severity=Severity.ERROR, category=Category.REFERENTIAL,
      templates=("B_02.02", "B_03.02", "B_05.02", "B_07.01"),
      references=(*CONSISTENCY, "DORA Art. 28(3)"),
      description="Every provider (direct provider, signatory, subcontractor or recipient of "
      "subcontracted services) must be described in B_05.01.")
def check_provider_refs(ctx: ValidationContext) -> Iterator[Finding]:
    for record, attr, value in _refs(ctx, PROVIDER_REFS):
        if value not in ctx.provider_codes:
            yield ctx.finding("XRF-003", f"Provider '{value}' is not listed in B_05.01",
                              record, attr, value=value)


@rule("XRF-004", "Function not identified in B_06.01", severity=Severity.ERROR,
      category=Category.REFERENTIAL, templates=("B_02.02", "B_06.01"),
      references=(*CONSISTENCY, "DORA Art. 28(3)", "DORA Art. 3(22)"),
      description="Each function supported by an ICT service in B_02.02 must be identified and "
      "assessed for criticality in B_06.01.")
def check_function_refs(ctx: ValidationContext) -> Iterator[Finding]:
    for svc in ctx.register.b_02_02:
        if svc.function_id is not None and svc.function_id not in ctx.function_ids:
            yield ctx.finding("XRF-004", f"Function '{svc.function_id}' is not identified in "
                              "B_06.01", svc, "function_id", value=svc.function_id)


@rule("XRF-005", "Function identified for a different entity", severity=Severity.WARNING,
      category=Category.REFERENTIAL, templates=("B_02.02", "B_06.01"),
      references=CONSISTENCY,
      description="The function exists in B_06.01 but not for the entity making use of the "
      "ICT service; check that the right function identifier/LEI pair is reported.")
def check_function_entity(ctx: ValidationContext) -> Iterator[Finding]:
    for svc in ctx.register.b_02_02:
        if (svc.function_id in ctx.function_ids and svc.entity_lei
                and (svc.function_id, svc.entity_lei) not in ctx.function_lookup):
            yield ctx.finding("XRF-005", f"Function '{svc.function_id}' is not identified for "
                              f"entity {svc.entity_lei} in B_06.01", svc, "function_id",
                              value=svc.function_id)


@rule("XRF-006", "Contractual arrangement without specific information",
      severity=Severity.ERROR, category=Category.REFERENTIAL, templates=("B_02.01", "B_02.02"),
      references=CONSISTENCY,
      description="Every arrangement in B_02.01 must be described by at least one row in B_02.02 "
      "(entity, provider, function and service type).")
def check_contract_has_services(ctx: ValidationContext) -> Iterator[Finding]:
    for contract in ctx.register.b_02_01:
        if contract.contract_ref and contract.contract_ref not in ctx.services_by_contract:
            yield ctx.finding("XRF-006", f"Contractual arrangement '{contract.contract_ref}' "
                              "has no row in B_02.02", contract, "contract_ref")


@rule("XRF-007", "Contractual arrangement without signing entity", severity=Severity.ERROR,
      category=Category.REFERENTIAL, templates=("B_02.01", "B_03.01", "B_03.03"),
      references=CONSISTENCY,
      description="Each arrangement must identify the entity (or entities) of the group that "
      "signed it, in B_03.01 (or B_03.03 for intra-group provision).")
def check_contract_signatory(ctx: ValidationContext) -> Iterator[Finding]:
    signed = {r.contract_ref for r in ctx.register.b_03_01} | {
        r.contract_ref for r in ctx.register.b_03_03
    }
    for contract in ctx.register.b_02_01:
        if contract.contract_ref and contract.contract_ref not in signed:
            yield ctx.finding("XRF-007", f"No signing entity reported in B_03.01 for "
                              f"'{contract.contract_ref}'", contract, "contract_ref")


@rule("XRF-008", "Provider in B_02.02 not reported as signatory in B_03.02",
      severity=Severity.WARNING, category=Category.REFERENTIAL,
      templates=("B_02.02", "B_03.02"), references=CONSISTENCY,
      description="The ICT third-party service provider of an arrangement is expected to be "
      "reported as signatory of that arrangement in B_03.02.")
def check_provider_signatory(ctx: ValidationContext) -> Iterator[Finding]:
    signed = {(r.contract_ref, r.provider_code) for r in ctx.register.b_03_02}
    reported: set[tuple[str, str]] = set()
    for svc in ctx.register.b_02_02:
        if not (svc.contract_ref and svc.provider_code):
            continue
        key = (svc.contract_ref, svc.provider_code)
        if key not in signed and key not in reported:
            reported.add(key)
            yield ctx.finding("XRF-008", f"Provider '{svc.provider_code}' of "
                              f"'{svc.contract_ref}' is not reported in B_03.02", svc,
                              "provider_code", value=svc.provider_code)


@rule("XRF-009", "Contractual arrangement without service recipient in B_04.01",
      severity=Severity.WARNING, category=Category.REFERENTIAL,
      templates=("B_02.01", "B_04.01"), references=CONSISTENCY,
      description="The entities making use of the ICT services of each arrangement are "
      "expected in B_04.01.")
def check_contract_recipient(ctx: ValidationContext) -> Iterator[Finding]:
    used = {r.contract_ref for r in ctx.register.b_04_01}
    for contract in ctx.register.b_02_01:
        if contract.contract_ref and contract.contract_ref not in used:
            yield ctx.finding("XRF-009", f"No entity making use of '{contract.contract_ref}' "
                              "is reported in B_04.01", contract, "contract_ref")


@rule("XRF-010", "Provider not used by any arrangement", severity=Severity.WARNING,
      category=Category.REFERENTIAL, templates=("B_05.01",), references=CONSISTENCY,
      description="A provider in B_05.01 that is neither a direct provider (B_02.02) nor part of "
      "a supply chain (B_05.02) or ultimate parent is probably stale.")
def check_unused_provider(ctx: ValidationContext) -> Iterator[Finding]:
    used: set[str] = {s.provider_code for s in ctx.register.b_02_02 if s.provider_code}
    for sc in ctx.register.b_05_02:
        used.update(c for c in (sc.provider_code, sc.recipient_code) if c)
    used.update(p.ultimate_parent_code for p in ctx.register.b_05_01
                if p.ultimate_parent_code and p.ultimate_parent_code != p.provider_code)
    for provider in ctx.register.b_05_01:
        if provider.provider_code and provider.provider_code not in used:
            yield ctx.finding("XRF-010", f"Provider '{provider.provider_code}' "
                              f"({provider.legal_name or 'unnamed'}) is not referenced by any "
                              "arrangement or supply chain", provider, "provider_code")


@rule("XRF-011", "Overarching arrangement reference does not resolve", severity=Severity.ERROR,
      category=Category.REFERENTIAL, templates=("B_02.01",), references=CONSISTENCY,
      description="A subsequent/associated arrangement must point to an arrangement reported in "
      "B_02.01 whose type is 'overarching'.")
def check_overarching(ctx: ValidationContext) -> Iterator[Finding]:
    by_ref = ctx.register.contracts_by_ref()
    for contract in ctx.register.b_02_01:
        ref = contract.overarching_ref
        if ref is None:
            continue
        parent = by_ref.get(ref)
        if parent is None:
            yield ctx.finding("XRF-011", f"Overarching arrangement '{ref}' is not reported in "
                              "B_02.01", contract, "overarching_ref", value=ref)
        elif parent.contract_type is not None and parent.contract_type is not \
                ContractType.OVERARCHING:
            yield ctx.finding("XRF-011", f"Arrangement '{ref}' is referenced as overarching but "
                              f"its type is {parent.contract_type.value}", contract,
                              "overarching_ref", value=ref)
        elif ref == contract.contract_ref:
            yield ctx.finding("XRF-011", "Arrangement references itself as overarching",
                              contract, "overarching_ref", value=ref)


@rule("XRF-012", "Branch not listed in B_01.03", severity=Severity.ERROR,
      category=Category.REFERENTIAL, templates=("B_04.01", "B_01.03"), references=CONSISTENCY,
      description="A branch making use of ICT services must be listed in B_01.03 under the same "
      "head office LEI.")
def check_branch_refs(ctx: ValidationContext) -> Iterator[Finding]:
    branches = {(b.branch_code, b.head_office_lei) for b in ctx.register.b_01_03}
    codes = {b.branch_code for b in ctx.register.b_01_03}
    for rec in ctx.register.b_04_01:
        if rec.branch_code is None:
            continue
        if (rec.branch_code, rec.entity_lei) not in branches:
            detail = ("belongs to another head office" if rec.branch_code in codes
                      else "is not listed in B_01.03")
            yield ctx.finding("XRF-012", f"Branch '{rec.branch_code}' {detail}", rec,
                              "branch_code", value=rec.branch_code)


@rule("XRF-013", "Assessment does not match any ICT service in B_02.02",
      severity=Severity.ERROR, category=Category.REFERENTIAL, templates=("B_07.01", "B_02.02"),
      references=CONSISTENCY,
      description="Each B_07.01 row (arrangement, provider, service type) must correspond to an "
      "ICT service reported in B_02.02.")
def check_assessment_matches(ctx: ValidationContext) -> Iterator[Finding]:
    services = {(s.contract_ref, s.provider_code, s.service_type) for s in ctx.register.b_02_02}
    for a in ctx.register.b_07_01:
        if a.contract_ref not in ctx.contract_refs:
            continue  # already reported by XRF-001
        if (a.contract_ref, a.provider_code, a.service_type) not in services:
            yield ctx.finding("XRF-013", f"No B_02.02 row for arrangement '{a.contract_ref}', "
                              f"provider '{a.provider_code}', service "
                              f"{a.service_type.value if a.service_type else '—'}", a,
                              "contract_ref")


@rule("XRF-014", "Parent undertaking outside the register scope", severity=Severity.INFO,
      category=Category.REFERENTIAL, templates=("B_01.02",), references=CONSISTENCY,
      description="The direct parent LEI is not itself listed in B_01.02. This is legitimate when "
      "the parent is outside the scope (e.g. a third-country holding) but should be confirmed.")
def check_parent_scope(ctx: ValidationContext) -> Iterator[Finding]:
    for e in ctx.register.b_01_02:
        if e.parent_lei and e.parent_lei not in ctx.entity_leis:
            yield ctx.finding("XRF-014", f"Parent '{e.parent_lei}' of {e.name or e.lei} is not "
                              "listed in B_01.02", e, "parent_lei", value=e.parent_lei)


@rule("XRF-015", "Entity in scope does not use any ICT service", severity=Severity.INFO,
      category=Category.REFERENTIAL, templates=("B_01.02",), references=("DORA Art. 28(3)",),
      description="An entity listed in B_01.02 is not referenced by any arrangement. Confirm "
      "that its ICT services are captured (possibly via another group entity).")
def check_entity_used(ctx: ValidationContext) -> Iterator[Finding]:
    used = {s.entity_lei for s in ctx.register.b_02_02} | {
        r.entity_lei for r in ctx.register.b_04_01
    }
    for e in ctx.register.b_01_02:
        if e.lei and e.lei not in used and e.deletion_date is None:
            yield ctx.finding("XRF-015", f"Entity {e.name or e.lei} is not referenced by any "
                              "ICT service", e, "lei")
