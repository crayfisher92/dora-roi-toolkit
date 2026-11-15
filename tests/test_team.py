"""Team use of the workbench: sign-in proxy, project spaces, edit locks, limits (Phase 3)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import anyio
import httpx
import pytest
from click.testing import CliRunner
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from dora_roi.cli import main
from dora_roi.project import load_project
from dora_roi.web import app as web_app
from dora_roi.web.app import MAX_REQUEST_BYTES, LRUStore, create_app
from dora_roi.web.auth import AuthConfig, clean_identity, parse_networks
from dora_roi.web.security import BodySizeLimitMiddleware
from dora_roi.web.spaces import ProjectLocks, user_folder

HEADER = "X-Forwarded-Email"
PROXY = ("127.0.0.1", 50000)
CELL = {"template": "B_02.01", "row": "4", "column": "c0050"}


def team_app(tmp_path: Path | None = None) -> object:
    return create_app(projects_dir=tmp_path, auth=AuthConfig(HEADER))


def as_user(app: object, email: str) -> TestClient:
    return TestClient(app, client=PROXY, headers={HEADER: email})  # type: ignore[arg-type]


def new_sample(client: TestClient) -> str:
    r = client.post("/sample", data={"variant": "clean"}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return str(r.headers["location"])


# ------------------------------------------------------------------ identity


def test_identity_comes_only_from_the_trusted_proxy() -> None:
    app = team_app()
    assert as_user(app, "anna@example.com").get("/").status_code == 200
    anonymous = TestClient(app, client=PROXY)  # type: ignore[arg-type]
    assert anonymous.get("/").status_code == 401
    assert anonymous.get("/api/health").status_code == 200  # container probe stays open
    direct = TestClient(app, client=("10.1.2.3", 4000),  # type: ignore[arg-type]
                        headers={HEADER: "mallory@example.com"})
    assert direct.get("/").status_code == 403  # header from an untrusted address


def test_config_parsing() -> None:
    cfg = AuthConfig(HEADER, parse_networks("10.0.0.5, 172.28.0.0/24"))
    assert cfg.enabled and cfg.is_trusted("172.28.0.10") and cfg.is_trusted("10.0.0.5")
    assert not cfg.is_trusted("10.0.0.6") and not cfg.is_trusted("testclient")
    assert not AuthConfig().enabled
    assert clean_identity("  Anna@Example.COM\n") == "anna@example.com"
    assert clean_identity("x" * 300) == ""
    with pytest.raises(ValueError):
        parse_networks("not-an-ip")


def test_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROI_AUTH_HEADER", "X-Forwarded-User")
    monkeypatch.setenv("ROI_TRUSTED_PROXIES", "172.28.0.10")
    cfg = AuthConfig.from_env()
    assert cfg.header == "X-Forwarded-User" and cfg.is_trusted("172.28.0.10")
    assert not cfg.is_trusted("127.0.0.1")


def test_workspaces_follow_the_user_not_the_browser() -> None:
    app = team_app()
    anna = as_user(app, "anna@example.com")
    url = new_sample(anna)
    page = anna.get(url).text
    assert "Signed in as anna@example.com" in page and 'action="/user"' not in page
    assert as_user(app, "ANNA@example.com").get(url).status_code == 200  # other browser
    assert as_user(app, "bob@example.com").get(url).status_code == 404
    assert anna.post("/user", data={"name": "Someone else"}).status_code == 404
    anna.post(url + "/cell", data={**CELL, "value": "123"})
    assert "anna@example.com" in anna.get(url + "/audit").text


# ------------------------------------------------------------------ spaces and locks


def test_private_and_team_spaces(tmp_path: Path) -> None:
    app = team_app(tmp_path)
    anna, bob = as_user(app, "anna@example.com"), as_user(app, "bob@example.com")
    url = new_sample(anna)
    private = tmp_path / "users" / user_folder("anna@example.com")
    files = list(private.glob("*.roiproj"))
    assert len(files) == 1
    assert files[0].name not in bob.get("/").text  # private space is private
    assert files[0].name in anna.get("/").text
    assert "Move to team space" in anna.get(url).text
    assert anna.post(url + "/share", follow_redirects=False).status_code == 303
    shared = list((tmp_path / "team").glob("*.roiproj"))
    assert len(shared) == 1 and not list(private.glob("*.roiproj"))
    assert "Moved to the team space" in anna.get(url).text
    home = bob.get("/").text
    assert shared[0].name in home and "Being edited by anna@example.com" in home
    # bob only gets a read-only view while anna edits
    r = bob.post("/projects/open", data={"space": "team", "file": shared[0].name},
                 follow_redirects=False)
    view = r.headers["location"]
    assert "anna@example.com is editing this project" in bob.get(view).text
    assert bob.post(view + "/cell", data={**CELL, "value": "1"}).status_code == 403
    anna.post(url + "/cell", data={**CELL, "value": "555"})
    assert load_project(shared[0]).row("B_02.01", 4).values["c0050"] == "555"
    # anna closes it; now bob edits and anna would be read-only
    assert anna.post(url + "/close", follow_redirects=False).status_code == 303
    r = bob.post("/projects/open", data={"space": "team", "file": shared[0].name},
                 follow_redirects=False)
    bob_url = r.headers["location"]
    bob.post(bob_url + "/cell", data={**CELL, "value": "666"})
    assert load_project(shared[0]).row("B_02.01", 4).values["c0050"] == "666"
    assert "666" in str(load_project(shared[0]).changes[-1].new)
    r = anna.post("/projects/open", data={"space": "team", "file": shared[0].name},
                  follow_redirects=False)
    assert "bob@example.com is editing" in anna.get(r.headers["location"]).text
    # opening it again while editing goes back to the same workspace
    again = bob.post("/projects/open", data={"space": "team", "file": shared[0].name},
                     follow_redirects=False)
    assert again.headers["location"] == bob_url
    # names outside the spaces are refused
    assert bob.post("/projects/open", data={"space": "team", "file": "../x.roiproj"}
                    ).status_code == 404
    assert bob.post("/projects/open", data={"space": "other", "file": shared[0].name}
                    ).status_code == 404


def test_changed_file_is_never_overwritten(tmp_path: Path) -> None:
    app = team_app(tmp_path)
    anna = as_user(app, "anna@example.com")
    url = new_sample(anna)
    path = next((tmp_path / "users").rglob("*.roiproj"))
    before = path.read_bytes()
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))  # changed elsewhere
    anna.post(url + "/cell", data={**CELL, "value": "999"})
    assert path.read_bytes() == before  # the other version is kept
    conflict = [p for p in path.parent.glob("*.roiproj") if "-conflict-" in p.name]
    assert len(conflict) == 1
    assert load_project(conflict[0]).row("B_02.01", 4).values["c0050"] == "999"
    assert "was saved as" in anna.get(url).text


def test_idle_lock_can_be_taken_over(tmp_path: Path) -> None:
    app = team_app(tmp_path)
    anna, bob = as_user(app, "anna@example.com"), as_user(app, "bob@example.com")
    url = new_sample(anna)
    anna.post(url + "/share")
    name = next((tmp_path / "team").glob("*.roiproj")).name
    ws = app.state.workspaces.peek(url.rsplit("/", 1)[-1])  # type: ignore[attr-defined]
    ws.last_active = time.monotonic() - 24 * 3600  # anna went home
    r = bob.post("/projects/open", data={"space": "team", "file": name}, follow_redirects=False)
    bob_url = r.headers["location"]
    assert bob.post(bob_url + "/cell", data={**CELL, "value": "1"},
                    follow_redirects=False).status_code == 303
    assert anna.post(url + "/cell", data={**CELL, "value": "2"}).status_code == 403
    assert "lock expired" in anna.get(url).text


def test_project_locks_unit() -> None:
    alive = {"a": True, "b": True}
    active = {"a": time.monotonic(), "b": time.monotonic()}
    locks = ProjectLocks(alive=lambda w: alive.get(w, False), last_active=active.__getitem__,
                         timeout=60)
    p = Path("project.roiproj")
    assert locks.acquire(p, "a", "Anna") is None
    holder = locks.acquire(p, "b", "Bob")
    assert holder is not None and holder.user == "Anna" and locks.holds(p, "a")
    alive["a"] = False  # evicted from memory
    assert locks.acquire(p, "b", "Bob") is None and locks.holder(p).user == "Bob"  # type: ignore[union-attr]
    active["b"] -= 120  # idle beyond the timeout
    assert locks.holder(p) is None
    locks.release(p, "a")  # not the holder: no effect
    assert locks.holds(p, "b")
    locks.release(p, "b")
    assert not locks.holds(p, "b")


def test_local_mode_keeps_one_private_folder(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_dir=tmp_path, auth=AuthConfig()))
    url = new_sample(client)
    assert len(list(tmp_path.glob("*.roiproj"))) == 1 and not (tmp_path / "team").exists()
    page = client.get(url).text
    assert 'action="/user"' in page and "Move to team space" not in page
    assert client.post(url + "/share").status_code == 404


# ------------------------------------------------------------------ memory, size, event loop


def test_store_limits_each_owner_separately() -> None:
    evicted: list[str] = []
    store: LRUStore[tuple[str, str, int]] = LRUStore(
        10, owner=lambda v: v[0], owner_capacity=2, owner_weight=100, weight=lambda v: v[2],
        on_evict=lambda v: evicted.append(v[1]))
    store.add("b1", ("bob", "b1", 10))
    store.add("a1", ("anna", "a1", 10))
    store.add("a2", ("anna", "a2", 10))
    store.add("a3", ("anna", "a3", 10))  # anna over her count: her oldest goes, not bob's
    assert evicted == ["a1"] and store.contains("b1")
    store.add("a4", ("anna", "a4", 95))  # anna over her rows: her other workspaces go
    assert evicted == ["a1", "a2", "a3"] and store.contains("a4") and store.contains("b1")
    assert store.remove("b1") is not None and store.peek("b1") is None


def test_body_size_limit() -> None:
    async def echo(request: Request) -> PlainTextResponse:
        return PlainTextResponse(str(len(await request.body())))

    small = BodySizeLimitMiddleware(Starlette(routes=[Route("/", echo, methods=["POST"])]),
                                    max_bytes=100)
    client = TestClient(small)
    assert client.post("/", content=b"x" * 100).text == "100"
    assert client.post("/", content=b"x" * 101).status_code == 413  # declared length

    def chunks():  # type: ignore[no-untyped-def]
        for _ in range(10):
            yield b"x" * 20

    assert client.post("/", content=chunks()).status_code == 413  # counted while streaming
    app = create_app(auth=AuthConfig())
    assert any(m.cls is BodySizeLimitMiddleware for m in app.user_middleware)
    assert MAX_REQUEST_BYTES > web_app.MAX_UPLOAD_BYTES


def test_slow_import_does_not_block_other_requests(monkeypatch: pytest.MonkeyPatch,
                                                   tmp_path: Path) -> None:
    started = threading.Event()

    def slow_load(path: object) -> object:
        started.set()
        time.sleep(1.5)
        raise ValueError("slow and broken")

    monkeypatch.setattr(web_app, "load_raw", slow_load)
    app = create_app(auth=AuthConfig())
    timings: dict[str, float] = {}

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            async def upload() -> None:
                await client.post("/import", files={"file": ("a.xlsx", b"PK", "x/y")})
                timings["import"] = time.monotonic()

            async def health() -> None:
                while not started.is_set():
                    await anyio.sleep(0.01)
                await client.get("/api/health")
                timings["health"] = time.monotonic()

            async with anyio.create_task_group() as tg:
                tg.start_soon(upload)
                tg.start_soon(health)

    anyio.run(run)
    assert timings["health"] < timings["import"] - 0.5


def test_cli_serve_team_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    calls: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    res = CliRunner().invoke(main, ["serve", "--auth-header", HEADER,
                                    "--trusted-proxy", "172.28.0.10"])
    assert res.exit_code == 0, res.output
    app, kw = calls[-1]
    assert kw["proxy_headers"] is False and "Team mode" in res.output
    auth = app.state.auth  # type: ignore[attr-defined]
    assert auth.header == HEADER and auth.is_trusted("172.28.0.10")
    bad = CliRunner().invoke(main, ["serve", "--trusted-proxy", "nope"])
    assert bad.exit_code != 0
