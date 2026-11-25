from __future__ import annotations

import asyncio
from concurrent.futures import Future
from datetime import datetime
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import monotonic
from typing import Callable

from asyncua import Client, ua
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

from config.settings import OpcUaClientSettings
from domain.models import AndonCategory
from domain.work_instruction import INSTRUCTION_NODE
from services.telemetry import PROCESS_STATUS_NODE, PRODUCTION_COUNT_NODE, TelemetryStore

StatusCallback = Callable[[str], None]


class _SubscriptionHandler:
    def __init__(self, telemetry: TelemetryStore) -> None:
        self._telemetry = telemetry

    def datachange_notification(self, node, value, _data) -> None:
        self._telemetry.update(str(node.nodeid.Identifier), value)


class OpcUaClientWorker:
    """Secure OPC UA subscriber with cooperative reconnects."""

    def __init__(
        self,
        settings: OpcUaClientSettings,
        telemetry: TelemetryStore,
        status_callback: StatusCallback,
    ) -> None:
        self._settings = settings
        self._telemetry = telemetry
        self._status_callback = status_callback
        self._stop = Event()
        self._connected = Event()
        self._commands: Queue[tuple[str, object, Future]] = Queue()
        self._commands_lock = Lock()
        self._thread = Thread(
            target=self._thread_main, name="opcua-client", daemon=True
        )

    def start(self) -> None:
        if not self._settings.enabled:
            self._telemetry.set_connection(False, "desabilitado")
            self._status_callback("desabilitado")
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._disconnect_commands("cliente OPC UA encerrado")
        if self._thread.is_alive():
            self._thread.join(timeout=10)

    def set_motor_speed(self, speed: int, timeout: float = 5.0) -> None:
        self.request_motor_speed(speed).result(timeout=timeout)

    def set_line_stopped(self, stopped: bool, timeout: float = 5.0) -> None:
        self.request_line_stop(stopped).result(timeout=timeout)

    def request_motor_speed(self, speed: int) -> Future[None]:
        if isinstance(speed, bool) or not isinstance(speed, int) or not 0 <= speed <= 100:
            raise ValueError("A velocidade deve ser um inteiro entre 0 e 100")
        return self._queue_command("motor_speed", speed)

    def request_line_stop(self, stopped: bool) -> Future[None]:
        if not isinstance(stopped, bool):
            raise ValueError("O comando de parada deve ser booleano")
        return self._queue_command("line_stop", stopped)

    def request_cycle_base(self, times: list[float]) -> Future[None]:
        return self._queue_command("cycle_base", times)

    def request_cycle_base_ready(self) -> Future[bool]:
        return self._queue_command("cycle_base_ready", None)

    def request_simulation_start(self) -> Future[datetime | None]:
        return self._queue_command("simulation_start", None)

    def request_base_reset(self) -> Future[datetime]:
        return self._queue_command("base_reset", None)

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._subscribe_once()
            except Exception as exc:
                status = f"desconectado: {exc}"
                self._telemetry.set_connection(False, status)
                self._status_callback(status)
            if not self._stop.is_set():
                await asyncio.sleep(self._settings.reconnect_seconds)

    async def _subscribe_once(self) -> None:
        client = Client(self._settings.endpoint, timeout=15)
        client.application_uri = self._settings.application_uri
        await client.set_security(
            SecurityPolicyBasic256Sha256,
            self._settings.certificate_path,
            self._settings.private_key_path,
            server_certificate=self._settings.server_certificate_path,
            mode=ua.MessageSecurityMode.SignAndEncrypt,
        )
        subscription = None
        try:
            await client.connect()
            namespace = await client.get_namespace_index(self._settings.namespace_uri)
            nodes = []
            for station in range(1, 13):
                prefix = f"P{station:02d}"
                for category in AndonCategory:
                    nodes.append(
                        client.get_node(
                            ua.NodeId(f"{prefix}/Andon/{category.label}", namespace)
                        )
                    )
                nodes.append(
                    client.get_node(ua.NodeId(f"{prefix}/TaktTime", namespace))
                )
                nodes.append(
                    client.get_node(ua.NodeId(f"{prefix}/UltimoCiclo", namespace))
                )

            values = await client.read_values(nodes)
            for node, value in zip(nodes, values, strict=True):
                self._telemetry.update(str(node.nodeid.Identifier), value)

            # These nodes may be absent on earlier Gateway or Desktop versions.
            for path in (INSTRUCTION_NODE, PRODUCTION_COUNT_NODE, PROCESS_STATUS_NODE):
                node = client.get_node(ua.NodeId(path, namespace))
                try:
                    value = await node.read_value()
                except ua.UaStatusCodeError:
                    self._telemetry.update(path, None)
                else:
                    self._telemetry.update(path, value)
                    nodes.append(node)

            subscription = await client.create_subscription(
                100, _SubscriptionHandler(self._telemetry)
            )
            await subscription.subscribe_data_change(nodes)
            self._connected.set()
            self._telemetry.set_connection(True, "conectado")
            self._status_callback("conectado")

            next_health_check = 0.0
            while not self._stop.is_set():
                await self._process_control_commands(client, namespace)
                now = monotonic()
                if now >= next_health_check:
                    await client.nodes.server_state.read_value()
                    self._telemetry.mark_alive()
                    next_health_check = now + 1.0
                await asyncio.sleep(0.05)
        finally:
            self._disconnect_commands("conexão OPC UA perdida")
            self._telemetry.set_connection(False, "desconectado")
            if subscription is not None:
                try:
                    await subscription.delete()
                except Exception:
                    pass
            try:
                await client.disconnect()
            except Exception:
                pass

    def _queue_command(self, name: str, value: object) -> Future:
        future = Future()
        if not self._settings.enabled:
            future.set_exception(RuntimeError("cliente OPC UA desabilitado"))
            return future
        with self._commands_lock:
            if self._stop.is_set() or not self._connected.is_set():
                future.set_exception(RuntimeError("cliente OPC UA desconectado"))
                return future
            self._commands.put((name, value, future))
        return future

    async def _process_control_commands(self, client: Client, namespace: int) -> None:
        line = client.get_node(ua.NodeId("Linha", namespace))
        while not self._stop.is_set():
            try:
                name, value, future = self._commands.get_nowait()
            except Empty:
                return
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = None
                if name == "motor_speed":
                    await line.call_method(
                        ua.NodeId("Linha/DefinirVelocidadeMotor", namespace),
                        ua.Variant(int(value), ua.VariantType.UInt16),
                    )
                elif name == "line_stop":
                    await line.call_method(
                        ua.NodeId("Linha/DefinirParada", namespace),
                        ua.Variant(bool(value), ua.VariantType.Boolean),
                    )
                elif name == "cycle_base":
                    error = await line.call_method(
                        ua.NodeId("Linha/CarregarBaseCiclos", namespace),
                        ua.Variant(value, ua.VariantType.Double),
                    )
                    if error:
                        raise RuntimeError(error)
                elif name == "cycle_base_ready":
                    result = await line.call_method(ua.NodeId("Linha/BaseCiclosCarregada", namespace))
                elif name == "simulation_start":
                    confirmed, error = await line.call_method(ua.NodeId("Linha/IniciarSimulacao", namespace))
                    if error:
                        raise RuntimeError(error)
                    result = datetime.fromisoformat(confirmed) if confirmed else None
                elif name == "base_reset":
                    confirmed, error = await line.call_method(ua.NodeId("Linha/LimparBase", namespace))
                    if error or not confirmed:
                        raise RuntimeError(error or "O CLP não confirmou a limpeza.")
                    result = datetime.fromisoformat(confirmed)
                future.set_result(result)
            except BaseException as exc:
                future.set_exception(exc)

    def _disconnect_commands(self, message: str) -> None:
        with self._commands_lock:
            self._connected.clear()
        while True:
            try:
                _name, _value, future = self._commands.get_nowait()
            except Empty:
                return
            if future.set_running_or_notify_cancel():
                future.set_exception(RuntimeError(message))
