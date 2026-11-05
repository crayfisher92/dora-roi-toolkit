"""Command-line interface: ``roi validate | report | export | template | rules | …``."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import click

from dora_roi import __version__
from dora_roi.api import validate_loaded
from dora_roi.io.loader import LoadResult, UnsupportedInputError, load
from dora_roi.io.xbrl_csv import CodeMap, XbrlCsvOptions, export_xbrl_csv, load_code_map
from dora_roi.validation import Severity, ValidationConfig, ValidationReport, rules_catalogue
from dora_roi.validation import validate as validate_register

EXIT_FINDINGS = 1
EXIT_USAGE = 2


def _write(text: str, output: Path | None) -> None:
    if output is None:
        click.echo(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        click.echo(f"Wrote {output}", err=True)


def _write_pdf(render_pdf: Callable[[], bytes], output: Path) -> None:
    from dora_roi.reporting.pdf import PdfUnavailableError

    try:
        data = render_pdf()
    except PdfUnavailableError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(EXIT_USAGE)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    click.echo(f"Wrote {output}", err=True)


def _load(path: Path, code_map: CodeMap | None) -> LoadResult:
    try:
        return load(path, code_map)
    except (FileNotFoundError, UnsupportedInputError) as exc:
        raise click.UsageError(str(exc)) from exc


def _code_map(path: Path | None) -> CodeMap | None:
    if path is None:
        return None
    try:
        return load_code_map(path)
    except (ValueError, json.JSONDecodeError) as exc:
        raise click.BadParameter(f"invalid code map: {exc}", param_hint="--code-map") from exc


def _config(disable: tuple[str, ...], reference_date: date | None,
            downgrade: tuple[str, ...] = ()) -> ValidationConfig:
    return ValidationConfig(
        disabled_rules=frozenset(d.upper() for d in disable),
        severity_overrides={d.upper(): Severity.WARNING for d in downgrade},
        reference_date=reference_date,
    )


def _summary_line(report: ValidationReport) -> str:
    c = report.severity_counts()
    state = "PASSED" if report.passed else "FAILED"
    return f"Validation {state}: {c['error']} error(s), {c['warning']} warning(s), {c['info']} info"


input_arg = click.argument("input_path", metavar="INPUT", type=click.Path(path_type=Path))
code_map_opt = click.option("--code-map", type=click.Path(exists=True, dir_okay=False,
                                                          path_type=Path),
                            help="JSON map of code-list values to EBA taxonomy members.")
ref_date_opt = click.option("--reference-date", type=click.DateTime(["%Y-%m-%d"]), default=None,
                            help="Override the reference date used by date-relative rules.")


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="roi")
def main() -> None:
    """DORA Register of Information toolkit.

    INPUT can be an .xlsx workbook, a folder (or zip) of CSV files, or an xBRL-CSV package.
    """


@main.command()
@input_arg
@click.option("-f", "--format", "fmt",
              type=click.Choice(["text", "json", "md", "html", "pdf"]), default="text",
              show_default=True, help="Report format (pdf needs -o and the [pdf] extra).")
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path),
              help="Write the report to a file instead of stdout.")
@click.option("--fail-on", type=click.Choice(["error", "warning", "never"]), default="error",
              show_default=True, help="Exit with status 1 when findings of this severity exist.")
@click.option("--disable", multiple=True, metavar="RULE", help="Skip a rule (repeatable).")
@click.option("--downgrade", multiple=True, metavar="RULE",
              help="Report a rule as a warning instead of its default severity (repeatable).")
@ref_date_opt
@code_map_opt
def validate(input_path: Path, fmt: str, output: Path | None, fail_on: str,
             disable: tuple[str, ...], downgrade: tuple[str, ...],
             reference_date: object, code_map: Path | None) -> None:
    """Validate a register and print or save a report."""
    from dora_roi.reporting import render
    from dora_roi.reporting.validation_report import render_pdf

    if fmt == "pdf" and output is None:
        raise click.UsageError("--format pdf needs --output FILE")
    ref = reference_date.date() if hasattr(reference_date, "date") else None
    loaded = _load(input_path, _code_map(code_map))
    report = validate_loaded(loaded, _config(disable, ref, downgrade))
    if fmt == "pdf" and output is not None:
        _write_pdf(lambda: render_pdf(report), output)
    else:
        _write(render(report, fmt), output)
    if output is not None or fmt != "text":
        click.echo(_summary_line(report), err=True)
    counts = report.severity_counts()
    failed = (fail_on == "error" and not report.passed) or (
        fail_on == "warning" and (not report.passed or counts["warning"] > 0))
    sys.exit(EXIT_FINDINGS if failed else 0)


@main.command()
@input_arg
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), required=True,
              help="Output file for the executive summary: .html, or .pdf (needs the [pdf] "
              "extra).")
@click.option("--client", "client_name", help="Client name shown in the title.")
@click.option("--prepared-by", help="Author shown in the header.")
@click.option("--validation-report", type=click.Path(dir_okay=False, path_type=Path),
              help="Also write the detailed validation report (format from extension: "
              ".html, .pdf, .md or .json).")
@click.option("--json", "json_path", type=click.Path(dir_okay=False, path_type=Path),
              help="Also write the concentration analysis as JSON.")
@ref_date_opt
@code_map_opt
def report(input_path: Path, output: Path, client_name: str | None, prepared_by: str | None,
           validation_report: Path | None, json_path: Path | None, reference_date: object,
           code_map: Path | None) -> None:
    """Generate the executive summary (HTML or PDF) with concentration-risk analytics."""
    from dora_roi.analytics import AnalyticsConfig, analyse
    from dora_roi.reporting import render
    from dora_roi.reporting.executive import render_executive_summary
    from dora_roi.reporting.pdf import html_to_pdf
    from dora_roi.reporting.validation_report import render_pdf

    ref = reference_date.date() if hasattr(reference_date, "date") else None
    loaded = _load(input_path, _code_map(code_map))
    vreport = validate_loaded(loaded, _config((), ref))
    cfg = AnalyticsConfig(reference_date=ref)
    analysis = analyse(loaded.register, cfg)
    as_pdf = output.suffix.lower() == ".pdf"
    html = render_executive_summary(loaded.register, vreport, analysis=analysis, config=cfg,
                                    client_name=client_name, prepared_by=prepared_by,
                                    pdf=as_pdf)
    if as_pdf:
        _write_pdf(lambda: html_to_pdf(html), output)
    else:
        _write(html, output)
    if validation_report is not None:
        suffix = validation_report.suffix.lower()
        if suffix == ".pdf":
            _write_pdf(lambda: render_pdf(vreport), validation_report)
        else:
            fmt = {".md": "md", ".json": "json"}.get(suffix, "html")
            _write(render(vreport, fmt), validation_report)
    if json_path is not None:
        _write(analysis.model_dump_json(indent=2), json_path)
    click.echo(_summary_line(vreport), err=True)


@main.command()
@input_arg
@click.option("-o", "--output", type=click.Path(path_type=Path), required=True,
              help="Output: a directory or .zip for xbrl-csv, a .xlsx for excel, a directory "
              "for csv.")
@click.option("--format", "fmt", type=click.Choice(["xbrl-csv", "excel", "csv"]),
              default="xbrl-csv", show_default=True)
@click.option("--unzipped", is_flag=True, help="xbrl-csv: write the package folder, not a zip.")
@click.option("--strict", is_flag=True, help="Refuse to export when validation finds errors.")
@click.option("--level", type=click.Choice(["CON", "IND", "SUB"]), default="CON",
              show_default=True, help="xbrl-csv: consolidation level used in entityID/name.")
@click.option("--entry-point", default=None, help="xbrl-csv: taxonomy entry point URL.")
@click.option("--exclude-entity", "exclude", multiple=True, metavar="LEI",
              help="xbrl-csv: leave an entity outside the DORA scope (e.g. the Swiss bank of "
              "a group) and what only concerns it out of the package (repeatable).")
@code_map_opt
def export(input_path: Path, output: Path, fmt: str, unzipped: bool, strict: bool, level: str,
           entry_point: str | None, exclude: tuple[str, ...], code_map: Path | None) -> None:
    """Export a register (xBRL-CSV package is BEST-EFFORT, see docs/ASSUMPTIONS.md)."""
    from dora_roi.io.csv_folder import write_csv_folder
    from dora_roi.io.excel import write_workbook

    cmap = _code_map(code_map)
    loaded = _load(input_path, cmap)
    register = loaded.register
    if exclude and fmt != "xbrl-csv":
        click.echo("Note: --exclude-entity only applies to the xbrl-csv package.", err=True)
    if exclude and fmt == "xbrl-csv":
        from dora_roi.scope import ScopeError, findings_in, restrict_to_scope

        try:
            register, summary = restrict_to_scope(register, {e.upper() for e in exclude})
        except ScopeError as exc:
            raise click.BadParameter(str(exc), param_hint="--exclude-entity") from exc
        click.echo(f"Outside the DORA scope: {', '.join(summary.excluded_entities)} "
                   f"({summary.total_removed} record(s) left out)", err=True)
        # the package is validated as what it is: the register restricted to the scope
        vreport = validate_register(
            register, parse_findings=findings_in(loaded.findings, register),
            source=loaded.source)
    else:
        vreport = validate_loaded(loaded)
    click.echo(_summary_line(vreport), err=True)
    if not vreport.passed:
        if strict:
            click.echo("Export refused (--strict): fix the validation errors first.", err=True)
            sys.exit(EXIT_FINDINGS)
        click.echo("Warning: exporting a register that does not pass validation.", err=True)
    if fmt == "excel":
        click.echo(f"Wrote {write_workbook(register, output)}", err=True)
        return
    if fmt == "csv":
        click.echo(f"Wrote {write_csv_folder(register, output)}", err=True)
        return
    options = XbrlCsvOptions(reporting_level=level, code_map=cmap or {})
    if entry_point:
        options.entry_point = entry_point
    result = export_xbrl_csv(register, output, options, unzipped=unzipped)
    for w in result.warnings:
        click.echo(f"! {w}", err=True)
    click.echo(f"Wrote {result.path}", err=True)


@main.command()
@click.argument("output", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--sample", is_flag=True, help="Fill the workbook with the synthetic sample "
              "register instead of leaving it blank.")
@click.option("--clean", is_flag=True, help="With --sample: omit the deliberately injected "
              "errors.")
def template(output: Path, sample: bool, clean: bool) -> None:
    """Generate a blank (or sample-filled) Excel workbook for the register."""
    from dora_roi.io.excel import write_workbook

    register = None
    if sample:
        from dora_roi.sample import generate_sample

        register = generate_sample(inject_errors=not clean).source_register
    click.echo(f"Wrote {write_workbook(register, output)}", err=True)


@main.command()
@click.option("-f", "--format", "fmt", type=click.Choice(["text", "md", "json"]),
              default="text", show_default=True)
def rules(fmt: str) -> None:
    """List all validation rules and the provisions they support."""
    cat = rules_catalogue()
    if fmt == "json":
        click.echo(json.dumps([
            {"id": r.id, "title": r.title, "severity": r.severity.value,
             "category": r.category.value, "templates": list(r.templates),
             "references": list(r.references), "description": r.description}
            for r in cat], indent=2))
        return
    if fmt == "md":
        from dora_roi.docs import regulatory_mapping_markdown

        click.echo(regulatory_mapping_markdown())
        return
    for r in cat:
        click.echo(f"{r.id:8} {r.severity.value:8} {r.title}  [{'; '.join(r.references)}]")


@main.command()
@click.argument("output", type=click.Path(path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["xlsx", "csv"]), default="xlsx",
              show_default=True)
@click.option("--clean", is_flag=True, help="Omit the deliberately injected errors.")
@click.option("--previous-year", is_flag=True,
              help="Generate last year's (clean) version of the register, for `roi diff`.")
@click.option("--inventory", is_flag=True,
              help="Generate a messy German contract inventory for the mapping wizard.")
@click.option("--seed", type=int, default=2554, show_default=True, help="Random seed.")
@click.option("--assessments", "assessments_out", type=click.Path(dir_okay=False, path_type=Path),
              help="Also write the sample Art. 30 contract assessments (.json or .xlsx).")
@click.option("--contract-document", type=click.Path(dir_okay=False, path_type=Path),
              help="Also write the sample contract document (.docx, .pdf or .txt).")
@click.option("--incidents", "incidents_out", type=click.Path(dir_okay=False, path_type=Path),
              help="Also write the sample incident log (.json); the open major incident is "
              "placed relative to now.")
def sample(output: Path, fmt: str, clean: bool, previous_year: bool, inventory: bool,
           seed: int, assessments_out: Path | None, contract_document: Path | None,
           incidents_out: Path | None) -> None:
    """Generate the synthetic sample register (fictional Swiss/EU banking group)."""
    from dora_roi.io.csv_folder import write_csv_folder
    from dora_roi.io.excel import write_workbook
    from dora_roi.sample import generate_previous_year, generate_sample

    if inventory:
        from dora_roi.sample.inventory_sample import write_sample_inventory

        click.echo(f"Wrote {write_sample_inventory(output)}", err=True)
        return
    result = (generate_previous_year(seed=seed) if previous_year
              else generate_sample(seed=seed, inject_errors=not clean))
    path = (write_workbook(result.source_register, output) if fmt == "xlsx"
            else write_csv_folder(result.source_register, output))
    click.echo(f"Wrote {path} ({len(result.injected)} injected error(s))", err=True)
    if assessments_out is not None:
        from dora_roi.contracts.analysis import contract_contexts
        from dora_roi.contracts.model import write_assessment_workbook
        from dora_roi.sample.assessments import sample_assessments

        book = sample_assessments(result.register)
        if assessments_out.suffix.lower() == ".xlsx":
            refs = {r: c.critical for r, c in contract_contexts(result.register).items()}
            write_assessment_workbook(book, assessments_out, refs)
            click.echo(f"Wrote {assessments_out}", err=True)
        else:
            _write(book.to_json(), assessments_out)
    if contract_document is not None:
        from dora_roi.sample.contract_docs import write_sample_contract

        click.echo(f"Wrote {write_sample_contract(contract_document)}", err=True)
    if incidents_out is not None:
        from dora_roi.sample.incidents import sample_incidents

        _write(sample_incidents(result.register).to_json(), incidents_out)


@main.command()
@click.argument("old_path", metavar="OLD", type=click.Path(path_type=Path))
@click.argument("new_path", metavar="NEW", type=click.Path(path_type=Path))
@click.option("-f", "--format", "fmt", type=click.Choice(["md", "json"]), default="md",
              show_default=True)
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path))
def diff(old_path: Path, new_path: Path, fmt: str, output: Path | None) -> None:
    """Compare two versions of a register (added / removed / changed records)."""
    import dataclasses

    from dora_roi.diff import diff_registers, render_diff_markdown

    old = _load(old_path, None)
    new = _load(new_path, None)
    result = diff_registers(old.register, new.register, old_path.name, new_path.name)
    if fmt == "json":
        _write(json.dumps(dataclasses.asdict(result), indent=2, default=str), output)
    else:
        _write(render_diff_markdown(result), output)


@main.command("audit-log")
@click.argument("project", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path))
def audit_log(project: Path, output: Path | None) -> None:
    """Export the change history (who/when/old/new) of a .roiproj project file as CSV."""
    from dora_roi.audit import audit_csv
    from dora_roi.project import ProjectError, load_project

    try:
        ws = load_project(project)
    except ProjectError as exc:
        raise click.UsageError(str(exc)) from exc
    _write(audit_csv(ws), output)


@main.command("check-package")
@click.argument("reference", type=click.Path(exists=True, path_type=Path))
@click.option("--ours", type=click.Path(exists=True, path_type=Path),
              help="Our package to compare (default: export of the clean Alpenrand sample).")
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path))
def check_package(reference: Path, ours: Path | None, output: Path | None) -> None:
    """Compare an xBRL-CSV package with a reference (e.g. official EBA sample) package."""
    import tempfile

    from dora_roi.io.package_check import compare_packages

    with tempfile.TemporaryDirectory() as tmp:
        if ours is None:
            from dora_roi.sample import generate_sample

            ours = export_xbrl_csv(generate_sample(inject_errors=False).register,
                                   Path(tmp)).path
        result = compare_packages(reference, ours)
    _write(result.to_markdown(), output)
    sys.exit(EXIT_FINDINGS if result.failures else 0)


def _write_report(html: str, output: Path) -> None:
    """Write an HTML report, or a PDF when ``output`` ends in ``.pdf`` (WeasyPrint)."""
    if output.suffix.lower() != ".pdf":
        _write(html, output)
        return
    from dora_roi.reporting.pdf import PdfUnavailableError, html_to_pdf

    try:
        data = html_to_pdf(html)
    except PdfUnavailableError as exc:
        raise click.ClickException(str(exc)) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    click.echo(f"Wrote {output}", err=True)


# =========================================================================== contracts

lang_opt = click.option("--lang", type=click.Choice(["en", "de"]), default="en",
                        show_default=True, help="Language of the output.")


@main.group()
def contracts() -> None:
    """DORA Art. 30 contract gap analysis (checklist, assessments, remediation plan)."""


@contracts.command("checklist")
@click.option("-f", "--format", "fmt", type=click.Choice(["text", "md", "json"]),
              default="text", show_default=True)
@lang_opt
def contracts_checklist(fmt: str, lang: str) -> None:
    """Print the Art. 30 checklist with article references."""
    from dora_roi.contracts.provisions import PROVISIONS, checklist_markdown

    if fmt == "md":
        click.echo(checklist_markdown(lang))
        return
    if fmt == "json":
        click.echo(json.dumps([
            {"id": p.id, "article": p.article, "scope": p.scope.value, "key": p.key,
             "title": p.title(lang), "requirement": p.requirement(lang),
             "remediation": p.remediation(lang), "related": list(p.related),
             "register_fields": list(p.register_fields)} for p in PROVISIONS], indent=2,
            ensure_ascii=False))
        return
    for p in PROVISIONS:
        star = "*" if p.key else " "
        click.echo(f"{p.id:11} {star} {p.article:24} {p.scope.value:8} {p.title(lang)}")


def _assessments(path: Path) -> tuple[object, list[str]]:
    from dora_roi.contracts.model import load_assessments

    try:
        return load_assessments(path)
    except (OSError, ValueError) as exc:
        raise click.BadParameter(str(exc), param_hint="--assessments") from exc


@contracts.command("assess")
@input_arg
@click.option("--assessments", "assessments_path", required=True,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Assessments (.json or .xlsx assessment workbook).")
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path),
              help="Write the remediation plan (.html, .pdf, .xlsx or .json).")
@click.option("--client", "client_name", help="Client name shown in the plan.")
@click.option("--prepared-by", help="Author shown in the plan.")
@click.option("--plan-date", type=click.DateTime(["%Y-%m-%d"]), default=None,
              help="Date the target dates are computed from (default: today).")
@click.option("--fail-on-gaps", is_flag=True,
              help="Exit with status 1 if high-priority gaps exist.")
@lang_opt
@code_map_opt
def contracts_assess(input_path: Path, assessments_path: Path, output: Path | None,
                     client_name: str | None, prepared_by: str | None, plan_date: object,
                     fail_on_gaps: bool, lang: str, code_map: Path | None) -> None:
    """Evaluate a register's arrangements against Art. 30 and build the remediation plan."""
    from dora_roi.contracts.analysis import evaluate, remediation_plan
    from dora_roi.contracts.model import AssessmentBook
    from dora_roi.contracts.report import render_plan_html, write_plan_workbook

    loaded = _load(input_path, _code_map(code_map))
    book, problems = _assessments(assessments_path)
    assert isinstance(book, AssessmentBook)
    for msg in problems:
        click.echo(f"! {assessments_path.name}: {msg}", err=True)
    pf = evaluate(loaded.register, book)
    when = plan_date.date() if hasattr(plan_date, "date") else None
    plan = remediation_plan(pf, when)
    counts, pc = pf.counts(), plan.counts()
    click.echo(f"Arrangements: {len(pf.contracts)} ({len(pf.critical_contracts)} supporting "
               f"critical functions) · assessed: {len(pf.contracts) - counts['not_assessed']} · "
               f"compliant: {counts['compliant']} · with gaps: {counts['gaps']} · "
               f"incomplete: {counts['incomplete']}", err=True)
    click.echo(f"Remediation actions: {len(plan.items)} (high {pc['high']}, medium "
               f"{pc['medium']}, low {pc['low']}); {len(plan.exceptions)} approved "
               f"exception(s); orphan assessments: {len(pf.orphans)}", err=True)
    if output is None:
        for i in plan.items[:20]:
            click.echo(f"{i.priority.value:6} {i.contract_ref:14} {i.provision.id:11} "
                       f"{i.status.value:8} {i.providers}")
        if len(plan.items) > 20:
            click.echo(f"… {len(plan.items) - 20} more (use -o plan.html or plan.xlsx)")
    elif output.suffix.lower() == ".xlsx":
        click.echo(f"Wrote {write_plan_workbook(plan, output, lang=lang, client=client_name)}",
                   err=True)
    elif output.suffix.lower() == ".json":
        _write(json.dumps({
            "schema": "dora-roi-toolkit/art30-remediation-plan/v1",
            "plan_date": plan.plan_date.isoformat(), "counts": pc,
            "contracts": {c.ref: {"status": c.status.value, "critical": c.context.critical,
                                  "missing": c.missing, "partial": c.partial,
                                  "not_assessed": c.unassessed,
                                  "inherited_from": c.inherited_from} for c in pf.contracts},
            "actions": [{"priority": i.priority.value, "contract_ref": i.contract_ref,
                         "providers": i.providers, "provision": i.provision.id,
                         "article": i.provision.article, "status": i.status.value,
                         "clause_ref": i.clause_ref, "evidence": i.evidence,
                         "target_date": i.target_date.isoformat(),
                         "target_agreed": i.due is not None, "progress": i.progress_key,
                         "owner": i.owner, "overdue": i.overdue(plan.plan_date),
                         "proposed_date_passed": i.late(plan.plan_date),
                         "applies_to": list(i.applies_to)} for i in plan.items],
            "exceptions": [{"contract_ref": e.contract_ref, "provision": e.provision.id,
                            "status": e.status.value, "reason": e.reason,
                            "approver": e.approver,
                            "until": e.until.isoformat() if e.until else None}
                           for e in plan.exceptions],
        }, indent=2, ensure_ascii=False), output)
    else:
        _write_report(render_plan_html(plan, lang=lang, client=client_name,
                                       prepared_by=prepared_by), output)
    if fail_on_gaps and pc["high"]:
        sys.exit(EXIT_FINDINGS)


