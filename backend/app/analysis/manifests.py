"""Parse package manifests and docker-compose files (static only)."""

import json
import posixpath
import re
import tomllib
from dataclasses import dataclass, field
from typing import Any

import yaml


def norm_dep(name: str) -> str:
    return name.strip().lower().replace("_", "-")


@dataclass
class ManifestInfo:
    dir: str  # posix, relative to repo root; "." for root
    name: str | None = None
    description: str | None = None
    deps: set[str] = field(default_factory=set)  # runtime deps
    dev_deps: set[str] = field(default_factory=set)
    has_bin: bool = False
    has_start: bool = False
    workspaces: bool = False
    sources: list[str] = field(default_factory=list)

    def merge(self, other: "ManifestInfo") -> None:
        self.name = self.name or other.name
        self.description = self.description or other.description
        self.deps |= other.deps
        self.dev_deps |= other.dev_deps
        self.has_bin |= other.has_bin
        self.has_start |= other.has_start
        self.workspaces |= other.workspaces
        self.sources += other.sources

    @property
    def all_deps(self) -> set[str]:
        return self.deps | self.dev_deps


def parse_package_json(text: str, dir_: str, source: str) -> ManifestInfo:
    d = json.loads(text)
    if not isinstance(d, dict):
        raise ValueError("package.json is not an object")
    scripts = d.get("scripts") if isinstance(d.get("scripts"), dict) else {}
    ws = d.get("workspaces")
    return ManifestInfo(
        dir=dir_,
        name=d.get("name") if isinstance(d.get("name"), str) else None,
        description=d.get("description") if isinstance(d.get("description"), str) else None,
        deps={norm_dep(k) for k in (d.get("dependencies") or {})},
        dev_deps={norm_dep(k) for k in (d.get("devDependencies") or {})},
        has_bin=bool(d.get("bin")),
        has_start=any(k in scripts for k in ("start", "dev", "serve")),
        workspaces=bool(ws) and (isinstance(ws, list) or isinstance(ws, dict)),
        sources=[source],
    )


_REQ_SPLIT = re.compile(r"[<>=!~;\[\s@(,]")


def _req_name(line: str) -> str | None:
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith("-"):
        return None
    name = _REQ_SPLIT.split(line, 1)[0]
    return norm_dep(name) if name else None


def parse_requirements(text: str, dir_: str, source: str) -> ManifestInfo:
    deps = {n for n in map(_req_name, text.splitlines()) if n}
    return ManifestInfo(dir=dir_, deps=deps, sources=[source])


def parse_pyproject(text: str, dir_: str, source: str) -> ManifestInfo:
    d = tomllib.loads(text)
    project: dict[str, Any] = d.get("project") or {}
    poetry: dict[str, Any] = (d.get("tool") or {}).get("poetry") or {}
    deps = {n for n in map(_req_name, project.get("dependencies") or []) if n}
    deps |= {norm_dep(k) for k in (poetry.get("dependencies") or {}) if k.lower() != "python"}
    dev: set[str] = set()
    for group in (project.get("optional-dependencies") or {}).values():
        dev |= {n for n in map(_req_name, group) if n}
    for group in (d.get("dependency-groups") or {}).values():
        dev |= {n for n in (_req_name(g) for g in group if isinstance(g, str)) if n}
    scripts = project.get("scripts") or poetry.get("scripts") or {}
    return ManifestInfo(
        dir=dir_,
        name=project.get("name") or poetry.get("name"),
        description=project.get("description") or poetry.get("description"),
        deps=deps,
        dev_deps=dev,
        has_bin=bool(scripts),
        sources=[source],
    )


def has_workspace_file(text: str) -> bool:
    d = yaml.safe_load(text)
    return isinstance(d, dict) and bool(d.get("packages"))


# --- docker-compose -------------------------------------------------------------------------


@dataclass
class ComposeService:
    name: str
    build_context: str | None  # repo-relative posix dir, or None
    dockerfile_dir: str | None  # Dockerfile's folder when it differs from the context
    image: str | None
    depends_on: list[str]
    env: dict[str, str]
    source: str  # compose file path


def _as_env(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): "" if v is None else str(v) for k, v in raw.items()}
    out: dict[str, str] = {}
    if isinstance(raw, list):
        for item in raw:
            k, _, v = str(item).partition("=")
            out[k] = v
    return out


def _build_dirs(base: str, build: Any) -> tuple[str | None, str | None]:
    """(context folder, Dockerfile folder inside it), repo-relative; None when not applicable."""
    ctx = build.get("context", ".") if isinstance(build, dict) else build
    if not isinstance(ctx, str):
        return None, None
    context = posixpath.normpath(posixpath.join(base, ctx))
    if context.startswith(".."):
        return None, None
    dockerfile = build.get("dockerfile") if isinstance(build, dict) else None
    if isinstance(dockerfile, str) and (sub_dir := posixpath.dirname(dockerfile)):
        sub = posixpath.normpath(posixpath.join(context, sub_dir))
        if not sub.startswith("..") and (context == "." or sub.startswith(context + "/")):
            return context, sub
    return context, None


def parse_compose(text: str, compose_path: str) -> dict[str, ComposeService]:
    d = yaml.safe_load(text)
    services = d.get("services") if isinstance(d, dict) else None
    if not isinstance(services, dict):
        return {}
    base = posixpath.dirname(compose_path) or "."
    out: dict[str, ComposeService] = {}
    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        context, dockerfile_dir = _build_dirs(base, svc.get("build"))
        dep = svc.get("depends_on") or []
        out[str(name)] = ComposeService(
            name=str(name),
            build_context=context,
            dockerfile_dir=dockerfile_dir,
            image=svc.get("image") if isinstance(svc.get("image"), str) else None,
            depends_on=[str(x) for x in (dep.keys() if isinstance(dep, dict) else dep)],
            env=_as_env(svc.get("environment")),
            source=compose_path,
        )
    return out
