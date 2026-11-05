"""Time import, validation, analytics, exports and every workbench page on a large register.

Usage::

    python scripts/profile_large.py [--contracts 10000] [--providers 1000] [--budget 3]

Prints one line per step and exits non-zero if any step exceeds the budget (seconds).
Results for the reference machine are recorded in ``docs/PERFORMANCE.md``.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Any

RESULTS: list[tuple[str, float]] = []


@contextmanager
def timed(label: str) -> Iterator[None]:
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    RESULTS.append((label, elapsed))
    print(f"{label:<44} {elapsed:7.2f} s", flush=True)


def run(fn: Callable[[], Any], label: str) -> Any:
    with timed(label):
        return fn()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contracts", type=int, default=10_000)
    ap.add_argument("--providers", type=int, default=1_000)
    ap.add_argument("--budget", type=float, default=3.0)
    ap.add_argument("--skip-web", action="store_true")
    args = ap.parse_args()

    from fastapi.testclient import TestClient

    from dora_roi.analytics import analyse
    from dora_roi.io.csv_folder import write_csv_folder
    from dora_roi.io.excel import write_workbook
    from dora_roi.io.loader import load
    from dora_roi.io.xbrl_csv import export_xbrl_csv
    from dora_roi.reporting.executive import render_executive_summary
    from dora_roi.reporting.validation_report import render_html
    from dora_roi.sample.large import generate_large
    from dora_roi.validation import validate
    from dora_roi.web.app import create_app

    res = run(lambda: generate_large(args.contracts, args.providers), "generate (not budgeted)")
    reg = res.register
    counts = reg.counts()
    print(f"  {counts['B_02.01']} contracts, {counts['B_05.01']} providers, "
          f"{sum(counts.values())} rows in total")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        xlsx = run(lambda: write_workbook(reg, d / "large.xlsx"), "export Excel")
        run(lambda: write_csv_folder(reg, d / "csv"), "export CSV folder")
        run(lambda: export_xbrl_csv(reg, d / "xbrl"), "export xBRL-CSV")
        loaded = run(lambda: load(xlsx), "import Excel (parse + typed model)")
        run(lambda: load(d / "csv"), "import CSV folder")
        report = run(lambda: validate(loaded.register, parse_findings=loaded.findings),
                     "validate (63 rules)")
        analysis = run(lambda: analyse(loaded.register), "concentration analytics")
        run(lambda: render_executive_summary(loaded.register, report, analysis=analysis),
            "executive summary HTML")
        run(lambda: render_html(report), "validation report HTML")
        if not args.skip_web:
            client = TestClient(create_app())
            with xlsx.open("rb") as fh:
                data = fh.read()
            r = run(lambda: client.post("/import", files={"file": ("large.xlsx", data)},
                                        follow_redirects=False), "web: upload + first page")
            url = r.headers["location"]
            pages = ["", "/fix", "/register", "/register/B_02.02", "/register/B_05.01",
                     "/analyse", "/renewals", "/export", "/compare", "/audit", "/versions"]
            for page in pages:
                resp = run(partial(client.get, url + page), f"web: GET {page or '/'}")
                assert resp.status_code == 200, (page, resp.status_code)
            code = reg.b_05_01[0].provider_code
            run(lambda: client.get(f"{url}/provider/{code}"), "web: provider page")
            run(lambda: client.get(f"{url}/register/B_02.01/4"), "web: record page")
            run(lambda: client.post(url + "/cell", data={
                "template": "B_02.01", "row": "4", "column": "c0050", "value": "123"}),
                "web: inline cell edit (revalidate)")
            from dora_roi.reporting.pdf import pdf_available

            kinds = ["xlsx", "xbrl", "executive.html", "project", "audit.csv"]
            kinds += ["executive.pdf", "validation.pdf"] if pdf_available() else []
            for kind in kinds:
                run(partial(client.get, f"{url}/download/{kind}"), f"web: download {kind}")
    slow = [(label, s) for label, s in RESULTS
            if s > args.budget and "not budgeted" not in label]
    for label, s in slow:
        print(f"SLOW: {label} {s:.2f} s > {args.budget} s", file=sys.stderr)
    return 1 if slow else 0


if __name__ == "__main__":
    sys.exit(main())
