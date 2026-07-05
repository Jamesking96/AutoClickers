# Auto Clicker Tools

Simple desktop automation tools with a Tkinter UI.

## Features

- `mouse_auto_clicker.py`
  - Set click interval in milliseconds.
  - Start a position-selection mode from the UI, then move the mouse anywhere on screen.
  - Left-click to sample and confirm a new click position.
  - Right-click to cancel position selection.
  - Set the click button by pressing the desired mouse button in button-selection mode.
  - Reset click button to left using `Default Left`.
- `keyboard_auto_clicker.py`
  - Set key press interval in milliseconds.
  - Start a key-selection mode and press a key to capture it.
  - Press `Escape` while selecting to cancel key selection.
  - Confirm the selected key in a dialog, or retry by choosing `No`.
  - Start/stop auto key pressing from the UI.
- Shared behavior
  - Click into the hotkey box and press a key combination to capture it, then press `Apply`.
  - Revert the toggle hotkey to default (`Alt+F6`) with `Revert Default`.

## Install

```bash
python -m pip install -r requirements.txt
```

## Run

```bash
python mouse_auto_clicker.py
python keyboard_auto_clicker.py
```

## Builds
- This is done by `pyinstaller` and the build scripts in the `build` folder.
- Example: `pyinstaller mouse_auto_clicker.spec`

## Notes

- The mouse tool performs left-clicks.
- The keyboard tool presses the selected key each interval.
- Global hotkeys are handled by `pynput`.
- If you answer `No` in the confirmation dialog, position selection immediately resumes so you can try again.
- On some systems, global input hooks may require extra permissions.

