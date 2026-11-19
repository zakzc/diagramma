"""A model seen at a given depth: components rolled up to that level, relations re-pointed.

The model stores components as a tree and relations between the leaves. Showing depth `d` means
every leaf is represented by its ancestor at level `min(d, leaf level)`; groups above that level
are drawn as nested boundaries and everything below is hidden inside its ancestor.
"""

from dataclasses import dataclass, field

from app.models import Component, Container, Model, Relation

AUTO_CAP = 60  # default view: the deepest level that still shows at most this many components
HUB_MIN_USERS = 8  # a component is a hub when at least this many others depend on it ...
HUB_MIN_SHARE = 0.25  # ... and at least this share of all dependents does


@dataclass
class ViewNode:
    comp: Component
    children: list["ViewNode"] = field(default_factory=list)


@dataclass
class View:
    depth: int
    containers: list[tuple[Container, list[ViewNode]]]
    relations: list[Relation]  # between the drawn boxes (components, externals)

    @property
    def grouped_relations(self) -> list[Relation]:
        """`relations` with every edge that crosses a group boundary attached to the sibling
        groups instead of the individual boxes (a hierarchical-graph "edge bundle").

        Inside one group, edges stay between boxes. Between two groups of the same container,
        the edge runs between the two sibling groups just below their common parent. Across
        containers, and to external systems, it runs from the top-level component (level 1).
        Parallel edges merge, so a dozen file-to-file imports become one thick edge.
        """
        chains: dict[str, list[str]] = {}  # node id -> [container, level-1 group, ..., node]

        def walk(n: ViewNode, prefix: list[str]) -> None:
            chains[n.comp.id] = [*prefix, n.comp.id]
            for ch in n.children:
                walk(ch, chains[n.comp.id])

        for c, roots in self.containers:
            chains.setdefault(c.id, [c.id])
            for r in roots:
                walk(r, [c.id])

        def top(chain: list[str]) -> str:
            return chain[1] if len(chain) > 1 else chain[0]

        acc: dict[tuple[str, str], Relation] = {}
        for r in self.relations:
            cs, ct = chains.get(r.source, [r.source]), chains.get(r.target, [r.target])
            if cs[0] == ct[0] and len(cs) > 1 and len(ct) > 1:  # same container, both inside it
                i = next((k for k in range(1, min(len(cs), len(ct))) if cs[k] != ct[k]), None)
                if i is None:
                    continue
                s, t = cs[i], ct[i]
            else:
                s, t = top(cs), top(ct)
            if s == t:
                continue
            cur = acc.get((s, t))
            if cur is None:
                acc[(s, t)] = r.model_copy(update={"source": s, "target": t})
            else:
                cur.strength += r.strength
                if cur.label != r.label:
                    cur.label = "Uses"
                cur.technology = cur.technology or r.technology
                cur.evidence = sorted({*cur.evidence, *r.evidence})  # type: ignore[misc]
        return sorted(acc.values(), key=lambda r: (r.source, r.target))

    @property
    def nodes(self) -> int:
        """Components drawn as boxes (groups that are expanded are boundaries, not boxes)."""

        def count(n: ViewNode) -> int:
            return sum(count(c) for c in n.children) if n.children else 1

        return sum(count(n) for _, roots in self.containers for n in roots)


def max_depth(model: Model) -> int:
    return max((k.depth for c in model.containers for k in c.components), default=1)


def _visible_at(model: Model, depth: int) -> int:
    """Number of components shown at `depth` (those at that level plus shallower leaves)."""
    n = 0
    for c in model.containers:
        parents = {k.parent for k in c.components if k.parent}
        n += sum(
            1 for k in c.components if k.depth == depth or (k.depth < depth and k.id not in parents)
        )
    return n


def auto_depth(model: Model, cap: int = AUTO_CAP) -> int:
    """Deepest level whose diagram has at most `cap` components (at least 1)."""
    for d in range(max_depth(model), 0, -1):
        if _visible_at(model, d) <= cap:
            return d
    return 1


def build_view(model: Model, depth: int) -> View:
    reps: dict[str, str] = {}  # component id -> id of the component representing it
    containers: list[tuple[Container, list[ViewNode]]] = []

    for c in sorted(model.containers, key=lambda c: c.id):
        by_id = {k.id: k for k in c.components}
        kids: dict[str | None, list[Component]] = {}
        for k in c.components:
            kids.setdefault(k.parent, []).append(k)

        def build(k: Component, by_id=by_id, kids=kids) -> ViewNode:
            expand = k.depth < depth and k.id in kids
            return ViewNode(k, [build(x) for x in kids[k.id]] if expand else [])

        roots = [build(k) for k in kids.get(None, [])]
        containers.append((c, roots))

        for k in c.components:  # rep = ancestor-or-self at level min(depth, own level)
            cur = k
            while cur.depth > depth and cur.parent:
                cur = by_id[cur.parent]
            reps[k.id] = cur.id

    acc: dict[tuple[str, str], Relation] = {}
    for r in model.relations:
        s, t = reps.get(r.source, r.source), reps.get(r.target, r.target)
        if s == t:
            continue
        cur_rel = acc.get((s, t))
        if cur_rel is None:
            acc[(s, t)] = r.model_copy(update={"source": s, "target": t})
        else:
            cur_rel.strength += r.strength
            if cur_rel.label != r.label:
                cur_rel.label = "Uses"
            cur_rel.technology = cur_rel.technology or r.technology
            cur_rel.evidence = sorted({*cur_rel.evidence, *r.evidence})  # type: ignore[misc]
    relations = sorted(acc.values(), key=lambda r: (r.source, r.target))
    return View(depth, containers, relations)


def find_hubs(relations: list[Relation], candidates: set[str]) -> dict[str, int]:
    """Components that a large part of the diagram depends on, with their number of dependents.

    Drawing every incoming edge of such a "shared module" (utils, config, core) fills the diagram
    with long parallel lines and tells little. They are drawn once, marked, with a count instead.
    Only `candidates` (components, never databases or other external systems) can be hubs.
    """
    users: dict[str, set[str]] = {}
    for r in relations:
        if r.target in candidates:
            users.setdefault(r.target, set()).add(r.source)
    sources = {r.source for r in relations}
    need = max(HUB_MIN_USERS, -(-len(sources) * 25 // 100))  # ceil(25% of all dependents)
    return {k: len(v) for k, v in sorted(users.items()) if len(v) >= need}
