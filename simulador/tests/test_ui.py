from PyQt6.QtCore import QSettings

from domain.models import AndonCategory
from services.base_import import MetricSnapshot
import ui.main_window as main_window_module
from ui.main_window import MainWindow


def test_window_has_twelve_stations_and_state_is_local(qtbot) -> None:
    window = MainWindow(60.0, 57.5)
    qtbot.addWidget(window)
    assert len(window.grid._buttons) == 48

    target = window.grid._buttons[(12, AndonCategory.MATERIAL)]
    neighbor = window.grid._buttons[(11, AndonCategory.MATERIAL)]
    window.set_andon_state(12, AndonCategory.MATERIAL, True)

    assert "ligado" in target.toolTip()
    assert "desligado" in neighbor.toolTip()


def test_manual_metric_edit_enables_execute_and_clear_restores_defaults(qtbot) -> None:
    window = MainWindow(60.0, 57.5)
    qtbot.addWidget(window)
    published = []
    window.metrics_published.connect(published.append)

    edit = window.grid._metric_edits[(1, "takt")]
    edit.selectAll()
    qtbot.keyClicks(edit, "61,5")

    assert window.grid.execute_button.isEnabled()
    window.grid.execute_button.click()
    assert published[-1][1] == (61.5, 57.5)
    assert not window.grid.execute_button.isEnabled()

    window.grid.clear_button.click()
    assert window.grid.metrics()[1] == (60.0, 57.5)
    assert published[-1][1] == (60.0, 57.5)
    assert not window.grid.execute_button.isEnabled()


def test_import_publishes_each_snapshot_one_second_apart(qtbot) -> None:
    window = MainWindow(60.0, 57.5)
    qtbot.addWidget(window)
    published = []
    window.metrics_published.connect(published.append)
    first = MetricSnapshot({station: (61.0, 58.0) for station in range(1, 13)})
    second = MetricSnapshot({station: (62.0, 59.0) for station in range(1, 13)})

    window.start_import([first, second], "base.xlsx")

    assert published == [first.values]
    assert not window.grid.import_button.isEnabled()
    assert window.grid._metric_edits[(1, "takt")].isReadOnly()
    qtbot.waitUntil(lambda: len(published) == 2, timeout=2000)
    assert published[-1] == second.values
    assert window.grid.metrics()[12] == (62.0, 59.0)
    assert window.grid.import_button.isEnabled()
    assert not window.grid.execute_button.isEnabled()


def test_import_dialog_remembers_last_directory_across_windows(
    qtbot, tmp_path, monkeypatch
) -> None:
    previous = tmp_path / "anterior"
    selected = tmp_path / "nova"
    previous.mkdir()
    selected.mkdir()
    settings_path = tmp_path / "preferences.ini"
    preferences = QSettings(str(settings_path), QSettings.Format.IniFormat)
    preferences.setValue("import/last_directory", str(previous))
    preferences.sync()
    opened_at = []

    def choose_file(_parent, _title, directory, _filter):
        opened_at.append(directory)
        return str(selected / "base.xlsx"), "Planilhas (*.xlsx)"

    values = {station: (60.0, 57.5) for station in range(1, 13)}
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", choose_file
    )
    monkeypatch.setattr(
        main_window_module,
        "load_metric_snapshots",
        lambda _filename: [MetricSnapshot(values)],
    )

    first_window = MainWindow(60.0, 57.5, preferences)
    qtbot.addWidget(first_window)
    first_window.choose_import_file()

    assert opened_at == [str(previous)]
    reloaded_preferences = QSettings(
        str(settings_path), QSettings.Format.IniFormat
    )
    second_window = MainWindow(60.0, 57.5, reloaded_preferences)
    qtbot.addWidget(second_window)
    assert second_window._last_import_directory == selected
