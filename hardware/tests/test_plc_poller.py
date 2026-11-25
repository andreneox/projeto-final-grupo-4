from dataclasses import replace
from datetime import datetime, timezone

import pytest

from gateway.config import ModbusSettings
from gateway.domain import CaptureResult
from gateway.plc_poller import PlcPoller
from gateway.register_map import REGISTER_COUNT


PAYLOAD = bytes.fromhex(
    "00 01 00 01 08 26 16 31 10 08 20 01 00 01 00 01"
)


def settings() -> ModbusSettings:
    return ModbusSettings(
        enabled=True,
        port="COM1",
        baudrate=115200,
        bytesize=8,
        parity="N",
        stopbits=1,
        device_id=1,
        timeout_seconds=0.2,
        retries=2,
        reconnect_seconds=0.1,
        poll_interval_seconds=0.25,
        clock_address=0,
        clock_apply_kind="coil",
        clock_apply_address=1,
        clock_apply_active_value=1,
        d100_address=100,
        motor_speed_address=200,
        line_control_address=201,
        event_byte_order="big",
        uint32_word_order="high_low",
        time_scale_to_seconds=0.001,
        ack_kind="coil",
        ack_address=0,
        ack_active_value=1,
    )


def registers_with_event() -> list[int]:
    registers = [0] * REGISTER_COUNT
    registers[0] = 8
    for index in range(8):
        registers[index + 1] = int.from_bytes(PAYLOAD[index * 2 : index * 2 + 2], "big")
    return registers


class FakeTransport:
    def __init__(self, registers: list[int], calls: list[str]) -> None:
        self.registers = registers
        self.calls = calls
        self.fail_ack = False
        self.motor_speed = 50
        self.fail_speed_read = False

    def synchronize_clock(self, timestamp: datetime) -> None:
        self.calls.append(("clock", timestamp))

    def read_register_block(self) -> list[int]:
        self.calls.append("read")
        return list(self.registers)

    def acknowledge_event(self) -> None:
        self.calls.append("p1000")
        if self.fail_ack:
            raise IOError("ack failed")

    def read_motor_speed(self) -> int:
        self.calls.append("read_speed")
        if self.fail_speed_read:
            raise IOError("speed read failed")
        return self.motor_speed

    def set_motor_speed(self, speed: int) -> None:
        self.calls.append(("motor_speed", speed))

    def set_line_stopped(self, stopped: bool) -> None:
        self.calls.append(("line_stop", stopped))

    def close(self) -> None:
        self.calls.append("close")


class FakeDatabase:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.capture_count = 0

    def capture_event(self, payload: bytes) -> CaptureResult:
        assert payload == PAYLOAD
        self.calls.append("commit")
        self.capture_count += 1
        return CaptureResult(7, self.capture_count == 1, False, "pending", False)

    def mark_plc_acknowledged(self, event_id: int) -> None:
        assert event_id == 7
        self.calls.append("mark_ack")


class FakeSimulationTransport(FakeTransport):
    def __init__(self, calls):
        super().__init__([0] * REGISTER_COUNT, calls)
        self.blocks = {}
        self.running = False
        self.fail_address = None
        self.fail_release = False
        self.production_count = 7
        self.process_statuses = [0] * 12

    def write_cycle_block(self, address, values):
        if address == self.fail_address:
            raise IOError("unverified write")
        self.blocks[address] = values

    def set_simulation_start(self, active):
        self.calls.append(("start", active))
        if active:
            self.running = True
        elif self.fail_release:
            raise IOError("release failed")

    def read_simulation_running(self):
        return self.running

    def set_base_reset(self, active):
        self.calls.append(("reset", active))
        if not active and self.fail_release:
            raise IOError("reset release failed")

    def read_production_count(self):
        return self.production_count

    def read_process_statuses(self):
        return self.process_statuses


def make_simulation_poller(calls, *, running_address=None, **overrides):
    transport = FakeSimulationTransport(calls)
    poller = PlcPoller(
        replace(settings(), simulation_running_address=running_address, **overrides),
        transport, FakeDatabase(calls), lambda _stations: None,
        lambda _motor_on, _speed: None, lambda: None, lambda _status: None,
    )
    return poller, transport


