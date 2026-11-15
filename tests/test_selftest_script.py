"""The black-box security self-test (scripts/security_selftest.py) against a live server."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from dora_roi.web.devserver import BackgroundServer

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def test_security_selftest_passes_on_the_workbench(tmp_path: Path) -> None:
    selftest = _load("security_selftest")
    with BackgroundServer() as url:
        results = selftest.run(selftest.Target(url), team=False, write=True)
        report = tmp_path / "r.md"
        assert selftest.main([url, "--no-write", "--report", str(report)]) == 0
    failed = [r for r in results if r.outcome == selftest.FAIL]
    assert not failed, failed
    names = {r.check for r in results}
    assert {"Content-Security-Policy", "cross-site POST rejected (Origin)",
            "oversized upload refused", "workspace link useless in another browser"} <= names
    assert report.read_text(encoding="utf-8").startswith("# Security self-test")


def test_selftest_detects_a_forged_identity_reaching_the_app() -> None:
    """Team checks against a server without SSO in front must fail (no false PASS)."""
    selftest = _load("security_selftest")
    with BackgroundServer() as url:
        results = selftest.run(selftest.Target(url), team=True, write=False)
    by_name = {r.check: r.outcome for r in results}
    assert by_name["anonymous request does not reach the workbench"] == selftest.FAIL
    assert by_name["forged X-Forwarded-Email ignored"] == selftest.FAIL


def test_sso_check_fails_without_a_sign_in_proxy() -> None:
    sso = _load("sso_check")
    with BackgroundServer() as url:
        results = sso.check(url, "anna@example.com")
    outcome = {name: ok for name, ok, _ in results}
    assert outcome["anonymous request is sent to sign-in"] is False
    assert outcome["workbench shows the signed-in user"] is False
    assert outcome["cross-site POST rejected for a signed-in user"] is True
