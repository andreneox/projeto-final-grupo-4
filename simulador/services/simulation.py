from __future__ import annotations

from concurrent.futures import Future
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from domain.clock import LogicalClock
from domain.models import AndonCategory
from persistence.database import DatabaseWorker


class SimulationService(QObject):
    state_changed = pyqtSignal(int, object, bool)
    operation_failed = pyqtSignal(str)
    event_enqueued = pyqtSignal(int)

    def __init__(self, database: DatabaseWorker, clock: LogicalClock) -> None:
        super().__init__()
        self._database = database
        self._clock = clock

    def toggle(self, station: int, category: AndonCategory) -> None:
        occurred_at = self._clock.now()
        future = self._database.submit(
            DatabaseWorker.toggle_and_enqueue, station, category, occurred_at
        )
        future.add_done_callback(
            lambda completed: self._toggle_completed(station, category, completed)
        )

    def load_states(
        self, callback: Callable[[dict[tuple[int, AndonCategory], bool]], None]
    ) -> None:
        future = self._database.submit(DatabaseWorker.load_states)

        def completed(result: Future) -> None:
            try:
                callback(result.result())
            except Exception as exc:
                self.operation_failed.emit(f"Falha ao carregar estados: {exc}")

        future.add_done_callback(completed)

    def _toggle_completed(
        self,
        station: int,
        category: AndonCategory,
        future: Future,
    ) -> None:
        try:
            is_on, event_id, _payload = future.result()
        except Exception as exc:
            self.operation_failed.emit(
                f"Estado nao alterado: falha ao gravar no banco ({exc})"
            )
            return
        self.state_changed.emit(station, category, is_on)
        self.event_enqueued.emit(event_id)

