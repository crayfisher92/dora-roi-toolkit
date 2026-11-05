"""Contract assessments against the DORA Art. 30 checklist, and their file formats.

An :class:`AssessmentBook` holds one :class:`ContractAssessment` per contractual arrangement,
keyed by the arrangement reference number of B_02.01 (c0010). That key is the link to the
register: the assessment does not copy provider, entity or function data, it reads them from
the register at evaluation time (:mod:`dora_roi.contracts.analysis`), so the two can never
disagree.

Formats:

* JSON (``dora-roi-toolkit/contract-assessments/v1``) – lossless, including the history;
* Excel – one row per contract × provision (sheet ``Assessments``), for working offline with
  a client; the same layout is read back by :func:`read_assessment_workbook`.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dora_roi import __version__
from dora_roi.contracts.provisions import PROVISIONS, PROVISIONS_BY_ID
from dora_roi.io.sheets import SheetBook
from dora_roi.io.xlsx_read import SpreadsheetError, iter_sheets

SCHEMA = "dora-roi-toolkit/contract-assessments/v1"
MAX_TEXT = 4000


class ProvisionStatus(StrEnum):
    PRESENT = "present"
    PARTIAL = "partial"
    MISSING = "missing"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def parse(cls, raw: object) -> ProvisionStatus:
        """Accept codes, English/German words and common shorthands (``ja``, ``n/a``…)."""
        text = str(raw or "").strip().casefold().replace("-", "_").replace(" ", "_")
        aliases = {
            "": cls.NOT_ASSESSED, "open": cls.NOT_ASSESSED, "tbd": cls.NOT_ASSESSED,
            "offen": cls.NOT_ASSESSED, "nicht_bewertet": cls.NOT_ASSESSED,
            "yes": cls.PRESENT, "ja": cls.PRESENT, "vorhanden": cls.PRESENT,
            "compliant": cls.PRESENT, "ok": cls.PRESENT,
            "teilweise": cls.PARTIAL, "partly": cls.PARTIAL, "partially": cls.PARTIAL,
            "no": cls.MISSING, "nein": cls.MISSING, "fehlt": cls.MISSING, "absent": cls.MISSING,
        }
        if text in aliases:
            return aliases[text]
        try:
            return cls(text)
        except ValueError as exc:
            raise ValueError(f"unknown status {raw!r} (use present, partial or missing)") from exc


class ProvisionAssessment(BaseModel):
    """Assessment of one checklist item for one contract."""

    model_config = ConfigDict(extra="forbid")

    provision_id: str
    status: ProvisionStatus = ProvisionStatus.NOT_ASSESSED
    clause_ref: str = Field(default="", max_length=200)
    evidence: str = Field(default="", max_length=MAX_TEXT)
    #: What the keyword heuristic proposed (kept for the audit trail), if it was used.
    suggested_status: ProvisionStatus | None = None
    #: Approved, time-bound exception for a missing/partial provision (D-071): why, by whom,
    #: until when. It does not make the clause present; it takes the gap out of the action
    #: list until the date passes.
    exception_reason: str = Field(default="", max_length=1000)
    exception_approver: str = Field(default="", max_length=200)
    exception_until: date | None = None

    def exception_valid(self, on: date) -> bool:
        return (self.status in (ProvisionStatus.MISSING, ProvisionStatus.PARTIAL)
                and bool(self.exception_reason) and self.exception_until is not None
                and self.exception_until >= on)

    @field_validator("provision_id")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in PROVISIONS_BY_ID:
            raise ValueError(f"unknown Art. 30 provision {value!r}")
        return value


class AssessmentEvent(BaseModel):
    """One entry of an assessment's history (append-only)."""

    model_config = ConfigDict(extra="forbid")

    at: datetime
    by: str = ""
    summary: str


class ContractAssessment(BaseModel):
    """Assessment of one contractual arrangement (B_02.01 record) against Art. 30."""

    model_config = ConfigDict(extra="forbid")

    contract_ref: str = Field(min_length=1, max_length=200)
    assessor: str = Field(default="", max_length=200)
    assessed_on: date | None = None
    document: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=MAX_TEXT)
    #: Subsequent arrangements (call-offs) inherit unassessed items from their overarching
    #: arrangement (B_02.01 c0030) when true.
    inherit: bool = True
    items: dict[str, ProvisionAssessment] = Field(default_factory=dict)
    history: list[AssessmentEvent] = Field(default_factory=list)

    def item(self, provision_id: str) -> ProvisionAssessment:
        return self.items.get(provision_id) or ProvisionAssessment(provision_id=provision_id)

    def set(self, provision_id: str, status: ProvisionStatus | str, clause_ref: str = "",
            evidence: str = "", suggested: ProvisionStatus | None = None,
            exception: tuple[str, str, date | None] | None = None) -> None:
        reason, approver, until = exception or ("", "", None)
        self.items[provision_id] = ProvisionAssessment(
            provision_id=provision_id,
            status=status if isinstance(status, ProvisionStatus) else ProvisionStatus.parse(status),
            clause_ref=clause_ref.strip(), evidence=evidence.strip(), suggested_status=suggested,
            exception_reason=reason.strip(), exception_approver=approver.strip(),
            exception_until=until)

    def assessed_items(self) -> dict[str, ProvisionAssessment]:
        return {k: v for k, v in self.items.items() if v.status is not ProvisionStatus.NOT_ASSESSED}


