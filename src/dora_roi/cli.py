"""Command-line interface: ``roi validate | report | export | template | rules | …``."""

from __future__ import annotations

import json
import sys
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
@click.option("-f", "--format", "fmt", type=click.Choice(["text", "json", "md", "html"]),
              default="text", show_default=True, help="Report format.")
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

    ref = reference_date.date() if hasattr(reference_date, "date") else None
    loaded = _load(input_path, _code_map(code_map))
    report = validate_loaded(loaded, _config(disable, ref, downgrade))
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
              help="Output HTML file for the executive summary.")
@click.option("--client", "client_name", help="Client name shown in the title.")
@click.option("--prepared-by", help="Author shown in the header.")
@click.option("--validation-report", type=click.Path(dir_okay=False, path_type=Path),
              help="Also write the detailed validation report (format from extension: "
              ".html, .md or .json).")
@click.option("--json", "json_path", type=click.Path(dir_okay=False, path_type=Path),
              help="Also write the concentration analysis as JSON.")
@ref_date_opt
@code_map_opt
def report(input_path: Path, output: Path, client_name: str | None, prepared_by: str | None,
           validation_report: Path | None, json_path: Path | None, reference_date: object,
           code_map: Path | None) -> None:
    """Generate the executive summary (HTML) with concentration-risk analytics."""
    from dora_roi.analytics import AnalyticsConfig, analyse
    from dora_roi.reporting import render
    from dora_roi.reporting.executive import render_executive_summary

    ref = reference_date.date() if hasattr(reference_date, "date") else None
    loaded = _load(input_path, _code_map(code_map))
    vreport = validate_loaded(loaded, _config((), ref))
    cfg = AnalyticsConfig(reference_date=ref)
    analysis = analyse(loaded.register, cfg)
    html = render_executive_summary(loaded.register, vreport, analysis=analysis, config=cfg,
                                    client_name=client_name, prepared_by=prepared_by)
    _write(html, output)
    if validation_report is not None:
        fmt = {".md": "md", ".json": "json"}.get(validation_report.suffix.lower(), "html")
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
def template(output: Path) -> None:
    """Generate a blank Excel workbook for the register."""
    from dora_roi.io.excel import write_blank_template

    click.echo(f"Wrote {write_blank_template(output)}", err=True)


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


if __name__ == "__main__":  # pragma: no cover
    main()
