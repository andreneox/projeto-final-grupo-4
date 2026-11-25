from datetime import datetime

import pytest

from domain.models import AndonCategory
from persistence.database import DatabaseWorker


@pytest.fixture
def database(tmp_path):
    worker = DatabaseWorker(tmp_path / "mock.db")
    worker.start()
    yield worker
    worker.stop()


def test_toggle_is_atomic_and_persists_queue(database: DatabaseWorker) -> None:
    timestamp = datetime(2026, 8, 31, 16, 8, 10)
    first = database.submit(
        DatabaseWorker.toggle_and_enqueue,
        1,
        AndonCategory.QUALIDADE,
        timestamp,
    ).result()
    second = database.submit(
        DatabaseWorker.toggle_and_enqueue,
        1,
        AndonCategory.QUALIDADE,
        timestamp,
    ).result()

    assert first[0] is True
    assert second[0] is False
    pending, confirmed = database.submit(DatabaseWorker.counts).result()
    assert (pending, confirmed) == (2, 0)
    states = database.submit(DatabaseWorker.load_states).result()
    assert states[(1, AndonCategory.QUALIDADE)] is False


def test_restart_restores_state_and_pending_queue(tmp_path) -> None:
    path = tmp_path / "mock.db"
    worker = DatabaseWorker(path)
    worker.start()
    worker.submit(
        DatabaseWorker.toggle_and_enqueue,
        12,
        AndonCategory.MATERIAL,
        datetime(2026, 8, 31),
    ).result()
    worker.stop()

    restarted = DatabaseWorker(path)
    restarted.start()
    try:
        states = restarted.submit(DatabaseWorker.load_states).result()
        event = restarted.submit(DatabaseWorker.first_pending).result()
        assert states[(12, AndonCategory.MATERIAL)] is True
        assert event is not None
        assert event.payload[2:4] == b"\x00\x0c"
    finally:
        restarted.stop()


def test_encoding_failure_rolls_back_state_and_event(database, monkeypatch) -> None:
    def fail(_event):
        raise RuntimeError("injected failure")

    monkeypatch.setattr("persistence.database.encode_event", fail)
    future = database.submit(
        DatabaseWorker.toggle_and_enqueue,
        1,
        AndonCategory.EQUIPAMENTO,
        datetime(2026, 8, 31),
    )
    with pytest.raises(RuntimeError, match="injected failure"):
        future.result()
    states = database.submit(DatabaseWorker.load_states).result()
    assert states[(1, AndonCategory.EQUIPAMENTO)] is False
    assert database.submit(DatabaseWorker.counts).result() == (0, 0)


def test_multiple_categories_can_be_on(database: DatabaseWorker) -> None:
    for category in (AndonCategory.QUALIDADE, AndonCategory.MATERIAL):
        database.submit(
            DatabaseWorker.toggle_and_enqueue,
            4,
            category,
            datetime(2026, 8, 31),
        ).result()
    states = database.submit(DatabaseWorker.load_states).result()
    assert states[(4, AndonCategory.QUALIDADE)] is True
    assert states[(4, AndonCategory.MATERIAL)] is True

