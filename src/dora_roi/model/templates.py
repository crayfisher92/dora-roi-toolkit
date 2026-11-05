"""Typed Pydantic models for every RoI template (B_01.01 – B_07.01).

Design notes (see ``docs/DECISIONS.md`` D-002):

* All fields are ``Optional`` at the type level. Mandatory/conditional requirements are
  declared in the :class:`~dora_roi.model.types.Col` metadata and enforced by the validation
  engine, so that an incomplete register can still be loaded and *fully* diagnosed instead
  of failing on the first missing value.
* Format checks (LEI checksum, ISO codes, ISO dates, code lists) are enforced by the field
  types and therefore by Pydantic.
* Column codes and labels follow the ITS on RoI templates as understood by this toolkit; see
  ``docs/ASSUMPTIONS.md`` for the parts that must be checked against the published text.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, ClassVar, get_args, get_origin, get_type_hints

from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

from dora_roi.model.codelists import (
    AdditionalCodeType,
    CodeEnum,
    ContractType,
    Criticality,
    DataSensitivity,
    EntityType,
    HierarchyInGroup,
    IctServiceType,
    Impact,
    NonSubstitutabilityReason,
    PersonType,
    ProviderCodeType,
    Reintegration,
    RelianceLevel,
    Substitutability,
    TerminationReason,
)
from dora_roi.model.types import (
    Amount as AmountT,
)
from dora_roi.model.types import (
    C,
    Col,
    Country,
    Currency,
    Flag,
    IsoDate,
    Kind,
    Lei,
    M,
    NonNegInt,
    O,
    PositiveInt,
    Text,
)
from dora_roi.model.types import (
    Code as CodeT,
)
from dora_roi.model.types import codelist_validator as cl

Value = str | int | float | bool | date | Decimal | None


class ColumnSpec:
    """Resolved column: Python attribute name plus its :class:`Col` metadata."""

    __slots__ = ("attr", "col")

    def __init__(self, attr: str, col: Col) -> None:
        self.attr = attr
        self.col = col

    @property
    def code(self) -> str:
        return self.col.code

    @property
    def label(self) -> str:
        return self.col.label

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ColumnSpec({self.attr!r}, {self.col.code!r})"


_COLUMNS_CACHE: dict[type[BaseModel], tuple[ColumnSpec, ...]] = {}
_TEXTUAL_ATTRS: dict[type[BaseModel], frozenset[str]] = {}

_TEXTUAL_KINDS = {Kind.TEXT, Kind.LEI, Kind.PROVIDER_CODE, Kind.COUNTRY, Kind.CURRENCY,
                  Kind.CODELIST}


class RoIRecord(BaseModel):
    """Base class of a row in an RoI template."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=False)

    TEMPLATE: ClassVar[str]
    TITLE: ClassVar[str]
    KEY: ClassVar[tuple[str, ...]]

    _row: int | None = PrivateAttr(default=None)
    _source: str | None = PrivateAttr(default=None)
    _invalid: frozenset[str] = PrivateAttr(default=frozenset())

    # ----------------------------------------------------------------- metadata

    @classmethod
    def columns(cls) -> tuple[ColumnSpec, ...]:
        """Columns of the template in ITS order."""
        cached = _COLUMNS_CACHE.get(cls)
        if cached is not None:
            return cached
        hints = get_type_hints(cls, include_extras=True)
        specs: list[ColumnSpec] = []
        for name in cls.model_fields:
            col = _find_col(hints[name])
            if col is not None:
                specs.append(ColumnSpec(name, col))
        result = tuple(specs)
        _COLUMNS_CACHE[cls] = result
        return result

    @classmethod
    def column(cls, attr: str) -> ColumnSpec:
        for spec in cls.columns():
            if spec.attr == attr:
                return spec
        raise KeyError(attr)

    @classmethod
    def column_by_code(cls, code: str) -> ColumnSpec | None:
        for spec in cls.columns():
            if spec.code == code:
                return spec
        return None

    # ----------------------------------------------------------------- provenance

    @property
    def row(self) -> int | None:
        """Source row number (1-based, as shown in Excel/CSV) if known."""
        # direct dict access: pydantic's private-attribute __getattr__ is ~10x slower and
        # these properties are read hundreds of thousands of times by the rule engine
        return self.__pydantic_private__["_row"]  # type: ignore[index, no-any-return]

    @property
    def source(self) -> str | None:
        return self.__pydantic_private__["_source"]  # type: ignore[index, no-any-return]

    @property
    def invalid_fields(self) -> frozenset[str]:
        """Attributes whose raw value failed format validation and was discarded."""
        return self.__pydantic_private__["_invalid"]  # type: ignore[index, no-any-return]

    def set_provenance(
        self, row: int | None, source: str | None, invalid: frozenset[str] = frozenset()
    ) -> None:
        private = self.__pydantic_private__
        if private is None:  # pragma: no cover - pydantic always initialises it
            private = self.__pydantic_private__ = {}
        private["_row"] = row
        private["_source"] = source
        private["_invalid"] = invalid

    # ----------------------------------------------------------------- helpers

    def key(self) -> tuple[Any, ...]:
        return tuple(getattr(self, k) for k in self.KEY)

    def key_str(self) -> str:
        return " | ".join("" if v is None else str(v) for v in self.key())

    def to_row(self) -> dict[str, str | None]:
        """Serialise to ``{column code: text}`` using internal codes and ISO dates."""
        out: dict[str, str | None] = {}
        for spec in self.columns():
            out[spec.code] = serialise_value(getattr(self, spec.attr))
        return out

    @model_validator(mode="before")
    @classmethod
    def _normalise_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        textual = _TEXTUAL_ATTRS.get(cls)
        if textual is None:
            textual = _TEXTUAL_ATTRS[cls] = frozenset(
                c.attr for c in cls.columns() if c.col.kind in _TEXTUAL_KINDS)
        out: dict[str, Any] = {}
        # exact type checks: this runs for every row of every import (hot path); enum
        # members (str subclasses) pass through unchanged
        for key, value in data.items():
            t = type(value)
            if t is str:
                value = value.strip() or None
            elif (t is int or t is float) and key in textual:
                value = str(int(value)) if float(value).is_integer() else str(value)
            out[key] = value
        return out


