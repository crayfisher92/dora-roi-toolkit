"""Checklist of the key contractual provisions of DORA Art. 30.

Every item is one element of Art. 30(1), 30(2) (all contractual arrangements on the use of
ICT services) or 30(3) (additionally, arrangements on ICT services supporting critical or
important functions). Composite points are split where contracts commonly contain one part
but not the other (e.g. Art. 30(2)(a): description of services *and* subcontracting
conditions; Art. 30(3)(e): the four elements of the right to monitor).

The wording **paraphrases** Regulation (EU) 2022/2554 in English and German; it is not a
quotation. ``docs/ASSUMPTIONS.md`` (A-A30-*) lists what must be checked against the official
text. The keyword patterns only drive *suggestions* for human review
(:mod:`dora_roi.contracts.suggest`); they never decide compliance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property


class Scope(StrEnum):
    """Which arrangements a provision applies to."""

    ALL = "all"  # Art. 30(1)/(2): every ICT service
    CRITICAL = "critical"  # Art. 30(3): ICT services supporting critical or important functions


@dataclass(frozen=True)
class Concept:
    """One idea a clause must express, as alternative regular expressions (EN and DE)."""

    name: str
    patterns: tuple[str, ...]

    @cached_property
    def regex(self) -> re.Pattern[str]:
        return re.compile("|".join(f"(?:{p})" for p in self.patterns),
                          re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class Provision:
    id: str
    article: str
    scope: Scope
    title_en: str
    title_de: str
    requirement_en: str
    requirement_de: str
    remediation_en: str
    remediation_de: str
    concepts: tuple[Concept, ...]
    #: Related provisions elsewhere (shown as context, not assessed separately).
    related: tuple[str, ...] = ()
    #: RoI columns that report facts which must come from this clause.
    register_fields: tuple[str, ...] = ()
    #: Key provisions are listed first within a remediation priority (contracts.analysis).
    key: bool = False

    def title(self, lang: str = "en") -> str:
        return self.title_de if lang == "de" else self.title_en

    def requirement(self, lang: str = "en") -> str:
        return self.requirement_de if lang == "de" else self.requirement_en

    def remediation(self, lang: str = "en") -> str:
        return self.remediation_de if lang == "de" else self.remediation_en

    @property
    def paragraph(self) -> str:
        """``"30(2)"`` – the paragraph the provision belongs to."""
        return "30(1)" if self.id.startswith("30.1") else (
            "30(2)" if self.id.startswith("30.2") else "30(3)")


C = Concept
_AUDIT = r"audit|inspect|Prüfung|Prüfungsrecht|Inspektion|Einsichtsrecht"
_AUTHORITY = (r"competent authorit|supervisory authorit|resolution authorit|regulator|"
              r"Aufsichtsbehörde|zuständige[n]? Behörde|Abwicklungsbehörde|BaFin|CSSF|FINMA|"
              r"\bFMA\b|Lead Overseer")

PROVISIONS: tuple[Provision, ...] = (
    # ------------------------------------------------------------------ Art. 30(1)
    Provision(
        "30.1", "DORA Art. 30(1)", Scope.ALL,
        "Written contract in one document, including the SLAs",
        "Schriftlicher Vertrag in einem Dokument, einschließlich der SLAs",
        "Rights and obligations of both parties are clearly allocated and set out in writing; "
        "the full contract, including the service level agreements, is documented in one "
        "written document available on paper or in a downloadable, durable and accessible "
        "format.",
        "Rechte und Pflichten beider Parteien sind klar zugewiesen und schriftlich festgelegt; "
        "der vollständige Vertrag einschließlich der Service-Level-Vereinbarungen ist in einem "
        "schriftlichen Dokument niedergelegt, das auf Papier oder in einem herunterladbaren, "
        "dauerhaften und zugänglichen Format verfügbar ist.",
        "Consolidate the master agreement, schedules, SLAs and amendments into one controlled "
        "document set and record where the signed version is kept.",
        "Rahmenvertrag, Anlagen, SLAs und Nachträge zu einem gelenkten Dokumentensatz "
        "zusammenführen und den Ablageort der unterzeichneten Fassung dokumentieren.",
        (C("written agreement", (r"entire agreement", r"whole agreement", r"complete agreement",
                                 r"in writing", r"written form", r"Schriftform",
                                 r"gesamte Vereinbarung", r"vollständige Vereinbarung")),
         C("service levels included", (r"service level", r"\bSLAs?\b", r"Service-Level",
                                       r"Leistungsbeschreibung"))),
    ),
    # ------------------------------------------------------------------ Art. 30(2)
    Provision(
        "30.2.a.1", "DORA Art. 30(2)(a)", Scope.ALL,
        "Description of all functions and ICT services",
        "Beschreibung aller Funktionen und IKT-Dienstleistungen",
        "A clear and complete description of all functions and ICT services to be provided by "
        "the ICT third-party service provider.",
        "Eine klare und vollständige Beschreibung aller Funktionen und IKT-Dienstleistungen, "
        "die der IKT-Drittdienstleister bereitstellt.",
        "Add a service description (statement of work) listing every function and ICT service "
        "in scope, consistent with the ICT service types reported in B_02.02.",
        "Eine Leistungsbeschreibung ergänzen, die jede Funktion und IKT-Dienstleistung im "
        "Umfang aufführt – konsistent mit den in B_02.02 gemeldeten IKT-Dienstleistungsarten.",
        (C("service description", (r"description of (the )?services", r"scope of (the )?services",
                                   r"service description", r"statement of work",
                                   r"Leistungsbeschreibung", r"Leistungsumfang",
                                   r"Vertragsgegenstand", r"Gegenstand des Vertrag")),),
        register_fields=("B_02.02 c0060",),
    ),
    Provision(
        "30.2.a.2", "DORA Art. 30(2)(a)", Scope.ALL,
        "Subcontracting: whether permitted and under which conditions",
        "Unterauftragsvergabe: ob zulässig und unter welchen Bedingungen",
        "The contract states whether subcontracting of an ICT service supporting a critical or "
        "important function, or material parts of it, is permitted and, if so, the conditions "
        "that apply to such subcontracting.",
        "Der Vertrag legt fest, ob die Unterauftragsvergabe einer IKT-Dienstleistung, die eine "
        "kritische oder wichtige Funktion unterstützt, oder wesentlicher Teile davon zulässig "
        "ist und, falls ja, unter welchen Bedingungen.",
        "Add a subcontracting clause: permitted or not; if permitted, prior notification or "
        "approval, the right to object, flow-down of the provider's obligations, monitoring of "
        "the chain and termination if conditions are breached.",
        "Eine Klausel zur Unterauftragsvergabe ergänzen: zulässig oder nicht; falls zulässig, "
        "vorherige Anzeige oder Zustimmung, Widerspruchsrecht, Weitergabe der Pflichten, "
        "Überwachung der Kette und Kündigung bei Verstößen.",
        (C("subcontracting", (r"sub-?contract", r"sub-?processor", r"Unterauftrag",
                              r"Subunternehmer", r"Unterbeauftrag", r"Nachunternehmer")),
         C("conditions", (r"prior (written )?(consent|approval|notice|notification)",
                          r"right to object", r"vorherige[nr]? (schriftliche[nr]? )?"
                          r"(Zustimmung|Genehmigung|Anzeige|Mitteilung)",
                          r"Widerspruchsrecht", r"widersprechen", r"subject to the conditions",
                          r"unter den Bedingungen"))),
        related=("DORA Art. 30(5)", "RTS on subcontracting (Art. 30(5))"),
        register_fields=("B_05.02",),
        key=True,
    ),
    Provision(
        "30.2.b.1", "DORA Art. 30(2)(b)", Scope.ALL,
        "Locations of service provision and of data processing and storage",
        "Standorte der Leistungserbringung sowie der Datenverarbeitung und -speicherung",
        "The regions or countries where the contracted or subcontracted functions and ICT "
        "services are provided and where data is processed, including the storage location.",
        "Die Regionen oder Länder, in denen die vertraglich vereinbarten oder unterbeauftragten "
        "Funktionen und IKT-Dienstleistungen erbracht und Daten verarbeitet werden, "
        "einschließlich des Speicherorts.",
        "Annex a list of service and data locations (countries or regions, incl. storage) for "
        "the provider and its subcontractors.",
        "Eine Liste der Leistungs- und Datenstandorte (Länder oder Regionen, inkl. Speicherort) "
        "für den Dienstleister und seine Unterauftragnehmer als Anlage aufnehmen.",
        (C("locations", (r"locations?", r"countr(y|ies)", r"regions?", r"Standort", r"Länder",
                         r"Rechenzentr", r"data cent(er|re)")),
         C("data processing/storage", (r"(data|Daten)\w*.{0,60}(stor|process|host|speicher|"
                                       r"verarbeit)",)),),
        register_fields=("B_02.02 c0130", "B_02.02 c0150", "B_02.02 c0160"),
    ),
    Provision(
        "30.2.b.2", "DORA Art. 30(2)(b)", Scope.ALL,
        "Advance notice before changing locations",
        "Vorherige Mitteilung vor einer Änderung der Standorte",
        "The ICT third-party service provider must notify the financial entity in advance if it "
        "envisages changing the locations of service provision or data processing.",
        "Der IKT-Drittdienstleister muss das Finanzunternehmen vorab benachrichtigen, wenn er "
        "eine Änderung der Standorte der Leistungserbringung oder Datenverarbeitung beabsichtigt.",
        "Add an obligation to notify location changes in advance, with a minimum notice period "
        "and the right to object or terminate.",
        "Eine Pflicht zur vorherigen Mitteilung von Standortänderungen mit Mindestfrist sowie "
        "ein Widerspruchs- oder Kündigungsrecht ergänzen.",
        (C("notice of location change", (
            r"(notif|inform|advance notice|prior notice|benachrichtig|mitteil|vorab|vorher)"
            r".{0,100}(location|countr|region|Standort|Land|Länder)",
            r"(location|countr|region|Standort|Länder).{0,100}(notif|inform|advance notice|"
            r"prior notice|benachrichtig|mitteil|vorab|vorher)")),),
    ),
    Provision(
        "30.2.c", "DORA Art. 30(2)(c)", Scope.ALL,
        "Availability, authenticity, integrity and confidentiality of data",
        "Verfügbarkeit, Authentizität, Integrität und Vertraulichkeit der Daten",
        "Provisions on availability, authenticity, integrity and confidentiality in relation "
        "to the protection of data, including personal data.",
        "Bestimmungen über Verfügbarkeit, Authentizität, Integrität und Vertraulichkeit in "
        "Bezug auf den Schutz von Daten, einschließlich personenbezogener Daten.",
        "Add data-protection and information-security clauses covering all four protection "
        "goals, plus a data processing agreement where personal data is processed.",
        "Datenschutz- und Informationssicherheitsklauseln für alle vier Schutzziele ergänzen, "
        "bei personenbezogenen Daten zusätzlich eine Auftragsverarbeitungsvereinbarung.",
        (C("confidentiality", (r"confidential", r"vertraulich", r"Geheimhaltung")),
         C("integrity/availability/authenticity", (r"integrity", r"Integrität", r"availability",
                                                   r"Verfügbarkeit", r"authenticity",
                                                   r"Authentizität")),
         C("personal data", (r"personal data", r"personenbezogen", r"data protection",
                             r"Datenschutz", r"GDPR", r"DSGVO"))),
        register_fields=("B_02.02 c0170",),
    ),
    Provision(
        "30.2.d", "DORA Art. 30(2)(d)", Scope.ALL,
        "Access, recovery and return of data on insolvency, resolution or termination",
        "Zugang, Wiederherstellung und Rückgabe der Daten bei Insolvenz, Abwicklung oder "
        "Beendigung",
        "Access, recovery and return, in an easily accessible format, of personal and "
        "non-personal data processed for the financial entity in the event of the provider's "
        "insolvency, resolution or discontinuation of business, or termination of the contract.",
        "Zugang, Wiederherstellung und Rückgabe personenbezogener und nicht personenbezogener "
        "Daten in leicht zugänglichem Format bei Insolvenz, Abwicklung oder Einstellung der "
        "Geschäftstätigkeit des Dienstleisters oder bei Beendigung des Vertrags.",
        "Add a data return and deletion clause: formats, timelines, assistance, and its "
        "survival of insolvency, resolution and termination.",
        "Eine Klausel zur Datenrückgabe und -löschung ergänzen: Formate, Fristen, Unterstützung "
        "sowie Fortgeltung bei Insolvenz, Abwicklung und Beendigung.",
        (C("data return", (r"return\w*\b.{0,40}\bdata",
                           r"data (return|retrieval|export|portability)",
                           r"Rückgabe", r"Herausgabe", r"herausgeben", r"Datenexport",
                           r"recover", r"Wiederherstell")),
         C("insolvency/termination", (r"insolven", r"Insolvenz", r"resolution", r"Abwicklung",
                                      r"terminat", r"Beendigung", r"discontinu",
                                      r"Einstellung"))),
        key=True,
    ),
    Provision(
        "30.2.e", "DORA Art. 30(2)(e)", Scope.ALL,
        "Service level descriptions, including updates and revisions",
        "Beschreibung der Dienstleistungsgüte (Service Level), einschließlich Aktualisierungen",
        "Service level descriptions, including updates and revisions thereof.",
        "Beschreibungen der Service Level einschließlich ihrer Aktualisierungen und "
        "Überarbeitungen.",
        "Attach a service level description and a change procedure for it.",
        "Eine Service-Level-Beschreibung und ein Verfahren zu ihrer Änderung beifügen.",
        (C("service levels", (r"service level", r"\bSLAs?\b", r"Service-Level", r"uptime",
                              r"availability of \d", r"Verfügbarkeit von \d")),),
    ),
    Provision(
        "30.2.f", "DORA Art. 30(2)(f)", Scope.ALL,
        "Assistance in ICT incidents at no additional or a pre-agreed cost",
        "Unterstützung bei IKT-Vorfällen ohne Zusatzkosten oder zu vorab festgelegten Kosten",
        "The provider must assist the financial entity when an ICT incident related to the "
        "service occurs, at no additional cost or at a cost determined ex ante.",
        "Der Dienstleister muss das Finanzunternehmen bei IKT-Vorfällen im Zusammenhang mit der "
        "Dienstleistung unterstützen – ohne zusätzliche Kosten oder zu im Voraus festgelegten "
        "Kosten.",
        "Add an incident-assistance clause with response obligations and either no additional "
        "charge or a pre-agreed rate card.",
        "Eine Klausel zur Unterstützung bei Vorfällen mit Reaktionspflichten und entweder ohne "
        "Zusatzkosten oder mit vorab vereinbarten Sätzen ergänzen.",
        (C("incident assistance", (
            r"(incident|Vorfall|Vorfällen|Störung|Sicherheitsvorfall).{0,150}(assist|support|"
            r"unterstütz|Hilfe|cooperat)",
            r"(assist|support|unterstütz).{0,150}(incident|Vorfall|Vorfällen|Störung)")),
         C("cost determined", (r"no additional (cost|charge)", r"without additional (cost|charge)",
                               r"free of charge", r"at no (extra )?cost", r"pre-?agreed",
                               r"agreed in advance", r"ex[- ]ante", r"rate card",
                               r"ohne (zusätzliche|weitere) (Kosten|Vergütung)", r"kostenlos",
                               r"unentgeltlich", r"im Voraus (vereinbart|festgelegt)"))),
    ),
    Provision(
        "30.2.g", "DORA Art. 30(2)(g)", Scope.ALL,
        "Full cooperation with competent and resolution authorities",
        "Uneingeschränkte Zusammenarbeit mit den zuständigen Behörden und Abwicklungsbehörden",
        "The provider must fully cooperate with the competent authorities and the resolution "
        "authorities of the financial entity, including persons appointed by them.",
        "Der Dienstleister muss mit den zuständigen Behörden und den Abwicklungsbehörden des "
        "Finanzunternehmens, einschließlich der von ihnen bestellten Personen, uneingeschränkt "
        "zusammenarbeiten.",
        "Add an authority-cooperation clause naming competent and resolution authorities and "
        "persons appointed by them.",
        "Eine Klausel zur Zusammenarbeit mit Aufsichts- und Abwicklungsbehörden sowie von ihnen "
        "bestellten Personen ergänzen.",
        (C("authorities", (_AUTHORITY,)),
         C("cooperation", (r"cooperat", r"co-operat", r"kooperier", r"zusammenarbeit",
                           r"zusammenzuarbeiten", r"mitwirk"))),
        key=True,
    ),
    Provision(
        "30.2.h", "DORA Art. 30(2)(h)", Scope.ALL,
        "Termination rights and minimum notice periods",
        "Kündigungsrechte und Mindestkündigungsfristen",
        "Termination rights and related minimum notice periods, in line with the expectations "
        "of competent and resolution authorities; the termination circumstances of DORA "
        "Art. 28(7) must be covered.",
        "Kündigungsrechte und zugehörige Mindestkündigungsfristen entsprechend den Erwartungen "
        "der zuständigen Behörden und Abwicklungsbehörden; die Kündigungsgründe nach DORA "
        "Art. 28 Abs. 7 müssen abgedeckt sein.",
        "Add termination rights for the Art. 28(7) circumstances (breach of law or contract, "
        "impaired performance, ICT risk weaknesses, impeded supervision) and minimum notice "
        "periods for both parties.",
        "Kündigungsrechte für die Fälle des Art. 28 Abs. 7 (Rechts- oder Vertragsverstoß, "
        "beeinträchtigte Leistung, Schwächen im IKT-Risikomanagement, behinderte Aufsicht) und "
        "Mindestkündigungsfristen für beide Parteien ergänzen.",
        (C("termination", (r"terminat", r"Kündigung", r"kündig")),
         C("notice period", (r"notice period", r"\d+\s*(calendar |business )?(days|months)'?"
                             r"\s*(prior )?(written )?notice", r"Kündigungsfrist",
                             r"Frist von \d+", r"mit einer Frist"))),
        related=("DORA Art. 28(7)",),
        register_fields=("B_02.02 c0100", "B_02.02 c0110"),
        key=True,
    ),
    Provision(
        "30.2.i", "DORA Art. 30(2)(i)", Scope.ALL,
        "Participation in ICT security awareness and resilience training",
        "Teilnahme an Sensibilisierungsprogrammen und Schulungen zur IKT-Sicherheit",
        "Conditions for the provider's participation in the financial entity's ICT security "
        "awareness programmes and digital operational resilience training (Art. 13(6)).",
        "Bedingungen für die Teilnahme des Dienstleisters an den Sensibilisierungsprogrammen "
        "zur IKT-Sicherheit und den Schulungen zur digitalen operationalen Resilienz des "
        "Finanzunternehmens (Art. 13 Abs. 6).",
        "Add a clause on the provider's participation in security awareness programmes and "
        "operational resilience training.",
        "Eine Klausel zur Teilnahme des Dienstleisters an Sensibilisierungsprogrammen und "
        "Resilienzschulungen ergänzen.",
        (C("training", (r"awareness", r"training", r"Schulung", r"Sensibilisierung")),
         C("security/resilience", (r"operational resilience", r"ICT security",
                                   r"information security", r"cyber", r"IKT-Sicherheit",
                                   r"Informationssicherheit", r"operationale[nr]? Resilienz"))),
        related=("DORA Art. 13(6)",),
    ),
    # ------------------------------------------------------------------ Art. 30(3)
    Provision(
        "30.3.a", "DORA Art. 30(3)(a)", Scope.CRITICAL,
        "Full service levels with precise quantitative and qualitative targets",
        "Vollständige Service Level mit präzisen quantitativen und qualitativen Zielen",
        "Full service level descriptions with precise quantitative and qualitative performance "
        "targets, allowing effective monitoring and appropriate corrective action without "
        "undue delay when service levels are not met.",
        "Vollständige Service-Level-Beschreibungen mit präzisen quantitativen und qualitativen "
        "Leistungszielen, die eine wirksame Überwachung und unverzügliche Abhilfemaßnahmen bei "
        "Nichterreichen ermöglichen.",
        "Define measurable targets (availability %, response and resolution times, RTO/RPO), "
        "reporting on them and corrective measures such as service credits.",
        "Messbare Ziele (Verfügbarkeit in %, Reaktions- und Lösungszeiten, RTO/RPO), Berichte "
        "dazu und Abhilfemaßnahmen wie Gutschriften festlegen.",
        (C("service levels", (r"service level", r"\bSLAs?\b", r"Service-Level")),
         C("quantitative targets", (r"\d+([.,]\d+)?\s?%", r"per cent", r"Prozent",
                                    r"response time", r"resolution time", r"Reaktionszeit",
                                    r"Lösungszeit", r"\bRTO\b", r"\bRPO\b")),
         C("corrective action", (r"service credit", r"corrective", r"remed", r"penalt",
                                 r"Vertragsstrafe", r"Gutschrift", r"Abhilfe", r"Malus"))),
        register_fields=("B_06.01 c0080", "B_06.01 c0090"),
    ),
    Provision(
        "30.3.b", "DORA Art. 30(3)(b)", Scope.CRITICAL,
        "Notice periods and reporting obligations, incl. material developments",
        "Mitteilungsfristen und Berichtspflichten, inkl. wesentlicher Entwicklungen",
        "Notice periods and reporting obligations of the provider, including notification of "
        "any development that might materially impact its ability to provide the services "
        "effectively and in line with agreed service levels.",
        "Mitteilungsfristen und Berichtspflichten des Dienstleisters, einschließlich der "
        "Mitteilung jeder Entwicklung, die seine Fähigkeit zur wirksamen Leistungserbringung "
        "gemäß den vereinbarten Service Levels wesentlich beeinträchtigen könnte.",
        "Add regular reporting duties and an obligation to notify material developments "
        "(financial distress, change of control, major incidents) within a fixed time.",
        "Regelmäßige Berichtspflichten und eine Pflicht zur fristgebundenen Mitteilung "
        "wesentlicher Entwicklungen (finanzielle Schieflage, Kontrollwechsel, schwere Vorfälle) "
        "ergänzen.",
        (C("reporting", (r"report", r"Bericht", r"berichten")),
         C("material developments", (
             r"(material|significant|wesentlich|erheblich)\w*.{0,100}(impact|change|development|"
             r"Auswirkung|Änderung|Entwicklung|Beeinträchtigung)",
             r"(notify|inform|benachrichtig|unverzüglich).{0,100}(material|significant|"
             r"wesentlich|erheblich)"))),
    ),
    Provision(
        "30.3.c", "DORA Art. 30(3)(c)", Scope.CRITICAL,
        "Tested business contingency plans and appropriate ICT security",
        "Getestete Notfallpläne und angemessene IKT-Sicherheit",
        "The provider implements and tests business contingency plans and has ICT security "
        "measures, tools and policies providing an appropriate level of security in line with "
        "the financial entity's regulatory framework.",
        "Der Dienstleister setzt Notfallpläne um, testet sie und verfügt über IKT-"
        "Sicherheitsmaßnahmen, -werkzeuge und -richtlinien mit einem dem Regelwerk des "
        "Finanzunternehmens entsprechenden Sicherheitsniveau.",
        "Require documented and tested business continuity / disaster recovery plans, test "
        "evidence, and security requirements (e.g. aligned with the entity's ICT security "
        "policy).",
        "Dokumentierte und getestete Notfall- und Wiederanlaufpläne, Testnachweise sowie "
        "Sicherheitsanforderungen (z. B. gemäß IKT-Sicherheitsleitlinie) verlangen.",
        (C("business continuity", (r"business continuity", r"contingency plan",
                                   r"disaster recovery", r"Notfallplan", r"Notfallkonzept",
                                   r"Geschäftsfortführung", r"\bBCM\b", r"Wiederanlauf")),
         C("testing", (r"\btest", r"exercise", r"Übung")),
         C("security measures", (r"security measures", r"security polic", r"information security",
                                 r"Sicherheitsmaßnahmen", r"Informationssicherheit",
                                 r"ISO ?/? ?(IEC )?27001"))),
    ),
    Provision(
        "30.3.d", "DORA Art. 30(3)(d)", Scope.CRITICAL,
        "Participation and full cooperation in threat-led penetration testing (TLPT)",
        "Teilnahme und uneingeschränkte Mitwirkung an bedrohungsorientierten Penetrationstests "
        "(TLPT)",
        "The provider must participate and fully cooperate in the financial entity's "
        "threat-led penetration testing under Art. 26 and 27.",
        "Der Dienstleister muss an den bedrohungsorientierten Penetrationstests des "
        "Finanzunternehmens nach Art. 26 und 27 teilnehmen und uneingeschränkt mitwirken.",
        "Add a TLPT clause: participation in the entity's (or pooled) TLPT, scoping, live "
        "production testing, confidentiality and remediation of findings.",
        "Eine TLPT-Klausel ergänzen: Teilnahme an (ggf. gepoolten) TLPT des Unternehmens, "
        "Scoping, Tests in der Produktion, Vertraulichkeit und Behebung von Feststellungen.",
        (C("TLPT", (r"threat[- ]led penetration", r"\bTLPT\b", r"TIBER", r"red[- ]team",
                    r"bedrohungsorientierte\w* Penetrationstest")),),
        related=("DORA Art. 26", "DORA Art. 27"),
        key=True,
    ),
    Provision(
        "30.3.e.i", "DORA Art. 30(3)(e)(i)", Scope.CRITICAL,
        "Unrestricted rights of access, inspection and audit",
        "Uneingeschränkte Zugangs-, Inspektions- und Prüfungsrechte",
        "Unrestricted rights of access, inspection and audit by the financial entity, an "
        "appointed third party and the competent authority, including the right to take copies "
        "of relevant documentation on site, not impeded by other contractual arrangements or "
        "policies.",
        "Uneingeschränkte Zugangs-, Inspektions- und Prüfungsrechte des Finanzunternehmens, "
        "eines beauftragten Dritten und der zuständigen Behörde, einschließlich des Rechts, vor "
        "Ort Kopien relevanter Unterlagen anzufertigen, ohne Einschränkung durch andere "
        "Vereinbarungen oder Richtlinien.",
        "Negotiate an audit addendum granting unrestricted access, inspection and audit rights "
        "to the entity, its appointed auditors and the competent authority, incl. on-site "
        "copies.",
        "Einen Prüfungsnachtrag mit uneingeschränkten Zugangs-, Inspektions- und Prüfungsrechten "
        "für das Unternehmen, beauftragte Prüfer und die zuständige Behörde, inkl. Kopien vor "
        "Ort, verhandeln.",
        (C("audit", (_AUDIT,)),
         C("access", (r"\baccess\b", r"Zugang", r"Zutritt", r"premises", r"Räumlichkeiten",
                      r"on[- ]site", r"vor Ort")),
         C("authority", (_AUTHORITY,))),
        related=("DORA Art. 28(6)",),
        register_fields=("B_07.01 c0070",),
        key=True,
    ),
    Provision(
        "30.3.e.ii", "DORA Art. 30(3)(e)(ii)", Scope.CRITICAL,
        "Right to agree alternative assurance levels",
        "Recht auf Vereinbarung alternativer Prüfungsniveaus",
        "The right to agree on alternative assurance levels if other clients' rights are "
        "affected.",
        "Das Recht, alternative Prüfungsniveaus zu vereinbaren, wenn Rechte anderer Kunden "
        "betroffen sind.",
        "Add the option of alternative assurance (pooled audits, independent certifications or "
        "reports) where other clients' rights are affected.",
        "Die Möglichkeit alternativer Prüfungen (Poolprüfungen, unabhängige Zertifizierungen "
        "oder Berichte) ergänzen, wenn Rechte anderer Kunden berührt sind.",
        (C("alternative assurance", (r"pooled audit", r"alternative assurance",
                                     r"third[- ]party certification", r"ISAE ?3402",
                                     r"\bSOC ?[12]\b", r"Sammelprüfung", r"Poolprüfung",
                                     r"gepoolte\w* Prüfung")),),
    ),
    Provision(
        "30.3.e.iii", "DORA Art. 30(3)(e)(iii)", Scope.CRITICAL,
        "Full cooperation during on-site inspections and audits",
        "Uneingeschränkte Mitwirkung bei Vor-Ort-Inspektionen und Prüfungen",
        "The provider must fully cooperate during on-site inspections and audits by the "
        "competent authorities, the Lead Overseer, the financial entity or an appointed third "
        "party.",
        "Der Dienstleister muss bei Vor-Ort-Inspektionen und Prüfungen durch die zuständigen "
        "Behörden, die federführende Überwachungsbehörde, das Finanzunternehmen oder einen "
        "beauftragten Dritten uneingeschränkt mitwirken.",
        "Add a cooperation duty for on-site inspections and audits, naming the Lead Overseer.",
        "Eine Mitwirkungspflicht bei Vor-Ort-Inspektionen und Prüfungen ergänzen, unter "
        "Nennung der federführenden Überwachungsbehörde.",
        (C("cooperation in audits", (
            r"(cooperat|co-operat|kooperier|unterstütz|mitwirk|Mitwirkung).{0,150}"
            r"(audit|inspect|Prüfung|Inspektion)",
            r"(audit|inspect|Prüfung|Inspektion).{0,150}(cooperat|co-operat|kooperier|"
            r"unterstütz|mitwirk)")),
         C("on-site / Lead Overseer", (r"Lead Overseer", r"federführende\w* "
                                       r"Überwachungsbehörde", r"on[- ]site", r"vor Ort"))),
    ),
    Provision(
        "30.3.e.iv", "DORA Art. 30(3)(e)(iv)", Scope.CRITICAL,
        "Scope, procedures and frequency of inspections and audits",
        "Umfang, Verfahren und Häufigkeit von Inspektionen und Prüfungen",
        "The obligation to provide details on the scope, procedures to be followed and "
        "frequency of such inspections and audits.",
        "Die Pflicht, Einzelheiten zu Umfang, Verfahren und Häufigkeit solcher Inspektionen und "
        "Prüfungen anzugeben.",
        "Define audit scope, procedure (notice, conduct, reporting) and frequency in an audit "
        "schedule.",
        "Prüfungsumfang, Verfahren (Ankündigung, Durchführung, Berichterstattung) und "
        "Häufigkeit in einem Prüfungsplan festlegen.",
        (C("audit scope/frequency", (
            r"(frequency|scope|procedure|Häufigkeit|Umfang|Verfahren|Ablauf)\w*.{0,100}"
            r"(audit|inspect|Prüfung)",
            r"(audit|inspect|Prüfung)\w*.{0,100}(frequency|scope|procedure|annual|"
            r"once (a|per) (calendar )?year|Häufigkeit|Umfang|jährlich|einmal (pro|im) Jahr)")),),
    ),
    Provision(
        "30.3.f.i", "DORA Art. 30(3)(f)(i)", Scope.CRITICAL,
        "Exit strategy: mandatory adequate transition period",
        "Ausstiegsstrategie: verpflichtender angemessener Übergangszeitraum",
        "Exit strategies, in particular a mandatory adequate transition period during which "
        "the provider continues providing the functions or ICT services, to reduce the risk of "
        "disruption or ensure effective resolution and restructuring.",
        "Ausstiegsstrategien, insbesondere ein verpflichtender angemessener Übergangszeitraum, "
        "in dem der Dienstleister die Funktionen oder IKT-Dienstleistungen weiter erbringt, um "
        "das Störungsrisiko zu verringern oder eine wirksame Abwicklung und Umstrukturierung "
        "sicherzustellen.",
        "Add an exit clause with a mandatory transition period (e.g. 12–24 months) during "
        "which the provider continues the service at agreed terms.",
        "Eine Exit-Klausel mit verpflichtendem Übergangszeitraum (z. B. 12–24 Monate) ergänzen, "
        "in dem der Dienstleister die Leistung zu vereinbarten Bedingungen fortführt.",
        (C("exit", (r"\bexit\b", r"Ausstieg", r"Exit")),
         C("transition period", (r"transition(al)? period", r"transition services",
                                 r"Übergangsfrist", r"Übergangszeitraum", r"Übergangsphase",
                                 r"continue to provide", r"weiterhin (zu )?erbring",
                                 r"Fortführung"))),
        related=("DORA Art. 28(8)",),
        register_fields=("B_07.01 c0080",),
        key=True,
    ),
    Provision(
        "30.3.f.ii", "DORA Art. 30(3)(f)(ii)", Scope.CRITICAL,
        "Exit strategy: migration to another provider or in-house",
        "Ausstiegsstrategie: Migration zu einem anderen Anbieter oder ins eigene Haus",
        "The transition period allows the financial entity to migrate to another ICT "
        "third-party service provider or to in-house solutions, consistent with the complexity "
        "of the service.",
        "Der Übergangszeitraum ermöglicht dem Finanzunternehmen die Migration zu einem anderen "
        "IKT-Drittdienstleister oder zu einer internen Lösung entsprechend der Komplexität der "
        "Dienstleistung.",
        "Add migration assistance obligations (data, know-how transfer, cooperation with the "
        "successor provider, re-insourcing support).",
        "Pflichten zur Migrationsunterstützung ergänzen (Daten, Wissenstransfer, Zusammenarbeit "
        "mit dem Nachfolgeanbieter, Unterstützung beim Re-Insourcing).",
        (C("migration", (r"migrat", r"transfer to (another|a new|an alternative|the successor)",
                         r"successor (provider|supplier)", r"in-house", r"insourc",
                         r"Migration", r"Nachfolge", r"Rückführung", r"Re-?Insourcing")),),
        related=("DORA Art. 28(8)",),
        register_fields=("B_07.01 c0090", "B_07.01 c0110"),
    ),
)

PROVISIONS_BY_ID: dict[str, Provision] = {p.id: p for p in PROVISIONS}


def clause_label(ref: str, lang: str = "en") -> str:
    """``"12.1"`` → ``"Clause 12.1"`` / ``"Ziffer 12.1"``; references with a word are kept."""
    ref = ref.strip()
    if ref[:1].isdigit():
        return ("Ziffer " if lang == "de" else "Clause ") + ref
    return ref


def applicable(critical: bool) -> tuple[Provision, ...]:
    """Provisions that apply to an arrangement (Art. 30(3) only when it supports a CIF)."""
    return tuple(p for p in PROVISIONS if critical or p.scope is Scope.ALL)


def checklist_markdown(lang: str = "en") -> str:
    """Markdown rendering of the checklist (``docs/ART30_CHECKLIST.md``)."""
    de = lang == "de"
    lines = [
        "# DORA Art. 30 contract checklist" if not de else "# Checkliste DORA Art. 30",
        "",
        "<!-- Generated by `python -m dora_roi.docs`; do not edit by hand. -->",
        "",
        "Key contractual provisions of Regulation (EU) 2022/2554, Art. 30, as assessed by "
        "`roi contracts` and the *Contracts* screen of the workbench. Art. 30(2) applies to "
        "every contractual arrangement on the use of ICT services; Art. 30(3) applies in "
        "addition to arrangements on ICT services supporting critical or important functions. "
        "The wording paraphrases the regulation – see [ASSUMPTIONS.md](ASSUMPTIONS.md) "
        "(A-A30-*).",
        "",
        f"**{len(PROVISIONS)} provisions** "
        f"({sum(1 for p in PROVISIONS if p.scope is Scope.ALL)} for all ICT services, "
        f"{sum(1 for p in PROVISIONS if p.scope is Scope.CRITICAL)} additionally for critical "
        "or important functions). ★ = key provision (listed first within a priority).",
        "",
    ]
    for para, heading in (("30(1)", "Art. 30(1) – form of the contract"),
                          ("30(2)", "Art. 30(2) – all contractual arrangements"),
                          ("30(3)", "Art. 30(3) – ICT services supporting critical or important "
                                    "functions")):
        lines += [f"## {heading}", "", "| ID | Reference | Provision | Requirement | Related RoI "
                  "fields |", "|---|---|---|---|---|"]
        for p in PROVISIONS:
            if p.paragraph != para:
                continue
            rel = "; ".join(p.related)
            req = p.requirement(lang) + (f" *Related: {rel}.*" if rel else "")
            lines.append(f"| `{p.id}` | {p.article} | {'★ ' if p.key else ''}{p.title(lang)} | "
                         f"{req} | {', '.join(p.register_fields) or '—'} |")
        lines.append("")
    return "\n".join(lines)
