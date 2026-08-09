"""Zugriff auf die offiziellen Dreame-Sprachpakete.

Dreame veröffentlicht für jedes Modell eine Liste seiner Sprachpakete
inklusive Größe und MD5-Prüfsumme:

    https://awsde0.fds.api.xiaomi.com/dreame-product/<modell>/voices/soundpackage.json

Diese Datei ist aus zwei Gründen zentral für die App:

1. Sie liefert das **Originalpaket des eigenen Modells**. Ein eigenes
   Sprachpaket wird nicht von Null gebaut, sondern als Kopie des Originals
   mit ausgetauschten Audiodateien. Dadurch bleiben alle Steuerdateien
   (voice_mapping.json, dmr_audio.json, mini_broad.json, first_audio.json,
   tts.json) unverändert erhalten und der Roboter findet weiterhin jede
   Ansage, die man nicht selbst ersetzt hat.

2. Sie ist der **Rückweg**. Zum Wiederherstellen wird schlicht das
   offizielle Paket mit Dreames eigener URL, Größe und Prüfsumme
   installiert - also exakt das, was die Dreamehome-App auch tut.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tarfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from .errors import NetworkError, PackError
from .paths import cache_dir

_LOG = logging.getLogger(__name__)

CATALOG_URL = ("https://awsde0.fds.api.xiaomi.com/dreame-product/"
               "{model}/voices/soundpackage.json")

# Dateien im Paket, die keine Audiodaten sind, sondern Steuerinformationen.
METADATA_FILES = {
    "voice_mapping.json", "tts.json", "dmr_audio.json",
    "first_audio.json", "mini_broad.json", "time.txt",
}

ProgressFn = Callable[[int, int], None]


class VoicePackInfo:
    """Ein offizielles Sprachpaket laut Dreame-Katalog."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.raw = raw
        self.id: str = raw.get("id", "")
        self.size: int = int(raw.get("size", 0) or 0)
        self.md5: str = (raw.get("md5sum", "") or "").lower()
        self.url: str = raw.get("download", "")
        self.preview_url: str = raw.get("listen", "")
        name = raw.get("name") or {}
        self.name: str = name.get("default") or self.id

    @property
    def label(self) -> str:
        return f"{self.name} ({self.id})"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VoicePackInfo {self.id} {self.size}B>"


def fetch_catalog(model: str, timeout: int = 20) -> List[VoicePackInfo]:
    """Lädt die Sprachpaketliste für ein Modell (z. B. dreame.vacuum.r2532h)."""
    if not model:
        raise PackError("Es ist kein Robotermodell bekannt.",
                        "Melde dich zuerst im Tab 'Verbindung' an.")
    url = CATALOG_URL.format(model=model)
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        raise NetworkError("Die Sprachpaketliste von Dreame ist nicht erreichbar.",
                           f"Technische Details: {exc}") from exc

    if resp.status_code == 404:
        raise PackError(
            f"Für das Modell {model} bietet Dreame keine Sprachpaketliste an.",
            "Das Modell ist entweder sehr neu oder wird über einen anderen "
            "Kanal versorgt. Ohne Originalpaket kann kein sicheres eigenes "
            "Paket gebaut werden.",
        )
    if resp.status_code != 200:
        raise NetworkError(f"Dreame antwortete mit HTTP {resp.status_code}.")

    try:
        data = resp.json()
    except ValueError as exc:
        raise PackError("Die Sprachpaketliste war unlesbar.") from exc

    voices = ((data.get("data") or {}).get("voices")) or []
    packs = [VoicePackInfo(v) for v in voices if v.get("download")]
    if not packs:
        raise PackError(f"Dreame listet für {model} keine Sprachpakete auf.")
    return packs


def find_pack(packs: List[VoicePackInfo], lang_id: str) -> Optional[VoicePackInfo]:
    for p in packs:
        if p.id.upper() == (lang_id or "").upper():
            return p
    return None


def md5_of_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def download_pack(pack: VoicePackInfo, model: str,
                  progress: Optional[ProgressFn] = None,
                  force: bool = False) -> Path:
    """Lädt ein offizielles Paket in den Zwischenspeicher und prüft es.

    Ein bereits vorhandenes Paket mit passender Prüfsumme wird
    wiederverwendet.
    """
    target = cache_dir() / f"{model}_{pack.id}.tar.gz"

    if target.exists() and not force:
        if pack.md5 and md5_of_file(target) == pack.md5:
            _LOG.info("Originalpaket %s aus dem Zwischenspeicher", pack.id)
            if progress:
                progress(pack.size, pack.size)
            return target
        target.unlink(missing_ok=True)

    tmp = target.with_suffix(".part")
    try:
        with requests.get(pack.url, stream=True, timeout=60) as resp:
            if resp.status_code != 200:
                raise NetworkError(
                    f"Das Originalpaket konnte nicht geladen werden "
                    f"(HTTP {resp.status_code}).")
            total = int(resp.headers.get("Content-Length") or pack.size or 0)
            done = 0
            with tmp.open("wb") as fh:
                for block in resp.iter_content(chunk_size=1 << 16):
                    if not block:
                        continue
                    fh.write(block)
                    done += len(block)
                    if progress:
                        progress(done, total)
    except requests.exceptions.RequestException as exc:
        tmp.unlink(missing_ok=True)
        raise NetworkError("Der Download des Originalpakets ist abgebrochen.",
                           f"Technische Details: {exc}") from exc

    actual = md5_of_file(tmp)
    if pack.md5 and actual != pack.md5:
        tmp.unlink(missing_ok=True)
        raise PackError(
            "Das heruntergeladene Originalpaket ist beschädigt.",
            f"Erwartete Prüfsumme {pack.md5}, tatsächlich {actual}. "
            "Bitte erneut versuchen.",
        )

    tmp.replace(target)
    _LOG.info("Originalpaket %s geladen (%d Bytes)", pack.id, target.stat().st_size)
    return target


