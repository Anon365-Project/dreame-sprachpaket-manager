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
import re
import tarfile
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Callable, Dict, List, Optional

import requests

from .errors import NetworkError, PackError
from .paths import cache_dir

_LOG = logging.getLogger(__name__)

CATALOG_URL = ("https://awsde0.fds.api.xiaomi.com/dreame-product/"
               "{model}/voices/soundpackage.json")

#: Von wo ein offizielles Sprachpaket kommen darf.
#:
#: Der Katalog liegt auf einem fremden Server, und seine `download`-Adresse
#: geht direkt als Auftrag an den Roboter - der lädt dann selbst. Ohne
#: diese Schranke bestimmte also der Server, welche Datei der Roboter
#: holt: `file://`, `http://` auf eine LAN-Adresse, jede beliebige Domain.
#: Dass der Roboter die Prüfsumme selbst kontrolliert, hilft dabei
#: nichts - sie kommt aus derselben Antwort.
#:
#: Nachgemessen am 30.08.2026 über neun Modelle von Dreame, MOVA und
#: Trouver: Ausgeliefert wird von `oss.iot.dreame.life` (143 Einträge)
#: und `oss.iot.dreame.tech` (38), ausnahmslos über https. `.life`
#: fehlte hier zuerst - damit verwarf die App jeden einzelnen Eintrag
#: und ließ sich überhaupt nicht mehr benutzen. Wer diese Liste
#: ändert, prüft sie bitte gegen den echten Katalog, nicht nur gegen
#: die Angriffstests.
ERLAUBTE_HOSTS = ("api.xiaomi.com", "mi-img.com", "miot-spec.org",
                  "dreametech.com", "dreame.tech", "dreame.life",
                  "mova-tech.com", "trouver-tech.com")

#: Größer ist kein Sprachpaket. Das Originalpaket des X50 wiegt 10,6 MB.
MAX_PAKET_BYTES = 200 * 1024 * 1024

#: Eine Kennung darf nur das sein - kein Pfad. Sie landet im Dateinamen
#: des Zwischenspeichers; mit "../.." schrieb die App sonst außerhalb
#: ihres Datenordners.
_KENNUNG_OK = re.compile(r"^[A-Za-z0-9_-]{1,16}$")


def adresse_erlaubt(url: str) -> bool:
    """Nur gesichert und nur von einem bekannten Hersteller-Server."""
    try:
        teil = urlsplit(url or "")
    except ValueError:
        return False
    if teil.scheme.lower() != "https":
        return False
    wirt = (teil.hostname or "").lower()
    return any(wirt == h or wirt.endswith("." + h) for h in ERLAUBTE_HOSTS)


# Dateien im Paket, die keine Audiodaten sind, sondern Steuerinformationen.
METADATA_FILES = {
    "voice_mapping.json", "tts.json", "dmr_audio.json",
    "first_audio.json", "mini_broad.json", "time.txt",
}

ProgressFn = Callable[[int, int], None]


def _text(wert) -> str:
    """Nur echter Text gilt. Alles andere ist keine Angabe.

    Der Katalog kommt von einem fremden Server; was dort steht, ist
    eine Behauptung. Eine Zahl als Kennung hat früher alle Schranken
    passiert, weil geprüft wurde, was `str(wert)` ergibt - gespeichert
    blieb aber die Zahl.
    """
    return wert.strip() if isinstance(wert, str) else ""


def _zahl(wert) -> int:
    """Zahl oder Zahltext; alles andere ist 0 und fällt damit auf.

    `int("groß")` warf früher eine ValueError bis in den
    Fehlerdialog - auf Englisch, ohne jeden Hinweis.
    """
    if isinstance(wert, bool):
        return 0
    if isinstance(wert, int):
        return wert
    if isinstance(wert, float):
        return int(wert)
    if isinstance(wert, str) and wert.strip().lstrip("+").isdigit():
        return int(wert.strip())
    return 0


