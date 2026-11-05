"""Validation engine: runs all registered rules and assembles a :class:`ValidationReport`."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field

from dora_roi import __version__
from dora_roi.model import RegisterOfInformation
from dora_roi.validation.context import ValidationConfig, ValidationContext
from dora_roi.validation.findings import RULES, Category, Finding, Rule, Severity


class RuleFailure(BaseModel):
    """A rule whose check function raised an exception (reported, never swallowed silently)."""

    rule_id: str
    error: str


class ValidationReport(BaseModel):
    """Result of validating a register."""

    toolkit_version: str = __version__
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str | None = None
    reference_date: date | None = None
    maintainer_lei: str | None = None
    maintainer_name: str | None = None
    record_counts: dict[str, int] = Field(default_factory=dict)
    rules_run: int = 0
    findings: list[Finding] = Field(default_factory=list)
    #: Warning/info findings accepted with a justification (excluded from counts).
    accepted: list[Finding] = Field(default_factory=list)
    rule_failures: list[RuleFailure] = Field(default_factory=list)

    # ---------------------------------------------------------------- summaries

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.INFO]

    @property
    def passed(self) -> bool:
        """True when there is no error-level finding."""
        return not self.errors and not self.rule_failures

    def severity_counts(self) -> dict[str, int]:
        counts = Counter(f.severity.value for f in self.findings)
        return {s.value: counts.get(s.value, 0) for s in Severity}

    def by_rule(self) -> list[tuple[Rule, int]]:
        counts = Counter(f.rule_id for f in self.findings)
        rules = [(RULES[rid], n) for rid, n in counts.items() if rid in RULES]
        return sorted(rules, key=lambda rn: (rn[0].severity.rank, -rn[1], rn[0].id))

    def by_template(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for f in self.findings:
            key = f.template or "register"
            bucket = out.setdefault(key, {s.value: 0 for s in Severity})
            bucket[f.severity.value] += 1
        return dict(sorted(out.items()))

    def sorted_findings(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (f.severity.rank, f.template or "", f.row or 0, f.rule_id,
                           f.column or ""),
        )

    def to_json_dict(self) -> dict[str, Any]:
        """Machine-readable representation (stable schema, see docs/ARCHITECTURE.md)."""
        return {
            "schema": "dora-roi-toolkit/validation-report/v1",
            "toolkit_version": self.toolkit_version,
            "generated_at": self.generated_at.isoformat(),
            "source": self.source,
            "reference_date": self.reference_date.isoformat() if self.reference_date else None,
            "maintainer": {"lei": self.maintainer_lei, "name": self.maintainer_name},
            "passed": self.passed,
            "summary": {
                "severity_counts": self.severity_counts(),
                "rules_run": self.rules_run,
                "record_counts": self.record_counts,
                "by_template": self.by_template(),
                "by_rule": [
                    {"rule_id": r.id, "title": r.title, "severity": r.severity.value, "count": n}
                    for r, n in self.by_rule()
                ],
            },
            "findings": [f.model_dump(mode="json", exclude={"accepted_reason"})
                         for f in self.sorted_findings()],
            "accepted": [f.model_dump(mode="json") for f in self.accepted],
            "rule_failures": [rf.model_dump() for rf in self.rule_failures],
        }


def engine_rules(config: ValidationConfig | None = None) -> list[Rule]:
    """Rules executed by the engine (those with a check function), in ID order."""
    disabled = config.disabled_rules if config else frozenset()
    return sorted(
        (r for r in RULES.values() if r.check is not None and r.id not in disabled),
        key=lambda r: r.id,
    )


def validate(
    register: RegisterOfInformation,
    *,
    parse_findings: Iterable[Finding] = (),
    config: ValidationConfig | None = None,
    source: str | None = None,
) -> ValidationReport:
    """Run every enabled rule against ``register``.

    ``parse_findings`` are the field-level findings produced while loading the input (see
    :func:`dora_roi.io.parse.parse_raw`); they are merged into the report after applying the
    same rule enable/severity configuration.
    """
    config = config or ValidationConfig()
    ctx = ValidationContext(register, config)
    findings: list[Finding] = []
    for f in parse_findings:
        if f.rule_id in config.disabled_rules:
            continue
        override = config.severity_overrides.get(f.rule_id)
        findings.append(f.model_copy(update={"severity": override}) if override else f)

    failures: list[RuleFailure] = []
    rules = engine_rules(config)
    for r in rules:
        if r.check is None:  # pragma: no cover - engine_rules() only returns checkable rules
            continue
        try:
            findings.extend(r.check(ctx))
        except Exception as exc:  # pragma: no cover - defensive: a buggy rule must not hide others
            failures.append(RuleFailure(rule_id=r.id, error=f"{type(exc).__name__}: {exc}"))

    m = register.maintainer
    return ValidationReport(
        source=source,
        reference_date=ctx.reference_date,
        maintainer_lei=m.lei if m else None,
        maintainer_name=m.name if m else None,
        record_counts=register.counts(),
        rules_run=len(rules) + sum(
            1 for r in RULES.values() if r.check is None and r.id not in config.disabled_rules
        ),
        findings=findings,
        rule_failures=failures,
    )


def rules_catalogue() -> list[Rule]:
    """All rules (engine and parser/importer rules) sorted by category and ID."""
    order = {c: i for i, c in enumerate(Category)}
    return sorted(RULES.values(), key=lambda r: (order[r.category], r.id))
