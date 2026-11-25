from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import random
from typing import Callable

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


STATIONS = tuple(range(1, 13))
SITUATIONS = tuple(range(10))
BASE_CYCLE = (55.2, 56.0, 54.8, 57.1, 56.5, 55.7, 58.2, 56.9, 55.4, 57.5, 56.2, 58.0)

ScenarioFunction = Callable[[int, int], tuple[float, float]]


@dataclass(frozen=True)
class Scenario:
    filename: str
    title: str
    description: str
    values: ScenarioFunction


def _round(values: tuple[float, float]) -> tuple[float, float]:
    return round(values[0], 1), round(max(0.0, values[1]), 1)


def _stable(situation: int, station: int) -> tuple[float, float]:
    variation = (-0.5, 0.1, 0.4, -0.2, 0.6, -0.3, 0.2, -0.4, 0.3, 0.0)
    phase = ((station * 3 + situation) % 5 - 2) * 0.1
    return _round((60.0, BASE_CYCLE[station - 1] + variation[situation] + phase))


def _increasing_cycle(situation: int, station: int) -> tuple[float, float]:
    return _round((60.0, BASE_CYCLE[station - 1] + situation * 0.85))


def _rotating_bottlenecks(situation: int, station: int) -> tuple[float, float]:
    targets = (2, 5, 8, 11, 3, 6, 9, 12, 4, 7)
    target = targets[situation]
    distance = abs(station - target)
    extra = 13.0 if distance == 0 else 5.0 if distance == 1 else 0.0
    return _round((60.0, BASE_CYCLE[station - 1] + extra))


def _line_recovery(situation: int, station: int) -> tuple[float, float]:
    extra = (11.0, 9.0, 7.2, 5.6, 4.1, 2.9, 1.9, 1.1, 0.5, 0.0)[situation]
    return _round((60.0, BASE_CYCLE[station - 1] + extra + (station % 3) * 0.2))


def _mixed(situation: int, station: int) -> tuple[float, float]:
    waves = (0.0, 1.5, -0.6, 4.0, 0.8, 7.5, -0.4, 3.0, 8.5, 0.2)
    local = ((station * 5 + situation * 3) % 7 - 3) * 0.45
    spike = 5.0 if (station + situation * 2) % 11 == 0 else 0.0
    return _round((60.0, BASE_CYCLE[station - 1] + waves[situation] + local + spike))


def _shift_start(situation: int, station: int) -> tuple[float, float]:
    extra = (13.0, 10.0, 7.8, 5.8, 4.2, 3.0, 1.9, 1.1, 0.5, 0.0)[situation]
    return _round((60.0, BASE_CYCLE[station - 1] + extra + (station % 4) * 0.15))


def _shift_fatigue(situation: int, station: int) -> tuple[float, float]:
    extra = max(0, situation - 1) * 0.9 + (station / 12) * situation * 0.12
    return _round((60.0, BASE_CYCLE[station - 1] + extra))


def _fixed_station_06(situation: int, station: int) -> tuple[float, float]:
    if station == 6:
        cycle = 68.0 + situation * 0.45
    elif station in (5, 7):
        cycle = BASE_CYCLE[station - 1] + 2.5
    else:
        cycle = BASE_CYCLE[station - 1] + ((situation % 3) - 1) * 0.2
    return _round((60.0, cycle))


def _migrating_bottleneck(situation: int, station: int) -> tuple[float, float]:
    target = (1, 2, 4, 5, 6, 8, 9, 10, 11, 12)[situation]
    extra = 14.0 if station == target else 4.0 if abs(station - target) == 1 else 0.0
    return _round((60.0, BASE_CYCLE[station - 1] + extra))


def _unbalanced(situation: int, station: int) -> tuple[float, float]:
    offsets = (-5.5, 5.8, -2.5, 7.0, -4.2, 3.6, -3.4, 6.2, -1.5, 4.8, -4.7, 7.5)
    drift = ((situation + station) % 4 - 1.5) * 0.25
    return _round((60.0, BASE_CYCLE[station - 1] + offsets[station - 1] + drift))


def _balanced(situation: int, station: int) -> tuple[float, float]:
    initial_offsets = (-6.0, 5.5, -4.0, 7.0, -3.0, 4.5, -5.0, 6.5, -2.0, 5.0, -4.5, 7.5)
    convergence = 1.0 - situation / 9
    target = 57.0 + ((station % 3) - 1) * 0.2
    cycle = target + initial_offsets[station - 1] * convergence
    return _round((60.0, cycle))


def _intermittent_spikes(situation: int, station: int) -> tuple[float, float]:
    spike_groups = {2: (2, 3, 4), 5: (6, 7, 8), 8: (10, 11, 12)}
    spike = 13.0 if station in spike_groups.get(situation, ()) else 0.0
    ripple = 2.0 if situation in (3, 6, 9) and station % 4 == 0 else 0.0
    return _round((60.0, BASE_CYCLE[station - 1] + spike + ripple))