@contracts.command("template")
@input_arg
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), required=True,
              help="Assessment workbook to write (.xlsx).")
@click.option("--assessments", "assessments_path",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Pre-fill with existing assessments.")
@lang_opt
@code_map_opt
def contracts_template(input_path: Path, output: Path, assessments_path: Path | None,
                       lang: str, code_map: Path | None) -> None:
    """Write an assessment workbook: one row per arrangement and applicable provision."""
    from dora_roi.contracts.analysis import contract_contexts
    from dora_roi.contracts.model import AssessmentBook, write_assessment_workbook

    loaded = _load(input_path, _code_map(code_map))
    book = AssessmentBook()
    if assessments_path is not None:
        found, _ = _assessments(assessments_path)
        assert isinstance(found, AssessmentBook)
        book = found
    refs = {r: c.critical for r, c in contract_contexts(loaded.register).items()}
    click.echo(f"Wrote {write_assessment_workbook(book, output, refs, lang=lang)}", err=True)


@contracts.command("suggest")
@click.argument("document", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--contract-ref", help="Arrangement reference (B_02.01 c0010) for the draft.")
@click.option("--not-critical", is_flag=True,
              help="Only Art. 30(2): the arrangement supports no critical function.")
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path),
              help="Write a draft assessment file (.json) for review.")
