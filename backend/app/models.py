"""Intermediate model (SPEC §7) and API schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Base(BaseModel):
    # Fields with defaults are always present in responses, so mark them required in OpenAPI.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Component(Base):
    id: str
    name: str
    role: Literal[
        "controller", "service", "repository", "ui", "model", "util", "config", "gateway", "other"
    ]
    technology: str | None = None
    paths: list[str] = Field(default_factory=list)
    description: str | None = None
    weight: int = 0  # lines of code (a group: the sum of its descendants)
    evidence: list[str] = Field(default_factory=list)
    # Components form a tree per container: groups contain folders/files; relations are drawn
    # between the leaves and rolled up to a chosen depth when rendering.
    parent: str | None = None
    depth: int = 1  # 1 = directly under the container
    kind: Literal["group", "folder", "file"] = "folder"
    file_count: int = 0  # source files in this component's subtree


class Container(Base):
    id: str
    name: str
    kind: Literal["webapp", "api", "service", "worker", "cli", "library", "other"]
    technology: str
    path: str
    description: str | None = None
    components: list[Component] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class External(Base):
    id: str
    name: str
    kind: Literal["system", "database", "queue"]
    technology: str | None = None
    evidence: list[str] = Field(default_factory=list)


class Relation(Base):
    source: str
    target: str
    label: str  # "Uses", "Reads/writes", "Calls", ...
    technology: str | None = None
    strength: int = 1  # number of underlying import edges
    # What the edge rests on. The Dependency graph uses only "import"; the others are weaker
    # container-level evidence. Merged edges carry the union. Empty = stored before this field.
    evidence: list[Literal["import", "compose", "manifest", "env"]] = Field(default_factory=list)


FileKind = Literal[
    "entry", "page", "component", "hook", "state", "api", "db", "util", "types", "config"
]


class SourceFile(Base):
    """A JS/TS source file of a React container, classified for the Imports view (SPEC §9.4)."""

    id: str
    path: str
    name: str  # display name: file name without extension (the folder for `index`)
    kind: FileKind
    container: str  # container id
    loc: int = 0
    packages: list[str] = Field(default_factory=list)  # bare npm packages it imports


class FileImport(Base):
    source: str  # file id
    target: str  # file id, or the id of an external system / database
    count: int = 1  # import statements


class Model(Base):
    system_name: str
    containers: list[Container] = Field(default_factory=list)
    externals: list[External] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    files: list[SourceFile] = Field(default_factory=list)  # React containers only; else empty
    file_imports: list[FileImport] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class DiagramCreate(BaseModel):
    url: str
    ref: str | None = None


class DiagramCreated(BaseModel):
    """Exactly one is set: a new job to follow, or an existing diagram to reuse."""

    jobId: str | None = None
    diagramId: str | None = None


ViewFormat = Literal["c4", "flowchart", "layers", "imports"]


class SavedEdit(Base):
    """Which views the user has saved an edit for (the text comes from the view endpoint)."""

    format: ViewFormat
    depth: int


class DiagramRecord(Base):
    """A generated diagram as stored in SQLite."""

    id: str = ""
    repo_url: str
    owner: str
    name: str
    ref: str | None = None
    commit_sha: str
    created_at: str
    container_count: int
    component_count: int
    mermaid_c4: str
    mermaid_flowchart: str | None = None
    commit_date: str = ""
    max_depth: int = 1  # deepest component level in the model
    auto_depth: int = 1  # depth the stored texts above were rendered at
    saved_edits: list["SavedEdit"] = Field(default_factory=list)
    model: Model
    warnings: list[str] = Field(default_factory=list)
    tool_version: str


class DiagramSummary(Base):
    """History list row: everything except the Mermaid texts and the model."""

    id: str
    repo_url: str
    owner: str
    name: str
    ref: str | None = None
    commit_sha: str
    created_at: str
    container_count: int
    component_count: int
    tool_version: str


MAX_EDIT_CHARS = 2_000_000


class EditBody(BaseModel):
    text: str = Field(max_length=MAX_EDIT_CHARS)


class UpwardEdge(Base):
    source: str  # display names
    target: str
    strength: int  # imports


class LayersSummary(Base):
    """What the Dependency graph shows and what it left out (SPEC §9.3)."""

    layer_count: int
    layer_sizes: list[int]  # nodes per layer, layer 0 first
    nodes: int
    edges_drawn: int
    edges_transitive_omitted: int  # implied by another path
    edges_long_omitted: int  # spanning more layers than the readability limit
    max_span: int  # that limit, in layers
    upward_edges: int  # imports against the layer order (the cycle structure)
    longest_chain: int  # = layer_count
    isolated: int  # components with no import link at this depth, not drawn
    top_upward: list[UpwardEdge]  # the strongest few


class LegendItem(Base):
    kind: str  # a FileKind, or "ext_api" / "ext_db" for external nodes
    label: str
    color: str  # fill colour, as drawn in the Mermaid text
    count: int  # nodes of this kind in the diagram


class ImportsSummary(Base):
    """What the Imports view shows and what it left out (SPEC §9.4)."""

    files: int  # file boxes drawn
    externals: int  # external boxes drawn (API clients and services, databases)
    edges_drawn: int
    hubs: int  # shared files drawn once, with a count, instead of with every incoming edge
    hub_edges_omitted: int
    isolated: int  # files with no import link, not drawn
    packages_not_drawn: int  # other npm packages (react, router, UI kits, ...)
    legend: list[LegendItem]


class DiagramView(Base):
    """One rendering of a diagram: a format at a depth, plus the user's saved edit if any."""

    format: ViewFormat
    depth: int
    generated: str
    edited: str | None = None
    nodes: int  # components visible at this depth
    edges: int  # relations drawn at this depth
    hubs: int = 0  # shared components drawn once instead of with all their incoming edges
    layers: LayersSummary | None = None  # only for the Dependency graph (format "layers")
    imports: ImportsSummary | None = None  # only for the Imports view (format "imports")