def describe_changes(old: ContractAssessment | None, new: ContractAssessment) -> str:
    """Short human summary of what changed between two versions of an assessment."""
    if old is None:
        n = len(new.assessed_items())
        return f"Assessment created ({n} provision(s) assessed)"
    changes: list[str] = []
    for pid in PROVISIONS_BY_ID:
        a, b = old.item(pid), new.item(pid)
        if a.status is not b.status:
            changes.append(f"{pid}: {a.status.value} → {b.status.value}")
        elif (a.clause_ref, a.evidence) != (b.clause_ref, b.evidence):
            changes.append(f"{pid}: evidence updated")
        if (a.exception_reason, a.exception_until) != (b.exception_reason, b.exception_until):
            changes.append(f"{pid}: exception until {b.exception_until} approved by "
                           f"{b.exception_approver or '?'}" if b.exception_reason
                           else f"{pid}: exception withdrawn")
    for name in ("assessor", "assessed_on", "document", "notes", "inherit"):
        if getattr(old, name) != getattr(new, name):
            changes.append(f"{name} updated")
    if not changes:
        return "Saved without changes"
    shown = "; ".join(changes[:6])
    return shown + (f" (+{len(changes) - 6} more)" if len(changes) > 6 else "")


class AssessmentBook(BaseModel):
    """All contract assessments of a register, keyed by arrangement reference number."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: str = Field(default=SCHEMA, alias="schema")
    toolkit_version: str = __version__
    assessments: dict[str, ContractAssessment] = Field(default_factory=dict)

    def get(self, contract_ref: str) -> ContractAssessment | None:
        return self.assessments.get(contract_ref)

    def __len__(self) -> int:
        return len(self.assessments)

    def save(self, assessment: ContractAssessment, by: str = "",
             summary: str | None = None, at: datetime | None = None) -> ContractAssessment:
        """Insert or replace an assessment and append a history entry."""
        old = self.assessments.get(assessment.contract_ref)
        history = list(old.history) if old else []
        history.append(AssessmentEvent(at=at or datetime.now(UTC), by=by,
                                       summary=summary or describe_changes(old, assessment)))
        stored = assessment.model_copy(update={"history": history})
        self.assessments[assessment.contract_ref] = stored
        return stored

    def remove(self, contract_ref: str) -> None:
        self.assessments.pop(contract_ref, None)

    def merge(self, other: AssessmentBook) -> int:
        """Add or replace assessments from ``other``; returns the number taken over."""
        for ref, a in other.assessments.items():
            self.assessments[ref] = a
        return len(other.assessments)

    # ------------------------------------------------------------------ JSON

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, indent=2, exclude_none=True)

    @classmethod
    def from_json(cls, text: str | bytes) -> AssessmentBook:
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise ValueError(f"not a contract assessment file (expected schema {SCHEMA!r})")
        return cls.model_validate(data)


# =========================================================================== Excel

SHEET = "Assessments"
HEADERS = ("contract_ref", "provision_id", "article", "provision", "status", "clause_ref",
           "evidence", "assessor", "assessed_on", "document", "exception_reason",
           "exception_approver", "exception_until")


def write_assessment_workbook(book: AssessmentBook, path: Path,
                              contracts: dict[str, bool] | None = None,
                              lang: str = "en") -> Path:
    """Write assessments as one row per contract × provision.

    ``contracts`` maps arrangement references to "supports a critical or important function";
    when given, every listed contract gets a row for every applicable provision (a working
    template for an assessment workshop), in addition to the contracts already in ``book``.
    """
    refs: dict[str, bool] = dict(contracts or {})
    for ref, existing in book.assessments.items():
        refs.setdefault(ref, any(PROVISIONS_BY_ID[p].scope.value == "critical"
                                 for p in existing.assessed_items()))
    rows: list[list[Any]] = []
    for ref in sorted(refs):
        a = book.get(ref)
        for p in PROVISIONS:
            if p.scope.value == "critical" and not refs[ref] and not (
                    a and p.id in a.assessed_items()):
                continue
            item = a.item(p.id) if a else None
            status = item.status if item else ProvisionStatus.NOT_ASSESSED
            rows.append([ref, p.id, p.article, p.title(lang),
                         "" if status is ProvisionStatus.NOT_ASSESSED else status.value,
                         item.clause_ref if item else "", item.evidence if item else "",
                         a.assessor if a else "",
                         a.assessed_on.isoformat() if a and a.assessed_on else "",
                         a.document if a else "",
                         item.exception_reason if item else "",
                         item.exception_approver if item else "",
                         item.exception_until.isoformat() if item and item.exception_until
                         else ""])
    with SheetBook(path) as wb:
        wb.sheet(SHEET, HEADERS, rows, (16, 12, 22, 60, 12, 16, 60, 18, 14, 30, 40, 20, 14),
                 lists={4: ("present", "partial", "missing")}, freeze_cols=2)
        wb.text_sheet("README", (
            "DORA Art. 30 contract assessment workbook",
            f"Generated by dora-roi-toolkit {__version__}.",
            "One row per contractual arrangement (B_02.01 c0010) and checklist provision.",
            "status: present | partial | missing (empty = not assessed).",
            "clause_ref: where the provision is found in the contract (e.g. 'Clause 14.2').",
            "evidence: short note or quotation supporting the status.",
            "exception_reason / exception_approver / exception_until (YYYY-MM-DD): an approved, "
            "time-bound exception for a missing or partial provision.",
            "Re-import with `roi contracts assess REGISTER --assessments THIS_FILE` or in the "
            "workbench (Art. 30 contracts → Import assessments).",
        ))
    return path


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def read_assessment_workbook(path: Path) -> tuple[AssessmentBook, list[str]]:
    """Read an assessment workbook; returns the book and a list of problems (row-level)."""
    try:
        sheets = dict(iter_sheets(path))
    except SpreadsheetError as exc:
        raise ValueError(str(exc)) from exc
    rows_all = sheets.get(SHEET) or next(iter(sheets.values()), [])
    title = SHEET if SHEET in sheets else next(iter(sheets), "?")
    header = [_cell_text(c).casefold() for c in (rows_all[0] if rows_all else [])]
    missing = [h for h in ("contract_ref", "provision_id", "status") if h not in header]
    if missing:
        raise ValueError(f"sheet {title!r} lacks column(s): {', '.join(missing)}")
    col = {h: header.index(h) for h in HEADERS if h in header}
    book = AssessmentBook()
    problems: list[str] = []
    for number, values in enumerate(rows_all[1:], start=2):
        def get(name: str, vals: list[Any] = values) -> str:
            i = col.get(name)
            return _cell_text(vals[i]) if i is not None and i < len(vals) else ""

        ref, pid = get("contract_ref"), get("provision_id")
        if not ref and not pid:
            continue
        if pid not in PROVISIONS_BY_ID:
            problems.append(f"row {number}: unknown provision {pid!r}")
            continue
        if not ref:
            problems.append(f"row {number}: contract_ref is empty")
            continue
        try:
            status = ProvisionStatus.parse(get("status"))
        except ValueError as exc:
            problems.append(f"row {number}: {exc}")
            continue
        if status is ProvisionStatus.NOT_ASSESSED and not get("evidence") \
                and not get("clause_ref"):
            continue
        found = book.assessments.get(ref)
        if found is None:
            assessed_on: date | None = None
            if get("assessed_on"):
                try:
                    assessed_on = date.fromisoformat(get("assessed_on")[:10])
                except ValueError:
                    problems.append(f"row {number}: assessed_on is not a date (YYYY-MM-DD)")
            found = ContractAssessment(contract_ref=ref[:200], assessor=get("assessor")[:200],
                                       assessed_on=assessed_on,
                                       document=get("document")[:300])
            book.assessments[ref] = found
        until: date | None = None
        if get("exception_until"):
            try:
                until = date.fromisoformat(get("exception_until")[:10])
            except ValueError:
                problems.append(f"row {number}: exception_until is not a date (YYYY-MM-DD)")
        found.set(pid, status, get("clause_ref")[:200], get("evidence")[:MAX_TEXT],
                  exception=(get("exception_reason")[:1000], get("exception_approver")[:200],
                             until))
    return book, problems


def load_assessments(path: Path) -> tuple[AssessmentBook, list[str]]:
    """Load assessments from ``.json`` or ``.xlsx``."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return AssessmentBook.from_json(path.read_bytes()), []
    if suffix in (".xlsx", ".xlsm"):
        return read_assessment_workbook(path)
    raise ValueError(f"unsupported assessment file {path.name!r} (use .json or .xlsx)")