@lang_opt
def contracts_suggest(document: Path, contract_ref: str | None, not_critical: bool,
                      output: Path | None, lang: str) -> None:
    """Keyword-based SUGGESTIONS for a contract document (.pdf, .docx, .txt) – review them."""
    from dora_roi.contracts.extract import ExtractionError, extract_text
    from dora_roi.contracts.model import AssessmentBook, ContractAssessment
    from dora_roi.contracts.suggest import apply_suggestions, suggest

    try:
        extracted = extract_text(document.name, document.read_bytes())
    except ExtractionError as exc:
        raise click.UsageError(str(exc)) from exc
    result = suggest(extracted.text, critical=not not_critical)
    click.echo(f"{document.name}: {extracted.words} words, {result.headings} clause headings. "
               "Suggestions only – review every item against the contract.", err=True)
    for i in result.items:
        click.echo(f"{i.provision.id:11} {i.suggestion.value:17} {i.clause_ref or '-':8} "
                   f"{i.provision.title(lang)}")
    if output is not None:
        ref = contract_ref or document.stem
        draft = apply_suggestions(ContractAssessment(contract_ref=ref, document=document.name),
                                  result, lang=lang)
        book = AssessmentBook()
        book.save(draft, summary="Draft from keyword suggestions (not reviewed)")
        _write(book.to_json(), output)


