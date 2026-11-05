"""ICT dependency graph: direct providers and their subcontractors (B_05.02).

Nodes are providers; an edge ``A → B`` means *B is a subcontractor of A* in at least one
supply chain. Layout is a deterministic layered (Sugiyama-style) drawing: providers are placed
in columns by longest path from a direct provider, then ordered within a column by the
barycentre of their predecessors to reduce crossings. The SVG is rendered server-side; the
web page adds hover/focus highlighting with a few lines of JavaScript.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from html import escape

from markupsafe import Markup

from dora_roi.model import RegisterOfInformation
from dora_roi.model.refdata import country_name, region_of

NODE_W = 236
NODE_H = 28
COL_GAP = 110
ROW_GAP = 10
PAD = 16

REGION_VARS = {"EU": "--series-1", "Switzerland": "--series-2", "EEA (non-EU)": "--series-3",
               "Third country": "--series-4", "Unknown": "--series-muted"}


@dataclass
class Node:
    code: str
    name: str
    country: str | None
    region: str
    direct: bool = False
    critical: bool = False
    contracts: set[str] = field(default_factory=set)
    level: int = 0
    x: float = 0.0
    y: float = 0.0


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    contracts: int
    critical: bool


@dataclass
class Graph:
    nodes: dict[str, Node]
    edges: list[Edge]
    width: float = 0.0
    height: float = 0.0

    @property
    def levels(self) -> int:
        return 1 + max((n.level for n in self.nodes.values()), default=-1)


def build_graph(register: RegisterOfInformation, *, critical_only: bool = False,
                focus: str | None = None, with_isolated: bool = False) -> Graph:
    """Build and lay out the dependency graph."""
    providers = register.providers_by_code()
    critical_refs = {s.contract_ref for s in register.b_02_02 if register.supports_critical(s)}
    nodes: dict[str, Node] = {}

    def node(code: str) -> Node:
        if code not in nodes:
            p = providers.get(code)
            country = p.hq_country if p else None
            nodes[code] = Node(code, (p.legal_name if p and p.legal_name else code), country,
                               region_of(country))
        return nodes[code]

    for s in register.b_02_02:
        if not s.provider_code:
            continue
        crit = s.contract_ref in critical_refs
        if critical_only and not crit:
            continue
        n = node(s.provider_code)
        n.direct = True
        n.critical |= crit
        if s.contract_ref:
            n.contracts.add(s.contract_ref)
    edge_acc: dict[tuple[str, str], tuple[set[str], bool]] = {}
    for e in register.b_05_02:
        if not (e.provider_code and e.recipient_code and e.rank and e.rank > 1):
            continue
        crit = e.contract_ref in critical_refs
        if critical_only and not crit:
            continue
        sub = node(e.provider_code)
        node(e.recipient_code)
        sub.critical |= crit
        if e.contract_ref:
            sub.contracts.add(e.contract_ref)
        key = (e.recipient_code, e.provider_code)
        refs, was_crit = edge_acc.get(key, (set(), False))
        if e.contract_ref:
            refs.add(e.contract_ref)
        edge_acc[key] = (refs, was_crit or crit)
    edges = [Edge(a, b, len(refs), crit) for (a, b), (refs, crit) in sorted(edge_acc.items())
             if a != b]

    if not with_isolated and focus is None:
        linked = {e.source for e in edges} | {e.target for e in edges}
        nodes = {k: v for k, v in nodes.items() if k in linked}
    if focus is not None and focus in nodes:
        keep = _connected(focus, edges)
        nodes = {k: v for k, v in nodes.items() if k in keep}
        edges = [e for e in edges if e.source in keep and e.target in keep]
    graph = Graph(nodes, edges)
    _layout(graph)
    return graph


def _connected(start: str, edges: list[Edge]) -> set[str]:
    down: dict[str, set[str]] = defaultdict(set)
    up: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        down[e.source].add(e.target)
        up[e.target].add(e.source)
    seen = {start}
    for adj in (down, up):
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
    return seen


def _layout(graph: Graph) -> None:
    preds: dict[str, list[str]] = defaultdict(list)
    for e in graph.edges:
        preds[e.target].append(e.source)
    level: dict[str, int] = {}

    def longest(code: str, trail: frozenset[str]) -> int:
        if code in level:
            return level[code]
        parents = [p for p in preds.get(code, []) if p not in trail]
        value = 0 if not parents else 1 + max(longest(p, trail | {code}) for p in parents)
        level[code] = value
        return value

    for code in graph.nodes:
        graph.nodes[code].level = longest(code, frozenset())
    columns: dict[int, list[Node]] = defaultdict(list)
    for n in graph.nodes.values():
        columns[n.level].append(n)
    position: dict[str, float] = {}
    for lvl in sorted(columns):
        col = columns[lvl]
        if lvl == 0:
            col.sort(key=lambda n: (not n.critical, -len(n.contracts), n.name.casefold()))
        else:
            def bary(n: Node) -> float:
                ps = [position[p] for p in preds.get(n.code, []) if p in position]
                return sum(ps) / len(ps) if ps else 1e9

            col.sort(key=lambda n: (bary(n), n.name.casefold()))
        for i, n in enumerate(col):
            position[n.code] = i
            n.x = PAD + lvl * (NODE_W + COL_GAP)
            n.y = PAD + i * (NODE_H + ROW_GAP)
    tallest = max((len(c) for c in columns.values()), default=0)
    graph.width = PAD * 2 + max(graph.levels, 1) * NODE_W + max(graph.levels - 1, 0) * COL_GAP
    graph.height = PAD * 2 + tallest * (NODE_H + ROW_GAP)


def _truncate(text: str, limit: int = 29) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_svg(graph: Graph, *, color_by: str = "criticality", link_prefix: str = "",
               labels: dict[str, str] | None = None) -> Markup:
    """Render the graph as accessible inline SVG (nodes are focusable links)."""
    labels = labels or {}
    if not graph.nodes:
        # bandit B704: label escaped
        return Markup(  # nosec B704
            f'<p class="muted">{escape(labels.get("empty", "No providers."))}</p>')
    crit_text = labels.get("critical", "supports a critical function")
    parts = [
        f'<svg class="dep-graph" viewBox="0 0 {graph.width:.0f} {graph.height:.0f}" '
        f'width="{graph.width:.0f}" height="{graph.height:.0f}" role="group" '
        f'aria-label="{escape(labels.get("title", "Dependency graph"))}">',
        '<g class="edges" aria-hidden="true">',
    ]
    for e in graph.edges:
        a, b = graph.nodes[e.source], graph.nodes[e.target]
        x1, y1 = a.x + NODE_W, a.y + NODE_H / 2
        x2, y2 = b.x, b.y + NODE_H / 2
        if b.level <= a.level:  # should not happen with longest-path layering
            continue
        mid = (x1 + x2) / 2
        css = "edge critical" if e.critical else "edge"
        width = min(1 + e.contracts * 0.5, 4)
        parts.append(f'<path class="{css}" data-source="{escape(e.source)}" '
                     f'data-target="{escape(e.target)}" stroke-width="{width:.1f}" '
                     f'd="M{x1:.1f},{y1:.1f} C{mid:.1f},{y1:.1f} {mid:.1f},{y2:.1f} '
                     f'{x2:.1f},{y2:.1f}"/>')
    parts.append("</g><g class=\"nodes\">")
    for n in sorted(graph.nodes.values(), key=lambda n: (n.level, n.y)):
        var = (REGION_VARS.get(n.region, "--series-muted") if color_by == "region"
               else ("--series-1" if n.critical else "--series-muted"))
        desc = (f"{n.name} – {country_name(n.country)} ({n.region}); "
                f"{len(n.contracts)} arrangement(s)" + (f"; {crit_text}" if n.critical else ""))
        href = f"{link_prefix}{n.code}" if link_prefix else "#"
        weight = ' font-weight="650"' if n.critical else ""
        mark = "◆ " if n.critical else ""
        parts.append(
            f'<a class="node{" critical" if n.critical else ""}" href="{escape(href)}" '
            f'data-code="{escape(n.code)}" aria-label="{escape(desc)}">'
            f"<title>{escape(desc)}</title>"
            f'<rect x="{n.x:.1f}" y="{n.y:.1f}" width="{NODE_W}" height="{NODE_H}" rx="6" '
            f'style="stroke:var({var})"/>'
            f'<circle cx="{n.x + 12:.1f}" cy="{n.y + NODE_H / 2:.1f}" r="5" '
            f'style="fill:var({var})"/>'
            f'<text x="{n.x + 24:.1f}" y="{n.y + NODE_H / 2 + 4:.1f}"{weight}>'
            f"{escape(mark + _truncate(n.name))}</text></a>")
    parts.append("</g></svg>")
    # bandit B704: every interpolated value is escaped (tests: test_xss_*)
    return Markup("".join(parts))  # nosec B704


def chains_table(register: RegisterOfInformation, focus: str | None = None
                 ) -> list[tuple[str, list[str]]]:
    """Textual alternative: ``[(arrangement, [rank1 name, rank2 name, …])]``."""
    providers = register.providers_by_code()
    by_contract: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for e in register.b_05_02:
        if e.contract_ref and e.rank and e.provider_code:
            name = providers[e.provider_code].legal_name if e.provider_code in providers \
                and providers[e.provider_code].legal_name else e.provider_code
            by_contract[e.contract_ref].append((e.rank, name or e.provider_code))
    out: list[tuple[str, list[str]]] = []
    focus_name = (providers[focus].legal_name if focus and focus in providers else focus)
    for ref in sorted(by_contract):
        names = [n for _, n in sorted(by_contract[ref])]
        if len(names) < 2:
            continue
        if focus_name and focus_name not in names:
            continue
        out.append((ref, names))
    return out
