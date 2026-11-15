#!/usr/bin/env sh
# Regenerate the hash-pinned dependency locks in requirements/ from pyproject.toml.
#
#   runtime.txt – core + web + pdf extras (Docker image, pip-audit)
#   dev.txt     – everything for development and CI (tests, linters, Playwright)
#
# Universal locks: valid for every supported Python version (3.11+) and platform. uv keeps
# the versions already pinned unless pyproject.toml requires otherwise; to upgrade
# deliberately, run with --upgrade (all) or --upgrade-package NAME. CI fails if the files are
# out of date. Needs uv (https://docs.astral.sh/uv/); CI pins the version in ci.yml.
set -eu
cd "$(dirname "$0")/.."
common="--universal --python-version 3.11 --generate-hashes --quiet"
# shellcheck disable=SC2086  # word splitting of $common and "$@" is intended
uv pip compile pyproject.toml --extra web --extra pdf $common "$@" -o requirements/runtime.txt
# shellcheck disable=SC2086
uv pip compile pyproject.toml --extra dev $common "$@" -o requirements/dev.txt
