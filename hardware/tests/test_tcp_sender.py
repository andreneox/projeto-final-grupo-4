import socketserver
from threading import Thread
import time

import pytest

from gateway.config import TcpSettings
from gateway.protocol import ACK
from gateway.persistence import GatewayDatabase
from gateway.tcp_sender import TcpSender


PAYLOAD = bytes.fromhex(
    "00 01 00 01 08 26 16 31 10 08 20 01 00 01 00 01"
)
SECOND_PAYLOAD = bytes.fromhex(
    "00 01 00 01 08 26 16 31 20 08 20 01 00 01 00 02"
)


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        payload = bytearray()
        while len(payload) < 16:
            payload.extend(self.request.recv(16 - len(payload)))
        self.server.payloads.append(bytes(payload))
        response = self.server.response
        self.request.sendall(response[:7])
        self.request.sendall(response[7:])


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, address, response: bytes) -> None:
        super().__init__(address, Handler)
        self.response = response
        self.payloads = []


def settings(port: int) -> TcpSettings:
    return TcpSettings("127.0.0.1", port, 1.0, 1.0, 1.0)


def test_sends_exact_payload_and_accepts_fragmented_ack() -> None:
    server = Server(("127.0.0.1", 0), ACK)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sender = TcpSender(settings(server.server_address[1]), None, lambda _status: None)
        sender.send_event(PAYLOAD)
        assert server.payloads == [PAYLOAD]
    finally:
        server.shutdown()
        server.server_close()


def test_rejects_invalid_ack() -> None:
    server = Server(("127.0.0.1", 0), b"X" * len(ACK))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sender = TcpSender(settings(server.server_address[1]), None, lambda _status: None)
        with pytest.raises(ValueError, match="Invalid ACK"):
            sender.send_event(PAYLOAD)
    finally:
        server.shutdown()
        server.server_close()


def test_persisted_events_are_delivered_fifo(tmp_path) -> None:
    server = Server(("127.0.0.1", 0), ACK)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    database = GatewayDatabase(tmp_path / "gateway.db", "LINHA_A")
    database.start()
    database.capture_event(PAYLOAD)
    database.capture_event(SECOND_PAYLOAD)
    sender = TcpSender(
        settings(server.server_address[1]), database, lambda _status: None
    )
    sender.start()
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and database.counts() != (0, 2):
            time.sleep(0.02)
        assert database.counts() == (0, 2)
        assert server.payloads == [PAYLOAD, SECOND_PAYLOAD]
    finally:
        sender.stop()
        database.stop()
        server.shutdown()
        server.server_close()
