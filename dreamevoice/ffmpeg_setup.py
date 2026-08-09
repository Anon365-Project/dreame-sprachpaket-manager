"""Einrichtungshilfe für ffmpeg.

ffmpeg wird gebraucht, um mp3-, wav- oder m4a-Dateien in das Format zu
bringen, das der Roboter versteht (OGG Vorbis, mono, 16000 Hz). Fertige
.ogg-Dateien im richtigen Format funktionieren auch ohne ffmpeg.

Diese Datei lädt nichts von allein herunter. Der Download startet
ausschließlich, wenn der Nutzer ihn in der Oberfläche ausdrücklich
bestätigt - dort steht vorher, von welcher Adresse geladen wird und wie
groß die Datei ist.

Quelle ist das öffentliche Release-Verzeichnis von BtbN/FFmpeg-Builds auf
GitHub. Das ist die von ffmpeg.org selbst verlinkte Bezugsquelle für
Windows-Builds.

Aus dem Archiv wird bewusst nicht alles entpackt, sondern gezielt nur
ffmpeg.exe und ffprobe.exe - und zwar nur anhand ihres Dateinamens, ohne
die im Archiv hinterlegten Pfade zu übernehmen. Ein manipuliertes Archiv
kann so nichts an anderer Stelle im Dateisystem ablegen.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Callable, Optional

import requests

from .audio import _run, find_ffmpeg
from .errors import AudioError, NetworkError
from .paths import data_dir

_LOG = logging.getLogger(__name__)

ProgressFn = Callable[[int, int], None]
LogFn = Callable[[str], None]

DOWNLOAD_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
                "latest/ffmpeg-master-latest-win64-gpl.zip")
PROJECT_URL = "https://github.com/BtbN/FFmpeg-Builds"
APPROX_SIZE_MB = 170

WANTED = {"ffmpeg.exe", "ffprobe.exe"}
MAX_ARCHIVE_BYTES = 400 * 1024 * 1024
MAX_MEMBER_BYTES = 250 * 1024 * 1024


def target_dir() -> Path:
    return data_dir() / "ffmpeg"


def installed_path() -> Optional[Path]:
    candidate = target_dir() / "ffmpeg.exe"
    return candidate if candidate.is_file() else None


def describe_source() -> str:
    """Text für den Bestätigungsdialog."""
    return (
        f"ffmpeg wird von GitHub geladen:\n\n{DOWNLOAD_URL}\n\n"
        f"Das ist das offizielle Windows-Build-Projekt, das auch ffmpeg.org "
        f"verlinkt ({PROJECT_URL}).\n\n"
        f"Größe: etwa {APPROX_SIZE_MB} MB. Aus dem Archiv werden nur "
        f"ffmpeg.exe und ffprobe.exe entnommen und in den Datenordner der App "
        f"gelegt. Am System wird nichts verändert, es wird nichts installiert "
        f"und nichts in die Registry geschrieben.\n\n"
        f"Alternative ohne Download: eine vorhandene ffmpeg.exe einfach in den "
        f"Ordner dieser App kopieren."
    )


def _noop_log(_: str) -> None:
    pass


def download_and_install(progress: Optional[ProgressFn] = None,
                         log: LogFn = _noop_log,
                         cancelled: Optional[Callable[[], bool]] = None) -> Path:
    """Lädt ffmpeg und legt ffmpeg.exe im Datenordner ab.

    Nur nach ausdrücklicher Bestätigung durch den Nutzer aufrufen.
    """
    cancelled = cancelled or (lambda: False)
    dest = target_dir()
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "_download.zip"

    log(f"Lade von {DOWNLOAD_URL}")
    try:
        with requests.get(DOWNLOAD_URL, stream=True, timeout=120,
                          headers={"User-Agent": "DreameSprachpakete/1.0"}) as resp:
            if resp.status_code != 200:
                raise NetworkError(
                    f"Der Download ist fehlgeschlagen (HTTP {resp.status_code}).",
                    f"Quelle: {DOWNLOAD_URL}")

            total = int(resp.headers.get("Content-Length") or 0)
            if total and total > MAX_ARCHIVE_BYTES:
                raise NetworkError(
                    "Die angebotene Datei ist unerwartet groß.",
                    f"{total // (1024 * 1024)} MB - der Download wurde abgebrochen.")

            done = 0
            with archive.open("wb") as fh:
                for block in resp.iter_content(chunk_size=1 << 18):
                    if cancelled():
                        raise NetworkError("Vom Benutzer abgebrochen.")
                    if not block:
                        continue
                    fh.write(block)
                    done += len(block)
                    if done > MAX_ARCHIVE_BYTES:
                        raise NetworkError("Der Download wurde unerwartet groß "
                                           "und wurde abgebrochen.")
                    if progress:
                        progress(done, total)
    except requests.exceptions.RequestException as exc:
        archive.unlink(missing_ok=True)
        raise NetworkError("ffmpeg konnte nicht geladen werden.",
                           f"Technische Details: {exc}") from exc
    except Exception:
        archive.unlink(missing_ok=True)
        raise

    log(f"Heruntergeladen: {archive.stat().st_size // (1024 * 1024)} MB")
    log("Entnehme ffmpeg.exe und ffprobe.exe ...")

    extracted: list[str] = []
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                # Nur der reine Dateiname zählt - Pfade aus dem Archiv werden
                # verworfen, damit nichts ausserhalb von dest landen kann.
                name = Path(info.filename.replace("\\", "/")).name
                if name.lower() not in WANTED:
                    continue
                if info.file_size > MAX_MEMBER_BYTES:
                    continue
                with zf.open(info) as src, (dest / name).open("wb") as out:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                extracted.append(name)
    except zipfile.BadZipFile as exc:
        archive.unlink(missing_ok=True)
        raise AudioError("Die heruntergeladene Datei ist kein gültiges Archiv.",
                         f"Technische Details: {exc}") from exc
    finally:
        archive.unlink(missing_ok=True)

    exe = dest / "ffmpeg.exe"
    if not exe.is_file():
        raise AudioError(
            "Im Archiv war keine ffmpeg.exe enthalten.",
            f"Gefunden wurde: {', '.join(extracted) or 'nichts'}. "
            f"Bitte ffmpeg von Hand besorgen und neben die App legen.")

    log(f"Entpackt: {', '.join(extracted)}")

    # Funktionsprobe: läuft die Datei, und kann sie Vorbis kodieren?
    try:
        version = _run([str(exe), "-version"], timeout=30)
    except Exception as exc:
        raise AudioError("Die entpackte ffmpeg.exe lässt sich nicht starten.",
                         f"Technische Details: {exc}") from exc

    if version.returncode != 0:
        raise AudioError("Die entpackte ffmpeg.exe meldet einen Fehler.",
                         (version.stderr or "")[:300])

    first_line = (version.stdout or "").splitlines()
    log(first_line[0] if first_line else "ffmpeg gestartet")

    encoders = _run([str(exe), "-hide_banner", "-encoders"], timeout=30)
    if "libvorbis" not in (encoders.stdout or ""):
        raise AudioError(
            "Diesem ffmpeg fehlt der Vorbis-Kodierer (libvorbis).",
            "Ohne ihn lassen sich keine Dreame-Sprachpakete erzeugen. "
            "Bitte einen vollständigen ffmpeg-Build verwenden.")

    log("Vorbis-Kodierer vorhanden - ffmpeg ist einsatzbereit.")
    return exe


def ensure() -> Optional[Path]:
    """Sucht ffmpeg (auch das selbst eingerichtete) - ohne Download."""
    return find_ffmpeg()
