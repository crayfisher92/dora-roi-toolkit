"""DORA Art. 30 contract gap analysis: checklist, assessments, portfolio and remediation plan.

Typical use::

    from dora_roi.contracts import AssessmentBook, evaluate, remediation_plan
    portfolio = evaluate(register, AssessmentBook.from_json(text))
    plan = remediation_plan(portfolio)
"""

from dora_roi.contracts.analysis import (
    ComplianceStatus,
    ContractCompliance,
    ContractContext,
    Portfolio,
    Priority,
    ProviderCompliance,
    RemediationItem,
    RemediationPlan,
    contract_contexts,
    evaluate,
    evaluate_contract,
    gaps_by_provision,
    remediation_plan,
)
from dora_roi.contracts.model import (
    AssessmentBook,
    ContractAssessment,
    ProvisionAssessment,
    ProvisionStatus,
    load_assessments,
    read_assessment_workbook,
    write_assessment_workbook,
)
from dora_roi.contracts.provisions import PROVISIONS, PROVISIONS_BY_ID, Provision, Scope

__all__ = [
    "PROVISIONS",
    "PROVISIONS_BY_ID",
    "AssessmentBook",
    "ComplianceStatus",
    "ContractAssessment",
    "ContractCompliance",
    "ContractContext",
    "Portfolio",
    "Priority",
    "ProviderCompliance",
    "Provision",
    "ProvisionAssessment",
    "ProvisionStatus",
    "RemediationItem",
    "RemediationPlan",
    "Scope",
    "contract_contexts",
    "evaluate",
    "evaluate_contract",
    "gaps_by_provision",
    "load_assessments",
    "read_assessment_workbook",
    "remediation_plan",
    "write_assessment_workbook",
]
