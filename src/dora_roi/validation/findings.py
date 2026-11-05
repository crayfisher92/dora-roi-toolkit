"""Findings, severities and the rule registry."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from dora_roi.validation.context import ValidationContext


class Severity(StrEnum):
    """Severity of a finding. ``ERROR`` findings would block a supervisory submission."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 0, "warning": 1, "info": 2}[self.value]


class Category(StrEnum):
    """Family of a rule."""

    IMPORT = "import"
    FIELD = "field"
    REFERENTIAL = "referential"
    SUPPLY_CHAIN = "supply_chain"
    BUSINESS = "business"


class Finding(BaseModel):
    """One problem detected in the register."""

    rule_id: str
    severity: Severity
    category: Category
    message: str
    template: str | None = None
    row: int | None = None
    column: str | None = None
    record_key: str | None = None
    value: str | None = None
    source: str | None = None

    @property
    def location(self) -> str:
        parts = [p for p in (self.template, f"row {self.row}" if self.row else None,
                             self.column) if p]
        return " / ".join(parts) if parts else "register"


CheckFn = Callable[["ValidationContext"], Iterable[Finding]]


@dataclass(frozen=True)
class Rule:
    """A validation rule and its regulatory justification."""

    id: str
    title: str
    severity: Severity
    category: Category
    templates: tuple[str, ...]
    references: tuple[str, ...]
    description: str
    check: CheckFn | None = field(default=None, compare=False)


RULES: dict[str, Rule] = {}


def register_rule(rule: Rule) -> Rule:
    if rule.id in RULES:
        raise ValueError(f"duplicate rule id {rule.id}")
    RULES[rule.id] = rule
    return rule


def rule(
    rule_id: str,
    title: str,
    *,
    severity: Severity,
    category: Category,
    templates: Iterable[str],
    references: Iterable[str],
    description: str,
) -> Callable[[CheckFn], CheckFn]:
    """Decorator registering a check function as a rule."""

    def decorator(fn: CheckFn) -> CheckFn:
        register_rule(
            Rule(rule_id, title, severity, category, tuple(templates), tuple(references),
                 description, fn)
        )
        return fn

    return decorator


def declare(
    rule_id: str,
    title: str,
    *,
    severity: Severity,
    category: Category,
    templates: Iterable[str],
    references: Iterable[str],
    description: str,
) -> Rule:
    """Register a rule whose findings are produced outside the engine (parser/importers)."""
    return register_rule(
        Rule(rule_id, title, severity, category, tuple(templates), tuple(references), description)
    )
