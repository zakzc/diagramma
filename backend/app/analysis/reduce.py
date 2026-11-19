"""Basic readability cap (SPEC §8): merge the smallest sibling components."""

from app.models import Component, Model, Relation
from app.render.escape import make_id

DEFAULT_CAP = 60


def reduce_components(model: Model, cap: int = DEFAULT_CAP) -> None:
    """Merge the smallest components of the busiest container into 'Other <container>'."""
    total = sum(len(c.components) for c in model.containers)
    if total <= cap:
        return
    used = {c.id for c in model.containers} | {e.id for e in model.externals}
    used |= {k.id for c in model.containers for k in c.components}
    remap: dict[str, str] = {}

    while total > cap:
        biggest = max(model.containers, key=lambda c: (len(c.components), c.id))
        if len(biggest.components) <= 1:
            model.warnings.append(
                f"{total} components remain after merging (cap {cap}); "
                "too many containers to reduce further."
            )
            break
        ordered = sorted(biggest.components, key=lambda k: (k.weight, k.id))
        take = ordered[: min(total - cap + 1, len(ordered))]
        taken = {k.id for k in take}
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
        )
        biggest.components = [k for k in biggest.components if k.id not in taken] + [merged]
        for k in take:
            remap[k.id] = merged.id
        model.warnings.append(
            f"Merged {len(take)} smallest components of '{biggest.name}' "
            f"into '{merged.name}' (cap {cap})."
        )
        total -= len(take) - 1

    # Re-point relations through (possibly chained) merges, then collapse duplicates.
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
            if cur.label != r.label:
                cur.label = "Uses"
    model.relations = sorted(acc.values(), key=lambda r: (r.source, r.target))
