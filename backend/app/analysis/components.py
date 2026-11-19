"""Component detection by folder convention (SPEC §8): a tree of folders and files per container."""

import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.analysis.containers import LANG_DISPLAY, Detected
from app.analysis.scan import ScanResult
from app.models import Component
from app.render.escape import make_id

SOURCE_ROOTS = ("src", "app", "lib")

MAX_DEPTH = 6  # component levels; anything deeper is folded into its depth-6 component
MIN_SPLIT_FILES = 4  # folder-level mode: a folder is only split when it holds this many files
FILE_LEVEL_MAX_FILES = 300  # containers up to this size also get one component per file

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


@dataclass
class _Dir:
    name: str  # folder name; "a/b" after pass-through folders were merged
    path: str  # repo-relative
    files: list[str] = field(default_factory=list)  # direct files (repo-relative)
    dirs: dict[str, "_Dir"] = field(default_factory=dict)


class _Builder:
    """Turns one container's folder tree into Component objects (parents before children)."""

    def __init__(self, det: Detected, loc: dict[str, int], lang_of: dict[str, str], used: set[str]):
        self.det, self.loc, self.lang_of, self.used = det, loc, lang_of, used
        self.container = det.container
        self.file_level = len(det.files) <= FILE_LEVEL_MAX_FILES
        self.lang, _, self.framework = self.container.technology.partition(" / ")
        self.file_comp: dict[str, str] = {}

    # -- tree helpers -------------------------------------------------------------------------

    def keep(self, f: str) -> bool:
        """Empty `__init__.py` files carry no information and would be noise as components."""
        return not (posixpath.basename(f) == "__init__.py" and self.loc.get(f, 0) == 0)

    def kept(self, d: _Dir) -> list[str]:
        return [f for f in d.files if self.keep(f)]

    def subtree(self, d: _Dir) -> list[str]:
        out = self.kept(d)
        for sub in d.dirs.values():
            out += self.subtree(sub)
        return out

    def compress(self, d: _Dir) -> _Dir:
        """Merge pass-through folders (no files of their own, a single sub-folder)."""
        while not self.kept(d) and len(d.dirs) == 1:
            (child,) = d.dirs.values()
            d = _Dir(f"{d.name}/{child.name}", child.path, child.files + d.files, child.dirs)
        return d

    # -- component construction ---------------------------------------------------------------

    def display(self, name: str) -> str:
        return " / ".join(humanize(part) for part in name.split("/"))

    def make(self, *, d_name: str, id_key: str, parent: Component | None, depth: int, kind: str,
             files: list[str], path: str, role: str, evidence0: str, name: str | None = None
             ) -> Component:  # fmt: skip
        langs: dict[str, int] = defaultdict(int)
        for f in files:
            langs[self.lang_of.get(f, "")] += 1
        top = max(sorted(langs), key=lambda k: langs[k]) if langs else ""
        lang = LANG_DISPLAY.get(top, top) or self.lang
        tech = (
            self.framework
            if role == "ui" and self.container.kind == "webapp" and self.framework
            else lang
        )
        comp = Component(
            id=make_id(f"{parent.id if parent else self.container.id}_{id_key}", self.used),
            name=name or self.display(d_name),
            role=role,  # type: ignore[arg-type]
            technology=tech or None,
            paths=[path],
            description=None,
            weight=max(1, sum(self.loc.get(f, 0) for f in files)),
            evidence=[evidence0, f"{len(files)} file{'s' if len(files) != 1 else ''}"],
            parent=parent.id if parent else None,
            depth=depth,
            kind=kind,  # type: ignore[arg-type]
            file_count=len(files),
        )
        self.container.components.append(comp)
        return comp

    def role_of(self, folder: str, parent: Component | None) -> str:
        role = role_for(folder.split("/")[-1], self.container.kind)
        if role == "other" and parent is not None:
            role = parent.role  # a sub-folder of routes/ is still part of the request layer
        return role

    def leaf(self, files: list[str], comp: Component) -> None:
        for f in files:
            self.file_comp[f] = comp.id

    def emit(
        self, d: _Dir, depth: int, parent: Component | None, *, label: str | None = None
    ) -> None:
        d = self.compress(d)
        own = sorted(self.kept(d))
        everything = sorted(self.subtree(d))
        n = len(everything)
        if n == 0:
            self.map_dropped(d, [])
            return []
        role = self.role_of(d.name, parent) if label is None else "other"
        if self.file_level:
            split = depth < MAX_DEPTH and n > 1 and (len(d.dirs) > 0 or len(own) >= 2)
        else:
            split = depth < MAX_DEPTH and n >= MIN_SPLIT_FILES and len(d.dirs) > 0
        marker = f"files in {d.path}" if label is not None else f"folder {d.path}"
        key = (label or d.name).lower()

        if not split:
            comp = self.make(
                d_name=d.name, id_key=key, parent=parent, depth=depth, kind="folder",
                files=everything, path=d.path, role=role, evidence0=marker, name=label,
            )  # fmt: skip
            comp.description = (
                ROLE_DESCRIPTION[role] if label is None else "Entry points and shared code"
            )
            self.leaf(everything, comp)
            self.map_dropped(d, [comp])
            return [comp]

        group = self.make(
            d_name=d.name, id_key=key, parent=parent, depth=depth, kind="group",
            files=everything, path=d.path, role=role, evidence0=marker, name=label,
        )  # fmt: skip
        group.description = f"{n} files"
        leaves: list[Component] = []
        for sub in sorted(d.dirs.values(), key=lambda x: x.name):
            leaves += self.emit(sub, depth + 1, group)
        if self.file_level:
            for f in own:
                stem = posixpath.splitext(posixpath.basename(f))[0]
                comp = self.make(
                    d_name=stem, id_key=stem, parent=group, depth=depth + 1, kind="file",
                    files=[f], path=f, role=self.role_of(stem, group), evidence0=f"file {f}",
                )  # fmt: skip
                comp.description = ROLE_DESCRIPTION[comp.role]
                self.leaf([f], comp)
                leaves.append(comp)
        elif own:
            comp = self.make(d_name="files", id_key="files", parent=group, depth=depth + 1,
                             kind="folder", files=own, path=d.path, role=group.role,
                             evidence0=f"files in {d.path}", name="Files")  # fmt: skip
            comp.description = f"Files directly in {posixpath.basename(d.path) or d.path}"
            self.leaf(own, comp)
            leaves.append(comp)
        self.map_dropped(d, leaves)
        return leaves

    def map_dropped(self, d: _Dir, leaves: list[Component]) -> None:
        """Empty `__init__.py` files are not components, but imports still resolve to them:
        attach them to the heaviest leaf of their folder so those import edges are kept."""
        dropped = [f for f in d.files if not self.keep(f)]
        if dropped and leaves:
            rep = max(leaves, key=lambda c: (c.weight, c.id))
            for f in dropped:
                self.file_comp[f] = rep.id


