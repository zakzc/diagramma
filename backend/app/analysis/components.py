"""Component detection by folder convention (SPEC §8). One component per feature folder."""

import posixpath
import re
from collections import defaultdict

from app.analysis.containers import Detected
from app.analysis.scan import ScanResult
from app.models import Component
from app.render.escape import make_id

SOURCE_ROOTS = ("src", "app", "lib")

ROLE_BY_FOLDER = {
    "controller": ["controllers", "controller", "routes", "routers", "router", "api", "handlers",
                   "endpoints", "resolvers", "middleware", "middlewares"],
    "service": ["services", "service", "usecases", "use_cases", "use-cases", "domain", "business",
                "logic"],
    "repository": ["repositories", "repository", "repos", "dal", "dao", "db", "database", "store",
                   "stores", "persistence", "migrations"],
    "ui": ["components", "pages", "ui", "screens", "hooks", "layouts", "widgets", "templates"],
    "model": ["models", "model", "entities", "schemas", "schema", "types", "dto", "dtos"],
    "util": ["utils", "util", "helpers", "lib", "common", "shared", "tools"],
    "config": ["config", "configs", "settings", "conf", "configuration"],
    "gateway": ["clients", "gateways", "adapters", "integrations", "external", "providers", "sdk"],
}  # fmt: skip
_ROLE_LOOKUP = {name: role for role, names in ROLE_BY_FOLDER.items() for name in names}
ROLE_DESCRIPTION = {
    "controller": "Handles incoming requests",
    "service": "Business logic",
    "repository": "Data access",
    "ui": "Views and UI components",
    "model": "Data models and schemas",
    "util": "Shared helpers",
    "config": "Configuration",
    "gateway": "Clients for external services",
    "other": None,
}
ACRONYMS = {"api", "ui", "db", "cli", "sdk", "ai", "ml", "io", "id", "url", "http", "sql", "auth"}


def role_for(folder: str, container_kind: str) -> str:
    key = folder.lower()
    if key == "views":
        return "ui" if container_kind == "webapp" else "controller"
    if key == "api" and container_kind == "webapp":
        return "gateway"  # a frontend's api/ folder holds clients, not endpoints
    return _ROLE_LOOKUP.get(key, "other")


def humanize(folder: str) -> str:
    words = [w for w in re.split(r"[-_\s]+", folder) if w]
    out = []
    for w in words:
        if w.lower() in ACRONYMS:
            out.append(w.upper() if w.lower() != "auth" else "Auth")
        elif w.islower():
            out.append(w.capitalize())
        else:
            out.append(w)
    return " ".join(out) or folder


def _rel(path: str, base: str) -> str:
    return path if base == "." else path[len(base) + 1 :]


def _source_root(base: str, rels: list[str], all_files: set[str]) -> str:
    """Folder (relative to the container) that holds the feature folders; '' = container root."""
    for cand in SOURCE_ROOTS:
        if any(r.startswith(cand + "/") for r in rels):
            root = cand
            break
    else:
        # A single top-level Python package (e.g. typer/) is the source root.
        tops: dict[str, int] = defaultdict(int)
        for r in rels:
            top = r.split("/", 1)[0]
            if (
                "/" in r
                and posixpath.normpath(posixpath.join(base, top, "__init__.py")) in all_files
            ):
                tops[top] += 1
        best = max(sorted(tops), key=lambda k: tops[k], default=None)
        root = best if best and tops[best] * 2 >= len(rels) else ""

    # Descend through a lone wrapper package (src/mypkg/...), Python only.
    while True:
        prefix = root + "/" if root else ""
        under = [r[len(prefix) :] for r in rels if r.startswith(prefix)]
        direct = [u for u in under if "/" not in u and u != "__init__.py"]
        children = {u.split("/", 1)[0] for u in under if "/" in u}
        if not direct and len(children) == 1:
            child = next(iter(children))
            if posixpath.normpath(posixpath.join(base, root, child, "__init__.py")) in all_files:
                root = posixpath.join(root, child)
                continue
        return root


def detect_components(detected: list[Detected], scan: ScanResult, used: set[str]) -> dict[str, str]:
    """Fill container.components; return file path -> component id."""
    all_files = {f.path for f in scan.files}
    loc = {f.path: f.loc for f in scan.files}
    file_comp: dict[str, str] = {}

    for det in detected:
        c = det.container
        if not det.files:
            continue
        base = c.path
        rels = {f: _rel(f, base) for f in det.files}
        root = _source_root(base, list(rels.values()), all_files)
        prefix = root + "/" if root else ""

        buckets: dict[str, list[str]] = defaultdict(list)
        for f, r in rels.items():
            if r.startswith(prefix) and "/" in r[len(prefix) :]:
                buckets[r[len(prefix) :].split("/", 1)[0]].append(f)
            else:
                buckets[""].append(f)  # root-level files and files outside the source root

        only_inits = buckets.get("") and all(
            posixpath.basename(f) == "__init__.py" for f in buckets[""]
        )
        if only_inits and len(buckets) > 1:
            del buckets[""]  # a bare package marker is not a component

        lang, _, framework = c.technology.partition(" / ")
        folder_names = {b.lower() for b in buckets if b}
        for bucket in sorted(buckets, key=lambda b: (b == "", b)):
            files = sorted(buckets[bucket])
            id_key = bucket or "core"
            if bucket:
                name, role = humanize(bucket), role_for(bucket, c.kind)
                path = posixpath.normpath(posixpath.join(base, root, bucket))
                desc = ROLE_DESCRIPTION[role]
            else:
                name = "Main" if "core" in folder_names else "Core"
                id_key = name.lower()
                role, desc = "other", "Entry points and shared code"
                path = posixpath.normpath(posixpath.join(base, root))
            tech = framework if role == "ui" and c.kind == "webapp" and framework else lang
            comp = Component(
                id=make_id(f"{c.id}_{id_key}", used),
                name=name,
                role=role,  # type: ignore[arg-type]
                technology=tech or None,
                paths=[path],
                description=desc,
                weight=max(1, sum(loc.get(f, 0) for f in files)),
                evidence=[
                    f"folder {path}" if bucket else f"files in {path}",
                    f"{len(files)} files",
                ],
            )
            c.components.append(comp)
            for f in files:
                file_comp[f] = comp.id
    return file_comp
