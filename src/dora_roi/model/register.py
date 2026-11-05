"""The :class:`RegisterOfInformation` container and cross-template look-ups."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from dora_roi.model.templates import (
    TEMPLATE_MODELS,
    Branch,
    ContractGeneral,
    ContractSigningEntity,
    ContractSigningProvider,
    ContractSpecific,
    EntityInScope,
    EntityMaintainingRegister,
    Function,
    IctThirdPartyProvider,
    IntraGroupContractLink,
    IntraGroupProvidingEntity,
    RoIRecord,
    ServiceAssessment,
    ServiceRecipient,
    SupplyChainEntry,
)

R = TypeVar("R", bound=RoIRecord)

#: Template code -> attribute name on :class:`RegisterOfInformation`.
TEMPLATE_ATTRS: dict[str, str] = {
    m.TEMPLATE: "b_" + m.TEMPLATE[2:].replace(".", "_") for m in TEMPLATE_MODELS
}


class RegisterOfInformation(BaseModel):
    """A complete register of information: one list of records per template."""

    b_01_01: list[EntityMaintainingRegister] = Field(default_factory=list)
    b_01_02: list[EntityInScope] = Field(default_factory=list)
    b_01_03: list[Branch] = Field(default_factory=list)
    b_02_01: list[ContractGeneral] = Field(default_factory=list)
    b_02_02: list[ContractSpecific] = Field(default_factory=list)
    b_02_03: list[IntraGroupContractLink] = Field(default_factory=list)
    b_03_01: list[ContractSigningEntity] = Field(default_factory=list)
    b_03_02: list[ContractSigningProvider] = Field(default_factory=list)
    b_03_03: list[IntraGroupProvidingEntity] = Field(default_factory=list)
    b_04_01: list[ServiceRecipient] = Field(default_factory=list)
    b_05_01: list[IctThirdPartyProvider] = Field(default_factory=list)
    b_05_02: list[SupplyChainEntry] = Field(default_factory=list)
    b_06_01: list[Function] = Field(default_factory=list)
    b_07_01: list[ServiceAssessment] = Field(default_factory=list)

    # ------------------------------------------------------------------ generic access

    def records(self, template: str) -> list[RoIRecord]:
        """Records of a template by code (``"B_02.02"``)."""
        value: list[RoIRecord] = getattr(self, TEMPLATE_ATTRS[template])
        return value

    def add(self, record: RoIRecord) -> None:
        self.records(record.TEMPLATE).append(record)

    def iter_all(self) -> Iterator[RoIRecord]:
        for model in TEMPLATE_MODELS:
            yield from self.records(model.TEMPLATE)

    def counts(self) -> dict[str, int]:
        return {m.TEMPLATE: len(self.records(m.TEMPLATE)) for m in TEMPLATE_MODELS}

    def is_empty(self) -> bool:
        return not any(self.counts().values())

    # ------------------------------------------------------------------ convenience

    @property
    def maintainer(self) -> EntityMaintainingRegister | None:
        return self.b_01_01[0] if self.b_01_01 else None

    @property
    def reference_date(self) -> date | None:
        """Reporting reference date from B_01.01 (if reported and valid)."""
        m = self.maintainer
        return m.reporting_date if m else None

    @property
    def reporting_currency(self) -> str | None:
        m = self.maintainer
        if m is None:
            return None
        for ent in self.b_01_02:
            if ent.lei == m.lei and ent.currency:
                return ent.currency
        return None

    def entity_leis(self) -> set[str]:
        return {e.lei for e in self.b_01_02 if e.lei}

    def entities_by_lei(self) -> dict[str, EntityInScope]:
        return {e.lei: e for e in self.b_01_02 if e.lei}

    def providers_by_code(self) -> dict[str, IctThirdPartyProvider]:
        return {p.provider_code: p for p in self.b_05_01 if p.provider_code}

    def contracts_by_ref(self) -> dict[str, ContractGeneral]:
        return {c.contract_ref: c for c in self.b_02_01 if c.contract_ref}

    def functions_by_id(self) -> dict[str, list[Function]]:
        out: dict[str, list[Function]] = defaultdict(list)
        for f in self.b_06_01:
            if f.function_id:
                out[f.function_id].append(f)
        return dict(out)

    def function_lookup(self) -> dict[tuple[str, str], Function]:
        return {
            (f.function_id, f.entity_lei): f
            for f in self.b_06_01
            if f.function_id and f.entity_lei
        }

    def critical_function_keys(self) -> set[tuple[str, str]]:
        return {k for k, f in self.function_lookup().items() if f.is_critical}

    def services_by_contract(self) -> dict[str, list[ContractSpecific]]:
        out: dict[str, list[ContractSpecific]] = defaultdict(list)
        for s in self.b_02_02:
            if s.contract_ref:
                out[s.contract_ref].append(s)
        return dict(out)

    def supply_chain_by_contract(self) -> dict[str, list[SupplyChainEntry]]:
        out: dict[str, list[SupplyChainEntry]] = defaultdict(list)
        for s in self.b_05_02:
            if s.contract_ref:
                out[s.contract_ref].append(s)
        return dict(out)

    def assessments_by_key(self) -> dict[tuple[Any, ...], ServiceAssessment]:
        return {
            (a.contract_ref, a.provider_code, a.service_type): a
            for a in self.b_07_01
            if a.contract_ref
        }

    def critical_checker(self) -> Callable[[ContractSpecific], bool]:
        """A fast :meth:`supports_critical` for many rows (lookups are built once)."""
        lookup = self.function_lookup()
        critical_ids = {f.function_id for f in self.b_06_01 if f.is_critical and f.function_id}

        def check(service: ContractSpecific) -> bool:
            fn = lookup.get((service.function_id or "", service.entity_lei or ""))
            if fn is not None:
                return fn.is_critical
            # fall back to function id only (another entity's function)
            return (service.function_id or "") in critical_ids

        return check

    def supports_critical(self, service: ContractSpecific) -> bool:
        """True if a B_02.02 row supports a critical or important function.

        Builds the function lookups on every call; use :meth:`critical_checker` in loops.
        """
        return self.critical_checker()(service)

    def summary(self) -> dict[str, Any]:
        """Lightweight description used in reports."""
        m = self.maintainer
        return {
            "maintainer_lei": m.lei if m else None,
            "maintainer_name": m.name if m else None,
            "reference_date": self.reference_date.isoformat() if self.reference_date else None,
            "counts": self.counts(),
        }
