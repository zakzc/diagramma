import pytest

from app.analysis.fetch import RepoSpec, clone_repo, parse_repo_url
from app.errors import AppError


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/o/r",
        "https://github.com/o/r/",
        "https://github.com/o/r.git",
        "o/r",
        " o/r ",
    ],
)
def test_parse_ok(url):
    assert parse_repo_url(url) == RepoSpec("o", "r", None)


BAD_URLS = [
    "", "http://github.com/o/r", "https://gitlab.com/o/r", "file:///etc", "o", "o/r/x", "../r",
    "o/..", "https://github.com/o/r/tree/main", "git@github.com:o/r.git",
]  # fmt: skip


@pytest.mark.parametrize("url", BAD_URLS)
def test_parse_rejects(url):
    with pytest.raises(AppError) as e:
        parse_repo_url(url)
    assert e.value.code == "INVALID_URL"


def test_parse_ref():
    assert parse_repo_url("o/r", "feature/x").ref == "feature/x"
    assert parse_repo_url("o/r", "  ").ref is None
    for bad in ["-evil", "a..b", "x y", "a;b"]:
        with pytest.raises(AppError):
            parse_repo_url("o/r", bad)


def test_clone_default_branch_and_cache_reuse(remote, tmp_path):
    cache = tmp_path / "cache"
    a = clone_repo(RepoSpec("owner", "repo"), cache, f"file://{remote}")
    assert (a.path / "src" / "index.ts").exists() and len(a.commit_sha) == 40
    b = clone_repo(RepoSpec("owner", "repo"), cache, f"file://{remote}")  # refresh path
    assert b.path == a.path and b.commit_sha == a.commit_sha


def test_clone_ref_branch_and_sha(remote, tmp_path):
    cache, base = tmp_path / "cache", f"file://{remote}"
    head = clone_repo(RepoSpec("owner", "repo"), cache, base).commit_sha
    assert clone_repo(RepoSpec("owner", "repo", "feature"), cache, base).commit_sha == head
    assert clone_repo(RepoSpec("owner", "repo", head), cache, base).commit_sha == head


def test_clone_missing_ref_and_repo(remote, tmp_path):
    cache, base = tmp_path / "cache", f"file://{remote}"
    with pytest.raises(AppError) as e:
        clone_repo(RepoSpec("owner", "repo", "nope"), cache, base)
    assert e.value.code == "CLONE_FAILED"
    with pytest.raises(AppError) as e:
        clone_repo(RepoSpec("owner", "missing"), cache, base)
    assert e.value.code in {"REPO_NOT_FOUND", "CLONE_FAILED"}
    assert not any(cache.glob("owner__missing*"))  # failed clones are cleaned up