class VoicePackInfo:
    """Ein offizielles Sprachpaket laut Dreame-Katalog."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        # Jede Angabe wird auf ihren Typ gebracht, statt ihn zu
        # unterstellen. Was nicht passt, wird leer bzw. 0 - und fällt
        # damit unten in `einwand` auf, statt als Ausnahme aus einer
        # ganz anderen Zeile zu kommen.
        if not isinstance(raw, dict):
            raw = {}
        self.raw = raw
        self.id: str = _text(raw.get("id"))
        self.size: int = _zahl(raw.get("size"))
        self.md5: str = _text(raw.get("md5sum")).lower()
        self.url: str = _text(raw.get("download"))
        self.preview_url: str = _text(raw.get("listen"))
        name = raw.get("name")
        if isinstance(name, dict):
            self.name: str = _text(name.get("default")) or self.id
        else:
            self.name = _text(name) or self.id

    @property
    def einwand(self) -> str:
        """Was gegen diesen Eintrag spricht - leer heißt: nichts.

        Gibt einen kurzen Grund zurück statt nur True/False. Als das
        hier bloß "unbrauchbar" meldete, verwarf die App wegen einer
        fehlenden Zeile in der Erlaubnisliste stillschweigend den
        gesamten Katalog - und sagte dem Nutzer nur, er sehe
        "ungewöhnlich aus".
        """
        if not _KENNUNG_OK.match(str(self.id or "")):
            return f"unzulässige Kennung {self.id!r}"
        teil = urlsplit(self.url or "")
        if teil.scheme.lower() != "https":
            return f"Bezugsadresse ohne https ({teil.scheme or 'ohne Schema'})"
        if not adresse_erlaubt(self.url):
            return f"unbekannter Server {teil.hostname or '?'}"
        if len(self.md5) != 32 or any(z not in "0123456789abcdef"
                                      for z in self.md5):
            # Ohne brauchbare Prüfsumme kann weder die App noch der
            # Roboter feststellen, ob unterwegs etwas verändert wurde.
            # Geprueft wurde das früher erst NACH dem Download.
            return f"unbrauchbare Prüfsumme {self.md5!r}"
        if self.size <= 0:
            return "keine Größenangabe"
        if self.size > MAX_PAKET_BYTES:
            return f"unplausible Größe {self.size} Bytes"
        return ""

    @property
    def brauchbar(self) -> bool:
        """Taugt dieser Eintrag überhaupt für den Roboter?

        Kennung ohne Pfadanteile, Adresse von einem bekannten
        Server, Größe plausibel. Was das nicht erfüllt, wird gar
        nicht erst angeboten.
        """
        return not self.einwand

    @property
    def label(self) -> str:
        return f"{self.name} ({self.id})"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VoicePackInfo {self.id} {self.size}B>"


def fetch_catalog(model: str, timeout: int = 20) -> List[VoicePackInfo]:
    """Lädt die Sprachpaketliste für ein Modell (z. B. dreame.vacuum.r2532h)."""
    if not model:
        raise PackError("Es ist kein Robotermodell bekannt.",
                        "Melde dich zuerst unter 'Verbindung' an.")
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

    # Der Umschlag selbst ist auch nur eine Behauptung: `data` als
    # Liste, `voices` als Wörterbuch, Einträge als Text - alles das
    # kam früher als englische Ausnahme im Fehlerdialog an.
    inhalt = data.get("data") if isinstance(data, dict) else None
    voices = inhalt.get("voices") if isinstance(inhalt, dict) else None
    if not isinstance(voices, list):
        raise PackError(
            "Die Sprachpaketliste von Dreame hat eine unerwartete Form.",
            "Erwartet wurde eine Liste von Sprachpaketen. Es wurde nichts "
            "geladen und nichts an den Roboter geschickt. Bleibt es dabei, "
            "hat Dreame das Format geändert - dann hilft nur eine neue "
            "Fassung dieser App.")
    alle = [VoicePackInfo(v) for v in voices
            if isinstance(v, dict) and _text(v.get("download"))]
    # Was die Schranken nicht erfüllt, wird gar nicht erst angeboten.
    # Der Katalog liegt auf einem fremden Server, und seine Adresse
    # geht als Auftrag an den Roboter - er lädt dann selbst.
    packs = [p for p in alle if p.brauchbar]
    verworfen = [(p.id, p.einwand) for p in alle if not p.brauchbar]
    if verworfen:
        _LOG.warning("Katalogeinträge verworfen: %s",
                     "; ".join(f"{k}: {grund}" for k, grund in verworfen[:10]))
    if not packs:
        if alle:
            # Der häufigste Grund zuerst, im Klartext. Früher stand
            # hier nur "sieht ungewöhnlich aus" - der Grund lag im
            # Protokoll, und auch dort nur als Kennung ohne Ursache.
            gruende = sorted({grund for _, grund in verworfen})
            raise PackError(
                "Der Sprachpaket-Katalog von Dreame sieht ungewöhnlich aus.",
                f"Alle {len(alle)} Einträge wurden abgelehnt. Grund: "
                + "; ".join(gruende[:3])
                + ".\n\nEs wurde nichts geladen und nichts an den Roboter "
                "geschickt. Nennt der Grund einen unbekannten Server, hat "
                "Dreame die Auslieferung umgestellt - dann hilft nur eine "
                "neue Fassung dieser App.")
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

    # ".tar.gz" -> ".tar.part" wäre es mit with_suffix geworden; der
    # Name soll aber erkennbar zum Ziel gehören.
    tmp = target.with_name(target.name + ".part")
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
                    if done > MAX_PAKET_BYTES:
                        raise NetworkError(
                            "Das angebotene Originalpaket ist unerwartet "
                            "groß.",
                            "Der Download wurde abgebrochen. Ein "
                            "Sprachpaket wiegt rund zehn Megabyte.")
                    if progress:
                        progress(done, total)
    except requests.exceptions.RequestException as exc:
        tmp.unlink(missing_ok=True)
        raise NetworkError("Der Download des Originalpakets ist abgebrochen.",
                           f"Technische Details: {exc}") from exc
    except BaseException:
        # Der Abbruch wegen Überlänge ist ein NetworkError und damit
        # KEINE RequestException - er lief früher an der Aufräumzeile
        # vorbei. Bei einem 300-MB-Strom blieben so 240 MB im
        # Zwischenspeicher liegen, und zwar bei jedem neuen Versuch
        # erneut. Auch ein Abbruch durch den Nutzer gehört hierher.
        tmp.unlink(missing_ok=True)
        raise

    actual = md5_of_file(tmp)
    if not pack.md5:
        # Früher hieß es "if pack.md5 and ..." - eine leere Angabe
        # im Katalog übersprang die Kontrolle also vollständig.
        tmp.unlink(missing_ok=True)
        raise PackError(
            "Zu diesem Originalpaket nennt Dreame keine Prüfsumme.",
            "Ohne sie lässt sich nicht feststellen, ob die Datei "
            "unterwegs verändert wurde. Sie wurde verworfen.")
    if actual != pack.md5:
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
