import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from pynput import keyboard

import sys
import os

# Handle imports for both development and PyInstaller bundled exe
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Running as bundled exe from PyInstaller
    base_path = sys._MEIPASS
else:
    # Running as normal Python script
    base_path = os.path.dirname(os.path.abspath(__file__))

if base_path not in sys.path:
    sys.path.insert(0, base_path)

from UI.auto_clicker_ui import AutoClickerUIBase, normalize_hotkey


def pynput_key_to_token(key: keyboard.Key | keyboard.KeyCode) -> str | None:
    if isinstance(key, keyboard.KeyCode):
        if key.char is None:
            return None
        value = key.char.lower()
        if value == " ":
            return "space"
        if len(value) == 1 and value.isalnum():
            return value
        return None

    key_map = {
        keyboard.Key.space: "space",
        keyboard.Key.tab: "tab",
        keyboard.Key.enter: "enter",
        keyboard.Key.shift: "shift",
        keyboard.Key.shift_l: "shift",
        keyboard.Key.shift_r: "shift",
        keyboard.Key.ctrl: "ctrl",
        keyboard.Key.ctrl_l: "ctrl",
        keyboard.Key.ctrl_r: "ctrl",
        keyboard.Key.alt: "alt",
        keyboard.Key.alt_l: "alt",
        keyboard.Key.alt_r: "alt",
    }
    if key in key_map:
        return key_map[key]

    key_name = getattr(key, "name", "")
    if key_name.startswith("f") and key_name[1:].isdigit():
        return key_name

    return None


def token_to_press_key(token: str) -> keyboard.Key | str:
    token_map = {
        "space": keyboard.Key.space,
        "tab": keyboard.Key.tab,
        "enter": keyboard.Key.enter,
        "shift": keyboard.Key.shift,
        "ctrl": keyboard.Key.ctrl,
        "alt": keyboard.Key.alt,
    }

    if token in token_map:
        return token_map[token]

    if token.startswith("f") and token[1:].isdigit():
        function_key = getattr(keyboard.Key, token, None)
        if function_key is not None:
            return function_key

    if len(token) == 1 and token.isalnum():
        return token

    raise ValueError(f"Unsupported key token: {token}")


