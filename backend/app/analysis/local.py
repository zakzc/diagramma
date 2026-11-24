"""Local folder input (SPEC §5.6): validate a path, honour .gitignore, fingerprint, browse."""

import hashlib
import os
import subprocess
from pathlib import Path

from app.analysis.fetch import GIT_TIMEOUT_S, ClonedRepo, RepoSpec, _git_env
from app.analysis.scan import MANIFEST_NAMES, ScanResult
from app.errors import AppError
from app.models import DirEntry, DirListing


def resolve_dir(raw: str | None) -> Path:
    raw = (raw or "").strip()
    p = Path(raw)
    if not raw or not p.is_absolute():
        raise AppError("INVALID_PATH", "Enter the absolute path of a folder.")
    try:
        p = p.resolve(strict=True)
    except (OSError, RuntimeError):  # missing, unreadable, or a symlink loop
        raise AppError("PATH_NOT_FOUND", "That folder does not exist.") from None
    if not p.is_dir():
        raise AppError("INVALID_PATH", "That path is not a folder.")
    return p


def parse_local_path(raw: str | None) -> RepoSpec:
    p = resolve_dir(raw)
    return RepoSpec("local", p.name or "root", None, str(p))


def open_local(spec: RepoSpec) -> ClonedRepo:
    """The folder is analysed in place; the commit is set from the scan (`fingerprint`)."""
    return ClonedRepo(resolve_dir(spec.path), "")


def git_files(root: Path) -> set[str] | None:
    """Files git tracks or does not ignore (.gitignore honoured); None if root is not a git repo.

    shortcut: a folder without its own .git gets no .gitignore handling, see SPEC §5.6 Q7.
    """
    if not (root / ".git").exists():
        return None
    try:
        p = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            env=_git_env(None),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    return {f for f in p.stdout.split("\0") if f}


def fingerprint(root: Path, scan: ScanResult) -> str:
    """Identity of a folder's content: path, size and mtime of every scanned file."""
    h = hashlib.sha256()
    for rel in sorted([*(f.path for f in scan.files), *scan.manifests, *scan.env_files]):
        try:
            st = (root / rel).stat()
        except OSError:
            continue
        h.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    return h.hexdigest()[:12]


def _is_repo(p: Path) -> bool:
    return (p / ".git").exists() or any((p / n).exists() for n in MANIFEST_NAMES)


def list_dirs(raw: str | None, hidden: bool = False) -> DirListing:
    """Sub-directories of `raw` (default: home). Names only; never reads file contents."""
    folder = resolve_dir(raw) if raw else Path.home().resolve()
    dirs: list[DirEntry] = []
    try:
        with os.scandir(folder) as it:
            for e in it:
                try:
                    if (hidden or not e.name.startswith(".")) and e.is_dir():
                        repo = _is_repo(Path(e.path))
                        dirs.append(DirEntry(name=e.name, path=e.path, is_repo=repo))
                except OSError:
                    continue
    except OSError:
        raise AppError("INVALID_PATH", "That folder cannot be read.") from None
    dirs.sort(key=lambda d: d.name.lower())
    parent = str(folder.parent) if folder.parent != folder else None
    return DirListing(path=str(folder), parent=parent, is_repo=_is_repo(folder), dirs=dirs)
