"""Input size limits protecting against decompression bombs and oversized uploads.

Limits can be tuned with environment variables (``ROI_MAX_UNCOMPRESSED_MB``,
``ROI_MAX_ROWS_PER_TABLE``). ``docs/BACKLOG.md`` B-02.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path


class InputTooLargeError(ValueError):
    """The input exceeds a configured size limit."""


def max_uncompressed_bytes() -> int:
    return int(os.environ.get("ROI_MAX_UNCOMPRESSED_MB", "200")) * 1024 * 1024


def max_rows_per_table() -> int:
    return int(os.environ.get("ROI_MAX_ROWS_PER_TABLE", "100000"))


def check_archive(path: str | Path) -> None:
    """Reject zip-based files (``.zip``, ``.xlsx``) whose content would expand too much.

    Uses the sizes declared in the central directory, plus a compression-ratio guard for
    members that lie about their size.
    """
    p = Path(path)
    if not zipfile.is_zipfile(p):
        return
    limit = max_uncompressed_bytes()
    with zipfile.ZipFile(p) as zf:
        infos = zf.infolist()
        if len(infos) > 10_000:
            raise InputTooLargeError(f"archive contains {len(infos)} files (limit 10000)")
        total = sum(i.file_size for i in infos)
        if total > limit:
            mb = 1024 * 1024
            raise InputTooLargeError(
                f"archive expands to {total // mb} MB (limit {limit // mb} MB)")
        for i in infos:
            if i.compress_size and i.file_size / i.compress_size > 1000 and i.file_size > 10**7:
                raise InputTooLargeError(f"suspicious compression ratio for {i.filename}")


def check_rows(template: str, count: int) -> None:
    limit = max_rows_per_table()
    if count > limit:
        raise InputTooLargeError(
            f"{template} has more than {limit} rows (set ROI_MAX_ROWS_PER_TABLE to raise the "
            "limit)")
