"""Regulatory reference labels used by the rules and the regulatory mapping document.

Article-level references to DORA are to Regulation (EU) 2022/2554. References to the ITS are
to the implementing technical standards on the register of information templates (Commission
Implementing Regulation (EU) 2024/2956) and are given at annex/template/column level, which
is how the ITS is structured. See ``docs/ASSUMPTIONS.md`` (A-REG-*) for caveats.
"""

from __future__ import annotations

DORA = "Regulation (EU) 2022/2554 (DORA)"
ITS = "Commission Implementing Regulation (EU) 2024/2956 (ITS on RoI templates)"

#: Short reference → explanation, rendered in ``docs/REGULATORY_MAPPING.md``.
REFERENCES: dict[str, str] = {
    "DORA Art. 3(22)": "Definition of 'critical or important function'.",
    "DORA Art. 28(1)": "ICT third-party risk managed as an integral component of ICT risk.",
    "DORA Art. 28(3)": (
        "Maintain and update a register of information on all contractual arrangements on the "
        "use of ICT services provided by ICT third-party service providers, at entity, "
        "sub-consolidated and consolidated level, distinguishing arrangements covering "
        "critical or important functions; report it to the competent authority on request."
    ),
    "DORA Art. 28(4)": "Pre-contractual assessment, including whether the arrangement "
    "covers a critical or important function.",
    "DORA Art. 28(6)": "Frequency of audits and inspections determined on a risk basis.",
    "DORA Art. 28(7)": "Termination rights of the financial entity.",
    "DORA Art. 28(8)": "Exit strategies for ICT services supporting critical or important "
    "functions.",
    "DORA Art. 28(9)": "Mandate for ITS establishing standard templates for the register.",
    "DORA Art. 29": "Preliminary assessment of ICT concentration risk at entity level, "
    "including substitutability and subcontracting chains.",
    "DORA Art. 30(2)": "Key contractual provisions, incl. description of services, "
    "subcontracting conditions and locations of service provision and data processing.",
    "DORA Art. 30(3)": "Additional provisions for critical or important functions, incl. "
    "notice periods and exit strategies.",
    "DORA Art. 31": "Designation of critical ICT third-party service providers (CTPPs), which "
    "relies on register data.",
    "ITS Annex I": "Templates of the register of information (B_01.01 – B_07.01).",
    "ITS Annex II": "Instructions for completing the templates.",
    "ITS Annex III": "Taxonomy of ICT service types.",
    "ITS Art. – identification": "Entities identified by LEI; providers by LEI or EUID.",
    "ITS Art. – consistency": "Information across templates must be consistent and linked "
    "through the contractual arrangement reference number and identification codes.",
    "ISO 17442": "Legal Entity Identifier format and MOD 97-10 check digits.",
    "ISO 3166-1": "Country codes (alpha-2).",
    "ISO 4217": "Currency codes.",
    "ISO 8601": "Date format YYYY-MM-DD.",
    "EBA reporting": "EBA reporting framework / xBRL-CSV technical requirements (filing "
    "rules for DORA RoI).",
}
