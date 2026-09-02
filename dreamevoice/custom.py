"""Eigene Sprachpakete - alles, was kein mitgelieferter Dialekt ist.

Die sieben Dialekte stecken fest im Programm. Wer aber ein Paket im Stil
einer bestimmten Figur bauen will - "Bruce Willis", "Pirat", "Butler" -,
braucht eine eigene Textsammlung, die sich anlegen, benennen und ändern
lässt.

Technisch ist ein eigenes Paket dasselbe wie ein Dialekt: ein
`DialectPack` mit Schlüssel, Name und einem Wörterbuch aus Ansage-Nummer
und Text. Dadurch funktioniert die ganze bestehende Maschinerie
unverändert - Kostprobe, Texteditor, Textdatei-Austausch, Erzeugen,
Fortsetzen nach aufgebrauchtem Kontingent.

Gespeichert wird je Paket eine JSON-Datei im Datenordner. Damit überlebt
alles einen Neustart und lässt sich weitergeben.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from .dialect import DialectPack
from .paths import data_dir

_LOG = logging.getLogger(__name__)

ORDNER = "Eigene Pakete"
ENDUNG = ".json"
FORMAT = 1

# Kennungen wie DE oder BAYERN. Der Roboter bekommt sie als Sprachkennung;
# vier bis acht Großbuchstaben haben sich bewährt.
_KENNUNG_ERLAUBT = re.compile(r"[^A-Z0-9]")


def folder() -> Path:
    d = data_dir() / ORDNER
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_key(name: str) -> str:
    """Dateiname aus dem Anzeigenamen - klein, ohne Sonderzeichen."""
    text = name.lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    # Apostrophe fallen ersatzlos weg, sonst wird aus "Käpt'n" ein
    # "kaept_n" mit Unterstrich mitten im Wort.
    text = re.sub(r"['’`]", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text[:40] or "eigenes"


def make_lang_id(name: str, vergeben: Optional[List[str]] = None) -> str:
    """Sprachkennung für den Roboter, z. B. "BRUCE".

    Sie darf nicht mit einer offiziellen Kennung kollidieren, sonst
    überschreibt das eigene Paket eine mitgelieferte Sprache.
    """
    roh = _KENNUNG_ERLAUBT.sub("", name.upper())
    kennung = (roh[:8] or "EIGEN")
    belegt = {k.upper() for k in (vergeben or [])}
    # Die offiziellen Kennungen von Dreame sind kurz; sicherheitshalber
    # bleiben wir von den gängigen weg.
    belegt |= {"DE", "EN", "ZH", "RU", "FR", "IT", "JA", "KO", "ES", "PL",
               "TR", "SV", "DA", "NB", "PT", "UK", "HE", "VI", "TH", "THA",
               "NL", "FI", "ID", "DK"}
    if kennung not in belegt:
        return kennung
    for nummer in range(2, 100):
        kandidat = f"{kennung[:7]}{nummer}"
        if kandidat not in belegt:
            return kandidat
    return f"EIGEN{int(time.time()) % 1000}"


def path_for(key: str) -> Path:
    return folder() / f"{key}{ENDUNG}"


# --------------------------------------------------------------------------
# Lesen und Schreiben
# --------------------------------------------------------------------------

def save(pack: DialectPack) -> Path:
    """Legt ein eigenes Paket im Datenordner ab."""
    ziel = path_for(pack.key)
    daten = {
        "format": FORMAT,
        "key": pack.key,
        "name": pack.name,
        "description": pack.description,
        "lang_id": pack.lang_id,
        "rate": pack.rate,
        "pitch": pack.pitch,
        "changed": time.strftime("%Y-%m-%d %H:%M"),
        "texts": {str(i): t for i, t in sorted(pack.texts.items())},
    }
    ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return ziel


def load(path: Path) -> Optional[DialectPack]:
    try:
        roh = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        _LOG.warning("Eigenes Paket nicht lesbar (%s): %s", path, exc)
        return None
    if not isinstance(roh, dict) or not roh.get("key"):
        return None

    texte: Dict[int, str] = {}
    for schluessel, wert in (roh.get("texts") or {}).items():
        try:
            nummer = int(schluessel)
        except (TypeError, ValueError):
            continue
        if isinstance(wert, str) and wert.strip():
            texte[nummer] = wert.strip()

    try:
        return DialectPack(
            key=str(roh["key"]),
            name=str(roh.get("name") or roh["key"]),
            description=str(roh.get("description") or ""),
            lang_id=str(roh.get("lang_id") or "EIGEN"),
            texts=texte,
            rate=int(roh.get("rate") or 0),
            pitch=int(roh.get("pitch") or 0),
        )
    except (KeyError, TypeError, ValueError) as exc:
        _LOG.warning("Eigenes Paket unvollständig (%s): %s", path, exc)
        return None


def list_packs() -> List[DialectPack]:
    """Alle eigenen Pakete, nach Namen sortiert."""
    treffer = []
    for pfad in sorted(folder().glob(f"*{ENDUNG}")):
        pack = load(pfad)
        if pack is not None:
            treffer.append(pack)
    treffer.sort(key=lambda p: p.name.lower())
    return treffer


def delete(key: str) -> bool:
    try:
        path_for(key).unlink()
        return True
    except OSError:
        return False


def exists(key: str) -> bool:
    return path_for(key).is_file()


# --------------------------------------------------------------------------
# Anlegen
# --------------------------------------------------------------------------

def create(name: str, texts: Optional[Dict[int, str]] = None,
           description: str = "", vergeben: Optional[List[str]] = None
           ) -> DialectPack:
    """Baut ein neues eigenes Paket - noch nicht gespeichert.

    `texts` ist üblicherweise die Kopie eines vorhandenen Pakets: dann hat
    der Nutzer alle Ansagen als Vorlage vor sich und schreibt sie um,
    statt bei Null anzufangen.
    """
    key = make_key(name)
    # Nicht versehentlich ein vorhandenes eigenes Paket überschreiben.
    if exists(key):
        for nummer in range(2, 100):
            if not exists(f"{key}_{nummer}"):
                key = f"{key}_{nummer}"
                break
    return DialectPack(
        key=key,
        name=name.strip() or key,
        description=description or "Eigenes Sprachpaket.",
        lang_id=make_lang_id(name, vergeben),
        texts=dict(texts or {}),
    )


def rename(pack: DialectPack, neuer_name: str) -> DialectPack:
    """Benennt ein eigenes Paket um. Der Schlüssel bleibt, damit die
    gesprochenen Aufnahmen weiter gefunden werden."""
    pack.name = neuer_name.strip() or pack.name
    return pack
