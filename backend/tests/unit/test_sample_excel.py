from datetime import date
from pathlib import Path

from app.excel.parse import parse_plan_xlsx

SAMPLE = Path(__file__).resolve().parents[3] / "examples" / "sample-plan.xlsx"


def test_sample_excel_imports_cleanly():
    res = parse_plan_xlsx(SAMPLE.read_bytes(), date(2026, 10, 5))
    assert res.ok, res.errors
    assert len(res.plan.tasks) == 15
    assert any(d.lag > 0 for d in res.plan.dependencies)
    assert res.warnings == []
