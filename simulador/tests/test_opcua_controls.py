from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from asyncua import ua

from communications.opcua_client import OpcUaClientWorker
from config.settings import OpcUaClientSettings
from services.telemetry import TelemetryStore


def settings() -> OpcUaClientSettings:
    return OpcUaClientSettings(
        enabled=True,
        endpoint="opc.tcp://127.0.0.1:4840/mock-linha/",
        namespace_uri="urn:mock-linha:telemetria:v1",
        application_uri="urn:test:client",
        certificate_path=Path("client.der"),
        private_key_path=Path("client.pem"),
        server_certificate_path=Path("server.der"),
        reconnect_seconds=1.0,
    )


class FakeLineNode:
    def __init__(self) -> None:
        self.calls = []

    async def call_method(self, method_id, argument) -> bool:
        self.calls.append((method_id, argument))
        return True


class FakeClient:
    def __init__(self, line: FakeLineNode) -> None:
        self.line = line
        self.requested_node = None

    def get_node(self, node_id):
        self.requested_node = node_id
        return self.line


def test_server_client_sends_both_control_methods_with_explicit_types() -> None:
    worker = OpcUaClientWorker(settings(), TelemetryStore(), lambda _status: None)
    worker._connected.set()
    speed = worker.request_motor_speed(72)
    stop = worker.request_line_stop(True)
    line = FakeLineNode()
    client = FakeClient(line)

    asyncio.run(worker._process_control_commands(client, 4))

    assert speed.result(timeout=0) is None
    assert stop.result(timeout=0) is None
    assert client.requested_node == ua.NodeId("Linha", 4)
    assert line.calls[0][0] == ua.NodeId("Linha/DefinirVelocidadeMotor", 4)
    assert line.calls[0][1].Value == 72
    assert line.calls[0][1].VariantType is ua.VariantType.UInt16
    assert line.calls[1][0] == ua.NodeId("Linha/DefinirParada", 4)
    assert line.calls[1][1].Value is True
    assert line.calls[1][1].VariantType is ua.VariantType.Boolean


def test_controls_validate_values_and_require_connection() -> None:
    worker = OpcUaClientWorker(settings(), TelemetryStore(), lambda _status: None)

    with pytest.raises(ValueError):
        worker.request_motor_speed(101)
    with pytest.raises(ValueError):
        worker.request_line_stop(1)
    with pytest.raises(RuntimeError, match="desconectado"):
        worker.request_motor_speed(50).result(timeout=0)