def _equipment_degradation(situation: int, station: int) -> tuple[float, float]:
    affected = station in (4, 5, 6, 7)
    extra = situation * (1.25 + (station - 4) * 0.12) if affected else situation * 0.08
    return _round((60.0, BASE_CYCLE[station - 1] + extra))


def _after_maintenance(situation: int, station: int) -> tuple[float, float]:
    extra = (12.0, 11.0, 10.0, 9.0, 2.5, 1.8, 1.1, 0.6, 0.2, 0.0)[situation]
    affected_extra = extra if station in (4, 5, 6, 7) else extra * 0.25
    return _round((60.0, BASE_CYCLE[station - 1] + affected_extra))


def _product_change(situation: int, station: int) -> tuple[float, float]:
    if situation < 3:
        return _round((60.0, BASE_CYCLE[station - 1]))
    adaptation = (65.0, 61.5, 58.5, 56.0, 54.0, 52.5, 51.5)[situation - 3]
    station_offset = ((station % 4) - 1.5) * 0.35
    return _round((54.0, adaptation + station_offset))


def _demand_increase(situation: int, station: int) -> tuple[float, float]:
    takt = 64.0 - situation
    cycle = BASE_CYCLE[station - 1] + 2.0 - situation * 0.28 + (station % 3) * 0.15
    return _round((takt, cycle))


def _demand_reduction(situation: int, station: int) -> tuple[float, float]:
    takt = 55.0 + situation
    cycle = BASE_CYCLE[station - 1] + 1.0 - situation * 0.18
    return _round((takt, cycle))


_RANDOM_VALUES: dict[tuple[int, int], float] = {}
_random = random.Random(1800)
for _situation in SITUATIONS:
    for _station in STATIONS:
        _RANDOM_VALUES[(_situation, _station)] = _random.uniform(-1.8, 1.8)


def _controlled_random(situation: int, station: int) -> tuple[float, float]:
    takt = 60.0 + ((situation % 3) - 1) * 0.2
    cycle = BASE_CYCLE[station - 1] + _RANDOM_VALUES[(situation, station)]
    return _round((takt, cycle))


def _critical_station_12(situation: int, station: int) -> tuple[float, float]:
    critical = (58.0, 59.0, 61.0, 70.0, 85.0, 92.0, 78.0, 68.0, 61.0, 58.0)
    if station == 12:
        cycle = critical[situation]
    elif station in (10, 11) and 3 <= situation <= 7:
        cycle = BASE_CYCLE[station - 1] + (8 - abs(5 - situation))
    else:
        cycle = BASE_CYCLE[station - 1]
    return _round((60.0, cycle))


def _cascade(situation: int, station: int) -> tuple[float, float]:
    center = 1.0 + situation * 11 / 9
    distance = abs(station - center)
    extra = max(0.0, 13.0 - distance * 4.5)
    return _round((60.0, BASE_CYCLE[station - 1] + extra))


SCENARIOS = (
    Scenario("01_operacao_estavel.xlsx", "Operacao estavel", "Pequenas variacoes proximas do padrao.", _stable),
    Scenario("02_aumento_cycle_time.xlsx", "Aumento de cycle time", "Ciclos aumentando gradualmente.", _increasing_cycle),
    Scenario("03_gargalos_por_posto.xlsx", "Gargalos por posto", "Gargalos alternando entre postos.", _rotating_bottlenecks),
    Scenario("04_recuperacao_da_linha.xlsx", "Recuperacao da linha", "Comeca degradado e retorna ao normal.", _line_recovery),
    Scenario("05_cenario_misto.xlsx", "Cenario misto", "Variacoes fortes, picos e estabilizacao.", _mixed),
    Scenario("06_partida_de_turno.xlsx", "Partida de turno", "Ciclos altos no inicio e estabilizacao gradual.", _shift_start),
    Scenario("07_fadiga_no_turno.xlsx", "Fadiga no turno", "Desempenho normal que piora progressivamente.", _shift_fatigue),
    Scenario("08_gargalo_fixo_posto_06.xlsx", "Gargalo fixo no posto 06", "P06 permanece acima do Takt.", _fixed_station_06),
    Scenario("09_gargalo_migrando.xlsx", "Gargalo migrando", "O gargalo passa de posto em posto.", _migrating_bottleneck),
    Scenario("10_linha_desbalanceada.xlsx", "Linha desbalanceada", "Postos rapidos e lentos operando juntos.", _unbalanced),
    Scenario("11_linha_balanceada.xlsx", "Linha balanceada", "Ciclos convergem progressivamente para o Takt.", _balanced),
    Scenario("12_picos_intermitentes.xlsx", "Picos intermitentes", "Aumentos bruscos em momentos alternados.", _intermittent_spikes),
    Scenario("13_degradacao_de_equipamento.xlsx", "Degradacao de equipamento", "P04 a P07 pioram continuamente.", _equipment_degradation),
    Scenario("14_pos_manutencao.xlsx", "Pos-manutencao", "Melhora expressiva depois de uma manutencao.", _after_maintenance),
    Scenario("15_mudanca_de_produto.xlsx", "Mudanca de produto", "Novo Takt e adaptacao gradual dos ciclos.", _product_change),
    Scenario("16_aumento_de_demanda.xlsx", "Aumento de demanda", "Takt diminui e a linha tenta acompanhar.", _demand_increase),
    Scenario("17_reducao_de_demanda.xlsx", "Reducao de demanda", "Takt aumenta e cria folga operacional.", _demand_reduction),
    Scenario("18_variacao_aleatoria_controlada.xlsx", "Variacao aleatoria controlada", "Oscilacoes realistas e deterministicas.", _controlled_random),
    Scenario("19_evento_critico_posto_12.xlsx", "Evento critico no posto 12", "Pico extremo no P12 seguido de recuperacao.", _critical_station_12),
    Scenario("20_efeito_cascata.xlsx", "Efeito cascata", "Uma demora se propaga pela linha.", _cascade),
)


