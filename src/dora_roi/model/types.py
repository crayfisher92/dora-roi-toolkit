"""Column metadata and reusable annotated field types.

Every template field is declared as ``Annotated[<type> | None, Col(...)]``. The :class:`Col`
object carries the ITS column code, label, requirement level and semantic kind; the
annotated types (``Lei``, ``Country`` …) carry the format checks. Format violations raise
:class:`pydantic_core.PydanticCustomError` with a ``roi_*`` error type so that the parser can
map them onto validation rule identifiers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator, Field
from pydantic_core import PydanticCustomError

from dora_roi.lei import explain_lei_error
from dora_roi.model.codelists import CodeEnum
from dora_roi.model.refdata import COUNTRIES, COUNTRY_HINTS, CURRENCIES


class Requirement(StrEnum):
    """Whether a column must be reported."""

    MANDATORY = "M"
    CONDITIONAL = "C"
    OPTIONAL = "O"


class Kind(StrEnum):
    """Semantic kind of a column; drives parsing, serialisation and documentation."""

    TEXT = "text"
    LEI = "lei"
    PROVIDER_CODE = "provider_code"
    COUNTRY = "country"
    CURRENCY = "currency"
    DATE = "date"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    MONETARY = "monetary"
    CODELIST = "codelist"


@dataclass(frozen=True)
class Col:
    """Metadata of one RoI column (attached to a model field via ``Annotated``)."""

    code: str
    label: str
    requirement: Requirement
    kind: Kind
    codelist: type[CodeEnum] | None = None
    condition: str | None = None

    @property
    def mandatory(self) -> bool:
        return self.requirement is Requirement.MANDATORY


M = Requirement.MANDATORY
C = Requirement.CONDITIONAL
O = Requirement.OPTIONAL  # noqa: E741 - mirrors the M/C/O notation used in the ITS

TEXT_MAX_LENGTH = 255
INDEFINITE_END_DATE = date(9999, 12, 31)


# --------------------------------------------------------------------------- validators


def _upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


def _check_lei(value: str) -> str:
    problem = explain_lei_error(value)
    if problem:
        raise PydanticCustomError("roi_lei", "'{value}' is not a valid LEI: {problem}",
                                  {"value": value, "problem": problem})
    return value


def _check_country(value: str) -> str:
    if value not in COUNTRIES:
        hint = COUNTRY_HINTS.get(value)
        suffix = f" (did you mean '{hint}'?)" if hint else ""
        raise PydanticCustomError(
            "roi_country",
            "'{value}' is not an ISO 3166-1 alpha-2 country code{suffix}",
            {"value": value, "suffix": suffix},
        )
    return value


def _check_currency(value: str) -> str:
    if value not in CURRENCIES:
        raise PydanticCustomError(
            "roi_currency", "'{value}' is not an active ISO 4217 currency code", {"value": value}
        )
    return value


_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[ T]00:00(?::00(?:\.0+)?)?)?$")


def _parse_date(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        match = _DATE_RE.match(value.strip())
        if match:
            try:
                return date.fromisoformat(match.group(1))
            except ValueError:
                pass
    raise PydanticCustomError(
        "roi_date", "'{value}' is not a valid ISO 8601 date (YYYY-MM-DD)", {"value": str(value)}
    )


_TRUE = {"true", "yes", "y", "1", "x", "ja", "oui"}
_FALSE = {"false", "no", "n", "0", "nein", "non"}


def _parse_bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().casefold()
        # tolerate taxonomy-style values such as "eba_BT:x28" being mapped upstream
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    raise PydanticCustomError(
        "roi_bool", "'{value}' is not a valid boolean (true/false)", {"value": str(value)}
    )


def _parse_decimal(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip().replace("'", "").replace(" ", "").replace(" ", "")
        # accept "1,234,567.89"; reject ambiguous European decimal commas loudly
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", text):
            text = text.replace(",", "")
        return text
    return value


def codelist_validator(enum_cls: type[CodeEnum]) -> BeforeValidator:
    """Build a before-validator resolving codes, labels and aliases of ``enum_cls``."""

    def _resolve(value: Any) -> Any:
        if value is None or isinstance(value, enum_cls):
            return value
        if isinstance(value, str):
            member = enum_cls.lookup(value)
            if member is not None:
                return member
        allowed = ", ".join(m.value for m in enum_cls)
        raise PydanticCustomError(
            "roi_codelist",
            "'{value}' is not a valid {codelist} code (allowed: {allowed})",
            {"value": str(value), "codelist": enum_cls.__name__, "allowed": allowed},
        )

    return BeforeValidator(_resolve)


# --------------------------------------------------------------------------- annotated types

Lei = Annotated[str, BeforeValidator(_upper), AfterValidator(_check_lei)]
Country = Annotated[str, BeforeValidator(_upper), AfterValidator(_check_country)]
Currency = Annotated[str, BeforeValidator(_upper), AfterValidator(_check_currency)]
IsoDate = Annotated[date, BeforeValidator(_parse_date)]
Flag = Annotated[bool, BeforeValidator(_parse_bool)]
Text = Annotated[str, Field(max_length=TEXT_MAX_LENGTH)]
Code = Annotated[str, BeforeValidator(_upper), Field(max_length=TEXT_MAX_LENGTH)]
Amount = Annotated[Decimal, BeforeValidator(_parse_decimal), Field(ge=0, decimal_places=6)]
NonNegInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
