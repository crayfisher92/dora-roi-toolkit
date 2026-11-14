"""The data model against the official EBA material in ``reference/eba`` (framework 4.0)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

from dora_roi.model import TEMPLATE_MODELS, TEMPLATES_BY_CODE
from dora_roi.model.eba_codes import OFFICIAL_CHECKS
from dora_roi.validation import RULES
from dora_roi.validation.eba_mapping import CHECK_NOTES, RULE_CHECKS, coverage, eba_checks

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = ROOT / "reference" / "eba" / "annotated-table-layout-dora-4.0-2024-12-17.xlsx"


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_eba_codes",
                                                  ROOT / "scripts" / "gen_eba_codes.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def layout(gen: ModuleType) -> dict[str, tuple[list[str], set[str]]]:
    """``{template: (column codes in layout order, primary-key column codes)}``."""
    out: dict[str, tuple[list[str], set[str]]] = {}
    current: str | None = None
    positions: dict[int, str] = {}
    for row in gen.read_rows(LAYOUT):
        first = next((c for c in row if c), "")
        title = re.match(r"^(B_\d\d\.\d\d) - ", first)
        if title:
            current, positions = title.group(1), {}
            continue
        if current is None:
            continue
        cells = [c for c in row if c]
        if not positions and cells and all(re.fullmatch(r"\d{4}", c) for c in cells):
            positions = {i: f"c{c}" for i, c in enumerate(row) if c}
            out[current] = (list(positions.values()), set())
        elif positions:
            for i, cell in enumerate(row):
                if "<Key value>" in cell and i in positions:
                    out[current][1].add(positions[i])
    return out


def test_layout_lists_exactly_our_templates(
        layout: dict[str, tuple[list[str], set[str]]]) -> None:
    assert set(layout) == {m.TEMPLATE for m in TEMPLATE_MODELS}


@pytest.mark.parametrize("model", TEMPLATE_MODELS, ids=lambda m: m.TEMPLATE)
def test_columns_match_annotated_layout(
        model: type, layout: dict[str, tuple[list[str], set[str]]]) -> None:
    codes, _ = layout[model.TEMPLATE]
    assert [c.code for c in model.columns()] == codes


@pytest.mark.parametrize("model", TEMPLATE_MODELS, ids=lambda m: m.TEMPLATE)
def test_primary_keys_match_annotated_layout(
        model: type, layout: dict[str, tuple[list[str], set[str]]]) -> None:
    _, keys = layout[model.TEMPLATE]
    ours = {model.column(attr).code for attr in model.KEY}
    assert ours == keys


def test_generated_eba_tables_are_up_to_date(gen: ModuleType) -> None:
    current = gen.TARGET.read_text(encoding="utf-8")
    assert gen.MARKER in current
    assert current.split(gen.MARKER, 1)[1] == gen.generate().split(gen.MARKER, 1)[1], (
        "run python scripts/gen_eba_codes.py")


# ------------------------------------------------------------------ official checks


#: Columns that DPM existence/completeness rules require but the toolkit models as conditional
#: on purpose: an empty parent LEI means "no direct parent" and is exported as the entity's own
#: LEI (FAQ Q58), see BUS-010.
DELIBERATELY_CONDITIONAL = {("B_01.02", "c0060")}


def test_every_active_official_check_is_covered() -> None:
    uncovered = [code for code, (rules, note) in coverage().items()
                 if OFFICIAL_CHECKS[code][2] == "active" and not rules and not note]
    assert not uncovered


def test_mapping_uses_real_checks_and_rules() -> None:
    assert set(RULE_CHECKS) <= set(RULES)
    assert {c for checks in RULE_CHECKS.values() for c in checks} <= set(OFFICIAL_CHECKS)
    assert set(CHECK_NOTES) <= set(OFFICIAL_CHECKS)
    assert len(OFFICIAL_CHECKS) == 120 and eba_checks("FLD-010") == ("806",)


def _columns(template: str, spec: str) -> set[str]:
    codes = [c.code for c in TEMPLATES_BY_CODE[template].columns()]
    out: set[str] = set()
    for part in (p.strip() for p in spec.split(",")):
        span = re.fullmatch(r"c(\d{4})-(\d{4})", part)
        if part == "c*":
            out |= set(codes)
        elif span:
            low, high = int(span.group(1)), int(span.group(2))
            out |= {c for c in codes if low <= int(c[1:]) <= high}
        else:
            out.add(part)
    return out


def test_columns_required_by_dpm_rules_are_mandatory() -> None:
    """FLD-001 implements the DPM existence and completeness rules only if every column they
    require is mandatory in the model."""
    problems = []
    for code in eba_checks("FLD-001"):
        family, table, status, summary = OFFICIAL_CHECKS[code]
        if family != "dpm" or status != "active":
            continue
        spec = summary[len(table) + 1:].split(" must be reported")[0]
        model = TEMPLATES_BY_CODE[table]
        for column in _columns(table, spec):
            col = model.column_by_code(column)
            assert col is not None, (code, column)
            if not col.col.mandatory and (table, column) not in DELIBERATELY_CONDITIONAL:
                problems.append((code, table, column, col.col.requirement.value))
    assert not problems
