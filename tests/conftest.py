from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from dora_roi.lei import make_lei
from dora_roi.model import (
    ContractGeneral,
    ContractSigningEntity,
    ContractSigningProvider,
    ContractSpecific,
    ContractType,
    Criticality,
    DataSensitivity,
    EntityInScope,
    EntityMaintainingRegister,
    EntityType,
    Function,
    HierarchyInGroup,
    IctServiceType,
    IctThirdPartyProvider,
    Impact,
    PersonType,
    ProviderCodeType,
    RegisterOfInformation,
    Reintegration,
    RelianceLevel,
    ServiceAssessment,
    ServiceRecipient,
    Substitutability,
    SupplyChainEntry,
)

ENTITY = make_lei("TESTENTITY00000001")
PARENT = make_lei("TESTPARENT00000001")
PROVIDER = make_lei("TESTPROVIDER000001")
SUBCONTRACTOR = make_lei("TESTSUBCONTRACT001")
REF_DATE = date(2025, 12, 31)


def build_valid_register() -> RegisterOfInformation:
    """A tiny register that passes every error and warning rule."""
    reg = RegisterOfInformation()
    reg.add(EntityMaintainingRegister(
        lei=ENTITY, name="Test Bank AG", country="DE", entity_type=EntityType.CREDIT_INSTITUTION,
        competent_authority="BaFin", reporting_date=REF_DATE))
    reg.add(EntityInScope(
        lei=ENTITY, name="Test Bank AG", country="DE", entity_type=EntityType.CREDIT_INSTITUTION,
        hierarchy=HierarchyInGroup.ULTIMATE_PARENT, last_update=date(2025, 12, 1),
        integration_date=date(2025, 1, 17), currency="EUR", total_assets=Decimal("1000000000")))
    reg.add(ContractGeneral(contract_ref="C-001", contract_type=ContractType.STANDALONE,
                            currency="EUR", annual_cost=Decimal("100000")))
    reg.add(ContractSpecific(
        contract_ref="C-001", entity_lei=ENTITY, provider_code=PROVIDER,
        provider_code_type=ProviderCodeType.LEI, function_id="F-PAY",
        service_type=IctServiceType.S19, start_date=date(2023, 1, 1),
        end_date=date(9999, 12, 31), notice_period_entity=90, notice_period_provider=180,
        governing_law_country="DE", service_country="DE", data_storage=True,
        data_location_storage="DE", data_location_processing="DE",
        data_sensitivity=DataSensitivity.HIGH, reliance_level=RelianceLevel.FULL))
    reg.add(ContractSigningEntity(contract_ref="C-001", entity_lei=ENTITY))
    reg.add(ContractSigningProvider(contract_ref="C-001", provider_code=PROVIDER,
                                    provider_code_type=ProviderCodeType.LEI))
    reg.add(ServiceRecipient(contract_ref="C-001", entity_lei=ENTITY, is_branch=False))
    for code, name, parent in ((PROVIDER, "SaaS Vendor GmbH", PROVIDER),
                               (SUBCONTRACTOR, "Cloud Host Ltd", SUBCONTRACTOR)):
        reg.add(IctThirdPartyProvider(
            provider_code=code, provider_code_type=ProviderCodeType.LEI, legal_name=name,
            person_type=PersonType.LEGAL, hq_country="DE", currency="EUR",
            total_annual_cost=Decimal("100000"), ultimate_parent_code=parent,
            ultimate_parent_code_type=ProviderCodeType.LEI))
    reg.add(SupplyChainEntry(contract_ref="C-001", service_type=IctServiceType.S19,
                             provider_code=PROVIDER, provider_code_type=ProviderCodeType.LEI,
                             rank=1))
    reg.add(SupplyChainEntry(contract_ref="C-001", service_type=IctServiceType.S19,
                             provider_code=SUBCONTRACTOR, provider_code_type=ProviderCodeType.LEI,
                             rank=2, recipient_code=PROVIDER,
                             recipient_code_type=ProviderCodeType.LEI))
    reg.add(Function(
        function_id="F-PAY", licensed_activity="Payment services", function_name="Payments",
        entity_lei=ENTITY, criticality=Criticality.CRITICAL,
        criticality_reasons="Disruption would impair continuity of payment services",
        last_assessment_date=date(2025, 6, 30), rto_hours=4, rpo_hours=1,
        discontinuation_impact=Impact.HIGH))
    reg.add(ServiceAssessment(
        contract_ref="C-001", provider_code=PROVIDER, provider_code_type=ProviderCodeType.LEI,
        service_type=IctServiceType.S19, substitutability=Substitutability.MEDIUM,
        last_audit_date=date(2024, 5, 1), exit_plan=True, reintegration=Reintegration.DIFFICULT,
        discontinuation_impact=Impact.HIGH, alternatives_identified=True,
        alternative_providers="Vendor B; Vendor C"))
    return reg


@pytest.fixture
def valid_register() -> RegisterOfInformation:
    return build_valid_register()
