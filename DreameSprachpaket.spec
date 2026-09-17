# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Bauplan für eine einzelne, portable EXE.

Bauen mit:   pyinstaller DreameSprachpaket.spec --noconfirm
Ergebnis:    dist/DreameSprachpaket.exe
"""

from pathlib import Path

BASE = Path(SPECPATH)

# Welche Fassung zu den entpackten Dateien gehört. Die EXE vergleicht das
# beim Start mit ihrer eigenen Version und erkennt so, ob sie nach einer
# Aktualisierung mit den Dateien der alten Fassung läuft
# (siehe aktualisierung.fremd_entpackt).
import re as _re

_version = _re.search(r'__version__\s*=\s*"([^"]+)"',
                      (BASE / "dreamevoice" / "__init__.py").read_text(
                          encoding="utf-8")).group(1)
_fassung = BASE / "build" / "_fassung" / "fassung.txt"
_fassung.parent.mkdir(parents=True, exist_ok=True)
_fassung.write_text(_version, encoding="utf-8")

a = Analysis(
    ["main.py"],
    pathex=[str(BASE)],
    binaries=[],
    # Der Sound-Katalog muss mit ins Bündel - er wird zur Laufzeit gelesen.
    # Die Anleitungen aus `docs` ebenfalls: Das Hilfe-Fenster verlinkt
    # sie, und wer nur die EXE hat, hätte sonst gar keinen Zugang zu
    # ihnen. Zusammen wiegen sie unter 100 kB.
    # app.ico steckt zwar unten schon als EXE-Symbol drin, aber nur als
    # Ressource der Programmdatei - auslesen lässt sich das zur
    # Laufzeit nicht. Fürs Fenstersymbol muss die Datei daneben liegen.
    datas=[("dreamevoice/data/sound_catalog.json", "dreamevoice/data"),
           (str(_fassung), "dreamevoice/data"),
           ("docs", "docs"),
           ("app.ico", ".")],
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
    # Symbol und Versionsangaben. Ohne beides ist die Datei für Windows
    # namenlos: SmartScreen zeigt dann nur den Dateinamen, und
    # heuristische Scanner werten eine Programmdatei ohne jede Angabe
    # über sich selbst als verdächtiger. Eine Signatur ersetzt das
    # nicht - aber es kostet nichts.
    icon="app.ico",
    version="version_info.txt",
)
