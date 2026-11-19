"""Layered dependency graph (SPEC §9.3): pure functions, no I/O, no Mermaid.

Input is a directed graph where an edge A -> B means "A imports B". The result puts every
node in a layer so that, apart from the *upward edges*, every dependency goes from a higher
layer to a strictly lower one (layer 0 depends on nothing).

Real code has import cycles (Django at package level is a single cycle holding most of its
packages), so cycles are *broken by ordering*, never collapsed into one node: nodes are put in
a linear order that keeps as many (weighted) edges pointing forward as a greedy heuristic can,
and the edges that point backwards are reported as upward edges.
"""

from collections import defaultdict
from dataclasses import dataclass, field

MAX_SPAN = 3  # forward edges spanning more layers than this are not drawn (counted instead)


@dataclass
class Layering:
    layer: dict[str, int]  # node -> layer (0 = depends on nothing)
    forward: dict[tuple[str, str], int]  # edges that go to a lower layer, with strength
    upward: dict[tuple[str, str], int]  # edges against the order (the cycle structure)
    reduced: dict[tuple[str, str], int] = field(default_factory=dict)  # forward, not implied
    drawn: dict[tuple[str, str], int] = field(default_factory=dict)  # reduced and short enough
    transitive_omitted: int = 0  # forward edges implied by another path
    long_omitted: int = 0  # reduced forward edges spanning more than max_span layers

    @property
    def layer_count(self) -> int:
        return max(self.layer.values(), default=-1) + 1

    def layer_sizes(self) -> list[int]:
        sizes = [0] * self.layer_count
        for n in self.layer.values():
            sizes[n] += 1
        return sizes


def order_nodes(nodes: list[str], edges: dict[tuple[str, str], int]) -> list[str]:
    """Linear order, dependents first, with few heavy edges pointing backwards.

    Greedy heuristic of Eades, Lin and Smyth: repeatedly move nodes nobody depends on to the
    front and nodes that depend on nothing to the back; when neither exists, move the node
    with the largest (outgoing minus incoming) weight to the front. Ties are broken by id so
    the result does not depend on input order.
    """
    out: dict[str, dict[str, int]] = defaultdict(dict)
    inn: dict[str, dict[str, int]] = defaultdict(dict)
    for (s, t), w in edges.items():
        out[s][t] = w
        inn[t][s] = w
    left = set(nodes)
    front: list[str] = []
    back: list[str] = []
    while left:
        moved = True
        while moved:
            moved = False
            for n in sorted(left):
                if not any(t in left for t in out[n]):  # depends on nothing that is left
                    left.discard(n)
                    back.append(n)
                    moved = True
                elif not any(s in left for s in inn[n]):  # nothing left depends on it
                    left.discard(n)
                    front.append(n)
                    moved = True
        if left:
            pick = max(
                sorted(left),
                key=lambda x: (
                    sum(w for t, w in out[x].items() if t in left)
                    - sum(w for s, w in inn[x].items() if s in left)
                ),
            )
            left.discard(pick)
            front.append(pick)
    return front + back[::-1]


def layer_graph(
    nodes: list[str], edges: dict[tuple[str, str], int], max_span: int = MAX_SPAN
) -> Layering:
    """Order, layer, transitively reduce and span-limit a dependency graph."""
    edges = {e: w for e, w in edges.items() if e[0] != e[1]}
    order = order_nodes(nodes, edges)
    pos = {n: i for i, n in enumerate(order)}
    forward = {e: w for e, w in edges.items() if pos[e[0]] < pos[e[1]]}
    upward = {e: w for e, w in edges.items() if pos[e[0]] > pos[e[1]]}

    deps: dict[str, list[str]] = defaultdict(list)
    for s, t in sorted(forward):
        deps[s].append(t)

    # Layers: dependencies come later in `order`, so walking it backwards sees them first.
    layer: dict[str, int] = {}
    for n in reversed(order):
        layer[n] = 1 + max((layer[d] for d in deps[n]), default=-1)

    # Transitive reduction: drop s -> t when another direct dependency of s already reaches t.
    reach: dict[str, set[str]] = {}
    for n in reversed(order):
        r: set[str] = set()
        for d in deps[n]:
            r.add(d)
            r |= reach[d]
        reach[n] = r
    reduced: dict[tuple[str, str], int] = {}
    for (s, t), w in forward.items():
        if any(t in reach[d] for d in deps[s] if d != t):
            continue
        reduced[(s, t)] = w
    drawn = {e: w for e, w in reduced.items() if layer[e[0]] - layer[e[1]] <= max_span}
    return Layering(
        layer=layer,
        forward=forward,
        upward=upward,
        reduced=reduced,
        drawn=drawn,
        transitive_omitted=len(forward) - len(reduced),
        long_omitted=len(reduced) - len(drawn),
    )
