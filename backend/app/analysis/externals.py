"""External systems and data stores (SPEC §8) from deps, compose images and env vars."""

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from app.analysis.containers import Detected
from app.analysis.manifests import ComposeService, norm_dep
from app.models import External
from app.render.escape import make_id

CATALOGUE_PATH = Path(__file__).with_name("catalogue.yaml")
_SCHEME_RE = re.compile(r"\b([a-z][a-z0-9+.-]*)://", re.I)


@cache
def load_catalogue() -> list[dict[str, Any]]:
    return yaml.safe_load(CATALOGUE_PATH.read_text(encoding="utf-8"))


@dataclass
class Link:
    container_id: str
    external_id: str
    evidence: str


@cache
def _catalogue_by_dep() -> dict[str, dict[str, Any]]:
    return {norm_dep(d): e for e in load_catalogue() for d in e.get("deps", [])}


def find_by_dep(name: str) -> dict[str, Any] | None:
    """Catalogue entry for an imported/declared package name, if any."""
    return _catalogue_by_dep().get(norm_dep(name))


@dataclass
class ExternalResult:
    used: set[str]
    links: list[Link] = field(default_factory=list)
    # compose service name -> external id, for depends_on edges
    by_service: dict[str, str] = field(default_factory=dict)
    technology_by_id: dict[str, str] = field(default_factory=dict)
    built: dict[str, External] = field(default_factory=dict)  # catalogue/generic id -> External

    @property
    def externals(self) -> list[External]:
        return sorted(self.built.values(), key=lambda e: e.id)

    def ensure(self, entry: dict[str, Any], evidence: str) -> str:
        ext = self.built.get(entry["id"])
        if ext is None:
            ext = External(
                id=make_id(entry["id"], self.used),
                name=entry["name"],
                kind=entry["kind"],
                technology=entry.get("technology"),
            )
            self.built[entry["id"]] = ext
        if evidence not in ext.evidence:
            ext.evidence.append(evidence)
        self.technology_by_id[ext.id] = entry.get("technology") or ""
        return ext.id


def _image_matches(image: str, tokens: list[str]) -> bool:
    last = image.split("@")[0].rsplit("/", 1)[-1].split(":")[0].lower()
    return any(last.startswith(t) for t in tokens)


def _env_matches(entry: dict[str, Any], env: dict[str, str]) -> str | None:
    prefixes = [p.upper() for p in entry.get("env_prefixes", [])]
    for key in sorted(env):
        if any(key.upper().startswith(p) for p in prefixes):
            return f"env var {key}"
    schemes = {s.lower() for s in entry.get("schemes", [])}
    if schemes:
        for key in sorted(env):
            for m in _SCHEME_RE.finditer(env[key]):
                if m.group(1).lower() in schemes:
                    return f"env var {key} uses {m.group(1).lower()}:// URL"
    return None


def detect_externals(
    detected: list[Detected], compose: dict[str, ComposeService], used: set[str]
) -> ExternalResult:
    catalogue = load_catalogue()
    res = ExternalResult(used=used)

    # 1. compose services that are not built from this repo: images are infrastructure.
    for svc in sorted(compose.values(), key=lambda s: s.name):
        if svc.build_context is not None or not svc.image:
            continue
        entry = next((e for e in catalogue if _image_matches(svc.image, e.get("images", []))), None)
        if entry is None:
            entry = {
                "id": f"svc_{svc.name}",
                "name": svc.name,
                "kind": "system",
                "technology": svc.image,
            }
        res.by_service[svc.name] = res.ensure(
            entry, f"docker-compose image '{svc.image}' ({svc.source})"
        )

    # 2. dependency names and env vars per container.
    for det in detected:
        deps = det.info.deps if det.info else set()
        for entry in catalogue:
            wanted = {norm_dep(d) for d in entry.get("deps", [])}
            hit = sorted(deps & wanted)
            if hit:
                ext_id = res.ensure(entry, f"dependency '{hit[0]}' in {det.container.name}")
                res.links.append(Link(det.container.id, ext_id, f"dependency '{hit[0]}'"))
                continue
            if env_hit := _env_matches(entry, det.env):
                ext_id = res.ensure(entry, f"{env_hit} in {det.container.name}")
                res.links.append(Link(det.container.id, ext_id, env_hit))
    return res
