from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from dora_roi.analytics import analyse
from dora_roi.api import validate_path
from dora_roi.cli import main
from dora_roi.lei import is_valid_lei
from dora_roi.reporting.executive import render_executive_summary
from dora_roi.sample import SampleResult, generate_sample, synthetic_lei
from dora_roi.validation import Severity, validate


@pytest.fixture(scope="module")
def dirty() -> SampleResult:
    return generate_sample()


@pytest.fixture(scope="module")
def clean() -> SampleResult:
    return generate_sample(inject_errors=False)


def test_synthetic_lei_is_valid_and_deterministic() -> None:
    a = synthetic_lei("Example AG")
    assert is_valid_lei(a) and a == synthetic_lei("Example AG")
    assert a != synthetic_lei("Example AG ")


def test_sample_size_matches_brief(clean: SampleResult) -> None:
    c = clean.register.counts()
    assert c["B_01.02"] == 3
    assert 38 <= c["B_05.01"] <= 50
    assert 100 <= c["B_02.01"] <= 140
    assert max(e.rank or 0 for e in clean.register.b_05_02) == 3
    names = {p.legal_name for p in clean.register.b_05_01}
    assert {"Nimbus Cloud Services EMEA Ltd", "Stratus Compute Corp.",
            "Cirrus Platforms Ireland Ltd"} <= names
    assert {e.country for e in clean.register.b_01_02} == {"DE", "LU", "AT"}


def test_sample_is_deterministic() -> None:
    a = generate_sample(seed=7, inject_errors=False).register.model_dump()
    b = generate_sample(seed=7, inject_errors=False).register.model_dump()
    assert a == b
    assert a != generate_sample(seed=8, inject_errors=False).register.model_dump()


def test_clean_sample_passes(clean: SampleResult) -> None:
    report = validate(clean.register, parse_findings=clean.findings)
    assert report.severity_counts()["error"] == 0
    assert report.severity_counts()["warning"] == 0
    assert {f.rule_id for f in report.findings} == {"XRF-014"}  # Swiss holding out of scope


def test_every_injected_error_is_detected(dirty: SampleResult) -> None:
    report = validate(dirty.register, parse_findings=dirty.findings)
    found = {f.rule_id for f in report.findings}
    assert len(dirty.injected) >= 20
    for err in dirty.injected:
        missing = set(err.rule_ids) - found
        assert not missing, f"{err.description}: {missing} not reported"
    assert not report.passed
    assert any(f.severity is Severity.WARNING for f in report.findings)


def test_sample_file_roundtrip(dirty: SampleResult, tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "s.xlsx"
    assert runner.invoke(main, ["sample", str(out)]).exit_code == 0
    _, report = validate_path(out)
    in_memory = validate(dirty.register, parse_findings=dirty.findings)
    assert report.severity_counts() == in_memory.severity_counts()
    res = runner.invoke(main, ["sample", str(tmp_path / "csv"), "--format", "csv", "--clean"])
    assert res.exit_code == 0 and "0 injected" in res.stderr
    _, report = validate_path(tmp_path / "csv")
    assert report.passed
    res = runner.invoke(main, ["template", str(tmp_path / "t.xlsx"), "--sample", "--clean"])
    assert res.exit_code == 0
    assert validate_path(tmp_path / "t.xlsx")[1].passed


def test_sample_analytics(clean: SampleResult) -> None:
    a = analyse(clean.register)
    assert a.groups[0].spend_share < 0.5
    nimbus = next(g for g in a.groups if g.group_name == "Nimbus Cloud Inc.")
    assert len(nimbus.providers) == 2 and nimbus.critical_functions >= 5
    assert a.subcontractors and a.max_chain_rank == 3
    assert any(k.level.value == "high" for k in a.key_findings)
    html = render_executive_summary(clean.register, validate(clean.register))
    assert "Alpenrand Bank (Europe) AG" in html
