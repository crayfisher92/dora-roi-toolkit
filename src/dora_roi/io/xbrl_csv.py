"""**Best-effort** export to (and re-import from) an xBRL-CSV report package.

.. warning::

   The EBA publishes the authoritative DPM, taxonomy and filing rules for the DORA register of
   information. This module reproduces the *structure* of an xBRL-CSV report package as the
   authors understand it (``docs/ASSUMPTIONS.md`` A-XBRL-*): a zip containing
   ``META-INF/reportPackage.json`` and a ``reports`` folder with ``report.json``,
   ``parameters.csv``, ``FilingIndicators.csv`` and one CSV per template. Taxonomy entry
   point, package naming, parameter values and – above all – the mapping of enumerated values
   to taxonomy members **must be checked and configured** before any supervisory submission.
   A package produced with the default settings is suitable for testing pipelines and
   reviewing content, not for filing.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from dora_roi import __version__
from dora_roi.io.csv_folder import read_csv_files, register_to_csv_texts
from dora_roi.io.raw import RawRegister
from dora_roi.model import TEMPLATE_MODELS, TEMPLATES_BY_CODE, RegisterOfInformation
from dora_roi.model.types import Kind

DEFAULT_ENTRY_POINT = "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/dora/4.0/mod/dora.json"
COUNTRY_PREFIX = "eba_GA:"
CURRENCY_PREFIX = "eba_CU:"
BEST_EFFORT_NOTICE = (
    "BEST-EFFORT EXPORT: package structure, naming, parameters and enumeration mapping follow "
    "the toolkit's assumptions (docs/ASSUMPTIONS.md A-XBRL-*) and must be verified against the "
    "EBA DORA taxonomy and filing rules in force before submission."
)

CodeMap = dict[str, dict[str, str]]


@dataclass
class XbrlCsvOptions:
    """Parameters of the generated package. Every default is an assumption (see module doc)."""

    entry_point: str = DEFAULT_ENTRY_POINT
    #: Consolidation level suffix used in entityID and package name (CON, IND or SUB).
    reporting_level: str = "CON"
    #: Prefix of the entityID parameter value.
    entity_scheme: str = "rs"
    #: Module code used in the package file name.
    module_code: str = "DORA010100"
    module_name: str = "DORA"
    decimals_monetary: int = 0
    decimals_integer: int = 0
    #: ``{code list name: {internal code: taxonomy member}}`` overrides, e.g.
    #: ``{"IctServiceType": {"S01": "eba_TA:S01"}}``.
    code_map: CodeMap = field(default_factory=dict)
    #: Fixed timestamp for reproducible packages (defaults to now, UTC).
    created_at: datetime | None = None
    #: Override of the package (zip) base name.
    package_name: str | None = None


@dataclass
class ExportResult:
    path: Path
    package_name: str
    files: list[str]
    warnings: list[str]


def load_code_map(path: str | Path) -> CodeMap:
    """Load a JSON code map ``{"CodeListName": {"CODE": "eba_XX:xNN"}}``."""
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


class _ValueMapper:
    def __init__(self, code_map: CodeMap) -> None:
        self.code_map = code_map
        self.unmapped: dict[str, set[str]] = {}

    def __call__(self, template: str, column: str, value: str) -> str:
        spec = TEMPLATES_BY_CODE[template].column_by_code(column)
        if spec is None:
            return value
        kind = spec.col.kind
        if kind is Kind.COUNTRY:
            return COUNTRY_PREFIX + value
        if kind is Kind.CURRENCY:
            return CURRENCY_PREFIX + value
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

    def mapper(template: str, column: str, value: str) -> str:
        spec = TEMPLATES_BY_CODE[template].column_by_code(column)
        if spec is None:
            return value
        kind = spec.col.kind
        for prefix, k in ((COUNTRY_PREFIX, Kind.COUNTRY), (CURRENCY_PREFIX, Kind.CURRENCY)):
            if kind is k and value.startswith(prefix):
                return value[len(prefix):]
        if kind is Kind.CODELIST and spec.col.codelist is not None:
            return inverse.get(spec.col.codelist.__name__, {}).get(value, value)
        return value

    return mapper


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
    mapper = _ValueMapper(options.code_map)
    tables = register_to_csv_texts(register, value_mapper=mapper, include_empty=False)
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
        warnings.append(
            f"{len(mapper.unmapped)} code list(s) exported with toolkit-internal codes because no "
            f"taxonomy mapping was supplied ({', '.join(sorted(mapper.unmapped))}); pass a code "
            "map (--code-map) with the EBA taxonomy members"
        )

    report_json = {
        "documentInfo": {
            "documentType": "https://xbrl.org/2021/xbrl-csv",
            "extends": [options.entry_point],
        },
        "x-dora-roi-toolkit": {
            "version": __version__,
            "notice": BEST_EFFORT_NOTICE,
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
    indicators = "templateID,reported\n" + "".join(
        f"{mdl.TEMPLATE},{'true' if register.records(mdl.TEMPLATE) else 'false'}\n"
        for mdl in TEMPLATE_MODELS
    )
    files: dict[str, str] = {
        "META-INF/reportPackage.json": json.dumps(
            {"documentInfo": {"documentType": "https://xbrl.org/report-package/2023"}}, indent=2),
        "reports/report.json": json.dumps(report_json, indent=2),
        "reports/parameters.csv": parameters,
        "reports/FilingIndicators.csv": indicators,
    }
    for name, text in tables.items():
        files[f"reports/{name}"] = text
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


def is_xbrl_package(path: str | Path) -> bool:
    p = Path(path)
    if p.is_dir():
        return any(p.rglob("report.json"))
    if p.suffix.lower() == ".zip" and zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as zf:
            return any(n.endswith("reports/report.json") for n in zf.namelist())
    return False


def read_xbrl_csv(path: str | Path, code_map: CodeMap | None = None) -> RawRegister:
    """Read a package written by :func:`export_xbrl_csv` (zip or folder) back to raw tables."""
    p = Path(path)
    files: list[tuple[str, str]] = []
    skip = {"parameters.csv", "filingindicators.csv"}
    indicators = ""
    if p.is_dir():
        for f in sorted(p.rglob("reports/*.csv")):
            text = f.read_text(encoding="utf-8-sig")
            if f.name.lower() == "filingindicators.csv":
                indicators = text
            elif f.name.lower() not in skip:
                files.append((f.name, text))
    else:
        with zipfile.ZipFile(p) as zf:
            for n in sorted(zf.namelist()):
                base = n.rsplit("/", 1)[-1]
                if "/reports/" not in f"/{n}" or not base.lower().endswith(".csv"):
                    continue
                text = io.TextIOWrapper(zf.open(n), encoding="utf-8-sig").read()
                if base.lower() == "filingindicators.csv":
                    indicators = text
                elif base.lower() not in skip:
                    files.append((base, text))
    raw = read_csv_files(files, p.name, mapper=_reverse_mapper(code_map or {}))
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
        if len(parts) >= 2 and parts[1].lower() == "false":
            out.add(parts[0])
    return out
