"""Import a client's own contract inventory (arbitrary columns) into a draft register.

Workflow (used by the web wizard and usable programmatically)::

    sheet = read_inventory("Vertragsinventar.xlsx")
    mapping = {i: s.field for i, s in enumerate(suggest_mapping(sheet)) if s.field}
    raw, notes = build_raw(sheet, mapping, EntityInfo(lei=..., name=..., country="DE"))

The inventory is *contract-centric*: one row per contract (or per contract and service).
:func:`build_raw` derives B_01.01/B_01.02 from the entity details and B_02.01, B_02.02,
B_03.01, B_03.02, B_04.01, B_05.01, B_06.01 and (when assessment columns are mapped) B_07.01
from the rows. Values are normalised where this is unambiguous (``31.12.2025`` → ISO date,
``Deutschland`` → ``DE``, ``ja`` → ``true``, "Cloud-Hosting (SaaS)" → ``S19``); anything else is
kept verbatim so the validator reports it and the user can fix it in the browser.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import Path

from openpyxl import load_workbook

from dora_roi.io.raw import RawRegister, RawRow, RawTable, RawValue
from dora_roi.lei import is_valid_lei_format
from dora_roi.model import TEMPLATE_MODELS, CodeEnum, EntityType
from dora_roi.normalise import (
    country_code,
    criticality,
    currency_code,
    end_date,
    fold,
    service_type,
    substitutability,
    to_amount,
    to_bool,
    to_date,
    to_int,
)


class FieldKind(StrEnum):
    TEXT = "text"
    LEI = "lei"
    COUNTRY = "country"
    DATE = "date"
    END_DATE = "end_date"
    AMOUNT = "amount"
    CURRENCY = "currency"
    BOOL = "bool"
    SERVICE = "service"
    CRITICALITY = "criticality"
    SUBSTITUTABILITY = "substitutability"
    DAYS = "days"


@dataclass(frozen=True)
class InventoryField:
    key: str
    kind: FieldKind
    label_en: str
    label_de: str
    target: str
    synonyms: tuple[str, ...]


F = InventoryField
FIELDS: tuple[InventoryField, ...] = (
    F("contract_ref", FieldKind.TEXT, "Contract reference", "Vertragsnummer",
      "B_02.01 c0010", ("contract id", "contract no", "contract number", "contract ref",
                        "reference", "vertragsnummer", "vertrags id", "vertrag nr", "vertragsnr",
                        "vertrags nr", "contract")),
    F("provider_name", FieldKind.TEXT, "Provider name", "Name des Dienstleisters",
      "B_05.01 c0050", ("provider", "vendor", "supplier", "provider name", "vendor name",
                        "lieferant", "dienstleister", "anbieter", "auftragnehmer",
                        "vertragspartner", "name dienstleister")),
    F("provider_lei", FieldKind.LEI, "Provider LEI", "LEI des Dienstleisters", "B_05.01 c0010",
      ("lei", "provider lei", "vendor lei", "supplier lei", "lei lieferant",
       "lei dienstleister", "legal entity identifier")),
    F("provider_country", FieldKind.COUNTRY, "Provider country (HQ)",
      "Sitzland des Dienstleisters", "B_05.01 c0080",
      ("provider country", "vendor country", "supplier country", "country", "hq country",
       "land", "sitzland", "sitz", "herkunftsland", "domicile")),
    F("service", FieldKind.SERVICE, "ICT service (type or description)",
      "IKT-Leistung (Art oder Beschreibung)", "B_02.02 c0060",
      ("service", "service type", "service description", "description", "category",
       "leistung", "leistungsart", "leistungsbeschreibung", "beschreibung", "kategorie",
       "ict service", "art der leistung")),
    F("function_name", FieldKind.TEXT, "Business function supported",
      "Unterstützte Geschäftsfunktion", "B_06.01 c0030",
      ("function", "business function", "process", "business process", "funktion",
       "geschaftsfunktion", "geschaftsprozess", "prozess", "unterstutzte funktion")),
    F("critical", FieldKind.CRITICALITY, "Critical or important function?",
      "Kritische oder wichtige Funktion?", "B_06.01 c0050",
      ("critical", "criticality", "cif", "critical or important", "kritisch", "wesentlich",
       "kritikalitat", "kritische funktion", "kritisch ja nein", "wesentliche auslagerung")),
    F("start_date", FieldKind.DATE, "Start date", "Vertragsbeginn", "B_02.02 c0070",
      ("start", "start date", "valid from", "effective date", "beginn", "vertragsbeginn",
       "gultig ab", "laufzeit von", "startdatum")),
    F("end_date", FieldKind.END_DATE, "End date", "Vertragsende", "B_02.02 c0080",
      ("end", "end date", "valid to", "expiry", "expiry date", "ende", "vertragsende",
       "gultig bis", "laufzeit bis", "enddatum", "laufzeitende")),
    F("annual_cost", FieldKind.AMOUNT, "Annual cost", "Jahreskosten", "B_02.01 c0050",
      ("annual cost", "cost", "annual value", "contract value", "amount", "budget",
       "kosten", "jahreskosten", "jahresentgelt", "volumen", "betrag", "kosten p a",
       "jahrliche kosten")),
    F("currency", FieldKind.CURRENCY, "Currency", "Währung", "B_02.01 c0040",
      ("currency", "ccy", "wahrung", "wahr")),
    F("governing_law", FieldKind.COUNTRY, "Governing law (country)", "Anwendbares Recht",
      "B_02.02 c0120", ("governing law", "law", "applicable law", "rechtswahl",
                        "anwendbares recht", "gerichtsstand", "recht")),
    F("data_location", FieldKind.COUNTRY, "Data location (country)", "Datenstandort",
      "B_02.02 c0150", ("data location", "data center", "data centre", "hosting location",
                        "datenstandort", "speicherort", "rechenzentrum", "hosting standort",
                        "region")),
    F("data_storage", FieldKind.BOOL, "Provider stores data?", "Speichert Daten?",
      "B_02.02 c0140", ("data storage", "stores data", "personal data", "datenspeicherung",
                        "speichert daten", "personenbezogene daten", "daten gespeichert")),
    F("notice_period", FieldKind.DAYS, "Notice period (entity)", "Kündigungsfrist",
      "B_02.02 c0100", ("notice period", "notice", "kundigungsfrist", "kundigung")),
    F("substitutability", FieldKind.SUBSTITUTABILITY, "Substitutability", "Ersetzbarkeit",
      "B_07.01 c0050", ("substitutability", "substitutable", "ersetzbarkeit",
                        "austauschbarkeit", "ersetzbar")),
    F("exit_plan", FieldKind.BOOL, "Exit plan exists?", "Exit-Plan vorhanden?",
      "B_07.01 c0080", ("exit plan", "exit strategy", "exitplan", "exit strategie",
                        "exit plan vorhanden", "exit")),
)
FIELDS_BY_KEY: dict[str, InventoryField] = {f.key: f for f in FIELDS}


@dataclass
class InventorySheet:
    headers: list[str]
    rows: list[list[RawValue]]
    sheet_name: str = ""
    header_row: int = 1
    source: str = ""

    def column_samples(self, index: int, limit: int = 3) -> list[str]:
        out: list[str] = []
        for r in self.rows:
            v = r[index] if index < len(r) else None
            if v not in (None, ""):
                out.append(str(v))
            if len(out) >= limit:
                break
        return out


class InventoryError(ValueError):
    pass


def _find_header(rows: list[list[RawValue]]) -> int:
    for i, r in enumerate(rows[:15]):
        texts = [c for c in r if isinstance(c, str) and c.strip()]
        if len(texts) >= 2:
            return i
    raise InventoryError("no header row found (need a row with at least two column names)")


def _sheet_from_rows(rows: list[list[RawValue]], sheet: str, source: str) -> InventorySheet:
    if not rows:
        raise InventoryError("the file contains no data")
    h = _find_header(rows)
    width = max(len(r) for r in rows)
    headers = [str(c).strip() if c not in (None, "") else f"Column {i + 1}"
               for i, c in enumerate(rows[h] + [None] * (width - len(rows[h])))]
    data = [r + [None] * (width - len(r)) for r in rows[h + 1:]
            if any(c not in (None, "") for c in r)]
    # drop trailing all-empty columns
    while headers and headers[-1].startswith("Column ") and all(
            r[len(headers) - 1] in (None, "") for r in data):
        headers.pop()
        data = [r[: len(headers)] for r in data]
    return InventorySheet(headers, data, sheet, h + 1, source)


def read_inventory(path: str | Path, sheet: str | None = None) -> InventorySheet:
    """Read the first non-empty sheet (or ``sheet``) of an .xlsx file, or a CSV file."""
    p = Path(path)
    if p.suffix.lower() == ".csv":
        text = p.read_text(encoding="utf-8-sig")
        first = text.splitlines()[0] if text else ""
        delim = max((",", ";", "\t"), key=first.count)
        rows: list[list[RawValue]] = [list(r) for r in csv.reader(io.StringIO(text),
                                                                  delimiter=delim)]
        return _sheet_from_rows(rows, p.stem, p.name)
    wb = load_workbook(p, read_only=True, data_only=True)
    try:
        sheets = [wb[sheet]] if sheet else wb.worksheets
        for ws in sheets:
            values: list[list[RawValue]] = [
                [c if c is None or isinstance(c, str | int | float | date | Decimal) else str(c)
                 for c in r]
                for r in ws.iter_rows(values_only=True)]
            if any(any(c not in (None, "") for c in r) for r in values):
                return _sheet_from_rows(values, ws.title, p.name)
    finally:
        wb.close()
    raise InventoryError("the workbook contains no data")


# --------------------------------------------------------------------------- suggestions


class MatchConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    NONE = "none"


@dataclass(frozen=True)
class MappingSuggestion:
    column: int
    header: str
    field: str | None
    confidence: MatchConfidence
    reason: str


def _header_score(header: str, fld: InventoryField) -> float:
    h = fold(header)
    if not h:
        return 0.0
    names = (*fld.synonyms, fold(fld.label_en), fold(fld.label_de))
    if h in names:
        return 1.0
    best = 0.0
    for syn in names:
        if len(syn) >= 4 and (syn in h or h in syn):
            best = max(best, 0.8 if len(syn) > 5 else 0.7)
        best = max(best, SequenceMatcher(None, h, syn).ratio() * 0.85)
    return best


def _value_score(samples: list[str], fld: InventoryField) -> float:
    if not samples:
        return 0.0
    checks = {
        FieldKind.LEI: lambda s: bool(re.fullmatch(r"[A-Z0-9]{18}\d{2}", s.strip().upper())),
        FieldKind.DATE: lambda s: to_date(s) is not None,
        FieldKind.END_DATE: lambda s: end_date(s) is not None,
        FieldKind.CURRENCY: lambda s: currency_code(s) is not None,
    }
    check = checks.get(fld.kind)
    if check is None:
        return 0.0
    hits = sum(1 for s in samples if check(s))
    return 0.6 * hits / len(samples)


def suggest_mapping(sheet: InventorySheet) -> list[MappingSuggestion]:
    """Suggest a target field per column (each field used at most once)."""
    scored: list[tuple[float, int, InventoryField, str]] = []
    for i, header in enumerate(sheet.headers):
        samples = sheet.column_samples(i, 5)
        for fld in FIELDS:
            hs = _header_score(header, fld)
            vs = _value_score(samples, fld)
            score = max(hs, vs)
            if score >= 0.55:
                reason = (f"header '{header}' matches" if hs >= vs
                          else "values look like " + fld.label_en.lower())
                scored.append((score, i, fld, reason))
    scored.sort(key=lambda x: -x[0])
    taken_fields: set[str] = set()
    taken_cols: dict[int, MappingSuggestion] = {}
    for score, i, fld, reason in scored:
        if i in taken_cols or fld.key in taken_fields:
            continue
        conf = MatchConfidence.HIGH if score >= 0.9 else MatchConfidence.MEDIUM
        taken_cols[i] = MappingSuggestion(i, sheet.headers[i], fld.key, conf, reason)
        taken_fields.add(fld.key)
    return [taken_cols.get(i, MappingSuggestion(i, h, None, MatchConfidence.NONE, ""))
            for i, h in enumerate(sheet.headers)]


# --------------------------------------------------------------------------- normalisation


def normalise(kind: FieldKind, value: RawValue) -> RawValue:
    """Normalise one value for ``kind``; returns the original when not confident."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip() if not isinstance(value, date) else ""
    result: object = None
    if kind is FieldKind.TEXT:
        return str(value).strip() if not isinstance(value, float) or not value.is_integer() \
            else str(int(value))
    if kind is FieldKind.LEI:
        cleaned = re.sub(r"\s", "", text).upper()
        return cleaned if is_valid_lei_format(cleaned) else text
    if kind is FieldKind.COUNTRY:
        result = country_code(text)
    elif kind is FieldKind.DATE:
        result = to_date(value)
    elif kind is FieldKind.END_DATE:
        result = end_date(value)
    elif kind is FieldKind.AMOUNT:
        result = to_amount(value)
    elif kind is FieldKind.CURRENCY:
        result = currency_code(text)
    elif kind is FieldKind.BOOL:
        result = to_bool(value)
    elif kind is FieldKind.SERVICE:
        result = service_type(text)
    elif kind is FieldKind.CRITICALITY:
        result = criticality(value)
    elif kind is FieldKind.SUBSTITUTABILITY:
        result = substitutability(text)
    elif kind is FieldKind.DAYS:
        result = to_int(value)
    if result is None:
        return value if not isinstance(value, str) else value.strip()
    if isinstance(result, CodeEnum):
        return result.value
    if isinstance(result, bool):
        return "true" if result else "false"
    if isinstance(result, date | Decimal | int | str):
        return result
    return str(result)  # pragma: no cover - defensive


