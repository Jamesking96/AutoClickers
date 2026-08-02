import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from pynput import keyboard, mouse

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
from mouse_auto_clicker import mouse_button_to_text
from keyboard_auto_clicker import pynput_key_to_token, token_to_press_key


DEFAULT_HOTKEY_MOUSE = "f6"
DEFAULT_HOTKEY_KEYBOARD = "alt+f6"


class CombinedAutoClickerApp(AutoClickerUIBase):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, "Auto Clicker", "460x560")

        self.mouse_controller = mouse.Controller()
        self.keyboard_controller = keyboard.Controller()

        self.hotkey_listener: keyboard.GlobalHotKeys | None = None
        self.selection_mouse_listener: mouse.Listener | None = None
        self.button_selection_mouse_listener: mouse.Listener | None = None
        self.selection_key_listener: keyboard.Listener | None = None

        self.mode_var = tk.StringVar(value="mouse")

        self.interval_ms_mouse_var = tk.StringVar(value="100")
        self.interval_ms_keyboard_var = tk.StringVar(value="100")
        self.interval_ms_var = tk.StringVar(value="100")

        self.position_text_var = tk.StringVar(value="Current cursor position")
        self.click_button_text_var = tk.StringVar(value="Left")
        self.mouse_selection_text_var = tk.StringVar(value="Press the button below to choose a click position.")

        self.key_text_var = tk.StringVar(value="Not set")
        self.keyboard_selection_text_var = tk.StringVar(value="Press the button below to choose a key to auto press.")

        self.hotkey_mouse_value = DEFAULT_HOTKEY_MOUSE
        self.hotkey_keyboard_value = DEFAULT_HOTKEY_KEYBOARD
        self.hotkeys_only_for_active_mode_var = tk.BooleanVar(value=False)

        self.target_position = None
        self.target_click_button = mouse.Button.left
        self.pending_selection_position = None
        self.pending_selection_button = None

        self.target_key_token: str | None = None
        self.pending_selection_token: str | None = None

        self.click_thread = None
        self.press_thread = None
        self.clicking_active = threading.Event()
        self.pressing_active = threading.Event()
        self.shutdown_event = threading.Event()

        self.position_selection_active = threading.Event()
        self.button_selection_active = threading.Event()
        self.selection_confirmation_pending = threading.Event()
        self.button_selection_confirmation_pending = threading.Event()

        self.key_selection_active = threading.Event()
        self.key_selection_confirmation_pending = threading.Event()

        self.state_lock = threading.Lock()

        self._load_hotkey_scope_preference()
        self._build_ui()
        self._sync_mode_view()
        self.apply_hotkey()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = self.build_root_container(padding=12)

        self.build_settings_button(outer, self._build_hotkey_scope_settings)

        ttk.Label(outer, text="Mode:", style="XP.TLabel").pack(anchor="w")
        mode_row = ttk.Frame(outer, style="XP.TFrame")
        mode_row.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(
            mode_row,
            text="Mouse",
            value="mouse",
            variable=self.mode_var,
            command=self._on_mode_changed,
            style="XP.TRadiobutton",
        ).pack(side="left", fill="x", expand=True)
        ttk.Radiobutton(
            mode_row,
            text="Keyboard",
            value="keyboard",
            variable=self.mode_var,
            command=self._on_mode_changed,
            style="XP.TRadiobutton",
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))

        ttk.Label(outer, text="Interval (milliseconds):", style="XP.TLabel").pack(anchor="w")
        self.interval_entry = ttk.Entry(outer, textvariable=self.interval_ms_var, style="XP.TEntry")
        self.interval_entry.pack(fill="x", pady=(0, 10))

        self.mode_content_frame = ttk.Frame(outer, style="XP.TFrame")
        self.mode_content_frame.pack(fill="x")

        self.mouse_frame = ttk.Frame(self.mode_content_frame, style="XP.TFrame")
        self._build_mouse_controls(self.mouse_frame)

        self.keyboard_frame = ttk.Frame(self.mode_content_frame, style="XP.TFrame")
        self._build_keyboard_controls(self.keyboard_frame)

        ttk.Separator(outer, style="XP.TSeparator").pack(fill="x", pady=8)

        self.build_hotkey_controls(outer, self.apply_hotkey, self.revert_default_hotkey)

        button_row = ttk.Frame(outer, style="XP.TFrame")
        button_row.pack(fill="x", pady=(6, 6))
        self.toggle_button = ttk.Button(button_row, text="Start", command=self.toggle_active_mode, style="XP.TButton")
        self.toggle_button.pack(side="left", fill="x", expand=True)

        self.build_status_section(outer)

    def _build_hotkey_scope_settings(self, body) -> None:
        ttk.Label(body, text="Hotkey behavior:", style="XP.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Checkbutton(
            body,
            text="Only run hotkeys for the active mode",
            variable=self.hotkeys_only_for_active_mode_var,
            command=self._save_hotkey_scope_preference,
            style="XP.TCheckbutton",
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(
            body,
            text="When enabled, the mouse hotkey only works on the mouse view and the keyboard hotkey only works on the keyboard view.",
            wraplength=280,
            style="Hint.XP.TLabel",
        ).pack(anchor="w")

    def _load_hotkey_scope_preference(self) -> None:
        value = self._saved_preferences.get("hotkeys_only_for_active_mode")
        if isinstance(value, bool):
            self.hotkeys_only_for_active_mode_var.set(value)

    def _save_hotkey_scope_preference(self) -> None:
        self._saved_preferences["hotkeys_only_for_active_mode"] = self.hotkeys_only_for_active_mode_var.get()
        self._save_theme_preference()

    def _build_mouse_controls(self, parent) -> None:
        ttk.Label(parent, text="Target mouse position:", style="XP.TLabel").pack(anchor="w")
        pos_row = ttk.Frame(parent, style="XP.TFrame")
        pos_row.pack(fill="x", pady=(0, 4))
        ttk.Label(pos_row, textvariable=self.position_text_var, style="XP.TLabel").pack(side="left")

        pos_button_row = ttk.Frame(parent, style="XP.TFrame")
        pos_button_row.pack(fill="x", pady=(0, 6))
        self.set_position_button = ttk.Button(
            pos_button_row,
            text="Set mouse position",
            command=self.start_position_selection,
            style="XP.TButton",
        )
        self.set_position_button.pack(side="left", fill="x", expand=True)
        self.clear_position_button = ttk.Button(
            pos_button_row,
            text="Clear",
            command=self.clear_position,
            style="XP.TButton",
        )
        self.clear_position_button.pack(side="left", padx=(8, 0))
        ttk.Label(
            parent,
            textvariable=self.mouse_selection_text_var,
            wraplength=410,
            style="Hint.XP.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(parent, text="Click button:", style="XP.TLabel").pack(anchor="w")
        button_row = ttk.Frame(parent, style="XP.TFrame")
        button_row.pack(fill="x", pady=(0, 4))
        ttk.Label(button_row, textvariable=self.click_button_text_var, style="XP.TLabel").pack(side="left")

        button_select_row = ttk.Frame(parent, style="XP.TFrame")
        button_select_row.pack(fill="x", pady=(0, 10))
        self.set_click_button_button = ttk.Button(
            button_select_row,
            text="Set click button",
            command=self.start_button_selection,
            style="XP.TButton",
        )
        self.set_click_button_button.pack(side="left", fill="x", expand=True)
        ttk.Button(
            button_select_row,
            text="Default Left",
            command=self.reset_click_button,
            style="XP.TButton",
        ).pack(side="left", padx=(8, 0))

    def _build_keyboard_controls(self, parent) -> None:
        ttk.Label(parent, text="Target key:", style="XP.TLabel").pack(anchor="w")
        key_row = ttk.Frame(parent, style="XP.TFrame")
        key_row.pack(fill="x", pady=(0, 4))
        ttk.Label(key_row, textvariable=self.key_text_var, style="XP.TLabel").pack(side="left")

        key_button_row = ttk.Frame(parent, style="XP.TFrame")
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
            parent,
            textvariable=self.keyboard_selection_text_var,
            wraplength=410,
            style="Hint.XP.TLabel",
        ).pack(anchor="w", pady=(0, 10))

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------
    def _on_mode_changed(self) -> None:
        self._sync_mode_view()

    def _sync_mode_view(self) -> None:
        mode = self.mode_var.get()

        self.mouse_frame.pack_forget()
        self.keyboard_frame.pack_forget()
        if mode == "mouse":
            self.mouse_frame.pack(fill="x")
            self.interval_entry.configure(textvariable=self.interval_ms_mouse_var)
            self.interval_ms_var = self.interval_ms_mouse_var
            self.hotkey_text_var.set(self.hotkey_mouse_value)
        else:
            self.keyboard_frame.pack(fill="x")
            self.interval_entry.configure(textvariable=self.interval_ms_keyboard_var)
            self.interval_ms_var = self.interval_ms_keyboard_var
            self.hotkey_text_var.set(self.hotkey_keyboard_value)

        self._refresh_status()

    def _is_active_mode_running(self) -> bool:
        if self.mode_var.get() == "mouse":
            return self.clicking_active.is_set()
        return self.pressing_active.is_set()

    def _hotkey_allowed_for_mode(self, mode: str) -> bool:
        if not self.hotkeys_only_for_active_mode_var.get():
            return True
        return self.mode_var.get() == mode

    def _refresh_status(self) -> None:
        running = self._is_active_mode_running()
        self.set_status(running)
        self.toggle_button.configure(text="Stop" if running else "Start")

    # ------------------------------------------------------------------
    # Mouse: position selection
    # ------------------------------------------------------------------
    def start_position_selection(self) -> None:
        if self.clicking_active.is_set():
            messagebox.showwarning("Stop clicking first", "Stop the auto clicker before choosing a new position.")
            return

        if self.button_selection_active.is_set():
            messagebox.showwarning("Button selection active", "Finish click-button selection before setting a position.")
            return

        if self.position_selection_active.is_set():
            self.mouse_selection_text_var.set(
                "Selection already active: left-click anywhere to confirm a position, or right-click to cancel."
            )
            self.show_selection_overlay(
                "Mouse position selection is active.\n\nLeft-click anywhere to confirm a position.\nPress Esc to cancel."
            )
            self.bring_window_to_front()
            return

        self.position_selection_active.set()
        self.selection_confirmation_pending.clear()
        self.set_position_button.state(["disabled"])
        self.mouse_selection_text_var.set(
            "Selection active: left-click anywhere to set the position, or right-click to cancel."
        )
        self.show_selection_overlay(
            "Mouse position selection is active.\n\nLeft-click anywhere to confirm a position.\nPress Esc to cancel."
        )
        self.bring_window_to_front()
        self._start_selection_listeners()

    def _start_selection_listeners(self) -> None:
        self.selection_mouse_listener = mouse.Listener(on_click=self._on_selection_mouse_click)
        self.selection_mouse_listener.start()

    def _stop_selection_listeners(self) -> None:
        if self.selection_mouse_listener is not None:
            self.selection_mouse_listener.stop()
            self.selection_mouse_listener = None

        self.selection_confirmation_pending.clear()
        self.pending_selection_position = None

    def _finish_position_selection(self, message: str) -> None:
        self.position_selection_active.clear()
        self._stop_selection_listeners()
        self.hide_selection_overlay()
        self.set_position_button.state(["!disabled"])
        self.mouse_selection_text_var.set(message)
        self.bring_window_to_front()

    def cancel_position_selection(self) -> None:
        if not self.position_selection_active.is_set():
            self.hide_selection_overlay()
            return
        self._finish_position_selection("Position selection cancelled.")

    def clear_position(self) -> None:
        if self.clicking_active.is_set():
            messagebox.showwarning("Stop clicking first", "Stop the auto clicker before clearing the position.")
            return
        with self.state_lock:
            self.target_position = None
        self.position_text_var.set("Current cursor position")
        self.mouse_selection_text_var.set("Press the button below to choose a click position.")

    def _on_selection_mouse_click(self, _x: int, _y: int, button: mouse.Button, pressed: bool) -> None:
        if not pressed or not self.position_selection_active.is_set():
            return

        if button == mouse.Button.right:
            self.schedule_ui(0, self.cancel_position_selection)
            return

        if button == mouse.Button.left and not self.selection_confirmation_pending.is_set():
            self.pending_selection_position = self.mouse_controller.position
            self.selection_confirmation_pending.set()
            self.hide_selection_overlay()
            self.schedule_ui(0, self._begin_position_confirmation)

    def _begin_position_confirmation(self) -> None:
        self.bring_window_to_front()
        self.schedule_ui(75, self._confirm_selected_position)

    def _confirm_selected_position(self) -> None:
        if not self.position_selection_active.is_set():
            self.selection_confirmation_pending.clear()
            return

        if self.pending_selection_position is None:
            self.selection_confirmation_pending.clear()
            return

        x, y = self.pending_selection_position

        confirmed = messagebox.askyesno(
            "Confirm Position",
            f"Use this mouse position?\n\nX: {x}\nY: {y}",
            parent=self.root,
        )
        if confirmed:
            with self.state_lock:
                self.target_position = (x, y)
            self.position_text_var.set(f"X={x}, Y={y}")
            self._finish_position_selection("Position confirmed and saved.")
            return

        self.selection_confirmation_pending.clear()
        self.mouse_selection_text_var.set(
            "Selection active: left-click anywhere to set the position, or right-click to cancel."
        )
        self.bring_window_to_front()

    # ------------------------------------------------------------------
    # Mouse: click button selection
    # ------------------------------------------------------------------
    def start_button_selection(self) -> None:
        if self.clicking_active.is_set():
            messagebox.showwarning("Stop clicking first", "Stop the auto clicker before choosing a click button.")
            return

        if self.position_selection_active.is_set():
            messagebox.showwarning("Position selection active", "Finish position selection before setting a click button.")
            return

        if self.button_selection_active.is_set():
            self.mouse_selection_text_var.set("Button selection already active: click a mouse button to use for auto click.")
            self.bring_window_to_front()
            return

        self.button_selection_active.set()
        self.button_selection_confirmation_pending.clear()
        self.pending_selection_button = None
        self.set_click_button_button.state(["disabled"])
        self.mouse_selection_text_var.set("Button selection active: click the mouse button you want to auto press.")
        self.pin_window_on_top()
        self.bring_window_to_front()
        self._start_button_selection_listener()

    def _start_button_selection_listener(self) -> None:
        self.button_selection_mouse_listener = mouse.Listener(on_click=self._on_button_selection_mouse_click)
        self.button_selection_mouse_listener.start()

    def _stop_button_selection_listener(self) -> None:
        if self.button_selection_mouse_listener is not None:
            self.button_selection_mouse_listener.stop()
            self.button_selection_mouse_listener = None

        self.button_selection_confirmation_pending.clear()
        self.pending_selection_button = None

    def _finish_button_selection(self, message: str) -> None:
        self.button_selection_active.clear()
        self._stop_button_selection_listener()
        self.set_click_button_button.state(["!disabled"])
        self.mouse_selection_text_var.set(message)
        self.release_window_on_top()
        self.bring_window_to_front()

    def cancel_button_selection(self) -> None:
        if not self.button_selection_active.is_set():
            return
        self._finish_button_selection("Click-button selection cancelled.")

    def reset_click_button(self) -> None:
        if self.clicking_active.is_set():
            messagebox.showwarning("Stop clicking first", "Stop the auto clicker before resetting the click button.")
            return
        with self.state_lock:
            self.target_click_button = mouse.Button.left
        self.click_button_text_var.set("Left")
        self.mouse_selection_text_var.set("Click button reset to Left.")

    def _on_button_selection_mouse_click(self, _x: int, _y: int, button: mouse.Button, pressed: bool) -> None:
        if not pressed or not self.button_selection_active.is_set():
            return

        if self.button_selection_confirmation_pending.is_set():
            return

        self.pending_selection_button = button
        self.button_selection_confirmation_pending.set()
        self.schedule_ui(0, self._begin_click_button_confirmation)

    def _begin_click_button_confirmation(self) -> None:
        self.pin_window_on_top()
        self.bring_window_to_front()
        self.schedule_ui(75, self._confirm_selected_click_button)

    def _confirm_selected_click_button(self) -> None:
        if not self.button_selection_active.is_set():
            self.button_selection_confirmation_pending.clear()
            return

        if self.pending_selection_button is None:
            self.button_selection_confirmation_pending.clear()
            return

        button = self.pending_selection_button
        button_name = mouse_button_to_text(button)
        confirmed = messagebox.askyesno(
            "Confirm Click Button",
            f"Use this mouse button for auto click?\n\nButton: {button_name}",
            parent=self.root,
        )
        if confirmed:
            with self.state_lock:
                self.target_click_button = button
            self.click_button_text_var.set(button_name)
            self._finish_button_selection("Click button confirmed and saved.")
            return

        self.pending_selection_button = None
        self.button_selection_confirmation_pending.clear()
        self.mouse_selection_text_var.set("Button selection active: click another mouse button to use for auto click.")
        self.pin_window_on_top()
        self.bring_window_to_front()

    # ------------------------------------------------------------------
    # Keyboard: key selection
    # ------------------------------------------------------------------
    def start_key_selection(self) -> None:
        if self.pressing_active.is_set():
            messagebox.showwarning("Stop pressing first", "Stop the auto presser before choosing a key.")
            return

        if self.key_selection_active.is_set():
            self.keyboard_selection_text_var.set("Selection already active: press a key to set it, or press Esc to cancel.")
            self.bring_window_to_front()
            return

        self.key_selection_active.set()
        self.key_selection_confirmation_pending.clear()
        self.pending_selection_token = None
        self.set_key_button.state(["disabled"])
        self.keyboard_selection_text_var.set("Selection active: press a key to set it, or press Esc to cancel.")
        self.bring_window_to_front()
        self._start_key_selection_listener()

    def _start_key_selection_listener(self) -> None:
        self.selection_key_listener = keyboard.Listener(on_press=self._on_selection_key_press)
        self.selection_key_listener.start()

    def _stop_key_selection_listener(self) -> None:
        if self.selection_key_listener is not None:
            self.selection_key_listener.stop()
            self.selection_key_listener = None

        self.key_selection_confirmation_pending.clear()
        self.pending_selection_token = None

    def _finish_key_selection(self, message: str) -> None:
        self.key_selection_active.clear()
        self._stop_key_selection_listener()
        self.set_key_button.state(["!disabled"])
        self.keyboard_selection_text_var.set(message)
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
        self.keyboard_selection_text_var.set("Press the button below to choose a key to auto press.")

    def _on_selection_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if not self.key_selection_active.is_set() or self.key_selection_confirmation_pending.is_set():
            return

        if key == keyboard.Key.esc:
            self.schedule_ui(0, self.cancel_key_selection)
            return

        token = pynput_key_to_token(key)
        if token is None:
            return

        self.pending_selection_token = token
        self.key_selection_confirmation_pending.set()
        self.schedule_ui(0, self._confirm_selected_key)

    def _confirm_selected_key(self) -> None:
        if not self.key_selection_active.is_set():
            self.key_selection_confirmation_pending.clear()
            return

        if self.pending_selection_token is None:
            self.key_selection_confirmation_pending.clear()
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
        self.key_selection_confirmation_pending.clear()
        self.keyboard_selection_text_var.set("Selection active: press another key to set it, or press Esc to cancel.")
        self.bring_window_to_front()

    # ------------------------------------------------------------------
    # Intervals
    # ------------------------------------------------------------------
    def get_interval_seconds(self, var: tk.StringVar) -> float:
        raw = var.get().strip()
        if not raw:
            raise ValueError("Interval is required")

        interval_ms = float(raw)
        if interval_ms <= 0:
            raise ValueError("Interval must be greater than 0")

        return interval_ms / 1000.0

    # ------------------------------------------------------------------
    # Mouse clicking loop
    # ------------------------------------------------------------------
    def start_clicking(self) -> None:
        try:
            self.get_interval_seconds(self.interval_ms_mouse_var)
        except ValueError as exc:
            messagebox.showerror("Invalid interval", str(exc))
            return

        if self.clicking_active.is_set():
            return

        self.clicking_active.set()
        self._refresh_status()
        self.click_thread = threading.Thread(target=self._click_loop, daemon=True)
        self.click_thread.start()

    def stop_clicking(self) -> None:
        if not self.clicking_active.is_set():
            return

        self.clicking_active.clear()
        self._refresh_status()

    def toggle_clicking(self) -> None:
        if self.clicking_active.is_set():
            self.stop_clicking()
        else:
            self.start_clicking()

    def _click_loop(self) -> None:
        while self.clicking_active.is_set() and not self.shutdown_event.is_set():
            with self.state_lock:
                target = self.target_position
                click_button = self.target_click_button

            if target is None:
                target = self.mouse_controller.position

            try:
                interval = self.get_interval_seconds(self.interval_ms_mouse_var)
            except ValueError:
                self.schedule_ui(0, self.stop_clicking)
                self.schedule_ui(
                    0,
                    lambda: messagebox.showerror(
                        "Invalid interval",
                        "Please enter a valid click interval in milliseconds.",
                    ),
                )
                break

            self.mouse_controller.position = target
            self.mouse_controller.click(click_button)
            time.sleep(interval)

    # ------------------------------------------------------------------
    # Keyboard pressing loop
    # ------------------------------------------------------------------
    def start_pressing(self) -> None:
        with self.state_lock:
            token = self.target_key_token

        if token is None:
            messagebox.showwarning("Key required", "Please set a key before starting auto press.")
            return

        try:
            self.get_interval_seconds(self.interval_ms_keyboard_var)
            token_to_press_key(token)
        except ValueError as exc:
            messagebox.showerror("Invalid setting", str(exc))
            return

        if self.pressing_active.is_set():
            return

        self.pressing_active.set()
        self._refresh_status()
        self.press_thread = threading.Thread(target=self._press_loop, daemon=True)
        self.press_thread.start()

    def stop_pressing(self) -> None:
        if not self.pressing_active.is_set():
            return

        self.pressing_active.clear()
        self._refresh_status()

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
                interval = self.get_interval_seconds(self.interval_ms_keyboard_var)
                press_key = token_to_press_key(token)
            except ValueError:
                self.schedule_ui(0, self.stop_pressing)
                self.schedule_ui(
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

    # ------------------------------------------------------------------
    # Shared start/stop for whichever mode is currently displayed
    # ------------------------------------------------------------------
    def toggle_active_mode(self) -> None:
        if self.mode_var.get() == "mouse":
            self.toggle_clicking()
        else:
            self.toggle_pressing()

    # ------------------------------------------------------------------
    # Hotkeys: each mode keeps its own, with optional active-mode gating
    # ------------------------------------------------------------------
    def apply_hotkey(self) -> None:
        value = self.hotkey_text_var.get().strip()
        try:
            normalize_hotkey(value)
        except ValueError as exc:
            messagebox.showerror("Invalid hotkey", str(exc))
            return

        other_value = self.hotkey_keyboard_value if self.mode_var.get() == "mouse" else self.hotkey_mouse_value
        try:
            if normalize_hotkey(value) == normalize_hotkey(other_value):
                messagebox.showerror(
                    "Hotkey conflict",
                    "This hotkey is already used by the other mode. Choose a different combination.",
                )
                return
        except ValueError:
            pass

        if self.mode_var.get() == "mouse":
            self.hotkey_mouse_value = value
        else:
            self.hotkey_keyboard_value = value

        self._rebuild_hotkey_listener()

    def _rebuild_hotkey_listener(self) -> None:
        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()
            self.hotkey_listener = None

        mapping = {}
        try:
            mapping[normalize_hotkey(self.hotkey_mouse_value)] = self._on_mouse_hotkey_trigger
        except ValueError:
            pass
        try:
            mapping[normalize_hotkey(self.hotkey_keyboard_value)] = self._on_keyboard_hotkey_trigger
        except ValueError:
            pass

        self.hotkey_listener = keyboard.GlobalHotKeys(mapping)
        self.hotkey_listener.start()

    def _on_mouse_hotkey_trigger(self) -> None:
        if self._hotkey_allowed_for_mode("mouse"):
            self.schedule_ui(0, self.toggle_clicking)

    def _on_keyboard_hotkey_trigger(self) -> None:
        if self._hotkey_allowed_for_mode("keyboard"):
            self.schedule_ui(0, self.toggle_pressing)

    def revert_default_hotkey(self) -> None:
        if self.mode_var.get() == "mouse":
            self.hotkey_text_var.set(DEFAULT_HOTKEY_MOUSE)
        else:
            self.hotkey_text_var.set(DEFAULT_HOTKEY_KEYBOARD)
        self.apply_hotkey()

    # ------------------------------------------------------------------
    def on_close(self) -> None:
        self.shutdown_event.set()
        self.stop_clicking()
        self.stop_pressing()
        self.cancel_position_selection()
        self.cancel_button_selection()
        self.cancel_key_selection()
        self.close_settings_window()
        self.hide_selection_overlay()

        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()
            self.hotkey_listener = None

        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = CombinedAutoClickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
