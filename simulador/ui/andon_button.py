from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton

from domain.models import AndonCategory


class AndonButton(QPushButton):
    toggle_requested = pyqtSignal(int, object)

    def __init__(self, station: int, category: AndonCategory) -> None:
        super().__init__()
        self.station = station
        self.category = category
        self._is_on = False
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"{category.label}, posto {station:02d}")
        self.clicked.connect(
            lambda: self.toggle_requested.emit(self.station, self.category)
        )
        self.set_state(False)

    def set_state(self, is_on: bool) -> None:
        self._is_on = is_on
        fill = self.category.color if is_on else "#F2F2F2"
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {fill};
                border: 2px solid {self.category.color};
                border-radius: 12px;
            }}
            QPushButton:hover {{ border-width: 3px; }}
            QPushButton:focus {{ outline: none; border-color: #1F2937; }}
            """
        )
        state = "ligado" if is_on else "desligado"
        self.setToolTip(
            f"Posto {self.station:02d} - {self.category.label} - {state}"
        )

