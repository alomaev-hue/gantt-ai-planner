import uuid

from app.services.events import EventBus


def test_forget_unknown_session_is_noop():
    bus = EventBus()
    bus.forget(uuid.uuid4())  # must not raise


def test_forget_drops_subscriber_set():
    bus = EventBus()
    sid = uuid.uuid4()
    queue = bus.subscribe(sid)
    assert sid in bus._subs

    bus.forget(sid)

    assert sid not in bus._subs
    # publishing after forget must not resurrect the entry or error out
    bus.publish(sid, {"type": "plan_changed"})
    assert queue.empty()
