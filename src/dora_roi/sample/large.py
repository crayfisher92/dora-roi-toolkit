"""A large synthetic register for performance testing (default 10 000 contracts, 1 000 providers).

It reuses the Alpenrand entities, functions and hand-written catalogue and adds generated
providers – grouped under ultimate parents, some hosted on the fictional hyperscalers – and
generated offerings until the requested number of contractual arrangements is reached. The
output is deterministic for a given seed and valid (no injected errors), so validation
timings reflect the rule engine rather than error formatting.
"""

from __future__ import annotations

import random
from dataclasses import replace

from dora_roi.io.parse import parse_raw
from dora_roi.model import ContractType, IctServiceType, RegisterOfInformation, Substitutability
from dora_roi.sample.catalogue import Catalogue, OfferingSpec, ProviderSpec
from dora_roi.sample.generator import (
    DEFAULT_REFERENCE_DATE,
    DEFAULT_SEED,
    SampleResult,
    _add_contract,
    _build_contracts,
    _build_entities,
    _build_providers,
    _Ctx,
    _finalise_providers,
    register_to_raw,
)

_COUNTRIES = ("DE", "DE", "DE", "AT", "LU", "FR", "NL", "IE", "BE", "IT", "ES", "PL", "SE",
              "FI", "DK", "CZ", "CH", "CH", "GB", "US", "US", "IN")
_SUFFIX = {"DE": "GmbH", "AT": "GmbH", "CH": "AG", "LU": "S.A.", "FR": "SAS", "BE": "SA",
           "NL": "B.V.", "IE": "Ltd", "GB": "Ltd", "US": "Inc.", "IT": "S.r.l.", "ES": "S.L.",
           "PL": "Sp. z o.o.", "SE": "AB", "FI": "Oy", "DK": "A/S", "CZ": "s.r.o.",
           "IN": "Pvt Ltd"}
_WORDS = ("Alpha", "Nordic", "Lumen", "Vertex", "Quanta", "Helix", "Orbit", "Pioneer",
          "Granite", "Summit", "Atlas", "Beacon", "Cobalt", "Delta", "Ember", "Fjord", "Harbor",
          "Iris", "Juniper", "Kestrel", "Meridian", "Nova", "Onyx", "Pulse", "Quarry", "Rhine",
          "Sigma", "Tundra", "Umbra", "Vista", "Willow", "Zephyr")
_TRADES = ("Data", "Systems", "Software", "Networks", "Analytics", "Solutions", "Digital",
           "Secure", "Cloud", "Tech", "Consulting", "Services")
_HOSTS = ("nimbus_eu", "stratus_eu", "cirrus_eu")


def _providers(rng: random.Random, count: int) -> tuple[ProviderSpec, ...]:
    """``count`` generated providers; about one in five belongs to a generated group."""
    out: list[ProviderSpec] = []
    parents: list[str] = []
    seen: set[str] = set()
    i = 0
    while len(out) < count:
        i += 1
        country = rng.choice(_COUNTRIES)
        name = f"{rng.choice(_WORDS)} {rng.choice(_TRADES)} {i:04d} {_SUFFIX[country]}"
        if name in seen:  # pragma: no cover - the running number makes names unique
            continue
        seen.add(name)
        key = f"gen{i:04d}"
        parent = rng.choice(parents) if parents and rng.random() < 0.2 else None
        out.append(ProviderSpec(key, name, country, parent=parent))
        if parent is None and rng.random() < 0.15:
            parents.append(key)
    return tuple(out)


def _offerings(rng: random.Random, cat: Catalogue,
               providers: tuple[ProviderSpec, ...]) -> tuple[OfferingSpec, ...]:
    capabilities = sorted({fn.capability for fns in cat.functions.values() for fn in fns})
    services = [s for s in IctServiceType if s not in (IctServiceType.S17,)]
    subst = list(Substitutability)
    out: list[OfferingSpec] = []
    for spec in providers:
        low = rng.randint(10, 400) * 1000
        hosted = rng.choice(_HOSTS) if rng.random() < 0.3 else None
        out.append(OfferingSpec(
            spec.key, rng.choice(services),
            tuple(rng.sample(capabilities, rng.randint(1, 3))), (low, low * 2),
            rng.choice(subst), data=rng.random() < 0.7, hosted_on=hosted,
            rank3="cirrus_us" if hosted and rng.random() < 0.1 else None))
    return tuple(out)


def generate_large(contracts: int = 10_000, providers: int = 1_000,
                   seed: int = DEFAULT_SEED) -> SampleResult:
    """A valid register with about ``contracts`` arrangements and ``providers`` providers."""
    # bandit B311: synthetic data, not security
    rng = random.Random(seed)  # nosec B311
    base = Catalogue()
    extra = _providers(rng, max(0, providers - len(base.providers)))
    cat = replace(base, providers=base.providers + extra,
                  offerings=base.offerings + _offerings(rng, base, extra))
    ctx = _Ctx(rng=rng, ref=DEFAULT_REFERENCE_DATE, cat=cat)
    _build_entities(ctx)
    _build_providers(ctx)
    _build_contracts(ctx)  # the hand-written catalogue (and one round of generated offerings)
    entities = list(cat.entities)
    offerings = list(cat.offerings[len(base.offerings):]) or list(cat.offerings)
    while len(ctx.reg.b_02_01) < contracts:
        offering = rng.choice(offerings)
        entity = rng.choice(entities)
        fns = [ctx.functions[(entity.key, cap)] for cap in offering.capabilities
               if (entity.key, cap) in ctx.functions]
        if fns:
            _add_contract(ctx, offering, entity, fns, ContractType.STANDALONE)
    _finalise_providers(ctx)
    parsed = parse_raw(register_to_raw(ctx.reg, "large-sample"))
    return SampleResult(ctx.reg, parsed.register, parsed.findings, [], DEFAULT_REFERENCE_DATE)


def large_register(contracts: int = 10_000, providers: int = 1_000,
                   seed: int = DEFAULT_SEED) -> RegisterOfInformation:
    return generate_large(contracts, providers, seed).register