@dataclass(frozen=True)
class PreviewCell:
    original: RawValue
    value: RawValue

    @property
    def changed(self) -> bool:
        return str(self.original if self.original is not None else "") != \
            str(self.value if self.value is not None else "")


def preview(sheet: InventorySheet, mapping: dict[int, str], limit: int = 10
            ) -> list[dict[str, PreviewCell]]:
    out: list[dict[str, PreviewCell]] = []
    for r in sheet.rows[:limit]:
        row: dict[str, PreviewCell] = {}
        for col, key in mapping.items():
            original = r[col] if col < len(r) else None
            row[key] = PreviewCell(original, normalise(FIELDS_BY_KEY[key].kind, original))
        out.append(row)
    return out


# --------------------------------------------------------------------------- build


@dataclass
class EntityInfo:
    lei: str
    name: str
    country: str
    entity_type: str = EntityType.CREDIT_INSTITUTION.value
    competent_authority: str = ""
    reporting_date: date = field(default_factory=lambda: date(date.today().year - 1, 12, 31))
    currency: str = "EUR"


@dataclass
class BuildNotes:
    rows: int = 0
    normalised: int = 0
    placeholder_providers: list[str] = field(default_factory=list)
    generated_refs: int = 0
    functions: int = 0

    def summary(self) -> list[str]:
        out = [f"{self.rows} inventory rows imported", f"{self.normalised} values normalised"]
        if self.generated_refs:
            out.append(f"{self.generated_refs} contract references generated (INV-…)")
        if self.placeholder_providers:
            out.append(f"{len(self.placeholder_providers)} providers without LEI got a "
                       "placeholder code (TBD-…) – add their LEI")
        out.append(f"{self.functions} functions identified")
        return out


