import asyncio
import json
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from sse_starlette.sse import EventSourceResponse

from app import __version__
from app.analysis.fetch import parse_repo_url, resolve_commit
from app.models import (
    DiagramCreate,
    DiagramCreated,
    DiagramRecord,
    DiagramSummary,
    EditBody,
    ErrorResponse,
    Health,
)

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


@router.put(
    "/diagrams/{diagram_id}/edits/{format}",
    response_model=DiagramRecord,
    responses={404: {"model": ErrorResponse}},
)
def save_edit(
    diagram_id: str, format: Literal["c4", "flowchart"], body: EditBody, request: Request
) -> DiagramRecord:
    """Save the user's edited Mermaid text (text equal to the generated one clears the edit)."""
    return request.app.state.store.set_edit(diagram_id, format, body.text)


@router.delete(
    "/diagrams/{diagram_id}/edits/{format}",
    response_model=DiagramRecord,
    responses={404: {"model": ErrorResponse}},
)
def discard_edit(
    diagram_id: str, format: Literal["c4", "flowchart"], request: Request
) -> DiagramRecord:
    """Reset: discard the saved edit; the generated text is shown again."""
    return request.app.state.store.set_edit(diagram_id, format, None)
