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

from UI.auto_clicker_ui import (AutoClickerUIBase, DEFAULT_HOTKEY, normalize_hotkey)


def mouse_button_to_text(button: mouse.Button) -> str:
    button_map = {
        mouse.Button.left: "Left",
        mouse.Button.right: "Right",
        mouse.Button.middle: "Middle",
    }
    return button_map.get(button, str(button).replace("Button.", "").title())


class MouseAutoClickerApp(AutoClickerUIBase):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, "Mouse Auto Clicker", "420x460")

        self.mouse_controller = mouse.Controller()
        self.hotkey_listener: keyboard.GlobalHotKeys | None = None
        self.selection_mouse_listener: mouse.Listener | None = None
        self.button_selection_mouse_listener: mouse.Listener | None = None

        self.interval_ms_var = tk.StringVar(value="100")
        self.position_text_var = tk.StringVar(value="Current cursor position")
        self.click_button_text_var = tk.StringVar(value="Left")
        self.selection_text_var = tk.StringVar(value="Press the button below to choose a click position.")

        self.target_position = None
        self.target_click_button = mouse.Button.left
        self.pending_selection_position = None
        self.pending_selection_button = None
        self.click_thread = None
        self.clicking_active = threading.Event()
        self.shutdown_event = threading.Event()
        self.position_selection_active = threading.Event()
        self.button_selection_active = threading.Event()
        self.selection_confirmation_pending = threading.Event()
        self.button_selection_confirmation_pending = threading.Event()
        self.state_lock = threading.Lock()

        self._build_ui()
        self.apply_hotkey()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        outer = self.build_root_container(padding=12)

        self.build_theme_controls(outer)

        ttk.Label(outer, text="Click interval (milliseconds):", style="XP.TLabel").pack(anchor="w")
        ttk.Entry(outer, textvariable=self.interval_ms_var, style="XP.TEntry").pack(fill="x", pady=(0, 10))

        ttk.Label(outer, text="Target mouse position:", style="XP.TLabel").pack(anchor="w")
        pos_row = ttk.Frame(outer, style="XP.TFrame")
        pos_row.pack(fill="x", pady=(0, 4))
        ttk.Label(pos_row, textvariable=self.position_text_var, style="XP.TLabel").pack(side="left")

        pos_button_row = ttk.Frame(outer, style="XP.TFrame")
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
            outer,
            textvariable=self.selection_text_var,
            wraplength=380,
            style="Hint.XP.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(outer, text="Click button:", style="XP.TLabel").pack(anchor="w")
        button_row = ttk.Frame(outer, style="XP.TFrame")
        button_row.pack(fill="x", pady=(0, 4))
        ttk.Label(button_row, textvariable=self.click_button_text_var, style="XP.TLabel").pack(side="left")

        button_select_row = ttk.Frame(outer, style="XP.TFrame")
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

        ttk.Separator(outer, style="XP.TSeparator").pack(fill="x", pady=8)

        self.build_hotkey_controls(outer, self.apply_hotkey, self.revert_default_hotkey)

        button_row = ttk.Frame(outer, style="XP.TFrame")
        button_row.pack(fill="x", pady=(6, 6))
        ttk.Button(button_row, text="Start", command=self.start_clicking, style="XP.TButton").pack(side="left", fill="x", expand=True)
        ttk.Button(button_row, text="Stop", command=self.stop_clicking, style="XP.TButton").pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.build_status_section(outer)

    def start_position_selection(self) -> None:
        if self.clicking_active.is_set():
            messagebox.showwarning("Stop clicking first", "Stop the auto clicker before choosing a new position.")
            return

        if self.button_selection_active.is_set():
            messagebox.showwarning("Button selection active", "Finish click-button selection before setting a position.")
            return

        if self.position_selection_active.is_set():
            self.selection_text_var.set(
                "Selection already active: left-click anywhere to confirm a position, or right-click to cancel."
            )
            self.bring_window_to_front()
            return

        self.position_selection_active.set()
        self.selection_confirmation_pending.clear()
        self.set_position_button.state(["disabled"])
        self.selection_text_var.set(
            "Selection active: left-click anywhere to set the position, or right-click to cancel."
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
        self.set_position_button.state(["!disabled"])
        self.selection_text_var.set(message)
        self.bring_window_to_front()

    def cancel_position_selection(self) -> None:
        if not self.position_selection_active.is_set():
            return
        self._finish_position_selection("Position selection cancelled.")

    def clear_position(self) -> None:
        if self.clicking_active.is_set():
            messagebox.showwarning("Stop clicking first", "Stop the auto clicker before clearing the position.")
            return
        with self.state_lock:
            self.target_position = None
        self.position_text_var.set("Current cursor position")
        self.selection_text_var.set("Press the button below to choose a click position.")

    def start_button_selection(self) -> None:
        if self.clicking_active.is_set():
            messagebox.showwarning("Stop clicking first", "Stop the auto clicker before choosing a click button.")
            return

        if self.position_selection_active.is_set():
            messagebox.showwarning("Position selection active", "Finish position selection before setting a click button.")
            return

        if self.button_selection_active.is_set():
            self.selection_text_var.set("Button selection already active: click a mouse button to use for auto click.")
            self.bring_window_to_front()
            return

        self.button_selection_active.set()
        self.button_selection_confirmation_pending.clear()
        self.pending_selection_button = None
        self.set_click_button_button.state(["disabled"])
        self.selection_text_var.set("Button selection active: click the mouse button you want to auto press.")
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
        self.selection_text_var.set(message)
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
        self.selection_text_var.set("Click button reset to Left.")

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
        self.selection_text_var.set("Button selection active: click another mouse button to use for auto click.")
        self.pin_window_on_top()
        self.bring_window_to_front()

    def _on_selection_mouse_click(self, _x: int, _y: int, button: mouse.Button, pressed: bool) -> None:
        if not pressed or not self.position_selection_active.is_set():
            return

        if button == mouse.Button.right:
            self.schedule_ui(0, self.cancel_position_selection)
            return

        if button == mouse.Button.left and not self.selection_confirmation_pending.is_set():
            # Capture position exactly at the left-click event and keep it fixed.
            self.pending_selection_position = self.mouse_controller.position
            self.selection_confirmation_pending.set()
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
        self.selection_text_var.set(
            "Selection active: left-click anywhere to set the position, or right-click to cancel."
        )
        self.bring_window_to_front()

    def get_interval_seconds(self) -> float:
        raw = self.interval_ms_var.get().strip()
        if not raw:
            raise ValueError("Interval is required")

        interval_ms = float(raw)
        if interval_ms <= 0:
            raise ValueError("Interval must be greater than 0")

        return interval_ms / 1000.0


    def start_clicking(self) -> None:

        try:
            self.get_interval_seconds()
        except ValueError as exc:
            messagebox.showerror("Invalid interval", str(exc))
            return

        if self.clicking_active.is_set():
            return

        self.clicking_active.set()
        self.set_status(True)
        self.click_thread = threading.Thread(target=self._click_loop, daemon=True)
        self.click_thread.start()

    def stop_clicking(self) -> None:
        if not self.clicking_active.is_set():
            return

        self.clicking_active.clear()
        self.set_status(False)

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
                interval = self.get_interval_seconds()
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

    def _on_hotkey_trigger(self) -> None:
        self.schedule_ui(0, self.toggle_clicking)

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
        self.stop_clicking()
        self.cancel_position_selection()
        self.cancel_button_selection()

        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()
            self.hotkey_listener = None

        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = MouseAutoClickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
