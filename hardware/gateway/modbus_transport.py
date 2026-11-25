from __future__ import annotations

from datetime import datetime
from typing import Protocol

from gateway.config import ModbusSettings
from gateway.plc_clock import encode_plc_clock
from gateway.register_map import REGISTER_COUNT, STATION_COUNT


class PlcTransport(Protocol):
    def synchronize_clock(self, timestamp: datetime) -> None: ...

    def read_register_block(self) -> list[int]: ...

    def read_motor_speed(self) -> int: ...

    def read_production_count(self) -> int: ...

    def read_process_statuses(self) -> list[int]: ...

    def acknowledge_event(self) -> None: ...

    def set_motor_speed(self, speed: int) -> None: ...

    def set_line_stopped(self, stopped: bool) -> None: ...

    def write_cycle_block(self, address: int, values: list[int]) -> None: ...

    def set_simulation_start(self, active: bool) -> None: ...

    def set_base_reset(self, active: bool) -> None: ...

    def read_simulation_running(self) -> bool: ...

    def close(self) -> None: ...


class PymodbusSerialTransport:
    def __init__(self, settings: ModbusSettings) -> None:
        self._settings = settings
        self._client = None

    def synchronize_clock(self, timestamp: datetime) -> None:
        values = encode_plc_clock(timestamp)
        client = self._connected_client()
        try:
            response = client.write_registers(
                self._settings.clock_address,
                values,
                device_id=self._settings.device_id,
            )
            self._check_response(response, "write D1000-D1003 PLC clock")
            if self._settings.clock_apply_kind == "coil":
                response = client.write_coil(
                    self._settings.clock_apply_address,
                    bool(self._settings.clock_apply_active_value),
                    device_id=self._settings.device_id,
                )
            else:
                response = client.write_register(
                    self._settings.clock_apply_address,
                    self._settings.clock_apply_active_value,
                    device_id=self._settings.device_id,
                )
            self._check_response(response, "set P10001 clock apply request")
        except Exception:
            self.close()
            raise

    def read_register_block(self) -> list[int]:
        client = self._connected_client()
        try:
            response = client.read_input_registers(
                self._settings.d100_address,
                count=REGISTER_COUNT,
                device_id=self._settings.device_id,
            )
            self._check_response(response, "read D100-D160")
            registers = list(response.registers)
            if len(registers) != REGISTER_COUNT:
                raise IOError(
                    f"PLC returned {len(registers)} of {REGISTER_COUNT} registers"
                )
            return registers
        except Exception:
            self.close()
            raise

    def read_motor_speed(self) -> int:
        client = self._connected_client()
        try:
            response = client.read_holding_registers(
                self._settings.motor_speed_address,
                count=1,
                device_id=self._settings.device_id,
            )
            self._check_response(response, "read D1200 motor speed")
            if len(response.registers) != 1:
                raise IOError("PLC must return exactly one D1200 motor speed register")
            speed = response.registers[0]
            if isinstance(speed, bool) or not isinstance(speed, int) or not 0 <= speed <= 100:
                raise ValueError("D1200 motor speed must be an integer between 0 and 100")
            return speed
        except Exception:
            self.close()
            raise

    def read_production_count(self) -> int:
        address = self._settings.production_count_address
        if address is None:
            raise RuntimeError("The production count register is not configured")
        client = self._connected_client()
        response = client.read_holding_registers(
            address, count=1, device_id=self._settings.device_id
        )
        self._check_response(response, "read D16052 production count")
        if len(response.registers) != 1 or not 0 <= response.registers[0] <= 0xFFFF:
            raise IOError("PLC must return one unsigned 16-bit production count")
        return response.registers[0]

    def read_process_statuses(self) -> list[int]:
        address = self._settings.process_status_address
        if address is None:
            raise RuntimeError("The process status registers are not configured")
        response = self._connected_client().read_holding_registers(
            address, count=STATION_COUNT, device_id=self._settings.device_id
        )
        self._check_response(response, "read D1651-D1662 process status")
        values = list(response.registers)
        if len(values) != STATION_COUNT:
            raise IOError(f"PLC must return {STATION_COUNT} process status registers")
        return values

    def acknowledge_event(self) -> None:
        client = self._connected_client()
        try:
            self._write_ack(client, self._settings.ack_active_value)
        except Exception:
            self.close()
            raise

    def set_motor_speed(self, speed: int) -> None:
        if isinstance(speed, bool) or not isinstance(speed, int) or not 0 <= speed <= 100:
            raise ValueError("Motor speed must be an integer between 0 and 100")
        client = self._connected_client()
        try:
            response = client.write_register(
                self._settings.motor_speed_address,
                speed,
                device_id=self._settings.device_id,
            )
            self._check_response(response, "write D1200 motor speed")
        except Exception:
            self.close()
            raise

    def set_line_stopped(self, stopped: bool) -> None:
        if not isinstance(stopped, bool):
            raise ValueError("Line stop command must be boolean")
        client = self._connected_client()
        try:
            response = client.read_holding_registers(
                self._settings.line_control_address,
                count=1,
                device_id=self._settings.device_id,
            )
            self._check_response(response, "read D1201 line control")
            current = int(response.registers[0])
            target = current | 0x0001 if stopped else current & 0xFFFE
            if target == current:
                return
            response = client.write_register(
                self._settings.line_control_address,
                target,
                device_id=self._settings.device_id,
            )
            self._check_response(response, "write D1201 line control")
        except Exception:
            self.close()
            raise

    def write_cycle_block(self, address: int, values: list[int]) -> None:
        client = self._connected_client()
        try:
            response = client.write_registers(address, values, device_id=self._settings.device_id)
            self._check_response(response, f"write cycle base at {address}")
            response = client.read_holding_registers(
                address, count=len(values), device_id=self._settings.device_id
            )
            self._check_response(response, f"verify cycle base at {address}")
            if list(response.registers) != values:
                raise IOError(f"Cycle base verification failed at Modbus address {address}")
        except Exception:
            self.close()
            raise

    def set_simulation_start(self, active: bool) -> None:
        self._write_simulation_coil(self._settings.simulation_start_address, active, "Start")

    def set_base_reset(self, active: bool) -> None:
        self._write_simulation_coil(self._settings.reset_base_address, active, "Reset")

    def _write_simulation_coil(self, address: int, active: bool, operation: str) -> None:
        client = self._connected_client()
        try:
            response = client.write_coil(
                address, active, device_id=self._settings.device_id
            )
            self._check_response(response, f"write simulation {operation} coil")
        except Exception:
            self.close()
            raise

    def read_simulation_running(self) -> bool:
        address = self._settings.simulation_running_address
        if address is None:
            raise RuntimeError("The simulation running input is not configured")
        client = self._connected_client()
        try:
            response = client.read_input_registers(address, count=1, device_id=self._settings.device_id)
            self._check_response(response, "read simulation running input")
            if response.registers not in ([0], [1]):
                raise IOError("The simulation running input must contain 0 or 1")
            return bool(response.registers[0])
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _connected_client(self):
        if self._client is None:
            try:
                from pymodbus.client import ModbusSerialClient
            except ImportError as exc:
                raise RuntimeError(
                    "pymodbus serial support is not installed"
                ) from exc
            self._client = ModbusSerialClient(
                port=self._settings.port,
                baudrate=self._settings.baudrate,
                bytesize=self._settings.bytesize,
                parity=self._settings.parity,
                stopbits=self._settings.stopbits,
                timeout=self._settings.timeout_seconds,
                retries=self._settings.retries,
            )
        if not self._client.connected and not self._client.connect():
            self.close()
            raise ConnectionError(f"cannot open Modbus port {self._settings.port}")
        return self._client

    def _write_ack(self, client, value: int) -> None:
        if self._settings.ack_kind == "coil":
            response = client.write_coil(
                self._settings.ack_address,
                bool(value),
                device_id=self._settings.device_id,
            )
        else:
            response = client.write_register(
                self._settings.ack_address,
                value,
                device_id=self._settings.device_id,
            )
        self._check_response(response, "set P10000 event acknowledgement")

    @staticmethod
    def _check_response(response, operation: str) -> None:
        if response is None or response.isError():
            raise IOError(f"Modbus operation failed: {operation}: {response!r}")
