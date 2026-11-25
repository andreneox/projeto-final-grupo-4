import asyncio
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from io import BytesIO
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from communications.desktop_start import DesktopStartClient, DesktopStartError
from domain.runtime_events import AndonRuntime
from services.process_configuration import ProcessConfiguration, ProcessConfigurationStore
from tools.reference_receiver import ReceiverDatabase
from web.dashboard import create_dashboard_app


def configuration(value=42.5):
    return {"stations": [
        {"station": station, "cycle_time_seconds": value + station,
         "has_prototype": int(station % 2 == 0)} for station in range(1, 13)
    ]}


def test_import_cycle_base_and_start_through_gateway(tmp_path):
    class Gateway:
        def __init__(self):
            self.times = None
            self.confirmed_at = None
            self.reject_upload = False

        @staticmethod
        def completed(value):
            future = Future()
            future.set_result(value)
            return future

        def request_cycle_base_ready(self):
            return self.completed(self.times is not None)

        def request_cycle_base(self, times):
            if self.reject_upload:
                future = Future()
                future.set_exception(RuntimeError("Falha ao conferir a base."))
                return future
            self.times = times
            return self.completed(None)

        def request_simulation_start(self):
            return self.completed(self.confirmed_at)

    gateway = Gateway()
    sessions = []
    database = ReceiverDatabase(tmp_path / "receiver.db")
    client = TestClient(create_dashboard_app(
        lambda: {"imported_cycle_base": database.imported_cycle_base()},
        plc_control=gateway, plc_session_started=sessions.append,
        cycle_base_imported=database.save_imported_cycle_base,
    ))
    assert client.get("/api/process/cycle-base").json() == {"available": True, "ready": False}
    url = "/api/process/cycle-base?filename=base.xlsx"
    assert client.post(url, content=b"invalid").status_code == 422
    assert gateway.times is None
    assert database.imported_cycle_base() is None

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Medida", *(f"P{station:02d}" for station in range(1, 13))])
    for cycle in range(12):
        sheet.append(["Takt time", *((60 + station + cycle) for station in range(1, 13))])
        sheet.append(["Último ciclo", *((station * 100 + cycle) / 10 for station in range(1, 13))])
    buffer = BytesIO()
    workbook.save(buffer)
    response = client.post(url, content=buffer.getvalue())
    assert response.status_code == 200, response.text
    assert gateway.times[:12] == [(100 + index) / 10 for index in range(12)]
    assert gateway.times[-12:] == [(1200 + index) / 10 for index in range(12)]
    assert client.get("/api/process/cycle-base").json()["ready"] is True
    imported = {"filename": "base.xlsx", "takt_times": list(range(61, 73))}
    assert ReceiverDatabase(database.path).imported_cycle_base() == imported
    assert client.get("/api/snapshot").json()["imported_cycle_base"] == imported

    gateway.reject_upload = True
    assert client.post("/api/process/cycle-base?filename=outra.xlsx", content=buffer.getvalue()).status_code == 503
    assert database.imported_cycle_base() == imported

    assert client.post("/api/process/start", headers={"Origin": "https://elsewhere.example"}).status_code == 403
    assert client.post("/api/process/start").json()["confirmed"] is False
    assert sessions == []
    gateway.confirmed_at = datetime.now(timezone.utc)
    assert client.post("/api/process/start").json()["confirmed"] is True
    assert sessions == [gateway.confirmed_at]


def test_configuration_persists_and_survives_restart(tmp_path):
    path = tmp_path / "receiver.db"
    store = ProcessConfigurationStore(path, 57.5)
    client = TestClient(create_dashboard_app(lambda: {}, store))
    initial = client.get("/api/process/configuration").json()
    assert len(initial["stations"]) == 12
    assert all(row["cycle_time_seconds"] == 57.5 and row["has_prototype"] == 0
               for row in initial["stations"])
    response = client.put("/api/process/configuration", json=configuration())
    assert response.status_code == 200
    assert response.json()["stations"] == configuration()["stations"]
    # Reading/opening the screen has no effect on the stored data.
    assert client.get("/api/process/configuration").json() == response.json()
    assert ProcessConfigurationStore(path, 99).read() == response.json()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM process_configuration").fetchone()[0] == 12


