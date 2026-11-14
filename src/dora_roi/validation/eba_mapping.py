"""Mapping of the toolkit's rules to the official EBA checks for the DORA register.

The official checks (``OFFICIAL_CHECKS``, generated from the EBA overview of technical checks
and validation rules in ``reference/eba``) come in three families: technical checks applied on
receipt (file, CSV and DPM technical checks), DPM validation rules (``e…_e`` existence rules and
``v…`` rules) and business checks against GLEIF/BRIS (``VR_…``). Every active official check is
either implemented by one or more toolkit rules (:data:`RULE_CHECKS`) or explained in
:data:`CHECK_NOTES` – met by the xBRL-CSV export, checked by the authority on submission, or
only partly checkable offline. ``tests/test_eba_reference.py`` enforces this.
"""

from __future__ import annotations

import re

from dora_roi.model.eba_codes import OFFICIAL_CHECKS

_EXPORT = ("Met by the xBRL-CSV export by construction; `roi check-package` compares a package "
           "with the official EBA sample")
_SUBMISSION = "Checked by the authority's reporting platform on submission"
_GLEIF = ("Partly: the toolkit checks the format and check digits offline; whether the LEI "
          "exists in GLEIF needs an online lookup")
_BRIS = ("Partly: the toolkit checks the EUID format offline; whether the EUID exists in BRIS "
         "needs an online lookup")


def _reporting_rules() -> tuple[str, ...]:
    """DPM existence and completeness rules ("… must be reported …")."""
    return tuple(code for code, (family, _, _, summary) in OFFICIAL_CHECKS.items()
                 if family == "dpm" and " must be reported" in summary)


#: Toolkit rule → official checks it implements (fully or, see :data:`CHECK_NOTES`, partly).
RULE_CHECKS: dict[str, tuple[str, ...]] = {
    "IMP-003": ("801",),
    "FLD-001": ("805", *_reporting_rules()),
    "FLD-002": ("v8826_m", "v8890_m", "v8891_m", "v8892_m", "v8893_m", "v8894_m", "v8895_m",
                "v8896_m", "v8897_m", "VR_2", "VR_12", "VR_23"),
    "FLD-003": ("320", "330"),
    "FLD-004": ("503",),
    "FLD-005": ("503",),
    "FLD-006": ("503",),
    "FLD-007": ("305", "331", "v22913_s", "v23716_s"),
    "FLD-008": ("332",),
    "FLD-010": ("806",),
    "FLD-012": ("724",),
    "FLD-013": ("v8821_m", "VR_71", "VR_72", "VR_77", "VR_78"),
    "FLD-014": ("v8803_m", "v8804_m", "v8824_m"),
    "FLD-015": ("503",),
    "XRF-001": ("807",),
    "XRF-002": ("807",),
    "XRF-003": ("807",),
    "XRF-004": ("807",),
    "XRF-011": ("807",),
    "XRF-012": ("807",),
    "XRF-013": ("807",),
    "BUS-001": ("v8816_m",),
    "BUS-007": ("v8805_m", "v22912_m"),
    "BUS-010": ("e23676_e", "v8862_m"),
    "BUS-014": ("v8823_m",),
    "BUS-020": ("v8825_m",),
}

#: Official check → how it is met outside the rules, or what the mapped rules do not cover.
CHECK_NOTES: dict[str, str] = {
    **dict.fromkeys(("101", "103", "104", "105", "106", "109", "110", "115", "306", "333",
                     "505", "510", "512", "514", "701", "702", "703", "704", "705", "714",
                     "720", "723", "802", "803", "804", "808", "809"), _EXPORT),
    **dict.fromkeys(("102", "107", "111"), _SUBMISSION),
    "801": "On import (IMP-003) and by the export, which writes only DPM column codes",
    "805": ("Key columns are mandatory (FLD-001); the export writes the ESAs' conventions "
            "('Not Applicable', eba_GA:qx2007) into empty conditional key columns"),
    "807": ("The cross-template checks XRF-001 to XRF-004 and XRF-011 to XRF-013 cover the "
            "foreign keys of the data model"),
    "e23676_e": ("Includes B_01.02 c0060: an empty parent LEI is exported as the entity's own "
                 "LEI (FAQ Q58); BUS-010 flags a missing parent where one is required"),
    "v8862_m": ("B_01.02 c0060: exported as the entity's own LEI when there is no direct "
                "parent (FAQ Q58); BUS-010 flags a missing parent where one is required"),
    "v8816_m": ("Deactivated by the EBA in March 2025; BUS-001 keeps it as an error because an "
                "end date before the start date is always a data error"),
    **dict.fromkeys(("VR_2", "VR_12", "VR_23", "VR_71", "VR_77"), _GLEIF),
    **dict.fromkeys(("VR_72", "VR_78"), _BRIS),
    "VR_16": ("Not covered: comparing the country with the GLEIF record needs an online "
              "lookup; FLD-005 checks the ISO code only"),
}


def eba_checks(rule_id: str) -> tuple[str, ...]:
    """Official checks implemented by the toolkit rule ``rule_id`` (empty if none)."""
    return RULE_CHECKS.get(rule_id, ())


def coverage() -> dict[str, tuple[tuple[str, ...], str]]:
    """``{official check: (toolkit rules, note)}`` for every official check."""
    rules: dict[str, list[str]] = {code: [] for code in OFFICIAL_CHECKS}
    for rule_id, checks in RULE_CHECKS.items():
        for check in checks:
            rules.setdefault(check, []).append(rule_id)
    return {code: (tuple(rules[code]), CHECK_NOTES.get(code, "")) for code in rules}


def sort_key(code: str) -> tuple[int, int, str]:
    """Technical checks by number, then DPM rules, then business checks."""
    family = OFFICIAL_CHECKS.get(code, ("", "", "", ""))[0]
    order = {"technical": 0, "dpm": 1, "business": 2}.get(family, 3)
    number = int(re.sub(r"\D", "", code) or 0)
    return order, number, code
