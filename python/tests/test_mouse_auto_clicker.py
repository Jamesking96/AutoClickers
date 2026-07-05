import unittest

from pynput import mouse

from ..UI.auto_clicker_ui import normalize_hotkey
from ..mouse_auto_clicker import mouse_button_to_text


class NormalizeHotkeyTests(unittest.TestCase):
    def test_default_shortcut(self) -> None:
        self.assertEqual(normalize_hotkey("alt+f6"), "<alt>+<f6>")

    def test_single_letter(self) -> None:
        self.assertEqual(normalize_hotkey("ctrl+k"), "<ctrl>+k")

    def test_invalid_token(self) -> None:
        with self.assertRaises(ValueError):
            normalize_hotkey("alt+mouse1")

    def test_mouse_button_labels(self) -> None:
        self.assertEqual(mouse_button_to_text(mouse.Button.left), "Left")
        self.assertEqual(mouse_button_to_text(mouse.Button.right), "Right")


if __name__ == "__main__":
    unittest.main()

