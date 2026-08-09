"""Lautstärke der Originalansagen als Vorlage.

Warum das nötig ist: die deutschen Originalansagen des X50 sind bewusst
sehr laut ausgesteuert (Median -15.9 LUFS, Spitzen bis +0.3 dBTP). Eine
neu gesprochene Ansage klingt daneben schnell zu leise - beim Roboter
fällt das sofort auf, weil laute und leise Ansagen abwechselnd kommen.

Deshalb wird jede Originalansage einmal ausgemessen. Beim Umwandeln
bekommt die neue Ansage dann genau die Lautheit der Ansage, die sie
ersetzt. Die Messung ist der langsame Teil (gut eine halbe Minute für
ein ganzes Paket), deshalb wird das Ergebnis neben dem Originalpaket
gespeichert und nur neu gemessen, wenn sich das Paket ändert.
"""

from __future__ import annotations

import json
import logging
import tarfile
import tempfile
from pathlib import Path
from typing import Callable, Dict, Optional

from .audio import TARGET_LUFS, find_ffmpeg, measure_loudness

_LOG = logging.getLogger(__name__)

CACHE_SUFFIX = ".lautstaerke.json"

# Version der Messlogik. Ändert sie sich, werden alte Dateien verworfen.
FORMAT = 1


def cache_path(base_pack: Path) -> Path:
    return Path(base_pack).with_suffix(Path(base_pack).suffix + CACHE_SUFFIX)


def _pack_kennung(base_pack: Path) -> str:
    """Grobe, aber ausreichende Kennung: Größe und Änderungszeit."""
    st = Path(base_pack).stat()
    return f"{st.st_size}-{int(st.st_mtime)}"


def load_cached(base_pack: Path) -> Optional[Dict[int, float]]:
    ziel = cache_path(base_pack)
    if not ziel.is_file():
        return None
    try:
        roh = json.loads(ziel.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(roh, dict) or roh.get("format") != FORMAT:
        return None
    if roh.get("paket") != _pack_kennung(base_pack):
        return None
    werte = roh.get("lufs")
    if not isinstance(werte, dict):
        return None
    ergebnis: Dict[int, float] = {}
    for schluessel, wert in werte.items():
        try:
            ergebnis[int(schluessel)] = float(wert)
        except (TypeError, ValueError):
            continue
    return ergebnis or None


def _save(base_pack: Path, werte: Dict[int, float]) -> None:
    try:
        cache_path(base_pack).write_text(
            json.dumps({
                "format": FORMAT,
                "paket": _pack_kennung(base_pack),
                "lufs": {str(k): round(v, 2) for k, v in sorted(werte.items())},
            }, indent=1),
            encoding="utf-8")
    except OSError as exc:
        _LOG.warning("Lautstärke-Tabelle nicht gespeichert: %s", exc)


def reference_levels(base_pack: Path,
                     ffmpeg: Optional[Path] = None,
                     log: Optional[Callable[[str], None]] = None,
                     cancelled: Optional[Callable[[], bool]] = None,
                     ) -> Dict[int, float]:
    """Lautheit jeder Originalansage in LUFS, nach Ansagenummer.

    Fehlt ffmpeg oder klappt etwas nicht, kommt ein leeres Wörterbuch
    zurück - dann wird einfach auf den festen Zielwert normalisiert.
    """
    base_pack = Path(base_pack)
    if not base_pack.is_file():
        return {}

    zwischenspeicher = load_cached(base_pack)
    if zwischenspeicher is not None:
        return zwischenspeicher

    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        return {}

    def sag(text: str) -> None:
        if log:
            log(text)

    sag("Messe einmalig die Lautstärke der Originalansagen "
        "(damit die neuen Ansagen genauso laut werden) ...")

    werte: Dict[int, float] = {}
    with tempfile.TemporaryDirectory(prefix="dreame_laut_") as tmp:
        ordner = Path(tmp)
        try:
            with tarfile.open(base_pack, "r:*") as tf:
                namen = [m for m in tf.getmembers()
                         if m.isfile() and m.name.lower().endswith(".ogg")]
                for member in namen:
                    stamm = Path(member.name).stem
                    if not stamm.isdigit():
                        continue
                    quelle = tf.extractfile(member)
                    if quelle is None:
                        continue
                    ziel = ordner / f"{stamm}.ogg"
                    ziel.write_bytes(quelle.read())
        except (tarfile.TarError, OSError) as exc:
            _LOG.warning("Originalpaket nicht lesbar: %s", exc)
            return {}

        dateien = sorted(ordner.glob("*.ogg"), key=lambda p: int(p.stem))
        for nummer, datei in enumerate(dateien, 1):
            if cancelled and cancelled():
                return werte
            gemessen = measure_loudness(datei, ffmpeg)
            if gemessen:
                werte[int(datei.stem)] = gemessen["input_i"]
            if nummer % 100 == 0:
                sag(f"  {nummer} von {len(dateien)} Originalansagen gemessen ...")

    if werte:
        sortiert = sorted(werte.values())
        sag(f"{len(werte)} Originalansagen gemessen "
            f"(Median {sortiert[len(sortiert) // 2]:.1f} LUFS).")
        _save(base_pack, werte)
    return werte


def target_for(levels: Dict[int, float], sound_id: int) -> float:
    """Zielwert für eine Ansage: die Lautheit des Originals.

    Gibt es kein Original (oder gar keine Messung), wird der allgemeine
    Zielwert genommen. Ausreißer werden begrenzt, damit ein einzelner
    Messfehler keine schreiend laute Ansage erzeugt.
    """
    wert = levels.get(int(sound_id))
    if wert is None:
        if not levels:
            return TARGET_LUFS
        sortiert = sorted(levels.values())
        wert = sortiert[len(sortiert) // 2]
    return max(-24.0, min(-12.0, float(wert)))
