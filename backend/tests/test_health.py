from fastapi.testclient import TestClient

from app import __version__
from app.main import app


def test_health():
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": __version__}


def test_openapi_has_model_schemas():
    schema = TestClient(app).get("/openapi.json").json()
    assert "Health" in schema["components"]["schemas"]
