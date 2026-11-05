"""Attach the sample DORA programme data (contract assessments, …) to a sample workspace."""

from __future__ import annotations

from dora_roi.sample.assessments import sample_assessments
from dora_roi.workspace import Workspace


def load_sample_programme(ws: Workspace) -> None:
    """Fill ``ws`` with the Alpenrand sample assessments."""
    ws.contracts = sample_assessments(ws.register)
