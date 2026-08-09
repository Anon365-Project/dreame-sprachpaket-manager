"""Ganze Ordner oder Archive auf einmal übernehmen.

Ansagen einzeln zuzuweisen ist bei 239 Stück keine Freude. Wer seine
Dateien ohnehin schon vorliegen hat - selbst aufgenommen, mit einer
Sprachsynthese erzeugt oder aus einem fremden Paket entnommen - soll sie
in einem Rutsch übernehmen können.

Die Zuordnung läuft über den Dateinamen: **die Zahl im Namen ist die
Ansage-Nummer**. `7.ogg`, `007.wav`, `7 - Reinigung gestartet.mp3` und
`Ansage_7.ogg` landen alle bei Ansage 7. Ein Name ohne Zahl wird
übersprungen, damit nichts an der falschen Stelle landet.

Damit man weiss, wie zu benennen ist, kann die App einen Vorlagenordner
anlegen: darin liegt jede Originalansage bereits richtig benannt. Man
hört sie an, spricht sie unter demselben Namen neu ein - fertig.
"""

from __future__ import annotations

import logging
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from .audio import SUPPORTED_INPUT
from .errors import PackError
from .sounds import SoundCatalog

_LOG = logging.getLogger(__name__)

LogFn = Callable[[str], None]

# Zahl irgendwo im Dateinamen - die erste zusammenhängende Ziffernfolge.
_ZAHL = re.compile(r"(\d+)")


@dataclass
class ImportResult:
    """Was ein Import ergeben hat."""

    assigned: Dict[int, Path] = field(default_factory=dict)
    unknown_ids: List[int] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    source: str = ""

    @property
    def count(self) -> int:
        return len(self.assigned)

    def summary(self) -> str:
        teile = [f"{self.count} Ansagen übernommen"]
        if self.unknown_ids:
            teile.append(f"{len(self.unknown_ids)} Nummern kennt dein Modell nicht")
        if self.skipped:
            teile.append(f"{len(self.skipped)} Dateien übersprungen")
        return ", ".join(teile)


def sound_id_from_name(name: str) -> Optional[int]:
    """Liest die Ansage-Nummer aus einem Dateinamen."""
    stamm = Path(name).stem
    treffer = _ZAHL.search(stamm)
    if not treffer:
        return None
    try:
        return int(treffer.group(1))
    except ValueError:
        return None


def scan_folder(folder: Path, known_ids: Optional[Iterable[int]] = None,
                log: Optional[LogFn] = None) -> ImportResult:
    """Durchsucht einen Ordner nach Audiodateien mit Nummern im Namen."""
    folder = Path(folder)
    if not folder.is_dir():
        raise PackError(f"Das ist kein Ordner:\n{folder}")

    bekannt = set(known_ids) if known_ids is not None else None
    ergebnis = ImportResult(source=str(folder))

    # Unterordner werden mitgenommen, aber flach ausgewertet.
    dateien = sorted(p for p in folder.rglob("*") if p.is_file())

    for pfad in dateien:
        if pfad.suffix.lower() not in SUPPORTED_INPUT:
            ergebnis.skipped.append(f"{pfad.name} (kein bekanntes Audioformat)")
            continue

        sound_id = sound_id_from_name(pfad.name)
        if sound_id is None:
            ergebnis.skipped.append(f"{pfad.name} (keine Nummer im Namen)")
            continue

        if bekannt is not None and sound_id not in bekannt:
            ergebnis.unknown_ids.append(sound_id)
            continue

        # Bei doppelten Nummern gewinnt die erste Datei - sonst haengt das
        # Ergebnis von der Sortierung des Dateisystems ab.
        if sound_id not in ergebnis.assigned:
            ergebnis.assigned[sound_id] = pfad

    if log:
        log(ergebnis.summary())
    return ergebnis


