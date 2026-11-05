"""Plain-language explanations of every rule, in English and German.

Each entry answers *what is wrong* and *how to fix it* in words a business user understands;
the regulatory references stay on the rule itself. A test asserts that every registered rule
has an entry in both languages.
"""

from __future__ import annotations

from dataclasses import dataclass

from dora_roi.validation import RULES


@dataclass(frozen=True)
class Explanation:
    title_de: str
    en: str
    de: str


E = Explanation

EXPLANATIONS: dict[str, Explanation] = {
    # ------------------------------------------------------------------ import
    "IMP-001": E("Unbekanntes Blatt oder Datei ignoriert",
                 "This sheet or file is not one of the RoI templates and was skipped. Rename it "
                 "to the template code (for example B_02.02) if it contains register data.",
                 "Dieses Blatt bzw. diese Datei entspricht keiner RoI-Vorlage und wurde "
                 "übersprungen. Benennen Sie es nach dem Vorlagencode (z. B. B_02.02), falls es "
                 "Registerdaten enthält."),
    "IMP-002": E("Vorlage fehlt in der Eingabe",
                 "No sheet was found for this template, so it is treated as empty. Add the sheet "
                 "if the template applies to you.",
                 "Für diese Vorlage wurde kein Blatt gefunden; sie gilt als leer. Ergänzen Sie "
                 "das Blatt, falls die Vorlage auf Sie zutrifft."),
    "IMP-003": E("Unbekannte Spalte ignoriert",
                 "This column header is not a column of the template, so its values were not "
                 "read. Use the official column code (c0010, c0020, …) as header.",
                 "Diese Spaltenüberschrift gehört nicht zur Vorlage; die Werte wurden nicht "
                 "eingelesen. Verwenden Sie den offiziellen Spaltencode (c0010, c0020, …)."),
    "IMP-004": E("Kopfzeile nicht gefunden",
                 "The sheet has no row with column codes, so none of its data could be read. "
                 "Start from the blank template or add a header row with c0010, c0020, …",
                 "Das Blatt enthält keine Zeile mit Spaltencodes; keine Daten konnten gelesen "
                 "werden. Nutzen Sie die leere Vorlage oder ergänzen Sie eine Kopfzeile."),
    # ------------------------------------------------------------------ field
    "FLD-001": E("Pflichtwert fehlt",
                 "A mandatory column is empty. Every row must have a value here before the "
                 "register can be submitted.",
                 "Eine Pflichtspalte ist leer. Vor der Einreichung muss jede Zeile hier einen "
                 "Wert haben."),
    "FLD-002": E("Ungültiger LEI",
                 "The Legal Entity Identifier is not valid: it must have 20 characters and its "
                 "last two digits are a checksum. Usually one character was mistyped – copy the "
                 "LEI from the GLEIF database.",
                 "Der LEI ist ungültig: Er hat 20 Zeichen, die letzten beiden sind eine "
                 "Prüfziffer. Meist ist ein Zeichen vertippt – kopieren Sie den LEI aus der "
                 "GLEIF-Datenbank."),
    "FLD-003": E("Ungültiges Datum",
                 "Dates must be written as YYYY-MM-DD (for example 2025-12-31). Convert local "
                 "formats such as 31.12.2025.",
                 "Datumsangaben müssen im Format JJJJ-MM-TT stehen (z. B. 2025-12-31). Wandeln "
                 "Sie lokale Formate wie 31.12.2025 um."),
    "FLD-004": E("Wert nicht in der Codeliste",
                 "This column only accepts values from a fixed list. Pick one of the allowed "
                 "codes shown in the message.",
                 "Diese Spalte akzeptiert nur Werte aus einer festen Liste. Wählen Sie einen der "
                 "in der Meldung genannten Codes."),
    "FLD-005": E("Ungültiger Ländercode",
                 "Countries must be two-letter ISO codes. Note the common traps: United Kingdom "
                 "is GB (not UK) and Greece is GR (not EL).",
                 "Länder müssen als zweistellige ISO-Codes angegeben werden. Achtung: "
                 "Großbritannien ist GB (nicht UK), Griechenland ist GR (nicht EL)."),
    "FLD-006": E("Ungültiger Währungscode",
                 "Currencies must be three-letter ISO codes such as EUR or CHF, not words or "
                 "symbols.",
                 "Währungen müssen dreistellige ISO-Codes wie EUR oder CHF sein, keine Wörter "
                 "oder Symbole."),
    "FLD-007": E("Ungültige Zahl",
                 "This must be a non-negative number (whole number for days, hours and ranks). "
                 "Remove text and units.",
                 "Hier muss eine nicht negative Zahl stehen (ganze Zahl bei Tagen, Stunden und "
                 "Rängen). Entfernen Sie Text und Einheiten."),
    "FLD-008": E("Ungültiger Wahrheitswert",
                 "Yes/no columns must contain true or false.",
                 "Ja/Nein-Spalten müssen true oder false enthalten."),
    "FLD-009": E("Text zu lang",
                 "Text values are limited to 255 characters. Shorten the text.",
                 "Texte sind auf 255 Zeichen begrenzt. Kürzen Sie den Text."),
    "FLD-010": E("Doppelter Schlüssel",
                 "The same record (for example the same contract reference) appears twice. Keep "
                 "one row and delete or renumber the other.",
                 "Derselbe Datensatz (z. B. dieselbe Vertragsnummer) kommt doppelt vor. Behalten "
                 "Sie eine Zeile und löschen oder nummerieren Sie die andere neu."),
    "FLD-011": E("B_01.01 muss genau eine Zeile enthalten",
                 "Exactly one entity maintains the register. Fill in B_01.01 with one row.",
                 "Genau ein Unternehmen führt das Register. Füllen Sie B_01.01 mit einer Zeile."),
    "FLD-012": E("Zentrale Vorlage ist leer",
                 "Entities, contracts, providers and functions are the core of the register; "
                 "this template must not be empty.",
                 "Unternehmen, Verträge, Dienstleister und Funktionen bilden den Kern des "
                 "Registers; diese Vorlage darf nicht leer sein."),
    "FLD-013": E("Dienstleistercode passt nicht zum Codetyp",
                 "The provider code does not match its type: an LEI must be a valid LEI, an EUID "
                 "starts with a country code and the register number. Correct the code or its "
                 "type.",
                 "Der Dienstleistercode passt nicht zum Typ: Ein LEI muss gültig sein, eine EUID "
                 "beginnt mit Ländercode und Registernummer. Korrigieren Sie Code oder Typ."),
    # ------------------------------------------------------------------ referential
    "XRF-001": E("Vertrag nicht in B_02.01 erfasst",
                 "This row refers to a contract reference that is not listed in B_02.01. Add the "
                 "contract there or correct the reference.",
                 "Diese Zeile verweist auf eine Vertragsnummer, die in B_02.01 fehlt. Ergänzen "
                 "Sie den Vertrag dort oder korrigieren Sie die Nummer."),
    "XRF-002": E("Unternehmen nicht in B_01.02 erfasst",
                 "This LEI is not one of the entities listed in B_01.02. Add the entity or "
                 "correct the LEI.",
                 "Dieser LEI gehört zu keinem in B_01.02 erfassten Unternehmen. Ergänzen Sie das "
                 "Unternehmen oder korrigieren Sie den LEI."),
    "XRF-003": E("IKT-Dienstleister nicht in B_05.01 erfasst",
                 "The provider is used here but not described in B_05.01. Add the provider "
                 "(name, country, parent) or correct the code.",
                 "Der Dienstleister wird hier verwendet, ist aber in B_05.01 nicht beschrieben. "
                 "Ergänzen Sie ihn (Name, Land, Mutter) oder korrigieren Sie den Code."),
    "XRF-004": E("Funktion nicht in B_06.01 erfasst",
                 "The function identifier is not listed in B_06.01. Every supported function "
                 "must be identified and assessed for criticality.",
                 "Die Funktionskennung fehlt in B_06.01. Jede unterstützte Funktion muss erfasst "
                 "und auf Kritikalität bewertet werden."),
    "XRF-005": E("Funktion einem anderen Unternehmen zugeordnet",
                 "The function exists, but for a different entity than the one using the "
                 "service. Check the function identifier and the entity LEI.",
                 "Die Funktion existiert, aber für ein anderes Unternehmen als das nutzende. "
                 "Prüfen Sie Funktionskennung und LEI."),
    "XRF-006": E("Vertrag ohne Detailangaben",
                 "This contract has no row in B_02.02, so nobody knows what it provides. Add the "
                 "service, provider, function and dates.",
                 "Zu diesem Vertrag gibt es keine Zeile in B_02.02. Ergänzen Sie Leistung, "
                 "Dienstleister, Funktion und Daten."),
    "XRF-007": E("Vertrag ohne unterzeichnendes Unternehmen",
                 "Record in B_03.01 which entity of the group signed this contract.",
                 "Erfassen Sie in B_03.01, welches Gruppenunternehmen den Vertrag unterzeichnet "
                 "hat."),
    "XRF-008": E("Dienstleister nicht als Unterzeichner in B_03.02",
                 "The provider of this contract should also be listed as signatory in B_03.02.",
                 "Der Dienstleister des Vertrags sollte in B_03.02 als Unterzeichner erfasst "
                 "sein."),
    "XRF-009": E("Vertrag ohne Leistungsempfänger in B_04.01",
                 "Record in B_04.01 which entities (or branches) use the services of this "
                 "contract.",
                 "Erfassen Sie in B_04.01, welche Unternehmen (oder Zweigstellen) die Leistungen "
                 "nutzen."),
    "XRF-010": E("Dienstleister ohne Vertrag",
                 "This provider is not used by any contract or supply chain. Remove it if the "
                 "relationship has ended.",
                 "Dieser Dienstleister wird von keinem Vertrag und keiner Lieferkette verwendet. "
                 "Entfernen Sie ihn, falls die Beziehung beendet ist."),
    "XRF-011": E("Rahmenvertrag nicht auflösbar",
                 "The referenced master (overarching) agreement does not exist or is not of type "
                 "overarching. Correct the reference or the master agreement's type.",
                 "Der referenzierte Rahmenvertrag existiert nicht oder ist nicht als "
                 "Rahmenvertrag typisiert. Korrigieren Sie Verweis oder Typ."),
    "XRF-012": E("Zweigstelle nicht in B_01.03",
                 "The branch using this service is not listed in B_01.03 for this head office.",
                 "Die nutzende Zweigstelle ist in B_01.03 für diesen Hauptsitz nicht erfasst."),
    "XRF-013": E("Bewertung passt zu keiner IKT-Dienstleistung",
                 "The assessment in B_07.01 does not match any contract/provider/service type "
                 "combination in B_02.02. Align the three values.",
                 "Die Bewertung in B_07.01 passt zu keiner Kombination aus Vertrag, Dienstleister "
                 "und Leistungsart in B_02.02. Gleichen Sie die drei Werte an."),
    "XRF-014": E("Mutterunternehmen außerhalb des Registers",
                 "The parent is not in B_01.02. That is fine if it is outside the scope (for "
                 "example a non-EU holding) – just confirm it.",
                 "Das Mutterunternehmen ist nicht in B_01.02. Das ist in Ordnung, wenn es "
                 "außerhalb des Anwendungsbereichs liegt (z. B. Holding außerhalb der EU)."),
    "XRF-015": E("Unternehmen ohne IKT-Dienstleistung",
                 "This entity does not use any service in the register. Confirm its ICT services "
                 "are covered.",
                 "Dieses Unternehmen nutzt keine Leistung des Registers. Bestätigen Sie, dass "
                 "seine IKT-Dienstleistungen erfasst sind."),
    # ------------------------------------------------------------------ supply chain
    "SC-001": E("Rang 1 ist nicht der direkte Dienstleister",
                "The first link of a supply chain must be the provider you contracted with.",
                "Das erste Glied einer Lieferkette muss der Vertragspartner sein."),
    "SC-002": E("Unterauftragnehmer ohne Empfänger",
                "For rank 2 and deeper, record which provider receives the subcontracted "
                "service.",
                "Ab Rang 2 muss erfasst sein, welcher Dienstleister die weitervergebene Leistung "
                "empfängt."),
    "SC-003": E("Unterauftragskette nicht auflösbar",
                "The recipient named for this subcontractor is not at the previous rank of the "
                "same chain, so the chain is broken. Add the missing link or correct the "
                "recipient.",
                "Der genannte Empfänger steht nicht auf dem vorherigen Rang derselben Kette; die "
                "Kette ist unterbrochen. Ergänzen Sie das fehlende Glied oder korrigieren Sie "
                "den Empfänger."),
    "SC-004": E("Empfänger bei Rang 1 angegeben",
                "The direct provider (rank 1) has no recipient; leave the field empty.",
                "Der direkte Dienstleister (Rang 1) hat keinen Empfänger; lassen Sie das Feld "
                "leer."),
    "SC-005": E("Zirkuläre Unterauftragskette",
                "A provider appears as its own subcontractor in the chain. Correct the ranks.",
                "Ein Dienstleister erscheint in der Kette als eigener Unterauftragnehmer. "
                "Korrigieren Sie die Ränge."),
    "SC-006": E("Keine Lieferkette für kritische Leistung",
                "Services supporting critical functions should have their supply chain in "
                "B_05.02 – at least the direct provider at rank 1.",
                "Leistungen für kritische Funktionen sollten ihre Lieferkette in B_05.02 "
                "haben – mindestens den direkten Dienstleister auf Rang 1."),
    # ------------------------------------------------------------------ business
    "BUS-001": E("Enddatum vor Startdatum",
                 "The contract ends before it starts. Check both dates.",
                 "Der Vertrag endet vor seinem Beginn. Prüfen Sie beide Daten."),
    "BUS-002": E("Beendigungsgrund fehlt",
                 "The contract has ended but no reason for its end is given. Select a reason.",
                 "Der Vertrag ist beendet, aber kein Beendigungsgrund ist angegeben. Wählen Sie "
                 "einen Grund."),
    "BUS-003": E("Beendigungsgrund bei laufendem Vertrag",
                 "A termination reason is given although the contract is still running.",
                 "Für einen laufenden Vertrag ist ein Beendigungsgrund angegeben."),
    "BUS-004": E("Speicherort der Daten fehlt",
                 "The provider stores data, so the country where the data is stored is required.",
                 "Der Dienstleister speichert Daten; das Land des Speicherorts ist "
                 "erforderlich."),
    "BUS-005": E("Sensibilität der Daten fehlt",
                 "The provider stores data, so say how sensitive it is (low, medium, high).",
                 "Der Dienstleister speichert Daten; geben Sie die Sensibilität an (niedrig, "
                 "mittel, hoch)."),
    "BUS-006": E("Ort der Datenverarbeitung fehlt",
                 "Where data is stored it is normally also processed; give the processing "
                 "country.",
                 "Gespeicherte Daten werden meist auch verarbeitet; geben Sie das Land der "
                 "Verarbeitung an."),
    "BUS-007": E("Vertragstyp passt nicht zum Rahmenvertrag",
                 "Only subsequent (call-off) contracts reference a master agreement, and they "
                 "must. Fix the type or the reference.",
                 "Nur Einzelverträge (Abrufe) verweisen auf einen Rahmenvertrag – und müssen es "
                 "auch. Korrigieren Sie Typ oder Verweis."),
    "BUS-008": E("Abweichende Währung",
                 "Amounts should be in the reporting currency so they can be added up.",
                 "Beträge sollten in der Berichtswährung angegeben werden, damit sie summiert "
                 "werden können."),
    "BUS-009": E("Gesamtkosten unter Summe der Verträge",
                 "The provider's total annual cost is lower than the sum of its contracts. One "
                 "of the amounts is probably wrong.",
                 "Die Gesamtkosten des Dienstleisters liegen unter der Summe seiner Verträge. "
                 "Einer der Beträge ist vermutlich falsch."),
    "BUS-010": E("Konzernhierarchie passt nicht zum Mutter-LEI",
                 "Subsidiaries need the LEI of their direct parent; an ultimate parent must not "
                 "have one.",
                 "Tochtergesellschaften benötigen den LEI der direkten Mutter; eine oberste "
                 "Muttergesellschaft darf keinen haben."),
    "BUS-011": E("Löschdatum vor Aufnahmedatum",
                 "The entity cannot leave the register before it joined.",
                 "Ein Unternehmen kann das Register nicht vor seiner Aufnahme verlassen."),
    "BUS-012": E("Datum nach dem Stichtag",
                 "This date lies after the reporting reference date. Check for typos.",
                 "Dieses Datum liegt nach dem Berichtsstichtag. Prüfen Sie auf Tippfehler."),
    "BUS-013": E("Zweigstellencode fehlt",
                 "The user is marked as a branch; give the branch code (or untick 'branch').",
                 "Der Nutzer ist als Zweigstelle markiert; geben Sie den Zweigstellencode an."),
    "BUS-014": E("Zusatzkennung ohne Typ",
                 "An additional provider code needs its type (VAT, CRN, …) and vice versa.",
                 "Eine zusätzliche Kennung benötigt ihren Typ (USt-ID, HR-Nummer, …) und "
                 "umgekehrt."),
    "BUS-015": E("Kritische Funktion ohne Begründung oder RTO/RPO",
                 "For a critical or important function, give the reasons and the recovery time "
                 "and recovery point objectives in hours.",
                 "Für eine kritische oder wichtige Funktion sind Begründung sowie RTO und RPO in "
                 "Stunden anzugeben."),
    "BUS-016": E("Kritikalität nicht bewertet",
                 "This function has not been assessed. Decide whether it is critical or "
                 "important.",
                 "Diese Funktion wurde nicht bewertet. Entscheiden Sie, ob sie kritisch oder "
                 "wichtig ist."),
    "BUS-017": E("Kritikalitätsbewertung veraltet",
                 "The last criticality assessment is more than a year old. Reassess the "
                 "function.",
                 "Die letzte Kritikalitätsbewertung ist älter als ein Jahr. Bewerten Sie die "
                 "Funktion neu."),
    "BUS-018": E("Kritische Leistung ohne Bewertung in B_07.01",
                 "Services supporting critical functions need an assessment of "
                 "substitutability, exit plan and reintegration in B_07.01.",
                 "Leistungen für kritische Funktionen benötigen in B_07.01 eine Bewertung von "
                 "Ersetzbarkeit, Exit-Plan und Rückführung."),
    "BUS-019": E("Kein Exit-Plan für kritische Leistung",
                 "DORA requires an exit strategy for ICT services supporting critical functions. "
                 "Document an exit plan and set 'exit plan' to true.",
                 "DORA verlangt eine Exit-Strategie für IKT-Leistungen kritischer Funktionen. "
                 "Dokumentieren Sie einen Exit-Plan und setzen Sie 'Exit-Plan' auf true."),
    "BUS-020": E("Begründung für Nicht-Ersetzbarkeit fehlt",
                 "If the provider is hard or impossible to replace, say why (no alternatives, "
                 "migration difficulties or both).",
                 "Wenn der Dienstleister schwer oder nicht ersetzbar ist, geben Sie den Grund an "
                 "(keine Alternativen, Migrationshürden oder beides)."),
    "BUS-021": E("Alternative Dienstleister nicht benannt",
                 "Alternatives are said to exist; name them.",
                 "Es sollen Alternativen existieren; benennen Sie diese."),
    "BUS-022": E("Kritischer Dienstleister nicht aktuell geprüft",
                 "Providers of critical services should be audited regularly. Record the date "
                 "of the last audit or plan one.",
                 "Dienstleister kritischer Leistungen sollten regelmäßig geprüft werden. Erfassen "
                 "Sie das Datum der letzten Prüfung oder planen Sie eine."),
    "BUS-023": E("Gruppeninterner Dienstleister ohne B_03.03",
                 "The provider is a group entity; list it in B_03.03 as the providing entity.",
                 "Der Dienstleister ist ein Gruppenunternehmen; erfassen Sie es in B_03.03 als "
                 "leistendes Unternehmen."),
    "BUS-024": E("Unbefristeter Vertrag mit ungewöhnlichem Enddatum",
                 "For contracts without an end date use 9999-12-31 instead of a far-future "
                 "placeholder.",
                 "Verwenden Sie für unbefristete Verträge 9999-12-31 statt eines Platzhalters in "
                 "ferner Zukunft."),
}


def explain(rule_id: str, lang: str = "en") -> str:
    entry = EXPLANATIONS.get(rule_id)
    if entry is None:
        rule = RULES.get(rule_id)
        return rule.description if rule else ""
    return entry.de if lang == "de" else entry.en


def rule_title(rule_id: str, lang: str = "en") -> str:
    entry = EXPLANATIONS.get(rule_id)
    if lang == "de" and entry is not None:
        return entry.title_de
    rule = RULES.get(rule_id)
    return rule.title if rule else rule_id
