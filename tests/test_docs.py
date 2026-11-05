from pathlib import Path
from typing import Any

import pytest

from dora_roi.docs import (
    data_dictionary_markdown,
    regulatory_mapping_markdown,
    sample_data_markdown,
    write_docs,
)

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_generated_docs_are_up_to_date() -> None:
    assert (DOCS / "REGULATORY_MAPPING.md").read_text() == regulatory_mapping_markdown(), (
        "run `python -m dora_roi.docs` to regenerate docs/REGULATORY_MAPPING.md")
    assert (DOCS / "DATA_DICTIONARY.md").read_text() == data_dictionary_markdown(), (
        "run `python -m dora_roi.docs` to regenerate docs/DATA_DICTIONARY.md")
    assert (DOCS / "SAMPLE_DATA.md").read_text() == sample_data_markdown()


def test_write_docs(tmp_path: Path) -> None:
    paths = write_docs(tmp_path)
    assert {p.name for p in paths} == {
        "REGULATORY_MAPPING.md", "DATA_DICTIONARY.md", "SAMPLE_DATA.md"}
    text = (tmp_path / "REGULATORY_MAPPING.md").read_text()
    assert "BUS-019" in text and "DORA Art. 28(8)" in text
    assert "## Coverage by provision" in text


# ------------------------------------------------------------------ release tooling


def _release_notes_module() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "release_notes", Path(__file__).resolve().parent.parent / "scripts" / "release_notes.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_changelog_has_notes_for_the_package_version(capsys: Any) -> None:
    from dora_roi import __version__

    rn = _release_notes_module()
    assert rn.package_version() == __version__
    assert rn.main(["--check", f"v{__version__}"]) == 0
    notes = capsys.readouterr().out
    assert "### Added" in notes and "](docs/" not in notes  # links made absolute
    assert f"/blob/v{__version__}/docs/" in notes
    assert rn.main(["--check", "v99.0.0"]) == 1
    assert rn.main(["Unreleased"]) == 1  # no date, no notes


def test_release_notes_section_parsing(tmp_path: Path) -> None:
    rn = _release_notes_module()
    text = ("# Changelog\n\n## [Unreleased]\n\n## [1.2.0] - 2026-01-02\n\n### Fixed\n- a "
            "[link](docs/X.md) and [anchor](#y)\n\n## [1.1.0] - 2025-12-01\n\n- old\n\n"
            "[1.2.0]: https://example.invalid\n")
    assert rn.section(text, "1.2.0").startswith("### Fixed")
    assert "old" not in rn.section(text, "1.2.0")
    assert rn.section(text, "1.1.0") == "- old"
    with pytest.raises(ValueError, match="no notes"):
        rn.section(text, "9.9.9")
    linked = rn.absolute_links(rn.section(text, "1.2.0"), "https://g.invalid/r", "v1.2.0")
    assert "(https://g.invalid/r/blob/v1.2.0/docs/X.md)" in linked and "(#y)" in linked
