from pathlib import Path

from dora_roi.docs import data_dictionary_markdown, regulatory_mapping_markdown, write_docs

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_generated_docs_are_up_to_date() -> None:
    assert (DOCS / "REGULATORY_MAPPING.md").read_text() == regulatory_mapping_markdown(), (
        "run `python -m dora_roi.docs` to regenerate docs/REGULATORY_MAPPING.md")
    assert (DOCS / "DATA_DICTIONARY.md").read_text() == data_dictionary_markdown(), (
        "run `python -m dora_roi.docs` to regenerate docs/DATA_DICTIONARY.md")


def test_write_docs(tmp_path: Path) -> None:
    paths = write_docs(tmp_path)
    assert {p.name for p in paths} == {"REGULATORY_MAPPING.md", "DATA_DICTIONARY.md"}
    text = (tmp_path / "REGULATORY_MAPPING.md").read_text()
    assert "BUS-019" in text and "DORA Art. 28(8)" in text
    assert "## Coverage by provision" in text
