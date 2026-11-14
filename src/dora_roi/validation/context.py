"""Validation context: the register plus configuration and pre-computed indexes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from typing import Any

from dora_roi.model import ContractSpecific, Function, RegisterOfInformation, RoIRecord
from dora_roi.validation.findings import RULES, Finding, Severity


@dataclass
class ValidationConfig:
    """Tunable parameters of the validation run."""

    #: Rule IDs to skip entirely.
    disabled_rules: frozenset[str] = frozenset()
    #: Per-rule severity overrides (e.g. downgrade a rule to ``warning``).
    severity_overrides: dict[str, Severity] = field(default_factory=dict)
    #: Reference date for date-relative checks; defaults to the B_01.01 reporting date.
    reference_date: date | None = None
    #: Maximum age of a criticality assessment before a warning (DORA expects regular review).
    max_assessment_age_days: int = 365
    #: Maximum age of the last audit of a provider supporting a critical function.
    max_audit_age_days: int = 3 * 365


class ValidationContext:
    """Everything a rule needs, with lazily built look-up indexes."""

    def __init__(self, register: RegisterOfInformation, config: ValidationConfig) -> None:
        self.register = register
        self.config = config

    # ------------------------------------------------------------------ dates

    @cached_property
    def reference_date(self) -> date:
        return self.config.reference_date or self.register.reference_date or date.today()

    # ------------------------------------------------------------------ indexes

    @cached_property
    def entity_leis(self) -> set[str]:
        return self.register.entity_leis()

    @cached_property
    def provider_codes(self) -> set[str]:
        return set(self.register.providers_by_code())

    @cached_property
    def contract_refs(self) -> set[str]:
        return set(self.register.contracts_by_ref())

    @cached_property
    def function_ids(self) -> set[str]:
        return set(self.register.functions_by_id())

    @cached_property
    def function_lookup(self) -> dict[tuple[str, str], Function]:
        return self.register.function_lookup()

    @cached_property
    def services_by_contract(self) -> dict[str, list[ContractSpecific]]:
        return self.register.services_by_contract()

    @cached_property
    def providers_by_contract(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for s in self.register.b_02_02:
            if s.contract_ref and s.provider_code:
                out[s.contract_ref].add(s.provider_code)
        return dict(out)

    @cached_property
    def critical_function_ids(self) -> set[str]:
        return {f.function_id for f in self.register.b_06_01 if f.is_critical and f.function_id}

    def supports_critical(self, service: ContractSpecific) -> bool:
        fn = self.function_lookup.get((service.function_id or "", service.entity_lei or ""))
        if fn is not None:
            return fn.is_critical
        return (service.function_id or "") in self.critical_function_ids

    @cached_property
    def critical_services(self) -> list[ContractSpecific]:
        return [s for s in self.register.b_02_02 if self.supports_critical(s)]

    # ------------------------------------------------------------------ findings

    def finding(
        self,
        rule_id: str,
        message: str,
        record: RoIRecord | None = None,
        attr: str | None = None,
        *,
        value: Any = None,
        template: str | None = None,
    ) -> Finding:
        """Create a finding for ``rule_id`` located at ``record``/``attr``."""
        rule = RULES[rule_id]
        severity = self.config.severity_overrides.get(rule_id, rule.severity)
        column = None
        if record is not None and attr is not None:
            column = type(record).column(attr).code
        return Finding(
            rule_id=rule_id,
            severity=severity,
            category=rule.category,
            message=message,
            template=template or (record.TEMPLATE if record is not None else None),
            row=record.row if record is not None else None,
            column=column,
            record_key=record.key_str() if record is not None else None,
            value=None if value is None else str(value),
            source=record.source if record is not None else None,
        )
