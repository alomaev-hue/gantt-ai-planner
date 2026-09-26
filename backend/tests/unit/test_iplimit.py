from app.services.iplimit import SlidingWindowLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limit_applies_per_key_within_the_window():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(window_seconds=3600, clock=clock)
    assert limiter.allow("1.1.1.1", 2) and limiter.allow("1.1.1.1", 2)
    assert not limiter.allow("1.1.1.1", 2)
    assert limiter.allow("2.2.2.2", 2)  # other clients are unaffected


def test_hits_expire_after_the_window():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(window_seconds=3600, clock=clock)
    assert limiter.allow("1.1.1.1", 1)
    clock.now += 3599
    assert not limiter.allow("1.1.1.1", 1)
    clock.now += 2
    assert limiter.allow("1.1.1.1", 1)


def test_rejected_attempts_do_not_extend_the_block():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(window_seconds=10, clock=clock)
    assert limiter.allow("k", 1)
    for _ in range(5):
        clock.now += 1
        assert not limiter.allow("k", 1)
    clock.now += 6
    assert limiter.allow("k", 1)


def test_idle_keys_are_swept():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(window_seconds=10, clock=clock, sweep_every=3)
    for i in range(3):
        limiter.allow(f"10.0.0.{i}", 5)
    clock.now += 11
    limiter.allow("10.0.0.99", 5)
    limiter.allow("10.0.0.99", 5)
    limiter.allow("10.0.0.99", 5)
    assert set(limiter._hits) == {"10.0.0.99"}
