from fastapi.testclient import TestClient

from fieldwise import __version__
from fieldwise.api.app import create_app


def test_health_reports_version() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