# =========================================================================== incidents


def _now_opt(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.now(UTC)


now_opt = click.option("--now", "now_value", type=click.DateTime(
    ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]), default=None,
    help="Evaluate as of this UTC time (default: now), e.g. 2025-11-20T10:00.")


def _incident_log(path: Path) -> object:
    from dora_roi.incidents.model import IncidentLog

    try:
        return IncidentLog.from_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise click.BadParameter(str(exc), param_hint="LOG") from exc


@main.group()
def incidents() -> None:
    """Major ICT-related incident classification and reporting deadlines (DORA Art. 18/19)."""


@incidents.command("criteria")
@lang_opt
def incidents_criteria(lang: str) -> None:
    """Print the classification criteria, thresholds and reporting time limits."""
    from dora_roi.incidents.criteria import DEFAULT_THRESHOLDS as TH
    from dora_roi.incidents.criteria import criteria

    for c in criteria():
        click.echo(f"{c.title(lang)} [{c.dora}; {c.rts}]\n    {c.threshold(lang)}")
    click.echo("Major: critical services affected AND (malicious unauthorised access OR "
               "thresholds of >= 2 other criteria met).")
    click.echo(f"Reporting: initial {TH.initial_after_classification_hours} h after "
               f"classification (max. {TH.initial_after_awareness_hours} h after awareness); "
               f"intermediate {TH.intermediate_after_initial_hours} h after the initial "
               f"notification; final {TH.final_after_intermediate_months} month after the "
               "intermediate report.")


