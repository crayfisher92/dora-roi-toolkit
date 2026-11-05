"""Text extraction from contract documents (PDF, DOCX, plain text) – locally, no network.

* **DOCX** is read with the standard library (``zipfile`` + ``xml.etree``): the body,
  headers, footers, footnotes and endnotes. Documents declaring a DTD are rejected (no
  entity expansion), and the uncompressed size is bounded (zip-bomb guard).
* **PDF** needs the optional ``pypdf`` package (``pip install 'dora-roi-toolkit[contracts]'``,
  included in the ``web`` extra). Scanned PDFs without a text layer yield no text; OCR is
  deliberately out of scope.
* **TXT / MD** are decoded as UTF-8 (falling back to Windows-1252).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024
MAX_PDF_PAGES = 400
SUFFIXES = (".pdf", ".docx", ".txt", ".md")

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DOCX_PARTS = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")


class ExtractionError(ValueError):
    """The document could not be read (unsupported, corrupt, encrypted or empty)."""


@dataclass(frozen=True)
class ExtractedText:
    name: str
    kind: str  # pdf | docx | text
    text: str
    pages: int | None = None
    warnings: tuple[str, ...] = ()

    @property
    def words(self) -> int:
        return len(self.text.split())


def extract_text(name: str, data: bytes) -> ExtractedText:
    """Extract plain text from a contract document given its file name and bytes."""
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ExtractionError("document is larger than 25 MB")
    lower = name.lower()
    if lower.endswith(".docx"):
        result = _docx(name, data)
    elif lower.endswith(".pdf"):
        result = _pdf(name, data)
    elif lower.endswith((".txt", ".md")):
        result = ExtractedText(name, "text", _decode(data))
    else:
        raise ExtractionError(f"unsupported document type {name!r} (use .pdf, .docx or .txt)")
    if not result.text.strip():
        raise ExtractionError("no text found in the document" + (
            " (scanned PDF without a text layer? OCR is not supported)"
            if result.kind == "pdf" else ""))
    return result


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _docx(name: str, data: bytes) -> ExtractedText:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ExtractionError("not a valid .docx file") from exc
    with zf:
        parts = [i for i in zf.infolist() if _DOCX_PARTS.match(i.filename)]
        if not any(i.filename == "word/document.xml" for i in parts):
            raise ExtractionError("not a Word document (word/document.xml missing)")
        if sum(i.file_size for i in parts) > MAX_UNCOMPRESSED_BYTES:
            raise ExtractionError("document is too large when uncompressed")
        order = {"document": 0, "header": 1, "footer": 2, "footnotes": 3, "endnotes": 4}
        parts.sort(key=lambda i: order.get(re.sub(r"\d+", "", i.filename[5:-4]), 9))
        chunks: list[str] = []
        for info in parts:
            xml = zf.read(info)
            if b"<!DOCTYPE" in xml[:4096] or b"<!ENTITY" in xml:
                raise ExtractionError("document declares a DTD; refused for safety")
            chunks.append(_docx_xml_text(xml))
    return ExtractedText(name, "docx", "\n".join(c for c in chunks if c.strip()))


def _docx_xml_text(xml: bytes) -> str:
    try:
        root = ElementTree.fromstring(xml)  # DTDs are rejected above
    except ElementTree.ParseError as exc:
        raise ExtractionError("corrupt .docx content") from exc
    paragraphs: list[str] = []
    for p in root.iter(f"{_W}p"):
        parts: list[str] = []
        for node in p.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def pdf_supported() -> bool:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


def _pdf(name: str, data: bytes) -> ExtractedText:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise ExtractionError("PDF support needs the optional 'pypdf' package: "
                              "pip install 'dora-roi-toolkit[contracts]'") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError("the PDF is encrypted")
        pages = reader.pages
        warnings: list[str] = []
        count = len(pages)
        if count > MAX_PDF_PAGES:
            warnings.append(f"only the first {MAX_PDF_PAGES} of {count} pages were read")
        texts = [(pages[i].extract_text() or "") for i in range(min(count, MAX_PDF_PAGES))]
    except ExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise ExtractionError(f"could not read the PDF ({type(exc).__name__})") from exc
    return ExtractedText(name, "pdf", "\n".join(texts), pages=count, warnings=tuple(warnings))