def test_reset_during_processing_pulses_until_two_seconds_and_waits_for_plc_state(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("gateway.cycle_control.monotonic", lambda: clock[0])
    calls = []
    poller, transport = make_simulation_poller(
        calls, running_address=120, production_count_address=15052, process_status_address=651,
    )
    transport.running = True
    transport.registers[12] = 1
    transport.process_statuses[0] = 2
    reset = poller.request_base_reset()
    poller.poll_once()
    assert ("reset", True) in calls
    duplicate = poller.request_base_reset()
    clock[0] = 101.99
    poller.poll_once()
    assert ("reset", False) not in calls
    with pytest.raises(RuntimeError, match="already in progress"):
        duplicate.result()
    clock[0] = 102.0
    poller.poll_once()
    assert ("reset", False) in calls and not reset.done()
    transport.production_count = 0
    poller.poll_once()
    assert not reset.done()
    transport.process_statuses[0] = 0
    poller.poll_once()
    assert reset.result().tzinfo is timezone.utc
    assert calls.count(("reset", True)) == calls.count(("reset", False)) == 1


def test_reset_releases_coil_and_rejects_when_count_stays_nonzero(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("gateway.cycle_control.monotonic", lambda: clock[0])
    calls = []
    poller, transport = make_simulation_poller(calls, production_count_address=15052)
    reset = poller.request_base_reset()
    poller.poll_once()
    clock[0] = 102.0
    transport.fail_release = True
    with pytest.raises(IOError, match="reset release failed"):
        poller.poll_once()
    with pytest.raises(IOError, match="reset release failed"):
        reset.result()
    transport.fail_release = False
    poller.poll_once()
    assert calls.count(("reset", False)) == 2
    reset = poller.request_base_reset()
    poller.poll_once()
    clock[0] = 110.0
    poller.poll_once()
    with pytest.raises(RuntimeError, match="não confirmou"):
        reset.result()


def test_imports_24_words_per_station_and_pulses_start_without_stopping_polls(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("gateway.cycle_control.monotonic", lambda: clock[0])
    calls = []
    poller, transport = make_simulation_poller(calls, running_address=120, process_status_address=651)
    rejected = poller.request_simulation_start()
    poller.poll_once()
    with pytest.raises(RuntimeError, match="Load and verify"):
        rejected.result()

    times = [(517 + cycle) / 10 for cycle in range(144)]
    upload = poller.request_cycle_base(times)
    poller.poll_once()
    for index in range(12):
        assert not poller.cycle_base_ready()
        poller.poll_once()
        address = 16001 + index * 24
        expected = list(range(517 + index * 12, 529 + index * 12))
        assert transport.blocks[address] == expected * 2
    assert upload.result() is None
    assert poller.cycle_base_ready()

    start = poller.request_simulation_start()
    poller.poll_once()
    duplicate = poller.request_simulation_start()
    clock[0] = 101.99
    poller.poll_once()
    assert calls[-2:] == ["read", "read_speed"]
    assert ("start", False) not in calls
    assert not start.done()
    with pytest.raises(RuntimeError, match="already in progress"):
        duplicate.result()
    clock[0] = 102.0
    poller.poll_once()
    assert calls[-3:] == [("start", False), "read", "read_speed"]
    assert start.result().tzinfo is timezone.utc


def test_partial_upload_prevents_start_and_failed_release_is_retried(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("gateway.cycle_control.monotonic", lambda: clock[0])
    calls = []
    poller, transport = make_simulation_poller(calls, process_status_address=651)
    upload = poller.request_cycle_base([51.7] * 144)
    for _ in range(13):
        poller.poll_once()
    upload.result()
    transport.fail_address = 16025
    failed = poller.request_cycle_base([52.7] * 144)
    poller.poll_once()
    poller.poll_once()
    with pytest.raises(IOError, match="unverified"):
        poller.poll_once()
    with pytest.raises(IOError, match="unverified"):
        failed.result()
    assert not poller.cycle_base_ready()

    transport.fail_address = None
    upload = poller.request_cycle_base([51.7] * 144)
    for _ in range(13):
        poller.poll_once()
    upload.result()
    start = poller.request_simulation_start()
    poller.poll_once()
    clock[0] = 102.0
    transport.fail_release = True
    with pytest.raises(IOError, match="release failed"):
        poller.poll_once()
    with pytest.raises(IOError, match="release failed"):
        start.result()
    transport.fail_release = False
    poller.poll_once()
    assert calls.count(("start", True)) == 1
    assert calls.count(("start", False)) == 2


def test_start_rechecks_every_station_and_andon_before_pulsing():
    calls = []
    poller, transport = make_simulation_poller(calls, process_status_address=651)
    upload = poller.request_cycle_base([51.7] * 144)
    for _ in range(13):
        poller.poll_once()
    upload.result()

    for status in (1, 2, 3, 7):
        transport.process_statuses[11] = status
        rejected = poller.request_simulation_start()
        poller.poll_once()
        with pytest.raises(RuntimeError, match="12 postos.*estado 0"):
            rejected.result()
        assert ("start", True) not in calls

    transport.process_statuses[11] = 0
    transport.registers[11] = 0x8000
    rejected = poller.request_simulation_start()
    poller.poll_once()
    with pytest.raises(RuntimeError, match="Andons"):
        rejected.result()
    assert ("start", True) not in calls

    transport.registers[11] = 0
    poller.request_simulation_start()
    poller.poll_once()
    assert calls.count(("start", True)) == 1


def test_start_requires_process_status_reading():
    calls = []
    poller, _ = make_simulation_poller(calls)
    upload = poller.request_cycle_base([51.7] * 144)
    for _ in range(13):
        poller.poll_once()
    upload.result()
    start = poller.request_simulation_start()
    poller.poll_once()
    with pytest.raises(RuntimeError, match="leitura do estado"):
        start.result()
    assert ("start", True) not in calls


def test_process_statuses_preserve_station_order_and_clear_on_read_failure(monkeypatch) -> None:
    clock = [100.0]
    monkeypatch.setattr("gateway.plc_poller.time.monotonic", lambda: clock[0])
    calls = []
    registers = [0] * REGISTER_COUNT
    registers[9] = 1
    transport = FakeTransport(registers, calls)
    samples = []
    motor = []
    poller = PlcPoller(
        replace(settings(), process_status_address=651), transport, FakeDatabase(calls),
        samples.append, lambda *values: motor.append(values), lambda: None, calls.append,
    )

    def unavailable() -> list[int]:
        raise OSError("process registers unavailable")

    transport.read_process_statuses = lambda: [0, 1, 2, 3] * 2 + [7, 1, 2, 3]
    poller.poll_once()
    assert [item.process_status for item in samples[-1].values()] == [
        0, 1, 2, 3, 0, 1, 2, 3, None, 1, 2, 3,
    ]
    transport.read_process_statuses = unavailable
    poller.poll_once()
    assert all(item.process_status is None for item in samples[-1].values())
    assert any(samples[-1][1].states.values())
    assert len(motor) == 2

    clock[0] += 1
    transport.read_process_statuses = lambda: [3] * 12
    poller.poll_once()
    assert all(item.process_status == 3 for item in samples[-1].values())

    transport.fail_speed_read = True
    with pytest.raises(IOError, match="speed read failed"):
        poller.poll_once()
    assert all(item.process_status is None for item in samples[-1].values())


def test_commit_always_happens_before_p1000() -> None:
    calls: list[str] = []
    transport = FakeTransport(registers_with_event(), calls)
    database = FakeDatabase(calls)
    wake_calls = []
    poller = PlcPoller(
        settings(), transport, database, lambda _stations: None,
        lambda _motor_on, _speed: None, lambda: wake_calls.append(1), lambda _status: None
    )

    poller.poll_once()

    assert calls == ["read", "read_speed", "commit", "p1000", "mark_ack"]
    assert wake_calls == [1]


def test_same_presented_buffer_is_not_captured_twice() -> None:
    calls: list[str] = []
    transport = FakeTransport(registers_with_event(), calls)
    database = FakeDatabase(calls)
    poller = PlcPoller(
        settings(), transport, database, lambda _stations: None,
        lambda _motor_on, _speed: None, lambda: None, lambda _status: None
    )

    poller.poll_once()
    poller.poll_once()

    assert database.capture_count == 1
    assert calls.count("p1000") == 1


def test_failed_p1000_is_retried_without_losing_persisted_event() -> None:
    calls: list[str] = []
    transport = FakeTransport(registers_with_event(), calls)
    transport.fail_ack = True
    database = FakeDatabase(calls)
    poller = PlcPoller(
        settings(),
        transport,
            database,
            lambda _stations: None,
            lambda _motor_on, _speed: None,
            lambda: None,
        lambda _status: None,
    )

    with pytest.raises(IOError, match="ack failed"):
        poller.poll_once()
    transport.fail_ack = False
    poller.poll_once()

    assert calls.index("commit") < calls.index("p1000")
    assert database.capture_count == 2
    assert calls.count("p1000") == 2


def test_control_commands_are_serialized_by_the_poller() -> None:
    calls: list = []
    transport = FakeTransport([0] * REGISTER_COUNT, calls)
    database = FakeDatabase(calls)
    poller = PlcPoller(
        settings(), transport, database, lambda _stations: None,
        lambda _motor_on, _speed: None, lambda: None, lambda _status: None
    )
    speed = poller.request_motor_speed(64)
    stop = poller.request_line_stop(True)

    poller.poll_once()

    assert speed.result(timeout=0) is None
    assert stop.result(timeout=0) is None
    assert calls[:3] == [("motor_speed", 64), ("line_stop", True), "read"]


def test_ntp_clock_update_is_serialized_before_the_next_read() -> None:
    calls: list = []
    transport = FakeTransport([0] * REGISTER_COUNT, calls)
    database = FakeDatabase(calls)
    poller = PlcPoller(
        settings(), transport, database, lambda _stations: None,
        lambda _motor_on, _speed: None, lambda: None, lambda _status: None
    )
    timestamp = datetime(2026, 9, 27, 15, 30, 0, tzinfo=timezone.utc)
    synchronized = poller.request_clock_sync(timestamp)

    poller.poll_once()

    assert synchronized.result(timeout=0) is None
    assert calls[:2] == [("clock", timestamp), "read"]


def test_clock_update_rejects_naive_datetime() -> None:
    calls: list = []
    poller = PlcPoller(
        settings(), FakeTransport([0] * REGISTER_COUNT, calls), FakeDatabase(calls),
        lambda _stations: None, lambda _motor_on, _speed: None, lambda: None,
        lambda _status: None
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        poller.request_clock_sync(datetime(2026, 9, 27, 15, 30, 0))


def test_forwards_d112_and_d1200_on_each_snapshot() -> None:
    calls: list = []
    registers = [0] * REGISTER_COUNT
    registers[12] = 1
    motor_states: list[tuple[bool, int]] = []
    transport = FakeTransport(registers, calls)
    poller = PlcPoller(
        settings(), transport, FakeDatabase(calls),
        lambda _stations: None, lambda on, speed: motor_states.append((on, speed)), lambda: None,
        lambda _status: None,
    )

    poller.poll_once()

    transport.motor_speed = 73
    poller.poll_once()
    registers[12] = 0
    poller.poll_once()

    assert motor_states == [(True, 50), (True, 73), (False, 73)]

def test_failed_speed_read_disables_motor_without_applying_partial_command() -> None:
    calls = []
    registers = [0] * REGISTER_COUNT
    registers[12] = 1
    transport = FakeTransport(registers, calls)
    transport.fail_speed_read = True
    states = []
    faults = []
    poller = PlcPoller(
        settings(), transport, FakeDatabase(calls), lambda _stations: None,
        lambda on, speed: states.append((on, speed)), lambda: None,
        lambda _status: None, motor_fault_callback=lambda: faults.append(True),
    )

    with pytest.raises(IOError, match="speed read failed"):
        poller.poll_once()

    assert states == []
    assert faults == [True]
