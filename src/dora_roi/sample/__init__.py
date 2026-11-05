"""Synthetic sample data (fictional Swiss/EU banking group 'Alpenrand')."""

from dora_roi.sample.generator import (
    DEFAULT_REFERENCE_DATE,
    DEFAULT_SEED,
    InjectedError,
    SampleResult,
    generate_sample,
    register_to_raw,
    synthetic_lei,
)

__all__ = [
    "DEFAULT_REFERENCE_DATE",
    "DEFAULT_SEED",
    "InjectedError",
    "SampleResult",
    "generate_sample",
    "register_to_raw",
    "synthetic_lei",
]