@incidents.command("summary")
@click.argument("log_path", metavar="LOG", type=click.Path(exists=True, dir_okay=False,
                                                           path_type=Path))
@click.option("--register", "register_path", type=click.Path(path_type=Path),
              help="Register to resolve providers, arrangements and functions.")
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path),
              help="Write the summary (.html, .pdf, .json or .md); default: text to stdout.")
@click.option("--client", "client_name", help="Client name shown in the HTML summary.")
@click.option("--fail-on-overdue", is_flag=True,
              help="Exit with status 1 if a reporting deadline is overdue.")
@now_opt
@lang_opt
def incidents_summary(log_path: Path, register_path: Path | None, output: Path | None,
                      client_name: str | None, fail_on_overdue: bool, now_value: object,
                      lang: str) -> None:
    """Classify every incident of a log and show reporting deadlines and recurring series."""
    from dora_roi.incidents.model import IncidentLog
    from dora_roi.incidents.report import (
        overview,
        render_summary_html,
        summary_dict,
        summary_markdown,
    )

    log = _incident_log(log_path)
    assert isinstance(log, IncidentLog)
    register = _load(register_path, None).register if register_path else None
    now = _now_opt(now_value)
    ov = overview(log, register, now)
    if output is None:
        for v in ov.views:
            nxt = v.next
            due = f"{nxt.kind.value} due {nxt.due:%Y-%m-%d %H:%M} UTC ({nxt.state(now).value})" \
                if nxt else "-"
            click.echo(f"{v.incident.id:14} {v.classification.outcome.value:12} "
                       f"{v.incident.status.value:9} {due:48} {v.incident.title}")
        for g in ov.recurring:
            click.echo(f"recurring {g.key}: {', '.join(i.id for i in g.incidents)} -> "
                       f"{g.classification.outcome.value}")
    elif output.suffix.lower() == ".json":
        _write(json.dumps(summary_dict(ov, log.timezone), indent=2, ensure_ascii=False), output)
    elif output.suffix.lower() == ".md":
        _write(summary_markdown(ov, lang), output)
    else:
        _write_report(render_summary_html(ov, lang=lang, client=client_name,
                                          timezone=log.timezone), output)
    counts = ov.counts()
    click.echo(f"{counts['total']} incident(s): {counts['major']} major, "
               f"{counts['undetermined']} undetermined, {counts['overdue']} overdue report(s), "
               f"{counts['recurring_major']} recurring series meeting the criteria", err=True)
    if fail_on_overdue and counts["overdue"]:
        sys.exit(EXIT_FINDINGS)