class KeyboardAutoClickerApp(AutoClickerUIBase):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, "Keyboard Auto Presser", "450x360")

        self.keyboard_controller = keyboard.Controller()
        self.hotkey_listener: keyboard.GlobalHotKeys | None = None
        self.selection_key_listener: keyboard.Listener | None = None

        self.interval_ms_var = tk.StringVar(value="100")
        self.key_text_var = tk.StringVar(value="Not set")
        self.selection_text_var = tk.StringVar(value="Press the button below to choose a key to auto press.")

        self.target_key_token: str | None = None
        self.pending_selection_token: str | None = None
        self.press_thread = None
        self.pressing_active = threading.Event()
        self.shutdown_event = threading.Event()
        self.key_selection_active = threading.Event()
        self.selection_confirmation_pending = threading.Event()
        self.state_lock = threading.Lock()

        self._build_ui()
        self.apply_hotkey()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        outer = self.build_root_container(padding=12)

        self.build_theme_controls(outer)

        ttk.Label(outer, text="Press interval (milliseconds):", style="XP.TLabel").pack(anchor="w")
        ttk.Entry(outer, textvariable=self.interval_ms_var, style="XP.TEntry").pack(fill="x", pady=(0, 10))

        ttk.Label(outer, text="Target key:", style="XP.TLabel").pack(anchor="w")
        key_row = ttk.Frame(outer, style="XP.TFrame")
        key_row.pack(fill="x", pady=(0, 4))
        ttk.Label(key_row, textvariable=self.key_text_var, style="XP.TLabel").pack(side="left")

        key_button_row = ttk.Frame(outer, style="XP.TFrame")
        key_button_row.pack(fill="x", pady=(0, 6))
        self.set_key_button = ttk.Button(
            key_button_row,
            text="Set key",
            command=self.start_key_selection,
            style="XP.TButton",
        )
        self.set_key_button.pack(side="left", fill="x", expand=True)
        self.clear_key_button = ttk.Button(
            key_button_row,
            text="Clear",
            command=self.clear_key,
            style="XP.TButton",
        )
        self.clear_key_button.pack(side="left", padx=(8, 0))
        ttk.Label(
            outer,
            textvariable=self.selection_text_var,
            wraplength=410,
            style="Hint.XP.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        ttk.Separator(outer, style="XP.TSeparator").pack(fill="x", pady=8)

        self.build_hotkey_controls(outer, self.apply_hotkey, self.revert_default_hotkey)

        button_row = ttk.Frame(outer, style="XP.TFrame")
        button_row.pack(fill="x", pady=(6, 6))
        ttk.Button(button_row, text="Start", command=self.start_pressing, style="XP.TButton").pack(side="left", fill="x", expand=True)
        ttk.Button(button_row, text="Stop", command=self.stop_pressing, style="XP.TButton").pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.build_status_section(outer)

    def start_key_selection(self) -> None:
        if self.pressing_active.is_set():
            messagebox.showwarning("Stop pressing first", "Stop the auto presser before choosing a key.")
            return

        if self.key_selection_active.is_set():
            self.selection_text_var.set("Selection already active: press a key to set it, or press Esc to cancel.")
            self.bring_window_to_front()
            return

        self.key_selection_active.set()
        self.selection_confirmation_pending.clear()
        self.pending_selection_token = None
        self.set_key_button.state(["disabled"])
        self.selection_text_var.set("Selection active: press a key to set it, or press Esc to cancel.")
        self.bring_window_to_front()
        self._start_selection_listener()

    def _start_selection_listener(self) -> None:
        self.selection_key_listener = keyboard.Listener(on_press=self._on_selection_key_press)
        self.selection_key_listener.start()

    def _stop_selection_listener(self) -> None:
        if self.selection_key_listener is not None:
            self.selection_key_listener.stop()
            self.selection_key_listener = None

        self.selection_confirmation_pending.clear()
        self.pending_selection_token = None

    def _finish_key_selection(self, message: str) -> None:
        self.key_selection_active.clear()
        self._stop_selection_listener()
        self.set_key_button.state(["!disabled"])
        self.selection_text_var.set(message)
        self.bring_window_to_front()

    def cancel_key_selection(self) -> None:
        if not self.key_selection_active.is_set():
            return
        self._finish_key_selection("Key selection cancelled.")

    def clear_key(self) -> None:
        if self.pressing_active.is_set():
            messagebox.showwarning("Stop pressing first", "Stop the auto presser before clearing the key.")
            return
        with self.state_lock:
            self.target_key_token = None
        self.key_text_var.set("Not set")
        self.selection_text_var.set("Press the button below to choose a key to auto press.")

    def _on_selection_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if not self.key_selection_active.is_set() or self.selection_confirmation_pending.is_set():
            return

        if key == keyboard.Key.esc:
            self.schedule_ui(0, self.cancel_key_selection)
            return

        token = pynput_key_to_token(key)
        if token is None:
            return

        self.pending_selection_token = token
        self.selection_confirmation_pending.set()
        self.schedule_ui(0, self._confirm_selected_key)

    def _confirm_selected_key(self) -> None:
        if not self.key_selection_active.is_set():
            self.selection_confirmation_pending.clear()
            return

        if self.pending_selection_token is None:
            self.selection_confirmation_pending.clear()
            return

        token = self.pending_selection_token
        confirmed = messagebox.askyesno(
            "Confirm Key",
            f"Use this key for auto pressing?\n\nKey: {token.upper()}",
            parent=self.root,
        )
        if confirmed:
            with self.state_lock:
                self.target_key_token = token
            self.key_text_var.set(token.upper())
            self._finish_key_selection("Key confirmed and saved.")
            return

        self.pending_selection_token = None
        self.selection_confirmation_pending.clear()
        self.selection_text_var.set("Selection active: press another key to set it, or press Esc to cancel.")
        self.bring_window_to_front()

    def get_interval_seconds(self) -> float:
        raw = self.interval_ms_var.get().strip()
        if not raw:
            raise ValueError("Interval is required")

        interval_ms = float(raw)
        if interval_ms <= 0:
            raise ValueError("Interval must be greater than 0")

        return interval_ms / 1000.0

    def _show_invalid_setting_error(self) -> None:
        messagebox.showerror(
            "Invalid setting",
            "Please enter a valid interval and selected key.",
        )


    def start_pressing(self) -> None:
        with self.state_lock:
            token = self.target_key_token

        if token is None:
            messagebox.showwarning("Key required", "Please set a key before starting auto press.")
            return

        try:
            self.get_interval_seconds()
            token_to_press_key(token)
        except ValueError as exc:
            messagebox.showerror("Invalid setting", str(exc))
            return

        if self.pressing_active.is_set():
            return

        self.pressing_active.set()
        self.set_status(True)
        self.press_thread = threading.Thread(target=self._press_loop, daemon=True)
        self.press_thread.start()

    def stop_pressing(self) -> None:
        if not self.pressing_active.is_set():
            return

        self.pressing_active.clear()
        self.set_status(False)

    def toggle_pressing(self) -> None:
        if self.pressing_active.is_set():
            self.stop_pressing()
        else:
            self.start_pressing()

    def _press_loop(self) -> None:
        while self.pressing_active.is_set() and not self.shutdown_event.is_set():
            with self.state_lock:
                token = self.target_key_token

            if token is None:
                self.schedule_ui(0, self.stop_pressing)
                break

            try:
                interval = self.get_interval_seconds()
                press_key = token_to_press_key(token)
            except ValueError:
                self.schedule_ui(0, self.stop_pressing)
                self.schedule_ui(0, self._show_invalid_setting_error)
                break

            self.keyboard_controller.press(press_key)
            self.keyboard_controller.release(press_key)
            time.sleep(interval)

    def _on_hotkey_trigger(self) -> None:
        self.schedule_ui(0, self.toggle_pressing)

    def apply_hotkey(self) -> None:
        value = self.hotkey_text_var.get().strip()
        try:
            pynput_hotkey = normalize_hotkey(value)
        except ValueError as exc:
            messagebox.showerror("Invalid hotkey", str(exc))
            return

        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()
            self.hotkey_listener = None

        self.hotkey_listener = keyboard.GlobalHotKeys({pynput_hotkey: self._on_hotkey_trigger})
        self.hotkey_listener.start()

    def revert_default_hotkey(self) -> None:
        self.hotkey_text_var.set("alt+f6")
        self.apply_hotkey()

    def on_close(self) -> None:
        self.shutdown_event.set()
        self.stop_pressing()
        self.cancel_key_selection()

        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()
            self.hotkey_listener = None

        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = KeyboardAutoClickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

