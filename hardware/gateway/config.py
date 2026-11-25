from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class ApplicationSettings:
    gateway_id: str
    database_path: Path
    log_path: Path
    timezone: str


@dataclass(frozen=True)
class ModbusSettings:
    enabled: bool
    port: str
    baudrate: int
    bytesize: int
    parity: str
    stopbits: int
    device_id: int
    timeout_seconds: float
    retries: int
    reconnect_seconds: float
    poll_interval_seconds: float
    clock_address: int
    clock_apply_kind: str
    clock_apply_address: int
    clock_apply_active_value: int
    d100_address: int
    motor_speed_address: int
    line_control_address: int
    event_byte_order: str
    uint32_word_order: str
    time_scale_to_seconds: float
    ack_kind: str
    ack_address: int
    ack_active_value: int
    cycle_base_address: int = 16001
    simulation_start_address: int = 2
    simulation_running_address: int | None = None
    production_count_address: int | None = None
    process_status_address: int | None = None
    reset_base_address: int = 3


@dataclass(frozen=True)
class TcpSettings:
    host: str
    port: int
    connect_timeout_seconds: float
    send_timeout_seconds: float
    response_timeout_seconds: float


@dataclass(frozen=True)
class NtpSettings:
    enabled: bool
    server: str
    port: int
    timeout_seconds: float
    retry_interval_seconds: float
    sync_interval_seconds: float
    apply_timeout_seconds: float


@dataclass(frozen=True)
class MotorOutputSettings:
    enabled: bool
    step_pin: int = 18
    dir_pin: int = 25
    en_pin: int = 15
    minimum_frequency: float = 100.0
    maximum_frequency: float = 5000.0
    ramp_seconds: float = 0.5
    clockwise_high: bool = True
    retry_interval_seconds: float = 2.0


@dataclass(frozen=True)
class OpcUaSettings:
    enabled: bool
    endpoint: str
    namespace_uri: str
    application_uri: str
    certificate_path: Path
    private_key_path: Path
    trusted_clients_dir: Path


@dataclass(frozen=True)
class Settings:
    application: ApplicationSettings
    modbus: ModbusSettings
    tcp: TcpSettings
    ntp: NtpSettings
    motor_output: MotorOutputSettings
    opcua: OpcUaSettings