# =========================================================================== FINMA


@main.command()
@input_arg
@click.option("--assessments", "assessments_path",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Art. 30 assessments (.json/.xlsx) as evidence for contract requirements.")
@click.option("--incidents", "incidents_path",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Incident log (.json) as evidence for incident management.")
@click.option("-f", "--format", "fmt", type=click.Choice(["text", "md", "json"]),
              default="text", show_default=True)
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path))
@lang_opt
@code_map_opt
def finma(input_path: Path, assessments_path: Path | None, incidents_path: Path | None,
          fmt: str, output: Path | None, lang: str, code_map: Path | None) -> None:
    """Swiss angle: which RoI data covers FINMA Circ. 2018/3 and 2023/1, and what is missing."""
    from dora_roi.contracts.analysis import evaluate
    from dora_roi.contracts.model import AssessmentBook
    from dora_roi.finma import evaluate_finma, mapping_markdown
    from dora_roi.incidents.model import IncidentLog

    loaded = _load(input_path, _code_map(code_map))
    portfolio = None
    if assessments_path is not None:
        book, _ = _assessments(assessments_path)
        assert isinstance(book, AssessmentBook)
        portfolio = evaluate(loaded.register, book)
    log = _incident_log(incidents_path) if incidents_path is not None else None
    assert log is None or isinstance(log, IncidentLog)
    view = evaluate_finma(loaded.register, portfolio, log)
    if fmt == "json":
        _write(json.dumps({
            "schema": "dora-roi-toolkit/finma-mapping/v1",
            "coverage_score": round(view.coverage_score, 4), "counts": view.counts(),
            "requirements": [{
                "id": s.requirement.id, "circular": s.requirement.circular,
                "title": s.requirement.title(lang), "coverage_by_design":
                s.requirement.coverage.value, "coverage_in_register": s.effective.value,
                "roi_fields": {str(f): s.field_fill.get(str(f)) for f in s.requirement.fields},
                "art30": list(s.requirement.art30), "art30_share": s.art30_share,
                "incidents_classified": s.incidents_classified,
                "missing": s.requirement.gap(lang)} for s in view.statuses],
            "swiss_context": {
                "entity_countries": view.context.entity_countries,
                "swiss_providers": [n for _, n in view.context.swiss_providers],
                "swiss_spend_share": round(view.context.swiss_spend_share, 4)},
        }, indent=2, ensure_ascii=False), output)
        return
    if fmt == "md":
        _write(mapping_markdown(lang), output)
        return
    lines = [f"{s.requirement.id:10} {s.effective.value:8} "
             f"(design {s.requirement.coverage.value:7}) {s.requirement.title(lang)}"
             for s in view.statuses]
    c = view.counts()
    lines.append(f"Coverage score {view.coverage_score:.0%}: {c['full']} covered, "
                 f"{c['partial']} partly, {c['none']} not covered.")
    _write("\n".join(lines), output)


