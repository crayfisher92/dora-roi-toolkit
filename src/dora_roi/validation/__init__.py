"""Validation engine for the register of information.

Importing this package registers every rule (field, referential, supply-chain and business).
"""

from dora_roi.validation import (  # noqa: F401  (imported for rule registration)
    business_rules,
    field_rules,
    referential_rules,
    supply_chain_rules,
)
from dora_roi.validation.context import ValidationConfig, ValidationContext
from dora_roi.validation.engine import (
    RuleFailure,
    ValidationReport,
    engine_rules,
    rules_catalogue,
    validate,
)
from dora_roi.validation.findings import RULES, Category, Finding, Rule, Severity

__all__ = [
    "RULES",
    "Category",
    "Finding",
    "Rule",
    "RuleFailure",
    "Severity",
    "ValidationConfig",
    "ValidationContext",
    "ValidationReport",
    "engine_rules",
    "rules_catalogue",
    "validate",
]