def serialise_value(value: Any) -> str | None:
    """Serialise a typed field value to its canonical text form."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, CodeEnum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    return str(value)


def _find_col(annotation: Any) -> Col | None:
    if get_origin(annotation) is Annotated:
        for meta in get_args(annotation)[1:]:
            if isinstance(meta, Col):
                return meta
    return None


# =========================================================================== B_01


class EntityMaintainingRegister(RoIRecord):
    """B_01.01 – Entity maintaining the register of information."""

    TEMPLATE: ClassVar[str] = "B_01.01"
    TITLE: ClassVar[str] = "Entity maintaining the register of information"
    KEY: ClassVar[tuple[str, ...]] = ("lei",)

    lei: Annotated[Lei | None, Col("c0010", "LEI of the entity maintaining the register", M,
                                   Kind.LEI)] = None
    name: Annotated[Text | None, Col("c0020", "Name of the entity", M, Kind.TEXT)] = None
    country: Annotated[Country | None, Col("c0030", "Country of the entity", M,
                                           Kind.COUNTRY)] = None
    entity_type: Annotated[EntityType | None, cl(EntityType),
                           Col("c0040", "Type of entity", M, Kind.CODELIST, EntityType)] = None
    competent_authority: Annotated[Text | None, Col("c0050", "Competent authority", M,
                                                    Kind.TEXT)] = None
    reporting_date: Annotated[IsoDate | None, Col("c0060", "Date of the reporting", M,
                                                  Kind.DATE)] = None


class EntityInScope(RoIRecord):
    """B_01.02 – List of entities within the scope of the register of information."""

    TEMPLATE: ClassVar[str] = "B_01.02"
    TITLE: ClassVar[str] = "List of entities within the scope of the register"
    KEY: ClassVar[tuple[str, ...]] = ("lei",)

    lei: Annotated[Lei | None, Col("c0010", "LEI of the entity", M, Kind.LEI)] = None
    name: Annotated[Text | None, Col("c0020", "Name of the entity", M, Kind.TEXT)] = None
    country: Annotated[Country | None, Col("c0030", "Country of the entity", M,
                                           Kind.COUNTRY)] = None
    entity_type: Annotated[EntityType | None, cl(EntityType),
                           Col("c0040", "Type of entity", M, Kind.CODELIST, EntityType)] = None
    hierarchy: Annotated[HierarchyInGroup | None, cl(HierarchyInGroup),
                         Col("c0050", "Hierarchy of the entity within the group", M,
                             Kind.CODELIST, HierarchyInGroup)] = None
    parent_lei: Annotated[Lei | None, Col(
        "c0060", "LEI of the direct parent undertaking", C, Kind.LEI,
        condition="Required unless the entity is the ultimate parent or not part of a group",
    )] = None
    last_update: Annotated[IsoDate | None, Col("c0070", "Date of last update", M,
                                               Kind.DATE)] = None
    integration_date: Annotated[IsoDate | None, Col("c0080", "Date of integration in the register",
                                                    M, Kind.DATE)] = None
    deletion_date: Annotated[IsoDate | None, Col(
        "c0090", "Date of deletion in the register", O, Kind.DATE,
        condition="Reported only when the entity left the scope",
    )] = None
    currency: Annotated[Currency | None, Col("c0100", "Currency", M, Kind.CURRENCY)] = None
    total_assets: Annotated[AmountT | None, Col("c0110", "Value of total assets", M,
                                                Kind.MONETARY)] = None


class Branch(RoIRecord):
    """B_01.03 – List of branches."""

    TEMPLATE: ClassVar[str] = "B_01.03"
    TITLE: ClassVar[str] = "List of branches"
    KEY: ClassVar[tuple[str, ...]] = ("branch_code", "head_office_lei")

    branch_code: Annotated[Text | None, Col("c0010", "Identification code of the branch", M,
                                            Kind.TEXT)] = None
    head_office_lei: Annotated[Lei | None, Col("c0020", "LEI of the head office of the branch", M,
                                               Kind.LEI)] = None
    name: Annotated[Text | None, Col("c0030", "Name of the branch", M, Kind.TEXT)] = None
    country: Annotated[Country | None, Col("c0040", "Country of the branch", M,
                                           Kind.COUNTRY)] = None


# =========================================================================== B_02


class ContractGeneral(RoIRecord):
    """B_02.01 – Contractual arrangements: general information."""

    TEMPLATE: ClassVar[str] = "B_02.01"
    TITLE: ClassVar[str] = "Contractual arrangements – general information"
    KEY: ClassVar[tuple[str, ...]] = ("contract_ref",)

    contract_ref: Annotated[Text | None, Col("c0010", "Contractual arrangement reference number",
                                             M, Kind.TEXT)] = None
    contract_type: Annotated[ContractType | None, cl(ContractType),
                             Col("c0020", "Type of contractual arrangement", M, Kind.CODELIST,
                                 ContractType)] = None
    overarching_ref: Annotated[Text | None, Col(
        "c0030", "Overarching contractual arrangement reference number", C, Kind.TEXT,
        condition="Required when the arrangement is a subsequent/associated arrangement",
    )] = None
    currency: Annotated[Currency | None, Col("c0040", "Currency of the amount reported", M,
                                             Kind.CURRENCY)] = None
    annual_cost: Annotated[AmountT | None, Col(
        "c0050", "Annual expense or estimated cost of the contractual arrangement", M,
        Kind.MONETARY)] = None


class ContractSpecific(RoIRecord):
    """B_02.02 – Contractual arrangements: specific information (one row per service)."""

    TEMPLATE: ClassVar[str] = "B_02.02"
    TITLE: ClassVar[str] = "Contractual arrangements – specific information"
    KEY: ClassVar[tuple[str, ...]] = (
        "contract_ref", "entity_lei", "provider_code", "function_id", "service_type",
    )

    contract_ref: Annotated[Text | None, Col("c0010", "Contractual arrangement reference number",
                                             M, Kind.TEXT)] = None
    entity_lei: Annotated[Lei | None, Col("c0020", "LEI of the entity making use of the ICT "
                                          "service(s)", M, Kind.LEI)] = None
    provider_code: Annotated[CodeT | None, Col(
        "c0030", "Identification code of the ICT third-party service provider", M,
        Kind.PROVIDER_CODE)] = None
    provider_code_type: Annotated[ProviderCodeType | None, cl(ProviderCodeType),
                                  Col("c0040", "Type of code to identify the ICT third-party "
                                      "service provider", M, Kind.CODELIST,
                                      ProviderCodeType)] = None
    function_id: Annotated[Text | None, Col("c0050", "Function identifier", M, Kind.TEXT)] = None
    service_type: Annotated[IctServiceType | None, cl(IctServiceType),
                            Col("c0060", "Type of ICT services", M, Kind.CODELIST,
                                IctServiceType)] = None
    start_date: Annotated[IsoDate | None, Col("c0070", "Start date of the contractual "
                                              "arrangement", M, Kind.DATE)] = None
    end_date: Annotated[IsoDate | None, Col(
        "c0080", "End date of the contractual arrangement", M, Kind.DATE,
        condition="Use 9999-12-31 for arrangements without an end date")] = None
    termination_reason: Annotated[TerminationReason | None, cl(TerminationReason), Col(
        "c0090", "Reason of the termination or ending of the contractual arrangement", C,
        Kind.CODELIST, TerminationReason,
        condition="Required when the end date is on or before the reporting date")] = None
    notice_period_entity: Annotated[NonNegInt | None, Col(
        "c0100", "Notice period for the financial entity (calendar days)", M,
        Kind.INTEGER)] = None
    notice_period_provider: Annotated[NonNegInt | None, Col(
        "c0110", "Notice period for the ICT third-party service provider (calendar days)", M,
        Kind.INTEGER)] = None
    governing_law_country: Annotated[Country | None, Col(
        "c0120", "Country of the governing law of the contractual arrangement", M,
        Kind.COUNTRY)] = None
    service_country: Annotated[Country | None, Col(
        "c0130", "Country of provision of the ICT services", M, Kind.COUNTRY)] = None
    data_storage: Annotated[Flag | None, Col("c0140", "Storage of data", M, Kind.BOOLEAN)] = None
    data_location_storage: Annotated[Country | None, Col(
        "c0150", "Location of the data at rest (storage)", C, Kind.COUNTRY,
        condition="Required when storage of data (c0140) is true")] = None
    data_location_processing: Annotated[Country | None, Col(
        "c0160", "Location of management of the data (processing)", C, Kind.COUNTRY,
        condition="Required when the ICT service involves processing of data")] = None
    data_sensitivity: Annotated[DataSensitivity | None, cl(DataSensitivity), Col(
        "c0170", "Sensitiveness of the data stored by the ICT third-party service provider", C,
        Kind.CODELIST, DataSensitivity,
        condition="Required when storage of data (c0140) is true")] = None
    reliance_level: Annotated[RelianceLevel | None, cl(RelianceLevel), Col(
        "c0180", "Level of reliance on the ICT service", M, Kind.CODELIST,
        RelianceLevel)] = None


class IntraGroupContractLink(RoIRecord):
    """B_02.03 – List of intra-group contractual arrangements (links between arrangements)."""

    TEMPLATE: ClassVar[str] = "B_02.03"
    TITLE: ClassVar[str] = "List of intra-group contractual arrangements"
    KEY: ClassVar[tuple[str, ...]] = ("contract_ref", "linked_contract_ref")

    contract_ref: Annotated[Text | None, Col("c0010", "Contractual arrangement reference number",
                                             M, Kind.TEXT)] = None
    linked_contract_ref: Annotated[Text | None, Col(
        "c0020", "Contractual arrangement linked to the arrangement in c0010", M,
        Kind.TEXT)] = None
    link: Annotated[Flag | None, Col("c0030", "Link", M, Kind.BOOLEAN)] = True


# =========================================================================== B_03


class ContractSigningEntity(RoIRecord):
    """B_03.01 – Entities signing the contractual arrangements for receiving ICT services."""

    TEMPLATE: ClassVar[str] = "B_03.01"
    TITLE: ClassVar[str] = "Entities signing the contractual arrangements (receiving)"
    KEY: ClassVar[tuple[str, ...]] = ("contract_ref", "entity_lei")

    contract_ref: Annotated[Text | None, Col("c0010", "Contractual arrangement reference number",
                                             M, Kind.TEXT)] = None
    entity_lei: Annotated[Lei | None, Col("c0020", "LEI of the entity signing the contractual "
                                          "arrangement", M, Kind.LEI)] = None
    link: Annotated[Flag | None, Col("c0030", "Link", M, Kind.BOOLEAN)] = True


class ContractSigningProvider(RoIRecord):
    """B_03.02 – ICT third-party service providers signing the contractual arrangements."""

    TEMPLATE: ClassVar[str] = "B_03.02"
    TITLE: ClassVar[str] = "ICT third-party service providers signing the arrangements"
    KEY: ClassVar[tuple[str, ...]] = ("contract_ref", "provider_code")

    contract_ref: Annotated[Text | None, Col("c0010", "Contractual arrangement reference number",
                                             M, Kind.TEXT)] = None
    provider_code: Annotated[CodeT | None, Col(
        "c0020", "Identification code of the ICT third-party service provider", M,
        Kind.PROVIDER_CODE)] = None
    provider_code_type: Annotated[ProviderCodeType | None, cl(ProviderCodeType), Col(
        "c0030", "Type of code to identify the ICT third-party service provider", M,
        Kind.CODELIST, ProviderCodeType)] = None
    link: Annotated[Flag | None, Col("c0040", "Link", M, Kind.BOOLEAN)] = True


class IntraGroupProvidingEntity(RoIRecord):
    """B_03.03 – Entities signing intra-group arrangements for *providing* ICT services."""

    TEMPLATE: ClassVar[str] = "B_03.03"
    TITLE: ClassVar[str] = "Entities signing the contractual arrangements (providing)"
    KEY: ClassVar[tuple[str, ...]] = ("contract_ref", "entity_lei")

    contract_ref: Annotated[Text | None, Col("c0010", "Contractual arrangement reference number",
                                             M, Kind.TEXT)] = None
    entity_lei: Annotated[Lei | None, Col("c0020", "LEI of the entity providing ICT services",
                                          M, Kind.LEI)] = None
    link: Annotated[Flag | None, Col("c0030", "Link", M, Kind.BOOLEAN)] = True


# =========================================================================== B_04


class ServiceRecipient(RoIRecord):
    """B_04.01 – Entities making use of the ICT services."""

    TEMPLATE: ClassVar[str] = "B_04.01"
    TITLE: ClassVar[str] = "Entities making use of the ICT services"
    KEY: ClassVar[tuple[str, ...]] = ("contract_ref", "entity_lei", "branch_code")

    contract_ref: Annotated[Text | None, Col("c0010", "Contractual arrangement reference number",
                                             M, Kind.TEXT)] = None
    entity_lei: Annotated[Lei | None, Col("c0020", "LEI of the entity making use of the ICT "
                                          "services", M, Kind.LEI)] = None
    is_branch: Annotated[Flag | None, Col(
        "c0030", "Nature of the entity making use of the ICT services (true = branch)", M,
        Kind.BOOLEAN)] = None
    branch_code: Annotated[Text | None, Col(
        "c0040", "Identification code of the branch", C, Kind.TEXT,
        condition="Required when c0030 is true (the user is a branch)")] = None


# =========================================================================== B_05


class IctThirdPartyProvider(RoIRecord):
    """B_05.01 – ICT third-party service providers."""

    TEMPLATE: ClassVar[str] = "B_05.01"
    TITLE: ClassVar[str] = "ICT third-party service providers"
    KEY: ClassVar[tuple[str, ...]] = ("provider_code",)

    provider_code: Annotated[CodeT | None, Col(
        "c0010", "Identification code of the ICT third-party service provider", M,
        Kind.PROVIDER_CODE)] = None
    provider_code_type: Annotated[ProviderCodeType | None, cl(ProviderCodeType), Col(
        "c0020", "Type of code to identify the ICT third-party service provider", M,
        Kind.CODELIST, ProviderCodeType)] = None
    additional_code: Annotated[CodeT | None, Col(
        "c0030", "Additional identification code of the ICT third-party service provider", O,
        Kind.TEXT)] = None
    additional_code_type: Annotated[AdditionalCodeType | None, cl(AdditionalCodeType), Col(
        "c0040", "Type of additional identification code", C, Kind.CODELIST,
        AdditionalCodeType, condition="Required when an additional code (c0030) is given")] = None
    legal_name: Annotated[Text | None, Col("c0050", "Legal name of the ICT third-party service "
                                           "provider", M, Kind.TEXT)] = None
    latin_name: Annotated[Text | None, Col("c0060", "Name of the ICT third-party service "
                                           "provider in Latin alphabet", O, Kind.TEXT)] = None
    person_type: Annotated[PersonType | None, cl(PersonType), Col(
        "c0070", "Type of person of the ICT third-party service provider", M, Kind.CODELIST,
        PersonType)] = None
    hq_country: Annotated[Country | None, Col(
        "c0080", "Country of the ICT third-party service provider's headquarters", M,
        Kind.COUNTRY)] = None
    currency: Annotated[Currency | None, Col("c0090", "Currency of the amount reported", M,
                                             Kind.CURRENCY)] = None
    total_annual_cost: Annotated[AmountT | None, Col(
        "c0100", "Total annual expense or estimated cost of the ICT third-party service provider",
        M, Kind.MONETARY)] = None
    ultimate_parent_code: Annotated[CodeT | None, Col(
        "c0110", "Identification code of the provider's ultimate parent undertaking", M,
        Kind.PROVIDER_CODE,
        condition="Report the provider's own code if it is its own ultimate parent")] = None
    ultimate_parent_code_type: Annotated[ProviderCodeType | None, cl(ProviderCodeType), Col(
        "c0120", "Type of code to identify the ultimate parent undertaking", M, Kind.CODELIST,
        ProviderCodeType)] = None


class SupplyChainEntry(RoIRecord):
    """B_05.02 – ICT service supply chains (subcontracting)."""

    TEMPLATE: ClassVar[str] = "B_05.02"
    TITLE: ClassVar[str] = "ICT service supply chains"
    KEY: ClassVar[tuple[str, ...]] = (
        "contract_ref", "service_type", "provider_code", "rank", "recipient_code",
    )

    contract_ref: Annotated[Text | None, Col("c0010", "Contractual arrangement reference number",
                                             M, Kind.TEXT)] = None
    service_type: Annotated[IctServiceType | None, cl(IctServiceType), Col(
        "c0020", "Type of ICT services", M, Kind.CODELIST, IctServiceType)] = None
    provider_code: Annotated[CodeT | None, Col(
        "c0030", "Identification code of the ICT third-party service provider", M,
        Kind.PROVIDER_CODE)] = None
    provider_code_type: Annotated[ProviderCodeType | None, cl(ProviderCodeType), Col(
        "c0040", "Type of code to identify the ICT third-party service provider", M,
        Kind.CODELIST, ProviderCodeType)] = None
    rank: Annotated[PositiveInt | None, Col("c0050", "Rank", M, Kind.INTEGER)] = None
    recipient_code: Annotated[CodeT | None, Col(
        "c0060", "Identification code of the recipient of sub-contracted ICT services", C,
        Kind.PROVIDER_CODE, condition="Required when rank > 1")] = None
    recipient_code_type: Annotated[ProviderCodeType | None, cl(ProviderCodeType), Col(
        "c0070", "Type of code to identify the recipient of sub-contracted ICT services", C,
        Kind.CODELIST, ProviderCodeType, condition="Required when rank > 1")] = None


# =========================================================================== B_06


class Function(RoIRecord):
    """B_06.01 – Functions identification."""

    TEMPLATE: ClassVar[str] = "B_06.01"
    TITLE: ClassVar[str] = "Functions identification"
    KEY: ClassVar[tuple[str, ...]] = ("function_id", "entity_lei")

    function_id: Annotated[Text | None, Col("c0010", "Function identifier", M, Kind.TEXT)] = None
    licensed_activity: Annotated[Text | None, Col("c0020", "Licensed activity", M,
                                                  Kind.TEXT)] = None
    function_name: Annotated[Text | None, Col("c0030", "Function name", M, Kind.TEXT)] = None
    entity_lei: Annotated[Lei | None, Col("c0040", "LEI of the financial entity", M,
                                          Kind.LEI)] = None
    criticality: Annotated[Criticality | None, cl(Criticality), Col(
        "c0050", "Criticality or importance assessment", M, Kind.CODELIST, Criticality)] = None
    criticality_reasons: Annotated[Text | None, Col(
        "c0060", "Reasons for criticality or importance", C, Kind.TEXT,
        condition="Required when the function is critical or important")] = None
    last_assessment_date: Annotated[IsoDate | None, Col(
        "c0070", "Date of the last assessment of criticality or importance", M,
        Kind.DATE)] = None
    rto_hours: Annotated[NonNegInt | None, Col(
        "c0080", "Recovery time objective of the function (hours)", C, Kind.INTEGER,
        condition="Required when the function is critical or important")] = None
    rpo_hours: Annotated[NonNegInt | None, Col(
        "c0090", "Recovery point objective of the function (hours)", C, Kind.INTEGER,
        condition="Required when the function is critical or important")] = None
    discontinuation_impact: Annotated[Impact | None, cl(Impact), Col(
        "c0100", "Impact of discontinuing the function", M, Kind.CODELIST, Impact)] = None

    @property
    def is_critical(self) -> bool:
        return self.criticality is Criticality.CRITICAL


# =========================================================================== B_07


class ServiceAssessment(RoIRecord):
    """B_07.01 – Assessment of the ICT services (substitutability, exit plans)."""

    TEMPLATE: ClassVar[str] = "B_07.01"
    TITLE: ClassVar[str] = "Assessment of the ICT services"
    KEY: ClassVar[tuple[str, ...]] = ("contract_ref", "provider_code", "service_type")

    contract_ref: Annotated[Text | None, Col("c0010", "Contractual arrangement reference number",
                                             M, Kind.TEXT)] = None
    provider_code: Annotated[CodeT | None, Col(
        "c0020", "Identification code of the ICT third-party service provider", M,
        Kind.PROVIDER_CODE)] = None
    provider_code_type: Annotated[ProviderCodeType | None, cl(ProviderCodeType), Col(
        "c0030", "Type of code to identify the ICT third-party service provider", M,
        Kind.CODELIST, ProviderCodeType)] = None
    service_type: Annotated[IctServiceType | None, cl(IctServiceType), Col(
        "c0040", "Type of ICT services", M, Kind.CODELIST, IctServiceType)] = None
    substitutability: Annotated[Substitutability | None, cl(Substitutability), Col(
        "c0050", "Substitutability of the ICT third-party service provider", M, Kind.CODELIST,
        Substitutability)] = None
    non_substitutability_reason: Annotated[
        NonSubstitutabilityReason | None, cl(NonSubstitutabilityReason), Col(
            "c0060", "Reason if the provider is not or difficult to be substitutable", C,
            Kind.CODELIST, NonSubstitutabilityReason,
            condition="Required when substitutability is NOT_SUBSTITUTABLE or HIGHLY_COMPLEX"),
    ] = None
    last_audit_date: Annotated[IsoDate | None, Col(
        "c0070", "Date of the last audit on the ICT third-party service provider", O,
        Kind.DATE)] = None
    exit_plan: Annotated[Flag | None, Col("c0080", "Existence of an exit plan", M,
                                          Kind.BOOLEAN)] = None
    reintegration: Annotated[Reintegration | None, cl(Reintegration), Col(
        "c0090", "Possibility of reintegration of the contracted ICT service", M,
        Kind.CODELIST, Reintegration)] = None
    discontinuation_impact: Annotated[Impact | None, cl(Impact), Col(
        "c0100", "Impact of discontinuing the ICT services", M, Kind.CODELIST, Impact)] = None
    alternatives_identified: Annotated[Flag | None, Col(
        "c0110", "Are there alternative ICT third-party service providers identified?", M,
        Kind.BOOLEAN)] = None
    alternative_providers: Annotated[Text | None, Col(
        "c0120", "Identification of alternative ICT third-party service providers", C,
        Kind.TEXT, condition="Required when c0110 is true")] = None


#: All template models in ITS order.
TEMPLATE_MODELS: tuple[type[RoIRecord], ...] = (
    EntityMaintainingRegister,
    EntityInScope,
    Branch,
    ContractGeneral,
    ContractSpecific,
    IntraGroupContractLink,
    ContractSigningEntity,
    ContractSigningProvider,
    IntraGroupProvidingEntity,
    ServiceRecipient,
    IctThirdPartyProvider,
    SupplyChainEntry,
    Function,
    ServiceAssessment,
)

TEMPLATES_BY_CODE: dict[str, type[RoIRecord]] = {m.TEMPLATE: m for m in TEMPLATE_MODELS}
