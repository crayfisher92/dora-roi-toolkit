"""State that only the web workbench needs about a workspace (owner, project file, lock)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WebSession:
    """Who owns a workspace in the web app and how it is stored – kept apart from the
    register itself, which the CLI and library use without any of this."""

    #: Signed-in user (``user:<e-mail>``) or browser session that owns the workspace.
    owner: str = ""
    #: Name of the owner as shown to others (e.g. who holds a project's edit lock).
    owner_label: str = ""
    #: Where the workspace is autosaved, if anywhere.
    project_path: Path | None = None
    #: Modification time and size of ``project_path`` when last read or written.
    project_stamp: tuple[int, int] | None = None
    #: Project space (``private`` or ``team``).
    space: str = "private"
    #: Set when someone else holds the edit lock: every change is refused.
    read_only: str | None = None
    #: Messages for the user, as ``(i18n key, parameters)``.
    notices: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    #: ``time.monotonic()`` of the last request (edit locks expire after inactivity).
    last_active: float = field(default_factory=time.monotonic)
    #: Workflow steps the user has opened (for the stepper).
    visited: set[str] = field(default_factory=set)
