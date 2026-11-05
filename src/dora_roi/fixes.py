"""Fix suggestions for findings and grouping of repeated errors for bulk fixing."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from dora_roi.lei import lei_check_digits
from dora_roi.model import TEMPLATES_BY_CODE
from dora_roi.model.types import Kind
from dora_roi.normalise import closest_code, country_code, currency_code, to_bool, to_date
from dora_roi.validation import Finding


class Confidence(StrEnum):
    HIGH = "high"  # safe to apply in bulk
    LOW = "low"  # plausible, needs a human look


@dataclass(frozen=True)
class FixSuggestion:
    value: str
    confidence: Confidence
    note: str


@dataclass
class BulkGroup:
    """Several findings with the same rule, column and wrong value."""

    rule_id: str
    template: str
    column: str
    value: str
    rows: list[int] = field(default_factory=list)
    suggestion: FixSuggestion | None = None

    @property
    def count(self) -> int:
        return len(self.rows)


def _kind(template: str | None, column: str | None) -> tuple[Kind | None, object]:
    if not template or not column or template not in TEMPLATES_BY_CODE:
        return None, None
    spec = TEMPLATES_BY_CODE[template].column_by_code(column)
    if spec is None:
        return None, None
    return spec.col.kind, spec.col.codelist


def suggest(finding: Finding) -> FixSuggestion | None:
    """Return a suggested replacement value for ``finding`` if one can be inferred."""
    value = (finding.value or "").strip()
    kind, codelist = _kind(finding.template, finding.column)
    rid = finding.rule_id
    if rid == "FLD-005" and value:
        code = country_code(value)
        if code:
            return FixSuggestion(code, Confidence.HIGH, f"ISO 3166-1 code for '{value}'")
    if rid == "FLD-006" and value:
        cur = currency_code(value)
        if cur:
            return FixSuggestion(cur, Confidence.HIGH, f"ISO 4217 code for '{value}'")
    if rid == "FLD-003" and value:
        parsed = to_date(value)
        if parsed:
            return FixSuggestion(parsed.isoformat(), Confidence.HIGH,
                                 "Same date in ISO 8601 format (day first assumed)")
    if rid == "FLD-004" and value and codelist is not None:
        member = closest_code(codelist, value)  # type: ignore[arg-type]
        if member is not None:
            return FixSuggestion(member.value, Confidence.LOW, f"Closest value: {member.label}")
    if rid == "FLD-008" and value:
        flag = to_bool(value)
        if flag is not None:
            return FixSuggestion("true" if flag else "false", Confidence.HIGH, "Boolean value")
    if rid in ("FLD-002", "FLD-013") and value:
        cleaned = re.sub(r"[\s\-]", "", value).upper()
        if len(cleaned) == 20 and re.fullmatch(r"[A-Z0-9]{18}\d{2}", cleaned):
            fixed = cleaned[:18] + lei_check_digits(cleaned[:18])
            if fixed != value:
                note = ("Removed spaces/lower case" if fixed == cleaned else
                        "Recomputed check digits – only correct if the first 18 characters "
                        "are right; verify in GLEIF")
                return FixSuggestion(fixed, Confidence.HIGH if fixed == cleaned
                                     else Confidence.LOW, note)
    if rid == "FLD-001" and kind is Kind.BOOLEAN and finding.column and \
            finding.template in ("B_02.03", "B_03.01", "B_03.02", "B_03.03"):
        return FixSuggestion("true", Confidence.HIGH, "Link columns are always true")
    if rid == "BUS-024":
        return FixSuggestion("9999-12-31", Confidence.HIGH, "Convention for open-ended contracts")
    if rid == "SC-004":
        return FixSuggestion("", Confidence.HIGH, "Rank 1 has no recipient")
    return None


def bulk_groups(findings: Iterable[Finding], min_count: int = 2) -> list[BulkGroup]:
    """Group findings that share rule, template, column and (wrong) value."""
    groups: dict[tuple[str, str, str, str], BulkGroup] = {}
    for f in findings:
        if not (f.template and f.column and f.row):
            continue
        if not f.value and f.rule_id != "FLD-001":
            continue
        key = (f.rule_id, f.template, f.column, f.value or "")
        group = groups.get(key)
        if group is None:
            group = groups[key] = BulkGroup(f.rule_id, f.template, f.column, f.value or "",
                                            suggestion=suggest(f))
        group.rows.append(f.row)
    result = [g for g in groups.values() if g.count >= min_count]
    return sorted(result, key=lambda g: (-g.count, g.template, g.column))


def findings_by_template(findings: Iterable[Finding]) -> dict[str, dict[str, list[Finding]]]:
    """``{template: {severity: [findings]}}`` sorted by template code."""
    out: dict[str, dict[str, list[Finding]]] = defaultdict(lambda: defaultdict(list))
    for f in findings:
        out[f.template or "register"][f.severity.value].append(f)
    return {k: dict(v) for k, v in sorted(out.items())}
