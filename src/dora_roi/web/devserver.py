"""Run the web app in a background thread (end-to-end tests and screenshot generation)."""

from __future__ import annotations

import socket
import threading
import time
from types import TracebackType

import uvicorn

from dora_roi.web.app import create_app


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


class BackgroundServer:
    """``with BackgroundServer() as url: ...`` serves a fresh app instance on localhost."""

    def __init__(self, port: int | None = None) -> None:
        self.port = port or free_port()
        config = uvicorn.Config(create_app(), host="127.0.0.1", port=self.port,
                                log_level="warning", lifespan="off")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> str:
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if time.monotonic() > deadline:  # pragma: no cover - defensive
                raise RuntimeError("web server did not start")
            time.sleep(0.05)
        return self.url

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
