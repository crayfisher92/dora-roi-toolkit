"""Keyword/heuristic pre-assessment of a contract text against the Art. 30 checklist.

**These are suggestions for human review, never conclusions.** A clause can be present in
wording the patterns do not know, and a keyword can appear in a sentence that says the
opposite ("the provider shall *not* be obliged to …"). The result therefore uses its own
vocabulary – *likely present*, *possibly partial*, *not found* – and the workbench shows
every suggestion with the matched passage and its clause number so the reviewer can confirm
or overrule it. No external service, AI model or network call is involved (D-051).

Method, per provision (:class:`~dora_roi.contracts.provisions.Concept` = an idea the clause
must express, as EN/DE patterns):

* the text is split into clauses at headings ("Clause 14.2", "§ 12", "Ziffer 7.3", "12.3");
* all concepts found *in the same clause* → *likely present*; some concepts found → *possibly
  partial*; none anywhere → *not found*;
* a negation shortly before a match ("not", "no", "nicht", "kein", "excluded") downgrades the
  match and is reported;
* the passage around the first match and its clause number are returned as evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from dora_roi.contracts.model import ContractAssessment, ProvisionStatus
from dora_roi.contracts.provisions import Concept, Provision, applicable

SNIPPET = 220
_NEGATION = re.compile(
    r"\b(not|no|never|without|excluded|exclude[sd]?|nicht|kein\w*|ohne|ausgeschlossen)\b",
    re.IGNORECASE)
_HEADING = re.compile(
    r"^[ \t]*(?P<ref>(?i:§|Art\.|Article|Artikel|Clause|Section|Ziffer|Ziff\.|Nr\.|Schedule|"
    r"Annex|Anlage)\s*\d+(?:\.\d+)*[a-z]?|\d+(?:\.\d+){0,3})[.)]?[ \t]+"
    r"(?=[A-ZÄÖÜ\"„“(])", re.MULTILINE)


class Suggestion(StrEnum):
    LIKELY_PRESENT = "likely_present"
    POSSIBLY_PARTIAL = "possibly_partial"
    NOT_FOUND = "not_found"

    @property
    def status(self) -> ProvisionStatus:
        """Status pre-selected in the review form (the reviewer confirms or changes it)."""
        return {"likely_present": ProvisionStatus.PRESENT,
                "possibly_partial": ProvisionStatus.PARTIAL,
                "not_found": ProvisionStatus.MISSING}[self.value]


@dataclass(frozen=True)
class Match:
    concept: str
    start: int
    text: str
    negated: bool


@dataclass
class ProvisionSuggestion:
    provision: Provision
    suggestion: Suggestion
    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    snippet: str = ""
    clause_ref: str = ""
    negated: bool = False

    @property
    def confidence(self) -> str:
        """``high`` when every concept matched without negation, else ``low``."""
        if self.suggestion is Suggestion.LIKELY_PRESENT and not self.negated:
            return "high"
        return "low"

    def evidence(self, lang: str = "en") -> str:
        """Evidence note pre-filled in the form (clearly marked as machine-generated)."""
        de = lang == "de"
        tag = "[Vorschlag – prüfen]" if de else "[Suggestion – review]"
        if self.suggestion is Suggestion.NOT_FOUND:
            lead = ("Keine passende Formulierung gefunden für" if de
                    else "No matching wording found for")
            return f"{tag} {lead}: " + ", ".join(self.missing) + "."
        note = f"{tag} {'Gefunden' if de else 'Matched'}: {', '.join(self.found)}"
        if self.missing:
            note += f"; {'nicht gefunden' if de else 'not found'}: {', '.join(self.missing)}"
        if self.negated:
            note += ("; Verneinung in der Nähe – Wortlaut prüfen" if de
                     else "; negation near the match – check the wording")
        return note + f". “{self.snippet}”"


@dataclass
class SuggestionResult:
    items: list[ProvisionSuggestion]
    words: int
    headings: int

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in Suggestion}
        for i in self.items:
            out[i.suggestion.value] += 1
        return out

    def by_id(self) -> dict[str, ProvisionSuggestion]:
        return {i.provision.id: i for i in self.items}


def _headings(text: str) -> list[tuple[int, str]]:
    return [(m.start(), re.sub(r"\s+", " ", m.group("ref")).strip())
            for m in _HEADING.finditer(text)]


def _clause_at(headings: list[tuple[int, str]], pos: int) -> str:
    ref = ""
    for start, label in headings:
        if start > pos:
            break
        ref = label
    return ref


def _snippet(text: str, start: int, end: int) -> str:
    a = max(0, start - SNIPPET // 2)
    b = min(len(text), end + SNIPPET // 2)
    cut = re.sub(r"\s+", " ", text[a:b]).strip()
    return ("… " if a > 0 else "") + cut + (" …" if b < len(text) else "")


def _find(concept: Concept, text: str, offset: int = 0) -> Match | None:
    first_negated: Match | None = None
    for m in concept.regex.finditer(text):
        window = text[max(0, m.start() - 60): m.start()]
        sentence = re.split(r"[.;:\n]", window)[-1]
        negated = bool(_NEGATION.search(sentence))
        found = Match(concept.name, offset + m.start(), m.group(0), negated)
        if not negated:
            return found
        first_negated = first_negated or found
    return first_negated


def _top_level(ref: str) -> bool:
    return "." not in ref.rstrip(".")


def _segments(text: str, headings: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """``(start, end, clause ref)`` of every top-level clause (sub-clauses such as 6.1 and 6.2
    belong to clause 6); text before the first heading is a segment of its own."""
    tops = [(pos, ref) for pos, ref in headings if _top_level(ref)] or headings
    bounds = [(0, "")] + [(pos, ref) for pos, ref in tops if pos > 0]
    out = []
    for i, (start, ref) in enumerate(bounds):
        end = bounds[i + 1][0] if i + 1 < len(bounds) else len(text)
        if end > start:
            out.append((start, end, ref))
    return out


def suggest_provision(provision: Provision, text: str,
                      headings: list[tuple[int, str]] | None = None) -> ProvisionSuggestion:
    heads = headings if headings is not None else _headings(text)
    names = [c.name for c in provision.concepts]
    best: tuple[int, int, list[Match], str] | None = None
    for start, end, ref in _segments(text, heads):
        chunk = text[start:end]
        found = [m for c in provision.concepts if (m := _find(c, chunk, start)) is not None]
        if not found:
            continue
        score = (sum(1 for m in found if not m.negated), len(found))
        if best is None or score > best[:2]:
            best = (*score, found, ref)
    if best is None:
        return ProvisionSuggestion(provision, Suggestion.NOT_FOUND, [], names)
    matches = best[2]
    found_names = [m.concept for m in matches]
    missing = [n for n in names if n not in found_names]
    negated = any(m.negated for m in matches)
    complete = not missing and not negated
    suggestion = Suggestion.LIKELY_PRESENT if complete else Suggestion.POSSIBLY_PARTIAL
    anchor = min(matches, key=lambda m: (m.negated, m.start))
    return ProvisionSuggestion(
        provision, suggestion, found_names, missing,
        _snippet(text, anchor.start, anchor.start + len(anchor.text)),
        _clause_at(heads, anchor.start), negated)


def suggest(text: str, critical: bool = True) -> SuggestionResult:
    """Suggest a status for every applicable provision."""
    heads = _headings(text)
    items = [suggest_provision(p, text, heads) for p in applicable(critical)]
    return SuggestionResult(items, len(text.split()), len(heads))


def apply_suggestions(assessment: ContractAssessment, result: SuggestionResult,
                      overwrite: bool = False, lang: str = "en") -> ContractAssessment:
    """Return a copy of ``assessment`` pre-filled with suggestions (unsaved draft).

    Items the reviewer already assessed are kept unless ``overwrite``. Each pre-filled item
    records ``suggested_status`` so that the audit trail shows what the heuristic proposed.
    """
    draft = assessment.model_copy(deep=True)
    for s in result.items:
        current = draft.items.get(s.provision.id)
        if current is not None and current.status is not ProvisionStatus.NOT_ASSESSED \
                and not overwrite:
            draft.items[s.provision.id] = current.model_copy(
                update={"suggested_status": s.suggestion.status})
            continue
        draft.set(s.provision.id, s.suggestion.status, s.clause_ref, s.evidence(lang),
                  suggested=s.suggestion.status)
    return draft
