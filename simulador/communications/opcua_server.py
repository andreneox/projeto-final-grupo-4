from __future__ import annotations

import asyncio
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from typing import Callable

from cryptography import x509
from cryptography.hazmat.primitives import hashes

from config.settings import OpcUaSettings
from domain.models import AndonCategory
from security.certificates import (
    CertificateConfigurationError,
    load_trusted_certificates,
    validate_client_certificate,
    validate_server_credentials,
)

StatusCallback = Callable[[str], None]
StateKey = tuple[int, AndonCategory]


@dataclass(frozen=True)
class _AndonUpdate:
    station: int
    category: AndonCategory
    is_on: bool


@dataclass(frozen=True)
class _MetricUpdate:
    values: dict[int, tuple[float, float]]


class OpcUaServerWorker:
    def __init__(
        self,
        settings: OpcUaSettings,
        initial_states: dict[StateKey, bool],
        takt_time: float,
        last_cycle: float,
        status_callback: StatusCallback,
    ) -> None:
        self._settings = settings
        self._initial_states = initial_states
        self._takt_time = takt_time
        self._last_cycle = last_cycle
        self._status_callback = status_callback
        self._updates: Queue[_AndonUpdate | _MetricUpdate] = Queue()
        self._stop = Event()
        self._thread = Thread(target=self._thread_main, name="opcua-server", daemon=True)

    def start(self) -> None:
        if not self._settings.enabled:
            self._status_callback("desabilitado")
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)

    def update_state(
        self, station: int, category: AndonCategory, is_on: bool
    ) -> None:
        self._updates.put(_AndonUpdate(station, category, is_on))

    def update_metrics(
        self, values: dict[int, tuple[float, float]]
    ) -> None:
        self._updates.put(_MetricUpdate(dict(values)))

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self._status_callback(f"indisponivel: {exc}")

    async def _serve(self) -> None:
        from asyncua import Server, ua

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
        server.set_server_name("Mock Linha Telemetria")
        await server.set_application_uri(self._settings.application_uri)
        server.set_security_policy(
            [ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt]
        )
        await server.load_certificate(self._settings.certificate_path)
        await server.load_private_key(self._settings.private_key_path)
        server.set_certificate_validator(validate_client)
        namespace = await server.register_namespace(self._settings.namespace_uri)
        variables: dict[StateKey, object] = {}
        metric_variables: dict[int, tuple[object, object]] = {}

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
                variables[(station, category)] = await andon_node.add_variable(
                    ua.NodeId(path, namespace),
                    category.label,
                    self._initial_states.get((station, category), False),
                    ua.VariantType.Boolean,
                )
            takt_variable = await station_node.add_variable(
                ua.NodeId(f"{prefix}/TaktTime", namespace),
                "TaktTime",
                self._takt_time,
                ua.VariantType.Double,
            )
            cycle_variable = await station_node.add_variable(
                ua.NodeId(f"{prefix}/UltimoCiclo", namespace),
                "UltimoCiclo",
                self._last_cycle,
                ua.VariantType.Double,
            )
            metric_variables[station] = (takt_variable, cycle_variable)

        async with server:
            self._status_callback("ativo e seguro")
            while not self._stop.is_set():
                try:
                    update = self._updates.get_nowait()
                except Empty:
                    await asyncio.sleep(0.1)
                    continue
                if isinstance(update, _AndonUpdate):
                    await variables[(update.station, update.category)].write_value(
                        update.is_on
                    )
                    continue
                writes = []
                for station, (takt_time, last_cycle) in update.values.items():
                    takt_variable, cycle_variable = metric_variables[station]
                    writes.extend(
                        (
                            takt_variable.write_value(float(takt_time)),
                            cycle_variable.write_value(float(last_cycle)),
                        )
                    )
                await asyncio.gather(*writes)
