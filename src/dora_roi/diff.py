"""Compare two versions of a register (e.g. last year's submission with this year's)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from dora_roi.model import RegisterOfInformation, RoIRecord, serialise_value

#: Templates compared, with a human name for the object type.
DIFF_TEMPLATES: dict[str, str] = {
    "B_01.02": "Entities",
    "B_05.01": "ICT third-party providers",
    "B_02.01": "Contractual arrangements",
    "B_02.02": "ICT services (arrangement details)",
    "B_06.01": "Functions",
    "B_07.01": "Assessments",
    "B_05.02": "Supply-chain entries",
}


@dataclass(frozen=True)
class FieldChange:
    column: str
    label: str
    old: str | None
    new: str | None


@dataclass
class RecordChange:
    key: str
    name: str
    changes: list[FieldChange]


@dataclass
class TemplateDiff:
    template: str
    title: str
    added: list[tuple[str, str]] = field(default_factory=list)  # (key, name)
    removed: list[tuple[str, str]] = field(default_factory=list)
    changed: list[RecordChange] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.added) + len(self.removed) + len(self.changed)


@dataclass
class RegisterDiff:
    old_label: str
    new_label: str
    templates: list[TemplateDiff]
    old_spend: Decimal
    new_spend: Decimal
    old_critical_functions: int
    new_critical_functions: int

    @property
    def is_empty(self) -> bool:
        return all(t.total == 0 for t in self.templates)

    def get(self, template: str) -> TemplateDiff:
        return next(t for t in self.templates if t.template == template)


def _name(record: RoIRecord, providers: dict[str, str]) -> str:
    for attr in ("legal_name", "name", "function_name"):
        value = getattr(record, attr, None)
        if value:
            return str(value)
    code = getattr(record, "provider_code", None)
    if code and code in providers:
        return f"{record.key_str().split(' | ')[0]} – {providers[code]}"
    return record.key_str()


def _index(records: list[RoIRecord]) -> dict[str, RoIRecord]:
    out: dict[str, RoIRecord] = {}
    for r in records:
        if any(v is not None for v in r.key()):
            out.setdefault(r.key_str(), r)
    return out


def _spend(reg: RegisterOfInformation) -> Decimal:
    return sum((c.annual_cost for c in reg.b_02_01 if c.annual_cost is not None), Decimal(0))


def diff_registers(old: RegisterOfInformation, new: RegisterOfInformation,
                   old_label: str = "previous", new_label: str = "current") -> RegisterDiff:
    """Compare two registers template by template using each template's primary key."""
    names = {p.provider_code: p.legal_name or p.provider_code
             for reg in (old, new) for p in reg.b_05_01 if p.provider_code}
    templates: list[TemplateDiff] = []
    for code, title in DIFF_TEMPLATES.items():
        a, b = _index(old.records(code)), _index(new.records(code))
        td = TemplateDiff(code, title)
        td.added = sorted((k, _name(b[k], names)) for k in b.keys() - a.keys())
        td.removed = sorted((k, _name(a[k], names)) for k in a.keys() - b.keys())
        for k in sorted(a.keys() & b.keys()):
            changes = []
            for spec in type(a[k]).columns():
                ov = serialise_value(getattr(a[k], spec.attr))
                nv = serialise_value(getattr(b[k], spec.attr))
                if ov != nv:
                    changes.append(FieldChange(spec.code, spec.label, ov, nv))
            if changes:
                td.changed.append(RecordChange(k, _name(b[k], names), changes))
        templates.append(td)
    return RegisterDiff(old_label, new_label, templates, _spend(old), _spend(new),
                        len(old.critical_function_keys()), len(new.critical_function_keys()))


def render_diff_markdown(d: RegisterDiff) -> str:
    lines = [f"# Register comparison: {d.old_label} → {d.new_label}", "",
             f"- Annual spend: {d.old_spend:,.0f} → {d.new_spend:,.0f}",
             f"- Critical or important functions: {d.old_critical_functions} → "
             f"{d.new_critical_functions}", "",
             "| Object | Added | Removed | Changed |", "|---|---:|---:|---:|"]
    lines += [f"| {t.title} ({t.template}) | {len(t.added)} | {len(t.removed)} | "
              f"{len(t.changed)} |" for t in d.templates]
    for t in d.templates:
        if not t.total:
            continue
        lines += ["", f"## {t.title} ({t.template})", ""]
        lines += [f"- **added** {name} (`{key}`)" for key, name in t.added]
        lines += [f"- **removed** {name} (`{key}`)" for key, name in t.removed]
        for rc in t.changed:
            detail = "; ".join(f"{c.label}: {c.old or '—'} → {c.new or '—'}" for c in rc.changes)
            lines.append(f"- **changed** {rc.name} (`{rc.key}`): {detail}")
    lines.append("")
    return "\n".join(lines)
