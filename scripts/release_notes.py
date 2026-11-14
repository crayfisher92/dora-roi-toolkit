"""Print the CHANGELOG section of a version (used as the GitHub release notes).

    python scripts/release_notes.py 0.1.0            # notes for v0.1.0
    python scripts/release_notes.py --check v0.1.0   # also verify tag == package version

Exits non-zero when the section is missing or empty, or (with ``--check``) when the tag does
not match ``dora_roi.__version__`` – so a release can never go out with the wrong version or
without notes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?\s*$")


def section(changelog: str, version: str) -> str:
    """The body of ``## [version]`` up to the next ``## `` heading (without link refs)."""
    lines = changelog.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        m = HEADING.match(line)
        if m:
            if inside:
                break
            inside = m["version"] == version
            if inside and not m["date"]:
                raise ValueError(f"version {version} has no release date in CHANGELOG.md")
            continue
        if inside:
            if re.match(r"^\[[^\]]+\]: https?://", line):
                break
            out.append(line)
    text = "\n".join(out).strip()
    if not text:
        raise ValueError(f"CHANGELOG.md has no notes for version {version}")
    return text


def absolute_links(text: str, repo_url: str, ref: str) -> str:
    """Relative Markdown links break on the release page; point them at the tagged files."""
    return re.sub(r"\]\((?!https?://|#|mailto:)([^)\s]+)\)",
                  lambda m: f"]({repo_url}/blob/{ref}/{m[1].lstrip('./')})", text)


def package_version() -> str:
    init = (ROOT / "src" / "dora_roi" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__ = "([^"]+)"', init, re.M)
    if not m:  # pragma: no cover - the file always defines it
        raise ValueError("__version__ not found")
    return m[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="version or tag, e.g. 0.1.0 or v0.1.0")
    ap.add_argument("--check", action="store_true", help="tag must equal the package version")
    ap.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    ap.add_argument("--repo-url", default="https://github.com/crayfisher92/dora-roi-toolkit")
    args = ap.parse_args(argv)
    version = args.version.removeprefix("refs/tags/").removeprefix("v")
    if args.check and version != package_version():
        print(f"tag v{version} does not match package version {package_version()}",
              file=sys.stderr)
        return 1
    try:
        notes = section(args.changelog.read_text(encoding="utf-8"), version)
        print(absolute_links(notes, args.repo_url.rstrip("/"), f"v{version}"))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
