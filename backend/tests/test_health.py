def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "app" in data
    assert "version" in data


def test_readiness_check_verifies_database_connection(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_check_hides_database_connection_errors(client, monkeypatch):
    from app.core import database

    class UnavailableEngine:
        def connect(self):
            from sqlalchemy.exc import OperationalError

            raise OperationalError("connect", {}, RuntimeError("private connection detail"))

    monkeypatch.setattr(database, "engine", UnavailableEngine())
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "private connection detail" not in response.text
