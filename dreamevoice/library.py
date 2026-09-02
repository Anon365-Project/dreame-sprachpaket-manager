"""Die Sammlung der selbst gebauten Sprachpakete.

Der Anlass: bis hierher hieß jedes Dialektpaket schlicht
`dialekt_bayerisch.tar.gz`. Wer ein Paket mit seiner bezahlten
ElevenLabs-Stimme gebaut hatte und danach dasselbe Dialektpaket zum
Ausprobieren mit einer Windows-Stimme erzeugte, hatte das erste
**überschrieben** - Kontingent verbraucht, Ergebnis weg.

Deshalb bekommt jedes Paket einen Namen, der Dialekt *und* Stimme nennt,
und daneben eine kleine Beschreibungsdatei. So liegen beliebig viele
Fassungen desselben Dialekts nebeneinander, und beim Installieren ist
erkennbar, welche welche ist.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .paths import build_dir

_LOG = logging.getLogger(__name__)

BESCHREIBUNG_SUFFIX = ".info.json"

# Was in einem Dateinamen nichts zu suchen hat.
_UNZULAESSIG = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MEHRFACH = re.compile(r"[_\s]+")

MAX_NAME = 80


def safe_name(text: str) -> str:
    """Macht aus einer Beschriftung einen brauchbaren Dateinamen."""
    ersetzt = {
        "ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
        "ß": "ss", "é": "e", "è": "e", "á": "a", "à": "a", "·": "-",
    }
    for alt, neu in ersetzt.items():
        text = text.replace(alt, neu)
    text = _UNZULAESSIG.sub(" ", text)
    text = _MEHRFACH.sub("_", text.strip())
    text = text.strip("._-")
    return text[:MAX_NAME] or "sprachpaket"


def suggest_name(dialect_name: str, engine: str, voice_label: str = "") -> str:
    """Vorschlag für den Paketnamen: Dialekt und Stimme.

    Beispiele:
        dialekt_Bayerisch_ElevenLabs_Bairischer_Bua
        dialekt_Wienerisch_Windows_Microsoft_Stefan
    """
    dienst = "ElevenLabs" if "eleven" in (engine or "").lower() else "Windows"
    stimme = (voice_label or "").strip()
    # Klammerzusätze wie "(de · selbst erzeugt)" machen den Namen unnötig lang.
    stimme = stimme.split("(")[0].strip()
    teile = ["dialekt", dialect_name, dienst]
    if stimme:
        teile.append(stimme)
    return safe_name("_".join(teile))


def existing_pack(folder: Path, name: str,
                  suffix: str = ".tar.gz") -> Optional[Path]:
    """Ein schon vorhandenes Paket dieses Namens - oder None.

    Damit kann die Oberfläche fragen, statt stillschweigend eine zweite
    Fassung danebenzulegen. Ersetzen ist erlaubt, aber nie die Vorgabe.
    """
    ziel = Path(folder) / f"{name}{suffix}"
    return ziel if ziel.exists() else None


def unique_path(folder: Path, name: str, suffix: str = ".tar.gz") -> Path:
    """Ein Pfad, der noch nicht belegt ist - notfalls mit Zähler."""
    folder = Path(folder)
    ziel = folder / f"{name}{suffix}"
    if not ziel.exists():
        return ziel
    for nummer in range(2, 100):
        ziel = folder / f"{name}_{nummer}{suffix}"
        if not ziel.exists():
            return ziel
    return folder / f"{name}_{int(time.time())}{suffix}"


# --------------------------------------------------------------------------
# Beschreibung neben dem Paket
# --------------------------------------------------------------------------

@dataclass
class PackInfo:
    """Was über ein gebautes Paket bekannt ist."""

    path: Path
    dialect: str = ""
    engine: str = ""
    voice: str = ""
    lang_id: str = ""
    replaced: int = 0
    total: int = 0
    created: str = ""

    @property
    def size_mb(self) -> float:
        try:
            return self.path.stat().st_size / (1024 * 1024)
        except OSError:
            return 0.0

    @property
    def label(self) -> str:
        """Eine Zeile, die das Paket eindeutig beschreibt."""
        teile = [self.dialect or self.path.stem]
        if self.voice:
            teile.append(self.voice)
        elif self.engine:
            teile.append(self.engine)
        kopf = " · ".join(teile)
        anhang = []
        if self.replaced:
            anhang.append(f"{self.replaced} Ansagen")
        anhang.append(f"{self.size_mb:.1f} MB")
        if self.created:
            anhang.append(self.created[:10])
        return f"{kopf}  ({', '.join(anhang)})"


def info_path(pack_path: Path) -> Path:
    p = Path(pack_path)
    return p.with_name(p.name + BESCHREIBUNG_SUFFIX)


def write_info(pack_path: Path, **felder) -> Optional[Path]:
    """Legt die Beschreibung neben das Paket. Fehler sind nicht schlimm."""
    daten = {"created": time.strftime("%Y-%m-%d %H:%M")}
    daten.update({k: v for k, v in felder.items() if v not in (None, "")})
    ziel = info_path(pack_path)
    try:
        ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        return ziel
    except OSError as exc:
        _LOG.warning("Beschreibung nicht geschrieben: %s", exc)
        return None


def read_info(pack_path: Path) -> PackInfo:
    pack_path = Path(pack_path)
    info = PackInfo(path=pack_path)
    quelle = info_path(pack_path)
    if not quelle.is_file():
        return info
    try:
        roh = json.loads(quelle.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return info
    if not isinstance(roh, dict):
        return info
    for feld in ("dialect", "engine", "voice", "lang_id", "created"):
        wert = roh.get(feld)
        if isinstance(wert, str):
            setattr(info, feld, wert)
    for feld in ("replaced", "total"):
        try:
            setattr(info, feld, int(roh.get(feld, 0)))
        except (TypeError, ValueError):
            pass
    return info


def list_packs(folder: Optional[Path] = None) -> List[PackInfo]:
    """Alle gebauten Pakete, neueste zuerst."""
    folder = Path(folder) if folder else build_dir()
    if not folder.is_dir():
        return []
    treffer = []
    for pfad in folder.glob("*.tar.gz"):
        if pfad.name.endswith(".part"):
            continue
        treffer.append(read_info(pfad))
    treffer.sort(key=lambda i: i.path.stat().st_mtime if i.path.exists() else 0,
                 reverse=True)
    return treffer
