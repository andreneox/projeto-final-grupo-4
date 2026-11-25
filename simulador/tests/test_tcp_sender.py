from datetime import datetime
import socketserver
from threading import Lock, Thread
import time

from communications.tcp_sender import TcpSender
from config.settings import TcpSettings
from domain.models import AndonCategory
from persistence.database import DatabaseWorker
from persistence.outbox import Outbox
from protocol.tcp_codec import ACK


class RecordingHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = bytearray()
        while len(data) < 16:
            chunk = self.request.recv(16 - len(data))
            if not chunk:
                return
            data.extend(chunk)
        with self.server.record_lock:
            self.server.received.append(bytes(data))
            reception = len(self.server.received)
        if reception == 1:
            self.request.sendall(b"invalid")
            return
        for chunk in (ACK[:3], ACK[3:17], ACK[17:]):
            self.request.sendall(chunk)


class RecordingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), RecordingHandler)
        self.received = []
        self.record_lock = Lock()


def test_sender_retries_head_then_preserves_fifo(tmp_path, monkeypatch) -> None:
    database = DatabaseWorker(tmp_path / "sender.db")
    database.start()
    payloads = []
    for station in (1, 2):
        result = database.submit(
            DatabaseWorker.toggle_and_enqueue,
            station,
            AndonCategory.QUALIDADE,
            datetime(2026, 8, 31, 16, 8, station),
        ).result()
        payloads.append(result[2])

    server = RecordingServer()
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    monkeypatch.setattr(TcpSender, "RETRY_DELAYS", (0.01,))
    settings = TcpSettings(
        host="127.0.0.1",
        port=server.server_address[1],
        connect_timeout_seconds=1,
        send_timeout_seconds=1,
        response_timeout_seconds=1,
        sync_on_start=False,
    )
    sender = TcpSender(settings, Outbox(database), lambda _status: None, lambda *_: None)
    sender.start()
    sender.wake()
    deadline = time.monotonic() + 5
    try:
        while time.monotonic() < deadline:
            if database.submit(DatabaseWorker.counts).result() == (0, 2):
                break
            time.sleep(0.02)
        assert database.submit(DatabaseWorker.counts).result() == (0, 2)
        assert server.received == [payloads[0], payloads[0], payloads[1]]
    finally:
        sender.stop()
        server.shutdown()
        server.server_close()
        database.stop()

