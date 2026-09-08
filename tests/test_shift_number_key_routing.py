from jaw.main import MainWindow


class _FakeEvent:
    def __init__(self, text: str, native_vk: int = 0):
        self._text = text
        self._native_vk = native_vk

    def text(self) -> str:
        return self._text

    def nativeVirtualKey(self) -> int:
        return self._native_vk


def test_shift_number_uses_underlying_number_key():
    assert MainWindow._matrix_key_from_event(_FakeEvent("!", ord("1"))) == "1"
    assert MainWindow._matrix_key_from_event(_FakeEvent("@", ord("2"))) == "2"
    assert MainWindow._matrix_key_from_event(_FakeEvent("#", ord("3"))) == "3"


def test_plain_alphanumeric_text_is_preserved():
    assert MainWindow._matrix_key_from_event(_FakeEvent("a", ord("A"))) == "A"
    assert MainWindow._matrix_key_from_event(_FakeEvent("4", ord("4"))) == "4"


def test_non_matrix_punctuation_without_alphanumeric_vk_is_ignored():
    assert MainWindow._matrix_key_from_event(_FakeEvent("!", 0)) == ""
