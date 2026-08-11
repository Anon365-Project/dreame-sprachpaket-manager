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

Aufbau eines Anhangs (am Dateiende):

    [ Daten ][ Länge, 8 Byte little-endian ][ MAGIC, 16 Byte ]

Es können **mehrere** Anhänge hintereinanderliegen. Gelesen wird vom
Dateiende rückwärts: Der letzte Abspann nennt die Länge seines Blocks,
davor beginnt der nächste Abspann. So kommt neben ffmpeg auch die
Sammlung der mitgelieferten Dialekte in dieselbe Datei, ohne dass eines
das andere unauffindbar macht.
"""

from __future__ import annotations

import logging
import lzma
import sys
import tarfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .paths import data_dir, is_frozen

_LOG = logging.getLogger(__name__)

MAGIC = b"DREAMEVOICE_FFMP"          # exakt 16 Byte, LZMA-gepackt
MAGIC_DIALEKTE = b"DREAMEVOICE_DIAL"  # exakt 16 Byte, unkomprimiertes tar
TRAILER_SIZE = 8 + len(MAGIC)        # Länge + Signatur

BEKANNT = {MAGIC, MAGIC_DIALEKTE}

ProgressFn = Callable[[int, int], None]
LogFn = Callable[[str], None]


def _container() -> Optional[Path]:
    """Die Datei, in der der Anhang stecken kann (nur als EXE sinnvoll)."""
    if not is_frozen():
        return None
    path = Path(sys.executable)
    return path if path.is_file() else None


def _bloecke() -> Dict[bytes, Tuple[int, int]]:
    """Alle Anhänge als {Signatur: (Startversatz, Länge)}.

    Gelesen wird vom Dateiende rückwärts, bis eine unbekannte Signatur
    auftaucht - dort endet die Kette und beginnt das Programm selbst.
    """
    container = _container()
    if container is None:
        return {}

    gefunden: Dict[bytes, Tuple[int, int]] = {}
    try:
        ende = container.stat().st_size
        with container.open("rb") as fh:
            while ende > TRAILER_SIZE:
                fh.seek(ende - TRAILER_SIZE)
                abspann = fh.read(TRAILER_SIZE)
                if len(abspann) != TRAILER_SIZE:
                    break
                signatur = abspann[8:]
                if signatur not in BEKANNT:
                    break
                laenge = int.from_bytes(abspann[:8], "little")
                start = ende - TRAILER_SIZE - laenge
                if laenge <= 0 or start < 0:
                    break
                # Der äusserste Block gewinnt, falls eine Signatur doppelt
                # vorkommt - das ist der zuletzt angehängte.
                gefunden.setdefault(signatur, (start, laenge))
                ende = start
    except OSError as exc:
        _LOG.debug("Anhang nicht lesbar: %s", exc)
    return gefunden


def payload_size() -> int:
    """Grösse des ffmpeg-Anhangs in Byte, 0 wenn keiner vorhanden ist."""
    block = _bloecke().get(MAGIC)
    return block[1] if block else 0


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

    block = _bloecke().get(MAGIC)
    container = _container()
    if block is None or container is None:
        return None
    start, length = block

    if log:
        log("Packe das mitgelieferte ffmpeg aus (einmalig) ...")

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")

    try:
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


# --------------------------------------------------------------------------
# Mitgelieferte Dialekte
# --------------------------------------------------------------------------
# Anders als ffmpeg werden sie NICHT komprimiert angehängt: der Inhalt sind
# Ogg-Dateien in ZIP-Archiven, also bereits verlustbehaftet gepackt. LZMA
# darüber kostet beim Bauen Minuten und spart nichts.

def _dialekt_tar():
    """Öffnet das angehängte tar mit den Aufnahme-Archiven."""
    block = _bloecke().get(MAGIC_DIALEKTE)
    container = _container()
    if block is None or container is None:
        return None
    start, laenge = block
    fh = container.open("rb")
    try:
        # Ein eigener Dateizeiger auf den Ausschnitt: tarfile liest ab der
        # aktuellen Position und stört sich nicht an dem, was dahinter
        # noch kommt.
        fh.seek(start)
        return tarfile.open(fileobj=_Ausschnitt(fh, start, laenge), mode="r|")
    except (OSError, tarfile.TarError) as exc:
        fh.close()
        _LOG.error("Mitgelieferte Dialekte nicht lesbar: %s", exc)
        return None


class _Ausschnitt:
    """Beschränkt das Lesen auf einen Bereich der Datei."""

    def __init__(self, fh, start: int, laenge: int) -> None:
        self._fh = fh
        self._rest = laenge
        self._fh.seek(start)

    def read(self, groesse: int = -1) -> bytes:
        if self._rest <= 0:
            return b""
        if groesse is None or groesse < 0:
            groesse = self._rest
        daten = self._fh.read(min(groesse, self._rest))
        self._rest -= len(daten)
        return daten

    def close(self) -> None:
        self._fh.close()


def has_dialekte() -> bool:
    return MAGIC_DIALEKTE in _bloecke()


def list_dialekte() -> List[str]:
    """Die Dateinamen der mitgelieferten Aufnahme-Archive."""
    tf = _dialekt_tar()
    if tf is None:
        return []
    try:
        return sorted(m.name for m in tf if m.isfile())
    except tarfile.TarError as exc:
        _LOG.error("Dialektliste nicht lesbar: %s", exc)
        return []
    finally:
        tf.close()


def dialekte_ordner() -> Path:
    return data_dir() / "Mitgelieferte Dialekte"


def extract_dialekt(dateiname: str,
                    log: Optional[LogFn] = None) -> Optional[Path]:
    """Packt ein mitgeliefertes Aufnahme-Archiv aus und gibt den Pfad zurück.

    Ein bereits ausgepacktes Archiv wird wiederverwendet.
    """
    ziel = dialekte_ordner() / dateiname
    if ziel.is_file() and ziel.stat().st_size > 1_000_000:
        return ziel

    tf = _dialekt_tar()
    if tf is None:
        return None

    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_suffix(ziel.suffix + ".part")
    geschrieben = 0
    try:
        for member in tf:
            if not member.isfile() or member.name != dateiname:
                continue
            quelle = tf.extractfile(member)
            if quelle is None:
                break
            if log:
                log(f"Packe {dateiname} aus (einmalig) ...")
            with tmp.open("wb") as dst:
                while True:
                    block = quelle.read(1 << 20)
                    if not block:
                        break
                    dst.write(block)
                    geschrieben += len(block)
            break
    except (OSError, tarfile.TarError) as exc:
        tmp.unlink(missing_ok=True)
        _LOG.error("%s nicht ausgepackt: %s", dateiname, exc)
        return None
    finally:
        tf.close()

    if geschrieben < 1_000_000:
        tmp.unlink(missing_ok=True)
        _LOG.error("%s ist unplausibel klein (%d Byte)", dateiname, geschrieben)
        return None

    try:
        tmp.replace(ziel)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        _LOG.error("%s nicht abgelegt: %s", dateiname, exc)
        return None

    _LOG.info("Dialekt %s ausgepackt (%d Byte)", dateiname, geschrieben)
    return ziel
