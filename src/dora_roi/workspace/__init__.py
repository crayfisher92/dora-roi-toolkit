"""Editable, versioned registers (``Workspace``) for the CLI, the library and the web app.

* :mod:`~dora_roi.workspace.core` – the workspace: raw values, editing, acceptances, versions;
* :mod:`~dora_roi.workspace.history` – audit-trail records and undoing changes;
* :mod:`~dora_roi.workspace.derived` – incremental parsing, validation, accepted findings;
* :mod:`~dora_roi.workspace.session` – web-app state (owner, project file, edit lock).
"""

from dora_roi.workspace.core import EditError, ReadOnlyError, Workspace
from dora_roi.workspace.history import (
    DEFAULT_USER,
    MAX_VERSIONS,
    Acceptance,
    Change,
    Version,
)
from dora_roi.workspace.session import WebSession

__all__ = ["DEFAULT_USER", "MAX_VERSIONS", "Acceptance", "Change", "EditError",
           "ReadOnlyError", "Version", "WebSession", "Workspace"]