def build_workbook(scenario: Scenario) -> Workbook:
    workbook = Workbook()
    workbook.properties.title = scenario.title
    workbook.properties.subject = "Base de exemplo para o Mock da Linha"
    workbook.properties.description = scenario.description
    sheet = workbook.active
    sheet.title = "Base"
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 75
    sheet.freeze_panes = "B2"

    headers = ["Posto"]
    for situation in range(1, 11):
        headers.extend((f"Takt {situation:02d}", f"Ultimo ciclo {situation:02d}"))
    sheet.append(headers)

    for station in STATIONS:
        row: list[str | float] = [f"P{station:02d}"]
        for situation in SITUATIONS:
            row.extend(scenario.values(situation, station))
        sheet.append(row)

    dark_blue = "1F4E78"
    takt_blue = "2F75B5"
    cycle_green = "548235"
    pale_blue = "EAF2F8"
    pale_green = "EDF4E8"
    white = "FFFFFF"
    grid = Side(style="thin", color="B7C4CF")

    for cell in sheet[1]:
        is_takt = cell.column > 1 and cell.column % 2 == 0
        cell.fill = PatternFill("solid", fgColor=takt_blue if is_takt else cycle_green)
        if cell.column == 1:
            cell.fill = PatternFill("solid", fgColor=dark_blue)
        cell.font = Font(color=white, bold=True, size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=Side(style="medium", color=dark_blue))
    sheet.row_dimensions[1].height = 34

    for row in range(2, 14):
        station_cell = sheet.cell(row=row, column=1)
        station_cell.fill = PatternFill("solid", fgColor="D9EAF7")
        station_cell.font = Font(color=dark_blue, bold=True)
        station_cell.alignment = Alignment(horizontal="center", vertical="center")
        station_cell.border = Border(left=grid, right=grid, top=grid, bottom=grid)
        sheet.row_dimensions[row].height = 23
        for column in range(2, 22):
            cell = sheet.cell(row=row, column=column)
            cell.fill = PatternFill(
                "solid", fgColor=pale_blue if column % 2 == 0 else pale_green
            )
            cell.font = Font(color="1F2937")
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.number_format = '0.0 "s"'
            cell.border = Border(left=grid, right=grid, top=grid, bottom=grid)

    sheet.column_dimensions["A"].width = 11
    for column in range(2, 22):
        sheet.column_dimensions[get_column_letter(column)].width = 15

    red_fill = PatternFill("solid", fgColor="F4CCCC")
    red_font = Font(color="9C0006", bold=True)
    for cycle_column in range(3, 22, 2):
        cycle_letter = get_column_letter(cycle_column)
        takt_letter = get_column_letter(cycle_column - 1)
        sheet.conditional_formatting.add(
            f"{cycle_letter}2:{cycle_letter}13",
            CellIsRule(
                operator="greaterThan",
                formula=[f"{takt_letter}2"],
                fill=red_fill,
                font=red_font,
            ),
        )

    sheet.auto_filter.ref = "A1:U13"
    sheet.print_title_rows = "1:1"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    return workbook


def generate(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    for scenario in SCENARIOS:
        path = output_dir / scenario.filename
        build_workbook(scenario).save(path)
        generated.append(path)
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera as bases de exemplo do mock")
    parser.add_argument("output_dir", nargs="?", default="bases_exemplo")
    args = parser.parse_args()
    generated = generate(Path(args.output_dir))
    print(f"{len(generated)} bases geradas em {Path(args.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
