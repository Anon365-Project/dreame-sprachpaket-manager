"""Mitgeliefertes ffmpeg, das hinten an die EXE angehängt ist.

Warum nicht einfach über PyInstaller bündeln?
---------------------------------------------
PyInstaller entpackt im Onefile-Modus **bei jedem Start** sämtliche
gebündelten Dateien in einen Temp-Ordner. Bei einer 139 MB grossen
ffmpeg.exe würde die App dadurch jedes Mal mehrere Sekunden zum Starten
brauchen - und das für ein Werkzeug, das die meisten Nutzer nie
benötigen, weil sie fertige .ogg-Dateien verwenden.

Deshalb wird ffmpeg stattdessen LZMA-komprimiert (139 MB -> 39 MB) hinten
an die fertige EXE angehängt. Der PyInstaller-Bootloader stört sich nicht
daran, weil er seinen eigenen Datenbereich über eine Signatur findet und
nicht über das Dateiende (nachgemessen: die EXE startet mit angehängten
Daten unverändert).

Ergebnis: weiterhin **eine einzige portable Datei**, unveränderter
Startvorgang, und ffmpeg wird genau einmal ausgepackt, wenn es zum ersten
Mal gebraucht wird.

Aufbau des Anhangs (am Dateiende):

    [ LZMA-Daten ][ Länge, 8 Byte little-endian ][ MAGIC, 16 Byte ]
"""

from __future__ import annotations

import logging
import lzma
import os
import sys
from pathlib import Path
from typing import Callable, Optional

from .paths import data_dir, is_frozen

_LOG = logging.getLogger(__name__)

MAGIC = b"DREAMEVOICE_FFMP"      # exakt 16 Byte
TRAILER_SIZE = 8 + len(MAGIC)    # Länge + Signatur

ProgressFn = Callable[[int, int], None]
LogFn = Callable[[str], None]


def _container() -> Optional[Path]:
    """Die Datei, in der der Anhang stecken kann (nur als EXE sinnvoll)."""
    if not is_frozen():
        return None
    path = Path(sys.executable)
    return path if path.is_file() else None


def payload_size() -> int:
    """Grösse des Anhangs in Byte, 0 wenn keiner vorhanden ist."""
    container = _container()
    if container is None:
        return 0
    try:
        total = container.stat().st_size
        if total <= TRAILER_SIZE:
            return 0
        with container.open("rb") as fh:
            fh.seek(-TRAILER_SIZE, os.SEEK_END)
            trailer = fh.read(TRAILER_SIZE)
        if trailer[8:] != MAGIC:
            return 0
        length = int.from_bytes(trailer[:8], "little")
        # Muss plausibel in die Datei passen.
        if 0 < length <= total - TRAILER_SIZE:
            return length
    except OSError as exc:
        _LOG.debug("Anhang nicht lesbar: %s", exc)
    return 0


def has_ffmpeg() -> bool:
    return payload_size() > 0


def target_path() -> Path:
    return data_dir() / "ffmpeg" / "ffmpeg.exe"


def extract_ffmpeg(progress: Optional[ProgressFn] = None,
                   log: Optional[LogFn] = None) -> Optional[Path]:
    """Packt das mitgelieferte ffmpeg aus. Gibt den Pfad zurück.

    Ein bereits ausgepacktes ffmpeg wird wiederverwendet.
    """
    target = target_path()
    if target.is_file() and target.stat().st_size > 1_000_000:
        return target

    length = payload_size()
    container = _container()
    if not length or container is None:
        return None

    if log:
        log("Packe das mitgelieferte ffmpeg aus (einmalig) ...")

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")

    try:
        total = container.stat().st_size
        start = total - TRAILER_SIZE - length

        decompressor = lzma.LZMADecompressor()
        written = 0
        with container.open("rb") as src, tmp.open("wb") as dst:
            src.seek(start)
            remaining = length
            while remaining > 0:
                block = src.read(min(1 << 20, remaining))
                if not block:
                    break
                remaining -= len(block)
                chunk = decompressor.decompress(block)
                if chunk:
                    dst.write(chunk)
                    written += len(chunk)
                if progress:
                    progress(length - remaining, length)
    except (OSError, lzma.LZMAError) as exc:
        tmp.unlink(missing_ok=True)
        _LOG.error("ffmpeg konnte nicht ausgepackt werden: %s", exc)
        return None

    if written < 1_000_000:
        tmp.unlink(missing_ok=True)
        _LOG.error("Ausgepacktes ffmpeg ist unplausibel klein (%d Byte)", written)
        return None

    try:
        tmp.replace(target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        _LOG.error("ffmpeg konnte nicht abgelegt werden: %s", exc)
        return None

    if log:
        log(f"ffmpeg ausgepackt ({written // (1024 * 1024)} MB).")
    _LOG.info("ffmpeg aus dem Anhang ausgepackt: %s", target)
    return target
