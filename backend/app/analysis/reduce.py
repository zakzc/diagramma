"""Readability cap (SPEC §8): merge the smallest top-level components of a busy container."""

from app.models import Component, Container, Model, Relation
from app.render.escape import make_id

DEFAULT_CAP = 60


def _tops(c: Container) -> list[Component]:
    return [k for k in c.components if k.depth == 1]


def _subtree_ids(c: Container, root_ids: set[str]) -> set[str]:
    """`root_ids` and every component below them."""
    out = set(root_ids)
    grew = True
    while grew:
        grew = False
        for k in c.components:
            if k.parent in out and k.id not in out:
                out.add(k.id)
                grew = True
    return out


def reduce_components(model: Model, cap: int = DEFAULT_CAP) -> None:
    """Merge the smallest top-level components of the busiest container into 'Other <container>'.

    Only depth-1 components count towards the cap (deeper levels are chosen with the depth
    setting when viewing). A merged component absorbs its subtree.
    """
    total = sum(len(_tops(c)) for c in model.containers)
    if total <= cap:
        return
    used = {c.id for c in model.containers} | {e.id for e in model.externals}
    used |= {k.id for c in model.containers for k in c.components}
    remap: dict[str, str] = {}

    while total > cap:
        biggest = max(model.containers, key=lambda c: (len(_tops(c)), c.id))
        tops = _tops(biggest)
        if len(tops) <= 1:
            model.warnings.append(
                f"{total} components remain after merging (cap {cap}); "
                "too many containers to reduce further."
            )
            break
        ordered = sorted(tops, key=lambda k: (k.weight, k.id))
        take = ordered[: min(total - cap + 1, len(ordered))]
        gone = _subtree_ids(biggest, {k.id for k in take})
        merged = Component(
            id=make_id(f"{biggest.id}_other", used),
            name=f"Other {biggest.name}",
            role="other",
            technology=take[0].technology,
            paths=sorted({p for k in take for p in k.paths})[:10],
            description=f"{len(take)} smaller components merged",
            weight=sum(k.weight for k in take),
            evidence=[
                "merged: " + ", ".join(k.name for k in take[:8]) + ("…" if len(take) > 8 else "")
            ],
            file_count=sum(k.file_count for k in take),
        )
        biggest.components = [k for k in biggest.components if k.id not in gone] + [merged]
        for gid in gone:
            remap[gid] = merged.id
        model.warnings.append(
            f"Merged {len(take)} smallest components of '{biggest.name}' "
            f"into '{merged.name}' (cap {cap})."
        )
        total -= len(take) - 1

    def final(i: str) -> str:
        while i in remap:
            i = remap[i]
        return i

    acc: dict[tuple[str, str], Relation] = {}
    for r in model.relations:
        s, t = final(r.source), final(r.target)
        if s == t:
            continue
        cur = acc.get((s, t))
        if cur is None:
            acc[(s, t)] = r.model_copy(update={"source": s, "target": t})
        else:
            cur.strength += r.strength
            cur.evidence = sorted({*cur.evidence, *r.evidence})  # type: ignore[misc]
            if cur.label != r.label:
                cur.label = "Uses"
    model.relations = sorted(acc.values(), key=lambda r: (r.source, r.target))
