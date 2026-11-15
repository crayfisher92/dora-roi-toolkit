"""Optional online check of the register's LEIs against the GLEIF Global LEI Index.

**Off by default.** The toolkit works offline; this module is only used with
``roi validate --online`` or, in the workbench, when ``ROI_GLEIF=1`` is set and a user clicks
*Check LEIs with GLEIF*. It sends nothing but the LEIs themselves – public identifiers – to
the public GLEIF API (``https://api.gleif.org``, no account, no API key); names, contracts and
all other register data stay local. HTTPS proxies are taken from the environment
(``HTTPS_PROXY``), as usual for :mod:`urllib`.

What is checked (rules ``GLEIF-001`` … ``GLEIF-004``, see ``docs/REGULATORY_MAPPING.md``):

* the LEI exists in the Global LEI Index;
* its registration is in good standing (*issued*, not lapsed, retired, annulled …) and the
  entity is *active*;
* the name in the register matches the GLEIF legal name or one of its other names;
* the country in the register matches the GLEIF legal address (entities) or headquarters
  address (ICT third-party service providers).

Checked are the LEIs that identify a record: the entity maintaining the register (B_01.01),
the entities in scope and their parents (B_01.02), and providers and their ultimate parents
whose code type is LEI (B_05.01). LEIs elsewhere refer to these records and are covered by the
referential rules.
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from dora_roi import __version__
from dora_roi.lei import is_valid_lei
from dora_roi.model import RegisterOfInformation
from dora_roi.model.templates import RoIRecord
from dora_roi.validation import Finding, ValidationConfig, ValidationContext

GLEIF_API = "https://api.gleif.org/api/v1/lei-records"
BATCH_SIZE = 200  # the API's maximum page size
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
TIMEOUT_SECONDS = 20.0
#: registration statuses of an LEI in good standing (GLEIF state transition rules)
GOOD_STANDING = frozenset({"ISSUED", "PENDING_TRANSFER", "PENDING_ARCHIVAL"})

class GleifError(Exception):
    """The GLEIF API could not be reached or returned something unexpected."""


@dataclass(frozen=True)
class LeiRecord:
    """What the toolkit uses from a GLEIF LEI record."""

    lei: str
    legal_name: str
    other_names: tuple[str, ...] = ()
    legal_country: str | None = None
    hq_country: str | None = None
    entity_status: str | None = None
    registration_status: str | None = None
    next_renewal: date | None = None
    successor_lei: str | None = None

    @property
    def in_good_standing(self) -> bool:
        return (self.registration_status in GOOD_STANDING
                and self.entity_status in (None, "ACTIVE"))


Fetch = Callable[[str], bytes]


def http_get(url: str) -> bytes:
    """GET ``url`` from the GLEIF API (HTTPS only, bounded size and time)."""
    if not url.startswith("https://"):
        raise GleifError("only HTTPS URLs are fetched")
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.api+json",
        "User-Agent": f"dora-roi-toolkit/{__version__}",
    })
    try:
        # bandit B310: the scheme is checked above and the URL is built from GLEIF_API
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310
            body: bytes = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise GleifError(f"GLEIF API answered HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise GleifError(f"GLEIF API not reachable ({reason})") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise GleifError("GLEIF API response too large")
    return body


def _str(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_records(body: bytes) -> dict[str, LeiRecord]:
    """Parse a ``lei-records`` response of the GLEIF API (JSON:API)."""
    try:
        payload = json.loads(body)
        data = payload["data"]
        if not isinstance(data, list):
            raise TypeError("data is not a list")
    except (ValueError, KeyError, TypeError) as exc:
        raise GleifError("unexpected response from the GLEIF API") from exc
    out: dict[str, LeiRecord] = {}
    for item in data:
        attrs = item.get("attributes") if isinstance(item, dict) else None
        if not isinstance(attrs, dict):
            continue
        lei = _str(attrs.get("lei")) or _str(item.get("id"))
        entity = attrs.get("entity") or {}
        registration = attrs.get("registration") or {}
        if not lei or not isinstance(entity, dict) or not isinstance(registration, dict):
            continue
        names = [(_str(n.get("name")) or "") for key in ("otherNames", "transliteratedOtherNames")
                 for n in entity.get(key) or [] if isinstance(n, dict)]
        successor = entity.get("successorEntity") or {}
        out[lei.upper()] = LeiRecord(
            lei=lei.upper(),
            legal_name=_str((entity.get("legalName") or {}).get("name")) or "",
            other_names=tuple(n for n in names if n),
            legal_country=_str((entity.get("legalAddress") or {}).get("country")),
            hq_country=_str((entity.get("headquartersAddress") or {}).get("country")),
            entity_status=_str(entity.get("status")),
            registration_status=_str(registration.get("status")),
            next_renewal=_date(registration.get("nextRenewalDate")),
            successor_lei=_str(successor.get("lei")) if isinstance(successor, dict) else None,
        )
    return out


class GleifClient:
    """Looks LEIs up in batches, with an in-memory cache (default: one day)."""

    def __init__(self, fetch: Fetch | None = None, *, base_url: str = GLEIF_API,
                 ttl: timedelta = timedelta(days=1)) -> None:
        self._fetch = fetch or http_get
        self._base_url = base_url
        self._ttl = ttl
        self._cache: dict[str, tuple[datetime, LeiRecord | None]] = {}

    def lookup(self, leis: Iterable[str]) -> dict[str, LeiRecord | None]:
        """Records for the syntactically valid ``leis``; ``None`` where GLEIF has none."""
        now = datetime.now(UTC)
        wanted = sorted({x.strip().upper() for x in leis if x and is_valid_lei(x.strip().upper())})
        out: dict[str, LeiRecord | None] = {}
        todo: list[str] = []
        for lei in wanted:
            hit = self._cache.get(lei)
            if hit is not None and now - hit[0] < self._ttl:
                out[lei] = hit[1]
            else:
                todo.append(lei)
        for start in range(0, len(todo), BATCH_SIZE):
            batch = todo[start:start + BATCH_SIZE]
            query = urllib.parse.urlencode({"filter[lei]": ",".join(batch),
                                            "page[size]": str(BATCH_SIZE)})
            found = parse_records(self._fetch(f"{self._base_url}?{query}"))
            for lei in batch:
                record = found.get(lei)
                self._cache[lei] = (now, record)
                out[lei] = record
        return out


# ---------------------------------------------------------------------------- register checks


@dataclass(frozen=True)
class _Subject:
    record: RoIRecord
    attr: str
    lei: str
    name_attr: str | None = None
    country_attr: str | None = None
    hq: bool = False  # compare with the headquarters (providers) instead of the legal address


def _subjects(register: RegisterOfInformation) -> Iterator[_Subject]:
    m = register.maintainer
    if m is not None and m.lei:
        yield _Subject(m, "lei", m.lei, "name", "country")
    for e in register.b_01_02:
        if e.lei:
            yield _Subject(e, "lei", e.lei, "name", "country")
        if e.parent_lei:
            yield _Subject(e, "parent_lei", e.parent_lei)
    for p in register.b_05_01:
        if p.provider_code and p.provider_code_type and p.provider_code_type.value == "LEI":
            yield _Subject(p, "provider_code", p.provider_code, "legal_name", "hq_country", hq=True)
        if (p.ultimate_parent_code and p.ultimate_parent_code_type
                and p.ultimate_parent_code_type.value == "LEI"):
            yield _Subject(p, "ultimate_parent_code", p.ultimate_parent_code)


def register_leis(register: RegisterOfInformation) -> set[str]:
    """The LEIs :func:`gleif_findings` checks (syntactically valid ones only)."""
    return {s.lei.upper() for s in _subjects(register) if is_valid_lei(s.lei.upper())}


def _norm(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", plain).split())


def gleif_findings(register: RegisterOfInformation,
                   records: dict[str, LeiRecord | None]) -> list[Finding]:
    """Findings for the register's LEIs, given the looked-up ``records``.

    LEIs not in ``records`` (not looked up, e.g. added after the check) are skipped.
    """
    ctx = ValidationContext(register, ValidationConfig())
    out: list[Finding] = []
    for s in _subjects(register):
        lei = s.lei.upper()
        if lei not in records:
            continue
        rec = records[lei]
        if rec is None:
            out.append(ctx.finding("GLEIF-001", f"LEI {lei} is not in the GLEIF Global LEI Index",
                                   s.record, s.attr, value=lei))
            continue
        if not rec.in_good_standing:
            detail = [f"registration {rec.registration_status or 'unknown'}"]
            if rec.entity_status not in (None, "ACTIVE"):
                detail.append(f"entity {rec.entity_status}")
            if rec.registration_status == "LAPSED" and rec.next_renewal:
                detail.append(f"renewal was due {rec.next_renewal.isoformat()}")
            if rec.successor_lei:
                detail.append(f"successor {rec.successor_lei}")
            out.append(ctx.finding("GLEIF-002", f"LEI {lei} ({rec.legal_name}) is not in good "
                                   f"standing: {', '.join(detail)}", s.record, s.attr, value=lei))
        name = getattr(s.record, s.name_attr) if s.name_attr else None
        if name and rec.legal_name:
            known = {_norm(n) for n in (rec.legal_name, *rec.other_names)}
            if _norm(name) not in known:
                out.append(ctx.finding("GLEIF-003", f"'{name}' differs from the GLEIF legal name "
                                       f"'{rec.legal_name}' of LEI {lei}", s.record, s.name_attr,
                                       value=name))
        country = getattr(s.record, s.country_attr) if s.country_attr else None
        expected = rec.hq_country if s.hq else rec.legal_country
        if country and expected and str(country).upper() != expected.upper():
            where = "headquarters" if s.hq else "legal address"
            out.append(ctx.finding("GLEIF-004", f"Country {country} differs from the GLEIF "
                                   f"{where} country {expected} of LEI {lei}", s.record,
                                   s.country_attr, value=str(country)))
    return out


def check_register(register: RegisterOfInformation,
                   client: GleifClient | None = None) -> tuple[dict[str, LeiRecord | None],
                                                           list[Finding]]:
    """Look the register's LEIs up and return the records and the findings."""
    records = (client or GleifClient()).lookup(register_leis(register))
    return records, gleif_findings(register, records)
