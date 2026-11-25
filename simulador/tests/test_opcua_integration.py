from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import socket
from threading import Event
import time

import pytest
from asyncua import Client, ua
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

from communications.opcua_server import OpcUaServerWorker
from communications.opcua_client import OpcUaClientWorker
from config.settings import OpcUaClientSettings, OpcUaSettings
from domain.models import AndonCategory
from services.telemetry import TelemetryStore
from tools.generate_dev_certificates import generate


def free_port() -> int:
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return int(connection.getsockname()[1])


async def connect_securely(
    endpoint: str,
    application_uri: str,
    client_certificate: Path,
    client_key: Path,
    server_certificate: Path,
) -> Client:
    client = Client(endpoint)
    client.application_uri = application_uri
    await client.set_security(
        SecurityPolicyBasic256Sha256,
        client_certificate,
        client_key,
        server_certificate=server_certificate,
        mode=ua.MessageSecurityMode.SignAndEncrypt,
    )
    await client.connect()
    return client


def test_secure_server_exposes_stable_read_only_nodes(tmp_path) -> None:
    server_uri = "urn:mock-linha:test-server"
    client_uri = "urn:mock-linha:test-client"
    server_certificate, server_key = generate(
        tmp_path / "server", "Mock Test Server", server_uri, "server"
    )
    client_certificate, client_key = generate(
        tmp_path / "client", "Mock Test Client", client_uri, "client"
    )
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    shutil.copy2(client_certificate, trusted / client_certificate.name)
    endpoint = f"opc.tcp://127.0.0.1:{free_port()}/mock-linha/"
    settings = OpcUaSettings(
        enabled=True,
        endpoint=endpoint,
        namespace_uri="urn:mock-linha:telemetria:v1",
        application_uri=server_uri,
        certificate_path=server_certificate,
        private_key_path=server_key,
        trusted_clients_dir=trusted,
    )
    active = Event()
    statuses = []

    def status_changed(status: str) -> None:
        statuses.append(status)
        if status == "ativo e seguro":
            active.set()

    worker = OpcUaServerWorker(settings, {}, 60.0, 57.5, status_changed)
    worker.start()
    assert active.wait(5), statuses

    async def verify() -> None:
        client = await connect_securely(
            endpoint, client_uri, client_certificate, client_key, server_certificate
        )
        try:
            endpoints = await client.get_endpoints()
            assert endpoints
            assert all(
                endpoint.SecurityMode == ua.MessageSecurityMode.SignAndEncrypt
                and endpoint.SecurityPolicyUri.endswith("#Basic256Sha256")
                for endpoint in endpoints
            )
            namespace = await client.get_namespace_index(settings.namespace_uri)
            paths = []
            for station in range(1, 13):
                prefix = f"P{station:02d}"
                paths.extend(
                    f"{prefix}/Andon/{category.label}" for category in AndonCategory
                )
                paths.extend((f"{prefix}/TaktTime", f"{prefix}/UltimoCiclo"))
            values = [
                await client.get_node(ua.NodeId(path, namespace)).read_value()
                for path in paths
            ]
            assert len(values) == 72
            station_12 = client.get_node(
                ua.NodeId("P12/Andon/Material", namespace)
            )
            with pytest.raises(ua.UaStatusCodeError):
                await station_12.write_value(True)
            worker.update_state(12, AndonCategory.MATERIAL, True)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if await station_12.read_value() is True:
                    break
                await asyncio.sleep(0.05)
            assert await station_12.read_value() is True
            updated_metrics = {
                station: (60.0 + station, 50.0 + station)
                for station in range(1, 13)
            }
            worker.update_metrics(updated_metrics)
            station_12_takt = client.get_node(
                ua.NodeId("P12/TaktTime", namespace)
            )
            station_12_cycle = client.get_node(
                ua.NodeId("P12/UltimoCiclo", namespace)
            )
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if await station_12_cycle.read_value() == 62.0:
                    break
                await asyncio.sleep(0.05)
            assert await station_12_takt.read_value() == 72.0
            assert await station_12_cycle.read_value() == 62.0
        finally:
            await client.disconnect()

    try:
        asyncio.run(verify())
    finally:
        worker.stop()


