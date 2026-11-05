"""Attach the sample DORA programme data (contract assessments, incidents) to a workspace."""

from __future__ import annotations

from datetime import datetime

from dora_roi.sample.assessments import sample_assessments
from dora_roi.sample.incidents import sample_incidents
from dora_roi.workspace import Workspace


def load_sample_programme(ws: Workspace, now: datetime | None = None) -> None:
    """Fill ``ws`` with the Alpenrand sample assessments and incidents."""
    ws.replace_programme(sample_assessments(ws.register), sample_incidents(ws.register, now))
