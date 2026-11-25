from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO, StringIO
from math import isfinite
from pathlib import Path
import re
from typing import BinaryIO, Sequence, TextIO


STATION_COUNT = 12


class BaseImportError(ValueError):
    pass


@dataclass(frozen=True)
class MetricSnapshot:
    values: dict[int, tuple[float, float]]


@dataclass(frozen=True)
class ImportedCycleBase:
    cycle_times: list[float]
    initial_takt_times: list[float]


def load_metric_snapshots(path: str | Path) -> list[MetricSnapshot]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        matrix = _load_workbook(source)
    elif suffix == ".csv":
        matrix = _load_csv(source)
    else:
        raise BaseImportError("Formato nao suportado. Use .xlsx, .xlsm ou .csv.")
    return parse_metric_matrix(matrix)


def load_cycle_times(content: bytes, filename: str) -> list[float]:
    return load_cycle_base(content, filename).cycle_times


def load_cycle_base(content: bytes, filename: str) -> ImportedCycleBase:
    extension = Path(filename).suffix.lower()
    if extension in {".xlsx", ".xlsm"}:
        matrix = _load_workbook(BytesIO(content))
    elif extension == ".csv":
        try:
            matrix = _read_csv(StringIO(content.decode("utf-8-sig")))
        except UnicodeError as exc:
            raise BaseImportError("Salve o CSV em UTF-8 para importar.") from exc
    else:
        raise BaseImportError("Formato não suportado. Use .xlsx, .xlsm ou .csv.")
    snapshots = parse_metric_matrix(matrix)
    if len(snapshots) != 12:
        raise BaseImportError(f"Informe 12 tempos de ciclo por posto. A base contém {len(snapshots)}.")
    times = []
    for station in range(1, STATION_COUNT + 1):
        for index, snapshot in enumerate(snapshots, 1):
            cycle = snapshot.values[station][1]
            scaled = Decimal(str(cycle)) * 10
            if (not scaled.is_finite() or not 1 <= scaled <= 65535
                    or scaled != scaled.to_integral_value()):
                raise BaseImportError(
                    f"P{station:02d}, ciclo {index}: use de 0,1 a 6553,5 s com até uma casa decimal."
                )
            times.append(cycle)
    initial_takt_times = [snapshots[0].values[station][0] for station in range(1, STATION_COUNT + 1)]
    return ImportedCycleBase(times, initial_takt_times)


def parse_metric_matrix(matrix: Sequence[Sequence[object]]) -> list[MetricSnapshot]:
    rows = [list(row) for row in matrix]
    if not rows:
        raise BaseImportError("A planilha esta vazia.")

    row_result = _parse_row_pairs(rows)
    if row_result is not None:
        return row_result

    column_result = _parse_column_pairs(rows)
    if column_result is not None:
        return column_result

    raise BaseImportError(
        "Cabecalho invalido. Informe P01 a P12 na primeira linha ou coluna, "
        "seguidos por pares de Takt time e Ultimo ciclo."
    )


def _load_workbook(path: Path | BinaryIO) -> list[list[object]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise BaseImportError(
            "A dependencia openpyxl nao esta instalada. Execute a instalacao "
            "das dependencias do projeto."
        ) from exc

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise BaseImportError(f"Nao foi possivel abrir a planilha: {exc}") from exc
    try:
        sheet = workbook.active
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _load_csv(path: Path) -> list[list[object]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return _read_csv(stream)
    except OSError as exc:
        raise BaseImportError(f"Nao foi possivel abrir o arquivo: {exc}") from exc


def _read_csv(stream: TextIO) -> list[list[object]]:
    sample = stream.read(4096)
    stream.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        return list(csv.reader(stream, delimiter=";"))
    return list(csv.reader(stream, dialect))


def _parse_row_pairs(rows: list[list[object]]) -> list[MetricSnapshot] | None:
    for header_index, row in enumerate(rows[:10]):
        columns = _station_positions(row)
        if len(columns) != STATION_COUNT:
            continue
        data_rows = [
            candidate
            for candidate in rows[header_index + 1 :]
            if any(_has_value(_cell(candidate, column)) for column in columns.values())
        ]
        if not data_rows or len(data_rows) % 2:
            raise BaseImportError(
                "Depois do cabecalho, use pares completos de linhas: "
                "Takt time e Ultimo ciclo."
            )
        snapshots = []
        for pair_index in range(0, len(data_rows), 2):
            takt_row = data_rows[pair_index]
            cycle_row = data_rows[pair_index + 1]
            snapshots.append(
                MetricSnapshot(
                    {
                        station: (
                            _metric(_cell(takt_row, column), station, "Takt time"),
                            _metric(
                                _cell(cycle_row, column), station, "Ultimo ciclo"
                            ),
                        )
                        for station, column in columns.items()
                    }
                )
            )
        return snapshots
    return None


def _parse_column_pairs(rows: list[list[object]]) -> list[MetricSnapshot] | None:
    width = max((len(row) for row in rows), default=0)
    for header_column in range(min(width, 10)):
        station_rows: dict[int, int] = {}
        for row_index, row in enumerate(rows):
            station = _station_number(_cell(row, header_column))
            if station is not None:
                station_rows[station] = row_index
        if len(station_rows) != STATION_COUNT:
            continue

        data_columns = [
            column
            for column in range(header_column + 1, width)
            if any(
                _has_value(_cell(rows[row_index], column))
                for row_index in station_rows.values()
            )
        ]
        if not data_columns or len(data_columns) % 2:
            raise BaseImportError(
                "Depois do cabecalho, use pares completos de colunas: "
                "Takt time e Ultimo ciclo."
            )
        snapshots = []
        for pair_index in range(0, len(data_columns), 2):
            takt_column = data_columns[pair_index]
            cycle_column = data_columns[pair_index + 1]
            snapshots.append(
                MetricSnapshot(
                    {
                        station: (
                            _metric(
                                _cell(rows[row_index], takt_column),
                                station,
                                "Takt time",
                            ),
                            _metric(
                                _cell(rows[row_index], cycle_column),
                                station,
                                "Ultimo ciclo",
                            ),
                        )
                        for station, row_index in station_rows.items()
                    }
                )
            )
        return snapshots
    return None


def _station_positions(values: Sequence[object]) -> dict[int, int]:
    positions: dict[int, int] = {}
    for index, value in enumerate(values):
        station = _station_number(value)
        if station is not None:
            positions[station] = index
    return positions


def _station_number(value: object) -> int | None:
    if value is None:
        return None
    match = re.fullmatch(r"P\s*0*(\d{1,2})", str(value).strip().upper())
    if not match:
        return None
    station = int(match.group(1))
    return station if 1 <= station <= STATION_COUNT else None


def _metric(value: object, station: int, name: str) -> float:
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise BaseImportError(
            f"{name} invalido para P{station:02d}: {value!r}."
        ) from exc
    if not isfinite(number):
        raise BaseImportError(f"{name} de P{station:02d} deve ser um número finito.")
    if number < 0:
        raise BaseImportError(f"{name} de P{station:02d} nao pode ser negativo.")
    return number


def _cell(row: Sequence[object], index: int) -> object:
    return row[index] if index < len(row) else None


def _has_value(value: object) -> bool:
    return value is not None and str(value).strip() != ""
