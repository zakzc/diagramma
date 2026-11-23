"""Imports view (SPEC §9.4): a `flowchart LR` of the files of a React app, one box per file,
coloured and shaped by what the file is, with an edge from every importer to what it imports.

Databases, third-party services and API-client packages (axios, react-query, ...) are drawn as
external boxes. Files imported by a large share of the app are drawn once, marked, instead of
with every incoming edge. Deterministic.
"""

import posixpath
from dataclasses import dataclass

from app.analysis.filekind import API_PACKAGES, REACT_PACKAGES
from app.errors import AppError
from app.models import ImportsSummary, LegendItem, Model, Relation, SourceFile
from app.render.c4 import RenderMeta
from app.render.escape import label, make_id
from app.render.flowchart import _width
from app.render.view import find_hubs

# kind -> (legend label, fill, stroke, shape template). Order = legend order.
KINDS: dict[str, tuple[str, str, str, str]] = {
    "entry": ("Entry point", "#FFD9A8", "#C2640A", '(("@"))'),
    "page": ("Page / route", "#F6C9E2", "#B03A82", '[["@"]]'),
    "component": ("Component", "#C9DEFA", "#2F62B5", '["@"]'),
    "hook": ("Hook", "#CBEFD3", "#2C8A47", '(["@"])'),
    "state": ("State / context", "#E3D5F7", "#6F42B8", '{{"@"}}'),
    "api": ("API / service layer", "#FFF0A8", "#A68400", '[/"@"/]'),
    "db": ("Database access", "#FFC9C0", "#C0392B", '[("@")]'),
    "util": ("Util / lib", "#E5E7EB", "#6B7280", '["@"]'),
    "types": ("Types", "#F3F4F6", "#9CA3AF", '["@"]'),
    "config": ("Config / constants", "#D5E2E8", "#4F7384", '["@"]'),
    "ext_api": ("External API / client", "#FFE066", "#8A6D00", '[/"@"\\]'),
    "ext_db": ("External database", "#FF9E8F", "#9A2A1D", '[("@")]'),
}
EXT_KIND = {"database": "ext_db", "queue": "ext_api", "system": "ext_api"}


@dataclass
class ImportsAnalysis:
    nodes: dict[str, tuple[str, str]]  # node id -> (kind, display name)
    groups: dict[str, list[str]]  # group label -> file ids ("" = ungrouped)
    edges: dict[tuple[str, str], int]  # drawn edges
    hubs: dict[str, int]  # hub file id -> number of dependents
    summary: ImportsSummary


def _group_of(f: SourceFile, container_path: str, multi: str | None) -> str:
    rel = posixpath.relpath(f.path, container_path) if container_path != "." else f.path
    parts = rel.split("/")[:-1]
    if parts and parts[0] == "src":
        parts = parts[1:]
    g = parts[0] if parts else ""
    if multi:
        return f"{multi}/{g}" if g else multi
    return g


