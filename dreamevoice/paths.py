"""Ablageorte für Konfiguration, Downloads und Arbeitsdateien.

Die App ist portabel gedacht: liegt sie in einem beschreibbaren Ordner
(USB-Stick, Desktop), landen alle Daten in einem Unterordner daneben.
Nur wenn das nicht geht (z. B. Programme-Ordner), wird auf %APPDATA%
ausgewichen.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_DIRNAME = "DreameSprachpakete"


def is_frozen() -> bool:
    """True, wenn die App als PyInstaller-EXE läuft."""
    return getattr(sys, "frozen", False)


def app_dir() -> Path:
    """Ordner, in dem die EXE bzw. das Projekt liegt."""
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Ordner mit den mitgelieferten Daten (im EXE-Bundle entpackt)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return Path(__file__).resolve().parent.parent


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".schreibtest"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def data_dir() -> Path:
    """Basisordner für Konfiguration und heruntergeladene Pakete."""
    portable = app_dir() / "Daten"
    if _writable(portable):
        return portable

    roaming = os.environ.get("APPDATA")
    fallback = Path(roaming) / _APP_DIRNAME if roaming else Path.home() / f".{_APP_DIRNAME}"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def config_file() -> Path:
    return data_dir() / "config.json"


def cache_dir() -> Path:
    """Offizielle Original-Pakete, damit sie nur einmal geladen werden."""
    d = data_dir() / "Originalpakete"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_dir() -> Path:
    """Hier entstehen die selbst gebauten Sprachpakete."""
    d = data_dir() / "Meine Pakete"
    d.mkdir(parents=True, exist_ok=True)
    return d


def preview_dir() -> Path:
    """Entpackte Original-Ogg-Dateien für die Hörprobe."""
    d = data_dir() / "Hörproben"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    return data_dir() / "verlauf.log"
