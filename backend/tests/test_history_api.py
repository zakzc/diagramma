import queue
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app import __version__
from app.analysis.fetch import RepoSpec, resolve_commit
from app.db import DiagramStore
from app.jobs.manager import JobManager
from app.jobs.pipeline import run_pipeline
from app.main import create_app
from tests.test_jobs_api import parse_sse


def make_client(tmp_path, store=None, pipeline=run_pipeline):
    mgr = JobManager(executor=ThreadPoolExecutor(2), queue_factory=queue.Queue, pipeline=pipeline)
    return TestClient(create_app(mgr, store or DiagramStore(tmp_path / "h.db")))


def patch_remote(monkeypatch, remote, tmp_path):
    from app.analysis import fetch

    real = fetch.clone_repo
    monkeypatch.setattr(
        "app.jobs.pipeline.clone_repo",
        lambda spec: real(spec, tmp_path / "cache", f"file://{remote}"),
    )
    monkeypatch.setattr(
        "app.api.routes.resolve_commit", lambda spec: resolve_commit(spec, f"file://{remote}")
    )


def generate(c, url="owner/repo", ref=None):
    r = c.post("/api/diagrams", json={"url": url, "ref": ref}).json()
    if r["diagramId"]:
        return r["diagramId"], None
    events = parse_sse(c.get(f"/api/jobs/{r['jobId']}/events").text)
    assert events[-1][0] == "done", events[-1]
    return events[-1][1]["diagramId"], events


def test_generate_list_reopen_delete(remote, tmp_path, monkeypatch):
    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        assert c.get("/api/diagrams").json() == []
        did, _ = generate(c)
        rows = c.get("/api/diagrams").json()
        assert [r["id"] for r in rows] == [did]
        assert rows[0]["owner"] == "owner" and rows[0]["container_count"] == 1
        assert "mermaid_c4" not in rows[0]
        full = c.get(f"/api/diagrams/{did}").json()
        assert full["mermaid_c4"].startswith("C4Component") and full["model"]["containers"]
        assert c.delete(f"/api/diagrams/{did}").status_code == 204
        assert c.get("/api/diagrams").json() == []
        assert c.get(f"/api/diagrams/{did}").json()["error"]["code"] == "DIAGRAM_NOT_FOUND"
        assert c.delete(f"/api/diagrams/{did}").json()["error"]["code"] == "DIAGRAM_NOT_FOUND"


def test_history_survives_a_restart(remote, tmp_path, monkeypatch):
    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
    with make_client(tmp_path) as c2:  # fresh app + store on the same database file
        assert [r["id"] for r in c2.get("/api/diagrams").json()] == [did]
        assert c2.get(f"/api/diagrams/{did}").json()["mermaid_c4"].startswith("C4Component")


def test_resubmitting_an_unchanged_repo_reuses_the_entry_without_a_job(
    remote, tmp_path, monkeypatch
):
    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, events = generate(c)
        assert events is not None
        again = c.post("/api/diagrams", json={"url": "https://github.com/owner/repo"}).json()
        assert again == {"jobId": None, "diagramId": did}
        assert len(c.get("/api/diagrams").json()) == 1


def test_new_commit_makes_a_new_entry(remote, tmp_path, monkeypatch):
    import subprocess

    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        first, _ = generate(c)
        work = tmp_path / "work"
        (work / "src" / "extra.ts").write_text("x\n")
        for args in (
            ["add", "-A"],
            ["commit", "-qm", "two"],
            ["push", "-q", str(remote / "owner/repo.git"), "HEAD:main"],
        ):
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                cwd=work, check=True, capture_output=True,
            )  # fmt: skip
        second, events = generate(c)
        assert second != first and events is not None  # a real job ran
        assert len(c.get("/api/diagrams").json()) == 2


def test_other_tool_version_regenerates_in_place(remote, tmp_path, monkeypatch):
    patch_remote(monkeypatch, remote, tmp_path)
    store = DiagramStore(tmp_path / "h.db")
    with make_client(tmp_path, store) as c:
        did, _ = generate(c)
        import sqlite3

        with sqlite3.connect(tmp_path / "h.db") as con:
            con.execute("UPDATE diagrams SET tool_version = '0.0.1'")
        again, events = generate(c)  # version differs -> job runs, entry refreshed
        assert again == did and events is not None
        assert store.get(did).tool_version == __version__