def list_sound_ids(pack_path: Path) -> List[int]:
    """Alle Ansage-Nummern, die ein Paket enthält."""
    ids: List[int] = []
    with tarfile.open(pack_path, "r:gz") as tf:
        for member in tf.getmembers():
            name = member.name.rsplit("/", 1)[-1]
            if name.endswith(".ogg") and name[:-4].isdigit():
                ids.append(int(name[:-4]))
    return sorted(ids)


def extract_previews(pack_path: Path, dest: Path,
                     progress: Optional[ProgressFn] = None) -> Dict[int, Path]:
    """Entpackt die Original-Ogg-Dateien zum Anhören.

    Es werden nur reguläre Dateien mit reinem Zahlennamen entpackt -
    damit kann ein manipuliertes Archiv nicht außerhalb des Zielordners
    schreiben.
    """
    dest.mkdir(parents=True, exist_ok=True)
    result: Dict[int, Path] = {}

    with tarfile.open(pack_path, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        total = len(members)
        for index, member in enumerate(members, 1):
            name = member.name.rsplit("/", 1)[-1]
            if not (name.endswith(".ogg") and name[:-4].isdigit()):
                continue
            out = dest / name
            if not out.exists() or out.stat().st_size != member.size:
                src = tf.extractfile(member)
                if src is None:
                    continue
                out.write_bytes(src.read())
            result[int(name[:-4])] = out
            if progress:
                progress(index, total)
    return result


def read_metadata(pack_path: Path) -> Dict[str, bytes]:
    """Liefert die Steuerdateien eines Pakets (für Diagnose/Anzeige)."""
    out: Dict[str, bytes] = {}
    with tarfile.open(pack_path, "r:gz") as tf:
        for member in tf.getmembers():
            name = member.name.rsplit("/", 1)[-1]
            if name in METADATA_FILES and member.isfile():
                src = tf.extractfile(member)
                if src is not None:
                    out[name] = src.read()
    return out


def read_voice_mapping(pack_path: Path, model: str) -> Dict[int, int]:
    """Liest die Nummern-Umsetzung, die für ein Modell gilt.

    Warum das wichtig ist: Dreame hat für neuere Geräte einzelne Ansagen
    neu aufgenommen und unter einer anderen Nummer abgelegt. Die Datei
    `voice_mapping.json` hält fest, welche Nummer bei welchem Modell an
    die Stelle einer anderen tritt.

    Beim X50 Ultra Complete etwa greift der Roboter für Ansage 18
    ("Lädt") in Wirklichkeit zu `856.ogg`. Wer nur `18.ogg` austauscht,
    hört weiterhin die Originalstimme - der Austausch läuft ins Leere.

    Rückgabe: {Quellnummer: Zielnummer}
    """
    if not model:
        return {}

    try:
        with tarfile.open(pack_path, "r:gz") as tf:
            eintrag = None
            for member in tf.getmembers():
                if member.name.rsplit("/", 1)[-1] == "voice_mapping.json":
                    eintrag = tf.extractfile(member)
                    break
            if eintrag is None:
                return {}
            daten = json.loads(eintrag.read().decode("utf-8"))
    except (tarfile.TarError, OSError, ValueError) as exc:
        _LOG.warning("voice_mapping.json nicht lesbar: %s", exc)
        return {}

    umsetzung: Dict[int, int] = {}
    for quelle, ziele in (daten or {}).items():
        if not isinstance(ziele, dict):
            continue
        for ziel, modelle in ziele.items():
            if not isinstance(modelle, list) or model not in modelle:
                continue
            try:
                # Schlüssel wie "298_1" kommen vor - nur die Zahl davor zählt.
                quell_nr = int(str(quelle).split("_")[0])
                umsetzung[quell_nr] = int(ziel)
            except (TypeError, ValueError):
                continue
    return umsetzung


def describe_pack(pack_path: Path) -> str:
    """Kurze Zusammenfassung eines Pakets für das Protokoll."""
    ids = list_sound_ids(pack_path)
    meta = read_metadata(pack_path)
    built = ""
    if "time.txt" in meta:
        built = meta["time.txt"].decode("utf-8", "replace").strip()
    parts = [f"{len(ids)} Ansagen"]
    if meta:
        parts.append(f"{len(meta)} Steuerdateien")
    if built:
        parts.append(f"Stand {built}")
    return ", ".join(parts)
