"""Workday arithmetic: Monday-Friday are workdays, no holidays."""

from datetime import date, timedelta

_ONE_DAY = timedelta(days=1)


def is_workday(d: date) -> bool:
    return d.weekday() < 5


def next_workday(d: date) -> date:
    """Return d if it is a workday, otherwise the following Monday."""
    while not is_workday(d):
        d += _ONE_DAY
    return d


def prev_workday(d: date) -> date:
    """Return d if it is a workday, otherwise the preceding Friday."""
    while not is_workday(d):
        d -= _ONE_DAY
    return d


def add_workdays(d: date, n: int) -> date:
    """Move n workdays from d (backwards when n < 0). Weekend d is normalized first."""
    d = next_workday(d) if n >= 0 else prev_workday(d)
    step = _ONE_DAY if n >= 0 else -_ONE_DAY
    weeks, remaining = divmod(abs(n), 5)
    d += step * 7 * weeks
    while remaining:
        d += step
        if is_workday(d):
            remaining -= 1
    return d


def workday_diff(a: date, b: date) -> int:
    """Signed number of workdays needed to move from workday a to workday b."""
    if a == b:
        return 0
    sign = 1 if b > a else -1
    lo, hi = (a, b) if sign > 0 else (b, a)
    weeks, _ = divmod((hi - lo).days, 7)
    count = weeks * 5
    d = lo + timedelta(days=7 * weeks)
    while d < hi:
        d += _ONE_DAY
        if is_workday(d):
            count += 1
    return sign * count
