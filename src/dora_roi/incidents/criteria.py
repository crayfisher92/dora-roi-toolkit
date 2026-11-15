"""Classification criteria and materiality thresholds for major ICT-related incidents.

Source: DORA Art. 18 and the RTS on the classification of ICT-related incidents (Commission
Delegated Regulation (EU) 2024/1772); reporting time limits: RTS/ITS on major incident
reports (Commission Delegated Regulation (EU) 2025/301). The official texts were **not**
available offline (no ``reference/eu/``): the article numbers and thresholds below are the
authors' best understanding and are listed as open assumptions A-INC-* in
``docs/ASSUMPTIONS.md``. Every threshold is a field of :class:`Thresholds`, so a corrected
value is a one-line change (or a configuration override) and not a code change.

Approach (A-INC-02): an incident is **major** when it affects *critical services* and either
(a) involves a successful, malicious, unauthorised access to network and information systems
that may result in data losses, or (b) meets the materiality thresholds of **two or more** of
the six other criteria.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

RTS_CLASSIFICATION = "Commission Delegated Regulation (EU) 2024/1772"
RTS_REPORTING = "Commission Delegated Regulation (EU) 2025/301"


@dataclass(frozen=True)
class Thresholds:
    """Materiality thresholds (all comparisons are 'higher than' unless stated)."""

    clients_share: float = 0.10  # of all clients using the affected service
    clients_absolute: int = 100_000  # clients using the affected service
    counterparts_share: float = 0.30  # of financial counterparts of the affected service
    transactions_share: float = 0.10  # of the daily average number of transactions
    transaction_value_share: float = 0.10  # of the daily average value of transactions
    duration_hours: float = 24.0  # incident duration
    downtime_hours: float = 2.0  # downtime of services supporting critical functions
    member_states: int = 2  # impact in at least this many Member States
    economic_eur: Decimal = Decimal(100_000)  # direct and indirect costs and losses
    recurrence_months: int = 6  # recurring incidents: same apparent root cause within …
    # reporting time limits
    initial_after_classification_hours: int = 4
    initial_after_awareness_hours: int = 24
    intermediate_after_initial_hours: int = 72
    final_after_intermediate_months: int = 1


DEFAULT_THRESHOLDS = Thresholds()


class Criterion(StrEnum):
    CRITICAL_SERVICES = "critical_services"
    CLIENTS = "clients"
    REPUTATION = "reputation"
    DURATION = "duration"
    GEOGRAPHY = "geography"
    DATA = "data"
    ECONOMIC = "economic"


#: The six criteria counted for the "two or more" condition (critical services is the gate).
COUNTED = (Criterion.CLIENTS, Criterion.REPUTATION, Criterion.DURATION, Criterion.GEOGRAPHY,
           Criterion.DATA, Criterion.ECONOMIC)


@dataclass(frozen=True)
class CriterionInfo:
    key: Criterion
    dora: str
    rts: str
    title_en: str
    title_de: str
    question_en: str
    question_de: str
    threshold_en: str
    threshold_de: str

    def title(self, lang: str = "en") -> str:
        return self.title_de if lang == "de" else self.title_en

    def question(self, lang: str = "en") -> str:
        return self.question_de if lang == "de" else self.question_en

    def threshold(self, lang: str = "en") -> str:
        return self.threshold_de if lang == "de" else self.threshold_en


def pct(value: float) -> str:
    return f"{value * 100:.0f} %"


def criteria(th: Thresholds = DEFAULT_THRESHOLDS) -> tuple[CriterionInfo, ...]:
    """The seven criteria with questions and the thresholds in force (EN/DE)."""
    return (
        CriterionInfo(
            Criterion.CRITICAL_SERVICES, "DORA Art. 18(1)(e)", "RTS Art. 6",
            "Critical services affected", "Betroffenheit kritischer Dienste",
            "Did the incident affect ICT services or network and information systems that "
            "support critical or important functions, financial services that require "
            "authorisation, or was there a successful malicious unauthorised access?",
            "Waren IKT-Dienste oder Netzwerk- und Informationssysteme betroffen, die kritische "
            "oder wichtige Funktionen unterstützen, zulassungspflichtige Finanzdienstleistungen, "
            "oder gab es einen erfolgreichen böswilligen unbefugten Zugriff?",
            "Gate: required for a major incident.",
            "Voraussetzung für einen schwerwiegenden Vorfall."),
        CriterionInfo(
            Criterion.CLIENTS, "DORA Art. 18(1)(a)", "RTS Art. 1, Art. 9(1)",
            "Clients, financial counterparts and transactions",
            "Kunden, finanzielle Gegenparteien und Transaktionen",
            "How many clients, financial counterparts and transactions were affected?",
            "Wie viele Kunden, finanzielle Gegenparteien und Transaktionen waren betroffen?",
            f"> {pct(th.clients_share)} of clients of the service, or > "
            f"{th.clients_absolute:,} clients, or > {pct(th.counterparts_share)} of financial "
            f"counterparts, or > {pct(th.transactions_share)} of the daily number or > "
            f"{pct(th.transaction_value_share)} of the daily value of transactions, or relevant "
            "clients/counterparts affected.",
            f"> {pct(th.clients_share)} der Kunden des Dienstes oder > "
            f"{th.clients_absolute:,} Kunden".replace(",", ".")
            + f", oder > {pct(th.counterparts_share)} der finanziellen Gegenparteien, oder > "
            f"{pct(th.transactions_share)} der täglichen Anzahl bzw. > "
            f"{pct(th.transaction_value_share)} des täglichen Werts der Transaktionen, oder "
            "relevante Kunden/Gegenparteien betroffen."),
        CriterionInfo(
            Criterion.REPUTATION, "DORA Art. 18(1)(a)", "RTS Art. 2, Art. 9(2)",
            "Reputational impact", "Reputationsschaden",
            "Was the incident reported in the media, did it cause repeated complaints, can "
            "regulatory requirements not be met, or are clients or counterparts likely to be "
            "lost?",
            "Wurde in den Medien berichtet, gab es wiederholte Beschwerden, können "
            "aufsichtsrechtliche Anforderungen nicht erfüllt werden oder drohen Kunden- bzw. "
            "Gegenparteiverluste?",
            "Any of: media coverage, repeated complaints, regulatory requirements not met, "
            "likely loss of clients or counterparts.",
            "Eines davon: Medienberichte, wiederholte Beschwerden, Nichterfüllung "
            "aufsichtsrechtlicher Anforderungen, wahrscheinlicher Kundenverlust."),
        CriterionInfo(
            Criterion.DURATION, "DORA Art. 18(1)(b)", "RTS Art. 3, Art. 9(3)",
            "Duration and service downtime", "Dauer und Ausfallzeit",
            "How long did the incident last, and how long were services supporting critical "
            "or important functions down?",
            "Wie lange dauerte der Vorfall, und wie lange waren Dienste für kritische oder "
            "wichtige Funktionen nicht verfügbar?",
            f"Duration > {th.duration_hours:g} h, or downtime of services supporting critical "
            f"functions > {th.downtime_hours:g} h.",
            f"Dauer > {th.duration_hours:g} h oder Ausfallzeit von Diensten für kritische "
            f"Funktionen > {th.downtime_hours:g} h."),
        CriterionInfo(
            Criterion.GEOGRAPHY, "DORA Art. 18(1)(c)", "RTS Art. 4, Art. 9(4)",
            "Geographical spread", "Geografische Ausbreitung",
            "In which Member States did the incident have an impact (clients, counterparts, "
            "branches, group entities, market infrastructures, providers)?",
            "In welchen Mitgliedstaaten hatte der Vorfall Auswirkungen (Kunden, Gegenparteien, "
            "Zweigniederlassungen, Gruppenunternehmen, Marktinfrastrukturen, Dienstleister)?",
            f"Impact in {th.member_states} or more Member States.",
            f"Auswirkungen in {th.member_states} oder mehr Mitgliedstaaten."),
        CriterionInfo(
            Criterion.DATA, "DORA Art. 18(1)(d)", "RTS Art. 5, Art. 9(5)",
            "Data losses", "Datenverluste",
            "Was the availability, authenticity, integrity or confidentiality of data affected "
            "with an adverse impact on business objectives or regulatory requirements?",
            "Waren Verfügbarkeit, Authentizität, Integrität oder Vertraulichkeit von Daten mit "
            "nachteiligen Folgen für Geschäftsziele oder aufsichtsrechtliche Anforderungen "
            "betroffen?",
            "Any such impact on data.", "Jede solche Beeinträchtigung von Daten."),
        CriterionInfo(
            Criterion.ECONOMIC, "DORA Art. 18(1)(f)", "RTS Art. 7, Art. 9(6)",
            "Economic impact", "Wirtschaftliche Auswirkungen",
            "What are the direct and indirect costs and losses (actual or likely)?",
            "Wie hoch sind die direkten und indirekten Kosten und Verluste (tatsächlich oder "
            "voraussichtlich)?",
            f"Costs and losses > EUR {th.economic_eur:,.0f}.",
            f"Kosten und Verluste > EUR {th.economic_eur:,.0f}".replace(",", ".") + "."),
    )


def criterion_info(key: Criterion, th: Thresholds = DEFAULT_THRESHOLDS) -> CriterionInfo:
    return next(c for c in criteria(th) if c.key is key)


def criteria_markdown(th: Thresholds = DEFAULT_THRESHOLDS) -> str:
    """``docs/INCIDENT_CLASSIFICATION.md`` – criteria, thresholds and time limits in force."""
    lines = [
        "# Major ICT-related incident classification",
        "",
        "<!-- Generated by `python -m dora_roi.docs`; do not edit by hand. -->",
        "",
        f"Criteria of DORA Art. 18 as specified by the RTS on classification ({RTS_CLASSIFICATION})"
        f" and reporting time limits ({RTS_REPORTING}), as implemented by `roi incidents` and "
        "the *Incidents* screen of the workbench. Thresholds and article numbers are open "
        "assumptions (A-INC-* in [ASSUMPTIONS.md](ASSUMPTIONS.md)); every value is a field of "
        "`dora_roi.incidents.criteria.Thresholds`.",
        "",
        "**Major incident** = *critical services affected* **and** either a successful, "
        "malicious, unauthorised access to network and information systems that may result in "
        "data losses, **or** the thresholds of **two or more** of the six other criteria met.",
        "",
        "| Criterion | DORA | RTS | Materiality threshold |",
        "|---|---|---|---|",
    ]
    for c in criteria(th):
        lines.append(f"| {c.title_en} | {c.dora} | {c.rts} | {c.threshold_en} |")
    lines += [
        "",
        "## Unknown answers",
        "",
        "Every answer may be *unknown*. The outcome is computed with all unknowns as \"not met\""
        " and as \"met\"; it is **major** or **not major** only when both agree, otherwise "
        "**undetermined** with the list of open questions that could change it. An ongoing "
        "incident's duration counts from occurrence (or awareness) to now and is not final.",
        "",
        "## Recurring incidents",
        "",
        f"Individually non-major incidents with the same apparent root cause (same recurrence "
        f"key) that occurred at least twice within {th.recurrence_months} months are combined: "
        "counts, durations, downtime and costs are added, totals use the largest denominator, "
        "yes/no answers are true if any is true, Member States are united. If the combination "
        "is major, the series is flagged for reporting as one major incident.",
        "",
        "## Reporting time limits",
        "",
        "| Report | Due |",
        "|---|---|",
        f"| Initial notification | {th.initial_after_classification_hours} h after "
        f"classification as major, at the latest {th.initial_after_awareness_hours} h after "
        "becoming aware |",
        f"| Intermediate report | {th.intermediate_after_initial_hours} h after the initial "
        "notification (projected from its deadline until it is submitted) |",
        f"| Final report | {th.final_after_intermediate_months} month after the intermediate "
        "report (projected likewise) |",
        "",
        "Weekend and bank-holiday relief is not applied (conservative).",
        "",
    ]
    return "\n".join(lines)
