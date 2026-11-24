import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from sse_starlette.sse import EventSourceResponse

from app import __version__
from app.analysis.details import node_details
from app.analysis.fetch import parse_repo_url, resolve_commit
from app.analysis.local import list_dirs, parse_local_path
from app.errors import AppError
from app.models import (
    DiagramCreate,
    DiagramCreated,
    DiagramRecord,
    DiagramSummary,
    DiagramView,
    DirListing,
    EditBody,
    ErrorResponse,
    Health,
    ImportsSummary,
    LayersSummary,
    NodeDetails,
    ViewFormat,
)
from app.render.c4 import RenderMeta, render_c4
from app.render.flowchart import drawn_relations, render_flowchart
from app.render.imports import analyze_imports, render_imports
from app.render.layers import analyze_layers, render_layers
from app.render.view import build_view

router = APIRouter(prefix="/api")


@router.get("/health", response_model=Health)
def health() -> Health:
    return Health(version=__version__)


@router.post(
    "/diagrams",
    response_model=DiagramCreated,
    responses={400: {"model": ErrorResponse}},
)
async def create_diagram(body: DiagramCreate, request: Request) -> DiagramCreated:
    if body.path is not None:
        if body.url is not None:
            raise AppError("INVALID_PATH", "Give either a GitHub URL or a folder path, not both.")
        # A folder has no cheap commit to compare: the job fingerprints it and the store reuses
        # the entry (SPEC §5.6).
        return DiagramCreated(jobId=request.app.state.jobs.submit(parse_local_path(body.path)).id)
    if body.url is None:
        raise AppError("VALIDATION_ERROR", "Invalid request body.")
    spec = parse_repo_url(body.url, body.ref)  # raises INVALID_URL
    store = request.app.state.store
    repo_url = spec.repo_url
    # Same repo + ref at the same commit (and tool version): reuse without cloning (SPEC §4.2).
    if store.has_repo(repo_url, spec.ref):
        commit = await run_in_threadpool(resolve_commit, spec)
        existing = store.find(repo_url, spec.ref, commit) if commit else None
        if existing is not None and existing.tool_version == __version__:
            return DiagramCreated(diagramId=existing.id)
    job = request.app.state.jobs.submit(spec)
    return DiagramCreated(jobId=job.id)


