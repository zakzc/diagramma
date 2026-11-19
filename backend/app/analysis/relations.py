"""Container-level relations (SPEC §8). Component-level imports arrive in milestone 4."""

from app.analysis.containers import Detected
from app.analysis.externals import ExternalResult
from app.analysis.graph import FileGraph
from app.models import Component, External, Relation

EXTERNAL_LABEL = {"database": "Reads/writes", "queue": "Publishes/consumes", "system": "Uses"}


def container_relations(detected: list[Detected], ext: ExternalResult) -> list[Relation]:
    kinds: dict[str, External] = {e.id: e for e in ext.externals}
    by_service = {d.compose_name: d.container.id for d in detected if d.compose_name}
    by_pkg = {d.info.name.lower(): d.container.id for d in detected if d.info and d.info.name}

    acc: dict[tuple[str, str], Relation] = {}

    def add(src: str, dst: str, label: str, tech: str | None) -> None:
        if src == dst:
            return
        r = acc.get((src, dst))
        if r is None:
            acc[(src, dst)] = Relation(source=src, target=dst, label=label, technology=tech or None)
        else:
            r.strength += 1

    for d in detected:
        cid = d.container.id
        # docker-compose depends_on
        for dep in d.compose.depends_on if d.compose else []:
            if dep in by_service:
                add(cid, by_service[dep], "Uses", None)
            elif dep in ext.by_service:
                e = kinds[ext.by_service[dep]]
                add(cid, e.id, EXTERNAL_LABEL[e.kind], ext.technology_by_id.get(e.id))
        # workspace siblings referenced as dependencies
        if d.info:
            for dep in sorted(d.info.all_deps):
                if (tgt := by_pkg.get(dep)) is not None:
                    add(cid, tgt, "Uses", None)

    for link in ext.links:
        e = kinds[link.external_id]
        add(link.container_id, e.id, EXTERNAL_LABEL[e.kind], ext.technology_by_id.get(e.id))

    return sorted(acc.values(), key=lambda r: (r.source, r.target))


# --- component level (milestone 4) ------------------------------------------------------------

ROLE_LABEL = {
    ("ui", "controller"): "Calls",
    ("ui", "gateway"): "Calls",
    ("service", "gateway"): "Calls",
    ("controller", "service"): "Uses",
    ("service", "repository"): "Reads/writes via",
    ("controller", "repository"): "Reads/writes via",
}
SOURCE_PREF = {
    "database": ["repository", "service", "model"],
    "queue": ["gateway", "service", "controller"],
    "system": ["gateway", "service", "controller"],
}
CONTAINER_SOURCE_PREF = ["gateway", "ui", "service", "controller"]
CONTAINER_TARGET_PREF = ["controller", "service"]


def role_label(src: Component, dst: Component) -> str:
    if dst.role == "config":
        return "Reads config from"
    if dst.role == "gateway":
        return "Calls"
    return ROLE_LABEL.get((src.role, dst.role), "Uses")


def _rep(det: Detected, prefer: list[str]) -> str:
    """Endpoint id standing in for a whole container (a component, else the container)."""
    comps = det.container.components
    if not comps:
        return det.container.id
    for role in prefer:
        hits = [c for c in comps if c.role == role]
        if hits:
            return max(hits, key=lambda c: (c.weight, c.id)).id
    return max(comps, key=lambda c: (c.weight, c.id)).id


def _core(det: Detected) -> str:
    comps = det.container.components
    core = [c for c in comps if c.evidence and c.evidence[0].startswith("files in ")]
    return core[0].id if core else _rep(det, [])


def component_relations(
    detected: list[Detected],
    ext: ExternalResult,
    graph: FileGraph,
    file_comp: dict[str, str],
    container_rels: list[Relation],
) -> list[Relation]:
    comps = {c.id: (c, d) for d in detected for c in d.container.components}
    by_container = {d.container.id: d for d in detected}
    kinds = {e.id: e for e in ext.externals}
    acc: dict[tuple[str, str], Relation] = {}
    ext_pairs: set[tuple[str, str]] = set()  # (container id, external id) with import evidence
    cont_pairs: set[tuple[str, str]] = set()

    def add(src: str, dst: str, label: str, tech: str | None, n: int = 1) -> None:
        if src == dst:
            return
        r = acc.get((src, dst))
        if r is None:
            acc[(src, dst)] = Relation(
                source=src, target=dst, label=label, technology=tech or None, strength=n
            )
        else:
            r.strength += n

    for (s, d), n in sorted(graph.files.items()):
        cs, cd = file_comp.get(s), file_comp.get(d)
        if not cs or not cd or cs == cd:
            continue
        (src, src_det), (dst, dst_det) = comps[cs], comps[cd]
        same = src_det.container.id == dst_det.container.id
        add(cs, cd, role_label(src, dst) if same else "Uses", None, n)
        if not same:
            cont_pairs.add((src_det.container.id, dst_det.container.id))

    for (s, target), n in sorted(graph.containers.items()):
        cs = file_comp.get(s)
        if cs is None or target not in by_container:
            continue
        src_cid = comps[cs][1].container.id
        add(cs, _core(by_container[target]), "Uses", None, n)
        cont_pairs.add((src_cid, target))

    for (s, eid), n in sorted(graph.externals.items()):
        cs = file_comp.get(s)
        if cs is None:
            continue
        e = kinds[eid]
        add(cs, eid, EXTERNAL_LABEL[e.kind], ext.technology_by_id.get(eid), n)
        ext_pairs.add((comps[cs][1].container.id, eid))

    # Container-level evidence (compose, manifests, env vars) not already backed by imports.
    for r in container_rels:
        src_det = by_container.get(r.source)
        if src_det is None:
            continue
        if r.target in kinds:
            if (r.source, r.target) in ext_pairs:
                continue
            prefs = SOURCE_PREF[kinds[r.target].kind]
            add(_rep(src_det, prefs), r.target, r.label, r.technology, r.strength)
        elif r.target in by_container and (r.source, r.target) not in cont_pairs:
            tgt = by_container[r.target]
            add(
                _rep(src_det, CONTAINER_SOURCE_PREF),
                _rep(tgt, CONTAINER_TARGET_PREF),
                r.label,
                r.technology,
                r.strength,
            )
    return sorted(acc.values(), key=lambda r: (r.source, r.target))
