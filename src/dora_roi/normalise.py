"""Best-effort normalisation of free-text values found in real-world inventories.

Used by the fix suggestions (``dora_roi.fixes``) and the column-mapping import
(``dora_roi.inventory``). Every function returns ``None`` when it is not confident, so callers
can keep the original value and let the validator report it.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from difflib import get_close_matches

from dora_roi.model import CodeEnum, Criticality, IctServiceType, Substitutability
from dora_roi.model.refdata import COUNTRIES, COUNTRY_HINTS, CURRENCIES


def fold(text: str) -> str:
    """Lower-case, strip accents and collapse non-alphanumerics to single spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


# --------------------------------------------------------------------------- countries

_COUNTRY_ALIASES: dict[str, str] = {
    "uk": "GB", "united kingdom": "GB", "great britain": "GB", "england": "GB",
    "grossbritannien": "GB", "vereinigtes konigreich": "GB", "usa": "US", "us": "US",
    "united states of america": "US", "vereinigte staaten": "US", "deutschland": "DE",
    "osterreich": "AT", "schweiz": "CH", "suisse": "CH", "svizzera": "CH", "frankreich": "FR",
    "italien": "IT", "spanien": "ES", "niederlande": "NL", "holland": "NL", "belgien": "BE",
    "luxemburg": "LU", "irland": "IE", "polen": "PL", "ungarn": "HU", "rumanien": "RO",
    "schweden": "SE", "danemark": "DK", "finnland": "FI", "norwegen": "NO", "tschechien": "CZ",
    "griechenland": "GR", "el": "GR", "portugal": "PT", "liechtenstein": "LI", "indien": "IN",
    "japan": "JP", "china": "CN", "kanada": "CA", "israel": "IL", "singapur": "SG",
    "south korea": "KR", "korea": "KR", "russia": "RU", "czech republic": "CZ",
    "turkey": "TR", "turkei": "TR", "slowakei": "SK", "slowenien": "SI", "kroatien": "HR",
    "bulgarien": "BG", "zypern": "CY", "estland": "EE", "lettland": "LV", "litauen": "LT",
}
_COUNTRY_BY_NAME: dict[str, str] = {fold(name): code for code, name in COUNTRIES.items()}


def country_code(text: str) -> str | None:
    """``'Deutschland'`` → ``'DE'``, ``'UK'`` → ``'GB'``, ``'de'`` → ``'DE'``."""
    raw = text.strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper in COUNTRY_HINTS:
        return COUNTRY_HINTS[upper]
    if len(upper) == 2 and upper in COUNTRIES:
        return upper
    key = fold(raw)
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    if key in _COUNTRY_BY_NAME:
        return _COUNTRY_BY_NAME[key]
    match = get_close_matches(key, list(_COUNTRY_BY_NAME) + list(_COUNTRY_ALIASES), n=1,
                              cutoff=0.85)
    if match:
        return _COUNTRY_BY_NAME.get(match[0]) or _COUNTRY_ALIASES[match[0]]
    return None


# --------------------------------------------------------------------------- currencies

_CURRENCY_ALIASES = {"euro": "EUR", "euros": "EUR", "€": "EUR", "eur.": "EUR", "chf.": "CHF",
                     "fr.": "CHF", "sfr": "CHF", "franken": "CHF", "$": "USD", "us$": "USD",
                     "dollar": "USD", "£": "GBP", "pound": "GBP", "pfund": "GBP"}


def currency_code(text: str) -> str | None:
    raw = text.strip()
    if raw.upper() in CURRENCIES:
        return raw.upper()
    return _CURRENCY_ALIASES.get(raw.casefold())


# --------------------------------------------------------------------------- dates