@router.get(
    "/fs/dirs",
    response_model=DirListing,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def fs_dirs(path: str | None = None, hidden: bool = False) -> DirListing:
    """Sub-directories of `path` (default: the home folder), for the folder browser."""
    return list_dirs(path, hidden)


@router.get("/jobs/{job_id}/events", responses={404: {"model": ErrorResponse}})
async def job_events(job_id: str, request: Request) -> EventSourceResponse:
    job = request.app.state.jobs.get(job_id)  # raises JOB_NOT_FOUND

    async def stream() -> AsyncIterator[dict[str, str]]:
        sent = 0
        while True:
            while sent < len(job.events):
                ev = job.events[sent]
                sent += 1
                yield {"event": ev["event"], "data": json.dumps(ev["data"])}
            if job.finished and sent >= len(job.events):
                return
            await asyncio.sleep(0.05)

    return EventSourceResponse(stream())


@router.get("/diagrams", response_model=list[DiagramSummary])
def list_diagrams(request: Request) -> list[DiagramSummary]:
    return request.app.state.store.list()


@router.get(
    "/diagrams/{diagram_id}",
    response_model=DiagramRecord,
    responses={404: {"model": ErrorResponse}},
)
def get_diagram(diagram_id: str, request: Request) -> DiagramRecord:
    return request.app.state.store.get(diagram_id)


@router.get(
    "/diagrams/{diagram_id}/nodes/{node_id}",
    response_model=NodeDetails,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def get_node(
    diagram_id: str, node_id: str, request: Request, depth: int | None = None
) -> NodeDetails:
    """Details of one box. `depth` is the viewed depth (default: the diagram's own)."""
    rec = request.app.state.store.get(diagram_id)
    d = rec.auto_depth if depth is None else depth
    if not 1 <= d <= rec.max_depth:
        raise AppError("INVALID_DEPTH", f"Depth must be between 1 and {rec.max_depth}.")
    return node_details(rec.model, node_id, d)


@router.delete("/diagrams/{diagram_id}", status_code=204, responses={404: {"model": ErrorResponse}})
def delete_diagram(diagram_id: str, request: Request) -> Response:
    request.app.state.store.delete(diagram_id)
    return Response(status_code=204)


Format = ViewFormat


@dataclass
class Generated:
    text: str
    nodes: int  # boxes drawn
    edges: int  # edges drawn
    hubs: int = 0  # shared modules marked instead of wired (flowchart)
    layers: LayersSummary | None = None  # dependency graph only
    imports: ImportsSummary | None = None  # imports view only


def _generated(rec: DiagramRecord, fmt: Format, depth: int) -> Generated:
    """The Mermaid text of a format at a depth, with what it draws."""
    if not 1 <= depth <= rec.max_depth:
        raise AppError("INVALID_DEPTH", f"Depth must be between 1 and {rec.max_depth}.")
    meta = RenderMeta(
        f"{rec.owner}/{rec.name}", rec.ref, rec.commit_sha, rec.commit_date, rec.tool_version
    )
    if fmt == "layers":  # imports only, layered; see SPEC §9.3
        analysis = analyze_layers(rec.model, depth)
        text = render_layers(rec.model, meta, depth, analysis)
        s = analysis.summary
        return Generated(text, s.nodes, s.edges_drawn, layers=s)
    if fmt == "imports":  # one box per file of a React app; independent of depth, see SPEC §9.4
        ia = analyze_imports(rec.model)
        text = render_imports(rec.model, meta, ia)
        return Generated(
            text,
            ia.summary.files + ia.summary.externals,
            ia.summary.edges_drawn,
            ia.summary.hubs,
            imports=ia.summary,
        )
    view = build_view(rec.model, depth)
    if fmt == "flowchart":  # grouped edges, shared modules marked instead of wired
        edges, hubs = drawn_relations(view)
        return Generated(
            render_flowchart(rec.model, meta, depth), view.nodes, len(edges), len(hubs)
        )
    # C4 can only connect boxes: every edge
    return Generated(render_c4(rec.model, meta, depth), view.nodes, len(view.relations))


def _view(request: Request, diagram_id: str, fmt: Format, depth: int) -> DiagramView:
    store = request.app.state.store
    g = _generated(store.get(diagram_id), fmt, depth)
    return DiagramView(
        format=fmt,
        depth=depth,
        generated=g.text,
        edited=store.get_edit(diagram_id, fmt, depth),
        nodes=g.nodes,
        edges=g.edges,
        hubs=g.hubs,
        layers=g.layers,
        imports=g.imports,
    )


@router.get(
    "/diagrams/{diagram_id}/views/{format}/{depth}",
    response_model=DiagramView,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def get_view(diagram_id: str, format: Format, depth: int, request: Request) -> DiagramView:
    """The diagram as `format` rolled up to `depth` (1 = top-level components only)."""
    return _view(request, diagram_id, format, depth)


@router.put(
    "/diagrams/{diagram_id}/edits/{format}/{depth}",
    response_model=DiagramView,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def save_edit(
    diagram_id: str, format: Format, depth: int, body: EditBody, request: Request
) -> DiagramView:
    """Save the user's edited text for this view (text equal to the generated one clears it)."""
    store = request.app.state.store
    generated = _generated(store.get(diagram_id), format, depth).text
    store.set_edit(diagram_id, format, depth, None if body.text == generated else body.text)
    return _view(request, diagram_id, format, depth)


@router.delete(
    "/diagrams/{diagram_id}/edits/{format}/{depth}",
    response_model=DiagramView,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def discard_edit(diagram_id: str, format: Format, depth: int, request: Request) -> DiagramView:
    """Reset: discard the saved edit; the generated text is shown again."""
    store = request.app.state.store
    _generated(store.get(diagram_id), format, depth)  # validates the depth
    store.set_edit(diagram_id, format, depth, None)
    return _view(request, diagram_id, format, depth)
