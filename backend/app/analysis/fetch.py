"""URL validation and git clone (SPEC §6, §5.5). Static only: never runs repo code."""

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.errors import AppError

GITHUB_BASE = "https://github.com"
CACHE_DIR = (
    Path(os.environ.get("DIAGRAMMA_CACHE_DIR", Path.home() / ".cache" / "diagramma")) / "repos"
)
GIT_TIMEOUT_S = 300

_NAME = r"[A-Za-z0-9_.-]+"
_URL_RE = re.compile(rf"^https://github\.com/(?P<owner>{_NAME})/(?P<name>{_NAME})/?$")
_SHORT_RE = re.compile(rf"^(?P<owner>{_NAME})/(?P<name>{_NAME})$")
_REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")


@dataclass(frozen=True)
class RepoSpec:
    owner: str
    name: str
    ref: str | None = None
    path: str | None = None  # local folder (SPEC §5.6): owner is "local", name the folder name

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def repo_url(self) -> str:
        return f"file://{self.path}" if self.path else f"{GITHUB_BASE}/{self.slug}"


@dataclass(frozen=True)
class ClonedRepo:
    path: Path
    commit_sha: str
    commit_date: str = ""  # ISO-8601 committer date: deterministic, unlike 'now'


def parse_repo_url(url: str, ref: str | None = None) -> RepoSpec:
    """Accept https://github.com/owner/repo(.git) and owner/repo."""
    url = (url or "").strip()
    m = _URL_RE.match(url) or _SHORT_RE.match(url)
    owner = name = ""
    if m:
        owner, name = m["owner"], m["name"].removesuffix(".git")
    if not m or not name or {owner, name} & {".", ".."}:
        raise AppError(
            "INVALID_URL", "Enter a GitHub repo as https://github.com/owner/repo or owner/repo."
        )
    ref = (ref or "").strip() or None
    if ref and (not _REF_RE.match(ref) or ".." in ref or ref.endswith(".lock")):
        raise AppError("INVALID_URL", f"'{ref}' is not a valid branch, tag or commit.")
    return RepoSpec(owner, name, ref)


def _git_env(token: str | None) -> dict[str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "true", "LC_ALL": "C"}
    if token:
        # Passed via env config so the token never appears in argv, remotes or logs.
        import base64

        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
            GIT_CONFIG_VALUE_0=f"Authorization: Basic {basic}",
        )
    return env


def _git(args: list[str], cwd: Path, token: str | None) -> str:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=_git_env(token),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
        )
    except FileNotFoundError as e:
        raise AppError("CLONE_FAILED", "git is not installed or not on PATH.") from e
    except subprocess.TimeoutExpired as e:
        raise AppError("CLONE_FAILED", "git timed out while fetching the repository.") from e
    if p.returncode != 0:
        raise _map_git_error(p.stderr, token)
    return p.stdout


def _map_git_error(stderr: str, token: str | None) -> AppError:
    err = (stderr or "").strip()
    if token:
        err = err.replace(token, "***")
    low = err.lower()
    if "couldn't find remote ref" in low:
        return AppError(
            "CLONE_FAILED", "That branch, tag or commit does not exist in the repository."
        )
    if "repository not found" in low or "does not appear to be a git repository" in low:
        return AppError("REPO_NOT_FOUND", "Repository not found.")
    if any(
        s in low
        for s in (
            "could not read username",
            "terminal prompts disabled",
            "authentication failed",
            "403",
        )
    ):
        hint = (
            "Authentication failed; check GITHUB_TOKEN."
            if token
            else ("Repository not found or private. For private repos set GITHUB_TOKEN.")
        )
        return AppError("AUTH_REQUIRED", hint)
    last = err.splitlines()[-1] if err else "unknown git error"
    return AppError("CLONE_FAILED", f"git failed: {last}")


def clone_repo(
    spec: RepoSpec,
    cache_dir: Path | None = None,
    base_url: str = GITHUB_BASE,
) -> ClonedRepo:
    """Shallow-fetch one ref into the cache (init + fetch handles branches, tags and SHAs)."""
    cache_dir = cache_dir or CACHE_DIR
    token = os.environ.get("GITHUB_TOKEN") or None
    key = hashlib.sha1((spec.ref or "").encode()).hexdigest()[:8]
    dest = cache_dir / f"{spec.owner}__{spec.name}__{key}"

    def fetch() -> None:
        if not (dest / ".git").is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            _git(["init", "-q"], dest, token)
            _git(
                ["remote", "add", "origin", f"{base_url}/{spec.owner}/{spec.name}.git"], dest, token
            )
        _git(["fetch", "-q", "--depth", "1", "origin", spec.ref or "HEAD"], dest, token)
        _git(["checkout", "-q", "--detach", "--force", "FETCH_HEAD"], dest, token)

    existed = (dest / ".git").is_dir()
    try:
        fetch()
    except AppError as e:
        if existed and e.code == "CLONE_FAILED" and "does not exist" not in e.message:
            shutil.rmtree(dest, ignore_errors=True)  # corrupt cache: retry from scratch
            try:
                fetch()
            except AppError:
                shutil.rmtree(dest, ignore_errors=True)
                raise
        else:
            if not existed:
                shutil.rmtree(dest, ignore_errors=True)
            raise
    sha = _git(["rev-parse", "HEAD"], dest, token).strip()
    date = _git(["show", "-s", "--format=%cI", "HEAD"], dest, token).strip()
    return ClonedRepo(dest, sha, date)


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def resolve_commit(spec: RepoSpec, base_url: str = GITHUB_BASE, timeout: float = 15) -> str | None:
    """Commit a ref currently points to (cheap `git ls-remote`), or None if unknown.

    Used to reuse an existing diagram without cloning. Any failure returns None so the normal
    job path (which reports real errors) takes over.
    """
    if spec.ref and _SHA_RE.match(spec.ref):
        return spec.ref
    ref = spec.ref
    patterns = [ref, f"{ref}^{{}}"] if ref else ["HEAD"]
    try:
        p = subprocess.run(
            ["git", "ls-remote", f"{base_url}/{spec.owner}/{spec.name}.git", *patterns],
            env=_git_env(os.environ.get("GITHUB_TOKEN") or None),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=Path.home(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    found: dict[str, str] = {}
    for line in p.stdout.splitlines():
        sha, _, name = line.partition("\t")
        found[name] = sha
    if ref is None:
        return found.get("HEAD")
    for name in (f"refs/heads/{ref}", f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}"):
        if name in found:
            return found[name]
    return None
