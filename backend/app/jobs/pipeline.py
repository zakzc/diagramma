"""Pipeline run inside a worker process. Emits stage events onto a queue."""

from datetime import UTC, datetime
from typing import Any

from app import __version__
from app.analysis.build import build_model
from app.analysis.fetch import RepoSpec, clone_repo
from app.analysis.scan import scan_repo
from app.errors import AppError
from app.models import DiagramRecord
from app.render.c4 import RenderMeta, render_c4
from app.render.flowchart import render_flowchart
from app.render.view import auto_depth, max_depth


def run_pipeline(spec: RepoSpec, queue: Any) -> dict[str, Any]:
    def stage(name: str, message: str) -> None:
        queue.put({"event": "stage", "data": {"stage": name, "message": message}})

    stage("cloning", f"Cloning {spec.slug}" + (f" @ {spec.ref}" if spec.ref else ""))
    repo = clone_repo(spec)

    stage("scanning", f"Scanning files at {repo.commit_sha[:7]}")
    scan = scan_repo(repo.path)
    if not scan.files and not scan.manifests:
        raise AppError(
            "NOTHING_DETECTED", "No source files or manifests were found in this repository."
        )

    stage("detecting", "Detecting containers, components and relations")
    model = build_model(repo.path, scan, spec.name)

    stage("rendering", "Rendering Mermaid")
    meta = RenderMeta(spec.slug, spec.ref, repo.commit_sha, repo.commit_date, __version__)
    depth = auto_depth(model)
    record = DiagramRecord(
        repo_url=f"https://github.com/{spec.slug}",
        owner=spec.owner,
        name=spec.name,
        ref=spec.ref,
        commit_sha=repo.commit_sha,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        container_count=len(model.containers),
        component_count=sum(len(c.components) for c in model.containers),
        commit_date=repo.commit_date,
        max_depth=max_depth(model),
        auto_depth=depth,
        mermaid_c4=render_c4(model, meta, depth),
        mermaid_flowchart=render_flowchart(model, meta, depth),
        model=model,
        warnings=model.warnings,
        tool_version=__version__,
    )
    return {
        "diagram": record.model_dump(),  # persisted by the API process, then replaced by diagramId
        "diagramId": None,
        "repo": spec.slug,
        "ref": spec.ref,
        "commit": repo.commit_sha,
        "files": len(scan.files),
        "languages": scan.language_counts(),
        "manifests": scan.manifests,
        "containers": record.container_count,
        "max_depth": record.max_depth,
        "components": record.component_count,
        "warnings": model.warnings,
    }