def analyze_imports(model: Model) -> ImportsAnalysis:
    if not model.files:
        raise AppError(
            "IMPORTS_UNAVAILABLE",
            "No React application found in this repository (JavaScript or TypeScript files that "
            "import react). If it was generated before this view existed, submit the repository "
            "again.",
        )
    files = {f.id: f for f in model.files}
    ext = {e.id: e for e in model.externals}
    cont = {c.id: c for c in model.containers}

    raw: dict[tuple[str, str], int] = {}  # file -> file | external | package node
    pkg_node: dict[str, str] = {}
    used = set(files) | set(ext)
    other_pkgs: set[str] = set()
    for f in model.files:
        for p in f.packages:
            if p in API_PACKAGES:
                node = pkg_node.setdefault(p, make_id(f"pkg_{p}", used))
                raw[(f.id, node)] = raw.get((f.id, node), 0) + 1
            elif p not in REACT_PACKAGES:
                other_pkgs.add(p)
    for i in model.file_imports:
        if i.source in files and (i.target in files or i.target in ext):
            raw[(i.source, i.target)] = raw.get((i.source, i.target), 0) + i.count

    rels = [Relation(source=s, target=t, label="Uses", strength=n) for (s, t), n in raw.items()]
    hubs = find_hubs(rels, set(files))
    hub_omitted = sum(1 for s, t in raw if t in hubs)
    edges = {k: v for k, v in raw.items() if k[1] not in hubs}
    linked = {x for e in raw for x in e}  # hubs stay drawn even though their edges are not
    linked |= set(hubs)

    nodes: dict[str, tuple[str, str]] = {}
    groups: dict[str, list[str]] = {}
    multi_containers = len({f.container for f in model.files}) > 1
    for fid in sorted(files):
        f = files[fid]
        if fid not in linked:
            continue
        nodes[fid] = (f.kind, f.name)
        c = cont.get(f.container)
        g = _group_of(f, c.path if c else ".", c.name if multi_containers and c else None)
        groups.setdefault(g, []).append(fid)
    n_files = len(nodes)
    for node in sorted({x for e in raw for x in e}):
        if node in ext:
            nodes[node] = (EXT_KIND[ext[node].kind], ext[node].name)
    for p, node in sorted(pkg_node.items()):
        nodes[node] = ("ext_api", p)

    counts: dict[str, int] = {}
    for kind, _ in nodes.values():
        counts[kind] = counts.get(kind, 0) + 1
    summary = ImportsSummary(
        files=n_files,
        externals=len(nodes) - n_files,
        edges_drawn=len(edges),
        hubs=len(hubs),
        hub_edges_omitted=hub_omitted,
        isolated=len(files) - n_files,
        packages_not_drawn=len(other_pkgs),
        legend=[
            LegendItem(kind=k, label=KINDS[k][0], color=KINDS[k][1], count=counts[k])
            for k in KINDS
            if k in counts
        ],
    )
    return ImportsAnalysis(nodes, groups, edges, hubs, summary)


def _node_line(nid: str, kind: str, name: str, hub: int | None) -> str:
    text = label(name, 40)
    if hub:
        text += f"<br/>used by {hub}"
    return f"{nid}{KINDS[kind][3].replace('@', text)}"


def render_imports(model: Model, meta: RenderMeta, analysis: ImportsAnalysis | None = None) -> str:
    a = analysis or analyze_imports(model)
    s = a.summary
    lines = [
        "flowchart LR",
        f"    %% Generated by Diagramma {meta.tool_version} - imports of a React app",
        f"    %% repo: {meta.repo} | ref: {meta.ref or 'HEAD'}",
        f"    %% commit: {meta.commit} | {meta.commit_date}",
        f"    %% {s.files} files, {s.externals} external, {s.edges_drawn} edges drawn; "
        f"{s.hubs} shared files marked ({s.hub_edges_omitted} edges not drawn); "
        f"{s.isolated} files with no import link; {s.packages_not_drawn} other npm packages",
        "    %% colours: " + ", ".join(f"{KINDS[i.kind][0]} {i.color}" for i in s.legend),
    ]
    for kind, (_, fill, stroke, _shape) in KINDS.items():
        lines.append(f"    classDef {kind} fill:{fill},stroke:{stroke},color:#111827")
    lines.append("    classDef hub stroke-width:3px,stroke-dasharray:5 3")
    lines.append("")

    used = set(a.nodes)
    for g in sorted(a.groups):
        ids = a.groups[g]
        if g:
            lines.append(f'    subgraph {make_id("grp_" + g, used)}["{label(g, 40)}"]')
        for fid in ids:
            kind, name = a.nodes[fid]
            lines.append(
                ("        " if g else "    ") + _node_line(fid, kind, name, a.hubs.get(fid))
            )
        if g:
            lines.append("    end")
    grouped = {x for ids in a.groups.values() for x in ids}
    for nid in sorted(a.nodes):
        if nid not in grouped:
            lines.append("    " + _node_line(nid, *a.nodes[nid], None))
    lines.append("")

    link_styles: list[str] = []
    for i, ((src, dst), w) in enumerate(sorted(a.edges.items())):
        lines.append(f'    {src} -->|"×{w}"| {dst}' if w > 1 else f"    {src} --> {dst}")
        if (width := _width(w)) is not None:
            link_styles.append(f"    linkStyle {i} stroke-width:{width}px")
    lines.append("")
    by_class: dict[str, list[str]] = {}
    for nid in sorted(a.nodes):
        by_class.setdefault(a.nodes[nid][0], []).append(nid)
    for kind in KINDS:
        if kind in by_class:
            lines.append(f"    class {','.join(by_class[kind])} {kind}")
    if a.hubs:
        lines.append(f"    class {','.join(sorted(a.hubs))} hub")
    lines += link_styles
    return "\n".join(lines) + "\n"
