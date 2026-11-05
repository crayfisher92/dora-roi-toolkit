"""Tests for the modules behind the web workbench (workspace, fixes, quality, diff, …)."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner
from openpyxl import Workbook

from dora_roi.cli import main
from dora_roi.diff import diff_registers, render_diff_markdown
from dora_roi.explain import EXPLANATIONS, explain, rule_title
from dora_roi.fixes import Confidence, bulk_groups, findings_by_template, suggest
from dora_roi.graph import build_graph, chains_table, render_svg
from dora_roi.inventory import (
    FIELDS,
    EntityInfo,
    FieldKind,
    InventoryError,
    MatchConfidence,
    build_raw,
    normalise,
    preview,
    read_inventory,
    suggest_mapping,
)
from dora_roi.lei import make_lei
from dora_roi.model import Criticality, IctServiceType, RegisterOfInformation, Substitutability
from dora_roi.normalise import (
    closest_code,
    country_code,
    criticality,
    currency_code,
    end_date,
    service_type,
    substitutability,
    to_amount,
    to_bool,
    to_date,
    to_int,
)
from dora_roi.quality import Readiness, quality_score
from dora_roi.sample import generate_previous_year, generate_sample, register_to_raw
from dora_roi.sample.inventory_sample import write_sample_inventory
from dora_roi.validation import RULES, Category, Finding, Severity, validate
from dora_roi.workspace import EditError, Workspace

from conftest import ENTITY, build_valid_register


def _finding(rule: str, value: str | None, template: str = "B_02.02", column: str = "c0120",
             row: int = 4) -> Finding:
    return Finding(rule_id=rule, severity=Severity.ERROR, category=Category.FIELD,
                   message="m", template=template, column=column, row=row, value=value)


@pytest.fixture
def ws() -> Workspace:
    return Workspace("valid", register_to_raw(build_valid_register()))


@pytest.fixture(scope="module")
def dirty_ws() -> Workspace:
    r = generate_sample()
    return Workspace("dirty", register_to_raw(r.source_register), kind="sample")


# ------------------------------------------------------------------ normalise


@pytest.mark.parametrize(("text", "code"), [
    ("Deutschland", "DE"), ("UK", "GB"), ("Österreich", "AT"), ("switzerland", "CH"),
    ("Germnay", "DE"), ("de", "DE"), ("El", "GR"), ("Atlantis", None), ("", None)])
def test_country_code(text: str, code: str | None) -> None:
    assert country_code(text) == code


def test_normalise_helpers() -> None:
    assert currency_code("Euro") == "EUR" and currency_code("chf") == "CHF"
    assert currency_code("doubloons") is None
    assert to_date("31.12.2025") == date(2025, 12, 31)
    assert to_date("2025/03/01") == date(2025, 3, 1)
    assert to_date(45657) == date(2024, 12, 31)
    assert to_date("2025-01-02T10:00") == date(2025, 1, 2)
    assert to_date("31.02.2025") is None and to_date(None) is None
    assert end_date("unbefristet") == date(9999, 12, 31)
    assert to_amount("1.234.567,89 €") == Decimal("1234567.89")
    assert to_amount("EUR 12k") == Decimal(12000)
    assert to_amount("1,234.5") == Decimal("1234.5")
    assert to_amount(12.5) == Decimal("12.5")
    assert to_amount("abc") is None and to_amount(True) is None and to_amount(None) is None
    assert to_int("90 Tage") == 90 and to_int("3 Monate") == 90 and to_int("1 year") == 365
    assert to_int(30.0) == 30 and to_int(True) is None and to_int("none") is None
    assert to_bool("ja") is True and to_bool("Nein") is False and to_bool("vielleicht") is None
    assert to_bool(1) is True
    assert service_type("Cloud-Software (SaaS)") is IctServiceType.S19
    assert service_type("Wartung") is IctServiceType.S14 and service_type("xyz") is None
    assert criticality("wesentlich") is Criticality.CRITICAL
    assert criticality("unkritisch") is Criticality.NOT_CRITICAL
    assert criticality("ja") is Criticality.CRITICAL and criticality("?") is None
    assert substitutability("hoch") is Substitutability.HIGHLY_COMPLEX
    assert substitutability("EASY") is Substitutability.EASY
    assert closest_code(IctServiceType, "S1 9") is IctServiceType.S19
    assert closest_code(IctServiceType, "zzzzzz") is None


# ------------------------------------------------------------------ explanations


def test_every_rule_explained_in_both_languages() -> None:
    assert set(EXPLANATIONS) == set(RULES)
    for rid, e in EXPLANATIONS.items():
        assert e.en and e.de and e.title_de, rid
    assert "GB" in explain("FLD-005") and "GB" in explain("FLD-005", "de")
    assert rule_title("BUS-019", "de").startswith("Kein Exit-Plan")
    assert rule_title("BUS-019") == RULES["BUS-019"].title
    assert explain("NOPE") == "" and rule_title("NOPE") == "NOPE"


# ------------------------------------------------------------------ fixes


@pytest.mark.parametrize(("rule", "value", "column", "expected", "conf"), [
    ("FLD-005", "UK", "c0120", "GB", Confidence.HIGH),
    ("FLD-003", "31/12/2027", "c0080", "2027-12-31", Confidence.HIGH),
    ("FLD-004", "S20", "c0060", "S12", Confidence.LOW),
    ("FLD-008", "ja", "c0140", "true", Confidence.HIGH),
    ("FLD-002", "529900t8bm49aursdo55", "c0020", "529900T8BM49AURSDO55", Confidence.HIGH),
    ("FLD-002", "529900T8BM49AURSDO56", "c0020", "529900T8BM49AURSDO55", Confidence.LOW),
    ("BUS-024", "2090-01-01", "c0080", "9999-12-31", Confidence.HIGH),
])
def test_suggestions(rule: str, value: str, column: str, expected: str,
                     conf: Confidence) -> None:
    s = suggest(_finding(rule, value, column=column))
    assert s is not None and s.value == expected and s.confidence is conf


def test_currency_and_link_suggestions() -> None:
    s = suggest(_finding("FLD-006", "EURO", "B_02.01", "c0040"))
    assert s is not None and s.value == "EUR"
    s = suggest(_finding("FLD-001", None, "B_03.01", "c0030"))
    assert s is not None and s.value == "true"
    s = suggest(_finding("SC-004", "X", "B_05.02", "c0060"))
    assert s is not None and s.value == ""
    assert suggest(_finding("FLD-005", "Atlantis")) is None
    assert suggest(_finding("BUS-019", "false", "B_07.01", "c0080")) is None
    assert suggest(_finding("FLD-004", "S20", "B_99.99", "c0060")) is None


def test_bulk_groups_and_grouping() -> None:
    fs = [_finding("FLD-005", "UK", row=r) for r in (4, 5, 6)] + [
        _finding("FLD-005", "XX", row=7), _finding("FLD-001", None, column="c0100", row=4),
        _finding("FLD-001", None, column="c0100", row=5),
        Finding(rule_id="FLD-011", severity=Severity.ERROR, category=Category.FIELD,
                message="m")]
    groups = bulk_groups(fs)
    assert [(g.value, g.count) for g in groups] == [("UK", 3), ("", 2)]
    assert groups[0].suggestion is not None and groups[0].suggestion.value == "GB"
    by_t = findings_by_template(fs)
    assert set(by_t) == {"B_02.02", "register"} and len(by_t["B_02.02"]["error"]) == 6


# ------------------------------------------------------------------ quality


def test_quality_score(ws: Workspace, dirty_ws: Workspace) -> None:
    q = ws.quality
    assert q.score == 100 and q.readiness is Readiness.READY
    d = dirty_ws.quality
    assert 80 < d.score < 100 and d.readiness is Readiness.NOT_READY
    empty = Workspace("e", register_to_raw(build_valid_register().model_copy(
        update={k: [] for k in RegisterOfInformation.model_fields})))
    assert empty.quality.readiness is Readiness.EMPTY and empty.quality.score == 0
    ws.edit("B_02.02", 4, "c0120", "")
    q2 = ws.quality
    assert q2.readiness is Readiness.ALMOST and q2.records_with_errors == 1
    ws.edit("B_06.01", 4, "c0050", "NOT_ASSESSED")
    assert ws.quality.records_with_warnings_only >= 1


def test_quality_register_level_cap() -> None:
    reg = build_valid_register()
    reg.b_06_01.clear()
    report = validate(reg)
    assert quality_score(report).score <= 50


# ------------------------------------------------------------------ workspace


def test_workspace_edit_and_versions(ws: Workspace) -> None:
    assert ws.report.passed and len(ws.versions) == 1
    change = ws.edit("B_02.02", 4, "c0120", "UK")
    assert change is not None and change.old == "DE" and change.new == "UK"
    assert {f.rule_id for f in ws.findings_for("B_02.02", 4)} == {"FLD-005"}
    assert ws.rows_with_findings("B_02.02").keys() == {4}
    assert ws.edit("B_02.02", 4, "c0120", "UK") is None  # unchanged
    ws.edit("B_02.02", 4, "c0120", " GB ")
    assert ws.report.passed and len(ws.versions) == 3
    rec = ws.record("B_02.02", 4)
    assert rec is not None and rec.governing_law_country == "GB"
    assert ws.record("B_02.02", 99) is None
    old = ws.register_at(2)
    assert old.b_02_02[0].governing_law_country is None
    with pytest.raises(EditError):
        ws.version(999)
    with pytest.raises(EditError):
        ws.edit("B_99.99", 4, "c0010", "x")
    with pytest.raises(EditError):
        ws.edit("B_02.02", 4, "c9999", "x")
    with pytest.raises(EditError):
        ws.edit("B_02.02", 99, "c0010", "x")
    with pytest.raises(EditError):
        ws.table("B_99.99")


def test_workspace_bulk_add_delete(ws: Workspace) -> None:
    n = ws.add_row("B_06.01", {"c0010": "F-NEW", "c0040": ENTITY, "c0050": "NOT_CRITICAL"})
    assert n == 5 and ws.record("B_06.01", n) is not None
    assert "FLD-001" in {f.rule_id for f in ws.findings_for("B_06.01", n)}
    assert ws.bulk_replace("B_06.01", "c0020", "", "Payment services", rows=[n]) == 1
    ws.delete_row("B_06.01", n)
    assert ws.record("B_06.01", n) is None
    assert ws.bulk_replace("B_02.02", "c0120", "DE", "AT") == 1
    assert ws.bulk_replace("B_02.02", "c0120", "XX", "AT") == 0
    assert ws.analysis.totals["contracts"] == 1


def test_workspace_export_keeps_raw_values(ws: Workspace, tmp_path: Path) -> None:
    from dora_roi.io.excel import write_workbook
    from dora_roi.io.loader import load

    ws.edit("B_02.02", 4, "c0120", "UK")
    path = write_workbook(ws.export_register(), tmp_path / "x.xlsx")
    loaded = load(path)
    assert "FLD-005" in {f.rule_id for f in loaded.findings}


def test_sample_workspace_bulk_fix(dirty_ws: Workspace) -> None:
    before = dirty_ws.report.severity_counts()["error"]
    f = next(f for f in dirty_ws.report.findings if f.rule_id == "FLD-005")
    s = suggest(f)
    assert s is not None and f.template and f.row and f.column
    dirty_ws.edit(f.template, f.row, f.column, s.value)
    assert dirty_ws.report.severity_counts()["error"] == before - 1


# ------------------------------------------------------------------ diff


def test_diff_previous_year() -> None:
    old = generate_previous_year()
    new = generate_sample(inject_errors=False)
    assert validate(old.register, parse_findings=old.findings).passed
    d = diff_registers(old.register, new.register, "2024", "2025")
    contracts = d.get("B_02.01")
    assert len(contracts.added) == 5 and len(contracts.removed) == 1
    assert d.get("B_05.01").removed[0][1] == "Legacy Mainframe Services GmbH"
    assert d.new_spend > d.old_spend and not d.is_empty
    md = render_diff_markdown(d)
    assert "**removed** Legacy Mainframe Services GmbH" in md
    same = diff_registers(new.register, new.register)
    assert same.is_empty and all(t.total == 0 for t in same.templates)


def test_cli_diff_and_samples(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(main, ["sample", str(tmp_path / "p.xlsx"),
                                "--previous-year"]).exit_code == 0
    assert runner.invoke(main, ["sample", str(tmp_path / "c.xlsx"), "--clean"]).exit_code == 0
    res = runner.invoke(main, ["diff", str(tmp_path / "p.xlsx"), str(tmp_path / "c.xlsx")])
    assert res.exit_code == 0 and "Register comparison" in res.output
    res = runner.invoke(main, ["diff", str(tmp_path / "p.xlsx"), str(tmp_path / "c.xlsx"),
                               "-f", "json", "-o", str(tmp_path / "d.json")])
    assert res.exit_code == 0 and '"old_label"' in (tmp_path / "d.json").read_text()
    res = runner.invoke(main, ["sample", str(tmp_path / "inv.xlsx"), "--inventory"])
    assert res.exit_code == 0 and (tmp_path / "inv.xlsx").exists()


# ------------------------------------------------------------------ inventory


def test_inventory_wizard_end_to_end(tmp_path: Path) -> None:
    path = write_sample_inventory(tmp_path / "inv.xlsx")
    sheet = read_inventory(path)
    assert sheet.header_row == 3 and sheet.headers[0] == "Vertragsnummer" and len(sheet.rows) > 40
    sug = suggest_mapping(sheet)
    mapped = {s.header: s.field for s in sug}
    assert mapped["Vertragsnummer"] == "contract_ref"
    assert mapped["Kritisch (ja/nein)"] == "critical"
    assert mapped["Bemerkung"] is None
    assert all(s.confidence is MatchConfidence.HIGH for s in sug if s.field)
    mapping = {s.column: s.field for s in sug if s.field}
    prev = preview(sheet, mapping, limit=3)
    assert len(prev) == 3 and prev[0]["start_date"].changed
    entity = EntityInfo(lei=generate_sample().register.b_01_01[0].lei or "", name="Alpenrand",
                        country="DE", competent_authority="BaFin",
                        reporting_date=date(2025, 12, 31))
    raw, notes = build_raw(sheet, mapping, entity)
    assert notes.rows == len(sheet.rows) and notes.normalised > 100
    assert notes.placeholder_providers and any("placeholder" in s for s in notes.summary())
    work = Workspace("inv", raw, kind="inventory")
    reg = work.register
    assert len(reg.b_02_01) == notes.rows and reg.b_05_01 and reg.b_06_01
    assert reg.b_02_02[0].start_date is not None
    assert any(f.is_critical for f in reg.b_06_01)
    rules = {f.rule_id for f in work.report.findings}
    assert "FLD-001" in rules and "FLD-005" not in rules


def test_inventory_csv_value_suggestions_and_errors(tmp_path: Path) -> None:
    p = tmp_path / "inv.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Supplier", "Col B", "Ref", "Kickoff"])
        w.writerow(["Acme", make_lei("ACMEACMEACMEACME01"), "", "01.02.2024"])
        w.writerow(["Acme", make_lei("ACMEACMEACMEACME01"), "", "2024-05-01"])
    sheet = read_inventory(p)
    sug = {s.header: s for s in suggest_mapping(sheet)}
    assert sug["Supplier"].field == "provider_name"
    assert sug["Col B"].field == "provider_lei" and "values look like" in sug["Col B"].reason
    mapping = {s.column: s.field for s in sug.values() if s.field}
    raw, notes = build_raw(sheet, mapping, EntityInfo(lei=ENTITY, name="X", country="DE"))
    assert notes.generated_refs == 2 and len(raw.tables["B_05.01"].rows) == 1
    empty = tmp_path / "empty.csv"
    empty.write_text("")
    with pytest.raises(InventoryError):
        read_inventory(empty)
    one = tmp_path / "one.csv"
    one.write_text("only\n1\n")
    with pytest.raises(InventoryError):
        read_inventory(one)
    wb = Workbook()
    wb.save(tmp_path / "blank.xlsx")
    with pytest.raises(InventoryError):
        read_inventory(tmp_path / "blank.xlsx")


def test_normalise_kinds() -> None:
    assert normalise(FieldKind.TEXT, 12.0) == "12"
    assert normalise(FieldKind.LEI, " 529900t8bm49aursdo55 ") == "529900T8BM49AURSDO55"
    assert normalise(FieldKind.LEI, "n/a") == "n/a"
    assert normalise(FieldKind.COUNTRY, "Irland") == "IE"
    assert normalise(FieldKind.COUNTRY, "Atlantis") == "Atlantis"
    assert normalise(FieldKind.BOOL, "nein") == "false"
    assert normalise(FieldKind.SERVICE, "SaaS") == "S19"
    assert normalise(FieldKind.DAYS, "90 Tage") == 90
    assert normalise(FieldKind.AMOUNT, "") is None
    assert normalise(FieldKind.CURRENCY, "€") == "EUR"
    assert {f.key for f in FIELDS} >= {"contract_ref", "provider_lei", "exit_plan"}


# ------------------------------------------------------------------ graph


def test_dependency_graph() -> None:
    reg = generate_sample(inject_errors=False).register
    g = build_graph(reg)
    assert g.nodes and g.edges and g.levels >= 3
    for e in g.edges:
        assert g.nodes[e.target].level > g.nodes[e.source].level
    assert all(e.source != e.target for e in g.edges)
    full = build_graph(reg, with_isolated=True)
    assert len(full.nodes) > len(g.nodes)
    crit = build_graph(reg, critical_only=True)
    assert all(n.critical for n in crit.nodes.values())
    nimbus = next(p.provider_code for p in reg.b_05_01
                  if p.legal_name == "Nimbus Cloud Services EMEA Ltd")
    assert nimbus
    focus = build_graph(reg, focus=nimbus)
    assert nimbus in focus.nodes and len(focus.nodes) < len(g.nodes)
    svg = render_svg(g, color_by="region", link_prefix="/p/")
    assert svg.startswith("<svg") and 'href="/p/' in svg and "--series-4" in svg
    assert "--series-muted" in render_svg(g)
    assert "No providers" in render_svg(build_graph(build_valid_register().model_copy(
        update={"b_05_02": [], "b_02_02": []})))
    chains = chains_table(reg)
    assert chains and all(len(c) >= 2 for _, c in chains)
    assert all("Nimbus Cloud Services EMEA Ltd" in c for _, c in chains_table(reg, nimbus))
