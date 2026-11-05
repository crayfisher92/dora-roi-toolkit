"""DORA reporting scope of a group dataset (P-15).

A Swiss group can keep its Swiss bank's arrangements in the same register as those of its EU
subsidiaries, so that one dataset serves both the DORA Register of Information and the FINMA
outsourcing inventory. Entities marked as **outside the DORA scope** stay in the dataset
(validation, analysis, FINMA view, Excel/CSV export) but are left out of the supervisory
xBRL-CSV package, together with everything that only concerns them:

* their B_01.02 entry, branches (B_01.03), service rows (B_02.02), signatures (B_03.01,
  B_03.03), recipients (B_04.01) and functions (B_06.01);
* arrangements no in-scope entity uses or signs (B_02.01 and their B_02.03, B_03.02, B_05.02,
  B_07.01 rows);
* providers no remaining arrangement or supply chain refers to (B_05.01), keeping the
  ultimate parents of the remaining providers.

The entity maintaining the register (B_01.01) cannot be excluded.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from dora_roi.model import TEMPLATES_BY_CODE, RegisterOfInformation
from dora_roi.validation import Finding


class ScopeError(ValueError):
    """The requested scope is not possible (e.g. excluding the maintaining entity)."""


@dataclass
class ScopeSummary:
    excluded_entities: list[str] = field(default_factory=list)
    removed: dict[str, int] = field(default_factory=dict)

    @property
    def total_removed(self) -> int:
        return sum(self.removed.values())


def restrict_to_scope(register: RegisterOfInformation, excluded: Iterable[str]
                      ) -> tuple[RegisterOfInformation, ScopeSummary]:
    """A copy of ``register`` without the entities in ``excluded`` (LEIs) and what only
    concerns them. Records are shared, not copied (they are not modified)."""
    out_leis = {e for e in excluded if e}
    maintainer = register.maintainer
    if maintainer is not None and maintainer.lei in out_leis:
        raise ScopeError("the entity maintaining the register cannot be outside the scope")
    summary = ScopeSummary(sorted(out_leis))
    if not out_leis:
        return register, summary
    reg = RegisterOfInformation()
    reg.b_01_01 = list(register.b_01_01)
    reg.b_01_02 = [e for e in register.b_01_02 if e.lei not in out_leis]
    reg.b_01_03 = [b for b in register.b_01_03 if b.head_office_lei not in out_leis]
    reg.b_02_02 = [s for s in register.b_02_02 if s.entity_lei not in out_leis]
    reg.b_03_01 = [s for s in register.b_03_01 if s.entity_lei not in out_leis]
    reg.b_04_01 = [r for r in register.b_04_01 if r.entity_lei not in out_leis]
    used = ({s.contract_ref for s in reg.b_02_02} | {s.contract_ref for s in reg.b_03_01}
            | {r.contract_ref for r in reg.b_04_01})
    excluded_only = ({s.contract_ref for s in register.b_02_02 if s.entity_lei in out_leis}
                     | {s.contract_ref for s in register.b_03_01 if s.entity_lei in out_leis}
                     | {r.contract_ref for r in register.b_04_01 if r.entity_lei in out_leis})
    dropped = excluded_only - used
    reg.b_02_01 = [c for c in register.b_02_01 if c.contract_ref not in dropped]
    reg.b_02_03 = [x for x in register.b_02_03
                   if x.contract_ref not in dropped and x.linked_contract_ref not in dropped]
    reg.b_03_02 = [x for x in register.b_03_02 if x.contract_ref not in dropped]
    reg.b_03_03 = [x for x in register.b_03_03
                   if x.contract_ref not in dropped and x.entity_lei not in out_leis]
    reg.b_05_02 = [x for x in register.b_05_02 if x.contract_ref not in dropped]
    reg.b_07_01 = [x for x in register.b_07_01 if x.contract_ref not in dropped]
    reg.b_06_01 = [f for f in register.b_06_01 if f.entity_lei not in out_leis]
    referenced = ({s.provider_code for s in reg.b_02_02} | {s.provider_code for s in reg.b_03_02}
                  | {s.provider_code for s in reg.b_05_02}
                  | {s.recipient_code for s in reg.b_05_02} | {a.provider_code
                                                               for a in reg.b_07_01})
    providers = register.providers_by_code()
    parents = {providers[c].ultimate_parent_code for c in referenced if c in providers}
    keep = referenced | parents
    reg.b_05_01 = [p for p in register.b_05_01
                   if p.provider_code in keep or p.provider_code is None]
    before, after = register.counts(), reg.counts()
    summary.removed = {k: before[k] - after[k] for k in before if before[k] != after[k]}
    return reg, summary


def findings_in(findings: Iterable[Finding], register: RegisterOfInformation) -> list[Finding]:
    """The import findings that concern records still in ``register`` (or no record), used
    to validate the restricted register as the package it becomes (P-20)."""
    kept = {(t, r.key_str()) for t in TEMPLATES_BY_CODE for r in register.records(t)}
    return [f for f in findings if f.record_key is None or (f.template, f.record_key) in kept]
