import tkinter as tk
from tkinter import ttk


DEFAULT_HOTKEY = "alt+f6"
DEFAULT_THEME = "Windows XP"
THEMES: dict[str, dict[str, str | list[str]]] = {
	"Windows XP": {
		"bg": "#ece9d8",
		"button_bg": "#f1efe2",
		"border": "#7f9db9",
		"text": "#000000",
		"hint": "#4a4a4a",
		"accent": "#0a246a",
		"button_pressed": "#dcd8c3",
		"button_active": "#faf8ed",
		"entry_bg": "#ffffff",
		"focus_light": "#ffffff",
	},
	"Light Gray": {
		"bg": "#f3f3f3",
		"button_bg": "#e8e8e8",
		"border": "#b9b9b9",
		"text": "#1f1f1f",
		"hint": "#5e5e5e",
		"accent": "#1f6feb",
		"button_pressed": "#d9d9d9",
		"button_active": "#f7f7f7",
		"entry_bg": "#ffffff",
		"focus_light": "#ffffff",
	},
	"Dark Slate": {
		"bg": "#1f232a",
		"button_bg": "#2b313a",
		"border": "#4a5463",
		"text": "#f0f6fc",
		"hint": "#9ea7b3",
		"accent": "#58a6ff",
		"button_pressed": "#242a33",
		"button_active": "#343c47",
		"entry_bg": "#151b23",
		"focus_light": "#3b4657",
	},
	"GAE": {
		"bg": "#fff1f8",
		"bg_gradient": ["#ff0000", "#ff7f00", "#ffff00", "#00ff00", "#00ffff", "#0000ff", "#4b0082", "#9400d3"],
		"button_bg": "#ffd166",
		"border": "#8338ec",
		"text": "#2d1b69",
		"hint": "#2a9d8f",
		"accent": "#3a86ff",
		"button_pressed": "#ff006e",
		"button_active": "#06d6a0",
		"entry_bg": "#f1f7ff",
		"focus_light": "#ffffff",
	},
}

# Keep legacy XP constants for callers that still import them.
XP_BG = THEMES[DEFAULT_THEME]["bg"]
XP_BUTTON_BG = THEMES[DEFAULT_THEME]["button_bg"]
XP_BORDER = THEMES[DEFAULT_THEME]["border"]
XP_TEXT = THEMES[DEFAULT_THEME]["text"]
XP_HINT = THEMES[DEFAULT_THEME]["hint"]
XP_ACCENT = THEMES[DEFAULT_THEME]["accent"]


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
	color = color.lstrip("#")
	return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
	return "#{:02x}{:02x}{:02x}".format(*rgb)


def _interpolate_color(start: str, end: str, ratio: float) -> str:
	start_rgb = _hex_to_rgb(start)
	end_rgb = _hex_to_rgb(end)
	blended = (
		int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio),
		int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio),
		int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio),
	)
	return _rgb_to_hex(blended)


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


