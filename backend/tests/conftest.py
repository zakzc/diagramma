import subprocess
from pathlib import Path

import pytest


def git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True,
    )  # fmt: skip


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    """A fake 'github': <base>/owner/repo.git with two commits and a branch."""
    work = tmp_path / "work"
    work.mkdir()
    git("init", "-q", "-b", "main", cwd=work)
    (work / "package.json").write_text('{"name":"demo"}')
    (work / "src").mkdir()
    (work / "src" / "index.ts").write_text("import x from './a'\nexport {}\n")
    (work / "src" / "index.test.ts").write_text("test()\n")
    git("add", "-A", cwd=work)
    git("commit", "-qm", "one", cwd=work)
    git("branch", "feature", cwd=work)
    base = tmp_path / "remote"
    (base / "owner").mkdir(parents=True)
    git("clone", "-q", "--bare", str(work), str(base / "owner" / "repo.git"), cwd=tmp_path)
    return base


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path_factory, monkeypatch):
    """Never touch the real history database or clone cache from tests."""
    data = tmp_path_factory.mktemp("data")
    monkeypatch.setenv("DIAGRAMMA_DATA_DIR", str(data))
    monkeypatch.setattr("app.analysis.fetch.CACHE_DIR", data / "repos")
