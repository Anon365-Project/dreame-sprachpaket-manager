"""Ein Sprachpaket anhören, bevor es auf den Roboter kommt.

Bis hierher war das Aufspielen ein Sprung ins kalte Wasser: Man baute
ein Paket, schickte es an den Roboter und erfuhr erst beim nächsten
Reinigungsstart, wie es klingt. Wem die Stimme dann nicht gefiel, der
musste alles noch einmal machen.

Diese Datei entnimmt einem Paket ein paar aussagekräftige Ansagen und
spielt sie nacheinander ab. Sie kommt mit allem zurecht, was in dieser
App ein "Paket" sein kann:

* ein gebautes Sprachpaket (`.tar.gz`)
* ein Archiv mit Aufnahmen (`.zip`)
* ein Ordner voller nummerierter Audiodateien

Abgespielt wird über winsound, weil das ohne Fremdbibliothek auskommt
und keinen externen Player öffnet - vier Fenster für vier Ansagen wäre
schlimmer als gar keine Vorschau. Dafür braucht winsound WAV, weshalb
die Ogg-Dateien vorher durch ffmpeg gehen.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .audio import SUPPORTED_INPUT
from .importer import sound_id_from_name
from .sounds import SoundCatalog

_LOG = logging.getLogger(__name__)

LogFn = Callable[[str], None]

#: Vier Ansagen, die man im Alltag wirklich hört und an denen man Stimme
#: und Dialekt gut beurteilen kann: Reinigung startet, Akku schwach,
#: festgefahren, Rückkehr zur Station.
BEISPIELE: List[int] = [7, 14, 40, 55]

#: Falls ein Paket keine davon mitbringt - dann eben die ersten,
#: die überhaupt da sind.
HOECHSTENS = 4


def _mitglieder_tar(archiv: Path) -> Dict[int, str]:
    with tarfile.open(archiv, "r:*") as tf:
        return {n: m.name for m in tf.getmembers() if m.isfile()
                for n in [sound_id_from_name(Path(m.name).name)]
                if n is not None
                and Path(m.name).suffix.lower() in SUPPORTED_INPUT}


def _mitglieder_zip(archiv: Path) -> Dict[int, str]:
    with zipfile.ZipFile(archiv) as zf:
        return {n: i.filename for i in zf.infolist() if not i.is_dir()
                for n in [sound_id_from_name(Path(i.filename).name)]
                if n is not None
                and Path(i.filename).suffix.lower() in SUPPORTED_INPUT}


def verfuegbare_ids(quelle: Path) -> List[int]:
    """Welche Ansagen stecken in diesem Paket?"""
    quelle = Path(quelle)
    try:
        if quelle.is_dir():
            return sorted({n for p in quelle.rglob("*")
                           if p.is_file()
                           and p.suffix.lower() in SUPPORTED_INPUT
                           for n in [sound_id_from_name(p.name)]
                           if n is not None})
        if zipfile.is_zipfile(quelle):
            return sorted(_mitglieder_zip(quelle))
        return sorted(_mitglieder_tar(quelle))
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        _LOG.warning("Paket nicht lesbar (%s): %s", quelle, exc)
        return []


def auswahl(quelle: Path, wunsch: Optional[List[int]] = None) -> List[int]:
    """Die Nummern, die vorgespielt werden sollen."""
    vorhanden = verfuegbare_ids(quelle)
    if not vorhanden:
        return []
    wunsch = wunsch if wunsch is not None else BEISPIELE
    passend = [i for i in wunsch if i in vorhanden]
    if passend:
        return passend[:HOECHSTENS]
    return vorhanden[:HOECHSTENS]


def entnehmen(quelle: Path, ziel: Path,
              ids: Optional[List[int]] = None) -> Dict[int, Path]:
    """Holt die gewünschten Ansagen aus dem Paket in einen Ordner."""
    quelle = Path(quelle)
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    gewuenscht = ids if ids is not None else auswahl(quelle)
    if not gewuenscht:
        return {}

    heraus: Dict[int, Path] = {}
    try:
        if quelle.is_dir():
            for pfad in sorted(quelle.rglob("*")):
                if not pfad.is_file():
                    continue
                nummer = sound_id_from_name(pfad.name)
                if nummer in gewuenscht and nummer not in heraus:
                    heraus[nummer] = pfad
        elif zipfile.is_zipfile(quelle):
            mitglieder = _mitglieder_zip(quelle)
            with zipfile.ZipFile(quelle) as zf:
                for nummer in gewuenscht:
                    name = mitglieder.get(nummer)
                    if not name:
                        continue
                    aus = ziel / f"{nummer}{Path(name).suffix}"
                    aus.write_bytes(zf.read(name))
                    heraus[nummer] = aus
        else:
            mitglieder = _mitglieder_tar(quelle)
            with tarfile.open(quelle, "r:*") as tf:
                for nummer in gewuenscht:
                    name = mitglieder.get(nummer)
                    if not name:
                        continue
                    fh = tf.extractfile(name)
                    if fh is None:
                        continue
                    aus = ziel / f"{nummer}{Path(name).suffix}"
                    aus.write_bytes(fh.read())
                    heraus[nummer] = aus
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        _LOG.warning("Ansagen nicht entnommen (%s): %s", quelle, exc)
    return heraus


def nach_wav(quelle: Path, ziel: Path, ffmpeg: Optional[Path]) -> Optional[Path]:
    """Wandelt eine Ansage in WAV - das Einzige, was winsound abspielt."""
    if quelle.suffix.lower() == ".wav":
        return quelle
    if not ffmpeg:
        return None
    try:
        fertig = subprocess.run(
            [str(ffmpeg), "-y", "-loglevel", "error", "-i", str(quelle),
             "-ar", "22050", "-ac", "1", str(ziel)],
            capture_output=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as exc:
        _LOG.warning("Umwandlung fehlgeschlagen: %s", exc)
        return None
    if fertig.returncode != 0 or not ziel.is_file():
        _LOG.warning("ffmpeg meldete %s", fertig.returncode)
        return None
    return ziel


def beschriftung(nummer: int, katalog: Optional[SoundCatalog] = None) -> str:
    """Was diese Ansage bedeutet - für die Anzeige beim Abspielen."""
    if katalog is None:
        return f"Ansage {nummer}"
    eintrag = katalog.get(nummer)
    return f"Ansage {nummer} · {eintrag.title}" if eintrag else f"Ansage {nummer}"


def abspielen(dateien: List[Path],
              cancelled: Optional[Callable[[], bool]] = None,
              melden: Optional[Callable[[int], None]] = None) -> int:
    """Spielt WAV-Dateien nacheinander ab. Gibt zurück, wie viele liefen.

    Läuft in einem Hintergrundfaden, weil winsound blockiert.
    """
    cancelled = cancelled or (lambda: False)
    if sys.platform != "win32":
        return 0
    try:
        import winsound
    except ImportError:            # pragma: no cover - nur auf Windows
        return 0

    gespielt = 0
    for index, datei in enumerate(dateien):
        if cancelled():
            break
        if melden:
            melden(index)
        try:
            winsound.PlaySound(str(datei), winsound.SND_FILENAME)
            gespielt += 1
        except RuntimeError as exc:
            _LOG.warning("Abspielen fehlgeschlagen (%s): %s", datei, exc)
    return gespielt


def probe_vorbereiten(quelle: Path, ffmpeg: Optional[Path],
                      ids: Optional[List[int]] = None,
                      log: Optional[LogFn] = None) -> Dict[int, Path]:
    """Entnimmt die Beispiele und wandelt sie in abspielbares WAV.

    Der Rückgabewert ist nach Nummer sortiert einsetzbar; ein leerer
    bedeutet, dass sich nichts anhören lässt.
    """
    arbeit = Path(tempfile.mkdtemp(prefix="dreamevoice_probe_"))
    roh = entnehmen(quelle, arbeit, ids)
    if not roh:
        if log:
            log("In diesem Paket ist keine Ansage zum Anhören.")
        return {}

    fertig: Dict[int, Path] = {}
    for nummer in sorted(roh):
        wav = nach_wav(roh[nummer], arbeit / f"{nummer}.wav", ffmpeg)
        if wav is not None:
            fertig[nummer] = wav

    if not fertig and log:
        log("Zum Anhören wird ffmpeg gebraucht - es ließ sich nicht nutzen.")
    return fertig