def extract_archive(archive: Path, target: Path,
                    log: Optional[LogFn] = None) -> Path:
    """Packt ein tar.gz- oder zip-Archiv in einen Ordner aus.

    Es werden nur Audiodateien entnommen, und zwar ausschliesslich anhand
    ihres Dateinamens ohne die Pfade aus dem Archiv - ein manipuliertes
    Archiv kann so nichts an anderer Stelle ablegen.
    """
    archive = Path(archive)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)

    def behalten(roh: str) -> Optional[str]:
        name = Path(roh.replace("\\", "/")).name
        if not name or name.startswith("."):
            return None
        return name if Path(name).suffix.lower() in SUPPORTED_INPUT else None

    anzahl = 0
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = behalten(info.filename)
                if name:
                    (target / name).write_bytes(zf.read(info))
                    anzahl += 1
    else:
        try:
            with tarfile.open(archive, "r:*") as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    name = behalten(member.name)
                    if name:
                        quelle = tf.extractfile(member)
                        if quelle is not None:
                            (target / name).write_bytes(quelle.read())
                            anzahl += 1
        except tarfile.TarError as exc:
            raise PackError(
                "Das Archiv liess sich nicht lesen.",
                f"Erwartet wird ein tar.gz- oder zip-Archiv. "
                f"Technische Details: {exc}") from exc

    if anzahl == 0:
        raise PackError(
            "In dem Archiv waren keine Audiodateien.",
            "Erwartet werden Dateien wie 7.ogg oder 12.wav.")

    if log:
        log(f"{anzahl} Dateien aus {archive.name} entpackt.")
    return target


def import_archive(archive: Path, work_dir: Path,
                   known_ids: Optional[Iterable[int]] = None,
                   log: Optional[LogFn] = None) -> ImportResult:
    """Archiv auspacken und gleich zuordnen."""
    ziel = Path(work_dir) / Path(archive).stem.replace(".tar", "")
    extract_archive(archive, ziel, log=log)
    ergebnis = scan_folder(ziel, known_ids, log=log)
    ergebnis.source = str(archive)
    return ergebnis


def create_template_folder(previews: Dict[int, Path],
                           catalog: SoundCatalog,
                           target: Path,
                           only_ids: Optional[Iterable[int]] = None,
                           log: Optional[LogFn] = None) -> Path:
    """Legt einen Ordner mit allen Originalansagen an - richtig benannt.

    Der bequemste Weg zu einem eigenen Paket: Ordner anlegen lassen, jede
    Datei anhören, sie unter demselben Namen neu einsprechen, danach den
    Ordner mit einem Klick importieren.
    """
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)

    ids = sorted(set(only_ids) & set(previews)) if only_ids is not None \
        else sorted(previews)
    if not ids:
        raise PackError(
            "Es stehen keine Originalansagen bereit.",
            "Lade in Tab 2 zuerst das Originalpaket deines Roboters herunter.")

    zeilen = [
        "So baust du dein eigenes Sprachpaket",
        "=" * 38,
        "",
        "In diesem Ordner liegt jede Ansage deines Roboters - bereits richtig",
        "benannt. Die Zahl im Dateinamen ist die Ansage-Nummer.",
        "",
        "1. Datei anhoeren, damit du weisst, was gesagt wird.",
        "2. Eigene Aufnahme unter GENAU DEMSELBEN NAMEN speichern.",
        "   (mp3, wav, m4a und flac gehen auch - die App wandelt um.)",
        "3. Was du nicht ersetzt, einfach liegen lassen: diese Ansagen",
        "   bleiben auf der deutschen Originalstimme.",
        "4. In der App auf 'Ganzen Ordner importieren' klicken und diesen",
        "   Ordner auswaehlen.",
        "",
        "Halte die Aufnahmen kurz - die Originale sind zwei bis sechs Sekunden.",
        "",
        "-" * 38,
        "",
    ]

    kopiert = 0
    for sound_id in ids:
        quelle = previews[sound_id]
        ziel = target / f"{sound_id}.ogg"
        if not ziel.exists():
            shutil.copy2(quelle, ziel)
        kopiert += 1

        eintrag = catalog.get(sound_id)
        beschreibung = eintrag.title if eintrag else "(unbekannt)"
        zeilen.append(f"{sound_id}.ogg  =  {beschreibung}")

    (target / "_Anleitung.txt").write_text("\n".join(zeilen) + "\n",
                                           encoding="utf-8")

    if log:
        log(f"{kopiert} Originalansagen nach {target} kopiert.")
    return target


def suggested_filename(sound_id: int, suffix: str = ".ogg") -> str:
    """Der Dateiname, den die App für eine Ansage erwartet."""
    return f"{sound_id}{suffix}"
