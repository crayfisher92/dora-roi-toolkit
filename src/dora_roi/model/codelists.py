"""Closed code lists used by the RoI templates.

Each code list is a :class:`CodeEnum`: a ``StrEnum`` whose *value* is the toolkit's stable
internal code and which also carries a human-readable ``label`` (taken from, or paraphrasing,
the ITS wording). Importers accept the code, the label or any registered alias,
case-insensitively, so that both "S19" and "Cloud services: SaaS" load correctly.

The official EBA taxonomy identifies enumerated values with qualified names (e.g.
``eba_CT:x12`` for a credit institution). Every member of every code list below has its
taxonomy member in :data:`dora_roi.model.eba_codes.CODE_MAP`, taken from the EBA *List of
possible values for all data fields with drop downs* (reporting framework 4.0); the code lists
and labels were reconciled against it and the *Annotated Table Layout DORA 4.0*.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Self


def _norm(text: str) -> str:
    text = text.strip().casefold()
    # Strip taxonomy prefixes such as "eba_CT:" so that xBRL-CSV values round-trip.
    text = re.sub(r"^eba_[a-z0-9]+:", "", text)
    return re.sub(r"[\s_\-]+", " ", text)


_LOOKUP_CACHE: dict[type, dict[str, object]] = {}
#: exact input text → member, filled on successful lookups (inputs repeat a lot)
_RAW_CACHE: dict[type, dict[str, object]] = {}
_RAW_CACHE_MAX = 10_000


class CodeEnum(StrEnum):
    """String enum with a human label and lookup by code, label or alias."""

    label: str

    def __new__(cls, value: str, label: str = "") -> Self:
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label = label or value
        return obj

    @classmethod
    def aliases(cls) -> dict[str, str]:
        """Extra accepted spellings → internal code. Override in subclasses."""
        return {}

    @classmethod
    def lookup(cls, raw: str) -> Self | None:
        """Resolve ``raw`` (code, label or alias, any case) to a member, or ``None``."""
        memo = _RAW_CACHE.setdefault(cls, {})
        hit = memo.get(raw)
        if hit is not None:
            return hit  # type: ignore[return-value]
        table = _LOOKUP_CACHE.get(cls)
        if table is None:
            table = {}
            for k, v in cls.aliases().items():
                table[_norm(k)] = cls(v)
            for member in cls:
                table[_norm(member.label)] = member
                table[_norm(member.value)] = member
            _LOOKUP_CACHE[cls] = table
        found = table.get(_norm(raw))
        if not isinstance(found, cls):
            return None
        if len(memo) < _RAW_CACHE_MAX:
            memo[raw] = found
        return found

    @classmethod
    def describe(cls) -> str:
        """Compact ``code = label`` description for templates and docs."""
        return "; ".join(f"{m.value} = {m.label}" for m in cls)


class EntityType(CodeEnum):
    """Type of entity (B_01.01 / B_01.02 c0040; DPM hierarchies CT6 and CT61).

    The 22 financial-entity types follow DORA Art. 2(1) as listed by the EBA; the last two
    values are the non-financial group entities that may only appear in B_01.02.
    """

    CREDIT_INSTITUTION = "CREDIT_INSTITUTION", "Credit institution"
    PAYMENT_INSTITUTION = "PAYMENT_INSTITUTION", "Payment institution"
    ACCOUNT_INFORMATION_SP = "ACCOUNT_INFORMATION_SP", "Account information service provider"
    E_MONEY_INSTITUTION = "E_MONEY_INSTITUTION", "Electronic money institution"
    INVESTMENT_FIRM = "INVESTMENT_FIRM", "Investment firm"
    CASP = "CASP", "Crypto-asset service provider"
    ART_ISSUER = "ART_ISSUER", "Issuer of asset-referenced tokens"
    CSD = "CSD", "Central securities depository"
    CCP = "CCP", "Central counterparty"
    TRADING_VENUE = "TRADING_VENUE", "Trading venue"
    TRADE_REPOSITORY = "TRADE_REPOSITORY", "Trade repository"
    AIFM = "AIFM", "Manager of alternative investment funds"
    UCITS_MANCO = "UCITS_MANCO", "Management company (UCITS)"
    DRSP = "DRSP", "Data reporting service provider"
    INSURANCE_UNDERTAKING = "INSURANCE_UNDERTAKING", "Insurance and reinsurance undertaking"
    INSURANCE_INTERMEDIARY = "INSURANCE_INTERMEDIARY", (
        "Insurance, reinsurance or ancillary insurance intermediary")
    IORP = "IORP", "Institution for occupational retirement provision"
    CRA = "CRA", "Credit rating agency"
    BENCHMARK_ADMINISTRATOR = "BENCHMARK_ADMINISTRATOR", "Administrator of critical benchmarks"
    CROWDFUNDING_SP = "CROWDFUNDING_SP", "Crowdfunding service provider"
    SECURITISATION_REPOSITORY = "SECURITISATION_REPOSITORY", "Securitisation repository"
    OTHER_FINANCIAL = "OTHER_FINANCIAL", "Other financial entity"
    NON_FINANCIAL_ICT_INTRAGROUP = "NON_FINANCIAL_ICT_INTRAGROUP", (
        "Non-financial entity: ICT intra-group service provider")
    OTHER = "OTHER", "Non-financial entity: other than ICT intra-group service provider"

    @property
    def is_financial(self) -> bool:
        """False for the two non-financial values (only allowed in B_01.02)."""
        return self not in (EntityType.NON_FINANCIAL_ICT_INTRAGROUP, EntityType.OTHER)

    @classmethod
    def aliases(cls) -> dict[str, str]:
        return {
            "bank": "CREDIT_INSTITUTION",
            "CI": "CREDIT_INSTITUTION",
            "IF": "INVESTMENT_FIRM",
            # labels used by the EBA list of possible values
            "credit institutions": "CREDIT_INSTITUTION",
            "investment firms": "INVESTMENT_FIRM",
            "asset management companies": "UCITS_MANCO",
            "management companies": "UCITS_MANCO",
            "central security depository": "CSD",
            "central counterparties (CCPs)": "CCP",
            "insurance and reinsurance undertakings": "INSURANCE_UNDERTAKING",
            # earlier toolkit versions split insurance and reinsurance undertakings
            "REINSURANCE_UNDERTAKING": "INSURANCE_UNDERTAKING",
            "reinsurance undertaking": "INSURANCE_UNDERTAKING",
        }


class HierarchyInGroup(CodeEnum):
    """Hierarchy of the entity within the group (B_01.02 c0050; DPM hierarchy RP8)."""

    ULTIMATE_PARENT = "ULTIMATE_PARENT", "Ultimate parent"
    PARENT = "PARENT", "Parent other than ultimate parent"
    SUBSIDIARY = "SUBSIDIARY", "Subsidiary"
    NOT_IN_GROUP = "NOT_IN_GROUP", "Entities other than entities of the group"
    OUTSOURCING = "OUTSOURCING", (
        "Service provider to which the financial entity outsources all its operational "
        "activities")

    @classmethod
    def aliases(cls) -> dict[str, str]:
        # "OTHER" was this toolkit's earlier (incorrect) code for the outsourcing option
        return {"OTHER": "OUTSOURCING", "outsourcing": "OUTSOURCING"}


class ContractType(CodeEnum):
    """Type of contractual arrangement (B_02.01 c0020)."""

    STANDALONE = "STANDALONE", "Standalone arrangement"
    OVERARCHING = "OVERARCHING", "Overarching / master arrangement"
    SUBSEQUENT = "SUBSEQUENT", "Subsequent or associated arrangement"

    @classmethod
    def aliases(cls) -> dict[str, str]:
        return {"master": "OVERARCHING", "associated": "SUBSEQUENT", "call-off": "SUBSEQUENT"}


_CODE_TYPE_ALIASES = {
    "legal entity identifier": "LEI",
    "legal entity identfier (LEI)": "LEI",  # sic, EBA list of possible values
    "european unified id (EUID)": "EUID",
    "national code": "NIN",
    "company registration number (CRN)": "CRN",
    "value added tax identification number (VAT)": "VAT",
    "passport number": "PNR",
}


class ProviderCodeType(CodeEnum):
    """Type of code identifying a provider (DPM hierarchy qCO:new_CO2).

    LEI or EUID for legal persons; the other codes for providers without either, e.g. natural
    persons acting in a business capacity (EBA FAQ on RoI reporting).
    """

    LEI = "LEI", "Legal Entity Identifier (LEI)"
    EUID = "EUID", "European Unique Identifier (EUID)"
    CRN = "CRN", "Company registration number"
    VAT = "VAT", "Value added tax identification number"
    PNR = "PNR", "Passport number"
    NIN = "NIN", "National identity number (national code)"

    @classmethod
    def aliases(cls) -> dict[str, str]:
        return _CODE_TYPE_ALIASES


class AdditionalCodeType(CodeEnum):
    """Type of additional identification code for a provider (B_05.01 c0040; qCO:new_CO2)."""

    LEI = "LEI", "Legal Entity Identifier (LEI)"
    EUID = "EUID", "European Unique Identifier (EUID)"
    CRN = "CRN", "Company registration number"
    VAT = "VAT", "Value added tax identification number"
    PNR = "PNR", "Passport number"
    NIN = "NIN", "National identity number (national code)"

    @classmethod
    def aliases(cls) -> dict[str, str]:
        return _CODE_TYPE_ALIASES


class PersonType(CodeEnum):
    """Type of person of the ICT third-party service provider (B_05.01 c0070)."""

    LEGAL = "LEGAL", "Legal person"
    NATURAL = "NATURAL", "Natural person (individual acting in a business capacity)"


class IctServiceType(CodeEnum):
    """Taxonomy of ICT services (ITS Annex III, as understood by this toolkit)."""

    S01 = "S01", "ICT project management"
    S02 = "S02", "ICT development"
    S03 = "S03", "ICT help desk and first level support"
    S04 = "S04", "ICT security management services"
    S05 = "S05", "Provision of data"
    S06 = "S06", "Data analysis"
    S07 = "S07", "ICT facilities hosting (excluding cloud services)"
    S08 = "S08", "Computation"
    S09 = "S09", "Non-cloud data storage"
    S10 = "S10", "Telecom carrier"
    S11 = "S11", "Network infrastructure"
    S12 = "S12", "Hardware and physical devices"
    S13 = "S13", "Software licencing (excluding SaaS)"
    S14 = "S14", "ICT operation management (including maintenance)"
    S15 = "S15", "ICT consulting"
    S16 = "S16", "ICT risk management"
    S17 = "S17", "Cloud services: IaaS"
    S18 = "S18", "Cloud services: PaaS"
    S19 = "S19", "Cloud services: SaaS"

    @property
    def is_cloud(self) -> bool:
        return self in (IctServiceType.S17, IctServiceType.S18, IctServiceType.S19)

    @classmethod
    def aliases(cls) -> dict[str, str]:
        return {"IaaS": "S17", "PaaS": "S18", "SaaS": "S19"}


class TerminationReason(CodeEnum):
    """Reason of the termination or ending of the contractual arrangement (B_02.02 c0090)."""

    EXPIRED = "EXPIRED", "Contract expired and was not renewed"
    BREACH_OF_LAW = "BREACH_OF_LAW", "Termination for cause: provider in breach of law or contract"
    PERFORMANCE = "PERFORMANCE", "Termination for cause: impediments altering service performance"
    DATA_SECURITY = "DATA_SECURITY", "Termination for cause: weaknesses in data security / risk"
    AUTHORITY_REQUEST = "AUTHORITY_REQUEST", "Termination at the request of a competent authority"
    OTHER = "OTHER", "Other reason"


class DataSensitivity(CodeEnum):
    """Sensitiveness of the data stored by the provider (B_02.02 c0170)."""

    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"


class RelianceLevel(CodeEnum):
    """Level of reliance on the ICT service (B_02.02 c0180)."""

    NOT_SIGNIFICANT = "NOT_SIGNIFICANT", "Not significant"
    LOW = "LOW", "Low reliance"
    MATERIAL = "MATERIAL", "Material reliance"
    FULL = "FULL", "Full reliance"


class Criticality(CodeEnum):
    """Criticality or importance assessment of a function (B_06.01 c0050)."""

    CRITICAL = "CRITICAL", "Critical or important function"
    NOT_CRITICAL = "NOT_CRITICAL", "Not critical or important"
    NOT_ASSESSED = "NOT_ASSESSED", "Assessment not performed"

    @classmethod
    def aliases(cls) -> dict[str, str]:
        return {
            "yes": "CRITICAL",
            "y": "CRITICAL",
            "true": "CRITICAL",
            "CIF": "CRITICAL",
            "critical or important": "CRITICAL",
            "no": "NOT_CRITICAL",
            "n": "NOT_CRITICAL",
            "false": "NOT_CRITICAL",
        }


class Impact(CodeEnum):
    """Impact of discontinuing a function or ICT service (B_06.01 c0100, B_07.01 c0100)."""

    LOW = "LOW", "Low impact"
    MEDIUM = "MEDIUM", "Medium impact"
    HIGH = "HIGH", "High impact"
    NOT_ASSESSED = "NOT_ASSESSED", "Assessment not performed"


class Substitutability(CodeEnum):
    """Substitutability of the ICT third-party service provider (B_07.01 c0050)."""

    NOT_SUBSTITUTABLE = "NOT_SUBSTITUTABLE", "Not substitutable"
    HIGHLY_COMPLEX = "HIGHLY_COMPLEX", "Highly complex substitutability"
    MEDIUM = "MEDIUM", "Medium complexity in terms of substitutability"
    EASY = "EASY", "Easily substitutable"

    @property
    def is_hard(self) -> bool:
        return self in (Substitutability.NOT_SUBSTITUTABLE, Substitutability.HIGHLY_COMPLEX)


class NonSubstitutabilityReason(CodeEnum):
    """Reason the provider is (difficult to be) not substitutable (B_07.01 c0060)."""

    NO_ALTERNATIVES = "NO_ALTERNATIVES", "Lack of real alternatives"
    MIGRATION = "MIGRATION", "Difficulties in migrating or reintegrating"
    BOTH = "BOTH", "Lack of real alternatives and difficulties in migrating or reintegrating"
    NOT_APPLICABLE = "NOT_APPLICABLE", "Not applicable"


class Reintegration(CodeEnum):
    """Possibility of reintegrating the contracted ICT service (B_07.01 c0090)."""

    EASY = "EASY", "Easy"
    DIFFICULT = "DIFFICULT", "Difficult"
    HIGHLY_COMPLEX = "HIGHLY_COMPLEX", "Highly complex"


class AlternativesIdentified(CodeEnum):
    """Are alternative ICT third-party service providers identified? (B_07.01 c0110; BT13)."""

    YES = "YES", "Yes"
    NO = "NO", "No"
    NOT_ASSESSED = "NOT_ASSESSED", "Assessment not performed"

    @classmethod
    def aliases(cls) -> dict[str, str]:
        # earlier toolkit versions modelled this column as a boolean
        return {"true": "YES", "y": "YES", "1": "YES", "false": "NO", "n": "NO", "0": "NO"}


ALL_CODELISTS: tuple[type[CodeEnum], ...] = (
    EntityType,
    HierarchyInGroup,
    ContractType,
    ProviderCodeType,
    AdditionalCodeType,
    PersonType,
    IctServiceType,
    TerminationReason,
    DataSensitivity,
    RelianceLevel,
    Criticality,
    Impact,
    Substitutability,
    NonSubstitutabilityReason,
    Reintegration,
    AlternativesIdentified,
)
