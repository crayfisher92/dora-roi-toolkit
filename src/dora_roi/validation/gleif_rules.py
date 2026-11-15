"""Rules of the optional online LEI check (findings produced by :mod:`dora_roi.gleif`).

Declared here so that the rule catalogue is the same whether or not the online check is used.
"""

from __future__ import annotations

from dora_roi.validation.findings import Category, Severity, declare

TEMPLATES = ("B_01.01", "B_01.02", "B_05.01")
REFERENCES = ("ISO 17442", "GLEIF Global LEI Index (reference data)")

declare("GLEIF-001", "LEI not found in the Global LEI Index", severity=Severity.WARNING,
        category=Category.FIELD, templates=TEMPLATES, references=REFERENCES,
        description="Online check (opt-in): the LEI has valid check digits but no record in "
        "the GLEIF Global LEI Index – it may be mistyped or never have been issued.")
declare("GLEIF-002", "LEI not in good standing", severity=Severity.WARNING,
        category=Category.FIELD, templates=TEMPLATES, references=REFERENCES,
        description="Online check (opt-in): the LEI registration is lapsed, retired, annulled, "
        "a duplicate or otherwise not issued, or the legal entity is inactive (e.g. merged); "
        "renew the LEI or report the successor entity's LEI.")
declare("GLEIF-003", "Name differs from the GLEIF record", severity=Severity.INFO,
        category=Category.FIELD, templates=TEMPLATES, references=REFERENCES,
        description="Online check (opt-in): the name in the register matches neither the GLEIF "
        "legal name nor any of its other names (comparison ignores case, accents and "
        "punctuation).")
declare("GLEIF-004", "Country differs from the GLEIF record", severity=Severity.INFO,
        category=Category.FIELD, templates=TEMPLATES, references=REFERENCES,
        description="Online check (opt-in): the country of an entity differs from its GLEIF "
        "legal address, or the headquarters country of a provider from its GLEIF "
        "headquarters address.")
