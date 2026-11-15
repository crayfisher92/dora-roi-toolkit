"""Optional online LEI check against GLEIF – all tests run offline with canned responses."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from dora_roi import gleif
from dora_roi.cli import main
from dora_roi.gleif import (
    GleifClient,
    GleifError,
    LeiRecord,
    gleif_findings,
    http_get,
    parse_records,
    register_leis,
)
from dora_roi.io.excel import write_workbook
from dora_roi.lei import make_lei
from dora_roi.validation import RULES
from dora_roi.web.app import create_app

from conftest import ENTITY, PROVIDER, build_valid_register


def record_json(lei: str, name: str, *, country: str = "DE", hq: str | None = None,
                status: str = "ISSUED", entity_status: str = "ACTIVE",
                other: tuple[str, ...] = (), successor: str | None = None) -> dict[str, Any]:
    return {"type": "lei-records", "id": lei, "attributes": {
        "lei": lei,
        "entity": {"legalName": {"name": name, "language": "de"},
                   "otherNames": [{"name": n, "language": "en"} for n in other],
                   "transliteratedOtherNames": [],
                   "legalAddress": {"country": country},
                   "headquartersAddress": {"country": hq or country},
                   "status": entity_status,
                   "successorEntity": {"lei": successor, "name": None}},
        "registration": {"status": status, "nextRenewalDate": "2025-03-01T00:00:00Z"}}}


def body(*records: dict[str, Any]) -> bytes:
    return json.dumps({"data": list(records), "meta": {}}).encode()


class FakeGleif:
    """Answers lei-records queries from a fixed set of records and counts the calls."""

    def __init__(self, *records: dict[str, Any]) -> None:
        self.records = {r["id"]: r for r in records}
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        leis = query["filter[lei]"][0].split(",")
        return body(*(self.records[x] for x in leis if x in self.records))


def test_rules_are_always_registered() -> None:
    assert {"GLEIF-001", "GLEIF-002", "GLEIF-003", "GLEIF-004"} <= set(RULES)
    assert RULES["GLEIF-001"].check is None  # produced outside the engine, only when asked


def test_parse_records() -> None:
    parsed = parse_records(body(record_json(
        PROVIDER, "SaaS Vendor GmbH", hq="AT", status="LAPSED", entity_status="INACTIVE",
        other=("SaaS Vendor",), successor=ENTITY)))
    rec = parsed[PROVIDER]
    assert rec.legal_name == "SaaS Vendor GmbH" and rec.other_names == ("SaaS Vendor",)
    assert (rec.legal_country, rec.hq_country) == ("DE", "AT")
    assert rec.registration_status == "LAPSED" and not rec.in_good_standing
    assert rec.next_renewal is not None and rec.next_renewal.isoformat() == "2025-03-01"
    assert rec.successor_lei == ENTITY
    assert parse_records(b'{"data": [{"id": 1}, "x"]}') == {}
    for bad in (b"not json", b"{}", b'{"data": {}}'):
        with pytest.raises(GleifError):
            parse_records(bad)


def test_client_batches_caches_and_skips_invalid() -> None:
    leis = [make_lei(f"BATCH{i:013d}") for i in range(250)]
    fake = FakeGleif(record_json(leis[0], "First AG"))
    client = GleifClient(fake)
    out = client.lookup([*leis, "NOT-AN-LEI", leis[0].lower(), ""])
    assert len(fake.urls) == 2 and len(out) == 250  # 200 + 50, invalid ones never sent
    assert all(u.startswith(gleif.GLEIF_API + "?") for u in fake.urls)
    assert out[leis[0]] is not None and out[leis[1]] is None
    assert client.lookup(leis[:3]) == {x: out[x] for x in leis[:3]} and len(fake.urls) == 2
    stale = GleifClient(fake, ttl=gleif.timedelta(0))
    stale.lookup(leis[:1])
    stale.lookup(leis[:1])
    assert len(fake.urls) == 4  # expired cache entries are fetched again


def test_findings_on_the_register() -> None:
    reg = build_valid_register()
    provider = reg.b_05_01[0]
    assert register_leis(reg) >= {ENTITY, provider.provider_code}
    records: dict[str, LeiRecord | None] = {
        ENTITY: None,
        provider.provider_code: LeiRecord(provider.provider_code, "Other Name SE",
                                          legal_country="DE", hq_country="IE",
                                          registration_status="LAPSED",
                                          next_renewal=gleif.date(2025, 3, 1),
                                          successor_lei=ENTITY),
    }
    found = {(f.rule_id, f.template, f.column) for f in gleif_findings(reg, records)}
    assert ("GLEIF-001", "B_01.01", "c0010") in found and ("GLEIF-001", "B_01.02", "c0010") in found
    assert ("GLEIF-002", "B_05.01", "c0010") in found
    assert ("GLEIF-003", "B_05.01", "c0050") in found and ("GLEIF-004", "B_05.01", "c0080") in found
    msg = next(f.message for f in gleif_findings(reg, records) if f.rule_id == "GLEIF-002")
    assert "LAPSED" in msg and "2025-03-01" in msg and ENTITY in msg
    # other names match regardless of case, accents and punctuation; same country: no finding
    ok = {provider.provider_code: LeiRecord(provider.provider_code, "Völlig Anders AG",
                                            other_names=(f"{provider.legal_name.upper()}.",),
                                            legal_country="XX", hq_country=provider.hq_country,
                                            registration_status="ISSUED",
                                            entity_status="ACTIVE")}
    assert gleif_findings(reg, ok) == []
    assert gleif_findings(reg, {}) == []  # nothing looked up, nothing reported


def test_http_get_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(GleifError, match="HTTPS"):
        http_get("http://api.gleif.org/api/v1/lei-records")

    def refuse(*_a: object, **_k: object) -> None:
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(gleif.urllib.request, "urlopen", refuse)
    with pytest.raises(GleifError, match="not reachable"):
        http_get(gleif.GLEIF_API)

    def forbidden(*_a: object, **_k: object) -> None:
        raise urllib.error.HTTPError(gleif.GLEIF_API, 429, "Too Many Requests", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(gleif.urllib.request, "urlopen", forbidden)
    with pytest.raises(GleifError, match="HTTP 429"):
        http_get(gleif.GLEIF_API)

    class Huge:
        def __enter__(self) -> Huge:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def read(self, n: int) -> bytes:
            return b"x" * n

    monkeypatch.setattr(gleif.urllib.request, "urlopen", lambda *_a, **_k: Huge())
    with pytest.raises(GleifError, match="too large"):
        http_get(gleif.GLEIF_API)


def test_cli_validate_online(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write_workbook(build_valid_register(), tmp_path / "r.xlsx")
    runner = CliRunner()
    offline = runner.invoke(main, ["validate", str(path), "--fail-on", "never"])
    assert offline.exit_code == 0 and "GLEIF" not in offline.output
    monkeypatch.setattr(gleif, "http_get", FakeGleif())
    r = runner.invoke(main, ["validate", str(path), "--online", "--fail-on", "never"])
    assert r.exit_code == 0 and "GLEIF-001" in r.output and "LEI(s) checked" in r.output
    r = runner.invoke(main, ["validate", str(path), "--online", "--disable", "GLEIF-001"])
    assert "GLEIF-001" not in r.output

    def down(_url: str) -> bytes:
        raise GleifError("GLEIF API not reachable (test)")

    monkeypatch.setattr(gleif, "http_get", down)
    r = runner.invoke(main, ["validate", str(path), "--online"])
    assert r.exit_code == 2 and "Run without --online" in r.output


def _sample(client: TestClient) -> str:
    r = client.post("/sample", data={"variant": "clean"}, follow_redirects=False)
    return str(r.headers["location"])


def test_workbench_is_offline_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROI_GLEIF", raising=False)
    client = TestClient(create_app(capacity=4))
    url = _sample(client)
    assert "data-gleif" not in client.get(url + "/fix").text
    assert client.post(url + "/gleif").status_code == 404


def test_workbench_gleif_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROI_GLEIF", "1")
    fake = FakeGleif()
    monkeypatch.setattr(gleif, "http_get", fake)
    client = TestClient(create_app(capacity=4))
    url = _sample(client)
    page = client.get(url + "/fix")
    assert "data-gleif" in page.text and "Check LEIs with GLEIF" in page.text
    r = client.post(url + "/gleif", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/fix?gleif=done")
    done = client.get(r.headers["location"])
    assert "LEI(s) checked with GLEIF" in done.text and "not in the GLEIF Global" in done.text
    assert "Last check" in done.text and len(fake.urls) == 1
    assert "LEIs checked with GLEIF" in client.get(url + "/audit").text

    def down(_url: str) -> bytes:
        raise GleifError("GLEIF API not reachable (test)")

    client2 = TestClient(create_app(capacity=4))
    monkeypatch.setattr(client2.app.state.web.gleif, "_fetch", down)  # type: ignore[attr-defined]
    url2 = _sample(client2)
    r = client2.post(url2 + "/gleif")
    assert "GLEIF could not be reached" in r.text and "not in the GLEIF Global" not in r.text
