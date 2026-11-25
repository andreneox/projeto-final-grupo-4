from json import dumps
from types import SimpleNamespace

import pytest

from domain.work_instruction import INSTRUCTION_NODE
from services.telemetry import PROCESS_STATUS_NODE, TelemetryStore


@pytest.fixture
def line(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr("services.telemetry.time", SimpleNamespace(monotonic=lambda: clock.now))
    telemetry = TelemetryStore()
    telemetry.set_connection(True, "conectado")

    def process_status(value):
        telemetry.update(PROCESS_STATUS_NODE, [0] * 6 + [value] + [0] * 5)

    return telemetry, clock, process_status


def test_instruction_follows_p07_transitions_and_the_36_second_sequence(line):
    telemetry, clock, process_status = line
    process_status(2)
    assert telemetry.instruction_snapshot()["status"] == "waiting"
    process_status(1)
    process_status(2)
    cycle = telemetry.instruction_snapshot()["cycle_id"]
    for elapsed, slide in ((0, 2), (7, 3), (14, 4), (29, 5), (36, 1), (40, 1)):
        clock.now = 100 + elapsed
        process_status(2)
        state = telemetry.instruction_snapshot()
        assert state["source"] == "plc"
        assert state["slide"] == slide
        assert state["cycle_id"] == cycle
        assert state["status"] == ("running" if elapsed < 36 else "complete")

    process_status(3)
    assert telemetry.instruction_snapshot()["short_cycle"] is False
    process_status(2)
    clock.now += 32
    process_status(3)
    state = telemetry.instruction_snapshot()
    assert (state["status"], state["slide"], state["cycle_time_seconds"]) == ("complete", 1, 32)
    assert state["short_cycle"] is True and state["cycle_id"] != cycle


def test_andon_interrupts_the_cycle_until_the_next_start(line):
    telemetry, clock, process_status = line
    process_status(0)
    process_status(2)
    clock.now += 8
    telemetry.update("P03/Andon/Material", True)
    state = telemetry.instruction_snapshot()
    assert (state["status"], state["slide"], state["stop_station"], state["stop_category"]) == (
        "paused", 1, 3, "material",
    )
    process_status(3)
    process_status(2)
    telemetry.update("P03/Andon/Material", False)
    assert telemetry.instruction_snapshot()["status"] == "interrupted"
    process_status(2)
    assert telemetry.instruction_snapshot()["slide"] == 1
    process_status(3)
    process_status(2)
    assert telemetry.instruction_snapshot()["slide"] == 2


def test_invalid_process_status_and_reconnection_wait_for_a_fresh_start(line):
    telemetry, _, process_status = line
    process_status(1)
    process_status(2)
    process_status(-1)
    assert telemetry.instruction_snapshot()["status"] == "disconnected"
    process_status(2)
    assert telemetry.instruction_snapshot()["status"] == "waiting"
    telemetry.set_connection(False, "desconectado")
    assert telemetry.instruction_snapshot()["status"] == "disconnected"
    process_status(1)
    process_status(2)
    telemetry.set_connection(True, "conectado")
    assert telemetry.instruction_snapshot()["status"] == "waiting"


def test_legacy_simulator_still_supplies_slides_without_plc_status(line):
    telemetry, clock, _ = line
    telemetry.update(INSTRUCTION_NODE, dumps({"station": 7, "status": "running", "slide": 4}))
    state = telemetry.instruction_snapshot()
    assert (state["source"], state["slide"]) == ("simulator", 4)
    clock.now += 2
    assert telemetry.instruction_snapshot()["status"] == "disconnected"
