import pytest

from scripts.tadas_kendo_adapter import (
    CSV_BUTTON_SELECTOR,
    DATE_INPUT_SELECTOR,
    EVENT_ID_SELECTOR,
    assert_preserved_value,
    clipboard_commit_kendo_date,
)


def test_current_tadas_dom_contract_selectors_are_specific():
    assert EVENT_ID_SELECTOR == "input[name='txtEaEventId']:visible"
    assert DATE_INPUT_SELECTOR == "input.k-input:not(.k-formatted-value):visible"
    assert "k-i-file-csv" in CSV_BUTTON_SELECTOR


def test_preserved_value_guard_accepts_exact_trimmed_value():
    assert_preserved_value("start_date", " 18-03-2024 00:00:00 ", "18-03-2024 00:00:00")


def test_preserved_value_guard_rejects_kendo_date_reset():
    with pytest.raises(RuntimeError, match="did not preserve start_date"):
        assert_preserved_value(
            "start_date",
            "17-08-2026 18:07:36",
            "18-03-2024 00:00:00",
        )


class FakePage:
    def __init__(self):
        self.calls = []

    def evaluate(self, expression, value):
        self.calls.append(("evaluate", expression, value))


class FakeLocator:
    def __init__(self):
        self.calls = []

    def click(self):
        self.calls.append(("click",))

    def press(self, key):
        self.calls.append(("press", key))


def test_kendo_date_commit_uses_full_value_clipboard_paste():
    page = FakePage()
    locator = FakeLocator()
    value = "18-03-2024 00:00:00"
    clipboard_commit_kendo_date(page, locator, value)
    assert page.calls == [
        ("evaluate", "text => navigator.clipboard.writeText(text)", value),
    ]
    assert locator.calls == [
        ("click",),
        ("press", "Control+A"),
        ("press", "Control+V"),
        ("press", "Tab"),
    ]