def test_unresolvable_commit_falls_back_to_a_job(remote, tmp_path, monkeypatch):
    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
        monkeypatch.setattr("app.api.routes.resolve_commit", lambda spec: None)
        again, events = generate(c)
        assert events is not None and again == did  # job ran, but upsert reused the entry
        assert len(c.get("/api/diagrams").json()) == 1


def test_resolve_commit_variants(remote):
    base = f"file://{remote}"
    sha = resolve_commit(RepoSpec("owner", "repo"), base)
    assert sha and len(sha) == 40
    assert resolve_commit(RepoSpec("owner", "repo", "main"), base) == sha
    assert resolve_commit(RepoSpec("owner", "repo", "feature"), base) == sha
    assert resolve_commit(RepoSpec("owner", "repo", sha), base) == sha
    assert resolve_commit(RepoSpec("owner", "repo", "nope"), base) is None
    assert resolve_commit(RepoSpec("owner", "missing"), base) is None


def test_edit_save_discard_and_isolation(remote, tmp_path, monkeypatch):
    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
        gen = c.get(f"/api/diagrams/{did}").json()
        assert gen["edited_c4"] is None and gen["edited_flowchart"] is None

        r = c.put(f"/api/diagrams/{did}/edits/c4", json={"text": "C4Component\n  title mine\n"})
        assert r.status_code == 200
        assert r.json()["edited_c4"] == "C4Component\n  title mine\n"
        assert r.json()["edited_flowchart"] is None  # each format keeps its own edit
        assert r.json()["mermaid_c4"] == gen["mermaid_c4"]  # generated text is never modified

        again = c.get(f"/api/diagrams/{did}").json()  # persisted, not just echoed
        assert again["edited_c4"] == "C4Component\n  title mine\n"

        r = c.put(f"/api/diagrams/{did}/edits/flowchart", json={"text": "flowchart TD\n a-->b\n"})
        assert r.json()["edited_flowchart"] == "flowchart TD\n a-->b\n"

        assert c.delete(f"/api/diagrams/{did}/edits/c4").json()["edited_c4"] is None
        assert c.get(f"/api/diagrams/{did}").json()["edited_flowchart"] is not None


def test_saving_the_generated_text_is_not_an_edit(remote, tmp_path, monkeypatch):
    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
        gen = c.get(f"/api/diagrams/{did}").json()["mermaid_c4"]
        c.put(f"/api/diagrams/{did}/edits/c4", json={"text": "x"})
        assert (
            c.put(f"/api/diagrams/{did}/edits/c4", json={"text": gen}).json()["edited_c4"] is None
        )


def test_edit_errors(remote, tmp_path, monkeypatch):
    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
        assert (
            c.put("/api/diagrams/nope/edits/c4", json={"text": "x"}).json()["error"]["code"]
            == "DIAGRAM_NOT_FOUND"
        )
        assert c.delete("/api/diagrams/nope/edits/c4").status_code == 404
        assert c.put(f"/api/diagrams/{did}/edits/svg", json={"text": "x"}).status_code == 422
        too_big = c.put(f"/api/diagrams/{did}/edits/c4", json={"text": "x" * 2_000_001})
        assert too_big.status_code == 422 and too_big.json()["error"]["code"] == "VALIDATION_ERROR"


def test_saved_edit_survives_restart_and_regeneration(remote, tmp_path, monkeypatch):
    import sqlite3

    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
        c.put(f"/api/diagrams/{did}/edits/c4", json={"text": "my fix"})
    with sqlite3.connect(tmp_path / "h.db") as con:
        con.execute("UPDATE diagrams SET tool_version = '0.0.1'")
    with make_client(tmp_path) as c2:  # restart, then re-generate with a newer tool version
        assert c2.get(f"/api/diagrams/{did}").json()["edited_c4"] == "my fix"
        again, events = generate(c2)
        assert again == did and events is not None
        rec = c2.get(f"/api/diagrams/{did}").json()
        assert rec["edited_c4"] == "my fix" and rec["tool_version"] == __version__
        assert rec["mermaid_c4"] != "my fix"  # the original generated text is kept alongside
