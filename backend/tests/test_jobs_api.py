import json
import queue
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.analysis.fetch import RepoSpec
from app.errors import AppError
from app.jobs.manager import JobManager
from app.jobs.pipeline import run_pipeline
from app.main import create_app


def parse_sse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        ev = data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = json.loads(line.split(":", 1)[1])
        if ev:
            out.append((ev, data))
    return out


def client(pipeline) -> TestClient:
    mgr = JobManager(executor=ThreadPoolExecutor(2), queue_factory=queue.Queue, pipeline=pipeline)
    return TestClient(create_app(mgr))


def test_invalid_url_error_shape():
    with client(run_pipeline) as c:
        r = c.post("/api/diagrams", json={"url": "https://evil.com/x/y"})
        assert r.status_code == 400
        assert r.json() == {
            "error": {"code": "INVALID_URL", "message": r.json()["error"]["message"]}
        }
        assert c.post("/api/diagrams", json={}).json()["error"]["code"] == "VALIDATION_ERROR"
        assert c.get("/api/jobs/nope/events").json()["error"]["code"] == "JOB_NOT_FOUND"


def test_job_streams_stages_then_done():
    def pipeline(spec: RepoSpec, q):
        q.put({"event": "stage", "data": {"stage": "cloning", "message": "c"}})
        q.put({"event": "stage", "data": {"stage": "scanning", "message": "s"}})
        return {"diagramId": None, "files": 3}

    with client(pipeline) as c:
        job = c.post("/api/diagrams", json={"url": "o/r"}).json()["jobId"]
        events = parse_sse(c.get(f"/api/jobs/{job}/events").text)
    assert [e for e, _ in events] == ["stage", "stage", "done"]
    assert events[-1][1]["files"] == 3


def test_job_error_event():
    def pipeline(spec, q):
        raise AppError("REPO_NOT_FOUND", "Repository not found.")

    with client(pipeline) as c:
        job = c.post("/api/diagrams", json={"url": "o/r"}).json()["jobId"]
        events = parse_sse(c.get(f"/api/jobs/{job}/events").text)
    assert events == [("error", {"code": "REPO_NOT_FOUND", "message": "Repository not found."})]


def test_unexpected_exception_becomes_internal_error():
    def pipeline(spec, q):
        raise RuntimeError("boom")

    with client(pipeline) as c:
        job = c.post("/api/diagrams", json={"url": "o/r"}).json()["jobId"]
        events = parse_sse(c.get(f"/api/jobs/{job}/events").text)
    assert events[0][0] == "error" and events[0][1]["code"] == "INTERNAL_ERROR"


def test_timeout():
    import time

    def pipeline(spec, q):
        time.sleep(1)

    mgr = JobManager(
        executor=ThreadPoolExecutor(1), queue_factory=queue.Queue, pipeline=pipeline, timeout_s=0.2
    )
    with TestClient(create_app(mgr)) as c:
        job = c.post("/api/diagrams", json={"url": "o/r"}).json()["jobId"]
        events = parse_sse(c.get(f"/api/jobs/{job}/events").text)
    assert events[0][1]["code"] == "TIMEOUT"


def test_same_repo_reuses_running_job():
    import threading

    gate = threading.Event()

    def pipeline(spec, q):
        gate.wait(2)
        return {}

    with client(pipeline) as c:
        a = c.post("/api/diagrams", json={"url": "o/r"}).json()["jobId"]
        b = c.post("/api/diagrams", json={"url": "https://github.com/o/r"}).json()["jobId"]
        other = c.post("/api/diagrams", json={"url": "o/r", "ref": "dev"}).json()["jobId"]
        gate.set()
    assert a == b and other != a


def test_real_pipeline_against_local_remote(remote, tmp_path, monkeypatch):
    from app.analysis import fetch

    real = fetch.clone_repo
    monkeypatch.setattr(
        "app.jobs.pipeline.clone_repo",
        lambda spec: real(spec, tmp_path / "cache", f"file://{remote}"),
    )
    with client(run_pipeline) as c:
        job = c.post("/api/diagrams", json={"url": "owner/repo"}).json()["jobId"]
        events = parse_sse(c.get(f"/api/jobs/{job}/events").text)
    names = [e for e, _ in events]
    assert names == ["stage"] * 4 + ["done"]
    done = events[-1][1]
    assert done["files"] == 1 and done["manifests"] == ["package.json"]
    assert done["containers"] == 1 and done["diagramId"] and "diagram" not in done
    assert done["languages"] == {"typescript": 1} and len(done["commit"]) == 40


@pytest.mark.parametrize("empty", [True])
def test_nothing_detected(empty, tmp_path, monkeypatch):
    from app.analysis.fetch import ClonedRepo

    (tmp_path / "README.md").write_text("hi")
    monkeypatch.setattr("app.jobs.pipeline.clone_repo", lambda spec: ClonedRepo(tmp_path, "a" * 40))
    with client(run_pipeline) as c:
        job = c.post("/api/diagrams", json={"url": "o/r"}).json()["jobId"]
        events = parse_sse(c.get(f"/api/jobs/{job}/events").text)
    assert events[-1][1]["code"] == "NOTHING_DETECTED"
