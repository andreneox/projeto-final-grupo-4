from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import Event
from time import monotonic

from gateway.config import ModbusSettings
from gateway.modbus_transport import PlcTransport
from gateway.register_map import ANDON_REGISTER_OFFSET, MOTOR_ON_REGISTER_OFFSET, STATION_COUNT


CYCLES_PER_STATION = 12
WORDS_PER_STATION = CYCLES_PER_STATION * 2
COMMAND_PULSE_SECONDS = 2.0
START_CONFIRMATION_SECONDS = 8.0


def encode_cycle_times(times: list[float]) -> tuple[int, ...]:
    if len(times) != STATION_COUNT * CYCLES_PER_STATION:
        raise ValueError("Expected 12 cycle times for each of the 12 stations")
    words = []
    for value in times:
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError("Cycle times must be numeric")
        scaled = Decimal(str(value)) * 10
        if (not scaled.is_finite() or not 1 <= scaled <= 65535
                or scaled != scaled.to_integral_value()):
            raise ValueError("Cycle times must fit one word in tenths of a second")
        words.append(int(scaled))
    return tuple(words)


@dataclass
class _Upload:
    words: tuple[int, ...]
    future: Future[None]
    station_index: int = 0


@dataclass
class _Start:
    future: Future[datetime | None]
    release_at: float | None
    confirm_by: float
    confirmed_at: datetime | None = None


@dataclass
class _Reset:
    future: Future[datetime]
    release_at: float | None
    confirm_by: float


class PlcCycleControl:
    """Advance recipe writes and the Start pulse on the serial worker."""

    def __init__(self, settings: ModbusSettings, transport: PlcTransport) -> None:
        self._settings = settings
        self._transport = transport
        self._ready = Event()
        self._upload: _Upload | None = None
        self._start: _Start | None = None
        self._reset: _Reset | None = None

    def ready(self) -> bool:
        return self._ready.is_set()

    def communication_failed(self, error: Exception) -> None:
        self._ready.clear()
        if self._upload is not None:
            self._upload.future.set_exception(error)
            self._upload = None

    def _require_no_pending_command(self) -> None:
        if self._upload is not None or self._start is not None or self._reset is not None:
            raise RuntimeError("A cycle base upload, Start or Reset is already in progress")

    def _require_idle(self) -> None:
        self._require_no_pending_command()
        if (self._settings.simulation_running_address is not None
                and self._transport.read_simulation_running()):
            raise RuntimeError("The PLC simulation is already running")

    def upload(self, words: tuple[int, ...], future: Future[None]) -> None:
        self._require_idle()
        self._ready.clear()
        self._upload = _Upload(words, future)

    def start(self, future: Future[datetime | None]) -> None:
        self._require_idle()
        if not self.ready():
            raise RuntimeError("Load and verify a cycle base before Start")
        if self._settings.process_status_address is None:
            raise RuntimeError("O Start exige a leitura do estado dos 12 postos")
        statuses = self._transport.read_process_statuses()
        if len(statuses) != STATION_COUNT or any(type(status) is not int or status != 0 for status in statuses):
            raise RuntimeError("Todos os 12 postos devem estar no estado 0 para dar Start")
        registers = self._transport.read_register_block()
        if any(registers[ANDON_REGISTER_OFFSET:MOTOR_ON_REGISTER_OFFSET]):
            raise RuntimeError("Libere todos os Andons antes de dar Start")
        now = monotonic()
        # Keep a pending release even if the PLC receives ON and its reply is lost.
        self._start = _Start(future, now, now + START_CONFIRMATION_SECONDS)
        self._transport.set_simulation_start(True)
        self._start.release_at = monotonic() + COMMAND_PULSE_SECONDS

    def reset_base(self, future: Future[datetime]) -> None:
        self._require_no_pending_command()
        if self._settings.production_count_address is None:
            raise RuntimeError("Configure a leitura do contador D16052 para confirmar a limpeza")
        now = monotonic()
        # Keep Reset OFF pending even if the ON reply is lost.
        self._reset = _Reset(future, now, now + START_CONFIRMATION_SECONDS)
        self._transport.set_base_reset(True)
        self._reset.release_at = monotonic() + COMMAND_PULSE_SECONDS

    def time_to_release(self) -> float | None:
        pulse = self._start or self._reset
        if pulse is None or pulse.release_at is None:
            return None
        return max(0.0, pulse.release_at - monotonic())

    def advance(self) -> None:
        if self._start is not None:
            self._advance_start(self._start)
        if self._reset is not None:
            self._advance_reset(self._reset)
        if self._upload is not None:
            self._advance_upload(self._upload)

    def _advance_upload(self, upload: _Upload) -> None:
        index = upload.station_index
        offset = index * CYCLES_PER_STATION
        words = upload.words[offset : offset + CYCLES_PER_STATION]
        address = self._settings.cycle_base_address + index * WORDS_PER_STATION
        self._transport.write_cycle_block(address, list(words) * 2)
        upload.station_index += 1
        if upload.station_index == STATION_COUNT:
            self._ready.set()
            self._upload = None
            upload.future.set_result(None)

    def _advance_start(self, start: _Start) -> None:
        now = monotonic()
        if start.release_at is not None and now >= start.release_at:
            try:
                self._transport.set_simulation_start(False)
            except Exception as exc:
                if not start.future.done():
                    start.future.set_exception(exc)
                raise
            start.release_at = None
        if start.future.done():
            if start.release_at is None:
                self._start = None
            return
        running_address = self._settings.simulation_running_address
        expects_confirmation = (
            running_address is not None or self._settings.process_status_address is not None
        )
        if expects_confirmation and start.confirmed_at is None and now < start.confirm_by:
            running = (
                self._transport.read_simulation_running()
                if running_address is not None else 2 in self._transport.read_process_statuses()
            )
            if running:
                start.confirmed_at = datetime.now(timezone.utc)
        if start.release_at is None and (
            not expects_confirmation or start.confirmed_at is not None or now >= start.confirm_by
        ):
            self._start = None
            start.future.set_result(start.confirmed_at)

    def _advance_reset(self, reset: _Reset) -> None:
        now = monotonic()
        if reset.release_at is not None:
            if now < reset.release_at:
                return
            try:
                self._transport.set_base_reset(False)
            except Exception as exc:
                if not reset.future.done():
                    reset.future.set_exception(exc)
                raise
            reset.release_at = None
        if reset.future.done():
            self._reset = None
            return
        if now >= reset.confirm_by:
            self._reset = None
            reset.future.set_exception(RuntimeError("O CLP não confirmou o reset dos postos"))
            return
        if self._transport.read_production_count() != 0:
            return
        if self._settings.process_status_address is not None and any(
            state not in (0, 1) for state in self._transport.read_process_statuses()
        ):
            return
        self._reset = None
        reset.future.set_result(datetime.now(timezone.utc))

    def stop(self) -> None:
        self._ready.clear()
        for operation in (self._upload, self._start, self._reset):
            if operation is not None and not operation.future.done():
                operation.future.set_exception(RuntimeError("Modbus poller stopped"))
        if self._start is not None and self._start.release_at is not None:
            self._transport.set_simulation_start(False)
        if self._reset is not None and self._reset.release_at is not None:
            self._transport.set_base_reset(False)
