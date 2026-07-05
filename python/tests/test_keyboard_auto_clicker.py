import unittest

from pynput import keyboard

from ..UI.auto_clicker_ui import (
    keysym_to_hotkey_token,
    normalize_hotkey,
)
from ..keyboard_auto_clicker import (
    pynput_key_to_token,
    token_to_press_key,
)


class KeyboardAutoClickerHelpersTests(unittest.TestCase):
    def test_normalize_hotkey_default(self) -> None:
        self.assertEqual(normalize_hotkey("alt+f6"), "<alt>+<f6>")

    def test_keysym_to_hotkey_token(self) -> None:
        self.assertEqual(keysym_to_hotkey_token("Control_L"), "ctrl")
        self.assertEqual(keysym_to_hotkey_token("F8"), "f8")

    def test_pynput_key_to_token(self) -> None:
        self.assertEqual(pynput_key_to_token(keyboard.Key.space), "space")
        self.assertEqual(pynput_key_to_token(keyboard.KeyCode.from_char("a")), "a")
        self.assertIsNone(pynput_key_to_token(keyboard.Key.esc))

    def test_token_to_press_key(self) -> None:
        self.assertEqual(token_to_press_key("space"), keyboard.Key.space)
        self.assertEqual(token_to_press_key("a"), "a")


if __name__ == "__main__":
    unittest.main()

