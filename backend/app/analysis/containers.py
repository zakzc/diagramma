"""Container detection (SPEC §8): compose services, workspace/manifest folders, fallback."""

import posixpath
from dataclasses import dataclass, field
from pathlib import Path

from app.analysis.manifests import (
    ComposeService,
    ManifestInfo,
    has_workspace_file,
    parse_package_json,
    parse_pyproject,
    parse_requirements,
)
from app.analysis.scan import ScanResult
from app.models import Container
from app.render.escape import make_id

# (dependency, display name), in precedence order within each group.
UI_FRAMEWORKS = [
    ("next", "Next.js"), ("nuxt", "Nuxt"), ("@angular/core", "Angular"),
    ("@sveltejs/kit", "SvelteKit"), ("svelte", "Svelte"), ("vue", "Vue"),
    ("solid-js", "Solid"), ("react", "React"), ("preact", "Preact"),
]  # fmt: skip
API_FRAMEWORKS = [
    ("@nestjs/core", "NestJS"), ("fastify", "Fastify"), ("express", "Express"), ("koa", "Koa"),
    ("hono", "Hono"), ("@hapi/hapi", "Hapi"), ("fastapi", "FastAPI"), ("flask", "Flask"),
    ("django", "Django"), ("starlette", "Starlette"), ("aiohttp", "aiohttp"),
    ("sanic", "Sanic"), ("litestar", "Litestar"), ("tornado", "Tornado"),
]  # fmt: skip
WORKER_LIBS = [
    ("celery", "Celery"), ("bullmq", "BullMQ"), ("bull", "Bull"), ("rq", "RQ"),
    ("dramatiq", "Dramatiq"), ("arq", "arq"),
]  # fmt: skip
CLI_LIBS = [("typer", "Typer"), ("click", "Click"), ("commander", "Commander"), ("yargs", "yargs")]

ENTRY_FILES = {"__main__.py", "main.py", "app.py", "manage.py", "server.py", "index.js", "index.ts"}
LANG_DISPLAY = {
    "typescript": "TypeScript", "javascript": "JavaScript", "python": "Python", "go": "Go",
    "java": "Java", "kotlin": "Kotlin", "csharp": "C#", "ruby": "Ruby", "rust": "Rust",
    "php": "PHP", "swift": "Swift", "scala": "Scala", "c": "C", "cpp": "C++",
}  # fmt: skip


@dataclass
class Detected:
    """A container plus the raw facts later stages (externals, relations) need."""

    container: Container
    info: ManifestInfo | None = None
    compose_name: str | None = None
    compose: ComposeService | None = None
    files: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)  # compose env + example env files


def _first(deps: set[str], table: list[tuple[str, str]]) -> str | None:
    return next((disp for dep, disp in table if dep in deps), None)


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8", errors="replace")


def load_manifests(
    root: Path, scan: ScanResult, warnings: list[str]
) -> tuple[dict[str, ManifestInfo], bool]:
    """Per-directory merged manifest info, and whether the root declares workspaces."""
    infos: dict[str, ManifestInfo] = {}
    root_workspace = False
    for rel in scan.manifests:
        name, dir_ = posixpath.basename(rel), posixpath.dirname(rel) or "."
        try:
            text = _read(root, rel)
            if name == "package.json":
                info = parse_package_json(text, dir_, rel)
            elif name == "pyproject.toml":
                info = parse_pyproject(text, dir_, rel)
            elif name == "requirements.txt":
                info = parse_requirements(text, dir_, rel)
            elif name == "pnpm-workspace.yaml":
                if dir_ == "." and has_workspace_file(text):
                    root_workspace = True
                continue
            else:
                continue
        except Exception as e:  # noqa: BLE001 - one broken manifest must not stop the run
            warnings.append(f"Could not parse {rel}: {type(e).__name__}")
            continue
        if dir_ in infos:
            infos[dir_].merge(info)
        else:
            infos[dir_] = info
    if "." in infos and infos["."].workspaces:
        root_workspace = True
    return infos, root_workspace


