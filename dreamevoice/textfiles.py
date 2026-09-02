"""Dialekttexte als einfache Textdateien aus- und wieder einlesen.

Der Zweck: 593 Ansagen einzeln im Fenster durchzugehen ist Arbeit für
einen Abend. Als Datei lässt sich der ganze Satz auf einmal kopieren,
einer Sprach-KI zum Überarbeiten geben und das Ergebnis in einem Rutsch
zurückspielen.

Das Format ist absichtlich stur einfach, damit es diese Runde übersteht:

    Nummer | Bedeutung auf Hochdeutsch | Dialekttext

Beim Einlesen zählt nur die Nummer und alles hinter dem **zweiten**
senkrechten Strich. Die mittlere Spalte darf sich also ändern, ohne dass
etwas kaputtgeht - und ein `|` im Dialekttext stört auch nicht. Zeilen
mit `#`, Leerzeilen und alles, was nicht mit einer Zahl beginnt, werden
überlesen. Fehlende Zeilen bleiben einfach, wie sie waren; eine KI darf
also auch nur einen Ausschnitt zurückgeben.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .dialect import DIALECTS, DialectPack, with_overrides
from .paths import data_dir
from .sounds import SoundCatalog

_LOG = logging.getLogger(__name__)

TRENNER = "|"
ORDNER = "Dialekttexte"
ENDUNG = ".txt"


def folder() -> Path:
    d = data_dir() / ORDNER
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_for(key: str) -> Path:
    return folder() / f"{key}{ENDUNG}"


# --------------------------------------------------------------------------
# Schreiben
# --------------------------------------------------------------------------

KOPF = """\
# {name} - Sprachpaket für Dreame-, MOVA- und Trouver-Saugroboter
# {anzahl} Ansagen.
#
# Die Nummern gelten für alle Modelle: Dreame nutzt eine gemeinsame
# Nummerierung, nachgeprüft an acht fremden Modellen. Ansagen, die dein
# Roboter nicht kennt, übergeht die App beim Bauen.
#
# So arbeitest du damit:
#   1. Diese Datei komplett kopieren und einer Sprach-KI geben. Ein
#      Auftrag, der sich bewährt hat:
#
#        "Unten stehen die Ansagen eines Saugroboters auf {name}.
#         Bitte überarbeite ausschließlich die dritte Spalte, damit sie
#         natürlich und einheitlich klingt. Nummer und Bedeutung
#         unverändert lassen, den Aufbau der Zeilen beibehalten und alle
#         Zeilen zurückgeben. Die Sätze bleiben kurz und werden
#         gesprochen, nicht gelesen."
#
#   2. Die Antwort hier wieder einfügen und die Datei speichern.
#   3. In der App auf "Texte aus Datei einlesen" klicken.
#
# Aufbau je Zeile:   Nummer | Bedeutung auf Hochdeutsch | Dialekttext
#
# Beim Einlesen zählt die Nummer und alles hinter dem zweiten
# senkrechten Strich. Zeilen mit # und Leerzeilen werden überlesen.
# Zeilen, die du löschst, bleiben unverändert - du kannst also auch
# nur einen Teil überarbeiten lassen.
#
# Halte die Sätze kurz. Die Originalansagen sind zwei bis sechs
# Sekunden lang; alles Längere wirkt am Roboter geschwätzig.
"""

ABSCHNITT_ANSAGEN = """
# ---------------------------------------------------------------------
# Ansagen
# ---------------------------------------------------------------------
"""

ABSCHNITT_SCHEMA = """
# ---------------------------------------------------------------------
# Schematische Ansagen
#
# Diese entstehen aus zwei Satzmustern (Akkustand in Prozent,
# Bestätigung je Zimmer) und unterscheiden sich nur in einem Wort. Für
# eine sprachliche Überarbeitung sind sie meist uninteressant - dann
# diesen Abschnitt einfach stehen lassen oder löschen.
# ---------------------------------------------------------------------
"""


def _schema_ids(pack: DialectPack) -> set:
    """Die Nummern, die aus den beiden Satzmustern entstehen."""
    try:
        from .dialects import muster
        modul = _modul_fuer(pack.key)
        if modul is None:
            return set()
        return set(muster.erzeuge(modul.AKKU_MUSTER, modul.RAUM_MUSTER,
                                  modul.RAUM_NAMEN))
    except Exception as exc:                       # pragma: no cover
        _LOG.warning("Satzmuster für %s nicht lesbar: %s", pack.key, exc)
        return set()


def _modul_fuer(key: str):
    from . import dialects
    for modul in dialects.MODULES:
        if getattr(modul, "KEY", "") == key:
            return modul
    return None


def write_one(pack: DialectPack,
              overrides: Optional[Dict[int, str]] = None,
              catalog: Optional[SoundCatalog] = None) -> Path:
    """Schreibt einen Dialekt als Textdatei. Rückgabe: der Pfad."""
    aktuell = with_overrides(pack, overrides or {})
    catalog = catalog or SoundCatalog.load()
    schema = _schema_ids(pack)

    zeilen: List[str] = [KOPF.format(name=pack.name, anzahl=aktuell.count)]

    def block(ids: List[int]) -> List[str]:
        raus = []
        for sound_id in ids:
            eintrag = catalog.get(sound_id)
            bedeutung = ""
            if eintrag is not None:
                bedeutung = eintrag.de or eintrag.en or ""
            bedeutung = bedeutung.replace(TRENNER, "/").strip() or "-"
            text = aktuell.texts.get(sound_id, "")
            raus.append(f"{sound_id:>4} {TRENNER} {bedeutung} {TRENNER} {text}")
        return raus

    normal = sorted(i for i in aktuell.texts if i not in schema)
    schematisch = sorted(i for i in aktuell.texts if i in schema)

    zeilen.append(ABSCHNITT_ANSAGEN)
    zeilen.extend(block(normal))
    if schematisch:
        zeilen.append(ABSCHNITT_SCHEMA)
        zeilen.extend(block(schematisch))

    ziel = file_for(pack.key)
    ziel.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return ziel


def all_packs() -> List[DialectPack]:
    """Mitgelieferte Dialekte und selbst angelegte Pakete."""
    from . import custom
    try:
        return list(DIALECTS) + custom.list_packs()
    except OSError:
        return list(DIALECTS)


def write_all(overrides_for=None,
              catalog: Optional[SoundCatalog] = None,
              packs: Optional[List[DialectPack]] = None) -> List[Path]:
    """Schreibt alle Pakete. `overrides_for(key)` liefert eigene Texte."""
    catalog = catalog or SoundCatalog.load()
    pfade = []
    for pack in (packs if packs is not None else all_packs()):
        eigene = overrides_for(pack.key) if overrides_for else {}
        pfade.append(write_one(pack, eigene, catalog))
    return pfade


def ensure_files(overrides_for=None) -> List[Path]:
    """Legt fehlende Dateien an, lässt vorhandene unangetastet.

    Damit sind die Listen nach dem ersten Start einfach da, ohne dass
    eine spätere eigene Überarbeitung überschrieben wird.
    """
    fehlend = [p for p in all_packs() if not file_for(p.key).is_file()]
    if not fehlend:
        return []
    catalog = SoundCatalog.load()
    pfade = []
    for pack in fehlend:
        eigene = overrides_for(pack.key) if overrides_for else {}
        pfade.append(write_one(pack, eigene, catalog))
    return pfade


# --------------------------------------------------------------------------
# Lesen
# --------------------------------------------------------------------------

@dataclass
class ReadResult:
    """Was beim Einlesen herauskam."""

    overrides: Dict[int, str] = field(default_factory=dict)
    gelesen: int = 0
    unveraendert: int = 0
    leer: int = 0
    unbekannt: List[int] = field(default_factory=list)
    unlesbar: List[int] = field(default_factory=list)

    @property
    def geaendert(self) -> int:
        return len(self.overrides)

    def summary(self) -> str:
        teile = [f"{self.gelesen} Zeilen gelesen",
                 f"{self.geaendert} Texte weichen vom mitgelieferten ab"]
        if self.unveraendert:
            teile.append(f"{self.unveraendert} unverändert")
        if self.leer:
            teile.append(f"{self.leer} ohne Text übersprungen")
        if self.unbekannt:
            teile.append(f"{len(self.unbekannt)} unbekannte Nummern")
        return ", ".join(teile) + "."


def read_one(path: Path, pack: DialectPack) -> ReadResult:
    """Liest eine Textdatei und gibt die Abweichungen zurück.

    Zurück kommen nur Texte, die sich vom mitgelieferten unterscheiden -
    genau das, was die App als eigene Fassung speichert.
    """
    ergebnis = ReadResult()
    roh = Path(path).read_text(encoding="utf-8-sig")

    for zeile in roh.splitlines():
        blank = zeile.strip()
        if not blank or blank.startswith("#"):
            continue

        teile = blank.split(TRENNER, 2)
        nummer_roh = teile[0].strip()
        if not nummer_roh.lstrip("-").isdigit():
            continue

        sound_id = int(nummer_roh)
        ergebnis.gelesen += 1

        if len(teile) >= 3:
            text = teile[2].strip()
        elif len(teile) == 2:
            # Jemand hat die mittlere Spalte entfernt - dann ist der Rest
            # der Dialekttext.
            text = teile[1].strip()
        else:
            ergebnis.unlesbar.append(sound_id)
            continue

        if sound_id not in pack.texts:
            ergebnis.unbekannt.append(sound_id)
            continue

        if not text:
            ergebnis.leer += 1
            continue

        if text == pack.texts[sound_id]:
            ergebnis.unveraendert += 1
            continue

        ergebnis.overrides[sound_id] = text

    return ergebnis


def read_for_key(key: str) -> Optional[ReadResult]:
    """Bequemer Weg: Datei zum Paketschlüssel einlesen."""
    pack = next((p for p in all_packs() if p.key == key), None)
    if pack is None:
        return None
    pfad = file_for(key)
    if not pfad.is_file():
        return None
    return read_one(pfad, pack)
