"""High-level convenience API.

Example::

    from dora_roi.api import validate_path
    loaded, report = validate_path("register.xlsx")
    print(report.severity_counts())
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from dora_roi.io.loader import LoadResult, load
from dora_roi.io.xbrl_csv import CodeMap
from dora_roi.validation import Finding, ValidationConfig, ValidationReport, validate


def validate_loaded(loaded: LoadResult, config: ValidationConfig | None = None,
                    extra_findings: Iterable[Finding] = ()) -> ValidationReport:
    """Validate a loaded register; ``extra_findings`` (e.g. the online LEI check) are merged
    in like the parser's findings, subject to the same rule configuration."""
    return validate(loaded.register, parse_findings=[*loaded.findings, *extra_findings],
                    config=config, source=loaded.source)


def validate_path(
    path: str | Path,
    config: ValidationConfig | None = None,
    code_map: CodeMap | None = None,
) -> tuple[LoadResult, ValidationReport]:
    """Load ``path`` (Excel, CSV folder/zip or xBRL-CSV package) and validate it."""
    loaded = load(path, code_map)
    return loaded, validate_loaded(loaded, config)