_DATE_PATTERNS = (
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"), "dmy"),
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$"), "dmy"),
    (re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$"), "dmy"),
    (re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$"), "ymd"),
    (re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$"), "ymd"),
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$"), "ymd"),
)
_OPEN_ENDED = {"unbefristet", "unlimited", "indefinite", "open", "open ended", "open-ended",
               "none", "n/a", "na", "-", "evergreen", "auto renewal", "automatic renewal"}


def to_date(value: object) -> date | None:
    """Parse ISO, ``31.12.2025``, ``31/12/2025`` (day first), Excel serial numbers."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool) and 20000 < value < 80000:
        return date(1899, 12, 30) + timedelta(days=int(value))
    if not isinstance(value, str):
        return None
    text = value.strip()
    for pattern, order in _DATE_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        a, b, c = (int(x) for x in m.groups()[:3])
        try:
            return date(c, b, a) if order == "dmy" else date(a, b, c)
        except ValueError:
            return None
    return None


def end_date(value: object) -> date | None:
    """Like :func:`to_date` but maps "unbefristet"/"indefinite" to 9999-12-31."""
    if isinstance(value, str) and fold(value) in {fold(x) for x in _OPEN_ENDED}:
        return date(9999, 12, 31)
    return to_date(value)


# --------------------------------------------------------------------------- numbers

_MULTIPLIERS = {"k": Decimal(1000), "tsd": Decimal(1000), "m": Decimal(10**6),
                "mio": Decimal(10**6), "mn": Decimal(10**6), "bn": Decimal(10**9)}


def to_amount(value: object) -> Decimal | None:
    """Parse ``1.234.567,89``, ``1,234,567.89``, ``EUR 12k``, ``CHF 1.2 Mio``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    if not isinstance(value, str):
        return None
    text = re.sub(r"\b[A-Z]{3}\b|[€$£]", "", value.strip()).strip()
    mult = Decimal(1)
    m = re.search(r"\s*(k|tsd|m|mio|mn|bn)\.?$", text, re.IGNORECASE)
    if m:
        mult = _MULTIPLIERS[m.group(1).lower()]
        text = text[: m.start()]
    text = text.replace("'", "").replace(" ", "").replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", text) or re.fullmatch(r"-?\d+,\d+", text):
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return Decimal(text) * mult if text else None
    except InvalidOperation:
        return None


def to_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        if m:
            n = int(m.group())
            if re.search(r"month|monat", value, re.IGNORECASE):
                return n * 30
            if re.search(r"year|jahr", value, re.IGNORECASE):
                return n * 365
            return n
    return None


# --------------------------------------------------------------------------- booleans

_TRUE = {"true", "yes", "y", "ja", "j", "x", "1", "oui", "si", "wahr", "vorhanden"}
_FALSE = {"false", "no", "n", "nein", "0", "non", "falsch", "keine", "kein", "none"}


def to_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        key = fold(value)
        if key in _TRUE:
            return True
        if key in _FALSE:
            return False
    return None


# --------------------------------------------------------------------------- code lists

_SERVICE_KEYWORDS: tuple[tuple[str, IctServiceType], ...] = (
    ("iaas", IctServiceType.S17), ("infrastructure as a service", IctServiceType.S17),
    ("paas", IctServiceType.S18), ("platform as a service", IctServiceType.S18),
    ("saas", IctServiceType.S19), ("software as a service", IctServiceType.S19),
    ("cloud", IctServiceType.S19), ("hosting", IctServiceType.S07),
    ("colocation", IctServiceType.S07), ("rechenzentrum", IctServiceType.S07),
    ("data centre", IctServiceType.S07), ("data center", IctServiceType.S07),
    ("licen", IctServiceType.S13), ("lizenz", IctServiceType.S13),
    ("wartung", IctServiceType.S14), ("maintenance", IctServiceType.S14),
    ("betrieb", IctServiceType.S14), ("operation", IctServiceType.S14),
    ("outsourcing", IctServiceType.S14), ("help desk", IctServiceType.S03),
    ("helpdesk", IctServiceType.S03), ("service desk", IctServiceType.S03),
    ("support", IctServiceType.S03), ("security", IctServiceType.S04),
    ("sicherheit", IctServiceType.S04), ("soc", IctServiceType.S04),
    ("market data", IctServiceType.S05), ("marktdaten", IctServiceType.S05),
    ("data provision", IctServiceType.S05), ("analytics", IctServiceType.S06),
    ("analyse", IctServiceType.S06), ("telecom", IctServiceType.S10),
    ("telekom", IctServiceType.S10), ("carrier", IctServiceType.S10),
    ("network", IctServiceType.S11), ("netzwerk", IctServiceType.S11),
    ("hardware", IctServiceType.S12), ("development", IctServiceType.S02),
    ("entwicklung", IctServiceType.S02), ("consulting", IctServiceType.S15),
    ("beratung", IctServiceType.S15), ("project", IctServiceType.S01),
    ("projekt", IctServiceType.S01), ("risk", IctServiceType.S16),
    ("backup", IctServiceType.S09), ("archiv", IctServiceType.S09),
    ("storage", IctServiceType.S09), ("compute", IctServiceType.S08),
    ("processing", IctServiceType.S08), ("verarbeitung", IctServiceType.S08),
)


def service_type(text: str) -> IctServiceType | None:
    """Map a free-text service description to an ICT service type (S01–S19)."""
    direct = IctServiceType.lookup(text)
    if direct is not None:
        return direct
    key = fold(text)
    for keyword, member in _SERVICE_KEYWORDS:
        if keyword in key:
            return member
    return None


def criticality(value: object) -> Criticality | None:
    if isinstance(value, str):
        member = Criticality.lookup(value)
        if member is not None:
            return member
        key = fold(value)
        if key in {"kritisch", "wesentlich", "critical", "important", "kritisch wichtig", "high"}:
            return Criticality.CRITICAL
        if key in {"nicht kritisch", "unkritisch", "not critical", "low", "non critical"}:
            return Criticality.NOT_CRITICAL
    flag = to_bool(value)
    if flag is not None:
        return Criticality.CRITICAL if flag else Criticality.NOT_CRITICAL
    return None


def substitutability(text: str) -> Substitutability | None:
    member = Substitutability.lookup(text)
    if member is not None:
        return member
    key = fold(text)
    table = {
        "not substitutable": Substitutability.NOT_SUBSTITUTABLE,
        "nicht ersetzbar": Substitutability.NOT_SUBSTITUTABLE,
        "none": Substitutability.NOT_SUBSTITUTABLE,
        "high": Substitutability.HIGHLY_COMPLEX, "hoch": Substitutability.HIGHLY_COMPLEX,
        "schwer": Substitutability.HIGHLY_COMPLEX, "difficult": Substitutability.HIGHLY_COMPLEX,
        "medium": Substitutability.MEDIUM, "mittel": Substitutability.MEDIUM,
        "low": Substitutability.EASY, "easy": Substitutability.EASY,
        "leicht": Substitutability.EASY, "niedrig": Substitutability.EASY,
    }
    return table.get(key)


def closest_code(codelist: type[CodeEnum], text: str) -> CodeEnum | None:
    """Fuzzy match ``text`` against codes and labels of a code list."""
    exact = codelist.lookup(text)
    if exact is not None:
        return exact
    candidates: dict[str, CodeEnum] = {}
    for m in codelist:
        candidates[fold(m.value)] = m
        candidates[fold(m.label)] = m
    match = get_close_matches(fold(text), list(candidates), n=1, cutoff=0.6)
    return candidates[match[0]] if match else None
