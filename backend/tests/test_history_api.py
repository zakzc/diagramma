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


def test_views_and_depth_scoped_edits(remote, tmp_path, monkeypatch):
    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
        rec = c.get(f"/api/diagrams/{did}").json()
        assert rec["max_depth"] >= 1 and 1 <= rec["auto_depth"] <= rec["max_depth"]
        assert rec["saved_edits"] == []
        depth = rec["auto_depth"]

        v = c.get(f"/api/diagrams/{did}/views/c4/{depth}").json()
        assert v["generated"] == rec["mermaid_c4"]  # the stored text is the auto-depth view
        assert v["edited"] is None and v["nodes"] >= 1 and v["edges"] >= 0
        assert v["hubs"] == 0  # a tiny repo has no shared modules to collapse
        flow = c.get(f"/api/diagrams/{did}/views/flowchart/{depth}").json()
        assert flow["generated"] == rec["mermaid_flowchart"] and flow["generated"].startswith(
            "flowchart"
        )

        r = c.put(
            f"/api/diagrams/{did}/edits/c4/{depth}", json={"text": "C4Component\n title mine\n"}
        )
        assert r.status_code == 200 and r.json()["edited"] == "C4Component\n title mine\n"
        assert r.json()["generated"] == v["generated"]  # the generated text is never modified
        # an edit belongs to one (format, depth) only
        assert c.get(f"/api/diagrams/{did}/views/flowchart/{depth}").json()["edited"] is None
        assert c.get(f"/api/diagrams/{did}").json()["saved_edits"] == [
            {"format": "c4", "depth": depth}
        ]

        r = c.delete(f"/api/diagrams/{did}/edits/c4/{depth}")
        assert (
            r.json()["edited"] is None and c.get(f"/api/diagrams/{did}").json()["saved_edits"] == []
        )


def test_saving_the_generated_text_is_not_an_edit(remote, tmp_path, monkeypatch):
    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
        gen = c.get(f"/api/diagrams/{did}/views/c4/1").json()["generated"]
        c.put(f"/api/diagrams/{did}/edits/c4/1", json={"text": "x"})
        assert c.put(f"/api/diagrams/{did}/edits/c4/1", json={"text": gen}).json()["edited"] is None


def test_view_and_edit_errors(remote, tmp_path, monkeypatch):
    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
        top = c.get(f"/api/diagrams/{did}").json()["max_depth"]
        for depth in (0, top + 1, -3):
            r = c.get(f"/api/diagrams/{did}/views/c4/{depth}")
            assert r.status_code == 422, depth
            assert r.json()["error"]["code"] in {"INVALID_DEPTH", "VALIDATION_ERROR"}
        bad = c.put(f"/api/diagrams/{did}/edits/c4/{top + 1}", json={"text": "x"})
        assert bad.json()["error"]["code"] == "INVALID_DEPTH"
        assert c.delete(f"/api/diagrams/{did}/edits/c4/{top + 1}").status_code == 422
        assert c.get("/api/diagrams/nope/views/c4/1").json()["error"]["code"] == "DIAGRAM_NOT_FOUND"
        assert c.put("/api/diagrams/nope/edits/c4/1", json={"text": "x"}).status_code == 404
        assert c.delete("/api/diagrams/nope/edits/c4/1").status_code == 404
        assert c.get(f"/api/diagrams/{did}/views/svg/1").status_code == 422
        assert c.get(f"/api/diagrams/{did}/views/c4/one").status_code == 422
        big = c.put(f"/api/diagrams/{did}/edits/c4/1", json={"text": "x" * 2_000_001})
        assert big.status_code == 422 and big.json()["error"]["code"] == "VALIDATION_ERROR"


def test_saved_edit_survives_restart_and_regeneration(remote, tmp_path, monkeypatch):
    import sqlite3

    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
        c.put(f"/api/diagrams/{did}/edits/c4/1", json={"text": "my fix"})
    with sqlite3.connect(tmp_path / "h.db") as con:
        con.execute("UPDATE diagrams SET tool_version = '0.0.1'")
    with make_client(tmp_path) as c2:  # restart, then re-generate with a newer tool version
        assert c2.get(f"/api/diagrams/{did}/views/c4/1").json()["edited"] == "my fix"
        again, events = generate(c2)
        assert again == did and events is not None
        rec = c2.get(f"/api/diagrams/{did}").json()
        assert rec["tool_version"] == __version__
        view = c2.get(f"/api/diagrams/{did}/views/c4/1").json()
        assert view["edited"] == "my fix" and view["generated"] != "my fix"  # kept alongside


def test_deleting_a_diagram_removes_its_edits(remote, tmp_path, monkeypatch):
    import sqlite3

    patch_remote(monkeypatch, remote, tmp_path)
    with make_client(tmp_path) as c:
        did, _ = generate(c)
        c.put(f"/api/diagrams/{did}/edits/c4/1", json={"text": "x"})
        c.delete(f"/api/diagrams/{did}")
    with sqlite3.connect(tmp_path / "h.db") as con:
        assert con.execute("SELECT count(*) FROM edits").fetchone()[0] == 0
