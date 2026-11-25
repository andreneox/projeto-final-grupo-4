from datetime import datetime

import pytest

from gateway.config import ModbusSettings
from gateway.modbus_transport import PymodbusSerialTransport
from gateway.register_map import REGISTER_COUNT


def settings(**overrides) -> ModbusSettings:
    values = {
        "enabled": True,
        "port": "COM9",
        "baudrate": 115200,
        "bytesize": 8,
        "parity": "N",
        "stopbits": 1,
        "device_id": 7,
        "timeout_seconds": 0.2,
        "retries": 2,
        "reconnect_seconds": 2.0,
        "poll_interval_seconds": 0.25,
        "clock_address": 0,
        "clock_apply_kind": "coil",
        "clock_apply_address": 9101,
        "clock_apply_active_value": 1,
        "d100_address": 4100,
        "motor_speed_address": 4200,
        "line_control_address": 4201,
        "event_byte_order": "big",
        "uint32_word_order": "high_low",
        "time_scale_to_seconds": 0.001,
        "ack_kind": "coil",
        "ack_address": 9100,
        "ack_active_value": 1,
    }
    values.update(overrides)
    return ModbusSettings(**values)


class Response:
    def __init__(self, registers=None) -> None:
        self.registers = registers

    def isError(self) -> bool:
        return False


class FakeClient:
    connected = True

    def __init__(self, register_value=0) -> None:
        self.calls = []
        self.register_value = register_value

    def read_holding_registers(self, address, *, count, device_id):
        self.calls.append(("read", address, count, device_id))
        return Response([self.register_value] * count)

    def read_input_registers(self, address, *, count, device_id):
        self.calls.append(("input", address, count, device_id))
        return Response([self.register_value] * count)

    def write_coil(self, address, value, *, device_id):
        self.calls.append(("coil", address, value, device_id))
        return Response()

    def write_register(self, address, value, *, device_id):
        self.calls.append(("register", address, value, device_id))
        return Response()

    def write_registers(self, address, values, *, device_id):
        self.calls.append(("registers", address, list(values), device_id))
        return Response()

    def close(self) -> None:
        self.connected = False


def test_writes_and_verifies_cycle_block_and_uses_coil_two_for_start() -> None:
    transport = PymodbusSerialTransport(settings())
    client = FakeClient(register_value=517)
    transport._client = client

    transport.write_cycle_block(16001, [517] * 24)
    transport.set_simulation_start(True)
    transport.set_simulation_start(False)
    transport.set_base_reset(True)
    transport.set_base_reset(False)

    assert client.calls == [
        ("registers", 16001, [517] * 24, 7), ("read", 16001, 24, 7),
        ("coil", 2, True, 7), ("coil", 2, False, 7),
        ("coil", 3, True, 7), ("coil", 3, False, 7),
    ]
    with pytest.raises(IOError, match="verification failed"):
        transport.write_cycle_block(16001, [518] * 24)


def test_reads_exact_block_with_configured_address_and_device_id() -> None:
    transport = PymodbusSerialTransport(settings())
    client = FakeClient()
    transport._client = client

    registers = transport.read_register_block()

    assert len(registers) == REGISTER_COUNT
    assert client.calls == [("input", 4100, REGISTER_COUNT, 7)]


def test_reads_d16052_as_one_holding_register() -> None:
    transport = PymodbusSerialTransport(settings(production_count_address=15052))
    client = FakeClient(register_value=321)
    transport._client = client

    assert transport.read_production_count() == 321
    assert client.calls == [("read", 15052, 1, 7)]


def test_reads_all_station_process_statuses_in_one_request() -> None:
    transport = PymodbusSerialTransport(settings(process_status_address=651))
    client = FakeClient(register_value=3)
    transport._client = client

    assert transport.read_process_statuses() == [3] * 12
    assert client.calls == [("read", 651, 12, 7)]


def test_synchronizes_plc_clock_with_one_four_register_write() -> None:
    transport = PymodbusSerialTransport(settings())
    client = FakeClient()
    transport._client = client

    transport.synchronize_clock(datetime(2026, 9, 27, 14, 5, 8))

    assert client.calls == [
        ("registers", 0, [0x0926, 0x1427, 0x0805, 0x2000], 7),
        ("coil", 9101, True, 7),
    ]


def test_sets_configured_ack_coil_for_the_plc_to_clear() -> None:
    transport = PymodbusSerialTransport(settings())
    client = FakeClient()
    transport._client = client

    transport.acknowledge_event()

    assert client.calls == [
        ("coil", 9100, True, 7),
    ]


def test_can_acknowledge_through_holding_register() -> None:
    transport = PymodbusSerialTransport(
        settings(ack_kind="holding_register", ack_active_value=55)
    )
    client = FakeClient()
    transport._client = client

    transport.acknowledge_event()

    assert client.calls == [
        ("register", 9100, 55, 7),
    ]


def test_sets_motor_speed_in_d200_and_rejects_out_of_range() -> None:
    transport = PymodbusSerialTransport(settings())
    client = FakeClient()
    transport._client = client

    transport.set_motor_speed(73)

    assert client.calls == [("register", 4200, 73, 7)]
    for invalid in (-1, 101, True):
        try:
            transport.set_motor_speed(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid speed {invalid!r}")


@pytest.mark.parametrize("speed", [0, 50, 100])
def test_reads_d1200_percentage_from_configured_holding_register(speed) -> None:
    transport = PymodbusSerialTransport(settings())
    client = FakeClient(register_value=speed)
    transport._client = client

    assert transport.read_motor_speed() == speed
    assert client.calls == [("read", 4200, 1, 7)]


@pytest.mark.parametrize("speed", [-1, 101, True])
def test_rejects_invalid_d1200_and_closes_connection(speed) -> None:
    transport = PymodbusSerialTransport(settings())
    client = FakeClient(register_value=speed)
    transport._client = client

    with pytest.raises(ValueError, match="D1200"):
        transport.read_motor_speed()
    assert client.connected is False


def test_rejects_missing_d1200_register() -> None:
    transport = PymodbusSerialTransport(settings())
    client = FakeClient()
    client.read_holding_registers = lambda *args, **kwargs: Response([])
    transport._client = client

    with pytest.raises(IOError, match="exactly one"):
        transport.read_motor_speed()
    assert client.connected is False


def test_line_stop_changes_only_bit_zero_of_d201() -> None:
    transport = PymodbusSerialTransport(settings())
    client = FakeClient(register_value=0b1010)
    transport._client = client

    transport.set_line_stopped(True)

    assert client.calls == [
        ("read", 4201, 1, 7),
        ("register", 4201, 0b1011, 7),
    ]

    client.calls.clear()
    client.register_value = 0b1011
    transport.set_line_stopped(False)
    assert client.calls == [
        ("read", 4201, 1, 7),
        ("register", 4201, 0b1010, 7),
    ]
