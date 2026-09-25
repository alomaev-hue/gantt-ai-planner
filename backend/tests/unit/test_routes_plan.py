from app.api.routes_plan import sanitize_filename


def test_sanitize_filename_strips_control_chars_and_collapses_whitespace():
    assert sanitize_filename("plan\n\t report .xlsx") == "plan report .xlsx"


def test_sanitize_filename_strips_guillemets():
    assert sanitize_filename("«план».xlsx") == "план.xlsx"


def test_sanitize_filename_caps_length():
    name = "a" * 200 + ".xlsx"
    result = sanitize_filename(name)
    assert len(result) == 100


def test_sanitize_filename_falls_back_when_empty():
    assert sanitize_filename(None) == "plan.xlsx"
    assert sanitize_filename("   ") == "plan.xlsx"
    assert sanitize_filename("\x00\x01") == "plan.xlsx"
