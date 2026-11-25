from __future__ import annotations

import asyncio
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
import shutil
import socket
from threading import Event
import time

import pytest
from asyncua import Client, ua
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

from gateway.config import OpcUaSettings
from gateway.domain import AndonCategory, StationTelemetry
from gateway.opcua_server import OpcUaServerWorker
from tools.generate_dev_certificates import generate


def free_port() -> int:
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return int(connection.getsockname()[1])


async def secure_client(
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


def test_secure_server_exposes_and_updates_the_same_72_nodes(tmp_path) -> None:
    server_uri = "urn:gateway:test-server"
    client_uri = "urn:gateway:test-client"
    server_certificate, server_key = generate(
        tmp_path / "server", "Gateway Test", server_uri, "server"
    )
    client_certificate, client_key = generate(
        tmp_path / "client", "Gateway Client", client_uri, "client"
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
        if status == "active and secure":
            active.set()

    commands = []

    def completed_command(name: str, value: int | bool) -> Future[None]:
        commands.append((name, value))
        future: Future[None] = Future()
        future.set_result(None)
        return future

    server = OpcUaServerWorker(
        settings,
        status_changed,
        lambda speed: completed_command("speed", speed),
        lambda stopped: completed_command("stop", stopped),
        base_reset_callback=lambda: reset_result,
    )
    reset_result = Future()
    reset_at = datetime(2026, 11, 21, 14, 0, tzinfo=timezone.utc)
    reset_result.set_result(reset_at)
    server.start()
    assert active.wait(10), statuses

    async def verify() -> None:
        client = await secure_client(
            endpoint, client_uri, client_certificate, client_key, server_certificate
        )
        try:
            namespace = await client.get_namespace_index(settings.namespace_uri)
            paths = []
            for station in range(1, 13):
                prefix = f"P{station:02d}"
                paths.extend(
                    f"{prefix}/Andon/{category.label}" for category in AndonCategory
                )
                paths.extend((f"{prefix}/TaktTime", f"{prefix}/UltimoCiclo"))
            assert len(paths) == 72
            nodes = [client.get_node(ua.NodeId(path, namespace)) for path in paths]
            assert len(await client.read_values(nodes)) == 72
            total = client.get_node(ua.NodeId("Linha/TotalProduzido", namespace))
            assert await total.read_value() == -1
            process = client.get_node(ua.NodeId("Linha/StatusProcesso", namespace))
            assert await process.read_value() == [-1] * 12

            telemetry = {
                station: StationTelemetry(
                    states={category: False for category in AndonCategory},
                    takt_time=60.0,
                    last_cycle=57.5,
                    process_status=station % 4,
                )
                for station in range(1, 13)
            }
            telemetry[12] = StationTelemetry(
                states={
                    category: category is AndonCategory.MATERIAL
                    for category in AndonCategory
                },
                takt_time=62.0,
                last_cycle=61.25,
                production_count=7,
                process_status=3,
            )
            server.update_telemetry(telemetry)
            material = client.get_node(
                ua.NodeId("P12/Andon/Material", namespace)
            )
            cycle = client.get_node(ua.NodeId("P12/UltimoCiclo", namespace))
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if await total.read_value() == 7:
                    break
                await asyncio.sleep(0.05)
            assert await material.read_value() is True
            assert await cycle.read_value() == 61.25
            assert await total.read_value() == 7
            assert await process.read_value() == [1, 2, 3, 0] * 2 + [1, 2, 3, 3]

            line = client.get_node(ua.NodeId("Linha", namespace))
            speed_result = await line.call_method(
                ua.NodeId("Linha/DefinirVelocidadeMotor", namespace),
                ua.Variant(73, ua.VariantType.UInt16),
            )
            stop_result = await line.call_method(
                ua.NodeId("Linha/DefinirParada", namespace),
                ua.Variant(True, ua.VariantType.Boolean),
            )
            assert speed_result is True
            assert stop_result is True
            assert commands == [("speed", 73), ("stop", True)]
            assert await line.call_method(ua.NodeId("Linha/LimparBase", namespace)) == [
                reset_at.isoformat(), "",
            ]

            with pytest.raises(Exception):
                await line.call_method(
                    ua.NodeId("Linha/DefinirVelocidadeMotor", namespace),
                    ua.Variant(101, ua.VariantType.UInt16),
                )
        finally:
            await client.disconnect()

    try:
        asyncio.run(verify())
    finally:
        server.stop()
