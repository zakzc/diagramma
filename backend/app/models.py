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
    weight: int = 0  # file count / LOC
    evidence: list[str] = Field(default_factory=list)


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


class Model(Base):
    system_name: str
    containers: list[Container] = Field(default_factory=list)
    externals: list[External] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
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
    edited_c4: str | None = None  # user's saved edit (milestone 6); None = no edit
    edited_flowchart: str | None = None
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