def _slug(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", fold(text).upper()).strip("-")[:30] or "UNKNOWN"


def build_raw(sheet: InventorySheet, mapping: dict[int, str], entity: EntityInfo
              ) -> tuple[RawRegister, BuildNotes]:
    """Turn inventory rows into a draft :class:`RawRegister`."""
    notes = BuildNotes()
    tables: dict[str, list[dict[str, RawValue]]] = defaultdict(list)
    lei = entity.lei.strip().upper()
    tables["B_01.01"].append({"c0010": lei, "c0020": entity.name, "c0030": entity.country,
                              "c0040": entity.entity_type,
                              "c0050": entity.competent_authority or None,
                              "c0060": entity.reporting_date})
    tables["B_01.02"].append({"c0010": lei, "c0020": entity.name, "c0030": entity.country,
                              "c0040": entity.entity_type, "c0050": "NOT_IN_GROUP",
                              "c0070": entity.reporting_date,
                              "c0080": entity.reporting_date.replace(month=1, day=17),
                              "c0100": entity.currency})
    providers: dict[str, dict[str, RawValue]] = {}
    provider_cost: dict[str, Decimal] = defaultdict(Decimal)
    functions: dict[str, tuple[str, RawValue]] = {}
    seen_refs: set[str] = set()
    for i, r in enumerate(sheet.rows, start=1):
        v: dict[str, RawValue] = {}
        for col, key in mapping.items():
            original = r[col] if col < len(r) else None
            value = normalise(FIELDS_BY_KEY[key].kind, original)
            if value is not None and str(value) != str(original).strip():
                notes.normalised += 1
            v[key] = value
        if all(x is None for x in v.values()):
            continue
        notes.rows += 1
        ref = str(v.get("contract_ref") or "")
        if not ref:
            ref = f"INV-{i:04d}"
            notes.generated_refs += 1
        name = str(v.get("provider_name") or "")
        lei_value = v.get("provider_lei")
        if isinstance(lei_value, str) and is_valid_lei_format(lei_value):
            pcode: str = lei_value
            ptype: RawValue = "LEI"
        else:
            pcode = "TBD-" + _slug(name or str(lei_value or f"PROVIDER-{i}"))
            ptype = None
            if pcode not in notes.placeholder_providers:
                notes.placeholder_providers.append(pcode)
        fname = str(v.get("function_name") or "Unspecified function")
        fkey = fold(fname)
        if fkey not in functions:
            functions[fkey] = (f"F-{len(functions) + 1:03d}", fname)
            tables["B_06.01"].append({"c0010": functions[fkey][0], "c0030": fname,
                                      "c0040": lei,
                                      "c0050": v.get("critical") or "NOT_ASSESSED"})
        fid = functions[fkey][0]
        currency = v.get("currency") or entity.currency
        cost = v.get("annual_cost")
        if ref not in seen_refs:
            seen_refs.add(ref)
            tables["B_02.01"].append({"c0010": ref, "c0020": "STANDALONE", "c0040": currency,
                                      "c0050": cost})
            tables["B_03.01"].append({"c0010": ref, "c0020": lei, "c0030": "true"})
            tables["B_03.02"].append({"c0010": ref, "c0020": pcode, "c0030": ptype,
                                      "c0040": "true"})
            tables["B_04.01"].append({"c0010": ref, "c0020": lei, "c0030": "false"})
            if isinstance(cost, Decimal):
                provider_cost[pcode] += cost
        storage = v.get("data_storage")
        if storage is None and v.get("data_location") is not None:
            storage = "true"
        country = v.get("provider_country")
        tables["B_02.02"].append({
            "c0010": ref, "c0020": lei, "c0030": pcode, "c0040": ptype, "c0050": fid,
            "c0060": v.get("service"), "c0070": v.get("start_date"), "c0080": v.get("end_date"),
            "c0100": v.get("notice_period"), "c0120": v.get("governing_law"),
            "c0130": country, "c0140": storage,
            "c0150": v.get("data_location") if storage == "true" else None,
            "c0160": v.get("data_location") if storage == "true" else None,
        })
        if v.get("substitutability") is not None or v.get("exit_plan") is not None:
            tables["B_07.01"].append({"c0010": ref, "c0020": pcode, "c0030": ptype,
                                      "c0040": v.get("service"), "c0050": v.get("substitutability"),
                                      "c0080": v.get("exit_plan")})
        if pcode not in providers:
            providers[pcode] = {"c0010": pcode, "c0020": ptype, "c0050": name or None,
                                "c0070": "LEGAL", "c0080": country, "c0090": currency,
                                "c0110": pcode, "c0120": ptype}
        elif providers[pcode].get("c0080") is None and country is not None:
            providers[pcode]["c0080"] = country
    for code, prow in providers.items():
        prow["c0100"] = provider_cost.get(code)
        tables["B_05.01"].append(prow)
    notes.functions = len(functions)
    raw = RawRegister(source=sheet.source or "inventory")
    for model in TEMPLATE_MODELS:
        rows = [RawRow(n, values) for n, values in enumerate(tables.get(model.TEMPLATE, []),
                                                              start=2)]
        raw.tables[model.TEMPLATE] = RawTable(model.TEMPLATE, [c.code for c in model.columns()],
                                              rows, source=f"{raw.source}:{model.TEMPLATE}")
    return raw, notes
