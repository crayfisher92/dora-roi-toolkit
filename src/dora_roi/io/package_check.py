"""Compare an xBRL-CSV report package with a reference package (e.g. an official EBA sample).

The comparison is structural and format-agnostic, so that it works with whatever sample the
EBA or a competent authority publishes:

* package layout (``META-INF/reportPackage.json``, ``reports/report.json`` …) and naming;
* ``report.json`` document type and taxonomy entry point;
* ``parameters.csv`` parameter names and value styles (``rs:…``, ``iso4217:…``);
* ``FilingIndicators.csv`` header and template-ID style;
* table files present, their header columns and order;
* per column, the *style* of enumerated values (e.g. reference uses ``eba_GA:DE`` where ours
  has ``DE``) – this pinpoints which code lists still need a taxonomy mapping.

Usage: ``roi check-package OFFICIAL.zip [--ours OURS.zip]``.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Status(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class Check:
    area: str
    status: Status
    message: str


@dataclass
class Package:
    name: str
    files: dict[str, str]  # path relative to package root -> text

    def csv(self, path: str) -> list[list[str]]:
        text = self.files.get(path, "")
        return list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))


@dataclass
class PackageComparison:
    reference: str
    ours: str
    checks: list[Check] = field(default_factory=list)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status is Status.FAIL]

    def add(self, area: str, status: Status, message: str) -> None:
        self.checks.append(Check(area, status, message))

    def to_markdown(self) -> str:
        icon = {Status.OK: "✅", Status.WARN: "⚠️", Status.FAIL: "❌"}
        counts = Counter(c.status for c in self.checks)
        lines = [f"# Package comparison: `{self.ours}` vs reference `{self.reference}`", "",
                 f"{counts[Status.OK]} ok · {counts[Status.WARN]} warnings · "
                 f"{counts[Status.FAIL]} failures", "", "| | Area | Finding |", "|---|---|---|"]
        lines += [f"| {icon[c.status]} | {c.area} | {c.message.replace('|', '/')} |"
                  for c in self.checks]
        lines.append("")
        return "\n".join(lines)


def read_package(path: str | Path) -> Package:
    """Read a zip or folder package; paths are made relative to the package root."""
    p = Path(path)
    raw: dict[str, str] = {}
    if p.is_dir():
        for f in p.rglob("*"):
            if f.is_file():
                raw[f.relative_to(p).as_posix()] = f.read_text(encoding="utf-8-sig",
                                                               errors="replace")
    else:
        with zipfile.ZipFile(p) as zf:
            for n in zf.namelist():
                if not n.endswith("/"):
                    raw[n] = zf.read(n).decode("utf-8-sig", errors="replace")
    roots = {k.split("/", 1)[0] for k in raw if "/" in k}
    files = raw
    if len(roots) == 1 and not any(k.startswith(("META-INF/", "reports/")) for k in raw):
        root = next(iter(roots))
        files = {k[len(root) + 1:]: v for k, v in raw.items() if k.startswith(root + "/")}
    return Package(p.stem if p.suffix else p.name, files)


def _value_style(value: str) -> str:
    """Abstract a value to its style: ``eba_GA:*``, ``date``, ``number``, ``bool``, ``text``."""
    v = value.strip()
    if not v:
        return "empty"
    m = re.match(r"^([A-Za-z_]+[A-Za-z0-9_]*):", v)
    if m:
        return f"{m.group(1)}:*"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return "date"
    if re.fullmatch(r"-?\d+(\.\d+)?", v):
        return "number"
    if v.lower() in ("true", "false"):
        return "bool"
    return "text"


def _name_shape(name: str) -> str:
    """Shape of a package name: letters → A, digits → 9 (runs collapsed), separators kept."""
    shape = re.sub(r"[A-Za-z]+", "A", name)
    return re.sub(r"\d+", "9", shape)


def compare_packages(reference: str | Path, ours: str | Path) -> PackageComparison:
    ref, our = read_package(reference), read_package(ours)
    out = PackageComparison(ref.name, our.name)

    # -- naming
    if _name_shape(ref.name) == _name_shape(our.name):
        out.add("naming", Status.OK, f"package name shape matches ({_name_shape(ref.name)})")
    else:
        out.add("naming", Status.WARN, f"package name '{our.name}' differs in shape from "
                f"reference '{ref.name}'")

    # -- layout
    for required in sorted(p for p in ref.files if not p.endswith(".csv")):
        status = Status.OK if required in our.files else Status.FAIL
        out.add("layout", status, f"{required} {'present' if status is Status.OK else 'missing'}")
    extra_meta = sorted(p for p in our.files if not p.endswith(".csv") and p not in ref.files)
    for p in extra_meta:
        out.add("layout", Status.WARN, f"{p} is not in the reference package")

    # -- report.json
    def report(pkg: Package) -> dict[str, object]:
        try:
            data = json.loads(pkg.files.get("reports/report.json", "{}"))
            info = data.get("documentInfo", {}) if isinstance(data, dict) else {}
            return info if isinstance(info, dict) else {}
        except json.JSONDecodeError:
            return {}

    r_info, o_info = report(ref), report(our)
    for key in ("documentType", "extends"):
        if key not in r_info:
            continue
        same = r_info.get(key) == o_info.get(key)
        out.add("report.json", Status.OK if same else Status.FAIL,
                f"{key}: ours {o_info.get(key)!r}" + ("" if same else
                                                       f" vs reference {r_info.get(key)!r}"))

    # -- parameters.csv
    def params(pkg: Package) -> dict[str, str]:
        rows = pkg.csv("reports/parameters.csv")
        return {r[0]: (r[1] if len(r) > 1 else "") for r in rows[1:] if r}

    rp, op = params(ref), params(our)
    for name in sorted(rp.keys() | op.keys()):
        if name not in op:
            out.add("parameters", Status.FAIL, f"parameter '{name}' missing")
        elif name not in rp:
            out.add("parameters", Status.WARN, f"parameter '{name}' not in reference")
        elif _value_style(rp[name]) != _value_style(op[name]):
            out.add("parameters", Status.FAIL, f"'{name}': value style "
                    f"{_value_style(op[name])} vs reference {_value_style(rp[name])} "
                    f"(ours {op[name]!r}, reference {rp[name]!r})")
        else:
            out.add("parameters", Status.OK, f"'{name}' ({_value_style(rp[name])})")

    # -- filing indicators
    rf, of = ref.csv("reports/FilingIndicators.csv"), our.csv("reports/FilingIndicators.csv")
    if rf:
        out.add("filing indicators", Status.OK if rf[0] == (of[0] if of else []) else Status.FAIL,
                f"header {of[0] if of else '—'}" + ("" if of and rf[0] == of[0]
                                                    else f" vs reference {rf[0]}"))
        r_ids = {r[0] for r in rf[1:] if r}
        o_ids = {r[0] for r in of[1:] if r}
        missing = sorted(r_ids - o_ids)
        if missing:
            out.add("filing indicators", Status.FAIL, f"template IDs not in ours: {missing}")
        else:
            out.add("filing indicators", Status.OK, f"{len(r_ids)} template IDs match")

    # -- tables
    skip = {"reports/parameters.csv", "reports/filingindicators.csv"}
    r_tables = {p for p in ref.files if p.endswith(".csv") and p.lower() not in skip}
    o_tables = {p for p in our.files if p.endswith(".csv") and p.lower() not in skip}
    for p in sorted(r_tables - o_tables):
        out.add("tables", Status.WARN, f"{p} in reference but not in ours (empty template?)")
    for p in sorted(o_tables - r_tables):
        out.add("tables", Status.WARN, f"{p} in ours but not in reference")
    for p in sorted(r_tables & o_tables):
        rr, orows = ref.csv(p), our.csv(p)
        rh, oh = (rr[0] if rr else []), (orows[0] if orows else [])
        if rh == oh:
            out.add("tables", Status.OK, f"{p}: header matches ({len(rh)} columns)")
        else:
            out.add("tables", Status.FAIL, f"{p}: columns only in reference "
                    f"{sorted(set(rh) - set(oh))}, only in ours {sorted(set(oh) - set(rh))}"
                    + (", order differs" if set(rh) == set(oh) else ""))
        for col in sorted(set(rh) & set(oh)):
            ri, oi = rh.index(col), oh.index(col)
            r_styles = {_value_style(r[ri]) for r in rr[1:] if len(r) > ri} - {"empty"}
            o_styles = {_value_style(r[oi]) for r in orows[1:] if len(r) > oi} - {"empty"}
            if r_styles and o_styles and r_styles != o_styles:
                out.add("values", Status.FAIL, f"{p} {col}: ours {sorted(o_styles)} vs "
                        f"reference {sorted(r_styles)}")
    return out
