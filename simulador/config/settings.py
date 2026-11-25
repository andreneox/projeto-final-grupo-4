from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib


@dataclass(frozen=True)
class ApplicationSettings:
    database_path: Path
    timezone: str
    takt_time_seconds: float
    last_cycle_seconds: float


@dataclass(frozen=True)
class TcpSettings:
    host: str
    port: int
    connect_timeout_seconds: float
    send_timeout_seconds: float
    response_timeout_seconds: float
    sync_on_start: bool


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
class OpcUaClientSettings:
    enabled: bool
    endpoint: str
    namespace_uri: str
    application_uri: str
    certificate_path: Path
    private_key_path: Path
    server_certificate_path: Path
    reconnect_seconds: float


@dataclass(frozen=True)
class DashboardSettings:
    host: str
    port: int
    shift_start: str
    shift_duration_minutes: int
    opcua_stale_seconds: float


@dataclass(frozen=True)
class ReceiverSettings:
    host: str
    port: int
    database_path: Path
    timezone: str


@dataclass(frozen=True)
class DesktopApiSettings:
    start_url: str = ""
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class RuntimeApiSettings:
    base_url: str = ""
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class Settings:
    application: ApplicationSettings
    tcp: TcpSettings
    opcua: OpcUaSettings
    opcua_client: OpcUaClientSettings
    dashboard: DashboardSettings
    receiver: ReceiverSettings
    desktop_api: DesktopApiSettings = DesktopApiSettings()
    runtime_api: RuntimeApiSettings = RuntimeApiSettings()


def _path(base: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


def load_settings(path: str | Path = "config.toml") -> Settings:
    config_path = Path(path).resolve()
    if not config_path.exists():
        config_path = Path("config.example.toml").resolve()
    with config_path.open("rb") as stream:
        raw = tomllib.load(stream)
    base = config_path.parent
    app = raw["application"]
    tcp = raw["tcp"]
    opcua = raw["opcua"]
    opcua_client = raw["opcua_client"]
    dashboard = raw["dashboard"]
    receiver = raw["receiver"]
    desktop_api = raw.get("desktop_api", {})
    timeout = float(desktop_api.get("timeout_seconds", 10.0))
    if not 0 < timeout <= 120:
        raise ValueError(
            "desktop_api.timeout_seconds deve ser maior que 0 e no máximo 120."
        )
    runtime_timeout = float(raw.get("runtime_api", {}).get("timeout_seconds", 10.0))
    if not 0 < runtime_timeout <= 120:
        raise ValueError(
            "runtime_api.timeout_seconds deve ser maior que 0 e no máximo 120."
        )
    return Settings(
        application=ApplicationSettings(
            database_path=_path(base, app["database_path"]),
            timezone=app["timezone"],
            takt_time_seconds=float(app["takt_time_seconds"]),
            last_cycle_seconds=float(app["last_cycle_seconds"]),
        ),
        tcp=TcpSettings(
            host=tcp["host"],
            port=int(tcp["port"]),
            connect_timeout_seconds=float(tcp["connect_timeout_seconds"]),
            send_timeout_seconds=float(tcp["send_timeout_seconds"]),
            response_timeout_seconds=float(tcp["response_timeout_seconds"]),
            sync_on_start=bool(tcp.get("sync_on_start", False)),
        ),
        opcua=OpcUaSettings(
            enabled=bool(opcua["enabled"]),
            endpoint=opcua["endpoint"],
            namespace_uri=opcua["namespace_uri"],
            application_uri=opcua["application_uri"],
            certificate_path=_path(base, opcua["certificate_path"]),
            private_key_path=_path(base, opcua["private_key_path"]),
            trusted_clients_dir=_path(base, opcua["trusted_clients_dir"]),
        ),
        opcua_client=OpcUaClientSettings(
            enabled=bool(opcua_client["enabled"]),
            endpoint=opcua_client["endpoint"],
            namespace_uri=opcua_client["namespace_uri"],
            application_uri=opcua_client["application_uri"],
            certificate_path=_path(base, opcua_client["certificate_path"]),
            private_key_path=_path(base, opcua_client["private_key_path"]),
            server_certificate_path=_path(
                base, opcua_client["server_certificate_path"]
            ),
            reconnect_seconds=float(opcua_client["reconnect_seconds"]),
        ),
        dashboard=DashboardSettings(
            host=dashboard["host"],
            port=int(dashboard["port"]),
            shift_start=dashboard["shift_start"],
            shift_duration_minutes=int(dashboard["shift_duration_minutes"]),
            opcua_stale_seconds=float(dashboard["opcua_stale_seconds"]),
        ),
        receiver=ReceiverSettings(
            host=receiver["host"],
            port=int(receiver["port"]),
            database_path=_path(base, receiver["database_path"]),
            timezone=receiver["timezone"],
        ),
        desktop_api=DesktopApiSettings(
            start_url=os.environ.get(
                "LEAN_DESKTOP_START_URL", desktop_api.get("start_url", "")
            ),
            timeout_seconds=timeout,
        ),
        runtime_api=RuntimeApiSettings(
            base_url=raw.get("runtime_api", {}).get("base_url", "").strip()
            or f"http://{tcp['host']}:{dashboard['port']}",
            timeout_seconds=runtime_timeout,
        ),
    )
