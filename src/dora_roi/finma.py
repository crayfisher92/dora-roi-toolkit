"""Swiss angle: which RoI data covers which FINMA requirement, and what is missing.

A Swiss banking group with EU subsidiaries maintains the DORA Register of Information for its
EU entities and, in Switzerland, an **outsourcing inventory** under FINMA Circular 2018/3
"Outsourcing – banks, insurance companies and selected financial institutions under FinIA"
(version of 4 November 2020) and **critical-function and ICT resilience documentation** under
FINMA Circular 2023/1 "Operational risks and resilience – banks". This module maps each FINMA
requirement to the RoI columns (and the Art. 30 contract checklist and incident log of this
toolkit) that evidence it, states the coverage *by design* (full / partial / none), measures
how complete that data is in a given register, and lists what has to be maintained in addition
– so that one dataset serves both regimes.

The requirement texts paraphrase the circulars; the margin numbers (Rz) were checked against
the current versions (``docs/MODULE_REVIEW.md``) – neither circular has a revision pending on
FINMA's list of regulatory projects (1 September 2026). Proportionality by supervisory
category (2023/1 Rz 20–21) and the institution types of 2018/3 (Rz 5–6.3) are not modelled.
The mapping is an interpretation, not FINMA guidance.
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
      "Service provider (Rz 14)", "Dienstleister (Rz 14)",
      PARTIAL, (F("B_05.01 c0050"), F("B_05.01 c0080"), F("B_05.01 c0010")),
      "The inventory covers all significant outsourced functions, including non-ICT ones; "
      "the RoI only holds ICT providers.",
      "Das Inventar umfasst alle wesentlichen ausgelagerten Funktionen, auch Nicht-IKT; das "
      "RoI enthält nur IKT-Dienstleister."),
    R("FIN-OS-03", OUTSOURCING, "Inventory", "Inventar",
      "Sub-providers of significant functions (Rz 14)",
      "Unterakkordanten wesentlicher Funktionen (Rz 14)",
      PARTIAL, (F("B_05.02 c0030"), F("B_05.02 c0050"),
                F("B_05.02 c0060", "subcontractor")),
      "Covered for ICT services; sub-providers of non-ICT outsourcings are not in the RoI.",
      "Für IKT-Dienstleistungen abgedeckt; Unterakkordanten von Nicht-IKT-Auslagerungen stehen "
      "nicht im RoI."),
    R("FIN-OS-04", OUTSOURCING, "Inventory", "Inventar",
      "Service recipient within the group (Rz 14)", "Leistungsempfänger in der Gruppe (Rz 14)",
      PARTIAL, (F("B_02.02 c0020"), F("B_04.01 c0020"), F("B_01.02 c0010")),
      "Swiss group entities are outside the DORA scope: add them to B_01.02 for the group "
      "view and mark them as outside the DORA reporting scope (this page, or `roi export "
      "--exclude-entity`) so the xBRL-CSV package leaves them out.",
      "Schweizer Gruppengesellschaften liegen außerhalb von DORA: für die Gruppensicht in "
      "B_01.02 aufnehmen und als außerhalb des DORA-Meldeumfangs markieren (diese Seite "
      "oder `roi export --exclude-entity`), damit das xBRL-CSV-Paket sie auslässt."),
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
      "Term and notice periods – evidence for an orderly change of provider (Rz 18–18.1)",
      "Laufzeit und Kündigungsfristen – Nachweis für einen geordneten Wechsel (Rz 18–18.1)",
      PARTIAL, (F("B_02.02 c0070"), F("B_02.02 c0080"), F("B_02.02 c0100"),
                F("B_02.02 c0110")),
      "Not an inventory or minimum contract requirement (Rz 14, 32–35); the dates support the "
      "orderly change of provider or insourcing (Rz 18–18.1).",
      "Keine Inventar- oder Mindestvertragsanforderung (Rz 14, 32–35); die Daten stützen den "
      "geordneten Wechsel oder die Rückführung (Rz 18–18.1)."),
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
      "Contractual security requirements and contingency framework (Rz 24–25)",
      "Vertragliche Sicherheitsanforderungen und Notfallrahmen (Rz 24–25)",
      PARTIAL, (F("B_02.02 c0170", "storage"),),
      "Data sensitivity and the Art. 30(2)(c) clause cover security in general. Critical data "
      "held abroad and its confidentiality are 2023/1 topics (Rz 79, 82); bank-client "
      "confidentiality follows from the Banking Act, not from 2018/3.",
      "Datensensitivität und die Klausel nach Art. 30 Abs. 2 lit. c decken Sicherheit "
      "allgemein ab. Kritische Daten im Ausland und ihre Vertraulichkeit sind Themen von "
      "2023/1 (Rz 79, 82); das Bankkundengeheimnis folgt aus dem Bankengesetz, nicht aus "
      "2018/3.",
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
      "Agreement in writing or text form; sub-outsourcing; termination (Rz 32–35)",
      "Vertrag schriftlich oder in Textform; Unterauslagerung; Kündigung (Rz 32–35)",
      PARTIAL, (F("B_07.01 c0080"),),
      "Largely covered by the Art. 30 checklist. Sub-outsourcing: the company must be informed "
      "early about the use or replacement of subcontractors and be able to terminate (Rz 33 – "
      "no prior consent since the 2020 amendment); internal approval procedures and signing "
      "powers (Rz 35) are outside the RoI.",
      "Weitgehend durch die Art.-30-Checkliste abgedeckt. Unterauslagerung: das Unternehmen "
      "ist frühzeitig über Beizug oder Wechsel von Unterakkordanten zu informieren und muss "
      "kündigen können (Rz 33 – seit der Änderung 2020 keine vorgängige Zustimmung); interne "
      "Genehmigungsverfahren und Zeichnungsberechtigungen (Rz 35) liegen ausserhalb des RoI.",
      art30=("30.1", "30.2.a.2", "30.2.h", "30.3.f.i", "30.3.f.ii")),
    R("FIN-OS-14", OUTSOURCING, "Intra-group outsourcing", "Gruppeninterne Auslagerung",
      "Intra-group outsourcings identified (Rz 14)",
      "Gruppeninterne Auslagerungen identifiziert (Rz 14)",
      PARTIAL, (F("B_03.03 c0020"), F("B_02.03 c0020")),
      "Covered for ICT services between DORA entities; intra-group outsourcings of Swiss "
      "entities and non-ICT outsourcings must be added.",
      "Für IKT-Dienstleistungen zwischen DORA-Unternehmen abgedeckt; gruppeninterne "
      "Auslagerungen Schweizer Gesellschaften und Nicht-IKT-Auslagerungen ergänzen."),
    # ------------------------------------------------------------------ 2023/1 resilience
    R("FIN-OR-01", OPRISK, "Operational resilience", "Operationelle Resilienz",
      "Inventory of critical functions (Rz 14–16, 107)",
      "Inventar der kritischen Funktionen (Rz 14–16, 107)",
      PARTIAL, (F("B_06.01 c0010"), F("B_06.01 c0030"), F("B_06.01 c0050")),
      "FINMA critical functions (disruption would jeopardise the institution's continuation or "
      "its role on the financial market) are a much narrower set than DORA critical or "
      "important functions – typically a few, top-down (Guidance 05/2025 §3.1): map them "
      "explicitly, with their dependencies (Rz 107).",
      "Kritische Funktionen nach FINMA (Störung gefährdet den Fortbestand des Instituts oder "
      "seine Rolle am Finanzmarkt) sind ein viel engerer Kreis als kritische oder wichtige "
      "Funktionen nach DORA – typischerweise wenige, top-down (Aufsichtsmitteilung 05/2025 "
      "§3.1): ausdrücklich zuordnen, mit ihren Abhängigkeiten (Rz 107)."),
    R("FIN-OR-02", OPRISK, "Operational resilience", "Operationelle Resilienz",
      "Tolerance for disruption per critical function (Rz 17)",
      "Unterbrechungstoleranz je kritischer Funktion (Rz 17)",
      NONE, (),
      "A tolerance for disruption is the extent (e.g. duration or expected damage) of a "
      "disruption the institution is willing to accept, set by the executive board "
      "irrespective of its ability to recover; RTO/RPO are not evidence of it (Guidance "
      "05/2025 §3.2). Define tolerances per FINMA critical function.",
      "Die Unterbrechungstoleranz ist das Ausmass (z. B. Dauer oder erwarteter Schaden) einer "
      "Störung, das das Institut zu akzeptieren bereit ist, festgelegt von der "
      "Geschäftsleitung unabhängig von der Wiederherstellungsfähigkeit; RTO/RPO sind kein "
      "Nachweis dafür (Aufsichtsmitteilung 05/2025 §3.2). Toleranzen je kritischer Funktion "
      "festlegen."),
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
      "The incident log covers the DORA classification and deadlines, which are no evidence "
      "of FINMA materiality. FINMA: significant ICT incidents and incidents involving critical "
      "data without delay (Rz 60, 81); cyber attacks with a preliminary notification within "
      "24 hours and a report within 72 hours, then a root cause analysis (Rz 68; Guidance "
      "05/2020, 03/2024; FINMASA Art. 29(2)) – track them separately.",
      "Das Vorfallverzeichnis deckt DORA-Klassifizierung und -Fristen ab; sie belegen keine "
      "Wesentlichkeit nach FINMA. FINMA: wesentliche IKT-Vorfälle und Vorfälle mit kritischen "
      "Daten unverzüglich (Rz 60, 81); Cyber-Angriffe mit Erstmeldung innert 24 Stunden und "
      "Bericht innert 72 Stunden, danach Ursachenanalyse (Rz 68; Aufsichtsmitteilungen "
      "05/2020, 03/2024; Art. 29 Abs. 2 FINMAG) – separat verfolgen.",
      incidents=True),
    R("FIN-OR-08", OPRISK, "Operational resilience", "Operationelle Resilienz",
      "Substitutability and exit for critical third-party dependencies",
      "Ersetzbarkeit und Ausstieg bei kritischen Abhängigkeiten von Dritten",
      PARTIAL, (F("B_07.01 c0050"), F("B_07.01 c0080"), F("B_07.01 c0110")),
      "Substitutability and exit plans are reported (2018/3 Rz 18–18.1; 2023/1 Rz 88, 110); "
      "test them in severe but plausible scenarios.",
      "Ersetzbarkeit und Exit-Pläne sind erfasst (2018/3 Rz 18–18.1; 2023/1 Rz 88, 110); in "
      "schweren, aber plausiblen Szenarien testen.",
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
      "Evidenced by the Art. 30 clauses on data security, security measures and training "
      "(2018/3 Rz 24; 2023/1 Rz 82, 85 – RTO/RPO agreed with providers).",
      "Durch die Art.-30-Klauseln zu Datensicherheit, Sicherheitsmassnahmen und Schulung "
      "belegt (2018/3 Rz 24; 2023/1 Rz 82, 85 – mit Dienstleistern vereinbarte RTO/RPO).",
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
        elif (req.fields and not req.art30 and not req.incidents and completeness is None
              and not register.is_empty()):
            # register-only evidence with nothing applicable to measure keeps the design
            effective = Coverage.PARTIAL
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
