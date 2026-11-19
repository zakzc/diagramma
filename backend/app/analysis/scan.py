"""File walker with ignore rules (SPEC §8). Deterministic ordering."""

import os
from dataclasses import dataclass, field
from pathlib import Path

LANG_BY_EXT = {
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".py": "python",
}  # fmt: skip
SUPPORTED = {"typescript", "javascript", "python"}
# Recognised but unsupported in the MVP: counted so we can warn (SPEC §8).
UNSUPPORTED_BY_EXT = {
    ".go": "go", ".java": "java", ".kt": "kotlin", ".cs": "csharp", ".rb": "ruby",
    ".rs": "rust", ".php": "php", ".swift": "swift", ".scala": "scala",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
}  # fmt: skip

IGNORED_DIRS = {
    "node_modules", "dist", "build", "out", "target", "vendor", "venv", "env", "site-packages",
    "__pycache__", "coverage", "bower_components", "generated", "__generated__",
    "tests", "test", "__tests__", "spec", "e2e", "fixtures", "__fixtures__",
    "mocks", "__mocks__", "docs", "doc",
}  # fmt: skip
IGNORED_SUFFIXES = (".min.js", ".bundle.js", ".d.ts", "_pb2.py", "_pb2_grpc.py", ".pb.go")
IGNORED_MARKERS = (".test.", ".spec.", ".generated.")
IGNORED_NAMES = {"conftest.py"}

MANIFEST_NAMES = {
    "package.json", "pnpm-workspace.yaml", "pyproject.toml", "requirements.txt",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
}  # fmt: skip
ENV_EXAMPLE_NAMES = {".env.example", ".env.sample", ".env.template", ".env.dist"}
MAX_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class FileEntry:
    path: str  # posix, relative to repo root
    language: str
    loc: int

    @property
    def supported(self) -> bool:
        return self.language in SUPPORTED


@dataclass
class ScanResult:
    files: list[FileEntry] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    env_files: list[str] = field(default_factory=list)  # example env files only, never real .env
    skipped_large: int = 0

    def language_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.files:
            counts[f.language] = counts.get(f.language, 0) + 1
        return dict(sorted(counts.items()))


def _is_ignored_file(name: str) -> bool:
    low = name.lower()
    if name in IGNORED_NAMES or low.endswith(IGNORED_SUFFIXES):
        return True
    if any(m in low for m in IGNORED_MARKERS):
        return True
    return (low.startswith("test_") and low.endswith(".py")) or low.endswith("_test.py")


def _count_lines(path: Path) -> int:
    with open(path, "rb") as fh:
        return sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(1 << 16), b""))


def _is_manifest(name: str) -> bool:
    if name in MANIFEST_NAMES:
        return True
    low = name.lower()
    return low.startswith("docker-compose.") and low.endswith((".yml", ".yaml"))


def scan_repo(root: Path) -> ScanResult:
    result = ScanResult()
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune in place; sort for deterministic traversal.
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".")
            and d not in IGNORED_DIRS
            and not os.path.islink(Path(dirpath, d))
        )
        rel_dir = Path(dirpath).relative_to(root)
        for name in sorted(filenames):
            full = Path(dirpath, name)
            if full.is_symlink():
                continue
            rel = (rel_dir / name).as_posix()
            if name in ENV_EXAMPLE_NAMES:
                result.env_files.append(rel)
                continue
            if _is_manifest(name):
                result.manifests.append(rel)
                continue
            ext = Path(name).suffix.lower()
            lang = LANG_BY_EXT.get(ext) or UNSUPPORTED_BY_EXT.get(ext)
            if not lang or _is_ignored_file(name):
                continue
            if full.stat().st_size > MAX_FILE_BYTES:
                result.skipped_large += 1
                continue
            result.files.append(FileEntry(rel, lang, _count_lines(full)))
    return result