# =========================================================================== readiness


@main.command()
@input_arg
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), required=True,
              help="Output file: .html (print-friendly) or .pdf (needs the 'pdf' extra).")
@click.option("--assessments", "assessments_path",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Art. 30 assessments (.json or .xlsx).")
@click.option("--incidents", "incidents_path",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Incident log (.json).")
@click.option("--client", "client_name", help="Client name shown in the title.")
@click.option("--prepared-by", help="Author shown in the header.")
@click.option("--no-finma", is_flag=True, help="Leave out the Swiss (FINMA) section.")
@click.option("--json", "json_path", type=click.Path(dir_okay=False, path_type=Path),
              help="Also write the traffic lights and actions as JSON.")
@click.option("--exclude-entity", "exclude", multiple=True, metavar="LEI",
              help="Entity outside the DORA scope: the register light shows the submission "
              "without it (as `roi export --exclude-entity`). Repeatable.")
@now_opt
@lang_opt
@code_map_opt
def readiness(input_path: Path, output: Path, assessments_path: Path | None,
              incidents_path: Path | None, client_name: str | None, prepared_by: str | None,
              no_finma: bool, json_path: Path | None, exclude: tuple[str, ...],
              now_value: object, lang: str, code_map: Path | None) -> None:
    """DORA readiness report for a CRO: register, Art. 30 contracts, incidents, concentration."""
    from dora_roi.analytics import analyse
    from dora_roi.contracts.analysis import evaluate, remediation_plan
    from dora_roi.contracts.model import AssessmentBook
    from dora_roi.finma import evaluate_finma
    from dora_roi.incidents.model import IncidentLog
    from dora_roi.incidents.report import overview
    from dora_roi.quality import quality_score
    from dora_roi.readiness import build_readiness, render_readiness_html

    loaded = _load(input_path, _code_map(code_map))
    report = validate_loaded(loaded)
    if exclude:
        from dora_roi.scope import ScopeError, findings_in, restrict_to_scope

        try:
            dora, _ = restrict_to_scope(loaded.register, {e.upper() for e in exclude})
        except ScopeError as exc:
            raise click.BadParameter(str(exc), param_hint="--exclude-entity") from exc
        report = validate_register(dora, parse_findings=findings_in(loaded.findings, dora),
                                   source=loaded.source)
    book = AssessmentBook()
    if assessments_path is not None:
        found, _ = _assessments(assessments_path)
        assert isinstance(found, AssessmentBook)
        book = found
    log = _incident_log(incidents_path) if incidents_path is not None else IncidentLog()
    assert isinstance(log, IncidentLog)
    now = _now_opt(now_value)
    reg = loaded.register
    portfolio = evaluate(reg, book)
    view = build_readiness(
        report=report, quality=quality_score(report), analysis=analyse(reg),
        portfolio=portfolio, plan=remediation_plan(portfolio, now.date()),
        incidents=overview(log, reg, now),
        finma=None if no_finma else evaluate_finma(reg, portfolio, log, now),
        lang=lang, now=now, register=reg, out_of_scope=len(set(exclude)))
    _write_report(render_readiness_html(view, lang=lang, client=client_name,
                                        prepared_by=prepared_by), output)
    if json_path is not None:
        _write(json.dumps({
            "schema": "dora-roi-toolkit/readiness/v1", "generated_at": now.isoformat(),
            "overall": view.overall.value,
            "pillars": [{"key": p.key, "status": p.rag.value, "metric": p.metric,
                         "details": p.lines} for p in view.pillars],
            "actions": [{"priority": a.priority, "area": a.pillar, "action": a.text}
                        for a in view.actions],
        }, indent=2, ensure_ascii=False), json_path)
    click.echo(f"Overall: {view.overall.value} · " + " · ".join(
        f"{p.key} {p.rag.value}" for p in view.pillars), err=True)


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option("--access-log", is_flag=True,
              help="Log every request line (off by default: URLs can contain client data).")
@click.option("--projects", "projects", type=click.Path(file_okay=False, path_type=Path),
              default=None, help="Folder where workspaces are autosaved as .roiproj project "
              "files and listed for reopening (single-user mode).")
def serve(host: str, port: int, access_log: bool, projects: Path | None) -> None:
    """Start the web UI (requires the 'web' extra)."""
    try:
        import uvicorn

        from dora_roi.web.app import create_app
    except ImportError as exc:
        raise click.ClickException(
            "The web UI needs extra dependencies: pip install 'dora-roi-toolkit[web]'") from exc
    uvicorn.run(create_app(projects_dir=projects), host=host, port=port, access_log=access_log,
                server_header=False,
                log_level="warning")


if __name__ == "__main__":  # pragma: no cover
    main()
