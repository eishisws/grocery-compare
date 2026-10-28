from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_basket_shape_validated() -> None:
    # Empty items are rejected before any DB access happens
    resp = client.post("/basket/totals", json={"lat": 0.0, "lon": 0.0, "items": []})
    assert resp.status_code == 422