def detect_components(detected: list[Detected], scan: ScanResult, used: set[str]) -> dict[str, str]:
    """Fill container.components (a tree, parents first); return file path -> leaf component id."""
    all_files = {f.path for f in scan.files}
    loc = {f.path: f.loc for f in scan.files}
    lang_of = {f.path: f.language for f in scan.files}
    file_comp: dict[str, str] = {}

    for det in detected:
        c = det.container
        if not det.files:
            continue
        base = c.path
        rels = {f: _rel(f, base) for f in det.files}
        root = _source_root(base, list(rels.values()), all_files)
        prefix = root + "/" if root else ""
        root_path = posixpath.normpath(posixpath.join(base, root))

        tree = _Dir("", root_path)
        core_files: list[str] = []  # root-level files and files outside the source root
        for f, r in rels.items():
            if not (r.startswith(prefix) and "/" in r[len(prefix) :]):
                core_files.append(f)
                continue
            node = tree
            parts = r[len(prefix) :].split("/")
            for seg in parts[:-1]:
                node = node.dirs.setdefault(seg, _Dir(seg, posixpath.join(node.path, seg)))
            node.files.append(f)

        b = _Builder(det, loc, lang_of, used)
        only_inits = core_files and all(posixpath.basename(f) == "__init__.py" for f in core_files)
        folder_names = {n.lower() for n in tree.dirs}
        for sub in sorted(tree.dirs.values(), key=lambda x: x.name):
            b.emit(sub, 1, None)
        if core_files and not (only_inits and tree.dirs):  # a bare package marker is no component
            label = "Main" if "core" in folder_names else "Core"
            b.emit(_Dir(label, root_path, core_files), 1, None, label=label)
        file_comp.update(b.file_comp)
    return file_comp
