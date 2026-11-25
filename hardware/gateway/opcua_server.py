from __future__ import annotations

import asyncio
from concurrent.futures import Future
from datetime import datetime
from queue import Empty, Queue
from threading import Event, Thread
from typing import Callable

from cryptography import x509
from cryptography.hazmat.primitives import hashes

from gateway.config import OpcUaSettings
from gateway.domain import AndonCategory, StationTelemetry
from gateway.security import (
    CertificateConfigurationError,
    load_trusted_certificates,
    validate_client_certificate,
    validate_server_credentials,
)


StatusCallback = Callable[[str], None]
MotorSpeedCallback = Callable[[int], Future[None]]
LineStopCallback = Callable[[bool], Future[None]]


class OpcUaServerWorker:
    def __init__(
        self,
        settings: OpcUaSettings,
        status_callback: StatusCallback,
        motor_speed_callback: MotorSpeedCallback,
        line_stop_callback: LineStopCallback,
        cycle_base_callback: Callable[[list[float]], Future[None]] | None = None,
        simulation_start_callback: Callable[[], Future[datetime | None]] | None = None,
        cycle_base_ready: Callable[[], bool] | None = None,
        base_reset_callback: Callable[[], Future[datetime]] | None = None,
    ) -> None:
        self._settings = settings
        self._status_callback = status_callback
        self._motor_speed_callback = motor_speed_callback
        self._line_stop_callback = line_stop_callback
        self._cycle_base_callback = cycle_base_callback
        self._simulation_start_callback = simulation_start_callback
        self._cycle_base_ready = cycle_base_ready
        self._base_reset_callback = base_reset_callback
        self._updates: Queue[dict[int, StationTelemetry]] = Queue()
        self._stop = Event()
        self._thread = Thread(target=self._thread_main, name="opcua-server", daemon=True)

    def start(self) -> None:
        if not self._settings.enabled:
            self._status_callback("disabled")
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)

    def update_telemetry(self, stations: dict[int, StationTelemetry]) -> None:
        self._updates.put(dict(stations))

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self._status_callback(f"unavailable: {exc}")

    async def _serve(self) -> None:
        from asyncua import Server, ua, uamethod

        validate_server_credentials(
            self._settings.certificate_path,
            self._settings.private_key_path,
            self._settings.application_uri,
        )
        trusted = load_trusted_certificates(self._settings.trusted_clients_dir)
        trusted_fingerprints = {
            certificate.fingerprint(hashes.SHA256()) for certificate in trusted
        }

        async def validate_client(
            certificate: x509.Certificate, application_description
        ) -> None:
            try:
                validate_client_certificate(
                    certificate,
                    application_description.ApplicationUri,
                    trusted_fingerprints,
                )
            except CertificateConfigurationError as exc:
                raise ua.UaError(str(exc)) from exc

        server = Server()
        await server.init()
        server.set_endpoint(self._settings.endpoint)
        server.set_server_name("Gateway Linha Telemetria")
        await server.set_application_uri(self._settings.application_uri)
        server.set_security_policy(
            [ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt]
        )
        await server.load_certificate(self._settings.certificate_path)
        await server.load_private_key(self._settings.private_key_path)
        server.set_certificate_validator(validate_client)
        namespace = await server.register_namespace(self._settings.namespace_uri)
        state_variables: dict[tuple[int, AndonCategory], object] = {}
        metric_variables: dict[int, tuple[object, object]] = {}
        current = {
            station: StationTelemetry(
                states={category: False for category in AndonCategory},
                takt_time=0.0,
                last_cycle=0.0,
            )
            for station in range(1, 13)
        }

        @uamethod
        async def set_motor_speed(_parent, speed: int) -> bool:
            value = int(speed)
            if isinstance(speed, bool) or not 0 <= value <= 100:
                raise ua.UaError("Motor speed must be between 0 and 100")
            await asyncio.wrap_future(self._motor_speed_callback(value))
            return True

        @uamethod
        async def set_line_stopped(_parent, stopped: bool) -> bool:
            if not isinstance(stopped, bool):
                raise ua.UaError("Line stop command must be boolean")
            await asyncio.wrap_future(self._line_stop_callback(stopped))
            return True

        line_node = await server.nodes.objects.add_object(
            ua.NodeId("Linha", namespace), "Linha"
        )
        # A negative value marks the period before the first valid Modbus read.
        production_count = await line_node.add_variable(
            ua.NodeId("Linha/TotalProduzido", namespace), "TotalProduzido",
            -1, ua.VariantType.Int32,
        )
        process_statuses = [-1] * len(current)
        process_status = await line_node.add_variable(
            ua.NodeId("Linha/StatusProcesso", namespace), "StatusProcesso",
            process_statuses, ua.VariantType.Int32,
        )
        await line_node.add_method(
            ua.NodeId("Linha/DefinirVelocidadeMotor", namespace),
            "DefinirVelocidadeMotor",
            set_motor_speed,
            [ua.VariantType.UInt16],
            [ua.VariantType.Boolean],
        )
        await line_node.add_method(
            ua.NodeId("Linha/DefinirParada", namespace),
            "DefinirParada",
            set_line_stopped,
            [ua.VariantType.Boolean],
            [ua.VariantType.Boolean],
        )

        if (self._cycle_base_callback is not None and self._simulation_start_callback is not None
                and self._cycle_base_ready is not None):
            await self._add_simulation_methods(line_node, namespace, ua, uamethod)
        if self._base_reset_callback is not None:
            reset = self._base_reset_callback

            @uamethod
            async def reset_base(_parent):
                try:
                    confirmed = await asyncio.wrap_future(reset())
                except (RuntimeError, OSError) as exc:
                    return "", str(exc)
                return confirmed.isoformat(), ""

            await line_node.add_method(
                ua.NodeId("Linha/LimparBase", namespace), "LimparBase",
                reset_base, [], [ua.VariantType.String] * 2,
            )

        for station in range(1, 13):
            prefix = f"P{station:02d}"
            station_node = await server.nodes.objects.add_object(
                ua.NodeId(prefix, namespace), prefix
            )
            andon_node = await station_node.add_object(
                ua.NodeId(f"{prefix}/Andon", namespace), "Andon"
            )
            for category in AndonCategory:
                path = f"{prefix}/Andon/{category.label}"
                state_variables[(station, category)] = await andon_node.add_variable(
                    ua.NodeId(path, namespace),
                    category.label,
                    False,
                    ua.VariantType.Boolean,
                )
            takt = await station_node.add_variable(
                ua.NodeId(f"{prefix}/TaktTime", namespace),
                "TaktTime",
                0.0,
                ua.VariantType.Double,
            )
            cycle = await station_node.add_variable(
                ua.NodeId(f"{prefix}/UltimoCiclo", namespace),
                "UltimoCiclo",
                0.0,
                ua.VariantType.Double,
            )
            metric_variables[station] = (takt, cycle)

        async with server:
            self._status_callback("active and secure")
            while not self._stop.is_set():
                try:
                    latest = self._updates.get_nowait()
                except Empty:
                    await asyncio.sleep(0.05)
                    continue
                while True:
                    try:
                        latest = self._updates.get_nowait()
                    except Empty:
                        break

                writes = []
                next_statuses = process_statuses.copy()
                for station, telemetry in latest.items():
                    previous = current[station]
                    for category, is_on in telemetry.states.items():
                        if previous.states[category] != is_on:
                            writes.append(
                                state_variables[(station, category)].write_value(is_on)
                            )
                    takt, cycle = metric_variables[station]
                    if previous.takt_time != telemetry.takt_time:
                        writes.append(takt.write_value(float(telemetry.takt_time)))
                    if previous.last_cycle != telemetry.last_cycle:
                        writes.append(cycle.write_value(float(telemetry.last_cycle)))
                    if (station == 12 and telemetry.production_count is not None
                            and previous.production_count != telemetry.production_count):
                        writes.append(production_count.write_value(
                            ua.Variant(telemetry.production_count, ua.VariantType.Int32)
                        ))
                    current[station] = telemetry
                    next_statuses[station - 1] = (
                        -1 if telemetry.process_status is None else telemetry.process_status
                    )
                if next_statuses != process_statuses:
                    process_statuses = next_statuses
                    writes.append(process_status.write_value(
                        ua.Variant(process_statuses, ua.VariantType.Int32)
                    ))
                if writes:
                    await asyncio.gather(*writes)

    async def _add_simulation_methods(self, line, namespace, ua, uamethod) -> None:
        upload = self._cycle_base_callback
        start = self._simulation_start_callback
        ready = self._cycle_base_ready
        assert upload is not None and start is not None and ready is not None

        @uamethod
        async def load_base(_parent, times):
            try:
                if not isinstance(times, list):
                    raise ValueError("Expected a list of cycle times")
                await asyncio.wrap_future(upload(times))
            except (ValueError, RuntimeError, OSError) as exc:
                return str(exc)
            return ""

        @uamethod
        async def start_simulation(_parent):
            try:
                confirmed = await asyncio.wrap_future(start())
            except (RuntimeError, OSError) as exc:
                return "", str(exc)
            return confirmed.isoformat() if confirmed else "", ""

        @uamethod
        def base_ready(_parent):
            return ready()

        times = ua.Argument()
        times.Name = "CycleTimesSeconds"
        times.Description = ua.LocalizedText("12 times per station, ordered from P01 to P12")
        times.DataType = ua.NodeId(ua.VariantType.Double.value)
        times.ValueRank = 1
        times.ArrayDimensions = [144]
        await line.add_method(ua.NodeId("Linha/CarregarBaseCiclos", namespace),
                              "CarregarBaseCiclos", load_base, [times], [ua.VariantType.String])
        await line.add_method(ua.NodeId("Linha/BaseCiclosCarregada", namespace),
                              "BaseCiclosCarregada", base_ready, [], [ua.VariantType.Boolean])
        await line.add_method(ua.NodeId("Linha/IniciarSimulacao", namespace),
                              "IniciarSimulacao", start_simulation, [], [ua.VariantType.String] * 2)
