from pathlib import Path
from threading import Thread
import time

from gateway.application import GatewayApplication
from gateway.config import (
    ApplicationSettings,
    ModbusSettings,
    MotorOutputSettings,
    NtpSettings,
    OpcUaSettings,
    Settings,
    TcpSettings,
)


def test_headless_application_starts_and_stops_without_hardware(tmp_path) -> None:
    settings = Settings(
        application=ApplicationSettings(
            gateway_id="TEST",
            database_path=tmp_path / "gateway.db",
            log_path=tmp_path / "gateway.log",
            timezone="America/Manaus",
        ),
        modbus=ModbusSettings(
            enabled=False,
            port="COM1",
            baudrate=115200,
            bytesize=8,
            parity="N",
            stopbits=1,
            device_id=1,
            timeout_seconds=0.2,
            retries=0,
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
        ),
        tcp=TcpSettings("127.0.0.1", 15000, 0.2, 0.2, 0.2),
        ntp=NtpSettings(False, "127.0.0.1", 123, 0.2, 0.1, 60.0, 1.0),
        motor_output=MotorOutputSettings(enabled=False),
        opcua=OpcUaSettings(
            enabled=False,
            endpoint="opc.tcp://127.0.0.1:4840/mock-linha/",
            namespace_uri="urn:mock-linha:telemetria:v1",
            application_uri="urn:mock-linha:servidor",
            certificate_path=Path("missing.der"),
            private_key_path=Path("missing.pem"),
            trusted_clients_dir=Path("missing"),
        ),
    )
    application = GatewayApplication(settings)
    thread = Thread(target=application.run)
    thread.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not settings.application.database_path.exists():
        time.sleep(0.02)

    application.request_stop()
    thread.join(timeout=5)

    assert settings.application.database_path.exists()
    assert not thread.is_alive()
