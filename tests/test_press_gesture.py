from jaw.desktop.press_gesture import LongPressGesture


def test_short_press_fires_only_when_released() -> None:
    gesture = LongPressGesture(700)

    assert gesture.begin("g", 10.0) is True
    assert gesture.poll(True, 10.4) is None
    assert gesture.poll(False, 10.4) == "short"
    assert gesture.active is False


def test_long_press_fires_once_and_suppresses_short_release() -> None:
    gesture = LongPressGesture(700)

    gesture.begin("G", 10.0)
    assert gesture.poll(True, 10.699) is None
    assert gesture.poll(True, 10.7) == "long"
    assert gesture.poll(True, 11.0) is None
    assert gesture.poll(False, 11.1) is None
    assert gesture.active is False


def test_repeated_key_events_do_not_restart_active_press() -> None:
    gesture = LongPressGesture(700)

    assert gesture.begin("G", 2.0) is True
    assert gesture.begin("G", 2.4) is False
    assert gesture.poll(True, 2.7) == "long"
