"""DORA Art. 30 contract gap analysis: checklist, assessments, analysis, extraction, reports."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner
from openpyxl import Workbook, load_workbook

from dora_roi.cli import main
from dora_roi.contracts import (
    PROVISIONS,
    PROVISIONS_BY_ID,
    AssessmentBook,
    ComplianceStatus,
    ContractAssessment,
    Priority,
    ProvisionStatus,
    Scope,
    contract_contexts,
    evaluate,
    gaps_by_provision,
    load_assessments,
    read_assessment_workbook,
    remediation_plan,
    write_assessment_workbook,
)
from dora_roi.contracts.analysis import EffectiveItem, priority
from dora_roi.contracts.extract import ExtractionError, extract_text, pdf_supported
from dora_roi.contracts.model import describe_changes
from dora_roi.contracts.provisions import applicable, checklist_markdown, clause_label
from dora_roi.contracts.report import render_plan_html, write_plan_workbook
from dora_roi.contracts.suggest import Suggestion, apply_suggestions, suggest
from dora_roi.i18n import CATALOGUE, format_date, translator
from dora_roi.io.excel import write_workbook
from dora_roi.model import (
    ContractGeneral,
    ContractSpecific,
    ContractType,
    Criticality,
    Function,
    IctServiceType,
    ProviderCodeType,
    RegisterOfInformation,
)
from dora_roi.sample import generate_sample
from dora_roi.sample.assessments import sample_assessments
from dora_roi.sample.contract_docs import (
    SAMPLE_CONTRACT_TEXT,
    docx_bytes,
    pdf_bytes,
    write_sample_contract,
)

from conftest import ENTITY, PARENT, PROVIDER, build_valid_register

ALL_IDS = [p.id for p in PROVISIONS]
CRITICAL_IDS = [p.id for p in PROVISIONS if p.scope is Scope.CRITICAL]


def _full(ref: str, status: ProvisionStatus = ProvisionStatus.PRESENT,
          ids: list[str] | None = None) -> ContractAssessment:
    a = ContractAssessment(contract_ref=ref, assessor="T", assessed_on=date(2025, 11, 1))
    for pid in ids or ALL_IDS:
        a.set(pid, status, "Clause 1", "ok")
    return a


def _group_register(master_critical: bool = True) -> RegisterOfInformation:
    """valid register + an overarching master (MSA) and a critical call-off (CO)."""
    reg = build_valid_register()
    reg.add(Function(function_id="F-HR", licensed_activity="x", function_name="HR",
                     entity_lei=ENTITY, criticality=Criticality.NOT_CRITICAL,
                     last_assessment_date=date(2025, 6, 30)))
    reg.add(ContractGeneral(contract_ref="MSA", contract_type=ContractType.OVERARCHING,
                            currency="EUR", annual_cost=Decimal(1)))
    reg.add(ContractGeneral(contract_ref="CO", contract_type=ContractType.SUBSEQUENT,
                            overarching_ref="MSA", currency="EUR", annual_cost=Decimal(1)))
    for ref, fn in (("MSA", "F-PAY" if master_critical else "F-HR"), ("CO", "F-PAY")):
        reg.add(ContractSpecific(contract_ref=ref, entity_lei=ENTITY, provider_code=PROVIDER,
                                 provider_code_type=ProviderCodeType.LEI, function_id=fn,
                                 service_type=IctServiceType.S19, start_date=date(2024, 1, 1),
                                 end_date=date(2027, 6, 30)))
    return reg


# =========================================================================== checklist


def test_checklist_structure_and_texts() -> None:
    assert len(PROVISIONS) == 22 and len(set(ALL_IDS)) == 22
    assert len(applicable(False)) == 12 and len(applicable(True)) == 22
    assert {p.paragraph for p in PROVISIONS} == {"30(1)", "30(2)", "30(3)"}
    for p in PROVISIONS:
        for text in (p.title_en, p.title_de, p.requirement_en, p.requirement_de,
                     p.remediation_en, p.remediation_de):
            assert len(text) > 10, p.id
        assert p.article.startswith("DORA Art. 30(")
        assert p.concepts and all(c.regex.pattern for c in p.concepts)
        assert p.title("de") == p.title_de and p.requirement("de") == p.requirement_de
    # the typical gaps the analysis must be able to express
    for pid in ("30.2.a.2", "30.3.d", "30.3.e.i", "30.3.f.i"):
        assert PROVISIONS_BY_ID[pid].key
    md = checklist_markdown()
    assert all(f"`{pid}`" in md for pid in ALL_IDS) and "DORA Art. 28(7)" in md
    assert "Checkliste" in checklist_markdown("de")
    assert clause_label("12.1") == "Clause 12.1" and clause_label("12", "de") == "Ziffer 12"
    assert clause_label("Schedule 2") == "Schedule 2"


def test_i18n_catalogue_and_dates() -> None:
    assert set(CATALOGUE["en"]) == set(CATALOGUE["de"])
    assert translator("de")("st.missing") == "Fehlt"
    assert translator("xx")("st.missing") == "Missing"
    assert translator("en")("nope") == "nope"
    assert format_date(date(2025, 12, 31), "de") == "31.12.2025"
    assert format_date(datetime(2025, 12, 31, 9, tzinfo=UTC)) == "31 Dec 2025"
    assert format_date(None) == "—" and format_date("x") == "x"


# =========================================================================== model


@pytest.mark.parametrize(("raw", "expected"), [
    ("present", ProvisionStatus.PRESENT), ("Ja", ProvisionStatus.PRESENT),
    ("teilweise", ProvisionStatus.PARTIAL), ("Partial", ProvisionStatus.PARTIAL),
    ("missing", ProvisionStatus.MISSING), ("nein", ProvisionStatus.MISSING),
    ("", ProvisionStatus.NOT_ASSESSED), (None, ProvisionStatus.NOT_ASSESSED),
    ("not assessed", ProvisionStatus.NOT_ASSESSED),
])
def test_status_parse(raw: object, expected: ProvisionStatus) -> None:
    assert ProvisionStatus.parse(raw) is expected


def test_status_parse_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown status"):
        ProvisionStatus.parse("maybe")


def test_assessment_book_history_json_and_merge() -> None:
    book = AssessmentBook()
    a = ContractAssessment(contract_ref="C-001")
    a.set("30.3.d", "missing")
    stored = book.save(a, by="Lena", at=datetime(2025, 1, 1, tzinfo=UTC))
    assert stored.history[0].summary.startswith("Assessment created (1")
    b = stored.model_copy(deep=True)
    b.set("30.3.d", ProvisionStatus.PRESENT, "Clause 9", "added")
    b.set("30.2.c", ProvisionStatus.PRESENT, "Clause 9", "x")
    b.notes = "renegotiated"
    book.save(b, by="Lena")
    hist = book.get("C-001").history  # type: ignore[union-attr]
    assert len(hist) == 2 and "30.3.d: missing → present" in hist[1].summary
    assert "notes updated" in hist[1].summary
    assert describe_changes(b, b) == "Saved without changes"
    c = b.model_copy(deep=True)
    c.items["30.3.d"] = c.items["30.3.d"].model_copy(update={"evidence": "new"})
    assert describe_changes(b, c) == "30.3.d: evidence updated"
    many = ContractAssessment(contract_ref="X")
    for pid in ALL_IDS[:9]:
        many.set(pid, "missing")
    assert "more)" in describe_changes(ContractAssessment(contract_ref="X"), many)
    text = book.to_json()
    assert '"schema": "dora-roi-toolkit/contract-assessments/v1"' in text
    again = AssessmentBook.from_json(text)
    assert again.get("C-001") == book.get("C-001") and len(again) == 1
    with pytest.raises(ValueError, match="schema"):
        AssessmentBook.from_json(json.dumps({"assessments": {}}))
    other = AssessmentBook()
    other.save(ContractAssessment(contract_ref="C-002"))
    assert book.merge(other) == 1 and len(book) == 2
    book.remove("C-002")
    book.remove("missing-ref")
    assert book.get("C-002") is None
    with pytest.raises(ValueError, match=r"unknown Art\. 30 provision"):
        ContractAssessment.model_validate({"contract_ref": "C", "items": {
            "x": {"provision_id": "30.9"}}})


def test_assessment_workbook_round_trip_and_problems(tmp_path: Path) -> None:
    book = AssessmentBook()
    book.save(_full("C-001"))
    path = write_assessment_workbook(book, tmp_path / "a.xlsx", {"C-001": True, "C-NEW": False})
    wb = load_workbook(path)
    assert wb.sheetnames == ["Assessments", "README"]
    rows = list(wb["Assessments"].iter_rows(min_row=2, values_only=True))
    assert len([r for r in rows if r[0] == "C-001"]) == 22
    assert len([r for r in rows if r[0] == "C-NEW"]) == 12  # Art. 30(2) only
    again, problems = read_assessment_workbook(path)
    assert problems == [] and set(again.assessments) == {"C-001"}
    assert again.get("C-001").items == book.get("C-001").items  # type: ignore[union-attr]

    bad = Workbook()
    ws = bad.active
    assert ws is not None
    ws.append(["contract_ref", "provision_id", "status", "assessed_on", "evidence"])
    ws.append(["C-1", "30.9", "present", None, None])
    ws.append([None, "30.1", "present", None, None])
    ws.append(["C-1", "30.1", "maybe", None, None])
    ws.append(["C-1", "30.2.c", "ja", "31.12.2025", None])
    ws.append(["C-1", "30.2.e", None, None, "only a note"])
    ws.append([None, None, None, None, None])
    bad.save(tmp_path / "bad.xlsx")
    book2, problems = read_assessment_workbook(tmp_path / "bad.xlsx")
    assert len(problems) == 4
    assert book2.get("C-1").item("30.2.c").status is ProvisionStatus.PRESENT  # type: ignore
    assert book2.get("C-1").item("30.2.e").evidence == "only a note"  # type: ignore[union-attr]

    nohead = Workbook()
    nohead.active.append(["foo"])  # type: ignore[union-attr]
    nohead.save(tmp_path / "nohead.xlsx")
    with pytest.raises(ValueError, match="lacks column"):
        read_assessment_workbook(tmp_path / "nohead.xlsx")
    (tmp_path / "a.json").write_text(book.to_json())
    assert len(load_assessments(tmp_path / "a.json")[0]) == 1
    assert len(load_assessments(path)[0]) == 1
    with pytest.raises(ValueError, match="unsupported"):
        load_assessments(tmp_path / "a.csv")


# =========================================================================== analysis


def test_contexts_and_status_levels(valid_register: RegisterOfInformation) -> None:
    ctx = contract_contexts(valid_register)["C-001"]
    assert ctx.critical and ctx.providers == {PROVIDER: "SaaS Vendor GmbH"}
    assert ctx.service_types == ["S19"] and ctx.open_ended and ctx.row is None
    assert ctx.functions[0].name == "Payments"
    book = AssessmentBook()
    assert evaluate(valid_register, book).contracts[0].status is ComplianceStatus.NOT_ASSESSED
    book.save(_full("C-001"))
    pf = evaluate(valid_register, book)
    c = pf.contracts[0]
    assert c.status is ComplianceStatus.COMPLIANT and c.coverage == 1.0 and c.assessed
    book.save(_full("C-001", ids=ALL_IDS[:5]))
    assert evaluate(valid_register, book).contracts[0].status is ComplianceStatus.INCOMPLETE
    a = _full("C-001")
    a.set("30.3.e.i", "partial")
    a.set("30.3.d", "missing")
    book.save(a)
    pf = evaluate(valid_register, book)
    c = pf.contracts[0]
    assert c.status is ComplianceStatus.GAPS and (c.missing, c.partial) == (1, 1)
    assert pf.counts()["gaps"] == 1 and pf.total_missing == 1 and pf.total_partial == 1
    assert pf.critical_assessed_share() == 1.0
    prov = pf.providers[0]
    assert prov.critical and prov.with_gaps == 1 and prov.assessed == 1
    assert prov.status is ComplianceStatus.GAPS and (prov.missing, prov.partial) == (1, 1)
    plan = remediation_plan(pf, date(2026, 1, 1))
    assert [(i.provision.id, i.priority) for i in plan.items] == [
        ("30.3.d", Priority.HIGH), ("30.3.e.i", Priority.MEDIUM)]
    assert plan.items[0].target_date == date(2026, 4, 1) and plan.counts()["high"] == 1
    assert plan.items[0].contract_end is None
    assert [p.id for p, _, _ in gaps_by_provision(pf)] == ["30.3.d", "30.3.e.i"]


def test_assessments_of_unknown_arrangements_are_orphans() -> None:
    reg = build_valid_register()
    book = AssessmentBook()
    book.save(_full("GONE"))
    pf = evaluate(reg, book)
    assert [a.contract_ref for a in pf.orphans] == ["GONE"]
    assert evaluate(RegisterOfInformation(), AssessmentBook()).critical_assessed_share() == 1.0


def test_arrangement_only_in_b0202_and_unknown_provider() -> None:
    reg = build_valid_register()
    reg.add(ContractSpecific(contract_ref="SHADOW", entity_lei=PARENT, provider_code="P-9",
                             function_id="F-X"))
    ctx = contract_contexts(reg)["SHADOW"]
    assert not ctx.in_register and ctx.providers == {"P-9": "P-9"} and not ctx.critical
    assert ctx.entities == {PARENT: PARENT} and ctx.functions[0].name == "F-X"


def test_priority_matrix() -> None:
    p = PROVISIONS_BY_ID["30.2.e"]
    assert priority(EffectiveItem(p, ProvisionStatus.MISSING), True) is Priority.HIGH
    assert priority(EffectiveItem(p, ProvisionStatus.MISSING), False) is Priority.MEDIUM
    assert priority(EffectiveItem(p, ProvisionStatus.PARTIAL), True) is Priority.MEDIUM
    assert priority(EffectiveItem(p, ProvisionStatus.PARTIAL), False) is Priority.LOW


def test_call_off_inherits_from_master() -> None:
    reg = _group_register()
    book = AssessmentBook()
    master = _full("MSA")
    master.set("30.3.d", "missing")
    book.save(master)
    pf = evaluate(reg, book)
    co = pf.by_ref()["CO"]
    assert co.status is ComplianceStatus.GAPS and co.inherited_from == "MSA"
    assert all(i.inherited_from == "MSA" for i in co.items)
    plan = remediation_plan(pf)
    tlpt = [i for i in plan.items if i.provision.id == "30.3.d"]
    assert len(tlpt) == 1 and tlpt[0].contract_ref == "MSA" and tlpt[0].applies_to == ("CO",)
    # own assessment overrides, inherit=False switches inheritance off
    own = ContractAssessment(contract_ref="CO")
    own.set("30.3.d", "present")
    book.save(own)
    co = evaluate(reg, book).by_ref()["CO"]
    assert next(i for i in co.items if i.provision.id == "30.3.d").inherited_from is None
    assert co.status is ComplianceStatus.COMPLIANT
    book.save(own.model_copy(update={"inherit": False}))
    assert evaluate(reg, book).by_ref()["CO"].status is ComplianceStatus.INCOMPLETE


def test_inherited_gap_escalates_master_or_is_listed_under_call_off() -> None:
    reg = _group_register(master_critical=False)
    book = AssessmentBook()
    master = _full("MSA")  # assessed incl. Art. 30(3) items although not critical itself
    master.set("30.2.e", "partial")  # low on the master, but a critical call-off relies on it
    master.set("30.3.d", "missing")  # not applicable to the master → listed under the call-off
    book.save(master)
    plan = remediation_plan(evaluate(reg, book))
    by_key = {(i.contract_ref, i.provision.id): i for i in plan.items}
    sla = by_key[("MSA", "30.2.e")]
    assert sla.priority is Priority.MEDIUM and sla.critical and sla.applies_to == ("CO",)
    tlpt = by_key[("CO", "30.3.d")]
    assert tlpt.inherited_from == "MSA" and tlpt.priority is Priority.HIGH
    assert ("MSA", "30.3.d") not in by_key


def test_sample_assessments_show_typical_gaps() -> None:
    reg = generate_sample(inject_errors=True).register
    book = sample_assessments(reg)
    pf = evaluate(reg, book)
    byref = pf.by_ref()

    def status(ref: str, pid: str) -> ProvisionStatus:
        return next(i.status for i in byref[ref].items if i.provision.id == pid)

    assert status("AR-DE-0022", "30.3.f.i") is ProvisionStatus.MISSING  # exit provisions
    assert status("AR-DE-0026", "30.3.e.i") is ProvisionStatus.MISSING  # audit rights
    assert status("AR-DE-0026", "30.2.a.2") is ProvisionStatus.MISSING  # subcontracting
    assert status("MSA-DE-0010", "30.3.d") is ProvisionStatus.MISSING  # TLPT
    assert byref["CO-LU-0002"].inherited_from == "MSA-DE-0001"
    assert byref["AR-AT-0048"].status is ComplianceStatus.INCOMPLETE
    assert byref["AR-DE-0030"].status is ComplianceStatus.COMPLIANT
    assert byref["AR-DE-0064"].status is ComplianceStatus.GAPS and not byref[
        "AR-DE-0064"].context.critical
    mobilio = book.get("AR-DE-0057")
    assert mobilio is not None
    assert mobilio.item("30.3.f.ii").suggested_status is ProvisionStatus.PRESENT
    assert mobilio.item("30.3.f.ii").status is ProvisionStatus.PARTIAL  # reviewer overruled
    assert len(sample_assessments()) == 13
    assert not pf.orphans
    assert pf.providers[0].name == "Nimbus Cloud Services EMEA Ltd"


# =========================================================================== extraction


def test_extract_docx_pdf_txt() -> None:
    docx = extract_text("c.docx", docx_bytes(SAMPLE_CONTRACT_TEXT))
    assert docx.kind == "docx" and "TLPT" not in docx.text and docx.words > 700
    txt = extract_text("c.txt", "Vertrag – Kündigungsfrist".encode("cp1252"))
    assert "Kündigungsfrist" in txt.text
    assert extract_text("c.md", b"\xef\xbb\xbfhello").text == "hello"
    if pdf_supported():
        pdf = extract_text("c.pdf", pdf_bytes(SAMPLE_CONTRACT_TEXT))
        assert pdf.kind == "pdf" and pdf.pages == 2 and "Subcontracting" in pdf.text


@pytest.mark.parametrize(("name", "data", "message"), [
    ("c.rtf", b"x", "unsupported document type"),
    ("c.txt", b"   ", "no text found"),
    ("c.docx", b"PK-not-a-zip", "not a valid .docx"),
    ("c.pdf", b"%PDF-1.4 garbage", "could not read the PDF"),
])
def test_extract_errors(name: str, data: bytes, message: str) -> None:
    if name.endswith(".pdf") and not pdf_supported():
        pytest.skip("pypdf not installed")
    with pytest.raises(ExtractionError, match=message):
        extract_text(name, data)


def _zip(parts: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in parts.items():
            zf.writestr(name, body)
    return buf.getvalue()


def test_extract_docx_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ExtractionError, match="not a Word document"):
        extract_text("c.docx", _zip({"other.xml": b"<a/>"}))
    with pytest.raises(ExtractionError, match="DTD"):
        extract_text("c.docx", _zip({"word/document.xml": b'<!DOCTYPE x [<!ENTITY a "b">]><x/>'}))
    with pytest.raises(ExtractionError, match="corrupt"):
        extract_text("c.docx", _zip({"word/document.xml": b"<unclosed"}))
    monkeypatch.setattr("dora_roi.contracts.extract.MAX_UNCOMPRESSED_BYTES", 10)
    with pytest.raises(ExtractionError, match="too large"):
        extract_text("c.docx", docx_bytes("x" * 100))
    monkeypatch.setattr("dora_roi.contracts.extract.MAX_DOCUMENT_BYTES", 10)
    with pytest.raises(ExtractionError, match="larger than"):
        extract_text("c.txt", b"x" * 100)


def test_extract_docx_headers_breaks_and_tabs() -> None:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = (f"<w:document {w}><w:body><w:p><w:r><w:t>A</w:t><w:tab/><w:t>B</w:t><w:br/>"
            "<w:t>C</w:t></w:r></w:p></w:body></w:document>").encode()
    header = f"<w:hdr {w}><w:p><w:r><w:t>Header text</w:t></w:r></w:p></w:hdr>".encode()
    out = extract_text("c.docx", _zip({"word/document.xml": body,
                                       "word/header1.xml": header})).text
    assert out.startswith("A\tB\nC") and "Header text" in out


def test_extract_pdf_without_pypdf(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real = builtins.__import__

    def fake(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("pypdf"):
            raise ImportError(name)
        return real(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake)
    assert not pdf_supported()
    with pytest.raises(ExtractionError, match="pypdf"):
        extract_text("c.pdf", b"%PDF")


@pytest.mark.skipif(not pdf_supported(), reason="pypdf not installed")
def test_extract_encrypted_pdf_and_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(pdf_bytes(SAMPLE_CONTRACT_TEXT))).pages:
        writer.add_page(page)
    writer.encrypt("secret")
    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(ExtractionError, match="encrypted"):
        extract_text("c.pdf", buf.getvalue())
    monkeypatch.setattr("dora_roi.contracts.extract.MAX_PDF_PAGES", 1)
    result = extract_text("c.pdf", pdf_bytes(SAMPLE_CONTRACT_TEXT))
    assert result.warnings and "first 1 of 2" in result.warnings[0]


# =========================================================================== suggestions

EXPECTED = {
    "30.1": "likely_present", "30.2.a.2": "likely_present", "30.2.b.2": "likely_present",
    "30.2.d": "likely_present", "30.2.h": "likely_present", "30.3.a": "likely_present",
    "30.3.c": "likely_present", "30.3.d": "not_found", "30.3.e.i": "possibly_partial",
    "30.3.e.iii": "not_found", "30.3.f.i": "not_found",
}


def test_suggestions_on_sample_contract() -> None:
    result = suggest(SAMPLE_CONTRACT_TEXT)
    by_id = result.by_id()
    for pid, expected in EXPECTED.items():
        assert by_id[pid].suggestion.value == expected, pid
    assert by_id["30.3.e.i"].missing == ["authority"] and by_id["30.3.e.i"].clause_ref == "12"
    assert by_id["30.2.h"].clause_ref.startswith("13") and by_id["30.2.h"].confidence == "high"
    assert by_id["30.3.d"].confidence == "low"
    assert sum(result.counts().values()) == 22 and result.headings > 30
    assert len(suggest(SAMPLE_CONTRACT_TEXT, critical=False).items) == 12
    evidence = by_id["30.3.e.i"].evidence()
    assert evidence.startswith("[Suggestion – review]") and "not found: authority" in evidence
    assert by_id["30.3.d"].evidence("de").startswith("[Vorschlag – prüfen] Keine passende")
    assert "nicht gefunden" in by_id["30.3.e.i"].evidence("de")
    assert Suggestion.NOT_FOUND.status is ProvisionStatus.MISSING


def test_suggestion_negation_and_german() -> None:
    text = ("§ 7 Tests\nDer Dienstleister ist nicht verpflichtet, an TLPT teilzunehmen.\n"
            "§ 8 Prüfung\nDie Bank und die Aufsichtsbehörde haben uneingeschränkte Prüfungsrechte "
            "und Zugang zu den Räumlichkeiten.\n")
    by_id = suggest(text).by_id()
    tlpt = by_id["30.3.d"]
    assert tlpt.suggestion is Suggestion.POSSIBLY_PARTIAL and tlpt.negated
    assert "Verneinung" in tlpt.evidence("de") and "negation" in tlpt.evidence()
    audit = by_id["30.3.e.i"]
    assert audit.suggestion is Suggestion.LIKELY_PRESENT and audit.clause_ref == "§ 8"


def test_apply_suggestions_keeps_reviewed_items() -> None:
    result = suggest(SAMPLE_CONTRACT_TEXT)
    base = ContractAssessment(contract_ref="AR-DE-0057")
    base.set("30.3.d", "present", "Side letter 2", "TLPT agreed in a side letter")
    draft = apply_suggestions(base, result)
    assert draft.item("30.3.d").status is ProvisionStatus.PRESENT
    assert draft.item("30.3.d").suggested_status is ProvisionStatus.MISSING
    assert draft.item("30.3.f.i").status is ProvisionStatus.MISSING
    assert base.item("30.3.f.i").status is ProvisionStatus.NOT_ASSESSED  # base untouched
    forced = apply_suggestions(base, result, overwrite=True)
    assert forced.item("30.3.d").status is ProvisionStatus.MISSING


# =========================================================================== reports


def test_plan_html_and_workbook(tmp_path: Path) -> None:
    reg = generate_sample(inject_errors=False).register
    plan = remediation_plan(evaluate(reg, sample_assessments(reg)), date(2025, 11, 5))
    html = render_plan_html(plan, client="Alpenrand", prepared_by="GRC")
    assert "Contract remediation plan" in html and "Helix Core Banking AG" in html
    assert "also relied on by CO-LU-0011" in html and "05 Nov 2025" in html
    de = render_plan_html(plan, lang="de")
    assert 'lang="de"' in de and "Maßnahmenplan" in de and "05.11.2025" in de
    path = write_plan_workbook(plan, tmp_path / "plan.xlsx", lang="de", client="Alpenrand")
    wb = load_workbook(path)
    assert wb.sheetnames == ["Maßnahmenplan", "Nach Dienstleister", "Ausnahmen", "Zu bewerten",
                             "Checkliste", "README"]
    assert wb["Ausnahmen"].max_row == 2  # the sample's Nimbus audit-rights exception
    assert wb["Maßnahmenplan"].max_row == len(plan.items) + 1
    en = load_workbook(write_plan_workbook(plan, tmp_path / "en.xlsx"))
    assert en.sheetnames[0] == "Remediation plan"
    empty = remediation_plan(evaluate(build_valid_register(), AssessmentBook()))
    assert "None." in render_plan_html(empty)


# =========================================================================== CLI


def test_cli_contracts(tmp_path: Path) -> None:
    runner = CliRunner()
    reg = tmp_path / "s.xlsx"
    r = runner.invoke(main, ["sample", str(reg), "--assessments", str(tmp_path / "a.json"),
                             "--contract-document", str(tmp_path / "c.docx")])
    assert r.exit_code == 0, r.output
    r = runner.invoke(main, ["sample", str(tmp_path / "s2.xlsx"), "--assessments",
                             str(tmp_path / "a.xlsx")])
    assert r.exit_code == 0 and (tmp_path / "a.xlsx").exists()
    r = runner.invoke(main, ["contracts", "assess", str(reg), "--assessments",
                             str(tmp_path / "a.json")])
    assert r.exit_code == 0 and "Remediation actions: 34" in r.output and "more" in r.output
    assert "1 approved exception(s)" in r.output
    for name in ("plan.html", "plan.xlsx", "plan.json"):
        r = runner.invoke(main, ["contracts", "assess", str(reg), "--assessments",
                                 str(tmp_path / "a.xlsx"), "-o", str(tmp_path / name),
                                 "--lang", "de", "--plan-date", "2025-11-05"])
        assert r.exit_code == 0, r.output
    data = json.loads((tmp_path / "plan.json").read_text())
    assert data["counts"]["high"] == 18 and data["plan_date"] == "2025-11-05"
    assert data["exceptions"][0]["provision"] == "30.3.e.i"
    r = runner.invoke(main, ["contracts", "assess", str(reg), "--assessments",
                             str(tmp_path / "a.json"), "--fail-on-gaps"])
    assert r.exit_code == 1
    (tmp_path / "bad.json").write_text("{}")
    r = runner.invoke(main, ["contracts", "assess", str(reg), "--assessments",
                             str(tmp_path / "bad.json")])
    assert r.exit_code == 2 and "schema" in r.output
    r = runner.invoke(main, ["contracts", "template", str(reg), "-o", str(tmp_path / "t.xlsx"),
                             "--assessments", str(tmp_path / "a.json")])
    assert r.exit_code == 0 and (tmp_path / "t.xlsx").exists()
    r = runner.invoke(main, ["contracts", "suggest", str(tmp_path / "c.docx"), "-o",
                             str(tmp_path / "draft.json"), "--contract-ref", "AR-DE-0057"])
    assert r.exit_code == 0 and "30.3.d      not_found" in r.output
    draft = AssessmentBook.from_json((tmp_path / "draft.json").read_text())
    assert draft.get("AR-DE-0057") is not None
    r = runner.invoke(main, ["contracts", "suggest", str(tmp_path / "c.docx"), "--not-critical"])
    assert "30.3" not in r.output
    (tmp_path / "x.rtf").write_text("x")
    assert runner.invoke(main, ["contracts", "suggest", str(tmp_path / "x.rtf")]).exit_code == 2
    for fmt in ("text", "md", "json"):
        r = runner.invoke(main, ["contracts", "checklist", "-f", fmt, "--lang", "de"])
        assert r.exit_code == 0 and "30.3.f.ii" in r.output
    assert write_sample_contract(tmp_path / "c.txt").read_text().startswith("DIGITAL BANKING")
    assert write_sample_contract(tmp_path / "c.pdf").read_bytes()[:5] == b"%PDF-"


def test_cli_template_without_assessments(tmp_path: Path) -> None:
    reg = write_workbook(build_valid_register(), tmp_path / "r.xlsx")
    r = CliRunner().invoke(main, ["contracts", "template", str(reg), "-o",
                                  str(tmp_path / "t.xlsx")])
    assert r.exit_code == 0
    rows = list(load_workbook(tmp_path / "t.xlsx")["Assessments"].iter_rows(min_row=2))
    assert len(rows) == 22
