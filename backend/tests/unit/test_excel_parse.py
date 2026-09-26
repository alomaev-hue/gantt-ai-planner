import zipfile
from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.excel.parse import parse_duration, parse_plan_xlsx

MON = date(2026, 9, 21)


def xlsx(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEADER = ["Задача", "Описание", "Исполнитель", "Длительность", "Предшественники"]


@pytest.mark.parametrize(
    ("raw", "expected", "warns"),
    [
        (5, 5, False),
        (5.0, 5, False),
        ("5", 5, False),
        ("5д", 5, False),
        ("5 д.", 5, False),
        ("5 дн", 5, False),
        ("5 дней", 5, False),
        ("5d", 5, False),
        ("1 нед", 5, False),
        ("2w", 10, False),
        ("2,5", 3, True),
        (None, 1, True),
        (0, 1, True),
        ("", 1, True),
    ],
)
def test_parse_duration(raw, expected, warns):
    value, warning = parse_duration(raw)
    assert value == expected
    assert (warning is not None) == warns


def test_parse_duration_invalid():
    with pytest.raises(ValueError):
        parse_duration("долго")


def test_basic_import_by_row_order_and_names():
    data = xlsx(
        [
            HEADER,
            ["Анализ", "Сбор требований", "Анна", 3, None],
            ["Дизайн", "", "Мария", "5д", "1"],
            ["Разработка", None, "Игорь", "2 нед", "1; Дизайн+2"],
        ]
    )
    res = parse_plan_xlsx(data, MON)
    assert res.ok, res.errors
    plan = res.plan
    assert [t.id for t in plan.tasks] == [1, 2, 3]
    assert plan.tasks[2].duration == 10
    assert {(d.predecessor_id, d.successor_id, d.lag) for d in plan.dependencies} == {
        (1, 2, 0),
        (1, 3, 0),
        (2, 3, 2),
    }
    assert plan.project_start == MON


def test_header_not_on_first_row_blank_rows_and_long_text():
    data = xlsx(
        [
            ["План переезда офиса"],
            [],
            ["№", "Название", "Ответственный", "Дни", "Зависимости"],
            [10, "Упаковка", "Олег", 2, None],
            [None, None, None, None, None],
            [20, "Х" * 250, None, 1, 10.0],
            [],
        ]
    )
    res = parse_plan_xlsx(data, MON)
    assert res.ok, res.errors
    assert [t.id for t in res.plan.tasks] == [10, 20]
    assert len(res.plan.tasks[1].name) == 200
    assert any("обрезано" in w.message for w in res.warnings)
    assert res.plan.dependencies[0].predecessor_id == 10


@pytest.mark.parametrize("cell", [3.0, "3.0", "3FS+2", "3 + 2д"])
def test_numeric_predecessor_variants(cell):
    rows = (
        [HEADER] + [[f"T{i}", "", None, 1, None] for i in range(1, 4)] + [["T4", "", None, 1, cell]]
    )
    res = parse_plan_xlsx(xlsx(rows), MON)
    assert res.ok, res.errors
    dep = res.plan.dependencies[0]
    assert (dep.predecessor_id, dep.successor_id) == (3, 4)
    assert dep.lag == (2 if "+" in str(cell) else 0)


def test_constraint_column_and_weekend_project_start():
    data = xlsx(
        [
            [*HEADER, "Не раньше"],
            ["A", "", None, 1, None, datetime(2026, 10, 5)],
            ["B", "", None, 1, None, "06.10.2026"],
        ]
    )
    res = parse_plan_xlsx(data, date(2026, 9, 27))  # Sunday
    assert res.ok, res.errors
    assert res.plan.project_start == date(2026, 9, 28)
    assert [t.constraint_start for t in res.plan.tasks] == [date(2026, 10, 5), date(2026, 10, 6)]


def test_errors_are_collected_with_rows():
    data = xlsx(
        [
            HEADER,
            ["A", "", None, 1, "5"],  # row 2: unknown ref
            ["", "", None, 1, None],  # row 3: empty name but other cells -> error
            ["C", "", None, "долго", None],  # row 4: bad duration
            ["D", "", None, 1, "D"],  # row 5: self reference
        ]
    )
    res = parse_plan_xlsx(data, MON)
    assert not res.ok and res.plan is None
    rows = {e.row for e in res.errors}
    assert {2, 3, 4, 5} <= rows


def test_ambiguous_name_and_cycle():
    ambiguous = xlsx(
        [HEADER, ["A", "", None, 1, None], ["A", "", None, 1, None], ["B", "", None, 1, "A"]]
    )
    res = parse_plan_xlsx(ambiguous, MON)
    assert not res.ok and any("укажите №" in e.message for e in res.errors)

    cycle = xlsx([HEADER, ["A", "", None, 1, "2"], ["B", "", None, 1, "1"]])
    res = parse_plan_xlsx(cycle, MON)
    assert not res.ok and any("Циклическая зависимость" in e.message for e in res.errors)


def test_missing_required_columns_and_empty_file():
    res = parse_plan_xlsx(xlsx([["Описание", "Исполнитель"], ["x", "y"]]), MON)
    assert not res.ok and "задача" in res.errors[0].message.lower()
    res = parse_plan_xlsx(xlsx([HEADER]), MON)
    assert not res.ok and "нет задач" in res.errors[0].message


def test_not_an_xlsx():
    res = parse_plan_xlsx(b"not a zip", MON)
    assert not res.ok and "xlsx" in res.errors[0].message


def test_duplicate_numbers_and_too_many_tasks():
    dup = xlsx([["№", *HEADER], [1, "A", "", None, 1, None], [1, "B", "", None, 1, None]])
    assert any("повторяется" in e.message for e in parse_plan_xlsx(dup, MON).errors)
    many = xlsx([HEADER] + [[f"T{i}", "", None, 1, None] for i in range(501)])
    assert any("500" in e.message for e in parse_plan_xlsx(many, MON).errors)


def test_excessive_lag_is_reported_not_a_crash():
    data = xlsx([HEADER, ["A", "", None, 1, None], ["B", "", None, 1, "1+9999"]])
    res = parse_plan_xlsx(data, MON)
    assert not res.ok and res.plan is None
    errs = [e for e in res.errors if e.row == 3]
    assert errs and "365" in errs[0].message


def test_too_many_tasks_keeps_previously_collected_errors():
    rows = [HEADER, ["", "", None, 1, None]] + [[f"T{i}", "", None, 1, None] for i in range(501)]
    res = parse_plan_xlsx(xlsx(rows), MON)
    assert not res.ok
    assert any("500" in e.message for e in res.errors)
    assert any(e.row == 2 for e in res.errors)


def test_zip_bomb_is_rejected_before_inflating(monkeypatch):
    """A member that declares a huge uncompressed size but compresses to almost
    nothing (e.g. megabytes of repeated zero bytes) must be rejected from the zip
    central directory alone — never decompressed, never handed to openpyxl.
    """
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"0" * (25 * 1024 * 1024))

    # Guard against a regression that would defeat the point of this test: if the
    # fix ever starts reading a member's actual (decompressed) bytes to decide
    # whether to reject it, fail loudly instead of silently inflating 25 MB.
    monkeypatch.setattr(
        zipfile.ZipExtFile, "read", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    res = parse_plan_xlsx(buf.getvalue(), MON)
    assert not res.ok
    assert "большой" in res.errors[0].message


def test_zip_with_too_many_entries_is_rejected():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(1001):
            zf.writestr(f"member{i}.xml", "x")
    res = parse_plan_xlsx(buf.getvalue(), MON)
    assert not res.ok
    assert "большой" in res.errors[0].message


def test_sheet_with_too_many_non_empty_rows_is_rejected():
    rows = [HEADER] + [[f"T{i}", "", None, 1, None] for i in range(600)]
    res = parse_plan_xlsx(xlsx(rows), MON)
    assert not res.ok
    assert any("лимит строк" in e.message for e in res.errors)


def test_sheet_with_too_many_total_rows_is_rejected_even_when_mostly_blank():
    """A "sparse" row bomb: almost all rows are blank (so the non-empty-row budget
    is never hit), but the sheer number of rows scanned must still be capped —
    otherwise a sheet declaring millions of rows could force a very long, mostly
    wasted scan even though it contains only a couple of real tasks.
    """
    rows = [HEADER, ["A", "", None, 1, None]] + [[None] * 5 for _ in range(5100)]
    res = parse_plan_xlsx(xlsx(rows), MON)
    assert not res.ok
    assert any("лимит строк" in e.message for e in res.errors)
