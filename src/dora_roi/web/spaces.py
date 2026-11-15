"""Project spaces and edit locks for the workbench's projects folder.

Layout of the projects folder (``roi serve --projects DIR``):

* **local single-user mode** – project files directly in ``DIR`` (one private space);
* **team mode** (signed-in users, ``docs/TEAM_DEPLOYMENT.md``) – ``DIR/users/<user>/`` is each
  user's private space and ``DIR/team/`` the team space every signed-in user can open.

Only one workspace edits a project file at a time: opening a project takes an **edit lock**
(:class:`ProjectLocks`); anyone else opening it gets a read-only view until the lock is
released (workspace closed or evicted) or goes stale (no activity for ``ROI_LOCK_MINUTES``,
default 30). Saving additionally checks that the file has not changed on disk since it was
read or last saved; if it has (another process, a stale lock taken over), the workspace is
saved to a new conflict copy instead of overwriting the other version.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from dora_roi.project import SUFFIX, list_projects

PRIVATE = "private"
TEAM = "team"
SPACES = (PRIVATE, TEAM)

Stamp = tuple[int, int]


def lock_timeout_seconds() -> float:
    """Inactivity after which an edit lock may be taken over (``ROI_LOCK_MINUTES``)."""
    try:
        return max(1.0, float(os.environ.get("ROI_LOCK_MINUTES", "30"))) * 60
    except ValueError:
        return 30 * 60.0


def user_folder(identity: str) -> str:
    """File-system-safe, collision-free folder name for a signed-in user."""
    slug = re.sub(r"[^a-z0-9]+", "-", identity.lower()).strip("-")[:40] or "user"
    return f"{slug}-{hashlib.sha256(identity.encode()).hexdigest()[:10]}"


def file_stamp(path: Path) -> Stamp | None:
    """Modification time and size of ``path`` (``None`` if it does not exist)."""
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def unique_path(folder: Path, stem: str) -> Path:
    """``folder/stem.roiproj``, or ``stem-2.roiproj`` … if that name is taken."""
    candidate = folder / f"{stem}{SUFFIX}"
    n = 2
    while candidate.exists():
        candidate = folder / f"{stem}-{n}{SUFFIX}"
        n += 1
    return candidate


def conflict_path(path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return unique_path(path.parent, f"{path.stem}-conflict-{stamp}")


@dataclass
class ProjectSpaces:
    """Folders of the private and team spaces under the projects folder ``root``."""

    root: Path
    team_mode: bool

    def folder(self, space: str, identity: str) -> Path | None:
        """Folder of ``space`` for the signed-in ``identity`` (created on demand)."""
        if space == PRIVATE:
            folder = self.root / "users" / user_folder(identity) if self.team_mode else self.root
        elif space == TEAM and self.team_mode:
            folder = self.root / TEAM
        else:
            return None
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def available(self) -> tuple[str, ...]:
        return SPACES if self.team_mode else (PRIVATE,)

    def resolve(self, space: str, name: str, identity: str) -> Path | None:
        """The project file ``name`` of a space – only names listed there, never paths."""
        folder = self.folder(space, identity)
        if folder is None:
            return None
        return next((p for p, _ in list_projects(folder) if p.name == name), None)


@dataclass
class Holder:
    workspace_id: str
    user: str
    since: float


class ProjectLocks:
    """In-process edit locks: at most one live workspace edits a project file.

    A lock is live while its workspace is still held in memory (``alive``) and has been
    active within the lock timeout (``last_active``); otherwise it may be taken over. The
    workbench keeps workspaces in memory, so it runs as a single process – the on-disk change
    check in the app protects against anything outside it.
    """

    def __init__(self, alive: Callable[[str], bool], last_active: Callable[[str], float],
                 timeout: float | None = None) -> None:
        self._alive = alive
        self._last_active = last_active
        self._timeout = timeout if timeout is not None else lock_timeout_seconds()
        self._held: dict[Path, Holder] = {}
        self._lock = Lock()

    def _live(self, holder: Holder) -> bool:
        return (self._alive(holder.workspace_id)
                and time.monotonic() - self._last_active(holder.workspace_id) < self._timeout)

    def acquire(self, path: Path, workspace_id: str, user: str) -> Holder | None:
        """Take the lock for ``workspace_id``; return the other live holder if there is one."""
        key = path.resolve()
        with self._lock:
            holder = self._held.get(key)
            if holder and holder.workspace_id != workspace_id and self._live(holder):
                return holder
            self._held[key] = Holder(workspace_id, user, time.monotonic())
            return None

    def holder(self, path: Path) -> Holder | None:
        """The live holder of ``path``'s lock, if any."""
        with self._lock:
            holder = self._held.get(path.resolve())
            return holder if holder and self._live(holder) else None

    def holds(self, path: Path, workspace_id: str) -> bool:
        with self._lock:
            holder = self._held.get(path.resolve())
            return holder is not None and holder.workspace_id == workspace_id

    def release(self, path: Path, workspace_id: str) -> None:
        key = path.resolve()
        with self._lock:
            holder = self._held.get(key)
            if holder and holder.workspace_id == workspace_id:
                del self._held[key]
