from __future__ import annotations

import argparse
import sys
from threading import Thread

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from communications.opcua_server import OpcUaServerWorker
from communications.tcp_sender import TcpSender, TcpTimeSynchronizer
from config.settings import load_settings
from domain.clock import LogicalClock
from persistence.database import DatabaseWorker
from persistence.outbox import Outbox
from services.simulation import SimulationService
from ui.main_window import MainWindow


class UiBridge(QObject):
    tcp_status = pyqtSignal(str)
    opc_status = pyqtSignal(str)
    queue_counts = pyqtSignal(int, int)


def run() -> int:
    parser = argparse.ArgumentParser(description="Simulador da Linha")
    parser.add_argument("--config", default="config.toml")
    args = parser.parse_args()
    settings = load_settings(args.config)

    database = DatabaseWorker(settings.application.database_path)
    database.start()
    initial_states = database.submit(DatabaseWorker.load_states).result(timeout=10)
    outbox = Outbox(database)
    clock = LogicalClock(settings.application.timezone)

    application = QApplication(sys.argv)
    application.setApplicationName("Simulador da Linha")
    window = MainWindow(
        settings.application.takt_time_seconds,
        settings.application.last_cycle_seconds,
    )
    bridge = UiBridge()
    bridge.tcp_status.connect(window.set_tcp_status)
    bridge.opc_status.connect(window.set_opc_status)
    bridge.queue_counts.connect(window.set_queue_counts)

    service = SimulationService(database, clock)
    sender = TcpSender(
        settings.tcp,
        outbox,
        bridge.tcp_status.emit,
        bridge.queue_counts.emit,
    )
    opcua = OpcUaServerWorker(
        settings.opcua,
        initial_states,
        settings.application.takt_time_seconds,
        settings.application.last_cycle_seconds,
        bridge.opc_status.emit,
    )
    window.grid.apply_states(initial_states)
    window.grid.toggle_requested.connect(service.toggle)
    service.state_changed.connect(window.set_andon_state)
    service.state_changed.connect(opcua.update_state)
    window.metrics_published.connect(opcua.update_metrics)
    service.operation_failed.connect(window.show_operation_error)
    service.event_enqueued.connect(lambda _event_id: sender.wake())

    stopped = False

    def shutdown() -> None:
        nonlocal stopped
        if stopped:
            return
        stopped = True
        sender.stop()
        opcua.stop()
        database.stop()

    application.aboutToQuit.connect(shutdown)
    sender.start()
    opcua.start()

    if settings.tcp.sync_on_start:
        synchronizer = TcpTimeSynchronizer(settings.tcp, clock)

        def synchronize_clock() -> None:
            try:
                synchronizer.synchronize()
                bridge.tcp_status.emit("relogio sincronizado")
            except Exception as exc:
                bridge.tcp_status.emit(f"sincronizacao de relogio falhou: {exc}")

        Thread(target=synchronize_clock, name="clock-sync", daemon=True).start()

    window.show()
    return application.exec()
