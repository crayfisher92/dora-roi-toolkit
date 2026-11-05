"""Fixtures for browser end-to-end tests (Playwright + axe-core).

The tests are skipped when Playwright or a Chromium build is unavailable, unless
``E2E_REQUIRED=1`` is set (as in CI), in which case that is an error. If Playwright's own
browser build is missing, ``CHROMIUM_EXECUTABLE`` (or ``/opt/pw-browsers/chromium``) is used.
axe-core is loaded from ``AXE_JS`` or ``node_modules/axe-core/axe.min.js``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ and Path("/opt/pw-browsers").exists():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/pw-browsers"

REQUIRED = os.environ.get("E2E_REQUIRED") == "1"
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


def _unavailable(reason: str) -> None:
    if REQUIRED:
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    from dora_roi.web.devserver import BackgroundServer

    with BackgroundServer() as url:
        yield url


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _unavailable("playwright is not installed")
    with sync_playwright() as p:
        b = None
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binary missing (e.g. Playwright upgraded)
            fallback = os.environ.get("CHROMIUM_EXECUTABLE") or "/opt/pw-browsers/chromium"
            if Path(fallback).exists():
                b = p.chromium.launch(executable_path=fallback)
            else:
                _unavailable(f"chromium not available: {exc}")
        yield b
        b.close()


@pytest.fixture
def page(browser: Any, base_url: str) -> Iterator[Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 900}, base_url=base_url)
    pg = context.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda exc: errors.append(str(exc)))
    yield pg
    context.close()
    assert not errors, f"JavaScript errors: {errors}"


def axe_source() -> str | None:
    candidates = [os.environ.get("AXE_JS"), ROOT / "node_modules/axe-core/axe.min.js"]
    for c in candidates:
        if c and Path(c).exists():
            return Path(c).read_text(encoding="utf-8")
    return None


@pytest.fixture(scope="session")
def axe() -> str:
    src = axe_source()
    if src is None:
        _unavailable("axe-core not found (npm install axe-core or set AXE_JS)")
    assert src is not None
    return src


def run_axe(page: Any, axe: str) -> list[dict[str, Any]]:
    """Run axe-core for WCAG 2.2 A/AA rules and return the violations."""
    page.add_script_tag(content=axe)
    result = page.evaluate(
        "tags => axe.run(document, {runOnly: {type: 'tag', values: tags}})", WCAG_TAGS)
    violations: list[dict[str, Any]] = result["violations"]
    return violations


def describe(violations: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{v['id']} ({v['impact']}): {v['help']} – "
        + "; ".join(n["target"][0] if isinstance(n["target"][0], str) else str(n["target"])
                    for n in v["nodes"][:3])
        for v in violations)


@pytest.fixture(scope="session")
def a11y(axe: str) -> Any:
    """``a11y(page)`` → human-readable list of WCAG violations ('' when clean)."""

    def scan(page: Any) -> str:
        return describe(run_axe(page, axe))

    return scan
