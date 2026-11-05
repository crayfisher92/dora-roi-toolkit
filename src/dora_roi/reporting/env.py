"""Shared Jinja2 environment for HTML reports."""

from __future__ import annotations

from functools import cache

from jinja2 import Environment, PackageLoader, select_autoescape


def _thousands(value: object, digits: int = 0) -> str:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    return f"{number:,.{digits}f}"


def _pct(value: object, digits: int = 0) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"


@cache
def environment() -> Environment:
    env = Environment(
        loader=PackageLoader("dora_roi", "reporting/templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["thousands"] = _thousands
    env.filters["pct"] = _pct
    return env
