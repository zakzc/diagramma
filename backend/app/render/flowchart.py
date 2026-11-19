"""Flowchart output (SPEC §9.2): nested subgraphs, role colours, edge weight. Deterministic.

This is the better view for deep hierarchies: Mermaid's flowchart layout routes edges around
nested groups, and the text renders in virtually every Mermaid viewer.
"""

import math

from app.models import Component, External, Model, Relation
from app.render.c4 import RenderMeta, header
from app.render.escape import label
from app.render.view import View, ViewNode, auto_depth, build_view, find_hubs

# fill, stroke per component role; "store"/"external" for data stores and third parties.
ROLE_COLORS = {
    "controller": ("#FDE2C4", "#D9822B"),
    "service": ("#D6E4FF", "#4A6FD3"),
    "repository": ("#D3F0DA", "#3F9B5B"),
    "ui": ("#EBDDF8", "#8A55C2"),
    "model": ("#FFF3BF", "#B8960C"),
    "util": ("#E6E8EB", "#7B8794"),
    "config": ("#FAD7E3", "#C2477B"),
    "gateway": ("#CFF1F0", "#2E9C99"),
    "other": ("#FFFFFF", "#6B7280"),
    "store": ("#C7E3F7", "#2F7FB5"),
}


def _classdefs() -> list[str]:
    lines = [
        f"    classDef {role} fill:{fill},stroke:{stroke},color:#111827"
        for role, (fill, stroke) in ROLE_COLORS.items()
    ]
    lines.append("    classDef external fill:#9CA3AF,stroke:#6B7280,color:#FFFFFF")
    lines.append("    classDef container fill:#438DD5,stroke:#2E6295,color:#FFFFFF")
    # A hub keeps its role colour and gets a dashed, heavier border (merged with the role class).
    lines.append("    classDef hub stroke-width:3px,stroke-dasharray:5 3")
    return lines


def _text(*lines: str | None) -> str:
    return "<br/>".join(label(x) for x in lines if x)


def _used_by(hubs: dict[str, int], cid: str) -> str | None:
    return f"used by {hubs[cid]}" if cid in hubs else None


def _leaf(c: Component, indent: str, hubs: dict[str, int]) -> str:
    tech = f"[Component: {c.technology}]" if c.technology else "[Component]"
    if c.kind == "file":
        text = _text(c.name, tech, _used_by(hubs, c.id))  # files stay compact: there can be many
    else:
        files = f"{c.file_count} files" if c.file_count > 1 else None
        text = _text(
            c.name, tech, c.description if c.description != files else None, files,
            _used_by(hubs, c.id),
        )  # fmt: skip
    return f'{indent}{c.id}["{text}"]'


def _group(
    n: ViewNode, indent: str, out: list[str], by_class: dict[str, list[str]], hubs: dict[str, int]
) -> None:
    k = n.comp
    if not n.children:
        out.append(_leaf(k, indent, hubs))
        by_class.setdefault(k.role, []).append(k.id)
        if k.id in hubs:
            by_class.setdefault("hub", []).append(k.id)
        return
    title = _text(k.name, f"{k.file_count} files", _used_by(hubs, k.id))
    out.append(f'{indent}subgraph {k.id}["{title}"]')
    out.append(f"{indent}    direction LR")
    for ch in n.children:
        _group(ch, indent + "    ", out, by_class, hubs)
    out.append(f"{indent}end")


def _external(e: External) -> str:
    text = _text(e.name, f"[{e.technology}]" if e.technology else None)
    if e.kind == "database":
        return f'    {e.id}[("{text}")]'
    if e.kind == "queue":
        return f'    {e.id}(["{text}"])'
    return f'    {e.id}["{text}"]'


def _width(strength: int) -> int | None:
    """Heavier coupling, thicker line: 1 import = default, then +1px per doubling (max 7)."""
    return None if strength <= 1 else min(7, 2 + int(math.log2(strength)))


def drawn_relations(view: View) -> tuple[list[Relation], dict[str, int]]:
    """The edges the flowchart draws, and the hubs (id -> dependents) it marks instead of wiring."""
    grouped = view.grouped_relations
    hubs = find_hubs(grouped, {n.comp.id for n in _all_nodes(view)})
    return [r for r in grouped if r.target not in hubs], hubs


def render_flowchart(model: Model, meta: RenderMeta, depth: int | None = None) -> str:
    depth = depth or auto_depth(model)
    view = build_view(model, depth)
    relations, hubs = drawn_relations(view)
    lines = ["flowchart LR", *header(meta, depth), *_classdefs(), ""]
    if hubs:
        lines.insert(4, f"    %% shared modules, incoming edges not drawn: {', '.join(hubs)}")
    by_class: dict[str, list[str]] = {}
    container_nodes: list[str] = []

    for c, roots in view.containers:
        if roots:
            lines.append(f'    subgraph {c.id}["{_text(c.name, f"[{c.technology}]")}"]')
            lines.append("        direction LR")
            for n in roots:
                _group(n, "        ", lines, by_class, hubs)
            lines.append("    end")
            lines.append(
                f"    style {c.id} fill:none,stroke:#444444,stroke-width:2px,stroke-dasharray:6 4"
            )
        else:
            text = _text(c.name, f"[Container: {c.technology}]", c.description)
            lines.append(f'    {c.id}["{text}"]')
            container_nodes.append(c.id)

    exts = sorted(model.externals, key=lambda e: e.id)
    if exts:
        lines.append("")
        lines += [_external(e) for e in exts]

    link_styles: list[str] = []
    if relations:
        lines.append("")
        for i, r in enumerate(relations):
            # "Uses" is the default and says nothing: only informative labels are drawn.
            name = None if r.label == "Uses" else r.label
            count = f"×{r.strength}" if r.strength > 1 else None
            text = _text(name, count, f"[{r.technology}]" if r.technology else None)
            arrow = f'-->|"{text}"|' if text else "-->"
            lines.append(f"    {r.source} {arrow} {r.target}")
            if (w := _width(r.strength)) is not None:
                link_styles.append(f"    linkStyle {i} stroke-width:{w}px")
    lines.append("")
    for cls in [*ROLE_COLORS, "external", "container", "hub"]:
        if cls == "store":
            ids = [e.id for e in exts if e.kind != "system"]
        elif cls == "external":
            ids = [e.id for e in exts if e.kind == "system"]
        elif cls == "container":
            ids = container_nodes
        else:
            ids = by_class.get(cls, [])
        if ids:
            lines.append(f"    class {','.join(ids)} {cls}")
    lines += link_styles
    return "\n".join(lines) + "\n"


def _all_nodes(view):
    """Every node of the view tree (groups and boxes)."""
    stack = [n for _, roots in view.containers for n in roots]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(n.children)
