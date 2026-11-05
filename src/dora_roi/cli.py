"""Command-line interface: ``roi validate | report | export | template | rules | …``."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

import click

from dora_roi import __version__
from dora_roi.api import validate_loaded
from dora_roi.io.loader import LoadResult, UnsupportedInputError, load
from dora_roi.io.xbrl_csv import CodeMap, XbrlCsvOptions, export_xbrl_csv, load_code_map
from dora_roi.validation import Severity, ValidationConfig, ValidationReport, rules_catalogue

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
@code_map_opt
def export(input_path: Path, output: Path, fmt: str, unzipped: bool, strict: bool, level: str,
           entry_point: str | None, code_map: Path | None) -> None:
    """Export a register (xBRL-CSV package is BEST-EFFORT, see docs/ASSUMPTIONS.md)."""
    from dora_roi.io.csv_folder import write_csv_folder
    from dora_roi.io.excel import write_workbook

    cmap = _code_map(code_map)
    loaded = _load(input_path, cmap)
    vreport = validate_loaded(loaded)
    click.echo(_summary_line(vreport), err=True)
    if not vreport.passed:
        if strict:
            click.echo("Export refused (--strict): fix the validation errors first.", err=True)
            sys.exit(EXIT_FINDINGS)
        click.echo("Warning: exporting a register that does not pass validation.", err=True)
    if fmt == "excel":
        click.echo(f"Wrote {write_workbook(loaded.register, output)}", err=True)
        return
    if fmt == "csv":
        click.echo(f"Wrote {write_csv_folder(loaded.register, output)}", err=True)
        return
    options = XbrlCsvOptions(reporting_level=level, code_map=cmap or {})
    if entry_point:
        options.entry_point = entry_point
    result = export_xbrl_csv(loaded.register, output, options, unzipped=unzipped)
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
def sample(output: Path, fmt: str, clean: bool, previous_year: bool, inventory: bool,
           seed: int) -> None:
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
