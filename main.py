"""Startpunkt des Dreame Sprachpaket-Managers.

Starten mit:      python main.py
Als EXE bauen:    siehe build_exe.ps1
"""

from __future__ import annotations

import sys
import traceback


def _enable_dpi_awareness() -> None:
    """Sagt Windows, dass die App selbst mit der Bildschirmskalierung umgeht.

    Ohne das behandelt Windows eine Tkinter-App auf skalierten Bildschirmen
    (125 %, 150 %, 4K) als "alte" Anwendung: Sie bekommt eine verkleinerte,
    virtuelle Bildschirmgrösse und wird anschliessend hochskaliert. Das
    Ergebnis ist unscharf, und beim Maximieren nutzt das Fenster den
    Bildschirm nicht wirklich aus.

    Muss vor dem ersten Tk-Fenster passieren, sonst wirkt es nicht.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # 2 = Per-Monitor-DPI-Awareness (Windows 8.1+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()   # aeltere Windows
        except Exception:
            pass


def _fatal(title: str, message: str) -> None:
    """Zeigt einen Fehler auch dann an, wenn die GUI nie hochkam."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        print(f"{title}\n\n{message}", file=sys.stderr)


def main() -> int:
    if sys.version_info < (3, 9):
        _fatal("Python zu alt",
               "Diese App braucht Python 3.9 oder neuer.\n"
               f"Gefunden: {sys.version.split()[0]}")
        return 1

    try:
        import requests  # noqa: F401
    except ImportError:
        _fatal("Baustein fehlt",
               "Das Paket 'requests' ist nicht installiert.\n\n"
               "Installiere es mit:\n\n    pip install -r requirements.txt")
        return 1

    try:
        import tkinter  # noqa: F401
    except ImportError:
        _fatal("Tkinter fehlt",
               "Diese Python-Installation enthält kein Tkinter.\n\n"
               "Unter Windows hilft eine Neuinstallation von python.org, "
               "unter Linux das Paket 'python3-tk'.")
        return 1

    _enable_dpi_awareness()

    try:
        from dreamevoice.ui.app import run
        run()
    except Exception:
        _fatal("Unerwarteter Fehler",
               "Die App musste beendet werden.\n\n" + traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