def test_shift_plan_and_confirmed_reset_preserve_the_measurement_and_previous_day(tmp_path):
    class Gateway:
        reject = True

        def request_base_reset(self):
            result = Future()
            if self.reject:
                result.set_exception(RuntimeError("O CLP não confirmou o reset"))
            else:
                result.set_result(now)
            return result

        def request_simulation_start(self):
            result = Future()
            result.set_result(now + timedelta(minutes=1))
            return result

    db = ReceiverDatabase(tmp_path / "receiver.db")
    now = datetime(2026, 11, 21, 14, 0, tzinfo=db.timezone)
    db.begin_plc_session(now - timedelta(minutes=10))
    for station, age in ((1, timedelta(days=1)), (2, timedelta(minutes=5))):
        db.apply_runtime(AndonRuntime(
            station=station, occurred_at=now - age, button_id=1, is_on=True,
        ))
    gateway = Gateway()
    client = TestClient(create_dashboard_app(
        lambda: {}, plc_control=gateway, plc_session_started=db.begin_plc_session,
        read_plan=db.production_plan, save_plan=db.save_production_plan,
        plc_base_cleared=db.clear_plc_base,
    ))
    plan_url = "/api/process/production-plan"
    assert client.get(plan_url).json()["production_target"] == 480
    assert client.put(plan_url, json={"production_target": 0, "available_time_minutes": 300}).status_code == 422
    plan = {"production_target": 600, "available_time_minutes": 300.5}
    assert client.put(plan_url, json=plan).json() == plan
    assert ReceiverDatabase(db.path).production_plan().model_dump() == plan
    before = db.dashboard_metrics(now, "00:00", 480, plc_production_count=7)
    assert before["timing"]["elapsed_seconds"] == 600
    assert before["timing"]["estimated_production"] == 19
    assert before["production_counts"]["line"]["defective"] == 1

    reset_url = "/api/process/clear-base"
    assert client.post(reset_url, headers={"Origin": "https://elsewhere.example"}).status_code == 403
    assert client.post(reset_url).status_code == 503
    assert db.dashboard_metrics(now, "00:00", 480, plc_production_count=7) == before
    gateway.reject = False
    assert client.post(reset_url).status_code == 200
    with sqlite3.connect(db.path) as connection:
        assert connection.execute("SELECT station FROM defect_item").fetchall() == [(1,)]
    late_event = AndonRuntime(station=3, occurred_at=now - timedelta(seconds=1), button_id=1, is_on=True)
    assert db.apply_runtime(late_event)["result"] == "ignored_before_reset"
    after = db.dashboard_metrics(now + timedelta(seconds=20), "00:00", 480, plc_production_count=0)
    assert after["timing"]["elapsed_seconds"] == 0
    assert after["timing"]["measurement_started_at"] is None
    assert after["production_counts"]["line"]["total"] == 0
    assert client.get(plan_url).json() == plan

    assert client.post("/api/process/start").json()["confirmed"] is True
    restarted = db.dashboard_metrics(now + timedelta(seconds=120), "00:00", 480, plc_production_count=1)
    assert restarted["timing"]["elapsed_seconds"] == 60
    assert restarted["production_counts"]["line"]["good"] == 1


@pytest.mark.parametrize("field,value", [
    ("cycle_time_seconds", 0), ("cycle_time_seconds", -1),
    ("cycle_time_seconds", "12"), ("cycle_time_seconds", True),
    ("cycle_time_seconds", None), ("has_prototype", 2),
    ("has_prototype", True), ("has_prototype", "1"),
    ("station", 0), ("station", 13), ("station", True),
])
def test_invalid_values_do_not_change_database(tmp_path, field, value):
    store = ProcessConfigurationStore(tmp_path / "r.db")
    client = TestClient(create_dashboard_app(lambda: {}, store))
    before = store.read()
    data = configuration()
    data["stations"][0][field] = value
    assert client.put("/api/process/configuration", json=data).status_code == 422
    assert store.read() == before


