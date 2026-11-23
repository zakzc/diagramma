"""React file-level model for the Imports view (SPEC §9.4): which files exist, what kind each
one is, and which files, databases, services and API clients each one imports."""

from pathlib import Path

from app.analysis.containers import Detected
from app.analysis.externals import ExternalResult
from app.analysis.filekind import REACT_PACKAGES, Evidence, classify, display_name
from app.analysis.graph import ALIAS_PREFIXES, FileGraph, _js_pkg
from app.analysis.parse import read_js_file
from app.analysis.scan import ScanResult
from app.models import FileImport, SourceFile
from app.render.escape import make_id

JS_LANGS = {"typescript", "javascript"}


def build_file_model(
    root: Path,
    scan: ScanResult,
    detected: list[Detected],
    file_comp: dict[str, str],
    graph: FileGraph,
    ext: ExternalResult,
    used: set[str],
) -> tuple[list[SourceFile], list[FileImport]]:
    """Files of the containers that use React (others are not React applications), with ids."""
    owner = {p: d.container.id for d in detected for p in d.files}
    by_ext = {e.id: e for e in ext.externals}
    info: dict[str, tuple[Evidence, int]] = {}
    for f in scan.files:
        if f.language not in JS_LANGS or f.path not in file_comp or f.path not in owner:
            continue
        try:
            js = read_js_file(root / f.path, f.path, f.language)
        except Exception:  # noqa: BLE001 - counted as a parse failure by the graph stage
            continue
        pk: set[str] = set()
        for imp in js.imports:
            s = imp.module
            if s and not s.startswith(".") and not s.startswith(ALIAS_PREFIXES):
                pk.add(_js_pkg(s.removeprefix("node:")))
        info[f.path] = (Evidence(f.path, js.text, js.has_jsx, pk, False, False), f.loc)

    # A container is a React app when it declares react or any of its files imports it.
    react = {d.container.id for d in detected if d.info and d.info.all_deps & REACT_PACKAGES}
    react |= {owner[p] for p, (ev, _) in info.items() if ev.packages & REACT_PACKAGES}
    ext_of: dict[str, set[str]] = {}
    for (src, eid), _n in graph.externals.items():
        ext_of.setdefault(src, set()).add(eid)

    files: list[SourceFile] = []
    ids: dict[str, str] = {}
    for path in sorted(info):
        if owner[path] not in react:
            continue
        ev, loc = info[path]
        kinds = {by_ext[e].kind for e in ext_of.get(path, set()) if e in by_ext}
        ev = Evidence(
            ev.path,
            ev.text,
            ev.has_jsx,
            ev.packages,
            "database" in kinds,
            bool(kinds - {"database"}),
        )
        ids[path] = make_id(f"f_{path}", used)
        files.append(
            SourceFile(
                id=ids[path],
                path=path,
                name=display_name(path),
                kind=classify(ev),
                container=owner[path],
                loc=loc,
                packages=sorted(ev.packages),
            )
        )

    edges: dict[tuple[str, str], int] = {}
    for (src, dst), n in graph.files.items():
        if src in ids and dst in ids:
            edges[(ids[src], ids[dst])] = n
    for (src, eid), n in graph.externals.items():
        if src in ids:
            edges[(ids[src], eid)] = n
    imports = [FileImport(source=s, target=t, count=n) for (s, t), n in sorted(edges.items())]
    return files, imports
