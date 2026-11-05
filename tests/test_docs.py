from pathlib import Path

from dora_roi.contracts.provisions import checklist_markdown
from dora_roi.docs import (
    data_dictionary_markdown,
    regulatory_mapping_markdown,
    sample_data_markdown,
    write_docs,
)
from dora_roi.incidents.criteria import criteria_markdown

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_generated_docs_are_up_to_date() -> None:
    assert (DOCS / "REGULATORY_MAPPING.md").read_text() == regulatory_mapping_markdown(), (
        "run `python -m dora_roi.docs` to regenerate docs/REGULATORY_MAPPING.md")
    assert (DOCS / "DATA_DICTIONARY.md").read_text() == data_dictionary_markdown(), (
        "run `python -m dora_roi.docs` to regenerate docs/DATA_DICTIONARY.md")
    assert (DOCS / "SAMPLE_DATA.md").read_text() == sample_data_markdown()
    assert (DOCS / "ART30_CHECKLIST.md").read_text() == checklist_markdown()
    assert (DOCS / "INCIDENT_CLASSIFICATION.md").read_text() == criteria_markdown()


def test_write_docs(tmp_path: Path) -> None:
    paths = write_docs(tmp_path)
    assert {p.name for p in paths} == {
        "REGULATORY_MAPPING.md", "DATA_DICTIONARY.md", "SAMPLE_DATA.md", "ART30_CHECKLIST.md",
        "INCIDENT_CLASSIFICATION.md"}
    text = (tmp_path / "REGULATORY_MAPPING.md").read_text()
    assert "BUS-019" in text and "DORA Art. 28(8)" in text
    assert "## Coverage by provision" in text