def test_wrong_server_certificate_is_rejected(tmp_path) -> None:
    server_uri = "urn:mock-linha:test-server"
    client_uri = "urn:mock-linha:test-client"
    server_certificate, server_key = generate(
        tmp_path / "server", "Mock Test Server", server_uri, "server"
    )
    wrong_server_certificate, _ = generate(
        tmp_path / "wrong-server", "Wrong Server", server_uri, "server"
    )
    client_certificate, client_key = generate(
        tmp_path / "client", "Mock Test Client", client_uri, "client"
    )
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    shutil.copy2(client_certificate, trusted / client_certificate.name)
    endpoint = f"opc.tcp://127.0.0.1:{free_port()}/mock-linha/"
    settings = OpcUaSettings(
        enabled=True,
        endpoint=endpoint,
        namespace_uri="urn:mock-linha:telemetria:v1",
        application_uri=server_uri,
        certificate_path=server_certificate,
        private_key_path=server_key,
        trusted_clients_dir=trusted,
    )
    active = Event()
    worker = OpcUaServerWorker(
        settings, {}, 60.0, 57.5, lambda status: active.set() if status == "ativo e seguro" else None
    )
    worker.start()
    assert active.wait(5)

    async def verify_rejection() -> None:
        with pytest.raises(Exception):
            client = await connect_securely(
                endpoint,
                client_uri,
                client_certificate,
                client_key,
                wrong_server_certificate,
            )
            await client.disconnect()

    try:
        asyncio.run(verify_rejection())
    finally:
        worker.stop()


def test_unknown_client_certificate_is_rejected(tmp_path) -> None:
    server_uri = "urn:mock-linha:test-server"
    trusted_uri = "urn:mock-linha:trusted-client"
    unknown_uri = "urn:mock-linha:unknown-client"
    server_certificate, server_key = generate(
        tmp_path / "server", "Mock Test Server", server_uri, "server"
    )
    trusted_certificate, _ = generate(
        tmp_path / "trusted-client", "Trusted", trusted_uri, "client"
    )
    unknown_certificate, unknown_key = generate(
        tmp_path / "unknown-client", "Unknown", unknown_uri, "client"
    )
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    shutil.copy2(trusted_certificate, trusted / trusted_certificate.name)
    endpoint = f"opc.tcp://127.0.0.1:{free_port()}/mock-linha/"
    settings = OpcUaSettings(
        enabled=True,
        endpoint=endpoint,
        namespace_uri="urn:mock-linha:telemetria:v1",
        application_uri=server_uri,
        certificate_path=server_certificate,
        private_key_path=server_key,
        trusted_clients_dir=trusted,
    )
    active = Event()
    worker = OpcUaServerWorker(
        settings, {}, 60.0, 57.5, lambda status: active.set() if status == "ativo e seguro" else None
    )
    worker.start()
    assert active.wait(5)

    async def verify_rejection() -> None:
        with pytest.raises(Exception):
            client = await connect_securely(
                endpoint,
                unknown_uri,
                unknown_certificate,
                unknown_key,
                server_certificate,
            )
            await client.disconnect()

    try:
        asyncio.run(verify_rejection())
    finally:
        worker.stop()


def test_dashboard_client_subscribes_to_mock_server(tmp_path) -> None:
    server_uri = "urn:mock-linha:dashboard-test-server"
    client_uri = "urn:mock-linha:dashboard-test-client"
    server_certificate, server_key = generate(
        tmp_path / "server", "Dashboard Test Server", server_uri, "server"
    )
    client_certificate, client_key = generate(
        tmp_path / "client", "Dashboard Test Client", client_uri, "client"
    )
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    shutil.copy2(client_certificate, trusted / client_certificate.name)
    endpoint = f"opc.tcp://127.0.0.1:{free_port()}/mock-linha/"
    server_settings = OpcUaSettings(
        enabled=True,
        endpoint=endpoint,
        namespace_uri="urn:mock-linha:telemetria:v1",
        application_uri=server_uri,
        certificate_path=server_certificate,
        private_key_path=server_key,
        trusted_clients_dir=trusted,
    )
    server_active = Event()
    server = OpcUaServerWorker(
        server_settings,
        {},
        60.0,
        57.5,
        lambda status: server_active.set() if status == "ativo e seguro" else None,
    )
    server.start()
    assert server_active.wait(5)

    telemetry = TelemetryStore()
    client_connected = Event()
    client_settings = OpcUaClientSettings(
        enabled=True,
        endpoint=endpoint,
        namespace_uri=server_settings.namespace_uri,
        application_uri=client_uri,
        certificate_path=client_certificate,
        private_key_path=client_key,
        server_certificate_path=server_certificate,
        reconnect_seconds=0.1,
    )
    client = OpcUaClientWorker(
        client_settings,
        telemetry,
        lambda status: client_connected.set() if status == "conectado" else None,
    )
    client.start()
    try:
        assert client_connected.wait(5)
        initial = telemetry.snapshot(10)
        assert initial["connected"] is True
        assert initial["stations"]["12"]["takt_time"] == 60.0
        assert initial["stations"]["12"]["cycle_time"] == 57.5

        server.update_state(12, AndonCategory.MATERIAL, True)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if telemetry.snapshot(10)["stations"]["12"]["andon"]["material"]:
                break
            time.sleep(0.05)
        assert telemetry.snapshot(10)["stations"]["12"]["andon"]["material"] is True
    finally:
        client.stop()
        server.stop()
