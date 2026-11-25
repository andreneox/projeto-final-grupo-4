from __future__ import annotations

from persistence.database import DatabaseWorker


class Outbox:
    def __init__(self, database: DatabaseWorker) -> None:
        self._database = database

    def first_pending(self):
        return self._database.submit(DatabaseWorker.first_pending).result(timeout=10)

    def record_failure(self, event_id: int, error: str) -> None:
        self._database.submit(
            DatabaseWorker.record_failure, event_id, error
        ).result(timeout=10)

    def mark_confirmed(self, event_id: int) -> None:
        self._database.submit(DatabaseWorker.mark_confirmed, event_id).result(timeout=10)

    def counts(self) -> tuple[int, int]:
        return self._database.submit(DatabaseWorker.counts).result(timeout=10)
