"""Export to (and re-import from) an xBRL-CSV report package for the DORA register.

The package follows the EBA DORA reporting framework 4.0 as published in ``reference/eba/``
(official sample instance, annotated table layout, list of possible values, technical checks):

* a zip containing ``META-INF/reportPackage.json`` and ``reports/`` with ``report.json``
  (extending the DORA module entry point), ``parameters.csv``, ``FilingIndicators.csv`` and
  one ``b_XX.YY.csv`` per template;
* **every** template is reported – empty templates as a header-only file – and every filing
  indicator is ``true`` (technical check 808), including ``B_99.01``;
* closed lists are written as taxonomy members (``eba_CT:x12``, ``eba_BT:x28`` …) using the
  official code map in :mod:`dora_roi.model.eba_codes` (overridable per value);
* the ESAs' conventions for empty key fields are applied (EBA RoI FAQ Q26, Q58–Q65, Q124):
  "Not Applicable", ``eba_GA:qx2007``, the entity's own LEI as parent and the provider's own
  code as rank-1 recipient.

.. warning::

   This is still not an official EBA/ESA tool. The framework version, entry point and
   parameters must match what the competent authority accepts for the reference date, and the
   package should be run through the authority's own validation before filing.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from dora_roi.io.csv_folder import read_csv_files, register_to_csv_texts
from dora_roi.io.limits import check_archive
from dora_roi.io.raw import RawRegister
from dora_roi.model import TEMPLATE_MODELS, TEMPLATES_BY_CODE, RegisterOfInformation
from dora_roi.model.eba_codes import (
    BOOLEAN_MEMBERS,
    CODE_MAP,
    COUNTRY_NOT_APPLICABLE,
    EBA_COUNTRIES,
    EBA_CURRENCIES,
    FRAMEWORK,
    TEXT_NOT_APPLICABLE,
    licensed_activity_code,
    licensed_activity_label,
)
from dora_roi.model.templates import NO_DIRECT_PARENT
from dora_roi.model.types import Kind

DEFAULT_ENTRY_POINT = "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/dora/4.0/mod/dora.json"
COUNTRY_PREFIX = "eba_GA:"
CURRENCY_PREFIX = "eba_CU:"
#: Consolidation levels accepted in ``entityID`` and the package name (``rs:<LEI>.CON|IND``).
REPORTING_LEVELS = ("CON", "IND")
BEST_EFFORT_NOTICE = (
    f"BEST-EFFORT EXPORT: package layout, code lists and conventions follow the {FRAMEWORK} "
    "as published by the EBA (see reference/eba and docs/ASSUMPTIONS.md); this is not an "
    "official tool – check the framework version in force for the reference date and run the "
    "competent authority's validation before filing."
)

#: Templates the DPM defines in addition to the toolkit's 14: B_99.01 (definitions from
#: entities making use of the ICT services) is reported empty with a ``true`` indicator.
EXTRA_TEMPLATES: dict[str, list[str]] = {
    "B_99.01": [f"c{n:04d}" for n in range(10, 200, 10)],
}

CodeMap = dict[str, dict[str, str]]

_LICENSED_COLUMN = ("B_06.01", "c0020")


@dataclass
class XbrlCsvOptions:
    """Parameters of the generated package."""

    entry_point: str = DEFAULT_ENTRY_POINT
    #: Consolidation level suffix used in entityID and package name (CON or IND).
    reporting_level: str = "CON"
    #: Prefix of the entityID parameter value.
    entity_scheme: str = "rs"
    #: Module code used in the package file name.
    module_code: str = "DORA010100"
    module_name: str = "DORA"
    decimals_monetary: int = 0
    decimals_integer: int = 0
    #: ``{code list name: {internal code: taxonomy member}}`` overrides applied on top of the
    #: official code map (:data:`dora_roi.model.eba_codes.CODE_MAP`).
    code_map: CodeMap = field(default_factory=dict)
    #: Start from the official code map (switch off only to test custom maps in isolation).
    use_default_code_map: bool = True
    #: Fixed timestamp for reproducible packages (defaults to now, UTC).
    created_at: datetime | None = None
    #: Override of the package (zip) base name.
    package_name: str | None = None

    def __post_init__(self) -> None:
        if self.reporting_level not in REPORTING_LEVELS:
            raise ValueError(f"reporting level must be one of {', '.join(REPORTING_LEVELS)}, "
                             f"not {self.reporting_level!r}")

    def effective_code_map(self) -> CodeMap:
        base: CodeMap = (
            {name: dict(values) for name, values in CODE_MAP.items()}
            if self.use_default_code_map else {}
        )
        for name, values in self.code_map.items():
            base.setdefault(name, {}).update(values)
        return base


@dataclass
class ExportResult:
    path: Path
    package_name: str
    files: list[str]
    warnings: list[str]


def load_code_map(path: str | Path) -> CodeMap:
    """Load a JSON code map ``{"CodeListName": {"CODE": "eba_XX:xNN"}}`` (overrides)."""
    from dora_roi.model import ALL_CODELISTS

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("code map must be a JSON object of objects")
    lists = {cl.__name__: {m.value for m in cl} for cl in ALL_CODELISTS}
    out: CodeMap = {}
    for name, mapping in data.items():
        if str(name).startswith("_"):
            continue  # comments
        if not isinstance(mapping, dict):
            raise ValueError(f"code map entry {name!r} must be an object")
        if name not in lists:
            raise ValueError(f"unknown code list {name!r} (known: {', '.join(sorted(lists))})")
        unknown = set(mapping) - lists[name]
        if unknown:
            raise ValueError(f"{name}: unknown code(s) {', '.join(sorted(unknown))}")
        out[str(name)] = {str(a): str(b) for a, b in mapping.items()}
    return out


# --------------------------------------------------------------------------- conventions


def _fill_conventions(template: str, row: dict[str, str | None]) -> dict[str, str | None]:
    """Apply the ESAs' conventions for empty key / foreign-key fields to a serialised row."""
    out = dict(row)
    if template == "B_01.02":
        # FAQ Q58: an entity without a direct parent repeats its own LEI
        no_parent = {h.value for h in NO_DIRECT_PARENT}
        if not out.get("c0060") and out.get("c0050") in no_parent:
            out["c0060"] = out.get("c0010")
    elif template == "B_02.01":
        if not out.get("c0030"):  # FAQ Q124 (foreign key)
            out["c0030"] = TEXT_NOT_APPLICABLE
    elif template == "B_02.02":
        for col in ("c0130", "c0150", "c0160"):  # FAQ Q59, Q61, Q63 (keys)
            if not out.get(col):
                out[col] = COUNTRY_NOT_APPLICABLE
    elif template == "B_04.01":
        if not out.get("c0040"):  # FAQ Q64 (key)
            out["c0040"] = TEXT_NOT_APPLICABLE
    elif template == "B_05.02" and out.get("c0050") == "1" and not out.get("c0060"):
        # FAQ Q65: the direct provider is its own recipient
        out["c0060"] = out.get("c0030")
        out["c0070"] = out.get("c0070") or out.get("c0040")
    return out


