"""A deliberately messy, German-language contract inventory for the column-mapping wizard.

It mimics what a consultant typically receives from a client's procurement tool: a title
row above the header, German column names, ``31.12.2025`` dates, "unbefristet", amounts like
``1.234.567,00 €``, country names instead of ISO codes, ``ja``/``nein`` flags, free-text
service descriptions, a few missing LEIs and an irrelevant comments column.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from dora_roi.model import IctServiceType, Substitutability
from dora_roi.model.types import INDEFINITE_END_DATE
from dora_roi.sample.generator import generate_sample

HEADERS = ("Vertragsnummer", "Lieferant", "LEI Lieferant", "Sitzland", "Leistungsbeschreibung",
           "Geschäftsfunktion", "Kritisch (ja/nein)", "Vertragsbeginn", "Vertragsende",
           "Jahreskosten", "Währung", "Datenstandort", "Exit-Plan vorhanden", "Ersetzbarkeit",
           "Bemerkung")

_COUNTRY_DE = {"DE": "Deutschland", "AT": "Österreich", "CH": "Schweiz", "IE": "Irland",
               "LU": "Luxemburg", "FR": "Frankreich", "NL": "Niederlande", "BE": "Belgien",
               "IT": "Italien", "GB": "Vereinigtes Königreich", "US": "USA", "HU": "Ungarn",
               "PL": "Polen", "RO": "Rumänien", "SE": "Schweden", "GR": "Griechenland"}
_SERVICE_DE = {
    IctServiceType.S01: "IT-Projektmanagement", IctServiceType.S02: "Softwareentwicklung",
    IctServiceType.S03: "Helpdesk / 1st-Level-Support", IctServiceType.S04: "IT-Sicherheit (SOC)",
    IctServiceType.S05: "Marktdaten", IctServiceType.S06: "Datenanalyse (Analytics)",
    IctServiceType.S07: "Rechenzentrum / Colocation", IctServiceType.S08: "Verarbeitung",
    IctServiceType.S09: "Archiv / Backup", IctServiceType.S10: "Telekommunikation (Carrier)",
    IctServiceType.S11: "Netzwerk", IctServiceType.S12: "Hardware",
    IctServiceType.S13: "Softwarelizenz", IctServiceType.S14: "Betrieb und Wartung",
    IctServiceType.S15: "IT-Beratung", IctServiceType.S16: "IKT-Risikomanagement",
    IctServiceType.S17: "Cloud IaaS", IctServiceType.S18: "Cloud-Plattform (PaaS)",
    IctServiceType.S19: "Cloud-Software (SaaS)",
}
_SUBST_DE = {Substitutability.NOT_SUBSTITUTABLE: "nicht ersetzbar",
             Substitutability.HIGHLY_COMPLEX: "hoch", Substitutability.MEDIUM: "mittel",
             Substitutability.EASY: "niedrig"}


def _de_amount(value: Decimal) -> str:
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def inventory_rows(limit: int | None = None) -> list[list[object]]:
    """Rows of the messy inventory, derived from the clean Alpenrand sample (DE entity)."""
    reg = generate_sample(inject_errors=False).register
    de_lei = reg.b_01_01[0].lei
    providers = reg.providers_by_code()
    contracts = reg.contracts_by_ref()
    functions = reg.function_lookup()
    assessments = reg.assessments_by_key()
    rows: list[list[object]] = []
    seen: set[str] = set()
    for i, s in enumerate(x for x in reg.b_02_02 if x.entity_lei == de_lei):
        if s.contract_ref in seen or s.contract_ref is None:
            continue
        seen.add(s.contract_ref)
        p = providers.get(s.provider_code or "")
        c = contracts.get(s.contract_ref)
        fn = functions.get((s.function_id or "", s.entity_lei or ""))
        a = assessments.get((s.contract_ref, s.provider_code, s.service_type))
        lei = "" if i % 9 == 4 or (p and p.provider_code_type and
                                   p.provider_code_type.value != "LEI") else s.provider_code
        start: date | None = s.start_date
        end: date | None = s.end_date
        rows.append([
            s.contract_ref,
            p.legal_name if p else "",
            lei,
            _COUNTRY_DE.get(p.hq_country or "", p.hq_country) if p else "",
            _SERVICE_DE.get(s.service_type, "") if s.service_type else "",
            fn.function_name if fn else "",
            "ja" if fn and fn.is_critical else "nein",
            start.strftime("%d.%m.%Y") if start else "",
            "unbefristet" if end == INDEFINITE_END_DATE else (end.strftime("%d.%m.%Y")
                                                              if end else ""),
            _de_amount(c.annual_cost) if c and c.annual_cost is not None else "",
            "EUR",
            _COUNTRY_DE.get(s.data_location_storage or "", "") if s.data_storage else "",
            ("ja" if a.exit_plan else "nein") if a else "",
            _SUBST_DE.get(a.substitutability, "") if a and a.substitutability else "",
            "Verlängerung in Prüfung" if i % 7 == 3 else "",
        ])
        if limit and len(rows) >= limit:
            break
    return rows


def write_sample_inventory(path: str | Path, limit: int | None = None) -> Path:
    """Write the messy inventory workbook (title row, blank row, header, data)."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Vertragsinventar"
    ws.append(["Vertragsinventar IKT-Dienstleister – Alpenrand Bank (Europe) AG – "
               "Stand 31.12.2025"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(list(HEADERS))
    for cell in ws[3]:
        cell.font = Font(bold=True)
    for r in inventory_rows(limit):
        ws.append(r)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
