# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

# Resolve paths from the project root so builds work when launched from
# d:\TechArt\Personal_Projects\Python.
spec_dir = os.path.join(os.getcwd(), 'Tools', 'AutoClickers', 'python')

a = Analysis(
    ['keyboard_auto_clicker.py'],
    pathex=[spec_dir],
    binaries=[],
    # Include the UI package - path is relative to spec file location
    datas=[(os.path.join(spec_dir, 'UI'), 'UI')],
    hiddenimports=[
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='keyboard_auto_clicker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(spec_dir, 'keyboard_auto_clicker.ico') if os.path.exists(os.path.join(spec_dir, 'keyboard_auto_clicker.ico')) else None,
)

