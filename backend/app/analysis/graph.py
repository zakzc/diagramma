"""File-level import graph, resolved to files, containers and external systems (SPEC §8)."""

import posixpath
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.analysis.containers import Detected
from app.analysis.externals import ExternalResult, find_by_dep
from app.analysis.parse import ImportRef, extract_imports
from app.analysis.scan import SUPPORTED, ScanResult

JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
_JS_STRIP = re.compile(r"\.(m|c)?jsx?$")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALIAS_PREFIXES = ("@/", "~/", "#/")


@dataclass
class FileGraph:
    # (src file, dst file) -> number of import statements
    files: Counter[tuple[str, str]] = field(default_factory=Counter)
    # (src file, target container id) from a bare import of a workspace package
    containers: Counter[tuple[str, str]] = field(default_factory=Counter)
    # (src file, external id)
    externals: Counter[tuple[str, str]] = field(default_factory=Counter)
    parse_failures: int = 0


def _js_pkg(spec: str) -> str:
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def _resolve_js(base: str, all_files: set[str]) -> str | None:
    base = posixpath.normpath(base)
    stem = _JS_STRIP.sub("", base)  # TS imports './x.js' for x.ts
    for b in dict.fromkeys((base, stem)):
        if b in all_files:
            return b
        for ext in JS_EXTS:
            if b + ext in all_files:
                return b + ext
        for ext in JS_EXTS:
            if f"{b}/index{ext}" in all_files:
                return f"{b}/index{ext}"
    return None


def _py_module_index(detected: list[Detected]) -> dict[str, str]:
    """Dotted module name -> file, for each plausible import root of each container."""
    index: dict[str, str] = {}
    for det in detected:
        base = det.container.path
        roots = {base, posixpath.join(base, "src") if base != "." else "src"}
        for f in sorted(det.files):
            if not f.endswith(".py"):
                continue
            for root in sorted(roots):
                if root != "." and not f.startswith(root + "/"):
                    continue
                rel = f if root == "." else f[len(root) + 1 :]
                parts = rel[:-3].split("/")
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                if parts and all(_IDENT.match(p) for p in parts):
                    index.setdefault(".".join(parts), f)
    return index


def _resolve_py(imp: ImportRef, src: str, index: dict[str, str], all_files: set[str]) -> list[str]:
    """Files an import statement depends on.

    `from pkg import a, b` depends on the submodules `a` and `b` when they are modules; the
    package's own `__init__` only counts if some imported name is not a submodule (a class or
    function defined or re-exported there). One statement is one dependency, not two.
    """
    module_file: str | None = None
    subs: list[str] = []
    all_subs = bool(imp.names)
    if imp.level:
        pkg = posixpath.dirname(src)
        for _ in range(imp.level - 1):
            pkg = posixpath.dirname(pkg)
        base = (
            posixpath.normpath(posixpath.join(pkg, imp.module.replace(".", "/")))
            if imp.module
            else pkg
        )
        module_file = next(
            (c for c in (f"{base}.py", f"{base}/__init__.py") if c in all_files), None
        )
        for n in imp.names:
            hit = next(
                (c for c in (f"{base}/{n}.py", f"{base}/{n}/__init__.py") if c in all_files), None
            )
            if hit:
                subs.append(hit)
            else:
                all_subs = False
    else:
        module_file = index.get(imp.module)
        for n in imp.names:
            if (sub := f"{imp.module}.{n}") in index:
                subs.append(index[sub])
            else:
                all_subs = False
    out = subs if (all_subs and subs) else ([module_file] if module_file else []) + subs
    return list(dict.fromkeys(out))


def build_graph(
    root: Path,
    scan: ScanResult,
    detected: list[Detected],
    file_comp: dict[str, str],
    ext: ExternalResult,
) -> FileGraph:
    g = FileGraph()
    all_files = {f.path for f in scan.files}
    owner = {p: d for d in detected for p in d.files}
    pkg_to_container = {
        d.info.name.lower(): d.container.id for d in detected if d.info and d.info.name
    }
    py_index = _py_module_index(detected)

    for f in scan.files:
        if f.language not in SUPPORTED or f.path not in file_comp:
            continue
        det = owner.get(f.path)
        try:
            imports = extract_imports(root / f.path, f.path, f.language)
        except Exception:  # noqa: BLE001 - a grammar/parse failure must not fail the whole job
            g.parse_failures += 1
            continue

        for imp in imports:
            if f.language == "python":
                targets = _resolve_py(imp, f.path, py_index, all_files)
                for t in targets:
                    g.files[(f.path, t)] += 1
                if targets or imp.level:
                    continue
                top = imp.module.split(".")[0]
                entry = find_by_dep(top)
                if entry:
                    eid = ext.ensure(entry, f"import of '{top}' in {f.path}")
                    g.externals[(f.path, eid)] += 1
                continue

            spec = imp.module
            if spec.startswith("."):
                t = _resolve_js(posixpath.join(posixpath.dirname(f.path), spec), all_files)
            elif spec.startswith(ALIAS_PREFIXES) and det is not None:
                rest = spec[2:]
                t = None
                for root_dir in (posixpath.join(det.container.path, "src"), det.container.path):
                    t = _resolve_js(posixpath.join(root_dir, rest), all_files)
                    if t:
                        break
            else:
                t = None
                pkg = _js_pkg(spec.removeprefix("node:"))
                target = pkg_to_container.get(pkg.lower())
                if target and det is not None and target != det.container.id:
                    g.containers[(f.path, target)] += 1
                elif target is None and (entry := find_by_dep(pkg)):
                    eid = ext.ensure(entry, f"import of '{pkg}' in {f.path}")
                    g.externals[(f.path, eid)] += 1
            if t and t != f.path:
                g.files[(f.path, t)] += 1
    return g
