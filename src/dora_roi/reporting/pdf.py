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
import os
import threading
from typing import Any, NoReturn

__all__ = ["PdfBusyError", "PdfUnavailableError", "html_to_pdf", "pdf_available"]

#: Concurrent PDF renders (each takes seconds of CPU and ~100 MB): ``ROI_MAX_PDF_JOBS``.
_JOBS = threading.BoundedSemaphore(max(1, int(os.environ.get("ROI_MAX_PDF_JOBS", "2") or 2)))

INSTALL_HINT = ('PDF export needs WeasyPrint: pip install "dora-roi-toolkit[pdf]" (and the Pango '
                "library, see https://doc.courtbouillon.org/weasyprint/stable/first_steps.html), "
                "or use the Docker image. Alternatively open the HTML report and print it to PDF.")


class PdfUnavailableError(RuntimeError):
    """WeasyPrint (or the system libraries it needs) is not installed."""


class PdfBusyError(RuntimeError):
    """Too many PDFs are being rendered at the same time; try again shortly."""


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


def html_to_pdf(html: str, *, wait: float = 60.0) -> bytes:
    """Render a self-contained HTML report to PDF bytes (title taken from ``<title>``).

    At most ``ROI_MAX_PDF_JOBS`` renders run at once; a caller waits up to ``wait`` seconds
    for a slot and then gets :class:`PdfBusyError`.
    """
    weasyprint = _weasyprint()
    if not _JOBS.acquire(timeout=wait):
        raise PdfBusyError("the server is busy rendering other PDFs; please try again")
    try:
        document = weasyprint.HTML(string=html, url_fetcher=_no_fetch(weasyprint),
                                   base_url=None)
        pdf: bytes = document.write_pdf(presentational_hints=True)
    finally:
        _JOBS.release()
    return pdf
