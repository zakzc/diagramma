"""Details of one box of a diagram, from the stored model (SPEC §9.5)."""

from collections.abc import Iterable

from app.errors import AppError
from app.models import Model, NodeDetails, NodeLink, Relation
from app.render.flowchart import drawn_relations
from app.render.view import build_view


def _links(rels: Iterable[Relation], node_id: str, names: dict[str, str]):
    def link(r: Relation, other: str) -> NodeLink:
        return NodeLink(
            id=other,
            name=names.get(other, other),
            strength=r.strength,
            label=r.label,
            evidence=list(r.evidence),
        )

    rels = list(rels)
    uses = [link(r, r.target) for r in rels if r.source == node_id]
    used_by = [link(r, r.source) for r in rels if r.target == node_id]
    key = lambda x: (-x.strength, x.name)  # noqa: E731
    return sorted(uses, key=key), sorted(used_by, key=key)


def node_details(model: Model, node_id: str, depth: int) -> NodeDetails:
    """`depth` is the depth of the view the user clicked in; it decides hub status only."""
    comps = {k.id: (c, k) for c in model.containers for k in c.components}
    conts = {c.id: c for c in model.containers}
    exts = {e.id: e for e in model.externals}
    files = {f.id: f for f in model.files}
    names = {
        **{i: k.name for i, (_, k) in comps.items()},
        **{i: c.name for i, c in conts.items()},
        **{i: e.name for i, e in exts.items()},
        **{i: f.name for i, f in files.items()},
    }

    if node_id in comps:
        c, k = comps[node_id]
        by_id = {x.id: x for x in c.components}
        trail: list[str] = []
        p = k.parent
        while p and p in by_id:
            trail.insert(0, by_id[p].name)
            p = by_id[p].parent
        # Relations at the node's own level: siblings and shallower boxes, whatever the view depth.
        uses, used_by = _links(build_view(model, k.depth).relations, node_id, names)
        hubs = drawn_relations(build_view(model, depth))[1]
        return NodeDetails(
            id=k.id, name=k.name, kind="component", role=k.role, technology=k.technology,
            description=k.description, container=c.name, trail=trail, paths=k.paths,
            weight=k.weight, file_count=k.file_count, evidence=k.evidence,
            children=[x.name for x in c.components if x.parent == k.id],
            is_hub=k.id in hubs, uses=uses, used_by=used_by,
        )  # fmt: skip

    if node_id in conts:
        c = conts[node_id]
        cof = {i: x.id for i, (x, _) in comps.items()}
        acc: dict[tuple[str, str], Relation] = {}
        for r in model.relations:
            s, t = cof.get(r.source, r.source), cof.get(r.target, r.target)
            if s == t or node_id not in (s, t):
                continue
            cur = acc.setdefault((s, t), Relation(source=s, target=t, label=r.label, strength=0))
            cur.strength += r.strength
            cur.evidence = sorted({*cur.evidence, *r.evidence})  # type: ignore[misc]
        uses, used_by = _links(acc.values(), node_id, names)
        return NodeDetails(
            id=c.id, name=c.name, kind="container", role=c.kind, technology=c.technology,
            description=c.description, paths=[c.path], evidence=c.evidence,
            weight=sum(k.weight for k in c.components if k.parent is None),
            file_count=sum(k.file_count for k in c.components if k.parent is None),
            children=[k.name for k in c.components if k.parent is None], uses=uses, used_by=used_by,
        )  # fmt: skip

    if node_id in exts:
        e = exts[node_id]
        uses, used_by = _links(build_view(model, 1).relations, node_id, names)
        return NodeDetails(
            id=e.id, name=e.name, kind="external", role=e.kind, technology=e.technology,
            evidence=e.evidence, uses=uses, used_by=used_by,
        )  # fmt: skip

    if node_id in files:
        f = files[node_id]
        rels = [
            Relation(source=i.source, target=i.target, label="Imports", strength=i.count)
            for i in model.file_imports
        ]
        uses, used_by = _links(rels, node_id, names)
        return NodeDetails(
            id=f.id, name=f.name, kind="file", role=f.kind, container=names.get(f.container),
            paths=[f.path], weight=f.loc, evidence=[f"imports {p}" for p in f.packages],
            uses=uses, used_by=used_by,
        )  # fmt: skip

    raise AppError("NODE_NOT_FOUND", "No such box in this diagram.")
