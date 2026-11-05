"""ICT service supply chain (subcontracting) rules (SC-*), template B_05.02.

Interpretation (``docs/ASSUMPTIONS.md`` A-TPL-07): within one arrangement and service type the
direct provider is at rank 1 and has no recipient; a rank *n* > 1 subcontractor names, as its
recipient, a provider present at rank *n − 1* of the same chain.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from dora_roi.model import IctServiceType, SupplyChainEntry
from dora_roi.validation.context import ValidationContext
from dora_roi.validation.findings import Category, Finding, Severity, rule

REFS = ("DORA Art. 28(3)", "DORA Art. 29", "DORA Art. 30(2)", "ITS Annex II")

ChainKey = tuple[str | None, IctServiceType | None]


def chains(ctx: ValidationContext) -> dict[ChainKey, list[SupplyChainEntry]]:
    out: dict[ChainKey, list[SupplyChainEntry]] = defaultdict(list)
    for entry in ctx.register.b_05_02:
        out[(entry.contract_ref, entry.service_type)].append(entry)
    return dict(out)


@rule("SC-001", "Rank 1 provider is not the direct provider of the arrangement",
      severity=Severity.ERROR, category=Category.SUPPLY_CHAIN, templates=("B_05.02", "B_02.02"),
      references=REFS,
      description="The rank 1 entry of a supply chain must be the ICT third-party service "
      "provider that provides the service under the arrangement (as reported in B_02.02).")
def check_rank_one(ctx: ValidationContext) -> Iterator[Finding]:
    for entry in ctx.register.b_05_02:
        if entry.rank != 1 or entry.contract_ref not in ctx.services_by_contract:
            continue
        direct = ctx.providers_by_contract.get(entry.contract_ref or "", set())
        if entry.provider_code and entry.provider_code not in direct:
            yield ctx.finding("SC-001", f"Rank 1 provider '{entry.provider_code}' is not a "
                              f"direct provider of '{entry.contract_ref}' (expected one of: "
                              f"{', '.join(sorted(direct)) or '—'})", entry, "provider_code",
                              value=entry.provider_code)


@rule("SC-002", "Subcontractor without recipient", severity=Severity.ERROR,
      category=Category.SUPPLY_CHAIN, templates=("B_05.02",), references=REFS,
      description="Entries with rank greater than 1 must identify the recipient of the "
      "sub-contracted ICT services (c0060/c0070).")
def check_recipient_present(ctx: ValidationContext) -> Iterator[Finding]:
    for entry in ctx.register.b_05_02:
        if entry.rank is None or entry.rank <= 1 or "recipient_code" in entry.invalid_fields:
            continue
        if entry.recipient_code is None:
            yield ctx.finding("SC-002", f"Rank {entry.rank} subcontractor "
                              f"'{entry.provider_code}' has no recipient", entry,
                              "recipient_code")
        elif entry.recipient_code_type is None and \
                "recipient_code_type" not in entry.invalid_fields:
            yield ctx.finding("SC-002", "Type of code of the recipient is missing", entry,
                              "recipient_code_type")


@rule("SC-003", "Subcontracting chain does not resolve", severity=Severity.ERROR,
      category=Category.SUPPLY_CHAIN, templates=("B_05.02",), references=REFS,
      description="The recipient of a rank n subcontractor must appear as provider at rank n-1 of "
      "the same arrangement and service type; otherwise the chain is broken (missing link).")
def check_chain_resolves(ctx: ValidationContext) -> Iterator[Finding]:
    for (contract_ref, _service), entries in chains(ctx).items():
        by_rank: dict[int, set[str]] = defaultdict(set)
        for e in entries:
            if e.rank is not None and e.provider_code:
                by_rank[e.rank].add(e.provider_code)
        for e in entries:
            if e.rank is None or e.rank <= 1 or e.recipient_code is None:
                continue
            if e.recipient_code not in by_rank.get(e.rank - 1, set()):
                yield ctx.finding("SC-003", f"In '{contract_ref}', recipient '{e.recipient_code}' "
                                  f"of rank {e.rank} subcontractor '{e.provider_code}' is not "
                                  f"reported at rank {e.rank - 1}", e, "recipient_code",
                                  value=e.recipient_code)


@rule("SC-004", "Recipient reported for a rank 1 provider", severity=Severity.WARNING,
      category=Category.SUPPLY_CHAIN, templates=("B_05.02",), references=REFS,
      description="The direct provider (rank 1) has no recipient of sub-contracted services.")
def check_rank_one_recipient(ctx: ValidationContext) -> Iterator[Finding]:
    for e in ctx.register.b_05_02:
        if e.rank == 1 and e.recipient_code is not None:
            yield ctx.finding("SC-004", "Rank 1 entry should not report a recipient", e,
                              "recipient_code", value=e.recipient_code)


@rule("SC-005", "Circular subcontracting chain", severity=Severity.ERROR,
      category=Category.SUPPLY_CHAIN, templates=("B_05.02",), references=REFS,
      description="A provider cannot (directly or indirectly) subcontract to itself within the "
      "same chain.")
def check_cycles(ctx: ValidationContext) -> Iterator[Finding]:
    for (contract_ref, _service), entries in chains(ctx).items():
        edges: dict[str, set[str]] = defaultdict(set)  # recipient -> subcontractors
        for e in entries:
            if e.recipient_code and e.provider_code:
                edges[e.recipient_code].add(e.provider_code)
        reported: set[str] = set()
        for start in list(edges):
            stack = [(start, frozenset({start}))]
            while stack:
                node, path = stack.pop()
                for nxt in edges.get(node, ()):
                    if nxt in path:
                        if nxt not in reported:
                            reported.add(nxt)
                            entry = next(x for x in entries if x.provider_code == nxt)
                            yield ctx.finding("SC-005", f"Provider '{nxt}' appears in a "
                                              f"subcontracting cycle in '{contract_ref}'",
                                              entry, "provider_code", value=nxt)
                    else:
                        stack.append((nxt, path | {nxt}))


@rule("SC-006", "No supply chain reported for an ICT service supporting a critical function",
      severity=Severity.WARNING, category=Category.SUPPLY_CHAIN,
      templates=("B_05.02", "B_02.02", "B_06.01"), references=(*REFS, "DORA Art. 28(8)"),
      description="ICT services supporting critical or important functions are expected to have "
      "their supply chain (at least the rank 1 provider) reported in B_05.02.")
def check_critical_chain_present(ctx: ValidationContext) -> Iterator[Finding]:
    present = {(e.contract_ref, e.service_type) for e in ctx.register.b_05_02}
    seen: set[tuple[str | None, IctServiceType | None]] = set()
    for svc in ctx.critical_services:
        key = (svc.contract_ref, svc.service_type)
        if key in present or key in seen or svc.contract_ref is None:
            continue
        seen.add(key)
        yield ctx.finding("SC-006", f"'{svc.contract_ref}' "
                          f"({svc.service_type.value if svc.service_type else '—'}) supports "
                          f"critical function '{svc.function_id}' but has no B_05.02 entries",
                          svc, "contract_ref")