class AutoClickerUIBase:
	def __init__(self, root: tk.Tk, title: str, geometry: str) -> None:
		self.root = root
		self.root.title(title)
		self.root.geometry(geometry)
		self.style = ttk.Style()
		if "clam" in self.style.theme_names():
			self.style.theme_use("clam")

		self.hotkey_text_var = tk.StringVar(value=DEFAULT_HOTKEY)
		self.status_text_var = tk.StringVar(value="Stopped")
		self.theme_name_var = tk.StringVar(value=DEFAULT_THEME)
		self.hotkey_capture_active = False
		self.hotkey_capture_tokens: list[str] = []
		self.hotkey_pressed_tokens: set[str] = set()
		self.keep_window_on_top = False
		self._active_theme_colors = THEMES[DEFAULT_THEME]

		# Canvas-based background lets themes render either a solid color or a gradient.
		self.root_canvas = tk.Canvas(self.root, highlightthickness=0, borderwidth=0)
		self.root_canvas.pack(fill="both", expand=True)
		self.root_canvas.bind("<Configure>", self._on_canvas_resize)
		# Use tk.Frame with no background so gradient shows through
		self.root_content_frame = tk.Frame(self.root_canvas, background="")
		self.root_content_window = self.root_canvas.create_window(0, 0, anchor="nw", window=self.root_content_frame)
		self._inner_content_frame = None

		self._apply_theme(self.theme_name_var.get())

	def build_root_container(self, padding: int = 12):
		# Create inner ttk.Frame with padding inside the transparent root frame
		if self._inner_content_frame is not None:
			self._inner_content_frame.destroy()
		self._inner_content_frame = ttk.Frame(self.root_content_frame, style="XP.TFrame", padding=padding)
		self._inner_content_frame.pack(fill="both", expand=True)
		return self._inner_content_frame

	def _on_canvas_resize(self, event) -> None:
		self.root_canvas.itemconfigure(self.root_content_window, width=event.width, height=event.height)
		self._redraw_background(event.width, event.height)

	def _redraw_background(self, width: int, height: int) -> None:
		width = max(1, width)
		height = max(1, height)
		self.root_canvas.delete("theme_bg")

		gradient_stops = self._active_theme_colors.get("bg_gradient")
		if isinstance(gradient_stops, list) and len(gradient_stops) >= 2:
			segments = len(gradient_stops) - 1
			for y in range(height):
				progress = y / max(1, height - 1)
				segment_float = progress * segments
				segment_index = min(segments - 1, int(segment_float))
				local_ratio = segment_float - segment_index
				line_color = _interpolate_color(
					gradient_stops[segment_index],
					gradient_stops[segment_index + 1],
					local_ratio,
				)
				self.root_canvas.create_line(0, y, width, y, fill=line_color, tags="theme_bg")
		else:
			bg_color = str(self._active_theme_colors["bg"])
			self.root_canvas.create_rectangle(0, 0, width, height, fill=bg_color, outline=bg_color, tags="theme_bg")

		self.root_canvas.tag_lower("theme_bg")

	def _apply_theme(self, theme_name: str) -> None:
		colors = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
		self._active_theme_colors = colors
		self.theme_name_var.set(theme_name if theme_name in THEMES else DEFAULT_THEME)
		self.root.configure(background=colors["bg"])
		self.root_canvas.configure(background=colors["bg"])
		self._redraw_background(self.root_canvas.winfo_width(), self.root_canvas.winfo_height())

		self.style.configure(".", font=("Tahoma", 9))
		# Root content frame uses tk.Frame with no background, inner frames use XP.TFrame
		self.style.configure("XP.TFrame", background=colors["bg"])
		self.style.configure("XP.TLabel", background=colors["bg"], foreground=colors["text"])
		self.style.configure("Hint.XP.TLabel", background=colors["bg"], foreground=colors["hint"])
		self.style.configure("StatusCaption.XP.TLabel", background=colors["bg"], foreground=colors["text"], font=("Tahoma", 9, "bold"))
		self.style.configure("Status.XP.TLabel", background=colors["bg"], foreground=colors["accent"], font=("Tahoma", 9, "bold"))
		self.style.configure(
			"XP.TButton",
			background=colors["button_bg"],
			foreground=colors["text"],
			bordercolor=colors["border"],
			lightcolor=colors["focus_light"],
			darkcolor=colors["border"],
			focusthickness=1,
			focuscolor=colors["accent"],
			padding=(8, 3),
		)
		self.style.map(
			"XP.TButton",
			background=[("pressed", colors["button_pressed"]), ("active", colors["button_active"])],
			bordercolor=[("pressed", colors["accent"]), ("active", colors["accent"])],
		)
		self.style.configure(
			"XP.TEntry",
			fieldbackground=colors["entry_bg"],
			foreground=colors["text"],
			bordercolor=colors["border"],
			lightcolor=colors["focus_light"],
			darkcolor=colors["border"],
			insertcolor=colors["text"],
		)
		self.style.map("XP.TEntry", bordercolor=[("focus", colors["accent"])])
		self.style.configure("XP.TSeparator", background=colors["border"])
		self.style.configure(
			"XP.TCombobox",
			fieldbackground=colors["entry_bg"],
			foreground=colors["text"],
			background=colors["button_bg"],
			bordercolor=colors["border"],
			lightcolor=colors["focus_light"],
			darkcolor=colors["border"],
			arrowcolor=colors["text"],
		)
		self.style.map(
			"XP.TCombobox",
			fieldbackground=[("readonly", colors["entry_bg"])],
			foreground=[("readonly", colors["text"])],
			bordercolor=[("focus", colors["accent"])],
		)

	def build_theme_controls(self, parent, label_text: str = "Theme:"):
		ttk.Label(parent, text=label_text, style="XP.TLabel").pack(anchor="w")
		row = ttk.Frame(parent, style="XP.TFrame")
		row.pack(fill="x", pady=(0, 10))
		theme_picker = ttk.Combobox(
			row,
			textvariable=self.theme_name_var,
			values=list(THEMES.keys()),
			state="readonly",
			style="XP.TCombobox",
		)
		theme_picker.pack(side="left", fill="x", expand=True)
		theme_picker.bind("<<ComboboxSelected>>", lambda _event: self._apply_theme(self.theme_name_var.get()))
		return theme_picker

	def bring_window_to_front(self) -> None:
		self.root.deiconify()
		self.root.attributes("-topmost", True)
		self.root.lift()
		self.root.focus_force()
		if not self.keep_window_on_top:
			self.root.after(50, lambda: self._clear_topmost())

	def _clear_topmost(self) -> None:
		if not self.keep_window_on_top:
			self.root.attributes("-topmost", False)

	def pin_window_on_top(self) -> None:
		self.keep_window_on_top = True
		self.root.attributes("-topmost", True)
		self.root.lift()
		self.root.focus_force()

	def release_window_on_top(self) -> None:
		self.keep_window_on_top = False
		self.root.attributes("-topmost", False)

	def schedule_ui(self, delay_ms: int, callback) -> None:
		self.root.after(delay_ms, lambda: callback())

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

	def set_status(self, is_on: bool) -> None:
		self.status_text_var.set("Running" if is_on else "Stopped")

	def build_hotkey_controls(self, parent, apply_command, revert_command, label_text: str = "Toggle hotkey (default Alt+F6):"):
		ttk.Label(parent, text=label_text, style="XP.TLabel").pack(anchor="w")
		hotkey_row = ttk.Frame(parent, style="XP.TFrame")
		hotkey_row.pack(fill="x", pady=(0, 8))
		self.hotkey_entry = ttk.Entry(hotkey_row, textvariable=self.hotkey_text_var, style="XP.TEntry")
		self.hotkey_entry.pack(side="left", fill="x", expand=True)
		self.hotkey_entry.bind("<FocusIn>", self._begin_hotkey_capture)
		self.hotkey_entry.bind("<FocusOut>", self._end_hotkey_capture)
		self.hotkey_entry.bind("<KeyPress>", self._on_hotkey_entry_key_press)
		self.hotkey_entry.bind("<KeyRelease>", self._on_hotkey_entry_key_release)
		ttk.Button(hotkey_row, text="Apply", command=apply_command, style="XP.TButton").pack(side="left", padx=(8, 0))
		ttk.Button(hotkey_row, text="Revert Default", command=revert_command, style="XP.TButton").pack(side="left", padx=(8, 0))
		return self.hotkey_entry

	def build_status_section(self, parent, tip_text: str = "Tip: Use the hotkey anytime to toggle ON/OFF.") -> None:
		status_row = ttk.Frame(parent, style="XP.TFrame")
		status_row.pack(fill="x", anchor="w", pady=(6, 0))
		ttk.Label(status_row, text="Tool status:", style="StatusCaption.XP.TLabel").pack(side="left")
		ttk.Label(status_row, textvariable=self.status_text_var, style="Status.XP.TLabel").pack(side="left", padx=(6, 0))
		ttk.Label(parent, text=tip_text, style="Hint.XP.TLabel").pack(anchor="w", pady=(6, 0))



