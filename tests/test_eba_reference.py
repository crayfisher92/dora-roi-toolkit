"""The data model against the official EBA material in ``reference/eba`` (framework 4.0)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

from dora_roi.model import TEMPLATE_MODELS

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


def test_layout_lists_our_templates_plus_b_99_01(
        layout: dict[str, tuple[list[str], set[str]]]) -> None:
    assert set(layout) == {m.TEMPLATE for m in TEMPLATE_MODELS} | {"B_99.01"}


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
