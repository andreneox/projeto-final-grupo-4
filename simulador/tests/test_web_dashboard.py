from fastapi.testclient import TestClient

from web.dashboard import create_dashboard_app


def sample_snapshot() -> dict:
    return {
        "opcua": {
            "connected": False,
            "status": "teste",
            "last_seen": None,
            "stations": {},
        },
        "analytics": {
            "stations": {},
            "line": {},
            "downtime_minutes": {},
        },
    }


def test_dashboard_serves_page_api_and_websocket() -> None:
    client = TestClient(create_dashboard_app(sample_snapshot))

    page = client.get("/")
    assert page.status_code == 200
    assert "Dashboard da Linha" in page.text
    assert 'data-testid="station-table"' in page.text
    assert client.get("/api/snapshot").json() == sample_snapshot()

    with client.websocket_connect("/ws") as websocket:
        assert websocket.receive_json() == sample_snapshot()


def test_dashboard_serves_the_station_charts_and_e07_assets() -> None:
    with TestClient(create_dashboard_app(sample_snapshot)) as client:
        assert client.get("/graficos").status_code == 200
        assert client.get("/instrucao/e07").status_code == 200
        assert client.get("/api/instruction/e07").json()["slide"] == 1
        asset = client.get("/static/instructions/e07/slide-01.png")
        assert asset.status_code == 200
        assert asset.headers["content-type"] == "image/png"
