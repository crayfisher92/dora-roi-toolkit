"""Swiss angle: mapping of RoI data to FINMA Circ. 2018/3 and 2023/1 requirements."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from dora_roi.cli import main
from dora_roi.contracts import AssessmentBook, ContractAssessment, evaluate
from dora_roi.finma import (
    OPRISK,
    OUTSOURCING,
    REQUIREMENTS,
    Coverage,
    FieldRef,
    evaluate_finma,
    fill_rate,
    mapping_markdown,
)
from dora_roi.incidents import Answers, Incident, IncidentLog
from dora_roi.model import TEMPLATES_BY_CODE, RegisterOfInformation
from dora_roi.sample import generate_sample
from dora_roi.sample.assessments import sample_assessments
from dora_roi.sample.incidents import sample_incidents

from conftest import build_valid_register


def test_requirements_are_well_formed() -> None:
    ids = [r.id for r in REQUIREMENTS]
    assert len(ids) == len(set(ids)) == 24
    assert {r.circular for r in REQUIREMENTS} == {OUTSOURCING, OPRISK}
    for r in REQUIREMENTS:
        for f in r.fields:  # every referenced column exists in the data model
            assert TEMPLATES_BY_CODE[f.template].column_by_code(f.column) is not None, f
            assert f.label and str(f).startswith("B_")
        assert r.title("de") and r.topic("de") and r.gap("de")
        if r.coverage is Coverage.NONE:
            assert not r.fields and not r.art30
    assert "FIN-OS-11" in mapping_markdown() and "FINMA-Zuordnung" in mapping_markdown("de")


def test_fill_rate_respects_conditions(valid_register: RegisterOfInformation) -> None:
    assert fill_rate(valid_register, FieldRef("B_06.01", "c0080", "critical")) == 1.0
    assert fill_rate(valid_register, FieldRef("B_05.02", "c0060", "subcontractor")) == 1.0
    assert fill_rate(valid_register, FieldRef("B_03.03", "c0020")) is None
    assert fill_rate(RegisterOfInformation(), FieldRef("B_05.01", "c0050")) is None
    with pytest.raises(KeyError):
        fill_rate(valid_register, FieldRef("B_05.01", "c0999"))


def test_evaluation_without_and_with_programme_data() -> None:
    reg = generate_sample().register
    bare = evaluate_finma(reg)
    by_id = {s.requirement.id: s for s in bare.statuses}
    assert by_id["FIN-OS-02"].effective is Coverage.FULL
    assert by_id["FIN-OS-05"].effective is Coverage.NONE
    assert by_id["FIN-OS-11"].effective is Coverage.NONE  # only Art. 30 evidence, none given
    assert by_id["FIN-OS-14"].effective is Coverage.FULL  # nothing applicable to measure
    now = datetime(2026, 1, 15, tzinfo=UTC)
    full = evaluate_finma(reg, evaluate(reg, sample_assessments(reg)),
                          sample_incidents(reg, now), now)
    by_id = {s.requirement.id: s for s in full.statuses}
    assert by_id["FIN-OS-11"].effective is Coverage.PARTIAL
    assert 0 < (by_id["FIN-OS-11"].art30_share or 0) < 0.2
    assert by_id["FIN-OR-07"].incidents_classified == 1.0
    assert full.coverage_score > bare.coverage_score
    assert full.counts(OUTSOURCING)["full"] == 5 and sum(full.counts().values()) == 24
    assert len(full.by_circular(OPRISK)) == 10
    ctx = full.context
    assert ctx.swiss_entities == 0 and "Helix Core Banking AG" in [n for _, n in
                                                                    ctx.swiss_providers]
    assert 0.2 < ctx.swiss_spend_share < 0.6 and ctx.providers_outside_eea_ch > 0


def test_full_coverage_needs_complete_data() -> None:
    reg = build_valid_register()
    reg.b_05_01[0].hq_country = None
    reg.b_05_01[1].hq_country = None
    s = {x.requirement.id: x for x in evaluate_finma(reg).statuses}
    assert s["FIN-OS-02"].effective is Coverage.PARTIAL and s["FIN-OS-02"].completeness == 0
    empty = evaluate_finma(RegisterOfInformation())
    assert all(x.effective is not Coverage.FULL for x in empty.statuses)
    assert empty.context.swiss_spend_share == 0.0


def test_unassessed_portfolio_and_undetermined_incidents() -> None:
    reg = build_valid_register()
    pf = evaluate(reg, AssessmentBook())
    log = IncidentLog()
    log.save(Incident(id="I", title="t", detected_at=datetime(2025, 1, 1, tzinfo=UTC),
                      answers=Answers()), "created")
    s = {x.requirement.id: x for x in evaluate_finma(reg, pf, log).statuses}
    assert s["FIN-OS-11"].art30_share is None and s["FIN-OR-07"].incidents_classified == 0.0
    book = AssessmentBook()
    a = ContractAssessment(contract_ref="C-001")
    for pid in ("30.3.e.i", "30.3.e.iii"):
        a.set(pid, "present")
    book.save(a)
    s = {x.requirement.id: x for x in evaluate_finma(reg, evaluate(reg, book)).statuses}
    assert s["FIN-OS-11"].art30_share == 1.0


def test_cli_finma(tmp_path: Path) -> None:
    runner = CliRunner()
    reg = tmp_path / "s.xlsx"
    r = runner.invoke(main, ["sample", str(reg), "--assessments", str(tmp_path / "a.json"),
                             "--incidents", str(tmp_path / "i.json")])
    assert r.exit_code == 0
    r = runner.invoke(main, ["finma", str(reg), "--assessments", str(tmp_path / "a.json"),
                             "--incidents", str(tmp_path / "i.json")])
    assert r.exit_code == 0 and "Coverage score 56%" in r.output
    r = runner.invoke(main, ["finma", str(reg), "-f", "json", "-o", str(tmp_path / "f.json"),
                             "--lang", "de"])
    data = json.loads((tmp_path / "f.json").read_text())
    assert data["schema"] == "dora-roi-toolkit/finma-mapping/v1"
    assert data["requirements"][0]["coverage_in_register"] == "partial"
    r = runner.invoke(main, ["finma", str(reg), "-f", "md"])
    assert r.exit_code == 0 and "| FIN-OR-09 |" in r.output
