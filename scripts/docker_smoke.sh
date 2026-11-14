#!/usr/bin/env bash
# Smoke-test a built image the way it is meant to run: read-only root filesystem, no Linux
# capabilities, no privilege escalation, non-root user, published on localhost only.
#   scripts/docker_smoke.sh IMAGE[:TAG]
set -euo pipefail
image="${1:?usage: docker_smoke.sh IMAGE}"
name="roi-smoke-$$"
work="$(mktemp -d)"
cleanup() { docker logs "$name" 2>&1 | tail -20 || true; docker rm -f "$name" >/dev/null 2>&1 || true; rm -rf "$work"; }
trap cleanup EXIT

docker run -d --name "$name" -p 127.0.0.1:8000:8000 --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges:true "$image" >/dev/null
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:8000/api/health
echo
test "$(docker exec "$name" whoami)" = "roi"
docker exec "$name" roi --version

# a workspace from the sample, then downloads that exercise the main export paths
ws=$(curl -fsS -c "$work/jar" -b "$work/jar" -o /dev/null -w "%{redirect_url}" \
     -X POST -d variant=dirty http://127.0.0.1:8000/sample)
test -n "$ws"
curl -fsS -b "$work/jar" "$ws/download/xlsx" -o "$work/register.xlsx"
head -c 2 "$work/register.xlsx" | grep -q "PK"
curl -fsS -b "$work/jar" "$ws/download/executive.pdf" -o "$work/executive.pdf"
head -c 5 "$work/executive.pdf" | grep -q "%PDF-"   # PDF works on the read-only root
curl -fsS -b "$work/jar" "$ws/download/project" -o "$work/project.roiproj"
head -c 15 "$work/project.roiproj" | grep -q "SQLite format 3"
echo "smoke test passed: $image"
