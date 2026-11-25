from openpyxl import Workbook
import pytest

from services.base_import import (
    BaseImportError,
    load_metric_snapshots,
    parse_metric_matrix,
)


def test_parses_repeated_row_pairs() -> None:
    header = ["Medida", *(f"P{station:02d}" for station in range(1, 13))]
    matrix = [
        header,
        ["Takt time", *(60 + station for station in range(1, 13))],
        ["Ultimo ciclo", *(50 + station for station in range(1, 13))],
        ["Takt time", *(70 + station for station in range(1, 13))],
        ["Ultimo ciclo", *(55 + station for station in range(1, 13))],
    ]

    snapshots = parse_metric_matrix(matrix)

    assert len(snapshots) == 2
    assert snapshots[0].values[1] == (61.0, 51.0)
    assert snapshots[1].values[12] == (82.0, 67.0)


def test_parses_repeated_column_pairs() -> None:
    matrix = [["Posto", "Takt 1", "Ciclo 1", "Takt 2", "Ciclo 2"]]
    matrix.extend(
        [f"P{station:02d}", 60 + station, 50 + station, 70 + station, 55 + station]
        for station in range(1, 13)
    )

    snapshots = parse_metric_matrix(matrix)

    assert len(snapshots) == 2
    assert snapshots[0].values[12] == (72.0, 62.0)
    assert snapshots[1].values[1] == (71.0, 56.0)


def test_loads_xlsx_first_sheet(tmp_path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Medida", *(f"P{station:02d}" for station in range(1, 13))])
    sheet.append(["Takt time", *([60] * 12)])
    sheet.append(["Ultimo ciclo", *([57.5] * 12)])
    path = tmp_path / "base.xlsx"
    workbook.save(path)

    snapshots = load_metric_snapshots(path)

    assert snapshots[0].values[1] == (60.0, 57.5)
    assert snapshots[0].values[12] == (60.0, 57.5)


def test_rejects_incomplete_pair() -> None:
    matrix = [
        ["Medida", *(f"P{station:02d}" for station in range(1, 13))],
        ["Takt time", *([60] * 12)],
    ]

    with pytest.raises(BaseImportError, match="pares completos"):
        parse_metric_matrix(matrix)
