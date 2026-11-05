# Releasing

Versions follow [Semantic Versioning](https://semver.org/); the single source of the version
is `__version__` in `src/dora_roi/__init__.py` (the package metadata reads it). Releases are
built by [`.github/workflows/release.yml`](../.github/workflows/release.yml) from a tag.

## Steps

1. On a branch, set `__version__` (e.g. `0.2.0`, or `0.2.0-rc.1` for a pre-release) and move the
   `## [Unreleased]` entries in [`CHANGELOG.md`](../CHANGELOG.md) under
   `## [0.2.0] - YYYY-MM-DD`; add the compare link at the bottom. CI's *Package* job fails if the
   changelog has no dated section for the version.
2. Merge to `main` with green CI.
3. Tag the merge commit and push the tag:

   ```bash
   git tag -a v0.2.0 -m "v0.2.0"
   ```

   ```bash
   git push origin v0.2.0
   ```

4. The workflow then
   - checks that the tag equals the package version and extracts the release notes
     (`scripts/release_notes.py --check`),
   - runs lint, type checks and the test suite,
   - builds the wheel and sdist, runs `twine check`, installs the wheel in a clean virtual
     environment and runs the CLI, and writes `SHA256SUMS`,
   - builds the Docker image, smoke-tests it read-only and unprivileged
     (`scripts/docker_smoke.sh`), then builds and pushes `linux/amd64` and `linux/arm64` images
     with SBOM and provenance attestations to `ghcr.io/crayfisher92/dora-roi-toolkit` as
     `0.2.0`, `0.2` and `latest` (pre-releases only get their exact version),
   - creates the GitHub release with the changelog notes, install instructions, the wheel, the
     sdist and the checksums.

To rebuild an existing tag without publishing (e.g. to test the workflow), run it manually
(*Actions → Release → Run workflow*) with `publish` unchecked.

## Not (yet) automated

- **PyPI.** Publishing is a one-step addition once a PyPI project exists: a
  `pypa/gh-action-pypi-publish` job with trusted publishing (OIDC, no API token).
- **Signing.** Images carry BuildKit provenance and an SBOM; Sigstore/cosign signatures can be
  added when consumers verify them.
