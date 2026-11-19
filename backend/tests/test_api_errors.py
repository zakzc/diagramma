from fastapi.testclient import TestClient

from app.main import app


def envelope(r):
    body = r.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}
    return body["error"]["code"]


def test_every_error_uses_the_error_envelope():
    with TestClient(app) as c:
        assert (c.get("/api/nope").status_code, envelope(c.get("/api/nope"))) == (404, "NOT_FOUND")
        r = c.post("/api/health")
        assert (r.status_code, envelope(r)) == (405, "METHOD_NOT_ALLOWED")
        assert envelope(c.post("/api/diagrams", json={})) == "VALIDATION_ERROR"
        assert envelope(c.post("/api/diagrams", json={"url": "ftp://x/y"})) == "INVALID_URL"
        assert envelope(c.get("/api/diagrams/missing")) == "DIAGRAM_NOT_FOUND"
        assert envelope(c.get("/api/jobs/missing/events")) == "JOB_NOT_FOUND"


def test_unexpected_errors_do_not_leak_details(tmp_path, monkeypatch):
    from app.main import create_app

    monkeypatch.setattr("app.main.FRONTEND_DIST", tmp_path / "none")  # no static mount in the way
    fresh = create_app()

    @fresh.get("/api/_boom")
    def boom():
        raise RuntimeError("secret internal detail")

    with TestClient(fresh, raise_server_exceptions=False) as c:
        r = c.get("/api/_boom")
    assert r.status_code == 500 and envelope(r) == "INTERNAL_ERROR"
    assert "secret" not in r.text


def test_cors_allows_only_the_local_frontend():
    with TestClient(app) as c:

        def preflight(origin):
            return c.options(
                "/api/health",
                headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
            )

        assert preflight("http://localhost:5173").headers["access-control-allow-origin"] == (
            "http://localhost:5173"
        )
        assert preflight("http://127.0.0.1:5173").status_code == 200
        evil = preflight("https://evil.example")
        assert evil.status_code == 400 and "access-control-allow-origin" not in evil.headers
        plain = c.get("/api/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in plain.headers


def test_server_entry_point_binds_loopback_only():
    import app.__main__ as entry

    assert entry.HOST == "127.0.0.1"
