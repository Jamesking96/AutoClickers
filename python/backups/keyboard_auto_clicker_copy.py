import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from pynput import keyboard


DEFAULT_HOTKEY = "alt+f6"
XP_BG = "#ece9d8"
XP_BUTTON_BG = "#f1efe2"
XP_BORDER = "#7f9db9"
XP_TEXT = "#000000"
XP_HINT = "#4a4a4a"
XP_ACCENT = "#0a246a"


def normalize_hotkey(value: str) -> str:
    """Convert user-friendly hotkeys like 'alt+f6' into pynput GlobalHotKeys syntax."""
    token_map = {
        "alt": "<alt>",
        "ctrl": "<ctrl>",
        "control": "<ctrl>",
        "shift": "<shift>",
        "win": "<cmd>",
        "windows": "<cmd>",
        "cmd": "<cmd>",
        "space": "<space>",
        "tab": "<tab>",
        "enter": "<enter>",
        "esc": "<esc>",
        "escape": "<esc>",
    }

    parts = []
    for raw_token in value.lower().split("+"):
        token = raw_token.strip()
        if not token:
            continue

        if token in token_map:
            parts.append(token_map[token])
            continue

        if token.startswith("f") and token[1:].isdigit():
            parts.append(f"<{token}>")
            continue

        if len(token) == 1 and token.isalnum():
            parts.append(token)
            continue

        raise ValueError(f"Unsupported hotkey token: '{raw_token}'")

    if not parts:
        raise ValueError("Hotkey cannot be empty")

    return "+".join(parts)


def keysym_to_hotkey_token(keysym: str) -> str | None:
    normalized = keysym.strip().lower()
    alias_map = {
        "alt_l": "alt",
        "alt_r": "alt",
        "alt": "alt",
        "control_l": "ctrl",
        "control_r": "ctrl",
        "control": "ctrl",
        "shift_l": "shift",
        "shift_r": "shift",
        "shift": "shift",
        "win_l": "win",
        "win_r": "win",
        "super_l": "win",
        "super_r": "win",
        "space": "space",
        "tab": "tab",
        "return": "enter",
        "kp_enter": "enter",
        "escape": "esc",
    }

    if normalized in alias_map:
        return alias_map[normalized]

    if normalized.startswith("f") and normalized[1:].isdigit():
        return normalized

    if len(normalized) == 1 and normalized.isalnum():
        return normalized

    return None


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


class KeyboardAutoClickerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Keyboard Auto Presser")
        self.root.geometry("450x360")
        self.root.configure(background=XP_BG)

        self.keyboard_controller = keyboard.Controller()
        self.hotkey_listener: keyboard.GlobalHotKeys | None = None
        self.selection_key_listener: keyboard.Listener | None = None

        self.hotkey_text_var = tk.StringVar(value=DEFAULT_HOTKEY)
        self.interval_ms_var = tk.StringVar(value="100")
        self.key_text_var = tk.StringVar(value="Not set")
        self.status_text_var = tk.StringVar(value="Status: OFF")
        self.selection_text_var = tk.StringVar(value="Press the button below to choose a key to auto press.")

        self.target_key_token: str | None = None
        self.pending_selection_token: str | None = None
        self.press_thread = None
        self.pressing_active = threading.Event()
        self.shutdown_event = threading.Event()
        self.key_selection_active = threading.Event()
        self.selection_confirmation_pending = threading.Event()
        self.state_lock = threading.Lock()
        self.hotkey_capture_active = False
        self.hotkey_capture_tokens: list[str] = []
        self.hotkey_pressed_tokens: set[str] = set()

        self._configure_xp_theme()
        self._build_ui()
        self.apply_hotkey()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def bring_window_to_front(self) -> None:
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()
        self.root.after(50, self._clear_topmost)

    def _clear_topmost(self) -> None:
        self.root.attributes("-topmost", False)

    def _configure_xp_theme(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(".", font=("Tahoma", 9))
        style.configure("XP.TFrame", background=XP_BG)
        style.configure("XP.TLabel", background=XP_BG, foreground=XP_TEXT)
        style.configure("Hint.XP.TLabel", background=XP_BG, foreground=XP_HINT)
        style.configure("Status.XP.TLabel", background=XP_BG, foreground=XP_ACCENT, font=("Tahoma", 9, "bold"))
        style.configure(
            "XP.TButton",
            background=XP_BUTTON_BG,
            foreground=XP_TEXT,
            bordercolor=XP_BORDER,
            lightcolor="#ffffff",
            darkcolor=XP_BORDER,
            focusthickness=1,
            focuscolor=XP_ACCENT,
            padding=(8, 3),
        )
        style.map(
            "XP.TButton",
            background=[("pressed", "#dcd8c3"), ("active", "#faf8ed")],
            bordercolor=[("pressed", XP_ACCENT), ("active", XP_ACCENT)],
        )
        style.configure(
            "XP.TEntry",
            fieldbackground="#ffffff",
            foreground=XP_TEXT,
            bordercolor=XP_BORDER,
            lightcolor="#ffffff",
            darkcolor=XP_BORDER,
            insertcolor=XP_TEXT,
        )
        style.map("XP.TEntry", bordercolor=[("focus", XP_ACCENT)])
        style.configure("XP.TSeparator", background=XP_BORDER)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="XP.TFrame", padding=12)
        outer.pack(fill="both", expand=True)

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

        ttk.Label(outer, text="Toggle hotkey (default Alt+F6):", style="XP.TLabel").pack(anchor="w")
        hotkey_row = ttk.Frame(outer, style="XP.TFrame")
        hotkey_row.pack(fill="x", pady=(0, 8))
        self.hotkey_entry = ttk.Entry(hotkey_row, textvariable=self.hotkey_text_var, style="XP.TEntry")
        self.hotkey_entry.pack(side="left", fill="x", expand=True)
        self.hotkey_entry.bind("<FocusIn>", self._begin_hotkey_capture)
        self.hotkey_entry.bind("<FocusOut>", self._end_hotkey_capture)
        self.hotkey_entry.bind("<KeyPress>", self._on_hotkey_entry_key_press)
        self.hotkey_entry.bind("<KeyRelease>", self._on_hotkey_entry_key_release)
        ttk.Button(hotkey_row, text="Apply", command=self.apply_hotkey, style="XP.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(hotkey_row, text="Revert Default", command=self.revert_default_hotkey, style="XP.TButton").pack(
            side="left", padx=(8, 0)
        )

        button_row = ttk.Frame(outer, style="XP.TFrame")
        button_row.pack(fill="x", pady=(6, 6))
        ttk.Button(button_row, text="Start", command=self.start_pressing, style="XP.TButton").pack(side="left", fill="x", expand=True)
        ttk.Button(button_row, text="Stop", command=self.stop_pressing, style="XP.TButton").pack(side="left", fill="x", expand=True, padx=(8, 0))

        ttk.Label(outer, textvariable=self.status_text_var, style="Status.XP.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Label(
            outer,
            text="Tip: Use the hotkey anytime to toggle ON/OFF.",
            style="Hint.XP.TLabel",
        ).pack(anchor="w", pady=(6, 0))

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
            self.root.after(0, self.cancel_key_selection)
            return

        token = pynput_key_to_token(key)
        if token is None:
            return

        self.pending_selection_token = token
        self.selection_confirmation_pending.set()
        self.root.after(0, self._confirm_selected_key)

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

    def _begin_hotkey_capture(self, _event=None) -> None:
        self.hotkey_capture_active = True
        self.hotkey_capture_tokens = []
        self.hotkey_pressed_tokens.clear()

    def _end_hotkey_capture(self, _event=None) -> None:
        self.hotkey_capture_active = False
        self.hotkey_pressed_tokens.clear()

    def _on_hotkey_entry_key_press(self, event) -> str:
        if not self.hotkey_capture_active:
            return "break"

        token = keysym_to_hotkey_token(event.keysym)
        if token is None:
            return "break"

        if token not in self.hotkey_pressed_tokens:
            self.hotkey_pressed_tokens.add(token)
            self.hotkey_capture_tokens.append(token)
            self.hotkey_text_var.set("+".join(self.hotkey_capture_tokens))

        return "break"

    def _on_hotkey_entry_key_release(self, event) -> str:
        token = keysym_to_hotkey_token(event.keysym)
        if token is not None and token in self.hotkey_pressed_tokens:
            self.hotkey_pressed_tokens.remove(token)
        return "break"

    def get_interval_seconds(self) -> float:
        raw = self.interval_ms_var.get().strip()
        if not raw:
            raise ValueError("Interval is required")

        interval_ms = float(raw)
        if interval_ms <= 0:
            raise ValueError("Interval must be greater than 0")

        return interval_ms / 1000.0

    def set_status(self, is_on: bool) -> None:
        self.status_text_var.set("Status: ON" if is_on else "Status: OFF")

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
                self.root.after(0, self.stop_pressing)
                break

            try:
                interval = self.get_interval_seconds()
                press_key = token_to_press_key(token)
            except ValueError:
                self.root.after(0, self.stop_pressing)
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Invalid setting",
                        "Please enter a valid interval and selected key.",
                    ),
                )
                break

            self.keyboard_controller.press(press_key)
            self.keyboard_controller.release(press_key)
            time.sleep(interval)

    def _on_hotkey_trigger(self) -> None:
        self.root.after(0, self.toggle_pressing)

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
        self.hotkey_text_var.set(DEFAULT_HOTKEY)
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