class _ValueMapper:
    def __init__(self, code_map: CodeMap) -> None:
        self.code_map = code_map
        self.unmapped: dict[str, set[str]] = {}
        self.outside_dpm: set[str] = set()

    def __call__(self, template: str, column: str, value: str) -> str:
        if template == _LICENSED_COLUMN[0] and column == _LICENSED_COLUMN[1]:
            code = licensed_activity_code(value)
            if code is None:
                self.unmapped.setdefault("licensed activity (B_06.01 c0020)", set()).add(value)
                return value
            return code
        spec = TEMPLATES_BY_CODE[template].column_by_code(column)
        if spec is None:
            return value
        kind = spec.col.kind
        if kind is Kind.COUNTRY:
            if value == COUNTRY_NOT_APPLICABLE:
                return COUNTRY_PREFIX + value
            if value not in EBA_COUNTRIES:
                self.outside_dpm.add(f"country {value}")
            return COUNTRY_PREFIX + value
        if kind is Kind.CURRENCY:
            if value not in EBA_CURRENCIES:
                self.outside_dpm.add(f"currency {value}")
            return CURRENCY_PREFIX + value
        if kind is Kind.BOOLEAN:
            members = BOOLEAN_MEMBERS.get((template, column))
            if members is None:
                return value  # technical "Link" columns: true
            return members[0] if value == "true" else members[1]
        if kind is Kind.CODELIST and spec.col.codelist is not None:
            name = spec.col.codelist.__name__
            mapped = self.code_map.get(name, {}).get(value)
            if mapped is None:
                self.unmapped.setdefault(name, set()).add(value)
                return value
            return mapped
        return value


