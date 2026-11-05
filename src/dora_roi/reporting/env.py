"""Shared Jinja2 environment for HTML reports."""

from __future__ import annotations

from functools import cache

from jinja2 import Environment, PackageLoader, select_autoescape


@cache
def environment() -> Environment:
    return Environment(
        loader=PackageLoader("dora_roi", "reporting/templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