def _path(base: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


def load_settings(path: str | Path = "config.toml") -> Settings:
    config_path = Path(path).resolve()
    if not config_path.exists():
        fallback = config_path.parent / "config.example.toml"
        config_path = fallback if fallback.exists() else Path("config.example.toml").resolve()
    with config_path.open("rb") as stream:
        raw = tomllib.load(stream)
    base = config_path.parent
    app = raw["application"]
    modbus = raw["modbus"]
    tcp = raw["tcp"]
    ntp = raw.get("ntp", {})
    motor_output = raw.get("motor_output", {})
    opcua = raw["opcua"]
    settings = Settings(
        application=ApplicationSettings(
            gateway_id=str(app["gateway_id"]).strip(),
            database_path=_path(base, app["database_path"]),
            log_path=_path(base, app["log_path"]),
            timezone=str(app["timezone"]),
        ),
        modbus=ModbusSettings(
            enabled=bool(modbus.get("enabled", True)),
            port=str(modbus["port"]),
            baudrate=int(modbus.get("baudrate", 115200)),
            bytesize=int(modbus.get("bytesize", 8)),
            parity=str(modbus.get("parity", "N")).upper(),
            stopbits=int(modbus.get("stopbits", 1)),
            device_id=int(modbus["device_id"]),
            timeout_seconds=float(modbus.get("timeout_seconds", 0.2)),
            retries=int(modbus.get("retries", 2)),
            reconnect_seconds=float(modbus.get("reconnect_seconds", 2.0)),
            poll_interval_seconds=float(modbus.get("poll_interval_seconds", 0.25)),
            clock_address=int(
                modbus.get("clock_address", modbus.get("d50_address", 0))
            ),
            clock_apply_kind=str(modbus.get("clock_apply_kind", "coil")),
            clock_apply_address=int(modbus.get("clock_apply_address", 1)),
            clock_apply_active_value=int(
                modbus.get("clock_apply_active_value", 1)
            ),
            d100_address=int(modbus["d100_address"]),
            motor_speed_address=int(
                modbus.get("motor_speed_address", modbus.get("d200_address", 200))
            ),
            line_control_address=int(
                modbus.get("line_control_address", modbus.get("d201_address", 201))
            ),
            event_byte_order=str(modbus.get("event_byte_order", "big")),
            uint32_word_order=str(modbus.get("uint32_word_order", "high_low")),
            time_scale_to_seconds=float(modbus["time_scale_to_seconds"]),
            ack_kind=str(modbus.get("ack_kind", "coil")),
            ack_address=int(modbus["ack_address"]),
            ack_active_value=int(modbus.get("ack_active_value", 1)),
            cycle_base_address=int(modbus.get("cycle_base_address", 16001)),
            simulation_start_address=int(modbus.get("simulation_start_address", 2)),
            simulation_running_address=(
                int(modbus["simulation_running_address"])
                if "simulation_running_address" in modbus else None
            ),
            production_count_address=(
                int(modbus["production_count_address"])
                if "production_count_address" in modbus else None
            ),
            process_status_address=(
                int(modbus["process_status_address"])
                if "process_status_address" in modbus else None
            ),
            reset_base_address=int(modbus.get("reset_base_address", 3)),
        ),
        tcp=TcpSettings(
            host=str(tcp["host"]),
            port=int(tcp["port"]),
            connect_timeout_seconds=float(tcp.get("connect_timeout_seconds", 5.0)),
            send_timeout_seconds=float(tcp.get("send_timeout_seconds", 5.0)),
            response_timeout_seconds=float(tcp.get("response_timeout_seconds", 5.0)),
        ),
        ntp=NtpSettings(
            enabled=bool(ntp.get("enabled", True)),
            server=str(ntp.get("server", tcp["host"])).strip(),
            port=int(ntp.get("port", 123)),
            timeout_seconds=float(ntp.get("timeout_seconds", 2.0)),
            retry_interval_seconds=float(ntp.get("retry_interval_seconds", 10.0)),
            sync_interval_seconds=float(ntp.get("sync_interval_seconds", 3600.0)),
            apply_timeout_seconds=float(ntp.get("apply_timeout_seconds", 5.0)),
        ),
        motor_output=MotorOutputSettings(
            enabled=bool(motor_output.get("enabled", False)),
            step_pin=int(motor_output.get("step_pin", motor_output.get("gpio", 18))),
            dir_pin=int(motor_output.get("dir_pin", 25)),
            en_pin=int(motor_output.get("en_pin", 15)),
            minimum_frequency=float(motor_output.get("minimum_frequency", 100.0)),
            maximum_frequency=float(motor_output.get("maximum_frequency", 5000.0)),
            ramp_seconds=float(motor_output.get("ramp_seconds", 0.5)),
            clockwise_high=bool(motor_output.get("clockwise_high", True)),
            retry_interval_seconds=float(
                motor_output.get("retry_interval_seconds", 2.0)
            ),
        ),
        opcua=OpcUaSettings(
            enabled=bool(opcua.get("enabled", True)),
            endpoint=str(opcua["endpoint"]),
            namespace_uri=str(opcua["namespace_uri"]),
            application_uri=str(opcua["application_uri"]),
            certificate_path=_path(base, opcua["certificate_path"]),
            private_key_path=_path(base, opcua["private_key_path"]),
            trusted_clients_dir=_path(base, opcua["trusted_clients_dir"]),
        ),
    )
    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    if not settings.application.gateway_id:
        raise ValueError("application.gateway_id cannot be empty")
    modbus = settings.modbus
    if modbus.bytesize != 8 or modbus.stopbits != 1 or modbus.parity != "N":
        raise ValueError("The supported serial framing is 8N1")
    if modbus.baudrate != 115200:
        raise ValueError("The configured LS XGK link requires 115200 bps")
    if not 1 <= modbus.device_id <= 247:
        raise ValueError("modbus.device_id must be between 1 and 247")
    if not 0.2 <= modbus.poll_interval_seconds <= 0.3:
        raise ValueError(
            "modbus.poll_interval_seconds must be between 0.2 and 0.3"
        )
    if modbus.event_byte_order not in {"big", "little"}:
        raise ValueError("modbus.event_byte_order must be big or little")
    if modbus.uint32_word_order not in {"high_low", "low_high"}:
        raise ValueError("modbus.uint32_word_order must be high_low or low_high")
    if modbus.time_scale_to_seconds <= 0:
        raise ValueError("modbus.time_scale_to_seconds must be positive")
    if min(
        modbus.clock_address,
        modbus.clock_apply_address,
        modbus.d100_address,
        modbus.motor_speed_address,
        modbus.line_control_address,
        modbus.ack_address,
    ) < 0:
        raise ValueError("Modbus addresses cannot be negative")
    if modbus.ack_kind not in {"coil", "holding_register"}:
        raise ValueError("modbus.ack_kind must be coil or holding_register")
    if modbus.clock_apply_kind not in {"coil", "holding_register"}:
        raise ValueError(
            "modbus.clock_apply_kind must be coil or holding_register"
        )
    _validate_simulation_addresses(modbus)
    count_address = modbus.production_count_address
    if count_address is not None and not 0 <= count_address <= 65535:
        raise ValueError("modbus.production_count_address is outside the Modbus address space")
    status_address = modbus.process_status_address
    if status_address is not None and not 0 <= status_address <= 65536 - 12:
        raise ValueError("The 12 process status registers must fit in the Modbus address space")
    ntp = settings.ntp
    if ntp.enabled and not ntp.server:
        raise ValueError("ntp.server cannot be empty when NTP is enabled")
    if not 1 <= ntp.port <= 65535:
        raise ValueError("ntp.port must be between 1 and 65535")
    if min(
        ntp.timeout_seconds,
        ntp.retry_interval_seconds,
        ntp.sync_interval_seconds,
        ntp.apply_timeout_seconds,
    ) <= 0:
        raise ValueError("NTP timeouts and intervals must be positive")
    motor = settings.motor_output
    pins = (motor.step_pin, motor.dir_pin, motor.en_pin)
    if len(set(pins)) != 3 or any(not 0 <= pin <= 27 for pin in pins):
        raise ValueError("Motor STEP, DIR and EN must use distinct BCM GPIOs from 0 to 27")
    values = (
        motor.minimum_frequency, motor.maximum_frequency,
        motor.ramp_seconds, motor.retry_interval_seconds,
    )
    if not all(math.isfinite(value) and value > 0 for value in values):
        raise ValueError("Motor frequencies and intervals must be finite and positive")
    if motor.minimum_frequency > motor.maximum_frequency:
        raise ValueError("Motor minimum_frequency cannot exceed maximum_frequency")


def _validate_simulation_addresses(modbus: ModbusSettings) -> None:
    if not 0 <= modbus.cycle_base_address <= 65536 - 288:
        raise ValueError("The 288 cycle registers must fit in the Modbus address space")
    if not 0 <= modbus.simulation_start_address <= 65535:
        raise ValueError("modbus.simulation_start_address is outside the Modbus address space")
    if not 0 <= modbus.reset_base_address <= 65535:
        raise ValueError("modbus.reset_base_address is outside the Modbus address space")
    if modbus.reset_base_address == modbus.simulation_start_address:
        raise ValueError("The Reset coil must be distinct from the Start coil")
    running = modbus.simulation_running_address
    if running is not None and not 0 <= running <= 65535:
        raise ValueError("modbus.simulation_running_address is outside the Modbus address space")
    holding = {*range(modbus.clock_address, modbus.clock_address + 4),
               modbus.motor_speed_address, modbus.line_control_address}
    for kind, address in ((modbus.ack_kind, modbus.ack_address),
                          (modbus.clock_apply_kind, modbus.clock_apply_address)):
        if kind == "holding_register":
            holding.add(address)
        elif address == modbus.simulation_start_address:
            raise ValueError("The Start coil must be distinct from the event and clock coils")
        elif address == modbus.reset_base_address:
            raise ValueError("The Reset coil must be distinct from the event and clock coils")
    if holding.intersection(range(modbus.cycle_base_address, modbus.cycle_base_address + 288)):
        raise ValueError("The cycle base overlaps existing Modbus holding registers")