def _reverse_mapper(code_map: CodeMap) -> Any:
    inverse = {name: {v: k for k, v in m.items()} for name, m in code_map.items()}
    booleans = {key: {t: "true", f: "false"} for key, (t, f) in BOOLEAN_MEMBERS.items()}

    def mapper(template: str, column: str, value: str) -> str:
        if template == _LICENSED_COLUMN[0] and column == _LICENSED_COLUMN[1]:
            return licensed_activity_label(value)
        spec = TEMPLATES_BY_CODE[template].column_by_code(column)
        if spec is None:
            return value
        kind = spec.col.kind
        if kind is Kind.COUNTRY and value == COUNTRY_PREFIX + COUNTRY_NOT_APPLICABLE:
            return ""
        for prefix, k in ((COUNTRY_PREFIX, Kind.COUNTRY), (CURRENCY_PREFIX, Kind.CURRENCY)):
            if kind is k and value.startswith(prefix):
                return value[len(prefix):]
        if kind is Kind.BOOLEAN:
            return booleans.get((template, column), {}).get(value, value)
        if kind is Kind.CODELIST and spec.col.codelist is not None:
            return inverse.get(spec.col.codelist.__name__, {}).get(value, value)
        return value

    return mapper


# --------------------------------------------------------------------------- export


def package_name(register: RegisterOfInformation, options: XbrlCsvOptions) -> str:
    if options.package_name:
        return options.package_name
    m = register.maintainer
    lei = (m.lei if m else None) or "UNKNOWNLEI"
    country = (m.country if m else None) or "XX"
    ref: date = (m.reporting_date if m else None) or date.today()
    ts = (options.created_at or datetime.now(UTC)).strftime("%Y%m%d%H%M%S%f")[:-3]
    return (f"{lei}.{options.reporting_level}_{country}_{options.module_code}_"
            f"{options.module_name}_{ref.isoformat()}_{ts}")


def build_package_files(
    register: RegisterOfInformation, options: XbrlCsvOptions | None = None
) -> tuple[dict[str, str], list[str]]:
    """Return ``{relative path inside 'reports/' or 'META-INF/': text}`` and warnings."""
    options = options or XbrlCsvOptions()
    mapper = _ValueMapper(options.effective_code_map())
    tables = register_to_csv_texts(register, value_mapper=mapper, include_empty=True,
                                   row_filler=_fill_conventions)
    m = register.maintainer
    lei = (m.lei if m else None) or "UNKNOWNLEI"
    ref = register.reference_date
    currency = register.reporting_currency or "EUR"
    warnings = [BEST_EFFORT_NOTICE]
    if m is None or m.lei is None:
        warnings.append("B_01.01 has no valid LEI; entityID and package name use a placeholder")
    if ref is None:
        warnings.append("B_01.01 has no reporting date; refPeriod parameter left empty")
    if mapper.unmapped:
        details = "; ".join(f"{name}: {', '.join(sorted(values))}"
                            for name, values in sorted(mapper.unmapped.items()))
        warnings.append(
            f"value(s) without a taxonomy member, exported as given and likely to fail EBA "
            f"check 503 – {details}")
    if mapper.outside_dpm:
        warnings.append(
            "value(s) not in the DPM country/currency hierarchies of the framework, likely to "
            f"fail EBA check 503: {', '.join(sorted(mapper.outside_dpm))}")
    empty = [mdl.TEMPLATE for mdl in TEMPLATE_MODELS if not register.records(mdl.TEMPLATE)]
    if empty:
        warnings.append(f"template(s) reported empty: {', '.join(empty)}")

    report_json = {
        "documentInfo": {
            "documentType": "https://xbrl.org/2021/xbrl-csv",
            "extends": [options.entry_point],
        },
    }
    parameters = (
        "name,value\n"
        f"entityID,{options.entity_scheme}:{lei}.{options.reporting_level}\n"
        f"refPeriod,{ref.isoformat() if ref else ''}\n"
        f"baseCurrency,iso4217:{currency}\n"
        f"decimalsInteger,{options.decimals_integer}\n"
        f"decimalsMonetary,{options.decimals_monetary}\n"
    )
    template_ids = [mdl.TEMPLATE for mdl in TEMPLATE_MODELS] + list(EXTRA_TEMPLATES)
    # technical check 808: every filing indicator is true, empty templates are still reported
    indicators = "templateID,reported\n" + "".join(f"{t},true\n" for t in template_ids)
    files: dict[str, str] = {
        "META-INF/reportPackage.json": json.dumps(
            {"documentInfo": {"documentType": "https://xbrl.org/report-package/2023"}}, indent=2),
        "reports/report.json": json.dumps(report_json, indent=2),
        "reports/parameters.csv": parameters,
        "reports/FilingIndicators.csv": indicators,
    }
    for name, text in tables.items():
        files[f"reports/{name}"] = text
    for template, columns in EXTRA_TEMPLATES.items():
        files[f"reports/{template.lower()}.csv"] = ",".join(columns) + "\n"
    return files, warnings


