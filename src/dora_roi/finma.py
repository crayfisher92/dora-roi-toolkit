"""Swiss angle: which RoI data covers which FINMA requirement, and what is missing.

A Swiss banking group with EU subsidiaries maintains the DORA Register of Information for its
EU entities and, in Switzerland, an **outsourcing inventory** under FINMA Circular 2018/3
"Outsourcing" and **critical-function and ICT resilience documentation** under FINMA Circular
2023/1 "Operational risks and resilience – banks". This module maps each FINMA requirement to
the RoI columns (and the Art. 30 contract checklist and incident log of this toolkit) that
evidence it, states the coverage *by design* (full / partial / none), measures how complete
that data is in a given register, and lists what has to be maintained in addition – so that
one dataset serves both regimes.

The requirement texts paraphrase the circulars from the authors' knowledge; margin numbers
are deliberately not cited (A-FINMA-01). The mapping is an interpretation, not FINMA
guidance.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from dora_roi.contracts.analysis import Portfolio
from dora_roi.contracts.model import ProvisionStatus
from dora_roi.incidents.classify import Outcome, classify
from dora_roi.incidents.model import IncidentLog
from dora_roi.model import TEMPLATES_BY_CODE, RegisterOfInformation
from dora_roi.model.refdata import EEA_COUNTRIES

OUTSOURCING = "FINMA Circ. 2018/3"
OPRISK = "FINMA Circ. 2023/1"
FULL_THRESHOLD = 0.95


class Coverage(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"

    @property
    def rank(self) -> int:
        return {"full": 0, "partial": 1, "none": 2}[self.value]


#: Applicability of conditional columns: only these records are expected to have a value.
CONDITIONS: dict[str, Callable[[Any], bool]] = {
    "critical": lambda r: getattr(r, "is_critical", False),
    "storage": lambda r: getattr(r, "data_storage", None) is True,
    "subcontractor": lambda r: (getattr(r, "rank", None) or 0) > 1,
}


@dataclass(frozen=True)
class FieldRef:
    template: str
    column: str
    #: Key of :data:`CONDITIONS` for conditional columns (e.g. RTO only for critical functions).
    when: str | None = None

    @property
    def label(self) -> str:
        spec = TEMPLATES_BY_CODE[self.template].column_by_code(self.column)
        return spec.label if spec else self.column

    def __str__(self) -> str:
        return f"{self.template} {self.column}"


def F(ref: str, when: str | None = None) -> FieldRef:  # noqa: N802 - short constructor
    template, column = ref.split()
    return FieldRef(template, column, when)


@dataclass(frozen=True)
class FinmaRequirement:
    id: str
    circular: str
    topic_en: str
    topic_de: str
    title_en: str
    title_de: str
    coverage: Coverage
    fields: tuple[FieldRef, ...]
    gap_en: str
    gap_de: str
    art30: tuple[str, ...] = ()
    incidents: bool = False

    def topic(self, lang: str = "en") -> str:
        return self.topic_de if lang == "de" else self.topic_en

    def title(self, lang: str = "en") -> str:
        return self.title_de if lang == "de" else self.title_en

    def gap(self, lang: str = "en") -> str:
        return self.gap_de if lang == "de" else self.gap_en


R = FinmaRequirement
FULL, PARTIAL, NONE = Coverage.FULL, Coverage.PARTIAL, Coverage.NONE

REQUIREMENTS: tuple[FinmaRequirement, ...] = (
    # ------------------------------------------------------------------ 2018/3 outsourcing
    R("FIN-OS-01", OUTSOURCING, "Inventory", "Inventar",
      "Description of each outsourced function", "Beschreibung jeder ausgelagerten Funktion",
      PARTIAL, (F("B_06.01 c0030"), F("B_02.02 c0050"), F("B_02.02 c0060")),
      "The RoI lists ICT services, not outsourcings in the FINMA sense: flag which arrangements "
      "are outsourcings and add non-ICT outsourcings (e.g. cash handling, back office).",
      "Das RoI erfasst IKT-Dienstleistungen, nicht Auslagerungen im Sinne der FINMA: "
      "Auslagerungen kennzeichnen und Nicht-IKT-Auslagerungen (z. B. Bargeldlogistik, "
      "Backoffice) ergänzen."),
    R("FIN-OS-02", OUTSOURCING, "Inventory", "Inventar",
      "Service provider: name and domicile", "Dienstleister: Name und Sitz",
      FULL, (F("B_05.01 c0050"), F("B_05.01 c0080"), F("B_05.01 c0010")),
      "—", "—"),
    R("FIN-OS-03", OUTSOURCING, "Inventory", "Inventar",
      "Sub-providers of significant functions", "Unterakkordanten wesentlicher Funktionen",
      FULL, (F("B_05.02 c0030"), F("B_05.02 c0050"),
              F("B_05.02 c0060", "subcontractor")),
      "—", "—"),
    R("FIN-OS-04", OUTSOURCING, "Inventory", "Inventar",
      "Service recipient within the group", "Leistungsempfänger in der Gruppe",
      FULL, (F("B_02.02 c0020"), F("B_04.01 c0020"), F("B_01.02 c0010")),
      "Swiss group entities are outside the DORA scope: add them to B_01.02 for the group "
      "view and exclude them from the supervisory xBRL-CSV export.",
      "Schweizer Gruppengesellschaften liegen ausserhalb von DORA: für die Gruppensicht in "
      "B_01.02 aufnehmen und vom aufsichtlichen xBRL-CSV-Export ausnehmen."),
    R("FIN-OS-05", OUTSOURCING, "Inventory", "Inventar",
      "Responsible person or unit in the bank", "Verantwortliche Person oder Stelle in der Bank",
      NONE, (),
      "Not part of the RoI. Maintain a business owner / responsible unit per arrangement.",
      "Nicht Teil des RoI. Je Vereinbarung eine verantwortliche Stelle bzw. einen Owner "
      "pflegen."),
    R("FIN-OS-06", OUTSOURCING, "Definitions / inventory", "Begriffe / Inventar",
      "Assessment whether the outsourced function is significant",
      "Beurteilung, ob die ausgelagerte Funktion wesentlich ist",
      PARTIAL, (F("B_06.01 c0050"), F("B_06.01 c0060", "critical")),
      "DORA 'critical or important function' and FINMA 'significant function' are similar but "
      "not identical: record the FINMA significance assessment separately where it differs.",
      "„Kritische oder wichtige Funktion“ (DORA) und „wesentliche Funktion“ (FINMA) sind "
      "ähnlich, aber nicht identisch: abweichende FINMA-Beurteilung separat erfassen."),
    R("FIN-OS-07", OUTSOURCING, "Inventory / contract", "Inventar / Vertrag",
      "Term of the outsourcing and notice periods", "Laufzeit und Kündigungsfristen",
      FULL, (F("B_02.02 c0070"), F("B_02.02 c0080"), F("B_02.02 c0100"), F("B_02.02 c0110")),
      "—", "—"),
    R("FIN-OS-08", OUTSOURCING, "Selection, instruction and monitoring",
      "Auswahl, Instruktion und Kontrolle",
      "Due diligence before selection and ongoing monitoring of the provider",
      "Sorgfältige Auswahl und laufende Überwachung des Dienstleisters",
      PARTIAL, (F("B_07.01 c0070"),),
      "Only the last audit date is in the RoI. Keep due-diligence and monitoring evidence "
      "(date, result, owner).",
      "Nur das Datum der letzten Prüfung steht im RoI. Nachweise zu Due Diligence und "
      "Überwachung (Datum, Ergebnis, Verantwortliche) führen."),
    R("FIN-OS-09", OUTSOURCING, "Security", "Sicherheit",
      "Security and confidentiality, incl. bank-client confidentiality",
      "Sicherheit und Vertraulichkeit, inkl. Bankkundengeheimnis",
      PARTIAL, (F("B_02.02 c0170", "storage"),),
      "Data sensitivity and the Art. 30(2)(c) clause cover security in general; document "
      "client identifying data (CID) and the bank-client confidentiality assessment for "
      "providers abroad.",
      "Datensensitivität und die Klausel nach Art. 30 Abs. 2 lit. c decken Sicherheit "
      "allgemein ab; kundenidentifizierende Daten (CID) und die Beurteilung des "
      "Bankkundengeheimnisses bei Dienstleistern im Ausland dokumentieren.",
      art30=("30.2.c",)),
    R("FIN-OS-10", OUTSOURCING, "Security", "Sicherheit",
      "Business continuity of outsourced significant functions",
      "Geschäftsfortführung ausgelagerter wesentlicher Funktionen",
      PARTIAL, (F("B_06.01 c0080", "critical"), F("B_06.01 c0090", "critical")),
      "RTO/RPO and the contract clause on tested contingency plans are covered; keep the "
      "provider's BCP test results.",
      "RTO/RPO und die Vertragsklausel zu getesteten Notfallplänen sind abgedeckt; "
      "Testergebnisse des Dienstleisters ablegen.",
      art30=("30.3.c",)),
    R("FIN-OS-11", OUTSOURCING, "Audit and supervision", "Prüfung und Aufsicht",
      "Audit and information rights for the bank, its audit firm and FINMA",
      "Prüf- und Einsichtsrechte für Bank, Prüfgesellschaft und FINMA",
      PARTIAL, (),
      "The Art. 30(3)(e) clauses grant rights to the 'competent authority' (an EU authority): "
      "check that FINMA and the bank's audit firm are named explicitly.",
      "Die Klauseln nach Art. 30 Abs. 3 lit. e berechtigen die „zuständige Behörde“ (EU): "
      "prüfen, dass FINMA und die Prüfgesellschaft ausdrücklich genannt sind.",
      art30=("30.3.e.i", "30.3.e.iii")),
    R("FIN-OS-12", OUTSOURCING, "Outsourcing abroad", "Auslagerung ins Ausland",
      "Abroad: enforceable audit rights, restructuring/resolution, access to data from "
      "Switzerland", "Ausland: durchsetzbare Prüfrechte, Sanierung/Abwicklung, Datenzugriff "
      "aus der Schweiz",
      PARTIAL, (F("B_02.02 c0120"), F("B_02.02 c0130"), F("B_02.02 c0150", "storage")),
      "Governing law and locations are in the RoI; document that information needed for "
      "restructuring or resolution remains accessible from Switzerland.",
      "Anwendbares Recht und Standorte stehen im RoI; dokumentieren, dass für Sanierung oder "
      "Abwicklung nötige Informationen aus der Schweiz zugänglich bleiben.",
      art30=("30.2.d", "30.3.e.i")),
    R("FIN-OS-13", OUTSOURCING, "Contract", "Vertrag",
      "Written contract: sub-outsourcing conditions, termination, orderly transfer",
      "Schriftlicher Vertrag: Bedingungen für Unterauslagerung, Kündigung, geordnete Übergabe",
      PARTIAL, (F("B_07.01 c0080"),),
      "Covered by the Art. 30 checklist; FINMA may expect prior consent to sub-outsourcing of "
      "significant functions, which DORA does not require in every case.",
      "Durch die Art.-30-Checkliste abgedeckt; die FINMA kann eine vorgängige Zustimmung zur "
      "Unterauslagerung wesentlicher Funktionen erwarten, die DORA nicht in jedem Fall "
      "verlangt.",
      art30=("30.1", "30.2.a.2", "30.2.h", "30.3.f.i", "30.3.f.ii")),
    R("FIN-OS-14", OUTSOURCING, "Intra-group outsourcing", "Gruppeninterne Auslagerung",
      "Intra-group outsourcings identified", "Gruppeninterne Auslagerungen identifiziert",
      FULL, (F("B_03.03 c0020"), F("B_02.03 c0020")),
      "—", "—"),
    # ------------------------------------------------------------------ 2023/1 resilience
    R("FIN-OR-01", OPRISK, "Operational resilience", "Operationelle Resilienz",
      "Inventory of critical functions", "Inventar der kritischen Funktionen",
      PARTIAL, (F("B_06.01 c0010"), F("B_06.01 c0030"), F("B_06.01 c0050")),
      "FINMA critical functions (disruption endangers the bank or the functioning of the "
      "financial market) are not the same set as DORA critical or important functions: "
      "map them explicitly.",
      "Kritische Funktionen nach FINMA (Störung gefährdet Bank oder Finanzmarkt) sind nicht "
      "deckungsgleich mit kritischen oder wichtigen Funktionen nach DORA: ausdrücklich "
      "zuordnen."),
    R("FIN-OR-02", OPRISK, "Operational resilience", "Operationelle Resilienz",
      "Tolerance for disruption per critical function",
      "Unterbrechungstoleranz je kritischer Funktion",
      PARTIAL, (F("B_06.01 c0080", "critical"),),
      "The RTO approximates, but is not, a tolerance for disruption (which also covers data "
      "loss and service level): define tolerances per FINMA critical function.",
      "Die RTO nähert sich der Unterbrechungstoleranz an, ist es aber nicht (diese umfasst "
      "auch Datenverlust und Service-Niveau): Toleranzen je kritischer Funktion festlegen."),
    R("FIN-OR-03", OPRISK, "Operational resilience", "Operationelle Resilienz",
      "Mapping of critical functions to resources, incl. third parties",
      "Abbildung kritischer Funktionen auf Ressourcen, inkl. Dritter",
      PARTIAL, (F("B_02.02 c0050"), F("B_02.02 c0030"), F("B_05.02 c0030")),
      "Third-party dependencies are mapped; add people, premises, internal IT and data.",
      "Abhängigkeiten von Dritten sind abgebildet; Personal, Räumlichkeiten, interne IT und "
      "Daten ergänzen."),
    R("FIN-OR-04", OPRISK, "ICT risk management", "IKT-Risikomanagement",
      "ICT inventory with dependencies on third parties",
      "IKT-Inventar mit Abhängigkeiten von Dritten",
      PARTIAL, (F("B_02.02 c0060"), F("B_05.02 c0050")),
      "Covers ICT services bought from third parties, not the bank's own ICT assets.",
      "Deckt eingekaufte IKT-Dienstleistungen ab, nicht die eigenen IKT-Assets der Bank."),
    R("FIN-OR-05", OPRISK, "Critical data", "Kritische Daten",
      "Critical data: location and protection, also at third parties",
      "Kritische Daten: Ort und Schutz, auch bei Dritten",
      PARTIAL, (F("B_02.02 c0140"), F("B_02.02 c0150", "storage"), F("B_02.02 c0160"),
                F("B_02.02 c0170", "storage")),
      "Storage location and sensitivity are reported per service; identify which data is "
      "critical in the FINMA sense.",
      "Speicherort und Sensitivität sind je Dienstleistung erfasst; festlegen, welche Daten "
      "im Sinne der FINMA kritisch sind."),
    R("FIN-OR-06", OPRISK, "Business continuity management", "Geschäftsfortführung (BCM)",
      "Business impact analysis, recovery objectives and tested plans",
      "Business-Impact-Analyse, Wiederherstellungsziele und getestete Pläne",
      PARTIAL, (F("B_06.01 c0080", "critical"), F("B_06.01 c0090", "critical"),
                F("B_06.01 c0100")),
      "Keep the BIA and test evidence; the RoI only holds the resulting RTO/RPO and impact.",
      "BIA und Testnachweise führen; das RoI enthält nur die resultierenden RTO/RPO und "
      "Auswirkungen.",
      art30=("30.3.c",)),
    R("FIN-OR-07", OPRISK, "ICT / cyber incident management",
      "IKT- und Cyber-Vorfallmanagement",
      "Incident management and reporting of cyber attacks to FINMA",
      "Vorfallmanagement und Meldung von Cyber-Angriffen an die FINMA",
      PARTIAL, (),
      "The incident log covers classification and DORA deadlines; FINMA reporting of cyber "
      "attacks follows its own guidance and time limits – track them separately.",
      "Das Vorfallverzeichnis deckt Klassifizierung und DORA-Fristen ab; Meldungen von "
      "Cyber-Angriffen an die FINMA folgen eigenen Vorgaben und Fristen – separat verfolgen.",
      incidents=True),
    R("FIN-OR-08", OPRISK, "Operational resilience", "Operationelle Resilienz",
      "Substitutability and exit for critical third-party dependencies",
      "Ersetzbarkeit und Ausstieg bei kritischen Abhängigkeiten von Dritten",
      PARTIAL, (F("B_07.01 c0050"), F("B_07.01 c0080"), F("B_07.01 c0110")),
      "Substitutability and exit plans are reported; test them in severe but plausible "
      "scenarios.",
      "Ersetzbarkeit und Exit-Pläne sind erfasst; in schweren, aber plausiblen Szenarien "
      "testen.",
      art30=("30.3.f.i",)),
    R("FIN-OR-09", OPRISK, "Operational resilience", "Operationelle Resilienz",
      "Scenario testing of operational resilience", "Szenariotests der operationellen Resilienz",
      NONE, (),
      "Not part of the RoI. Plan and document severe but plausible scenario tests per "
      "critical function.",
      "Nicht Teil des RoI. Szenariotests je kritischer Funktion planen und dokumentieren."),
    R("FIN-OR-10", OPRISK, "ICT risk management", "IKT-Risikomanagement",
      "Contractual security requirements for ICT providers",
      "Vertragliche Sicherheitsanforderungen an IKT-Dienstleister",
      PARTIAL, (),
      "Evidenced by the Art. 30 clauses on data security, security measures and training.",
      "Durch die Art.-30-Klauseln zu Datensicherheit, Sicherheitsmassnahmen und Schulung "
      "belegt.",
      art30=("30.2.c", "30.3.c", "30.2.i")),
)


# =========================================================================== evaluation


@dataclass
class RequirementStatus:
    requirement: FinmaRequirement
    effective: Coverage
    #: Share of relevant records with every mapped RoI field filled (None: no RoI fields).
    completeness: float | None
    #: Share of arrangements supporting critical functions whose mapped Art. 30 provisions are
    #: all assessed as present (None: no Art. 30 link or nothing assessed).
    art30_share: float | None
    incidents_classified: float | None = None
    #: Fill rate per mapped field (fields without applicable records are omitted).
    field_fill: dict[str, float] = field(default_factory=dict)


@dataclass
class SwissContext:
    entity_countries: dict[str, int]
    swiss_entities: int
    swiss_providers: list[tuple[str, str]]
    swiss_spend_share: float
    swiss_law_arrangements: int
    swiss_data_arrangements: int
    providers_outside_eea_ch: int


@dataclass
class FinmaView:
    statuses: list[RequirementStatus]
    context: SwissContext

    def counts(self, circular: str | None = None) -> dict[str, int]:
        out = {c.value: 0 for c in Coverage}
        for s in self.statuses:
            if circular is None or s.requirement.circular == circular:
                out[s.effective.value] += 1
        return out

    def by_circular(self, circular: str) -> list[RequirementStatus]:
        return [s for s in self.statuses if s.requirement.circular == circular]

    @property
    def coverage_score(self) -> float:
        """Full = 1, partial = 0.5, none = 0 – averaged over all requirements."""
        weights = {Coverage.FULL: 1.0, Coverage.PARTIAL: 0.5, Coverage.NONE: 0.0}
        return sum(weights[s.effective] for s in self.statuses) / len(self.statuses)


def fill_rate(register: RegisterOfInformation, ref: FieldRef) -> float | None:
    """Share of applicable records with a value; ``None`` when no record is applicable."""
    model = TEMPLATES_BY_CODE[ref.template]
    spec = model.column_by_code(ref.column)
    if spec is None:
        raise KeyError(f"{ref.template} has no column {ref.column}")
    records = register.records(ref.template)
    if ref.when is not None:
        records = [r for r in records if CONDITIONS[ref.when](r)]
    if not records:
        return None
    return sum(1 for r in records if getattr(r, spec.attr) is not None) / len(records)


def _art30_share(req: FinmaRequirement, portfolio: Portfolio | None) -> float | None:
    if not req.art30 or portfolio is None:
        return None
    relevant = [c for c in portfolio.contracts if c.context.critical] or portfolio.contracts
    assessed = [c for c in relevant if c.assessed]
    if not assessed:
        return None
    ok = 0
    for c in relevant:
        items = {i.provision.id: i.status for i in c.items}
        if all(items.get(pid, ProvisionStatus.PRESENT) is ProvisionStatus.PRESENT
               for pid in req.art30) and c.assessed:
            ok += 1
    return ok / len(relevant)


def evaluate_finma(register: RegisterOfInformation, portfolio: Portfolio | None = None,
                   incidents: IncidentLog | None = None,
                   now: datetime | None = None) -> FinmaView:
    """Evaluate every FINMA requirement against a register (and optional programme data)."""
    moment = now or datetime.now(UTC)
    statuses: list[RequirementStatus] = []
    for req in REQUIREMENTS:
        rates = {str(f): fill_rate(register, f) for f in req.fields}
        fill = {k: v for k, v in rates.items() if v is not None}
        completeness = min(fill.values()) if fill else None
        share = _art30_share(req, portfolio)
        classified: float | None = None
        if req.incidents and incidents is not None and len(incidents):
            done = sum(1 for i in incidents.incidents.values()
                       if classify(i, moment).outcome is not Outcome.UNDETERMINED)
            classified = done / len(incidents)
        evidence = [v for v in (completeness, share, classified) if v is not None]
        if req.coverage is Coverage.NONE:
            effective = Coverage.NONE
        elif req.coverage is Coverage.FULL:
            # nothing applicable to measure (e.g. no intra-group arrangements) keeps the design
            effective = (Coverage.FULL if (completeness is None and not register.is_empty())
                         or (completeness or 0) >= FULL_THRESHOLD else Coverage.PARTIAL)
        else:
            effective = Coverage.PARTIAL if any(v > 0 for v in evidence) else Coverage.NONE
        statuses.append(RequirementStatus(req, effective, completeness, share, classified,
                                          fill))
    return FinmaView(statuses, swiss_context(register))


def swiss_context(register: RegisterOfInformation) -> SwissContext:
    countries: dict[str, int] = {}
    for e in register.b_01_02:
        if e.country:
            countries[e.country] = countries.get(e.country, 0) + 1
    providers = sorted(((p.provider_code or "", p.legal_name or p.provider_code or "")
                        for p in register.b_05_01 if p.hq_country == "CH"),
                       key=lambda x: x[1].casefold())
    swiss_codes = {code for code, _ in providers}
    spend = {c.contract_ref: c.annual_cost or Decimal(0) for c in register.b_02_01
             if c.contract_ref}
    total = sum(spend.values(), Decimal(0))
    swiss_refs = {s.contract_ref for s in register.b_02_02 if s.provider_code in swiss_codes}
    swiss = sum((spend.get(r or "", Decimal(0)) for r in swiss_refs), Decimal(0))
    return SwissContext(
        entity_countries=dict(sorted(countries.items())),
        swiss_entities=countries.get("CH", 0),
        swiss_providers=providers,
        swiss_spend_share=float(swiss / total) if total else 0.0,
        swiss_law_arrangements=len({s.contract_ref for s in register.b_02_02
                                    if s.governing_law_country == "CH"}),
        swiss_data_arrangements=len({s.contract_ref for s in register.b_02_02
                                     if "CH" in (s.data_location_storage,
                                                 s.data_location_processing)}),
        providers_outside_eea_ch=sum(1 for p in register.b_05_01 if p.hq_country
                                     and p.hq_country not in EEA_COUNTRIES
                                     and p.hq_country != "CH"),
    )


def mapping_markdown(lang: str = "en") -> str:
    """``docs/FINMA_MAPPING.md``: the static mapping (coverage by design)."""
    de = lang == "de"
    lines = [
        "# FINMA mapping" if not de else "# FINMA-Zuordnung",
        "",
        "<!-- Generated by `python -m dora_roi.docs`; do not edit by hand. -->",
        "",
        "How the DORA Register of Information (plus the Art. 30 contract assessments and the "
        "incident log of this toolkit) covers the outsourcing inventory of FINMA Circular "
        "2018/3 and the critical-function and ICT resilience documentation of FINMA Circular "
        "2023/1, and what a Swiss group has to maintain in addition. *Coverage by design*; the "
        "workbench (*Switzerland (FINMA)*) and `roi finma` also measure how complete the data "
        "is in a given register. Paraphrased and interpretive – see "
        "[ASSUMPTIONS.md](ASSUMPTIONS.md) (A-FINMA-*).",
        "",
    ]
    for circ, title in ((OUTSOURCING, "FINMA Circular 2018/3 – Outsourcing"),
                        (OPRISK, "FINMA Circular 2023/1 – Operational risks and resilience")):
        reqs = [r for r in REQUIREMENTS if r.circular == circ]
        lines += [f"## {title}", "", "| ID | Topic | Requirement | Coverage | RoI fields | "
                  "Art. 30 / incidents | What is missing |", "|---|---|---|---|---|---|---|"]
        for r in reqs:
            other = ", ".join(f"`{p}`" for p in r.art30) + (
                ("; " if r.art30 else "") + "incident log" if r.incidents else "")
            lines.append(f"| {r.id} | {r.topic(lang)} | {r.title(lang)} | {r.coverage.value} | "
                         f"{', '.join(str(f) for f in r.fields) or '—'} | {other or '—'} | "
                         f"{r.gap(lang)} |")
        lines.append("")
    counts = {c.value: sum(1 for r in REQUIREMENTS if r.coverage is c) for c in Coverage}
    lines += [f"**{len(REQUIREMENTS)} requirements:** {counts['full']} fully, "
              f"{counts['partial']} partially and {counts['none']} not covered by design.", ""]
    return "\n".join(lines)
