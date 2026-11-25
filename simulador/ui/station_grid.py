from __future__ import annotations

from PyQt6.QtCore import QRegularExpression, Qt, pyqtSignal
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from domain.models import AndonCategory
from ui.andon_button import AndonButton


class StationGrid(QWidget):
    toggle_requested = pyqtSignal(int, object)
    metrics_edited = pyqtSignal()
    execute_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    import_requested = pyqtSignal()

    def __init__(self, takt_time: float, last_cycle: float) -> None:
        super().__init__()
        self._buttons: dict[tuple[int, AndonCategory], AndonButton] = {}
        self._metric_edits: dict[tuple[int, str], QLineEdit] = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(15)

        corner = QLabel("Indicador")
        corner.setObjectName("rowHeader")
        layout.addWidget(corner, 0, 0)
        for station in range(1, 13):
            label = QLabel(f"{station:02d}")
            label.setObjectName("stationHeader")
            label.setMinimumWidth(42)
            layout.addWidget(label, 0, station)

        for row, category in enumerate(AndonCategory, start=1):
            label = QLabel(category.label)
            label.setObjectName("rowHeader")
            color_bar = QFrame()
            color_bar.setFixedWidth(4)
            color_bar.setStyleSheet(f"background: {category.color}; border: 0;")
            label_layout = QGridLayout()
            label_layout.setContentsMargins(0, 0, 0, 0)
            label_layout.setHorizontalSpacing(9)
            label_layout.addWidget(color_bar, 0, 0)
            label_layout.addWidget(label, 0, 1)
            label_container = QWidget()
            label_container.setLayout(label_layout)
            layout.addWidget(label_container, row, 0)
            for station in range(1, 13):
                button = AndonButton(station, category)
                button.toggle_requested.connect(self.toggle_requested)
                self._buttons[(station, category)] = button
                layout.addWidget(button, row, station)

        validator = QRegularExpressionValidator(
            QRegularExpression(r"\d{0,7}([\.,]\d{0,3})?")
        )
        metrics = (
            ("takt", "Takt time", takt_time),
            ("cycle", "Ultimo ciclo", last_cycle),
        )
        for metric_row, (key, name, value) in enumerate(metrics, start=5):
            label = QLabel(name)
            label.setObjectName("rowHeader")
            layout.addWidget(label, metric_row, 0)
            for station in range(1, 13):
                metric = QLineEdit(self._format_value(value))
                metric.setValidator(validator)
                metric.setObjectName("metricValue")
                metric.setMinimumWidth(52)
                metric.setMaximumWidth(76)
                metric.setAlignment(Qt.AlignmentFlag.AlignCenter)
                metric.setAccessibleName(f"{name} P{station:02d}")
                metric.textEdited.connect(self.metrics_edited)
                self._metric_edits[(station, key)] = metric
                layout.addWidget(metric, metric_row, station)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 12, 0, 0)
        self.execute_button = QPushButton("Executar")
        self.execute_button.setObjectName("primaryButton")
        self.execute_button.setEnabled(False)
        self.clear_button = QPushButton("Limpar base")
        self.clear_button.setObjectName("actionButton")
        self.import_button = QPushButton("Importar base")
        self.import_button.setObjectName("actionButton")
        self.execute_button.clicked.connect(self.execute_requested)
        self.clear_button.clicked.connect(self.clear_requested)
        self.import_button.clicked.connect(self.import_requested)
        controls_layout.addWidget(self.execute_button)
        controls_layout.addStretch()
        controls_layout.addWidget(self.clear_button)
        controls_layout.addWidget(self.import_button)
        layout.addWidget(controls, 7, 0, 1, 13)

        layout.setColumnMinimumWidth(0, 150)
        layout.setColumnStretch(0, 2)
        for column in range(1, 13):
            layout.setColumnStretch(column, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_state(self, station: int, category: AndonCategory, is_on: bool) -> None:
        self._buttons[(station, category)].set_state(is_on)

    def apply_states(
        self, states: dict[tuple[int, AndonCategory], bool]
    ) -> None:
        for key, is_on in states.items():
            if key in self._buttons:
                self._buttons[key].set_state(is_on)

    def metrics(self) -> dict[int, tuple[float, float]]:
        values: dict[int, tuple[float, float]] = {}
        for station in range(1, 13):
            values[station] = (
                self._parse_value(self._metric_edits[(station, "takt")]),
                self._parse_value(self._metric_edits[(station, "cycle")]),
            )
        return values

    def set_metrics(self, values: dict[int, tuple[float, float]]) -> None:
        for station, (takt_time, last_cycle) in values.items():
            self._metric_edits[(station, "takt")].setText(
                self._format_value(takt_time)
            )
            self._metric_edits[(station, "cycle")].setText(
                self._format_value(last_cycle)
            )

    def set_metric_editing_enabled(self, enabled: bool) -> None:
        for metric in self._metric_edits.values():
            metric.setReadOnly(not enabled)

    @staticmethod
    def _format_value(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".").replace(".", ",")

    @staticmethod
    def _parse_value(metric: QLineEdit) -> float:
        text = metric.text().strip().replace(",", ".")
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"Valor invalido em {metric.accessibleName()}.") from exc
        if value < 0:
            raise ValueError(f"{metric.accessibleName()} nao pode ser negativo.")
        return value
