"""Flowchart fallback (SPEC §9.2): renders in almost any Mermaid viewer."""

from app.models import Component, Container, External, Model
from app.render.c4 import RenderMeta, header
from app.render.escape import label

CLASSDEFS = [
    "    classDef component fill:#85BBF0,stroke:#5D82A8,color:#000",
    "    classDef container fill:#438DD5,stroke:#2E6295,color:#fff",
    "    classDef store fill:#85BBF0,stroke:#5D82A8,color:#000",
    "    classDef external fill:#999999,stroke:#6B6B6B,color:#fff",
]


def _text(*lines: str | None) -> str:
    return "<br/>".join(label(x) for x in lines if x)


def _component(c: Component) -> str:
    tech = f"[Component: {c.technology}]" if c.technology else "[Component]"
    return f'        {c.id}["{_text(c.name, tech, c.description)}"]'


def _container_node(c: Container) -> str:
    return f'    {c.id}["{_text(c.name, f"[Container: {c.technology}]", c.description)}"]'


def _external(e: External) -> str:
    text = _text(e.name, f"[{e.technology}]" if e.technology else None)
    if e.kind == "database":
        return f'    {e.id}[("{text}")]'
    if e.kind == "queue":
        return f'    {e.id}(["{text}"])'
    return f'    {e.id}["{text}"]'


def render_flowchart(model: Model, meta: RenderMeta) -> str:
    lines = ["flowchart LR", *header(meta), *CLASSDEFS, ""]
    comps: list[str] = []
    containers: list[str] = []
    for c in sorted(model.containers, key=lambda c: c.id):
        if c.components:
            lines.append(f'    subgraph {c.id}["{_text(c.name, f"[{c.technology}]")}"]')
            lines.append("        direction TB")
            for k in sorted(c.components, key=lambda k: k.id):
                lines.append(_component(k))
                comps.append(k.id)
            lines.append("    end")
            lines.append(f"    style {c.id} fill:none,stroke:#444444,stroke-dasharray:5 5")
        else:
            lines.append(_container_node(c))
            containers.append(c.id)
    exts = sorted(model.externals, key=lambda e: e.id)
    if exts:
        lines.append("")
        lines += [_external(e) for e in exts]
    if model.relations:
        lines.append("")
        for r in sorted(model.relations, key=lambda r: (r.source, r.target)):
            text = _text(r.label, f"[{r.technology}]" if r.technology else None)
            lines.append(f'    {r.source} -->|"{text}"| {r.target}')
    lines.append("")
    for cls, ids in (
        ("component", comps),
        ("container", containers),
        ("store", [e.id for e in exts if e.kind != "system"]),
        ("external", [e.id for e in exts if e.kind == "system"]),
    ):
        if ids:
            lines.append(f"    class {','.join(ids)} {cls}")
    return "\n".join(lines) + "\n"