@pytest.mark.parametrize("kind", ["duplicate", "missing", "extra"])
def test_must_supply_exactly_twelve_distinct_stations(tmp_path, kind):
    store = ProcessConfigurationStore(tmp_path / "r.db")
    client = TestClient(create_dashboard_app(lambda: {}, store))
    data = configuration()
    if kind == "duplicate":
        data["stations"][0]["station"] = 2
    elif kind == "missing":
        data["stations"].pop()
    else:
        data["stations"].append(data["stations"][0])
    before = store.read()
    assert client.put("/api/process/configuration", json=data).status_code == 422
    assert store.read() == before


def test_failed_transaction_rolls_back_all_stations(tmp_path):
    store = ProcessConfigurationStore(tmp_path / "r.db")
    before = store.read()
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER fail_save BEFORE UPDATE ON process_configuration
                      WHEN NEW.station = 6 BEGIN SELECT RAISE(ABORT, 'test'); END""")
    client = TestClient(create_dashboard_app(lambda: {}, store))
    assert client.put("/api/process/configuration", json=configuration()).status_code == 503
    assert store.read() == before


@pytest.mark.parametrize("value", [float("inf"), float("nan"), float("-inf")])
def test_nonfinite_times_are_rejected(value):
    with pytest.raises(ValueError):
        ProcessConfiguration.model_validate(configuration(value))


@pytest.mark.parametrize("result", [0, 1])
def test_start_calls_desktop_without_any_input(result):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=result)
    desktop = DesktopStartClient("http://desktop.local/start", transport=httpx.MockTransport(handler))
    client = TestClient(create_dashboard_app(lambda: {}, desktop_start=desktop))
    response = client.post("/api/process/start")
    assert response.status_code == 200
    assert response.json()["result"] == result
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].content == b""
    assert str(requests[0].url) == "http://desktop.local/start"


@pytest.mark.parametrize("result", [2, -1, True, False, 0.0, "0", {"result": 0}, None])
def test_start_rejects_invalid_desktop_response(result):
    desktop = DesktopStartClient("http://desktop.local/start",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=result)))
    client = TestClient(create_dashboard_app(lambda: {}, desktop_start=desktop))
    assert client.post("/api/process/start").status_code == 502


def test_missing_desktop_api_reports_unavailable():
    client = TestClient(create_dashboard_app(lambda: {}))
    response = client.post("/api/process/start")
    assert response.status_code == 503
    assert "ainda não configurada" in response.json()["detail"]


@pytest.mark.parametrize("url", ["http://[broken", "http://desktop:invalid/start",
                                  "ftp://desktop/start", "http://desktop/start?x=1"])
def test_invalid_desktop_url_reports_configuration_error(url):
    client = TestClient(create_dashboard_app(lambda: {}, desktop_start=DesktopStartClient(url)))
    assert client.post("/api/process/start").status_code == 503


@pytest.mark.parametrize("failure", ["timeout", "connection", "http", "json"])
def test_desktop_failure_never_reports_success(failure):
    expected = {"timeout": 504, "connection": 502, "http": 502, "json": 502}
    calls = []
    def handler(request):
        calls.append(request)
        if failure == "timeout": raise httpx.ReadTimeout("test", request=request)
        if failure == "connection": raise httpx.ConnectError("test", request=request)
        if failure == "http": return httpx.Response(500)
        return httpx.Response(200, content=b"invalid")
    desktop = DesktopStartClient("http://desktop.local/start", transport=httpx.MockTransport(handler))
    client = TestClient(create_dashboard_app(lambda: {}, desktop_start=desktop))
    assert client.post("/api/process/start").status_code == expected[failure]
    assert len(calls) == 1


def test_concurrent_start_is_rejected_without_second_desktop_call():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def handler(request):
            calls.append(request)
            entered.set()
            await release.wait()
            return httpx.Response(200, json=0)
        desktop = DesktopStartClient("http://desktop.local/start", transport=httpx.MockTransport(handler))
        first = asyncio.create_task(desktop.start())
        await entered.wait()
        with pytest.raises(DesktopStartError) as error:
            await desktop.start()
        assert error.value.status_code == 409
        release.set()
        assert await first == 0
        assert len(calls) == 1
    asyncio.run(scenario())
