# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Bauplan für eine einzelne, portable EXE.

Bauen mit:   pyinstaller DreameSprachpaket.spec --noconfirm
Ergebnis:    dist/DreameSprachpaket.exe
"""

from pathlib import Path

BASE = Path(SPECPATH)

a = Analysis(
    ["main.py"],
    pathex=[str(BASE)],
    binaries=[],
    # Der Sound-Katalog muss mit ins Bündel - er wird zur Laufzeit gelesen.
    datas=[("dreamevoice/data/sound_catalog.json", "dreamevoice/data")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Ballast, den Tkinter-Apps nicht brauchen. Spart deutlich Größe.
    excludes=[
        "numpy", "pandas", "matplotlib", "scipy", "PIL", "PyQt5", "PySide2",
        "notebook", "IPython", "pytest", "setuptools", "pip", "wheel",
        "test", "unittest", "pydoc_data", "distutils",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DreameSprachpaket",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # kein schwarzes Konsolenfenster
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Symbol und Versionsangaben. Ohne beides ist die Datei fuer Windows
    # namenlos: SmartScreen zeigt dann nur den Dateinamen, und
    # heuristische Scanner werten eine Programmdatei ohne jede Angabe
    # ueber sich selbst als verdaechtiger. Eine Signatur ersetzt das
    # nicht - aber es kostet nichts.
    icon="app.ico",
    version="version_info.txt",
)
