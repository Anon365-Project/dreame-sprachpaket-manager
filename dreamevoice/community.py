"""Fertige Sprachpakete aus der Community.

Was es wirklich gibt - und was nicht
------------------------------------
Es existiert **kein** offizieller oder inoffizieller Marktplatz mit
Dreame-Sprachpaketen. Was es gibt, sind einige wenige Bastelprojekte auf
GitHub. Die hier gelisteten Einträge wurden einzeln geprüft: das
Projekt existiert, die Datei lädt herunter, und der Inhalt ist ein
tar-Archiv mit Ogg-Dateien im erwarteten Schema.

Bayerisch, Schwäbisch oder eine Prominentenstimme wie Bruce Willis gibt
es als fertiges Dreame-Paket nicht. Solche Pakete müsste man selbst
erzeugen - technisch geht das mit dem Tab "Sprachpaket erstellen", indem
man die gewünschten Ansagen mit einer Sprachsynthese erzeugt und
zuweist. Stimmen realer Personen nachzubilden ist rechtlich heikel
(Persönlichkeitsrecht) und deshalb bewusst nicht Teil dieser App.

Wichtig zur Kompatibilität
---------------------------
Alle Community-Pakete stammen von älteren Modellen und enthalten nur
150-520 Ansagen, während der X50 Ultra Complete 558 kennt. Direkt
installiert bliebe der Roboter bei allen fehlenden Ansagen stumm.

Diese App installiert sie deshalb nie direkt, sondern legt sie über das
offizielle Paket des eigenen Modells (siehe packer.overlay_pack). Ersetzt
wird nur, was das Fremdpaket wirklich mitbringt - der Rest bleibt auf der
offiziellen deutschen Stimme.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import requests

from .errors import NetworkError, PackError
from .official import md5_of_file
from .paths import data_dir

_LOG = logging.getLogger(__name__)

ProgressFn = Callable[[int, int], None]


@dataclass
class CommunityPack:
    """Ein herunterladbares Community-Paket."""

    key: str
    name: str
    description: str
    language: str
    url: str
    project_url: str
    author: str
    license: str
    approx_sounds: int
    expected_size: int = 0
    expected_md5: str = ""
    archive_kind: str = "tar.gz"   # tar.gz oder zip
    notes: str = ""
    tags: List[str] = field(default_factory=list)

    @property
    def size_mb(self) -> float:
        return self.expected_size / (1024 * 1024) if self.expected_size else 0.0

    def local_path(self) -> Path:
        suffix = ".zip" if self.archive_kind == "zip" else ".tar.gz"
        folder = data_dir() / "Community-Pakete"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{self.key}{suffix}"


# --------------------------------------------------------------------------
# Geprüft am 08.08.2026: Projekt vorhanden, Datei lädt, Format stimmt.
# --------------------------------------------------------------------------

PACKS: List[CommunityPack] = [
    CommunityPack(
        key="glados_zigerschlitz",
        name="GLaDOS",
        description=(
            "Die sarkastische KI aus dem Spiel Portal. Der am besten gepflegte "
            "GLaDOS-Satz, als fertiges Archiv mit veröffentlichter Prüfsumme."
        ),
        language="Englisch",
        url=("https://github.com/Makers-Im-Zigerschlitz/voicepacks_dreame/"
             "releases/download/0.1/glados.tar.gz"),
        project_url="https://github.com/Makers-Im-Zigerschlitz/voicepacks_dreame",
        author="Makers Im Zigerschlitz",
        license="keine Lizenz angegeben",
        approx_sounds=155,
        expected_size=4322744,
        expected_md5="d79114b8b0b41e132dd0214f4922836c",
        tags=["lustig", "KI", "Spiel"],
    ),
    CommunityPack(
        key="r2d2_zigerschlitz",
        name="R2-D2",
        description=(
            "Statt Sätzen nur Piepen und Zwitschern des Star-Wars-Droiden. "
            "Sehr unterhaltsam, aber man erfährt nicht mehr, was der Roboter "
            "eigentlich meldet."
        ),
        language="ohne Sprache",
        url=("https://github.com/Makers-Im-Zigerschlitz/voicepacks_dreame/"
             "releases/download/0.1/r2d2.tar.gz"),
        project_url="https://github.com/Makers-Im-Zigerschlitz/voicepacks_dreame",
        author="Makers Im Zigerschlitz",
        license="keine Lizenz angegeben",
        approx_sounds=155,
        expected_size=18808415,
        expected_md5="bdd0b85996748e20037b20bbede258aa",
        notes="Achtung: Fehlermeldungen sind danach nicht mehr verständlich.",
        tags=["lustig", "Film", "ohne Sprache"],
    ),
    CommunityPack(
        key="memes_zigerschlitz",
        name="Memes",
        description="Internet-Meme-Sounds statt der üblichen Ansagen.",
        language="Englisch / ohne Sprache",
        url=("https://github.com/Makers-Im-Zigerschlitz/voicepacks_dreame/"
             "releases/download/0.1/memes.tar.gz"),
        project_url="https://github.com/Makers-Im-Zigerschlitz/voicepacks_dreame",
        author="Makers Im Zigerschlitz",
        license="keine Lizenz angegeben",
        approx_sounds=155,
        expected_size=4398965,
        expected_md5="ba83696fe8e954983a9960a14825b6c5",
        tags=["lustig"],
    ),
    CommunityPack(
        key="glados_findus23",
        name="GLaDOS (Variante 15.ai)",
        description=(
            "Aeltere GLaDOS-Fassung, mit der Sprachsynthese 15.ai erzeugt. "
            "Andere Betonung als die Variante oben."
        ),
        language="Englisch",
        url="https://github.com/Findus23/voice_pack_dreame/raw/main/voice_pack.tar.gz",
        project_url="https://github.com/Findus23/voice_pack_dreame",
        author="Findus23",
        license="keine Lizenz angegeben",
        approx_sounds=155,
        expected_size=4325024,
        expected_md5="8ebfabb9e23e169a5c9b867266f9d1ef",
        tags=["lustig", "KI", "Spiel"],
    ),
    CommunityPack(
        key="glados_x40_kokoro",
        name="GLaDOS für X40 (514 Ansagen)",
        description=(
            "Mit Abstand der umfangreichste Satz: alle 514 Ansagen des X40 "
            "Ultra neu getextet und mit Kokoro-TTS gesprochen. Da X40 und X50 "
            "sich 513 Nummern teilen, deckt dieses Paket fast den kompletten "
            "X50 ab."
        ),
        language="Englisch",
        url="https://github.com/sproft/dreame-x40-glados-voice-pack/archive/refs/heads/main.zip",
        project_url="https://github.com/sproft/dreame-x40-glados-voice-pack",
        author="sproft",
        license="siehe LICENSE im Projekt",
        approx_sounds=514,
        archive_kind="zip",
        notes=("Wird als Projektarchiv geladen; die App holt sich die "
               "Ogg-Dateien daraus. Größe und Prüfsumme ändern sich mit "
               "jeder Aktualisierung des Projekts und werden daher nicht "
               "fest geprüft."),
        tags=["lustig", "KI", "Spiel", "umfangreich"],
    ),
    CommunityPack(
        key="uk_female_pensive",
        name="Ukrainisch (weiblich, ruhig)",
        description="Ukrainische Ansagen, ruhig und sachlich gesprochen.",
        language="Ukrainisch",
        url=("https://github.com/oleksandr-belei/dreame-vacuum-uk-voice-packs/"
             "raw/main/voice_packs/uk_female_pensive"),
        project_url="https://github.com/oleksandr-belei/dreame-vacuum-uk-voice-packs",
        author="oleksandr-belei",
        license="MIT",
        approx_sounds=199,
        expected_size=3585448,
        tags=["Sprache"],
    ),
    CommunityPack(
        key="original_en_zigerschlitz",
        name="Original Englisch (Sicherung)",
        description=(
            "Die englischen Originalansagen eines älteren Modells. Vor allem "
            "als Vergleichsmaterial nützlich."
        ),
        language="Englisch",
        url=("https://github.com/Makers-Im-Zigerschlitz/voicepacks_dreame/"
             "releases/download/0.1/original-en.tar.gz"),
        project_url="https://github.com/Makers-Im-Zigerschlitz/voicepacks_dreame",
        author="Makers Im Zigerschlitz",
        license="keine Lizenz angegeben",
        approx_sounds=155,
        expected_size=3102855,
        expected_md5="2a467cdb59f0ecff54ccb6931c81c0b3",
        tags=["Sprache", "Referenz"],
    ),
]


def get(key: str) -> Optional[CommunityPack]:
    for pack in PACKS:
        if pack.key == key:
            return pack
    return None


def download(pack: CommunityPack, progress: Optional[ProgressFn] = None,
             force: bool = False) -> Path:
    """Lädt ein Community-Paket herunter und prüft es, soweit möglich."""
    target = pack.local_path()

    if target.exists() and not force:
        if not pack.expected_md5 or md5_of_file(target) == pack.expected_md5:
            if progress:
                progress(1, 1)
            return target
        target.unlink(missing_ok=True)

    tmp = target.with_suffix(target.suffix + ".part")
    try:
        with requests.get(pack.url, stream=True, timeout=90,
                          headers={"User-Agent": "DreameSprachpakete/1.0"}) as resp:
            if resp.status_code != 200:
                raise NetworkError(
                    f"Download fehlgeschlagen (HTTP {resp.status_code}).",
                    f"Quelle: {pack.url}",
                )
            total = int(resp.headers.get("Content-Length") or pack.expected_size or 0)
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
        raise NetworkError(f"Das Paket '{pack.name}' konnte nicht geladen werden.",
                           f"Technische Details: {exc}") from exc

    if pack.expected_md5:
        actual = md5_of_file(tmp)
        if actual != pack.expected_md5:
            tmp.unlink(missing_ok=True)
            raise PackError(
                f"Die Prüfsumme von '{pack.name}' stimmt nicht.",
                f"Erwartet {pack.expected_md5}, erhalten {actual}. Der Download "
                f"wurde verworfen - die Datei wird nicht verwendet.",
            )

    tmp.replace(target)
    _LOG.info("Community-Paket %s geladen (%d Bytes)", pack.key, target.stat().st_size)
    return target


def all_tags() -> List[str]:
    tags = set()
    for pack in PACKS:
        tags.update(pack.tags)
    return sorted(tags)
