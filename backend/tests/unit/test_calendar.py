from datetime import date

from app.domain.calendar import add_workdays, is_workday, next_workday, prev_workday, workday_diff

MON = date(2026, 9, 21)
FRI = date(2026, 9, 25)
SAT = date(2026, 9, 26)
SUN = date(2026, 9, 27)
NEXT_MON = date(2026, 9, 28)


def test_is_workday():
    assert is_workday(MON) and is_workday(FRI)
    assert not is_workday(SAT) and not is_workday(SUN)


def test_next_and_prev_workday():
    assert next_workday(MON) == MON
    assert next_workday(SAT) == NEXT_MON
    assert next_workday(SUN) == NEXT_MON
    assert prev_workday(SAT) == FRI
    assert prev_workday(FRI) == FRI


def test_add_workdays_forward():
    assert add_workdays(MON, 0) == MON
    assert add_workdays(MON, 4) == FRI
    assert add_workdays(FRI, 1) == NEXT_MON
    assert add_workdays(MON, 5) == NEXT_MON
    assert add_workdays(MON, 10) == date(2026, 10, 5)
    assert add_workdays(SAT, 0) == NEXT_MON  # weekend normalizes forward


def test_add_workdays_backward():
    assert add_workdays(NEXT_MON, -1) == FRI
    assert add_workdays(NEXT_MON, -5) == MON
    assert add_workdays(FRI, -4) == MON


def test_workday_diff_is_inverse_of_add():
    start = MON
    for n in range(-15, 16):
        target = add_workdays(start, n)
        assert workday_diff(start, target) == n
    assert workday_diff(FRI, NEXT_MON) == 1
    assert workday_diff(NEXT_MON, FRI) == -1
