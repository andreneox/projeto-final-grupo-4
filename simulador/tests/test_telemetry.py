from services.telemetry import PROCESS_STATUS_NODE, TelemetryStore


def test_telemetry_is_updated_only_by_opcua_paths() -> None:
    store = TelemetryStore()
    store.set_connection(True, "conectado")
    store.update("P12/Andon/Material", True)
    store.update("P12/TaktTime", 60.0)
    store.update("P12/UltimoCiclo", 57.5)

    snapshot = store.snapshot(10)

    assert snapshot["connected"] is True
    assert snapshot["stations"]["12"] == {
        "andon": {
            "qualidade": None,
            "equipamento": None,
            "processo": None,
            "material": True,
        },
        "takt_time": 60.0,
        "cycle_time": 57.5,
        "process_status": None,
    }


def test_unknown_paths_do_not_change_telemetry() -> None:
    store = TelemetryStore()
    before = store.snapshot(10)["stations"]
    store.update("P99/Unknown", 123)
    assert store.snapshot(10)["stations"] == before


def test_process_statuses_follow_station_order_and_clear_missing_values() -> None:
    store = TelemetryStore()
    store.update(PROCESS_STATUS_NODE, [0, 1, 2, 3, -1, 99, True, 0, 1, 2, 3, 2])

    stations = store.snapshot(10)["stations"]
    assert [station["process_status"] for station in stations.values()] == [
        0, 1, 2, 3, None, None, None, 0, 1, 2, 3, 2,
    ]
    store.update(PROCESS_STATUS_NODE, None)
    assert all(station["process_status"] is None for station in store.snapshot(10)["stations"].values())