def _owner(path: str, dirs: list[str]) -> str | None:
    """Nearest (longest-prefix) candidate directory containing `path`."""
    best = None
    for d in dirs:
        if d == "." or path.startswith(d + "/"):
            if best is None or len(d) > len(best):
                best = d
    return best


def _classify(
    info: ManifestInfo | None, files: list[str], from_compose: bool
) -> tuple[str, str | None]:
    deps = info.all_deps if info else set()
    if fw := _first(deps, UI_FRAMEWORKS):
        return "webapp", fw
    if fw := _first(deps, API_FRAMEWORKS):
        return "api", fw
    if fw := _first(deps, WORKER_LIBS):
        return "worker", fw
    if info and info.has_bin or _first(deps, CLI_LIBS):
        return "cli", _first(deps, CLI_LIBS)
    entry = (info and info.has_start) or any(posixpath.basename(f) in ENTRY_FILES for f in files)
    if entry or from_compose:
        return "service", None
    return "library", None


def detect_containers(
    root: Path,
    scan: ScanResult,
    repo_name: str,
    compose: dict[str, ComposeService],
    warnings: list[str],
    used: set[str],
) -> list[Detected]:
    infos, root_workspace = load_manifests(root, scan, warnings)
    by_context: dict[str, ComposeService] = {}
    for svc in compose.values():
        if svc.build_context is None:
            continue
        # `context: .` + `dockerfile: backend/Dockerfile` -> the Dockerfile's folder is the app,
        # but only when it actually holds a manifest or source files.
        d = svc.dockerfile_dir
        has_code = d is not None and (
            d in infos or any(f.path.startswith(d + "/") for f in scan.files)
        )
        by_context.setdefault(d if has_code and d else svc.build_context, svc)

    candidates = set(infos) | set(by_context)
    if root_workspace:
        candidates.discard(".")
    dirs = sorted(candidates)

    def assign(ds: list[str]) -> tuple[dict[str, list[str]], list[str]]:
        owned: dict[str, list[str]] = {d: [] for d in ds}
        unowned: list[str] = []
        for f in scan.files:
            o = _owner(f.path, ds)
            (owned[o] if o is not None else unowned).append(f.path)
        return owned, unowned

    owned, unowned = assign(dirs)
    if unowned and not root_workspace:  # loose source outside any manifest folder
        dirs = sorted({*dirs, "."})
        owned, unowned = assign(dirs)

    keep = [d for d in dirs if owned.get(d) or d in by_context]
    if not keep and dirs:
        keep = dirs[:1]
    if not keep:
        keep = ["."]
        owned["."] = []

    lang_of = {f.path: f.language for f in scan.files}
    out: list[Detected] = []
    for d in keep:
        info = infos.get(d)
        files = owned.get(d, [])
        svc = by_context.get(d)
        name = (
            svc.name
            if svc
            else (info.name if info and info.name else None)
            or (repo_name if d == "." else posixpath.basename(d))
        )
        name = name.split("/")[-1] if name.startswith("@") else name
        kind, fw = _classify(info, files, from_compose=svc is not None)
        langs: dict[str, int] = {}
        for p in files:
            langs[lang_of[p]] = langs.get(lang_of[p], 0) + 1
        lang = max(sorted(langs), key=lambda k: langs[k]) if langs else None
        tech = " / ".join(x for x in (LANG_DISPLAY.get(lang or "", lang), fw) if x) or (
            "Docker" if svc else "Unknown"
        )
        evidence = []
        if svc:
            evidence.append(f"docker-compose service '{svc.name}' ({svc.source})")
        if info:
            evidence += [f"manifest {s}" for s in sorted(info.sources)]
        if not evidence:
            evidence.append("source files at repository root" if d == "." else f"folder {d}")
        out.append(
            Detected(
                container=Container(
                    id=make_id(name, used),
                    name=name,
                    kind=kind,  # type: ignore[arg-type]
                    technology=tech,
                    path=d,
                    description=info.description if info else None,
                    evidence=evidence,
                ),
                info=info,
                compose_name=svc.name if svc else None,
                compose=svc,
                files=files,
            )
        )
    return out
