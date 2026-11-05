"""PDF rendering of the HTML reports (executive summary, validation report).

The PDF is produced from the same HTML as the downloadable report, laid out by the print
stylesheet in ``_style.css.j2`` (A4, page numbers, no interactive controls), so the HTML,
the browser's *Print → Save as PDF* and the generated PDF look alike (``docs/DECISIONS.md``
D-047).

WeasyPrint is an optional dependency (``pip install "dora-roi-toolkit[pdf]"``; it needs the
Pango text-layout library, which the Docker image includes). Without it,
:func:`pdf_available` is ``False`` and :func:`html_to_pdf` raises :class:`PdfUnavailableError`
with installation advice.

Security: reports contain client data and are rendered offline. The URL fetcher refuses
every external resource – no network requests, no ``file://`` reads – so nothing in the
document can make the renderer fetch or embed anything (the reports are self-contained
anyway).
"""

from __future__ import annotations

import importlib.util
from typing import Any, NoReturn

__all__ = ["PdfUnavailableError", "html_to_pdf", "pdf_available"]

INSTALL_HINT = ('PDF export needs WeasyPrint: pip install "dora-roi-toolkit[pdf]" (and the Pango '
                "library, see https://doc.courtbouillon.org/weasyprint/stable/first_steps.html), "
                "or use the Docker image. Alternatively open the HTML report and print it to PDF.")


class PdfUnavailableError(RuntimeError):
    """WeasyPrint (or the system libraries it needs) is not installed."""


def _refuse(url: str, *args: Any, **kwargs: Any) -> NoReturn:
    raise ValueError(f"external resources are disabled in PDF reports: {url[:80]}")


def _weasyprint() -> Any:
    if importlib.util.find_spec("weasyprint") is None:
        raise PdfUnavailableError(INSTALL_HINT)
    try:
        import weasyprint
    except OSError as exc:  # pragma: no cover - Python package present, Pango missing
        raise PdfUnavailableError(f"{INSTALL_HINT} ({exc})") from exc
    return weasyprint


def pdf_available() -> bool:
    """True if PDFs can be rendered in this installation."""
    try:
        _weasyprint()
    except PdfUnavailableError:
        return False
    return True


def _no_fetch(weasyprint: Any) -> Any:
    """A URL fetcher that refuses every URL, in the form this WeasyPrint version expects."""
    base = getattr(getattr(weasyprint, "urls", None), "URLFetcher", None)
    if base is None:  # pragma: no cover - WeasyPrint < 66 takes a plain function
        return _refuse

    class NoFetch(base):  # type: ignore[misc, valid-type]
        def fetch(self, url: str, headers: Any = None) -> Any:
            return _refuse(url)

    return NoFetch(allowed_protocols=(), fail_on_errors=False)


def html_to_pdf(html: str) -> bytes:
    """Render a self-contained HTML report to PDF bytes (title taken from ``<title>``)."""
    weasyprint = _weasyprint()
    document = weasyprint.HTML(string=html, url_fetcher=_no_fetch(weasyprint), base_url=None)
    pdf: bytes = document.write_pdf(presentational_hints=True)
    return pdf
