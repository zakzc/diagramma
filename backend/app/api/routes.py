import asyncio
import json
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from sse_starlette.sse import EventSourceResponse

from app import __version__
from app.analysis.fetch import parse_repo_url, resolve_commit
from app.errors import AppError
from app.models import (
    DiagramCreate,
    DiagramCreated,
    DiagramRecord,
    DiagramSummary,
    DiagramView,
    EditBody,
    ErrorResponse,
    Health,
)
from app.render.c4 import RenderMeta, render_c4
from app.render.flowchart import drawn_relations, render_flowchart
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
    spec = parse_repo_url(body.url, body.ref)  # raises INVALID_URL
    store = request.app.state.store
    repo_url = f"https://github.com/{spec.slug}"
    # Same repo + ref at the same commit (and tool version): reuse without cloning (SPEC §4.2).
    if store.has_repo(repo_url, spec.ref):
        commit = await run_in_threadpool(resolve_commit, spec)
        existing = store.find(repo_url, spec.ref, commit) if commit else None
        if existing is not None and existing.tool_version == __version__:
            return DiagramCreated(diagramId=existing.id)
    job = request.app.state.jobs.submit(spec)
    return DiagramCreated(jobId=job.id)


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


@router.delete("/diagrams/{diagram_id}", status_code=204, responses={404: {"model": ErrorResponse}})
def delete_diagram(diagram_id: str, request: Request) -> Response:
    request.app.state.store.delete(diagram_id)
    return Response(status_code=204)


Format = Literal["c4", "flowchart"]


def _generated(rec: DiagramRecord, fmt: Format, depth: int) -> tuple[str, int, int, int]:
    """(Mermaid text, boxes, edges drawn, hubs marked) for a format at a depth."""
    if not 1 <= depth <= rec.max_depth:
        raise AppError("INVALID_DEPTH", f"Depth must be between 1 and {rec.max_depth}.")
    meta = RenderMeta(
        f"{rec.owner}/{rec.name}", rec.ref, rec.commit_sha, rec.commit_date, rec.tool_version
    )
    text = (render_c4 if fmt == "c4" else render_flowchart)(rec.model, meta, depth)
    view = build_view(rec.model, depth)
    if fmt == "flowchart":  # grouped edges, shared modules marked instead of wired
        edges, hubs = drawn_relations(view)
        return text, view.nodes, len(edges), len(hubs)
    return text, view.nodes, len(view.relations), 0  # C4 can only connect boxes: every edge


def _view(request: Request, diagram_id: str, fmt: Format, depth: int) -> DiagramView:
    store = request.app.state.store
    rec = store.get(diagram_id)
    text, nodes, edges, hubs = _generated(rec, fmt, depth)
    return DiagramView(
        format=fmt,
        depth=depth,
        generated=text,
        edited=store.get_edit(diagram_id, fmt, depth),
        nodes=nodes,
        edges=edges,
        hubs=hubs,
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
    generated = _generated(store.get(diagram_id), format, depth)[0]
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
