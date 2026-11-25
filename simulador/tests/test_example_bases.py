from openpyxl import load_workbook

from services.base_import import load_metric_snapshots
from tools.generate_example_bases import SCENARIOS, generate


def test_generates_twenty_importable_example_bases(tmp_path) -> None:
    generated = generate(tmp_path)

    assert len(generated) == len(SCENARIOS) == 20
    assert len({path.name for path in generated}) == 20
    for path in generated:
        snapshots = load_metric_snapshots(path)
        assert len(snapshots) == 10
        assert all(set(snapshot.values) == set(range(1, 13)) for snapshot in snapshots)

        workbook = load_workbook(path, read_only=False, data_only=True)
        sheet = workbook.active
        assert sheet.max_row == 13
        assert sheet.max_column == 21
        assert sheet.freeze_panes == "B2"
        workbook.close()