def export_xbrl_csv(
    register: RegisterOfInformation,
    out: str | Path,
    options: XbrlCsvOptions | None = None,
    *,
    unzipped: bool = False,
) -> ExportResult:
    """Write an xBRL-CSV report package.

    ``out`` may be a ``.zip`` path or a directory (the package is then named with
    :func:`package_name`). With ``unzipped=True`` the package folder is written instead of a
    zip, which is convenient for review and diffing.
    """
    options = options or XbrlCsvOptions()
    files, warnings = build_package_files(register, options)
    out_path = Path(out)
    if out_path.suffix.lower() == ".zip":
        name = options.package_name or out_path.stem
        target = out_path
    else:
        name = package_name(register, options)
        target = out_path / (name if unzipped else f"{name}.zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    if unzipped:
        root = target.with_suffix("") if target.suffix == ".zip" else target
        for rel, text in files.items():
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
        target = root
    else:
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel, text in files.items():
                zf.writestr(f"{name}/{rel}", text)
    return ExportResult(target, name, sorted(files), warnings)


# --------------------------------------------------------------------------- import


def is_xbrl_package(path: str | Path) -> bool:
    p = Path(path)
    if p.is_dir():
        return any(p.rglob("report.json"))
    if p.suffix.lower() == ".zip" and zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as zf:
            return any(n.endswith("reports/report.json") for n in zf.namelist())
    return False


#: Files of a package that are not toolkit templates.
_SKIP = {"parameters.csv", "filingindicators.csv"} | {
    f"{t.lower()}.csv" for t in EXTRA_TEMPLATES}


def read_xbrl_csv(path: str | Path, code_map: CodeMap | None = None,
                  *, use_default_code_map: bool = True) -> RawRegister:
    """Read an xBRL-CSV package (zip or folder) back to raw tables.

    Taxonomy members are translated back with the official code map plus ``code_map``
    overrides; the "Not Applicable" conventions are read as empty values by the model.
    """
    effective = XbrlCsvOptions(code_map=code_map or {},
                               use_default_code_map=use_default_code_map).effective_code_map()
    p = Path(path)
    files: list[tuple[str, str]] = []
    indicators = ""
    if p.is_dir():
        for f in sorted(p.rglob("reports/*.csv")):
            text = f.read_text(encoding="utf-8-sig")
            if f.name.lower() == "filingindicators.csv":
                indicators = text
            elif f.name.lower() not in _SKIP:
                files.append((f.name, text))
    else:
        check_archive(p)
        with zipfile.ZipFile(p) as zf:
            for n in sorted(zf.namelist()):
                base = n.rsplit("/", 1)[-1]
                if "/reports/" not in f"/{n}" or not base.lower().endswith(".csv"):
                    continue
                text = io.TextIOWrapper(zf.open(n), encoding="utf-8-sig").read()
                if base.lower() == "filingindicators.csv":
                    indicators = text
                elif base.lower() not in _SKIP:
                    files.append((base, text))
    raw = read_csv_files(files, p.name, mapper=_reverse_mapper(effective))
    not_reported = _not_reported(indicators)
    raw.findings = [
        f for f in raw.findings if not (f.rule_id == "IMP-002" and f.template in not_reported)
    ]
    return raw


def _not_reported(indicators: str) -> set[str]:
    """Templates whose filing indicator is ``false`` (absent files are then expected)."""
    out: set[str] = set()
    for line in indicators.splitlines()[1:]:
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 2 and parts[1].lower() in {"false", "0"}:
            out.add(parts[0])
    return out
