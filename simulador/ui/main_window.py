from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from domain.models import AndonCategory
from services.base_import import BaseImportError, MetricSnapshot, load_metric_snapshots
from ui.station_grid import StationGrid


class MainWindow(QMainWindow):
    closing = pyqtSignal()
    metrics_published = pyqtSignal(object)

    def __init__(
        self,
        takt_time: float,
        last_cycle: float,
        preferences: QSettings | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Simulador da Linha")
        self.setMinimumSize(940, 500)
        self.resize(1240, 610)
        self._default_metrics = {
            station: (takt_time, last_cycle) for station in range(1, 13)
        }
        self._import_snapshots: list[MetricSnapshot] = []
        self._import_index = 0
        self._import_source_name = "base"
        self._preferences = (
            preferences
            if preferences is not None
            else QSettings("Lean Manufacturing", "MockDesktop")
        )
        saved_directory = Path(
            self._preferences.value(
                "import/last_directory", str(Path.home()), type=str
            )
        )
        self._last_import_directory = (
            saved_directory if saved_directory.is_dir() else Path.home()
        )
        self._import_timer = QTimer(self)
        self._import_timer.setInterval(1000)
        self._import_timer.timeout.connect(self._publish_next_import)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26, 0, 26, 0)
        title = QLabel("Simulador da Linha")
        title.setObjectName("title")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self._opc_status = QLabel("OPC UA: iniciando")
        self._opc_status.setObjectName("headerStatus")
        header_layout.addWidget(self._opc_status)
        header.setFixedHeight(72)
        root_layout.addWidget(header)

        self.grid = StationGrid(takt_time, last_cycle)
        self.grid.metrics_edited.connect(self._metrics_edited)
        self.grid.execute_requested.connect(self.execute_metrics)
        self.grid.clear_requested.connect(self.clear_base)
        self.grid.import_requested.connect(self.choose_import_file)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.grid)
        root_layout.addWidget(scroll, 1)

        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 10, 24, 10)
        self._tcp_status = QLabel("TCP: iniciando")
        self._action_status = QLabel("")
        self._queue_status = QLabel("Pendentes: 0 | Confirmados: 0")
        footer_layout.addWidget(self._tcp_status)
        footer_layout.addStretch()
        footer_layout.addWidget(self._action_status)
        footer_layout.addStretch()
        footer_layout.addWidget(self._queue_status)
        root_layout.addWidget(footer)

        self.setCentralWidget(root)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #FFFFFF; color: #1F2937; }
            #header { background: #1F4E78; }
            #header QLabel { background: transparent; }
            #title { color: white; font-size: 22px; font-weight: 700; }
            #headerStatus { color: #E6EEF5; font-size: 12px; }
            #stationHeader { color: #1F4E78; font-weight: 700; qproperty-alignment: AlignCenter; }
            #rowHeader { font-size: 13px; font-weight: 600; }
            #metricValue {
                border: 1px solid #5B9BD5;
                padding: 5px 3px;
                color: #1F4E78;
                background: #F7FAFC;
            }
            #metricValue:focus { border: 2px solid #1F4E78; background: white; }
            #actionButton, #primaryButton {
                min-width: 104px; min-height: 30px; padding: 0 12px;
                border: 1px solid #5B9BD5; background: #F7FAFC; color: #1F4E78;
            }
            #actionButton:hover { background: #EAF2F8; }
            #actionButton:disabled { color: #9CA3AF; border-color: #D1D5DB; }
            #primaryButton { background: #2F6FB3; color: white; border: 0; }
            #primaryButton:hover { background: #255D96; }
            #primaryButton:disabled { background: #C5CDD6; color: #F3F4F6; }
            #footer { border-top: 1px solid #D7DEE5; background: #F7F9FB; }
            #footer QLabel { background: transparent; color: #4B5563; font-size: 12px; }
            """
        )

    def set_tcp_status(self, text: str) -> None:
        self._tcp_status.setText(f"TCP: {text}")

    def set_opc_status(self, text: str) -> None:
        self._opc_status.setText(f"OPC UA: {text}")

    def set_queue_counts(self, pending: int, confirmed: int) -> None:
        self._queue_status.setText(
            f"Pendentes: {pending} | Confirmados: {confirmed}"
        )

    def show_operation_error(self, message: str) -> None:
        QMessageBox.critical(self, "Falha de persistencia", message)

    def set_andon_state(
        self, station: int, category: AndonCategory, is_on: bool
    ) -> None:
        self.grid.set_state(station, category, is_on)

    def execute_metrics(self) -> None:
        try:
            values = self.grid.metrics()
        except ValueError as exc:
            QMessageBox.warning(self, "Valores invalidos", str(exc))
            return
        self.metrics_published.emit(values)
        self.grid.execute_button.setEnabled(False)
        self._action_status.setText("Valores enviados ao OPC UA")

    def choose_import_file(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "Importar base de tempos",
            str(self._last_import_directory),
            "Planilhas (*.xlsx *.xlsm *.csv)",
        )
        if not filename:
            return
        self._last_import_directory = Path(filename).parent
        self._preferences.setValue(
            "import/last_directory", str(self._last_import_directory)
        )
        self._preferences.sync()
        try:
            snapshots = load_metric_snapshots(filename)
        except BaseImportError as exc:
            QMessageBox.warning(self, "Base invalida", str(exc))
            return
        self.start_import(snapshots, Path(filename).name)

    def start_import(
        self, snapshots: list[MetricSnapshot], source_name: str = "base"
    ) -> None:
        if not snapshots:
            QMessageBox.warning(self, "Base invalida", "A base nao possui valores.")
            return
        self._import_timer.stop()
        self._import_snapshots = list(snapshots)
        self._import_index = 0
        self._import_source_name = source_name
        self.grid.set_metric_editing_enabled(False)
        self.grid.execute_button.setEnabled(False)
        self.grid.import_button.setEnabled(False)
        self._publish_next_import()

    def clear_base(self) -> None:
        self._import_timer.stop()
        self._import_snapshots = []
        self._import_index = 0
        self.grid.set_metric_editing_enabled(True)
        self.grid.import_button.setEnabled(True)
        self.grid.set_metrics(self._default_metrics)
        self.grid.execute_button.setEnabled(False)
        self.metrics_published.emit(dict(self._default_metrics))
        self._action_status.setText("Base limpa; valores padrao enviados")

    def _metrics_edited(self) -> None:
        if not self._import_timer.isActive() and not self._import_snapshots:
            self.grid.execute_button.setEnabled(True)
            self._action_status.setText("Alteracoes pendentes")

    def _publish_next_import(self) -> None:
        snapshot = self._import_snapshots[self._import_index]
        self.grid.set_metrics(snapshot.values)
        self.metrics_published.emit(dict(snapshot.values))
        self._import_index += 1
        total = len(self._import_snapshots)
        self._action_status.setText(
            f"Importando {self._import_source_name}: {self._import_index}/{total}"
        )
        if self._import_index < total:
            self._import_timer.start()
            return
        self._import_timer.stop()
        self._import_snapshots = []
        self.grid.set_metric_editing_enabled(True)
        self.grid.import_button.setEnabled(True)
        self.grid.execute_button.setEnabled(False)
        self._action_status.setText(
            f"Importacao concluida: {total} conjunto(s) enviado(s)"
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closing.emit()
        event.accept()
