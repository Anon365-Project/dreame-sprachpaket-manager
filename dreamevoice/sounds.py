"""Der Katalog der Ansage-Nummern.

Die Datei `data/sound_catalog.json` wurde aus dem offiziellen deutschen
Sprachpaket des X50 Ultra Complete (dreame.vacuum.r2532h) erzeugt: 558
Ansagen. Die deutschen Bezeichnungen sind von Hand vergeben, die
englischen Hinweise stammen aus einer Whisper-Transkription des sehr
ähnlichen X40-Ultra-Pakets (513 der 514 IDs sind deckungsgleich).

Die Hinweise sind Orientierung, keine Wahrheit. Maßgeblich ist immer die
Hörprobe der Originaldatei, die die App direkt aus dem heruntergeladenen
Originalpaket abspielt.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .paths import resource_dir

_LOG = logging.getLogger(__name__)

GROUP_ORDER = [
    "Reinigung",
    "Fehler & Wartung",
    "Akku & Laden",
    "Basisstation",
    "Netzwerk",
    "Sprachassistent",
    "Akkustand",
    "Sonstiges",
]


@dataclass
class Sound:
    """Eine einzelne Ansage."""

    id: int
    de: str = ""
    en: str = ""
    group: str = "Sonstiges"
    common: bool = False

    @property
    def title(self) -> str:
        """Beste verfügbare Beschreibung."""
        if self.de:
            return self.de
        if self.en:
            return self.en
        return "(unbekannte Ansage - bitte Hörprobe nutzen)"

    @property
    def has_german_label(self) -> bool:
        return bool(self.de)

    def matches(self, needle: str) -> bool:
        if not needle:
            return True
        n = needle.strip().lower()
        if not n:
            return True
        if n.isdigit():
            return n in str(self.id)
        return n in self.de.lower() or n in self.en.lower() or n in self.group.lower()


class SoundCatalog:
    """Alle bekannten Ansagen, sortiert nach Nummer."""

    def __init__(self, sounds: Iterable[Sound], source_model: str = "") -> None:
        self._sounds: List[Sound] = sorted(sounds, key=lambda s: s.id)
        self._by_id: Dict[int, Sound] = {s.id: s for s in self._sounds}
        self.source_model = source_model

    # -- Zugriff ----------------------------------------------------------
    def __len__(self) -> int:
        return len(self._sounds)

    def __iter__(self):
        return iter(self._sounds)

    def get(self, sound_id: int) -> Optional[Sound]:
        return self._by_id.get(sound_id)

    def ids(self) -> List[int]:
        return [s.id for s in self._sounds]

    def groups(self) -> List[str]:
        present = {s.group for s in self._sounds}
        ordered = [g for g in GROUP_ORDER if g in present]
        ordered += sorted(present - set(ordered))
        return ordered

    def filtered(self, group: str = "", search: str = "",
                 only_common: bool = False) -> List[Sound]:
        out = []
        for s in self._sounds:
            if only_common and not s.common:
                continue
            if group and s.group != group:
                continue
            if not s.matches(search):
                continue
            out.append(s)
        return out

    def restrict_to(self, allowed_ids: Iterable[int]) -> "SoundCatalog":
        """Katalog auf die IDs beschränken, die im Originalpaket wirklich
        vorkommen. Fehlende IDs werden als Platzhalter ergänzt, damit auch
        ein Modell mit abweichendem Umfang vollständig bedienbar bleibt."""
        allowed = sorted(set(int(i) for i in allowed_ids))
        result: List[Sound] = []
        for i in allowed:
            existing = self._by_id.get(i)
            result.append(existing if existing else Sound(id=i))
        return SoundCatalog(result, self.source_model)

    # -- Laden ------------------------------------------------------------
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "SoundCatalog":
        path = path or (resource_dir() / "dreamevoice" / "data" / "sound_catalog.json")
        if not path.exists():
            # Zweiter Versuch relativ zum Modul (Entwicklungsumgebung).
            alt = Path(__file__).resolve().parent / "data" / "sound_catalog.json"
            path = alt if alt.exists() else path

        if not path.exists():
            _LOG.warning("sound_catalog.json nicht gefunden (%s)", path)
            return cls([])

        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            _LOG.error("sound_catalog.json unlesbar: %s", exc)
            return cls([])

        sounds = [
            Sound(id=int(entry["id"]), de=entry.get("de", ""), en=entry.get("en", ""),
                  group=entry.get("group", "Sonstiges"), common=bool(entry.get("common")))
            for entry in data.get("sounds", [])
        ]
        return cls(sounds, data.get("source_model", ""))
