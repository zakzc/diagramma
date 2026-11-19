"""Stage 'detect': scan result -> Model (containers, externals, relations)."""

import posixpath
from pathlib import Path

from app.analysis.components import detect_components
from app.analysis.containers import Detected, detect_containers
from app.analysis.externals import detect_externals
from app.analysis.graph import build_graph
from app.analysis.manifests import ComposeService, parse_compose
from app.analysis.reduce import reduce_components
from app.analysis.relations import component_relations, container_relations
from app.analysis.scan import SUPPORTED, ScanResult
from app.models import Model


def _load_compose(root: Path, scan: ScanResult, warnings: list[str]) -> dict[str, ComposeService]:
    out: dict[str, ComposeService] = {}
    for rel in scan.manifests:
        base = posixpath.basename(rel).lower()
        if not (
            base.startswith(("docker-compose", "compose")) and base.endswith((".yml", ".yaml"))
        ):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
            for name, svc in parse_compose(text, rel).items():
                out.setdefault(name, svc)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Could not parse {rel}: {type(e).__name__}")
    return out


def _attach_env(
    root: Path, scan: ScanResult, detected: list[Detected], warnings: list[str]
) -> None:
    """Compose environment + example env files (never real .env files) per container."""
    for det in detected:
        if det.compose:
            det.env.update(det.compose.env)
    dirs = sorted({d.container.path for d in detected})
    by_path = {d.container.path: d for d in detected}
    for rel in scan.env_files:
        folder = posixpath.dirname(rel) or "."
        owner = max(
            (d for d in dirs if d == "." or folder == d or folder.startswith(d + "/")),
            key=len,
            default=None,
        )
        if owner is None:
            continue
        try:
            for line in (root / rel).read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    by_path[owner].env.setdefault(
                        k.strip().removeprefix("export ").strip(), v.strip()
                    )
        except OSError:
            warnings.append(f"Could not read {rel}")


def build_model(root: Path, scan: ScanResult, system_name: str) -> Model:
    warnings: list[str] = []
    compose = _load_compose(root, scan, warnings)
    used: set[str] = set()  # one id namespace for containers, components and externals
    detected = detect_containers(root, scan, system_name, compose, warnings, used)
    _attach_env(root, scan, detected, warnings)
    ext = detect_externals(detected, compose, used)
    file_comp = detect_components(detected, scan, used)
    graph = build_graph(root, scan, detected, file_comp, ext)
    if graph.parse_failures:
        warnings.append(f"Could not parse imports in {graph.parse_failures} file(s).")
    relations = component_relations(
        detected, ext, graph, file_comp, container_relations(detected, ext)
    )

    counts = scan.language_counts()
    unsupported = {k: v for k, v in counts.items() if k not in SUPPORTED}
    if unsupported:
        listing = ", ".join(f"{k} ({v} files)" for k, v in unsupported.items())
        if not any(k in SUPPORTED for k in counts):
            warnings.append(
                f"Unsupported language(s): {listing}. Built from folders and manifests only."
            )
        else:
            warnings.append(f"Unsupported language(s) not analysed in depth: {listing}.")
    if scan.skipped_large:
        warnings.append(f"Skipped {scan.skipped_large} source file(s) larger than 1 MB.")

    model = Model(
        system_name=system_name,
        containers=[d.container for d in detected],
        externals=ext.externals,
        relations=relations,
        warnings=warnings,
    )
    reduce_components(model)
    return model
