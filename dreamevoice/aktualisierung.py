"""Nach einer neueren Fassung sehen und sie einspielen.

Warum das hier trotz "portabler EXE ohne Installation" geht
-----------------------------------------------------------
Windows lässt eine laufende Programmdatei nicht überschreiben - **wohl
aber umbenennen**. Darauf baut der Tausch auf:

1. Die neue Fassung neben die alte laden (`...neu.exe`).
2. Prüfsumme vergleichen. Erst danach wird überhaupt etwas angefasst.
3. Die laufende `DreameSprachpaket.exe` nach `...alt.exe` umbenennen.
4. Die neue Datei auf den frei gewordenen Namen umbenennen.
5. Neue Fassung starten, alte beenden.
6. Beim nächsten Start die `...alt.exe` wegräumen - dann läuft sie nicht mehr.

Schlägt Schritt 4 fehl, wird Schritt 3 rückgängig gemacht. Auch das
kann scheitern - abgezogener USB-Stick, verschwundenes Netzlaufwerk,
ein Virenscanner, der dazwischenfährt. Nur dann bleibt keine
startfähige Datei am Platz, und genau dafür gibt es `TauschNotstand`
mit einer Handanweisung. Ein früherer Kommentar hier behauptete, das
könne nicht vorkommen; das war falsch.

Ein Nebeneffekt, der die Sache lohnend macht: Eine Datei, die dieses
Programm selbst lädt, bekommt **kein "Mark of the Web"** - das setzt nur
der Browser. Die SmartScreen-Warnung beim ersten Start entfällt damit.

Datenschutz
-----------
Die Abfrage geht an GitHub und verrät dadurch, dass hier jemand diese App
benutzt (IP-Adresse und Zeitpunkt, wie bei jedem Seitenaufruf). Deshalb
ist sie **ausgeschaltet, bis der Benutzer sie einschaltet**, und es wird
nichts über ihn oder seinen Roboter mitgeschickt.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from typing import Callable, Optional

import requests

from . import PROJEKT_URL, __version__
from .errors import NetworkError

_LOG = logging.getLogger(__name__)

ProgressFn = Callable[[int, int], None]

#: Wie die Releases abgefragt werden. Ohne Anmeldung erlaubt GitHub 60
#: Anfragen je Stunde und IP - für einmal pro Programmstart reichlich.
API_URL = "https://api.github.com/repos/{pfad}/releases/latest"

#: So heißt die Programmdatei im Release.
EXE_NAME = "DreameSprachpaket.exe"

#: Endungen der Zwischenschritte.
ENDUNG_NEU = ".neu.exe"
ENDUNG_ALT = ".alt.exe"

#: Größer darf die heruntergeladene Datei nicht sein. Die EXE liegt bei
#: rund 90 MB; alles jenseits davon ist nicht das, was wir erwarten.
MAX_BYTES = 400 * 1024 * 1024

#: Von wo eine Programmdatei überhaupt kommen darf.
#:
#: Ohne diese Schranke folgte der Download jeder Adresse, die in der
#: API-Antwort steht - auch einem ungesicherten http:// auf einen
#: beliebigen Rechner. Wer die Antwort fälschen kann, setzt Datei
#: UND Prüfsumme selbst; die Prüfung liefe dann ins Leere. Die
#: Schranke macht wenigstens den Kanal eng.
ERLAUBTE_HOSTS = ("github.com", "objects.githubusercontent.com",
                  "release-assets.githubusercontent.com",
                  "raw.githubusercontent.com")

#: Eine SHA-256-Summe als Text.
_HEX64 = re.compile(r"\b([0-9a-fA-F]{64})\b")


@dataclass(frozen=True)
class Neuerung:
    """Eine verfügbare neuere Fassung."""

    version: str
    url: str
    groesse: int
    sha256: str
    seite: str
    notizen: str = ""

    @property
    def pruefbar(self) -> bool:
        """Ob eine Prüfsumme vorliegt.

        Ohne sie wird nicht getauscht. Eine Programmdatei ungeprüft über
        die eigene zu schreiben, wäre genau der Weg, den man einem
        Angreifer nicht offenlassen darf.
        """
        return bool(self.sha256)

    @property
    def groesse_mb(self) -> float:
        return self.groesse / 1024 / 1024


# --------------------------------------------------------------------------
# Versionen vergleichen
# --------------------------------------------------------------------------

def _teile(version: str) -> tuple:
    """"v1.10.2" -> (1, 10, 2). Unbrauchbares ergibt (0,)."""
    sauber = (version or "").strip().lstrip("vV")
    zahlen = []
    for stueck in re.split(r"[.\-+]", sauber):
        if stueck.isdigit():
            zahlen.append(int(stueck))
        else:
            break
    return tuple(zahlen) if zahlen else (0,)


def ist_neuer(kandidat: str, als: str = __version__) -> bool:
    """Ist `kandidat` eine höhere Version als `als`?

    Verglichen wird zahlenweise, nicht als Text: Sonst stünde "1.10.0"
    vor "1.9.0", weil "1" kleiner ist als "9".
    """
    a, b = _teile(kandidat), _teile(als)
    laenge = max(len(a), len(b))
    a = a + (0,) * (laenge - len(a))
    b = b + (0,) * (laenge - len(b))
    return a > b


# --------------------------------------------------------------------------
# Nachsehen
# --------------------------------------------------------------------------

def _repo_pfad(projekt_url: str = PROJEKT_URL) -> str:
    """"https://github.com/wer/was" -> "wer/was"."""
    rest = (projekt_url or "").rstrip("/").split("github.com/", 1)
    return rest[1] if len(rest) == 2 else ""


def _pruefsumme_finden(release: dict, eintrag: dict) -> str:
    """Die SHA-256-Summe der Programmdatei, aus dem, was das Release hergibt.

    Drei Quellen, in dieser Reihenfolge: das `digest`-Feld der Datei, das
    GitHub selbst berechnet; eine beigelegte Prüfsummendatei; und zuletzt
    eine 64-stellige Zeichenfolge im Begleittext. Alle drei kommen über
    dieselbe gesicherte Verbindung wie die Datei selbst.
    """
    roh = str(eintrag.get("digest") or "")
    if roh.lower().startswith("sha256:"):
        summe = roh.split(":", 1)[1].strip()
        if len(summe) == 64:
            return summe.lower()

    for datei in release.get("assets") or []:
        name = str(datei.get("name") or "").lower()
        if "sha256" not in name or not name.endswith((".txt", ".sha256")):
            continue
        try:
            # Erst die Größe prüfen, dann lesen: Ein falsch
            # benannter Riesenanhang landete sonst komplett im
            # Speicher, bevor er abgelehnt wurde.
            adresse = datei.get("browser_download_url")
            if not _adresse_erlaubt(adresse):
                continue
            with requests.get(adresse,
                              timeout=15, stream=True,
                              headers={"User-Agent": _kennung()}) as antwort:
                if antwort.status_code != 200:
                    continue
                roh = antwort.raw.read(65536 + 1, decode_content=True)
            if len(roh) > 65536:
                continue
            for zeile in roh.decode("utf-8", "replace").splitlines():
                if EXE_NAME.lower() in zeile.lower():
                    treffer = _HEX64.search(zeile)
                    if treffer:
                        return treffer.group(1).lower()
        except requests.exceptions.RequestException:
            continue

    # Im Begleittext nur eine Zeile nehmen, die auch die Programmdatei
    # nennt. Sonst gewinnt die erste beste 64-stellige Zeichenfolge -
    # etwa die eines anderen Anhangs - und jede Aktualisierung
    # scheiterte dauerhaft an einer Prüfsumme, die nie passen kann.
    for zeile in str(release.get("body") or "").splitlines():
        if EXE_NAME.lower() in zeile.lower():
            treffer = _HEX64.search(zeile)
            if treffer:
                return treffer.group(1).lower()
    # Steht sie allein und ohne Dateinamen da, gilt sie nur, wenn es
    # im ganzen Text genau eine gibt - dann ist sie eindeutig gemeint.
    alle = set(_HEX64.findall(str(release.get("body") or "")))
    return alle.pop().lower() if len(alle) == 1 else ""


def _adresse_erlaubt(url: str) -> bool:
    """Nur gesichert und nur von GitHub."""
    try:
        teil = urlsplit(url or "")
    except ValueError:
        return False
    if teil.scheme.lower() != "https":
        return False
    wirt = (teil.hostname or "").lower()
    return any(wirt == h or wirt.endswith("." + h)
               for h in ERLAUBTE_HOSTS)


def _zahl(wert) -> int:
    """Was sich als Zahl lesen lässt - sonst 0."""
    try:
        return max(0, int(wert))
    except (TypeError, ValueError):
        return 0


def _kennung() -> str:
    return f"DreameSprachpaket/{__version__}"


def pruefen(timeout: int = 12,
            projekt_url: str = PROJEKT_URL) -> Optional[Neuerung]:
    """Fragt nach, ob es eine neuere Fassung gibt.

    `None` heißt: Es gibt keine neuere. Fehler werden als NetworkError
    gemeldet - der Aufrufer entscheidet, ob er sie zeigt. Beim
    Start soll ein ausgefallener Server nicht stören.
    """
    pfad = _repo_pfad(projekt_url)
    if not pfad:
        raise NetworkError("Es ist keine Projektadresse hinterlegt.",
                           "Ohne sie weiß die App nicht, wo sie nachsehen soll.")
    try:
        antwort = requests.get(
            API_URL.format(pfad=pfad), timeout=timeout,
            headers={"User-Agent": _kennung(),
                     "Accept": "application/vnd.github+json"})
    except requests.exceptions.RequestException as exc:
        raise NetworkError("Die Suche nach Aktualisierungen ist fehlgeschlagen.",
                           f"Technische Details: {exc}") from exc

    if antwort.status_code == 404:
        return None
    if antwort.status_code != 200:
        raise NetworkError(
            f"GitHub antwortete mit HTTP {antwort.status_code}.",
            "Versuche es später noch einmal, oder sieh auf der "
            "Projektseite selbst nach.")
    try:
        release = antwort.json()
    except ValueError as exc:
        raise NetworkError("Die Antwort von GitHub war nicht lesbar.",
                           f"Technische Details: {exc}") from exc

    version = str(release.get("tag_name") or "").strip()
    if not version or not ist_neuer(version):
        return None

    eintrag = next((d for d in (release.get("assets") or [])
                    if str(d.get("name") or "").lower() == EXE_NAME.lower()),
                   None)
    if eintrag is None:
        # Es GIBT eine neuere Fassung, nur ohne Programmdatei - etwa
        # weil sie gerade hochgeladen wird. Früher meldete die App
        # daraufhin "du hast die neueste"; das stimmte nicht.
        raise NetworkError(
            f"Version {version.lstrip('vV')} ist da, aber ohne "
            f"Programmdatei.",
            f"Vermutlich wird sie gerade hochgeladen. Sieh in ein paar "
            f"Minuten noch einmal nach, oder hol sie dir hier:\n"
            f"{release.get('html_url') or projekt_url}")

    return Neuerung(
        version=version.lstrip("vV"),
        url=str(eintrag.get("browser_download_url") or ""),
        # Die Größe ist nur eine Anzeige. Eine Zeichenkette dort
        # ließ früher ein rohes ValueError fliegen, das an der
        # NetworkError-Behandlung vorbeilief.
        groesse=_zahl(eintrag.get("size")),
        sha256=_pruefsumme_finden(release, eintrag),
        seite=str(release.get("html_url") or projekt_url),
        notizen=str(release.get("body") or "").strip(),
    )


# --------------------------------------------------------------------------
# Herunterladen und tauschen
# --------------------------------------------------------------------------

def eigene_exe() -> Optional[Path]:
    """Die laufende Programmdatei - oder None, wenn aus dem Quellcode gestartet."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        return Path(sys.executable).resolve()
    except OSError:                                    # pragma: no cover
        return None


def ordner_beschreibbar(exe: Path) -> bool:
    """Lässt sich im Ordner der EXE überhaupt eine Datei anlegen?

    Liegt die App unter `Programme`, ist die Antwort nein - dann hat ein
    Tausch keinen Sinn, und der Benutzer bekommt lieber gleich den Weg
    über die Projektseite angeboten.
    """
    probe = exe.parent / f".schreibprobe_{os.getpid()}"
    try:
        probe.write_bytes(b"x")
        probe.unlink()
        return True
    except OSError:
        return False


def herunterladen(neuerung: Neuerung, ziel: Optional[Path] = None,
                  progress: Optional[ProgressFn] = None,
                  cancelled: Optional[Callable[[], bool]] = None) -> Path:
    """Lädt die neue Fassung und prüft sie. Gibt den Pfad zurück."""
    cancelled = cancelled or (lambda: False)
    if not neuerung.pruefbar:
        raise NetworkError(
            "Zu dieser Fassung liegt keine Prüfsumme vor.",
            "Ohne sie wird nichts ausgetauscht. Lade die Datei von der "
            "Projektseite und ersetze sie von Hand.")

    exe = eigene_exe()
    if ziel is None:
        if exe is None:
            raise NetworkError(
                "Die App läuft aus dem Quellcode.",
                "Ein Austausch der Programmdatei ergibt hier keinen Sinn - "
                "hol dir die neue Fassung über git.")
        ziel = exe.with_name(exe.stem + ENDUNG_NEU)

    if not _adresse_erlaubt(neuerung.url):
        raise NetworkError(
            "Die Bezugsadresse der neuen Fassung ist nicht zulässig.",
            f"Erwartet wird eine gesicherte Adresse bei GitHub, "
            f"angegeben war:\n{neuerung.url}\n\nEs wurde nichts geladen.")

    ziel.unlink(missing_ok=True)
    hasher = hashlib.sha256()
    geladen = 0
    try:
        with requests.get(neuerung.url, stream=True, timeout=90,
                          headers={"User-Agent": _kennung()}) as antwort:
            if antwort.status_code != 200:
                raise NetworkError(
                    f"Der Download ist fehlgeschlagen (HTTP "
                    f"{antwort.status_code}).", f"Quelle: {neuerung.url}")
            gesamt = int(antwort.headers.get("Content-Length")
                         or neuerung.groesse or 0)
            with ziel.open("wb") as datei:
                for block in antwort.iter_content(chunk_size=1 << 18):
                    if cancelled():
                        raise NetworkError("Vom Benutzer abgebrochen.")
                    if not block:
                        continue
                    datei.write(block)
                    hasher.update(block)
                    geladen += len(block)
                    if geladen > MAX_BYTES:
                        raise NetworkError(
                            "Die Datei ist unerwartet groß.",
                            "Der Download wurde abgebrochen.")
                    if progress:
                        progress(geladen, gesamt)
    except requests.exceptions.RequestException as exc:
        ziel.unlink(missing_ok=True)
        raise NetworkError("Der Download ist abgebrochen.",
                           f"Technische Details: {exc}") from exc
    except BaseException:
        ziel.unlink(missing_ok=True)
        raise

    tatsaechlich = hasher.hexdigest()
    if tatsaechlich != neuerung.sha256:
        ziel.unlink(missing_ok=True)
        raise NetworkError(
            "Die heruntergeladene Datei stimmt nicht mit der Prüfsumme überein.",
            f"Erwartet {neuerung.sha256[:16]}…, erhalten {tatsaechlich[:16]}…. "
            f"Es wurde nichts ausgetauscht.")
    return ziel


class TauschNotstand(NetworkError):
    """Der Tausch scheiterte UND ließ sich nicht zurücknehmen.

    Der einzige Fall, in dem am Ende keine startfähige Programmdatei am
    gewohnten Platz steht. Er braucht eine eigene Ausnahme, weil der
    Benutzer dann etwas tun muss - und weil die übliche Meldung ("es
    wurde nichts ausgetauscht") hier genau das Gegenteil der Wahrheit
    wäre.
    """


def summe(datei: Path) -> str:
    """SHA-256 einer Datei, blockweise gelesen."""
    hasher = hashlib.sha256()
    with datei.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


def austauschen(neu: Path, exe: Optional[Path] = None,
                erwartet_sha256: str = "") -> Path:
    """Setzt die neue Fassung an die Stelle der laufenden.

    Gibt den Pfad der beiseitegelegten alten Datei zurück.

    Schlägt der zweite Schritt fehl, wird der erste zurückgenommen. Auch
    das kann scheitern - ein abgezogener USB-Stick, ein verschwundenes
    Netzlaufwerk, ein Virenscanner, der genau dazwischenfährt. Dann und
    nur dann bleibt keine startfähige Datei am Platz, und dieser Fall
    bekommt eine eigene Ausnahme mit einer Handanweisung. Ein früherer
    Kommentar hier behauptete, das könne nicht vorkommen; das war
    schlicht falsch.
    """
    exe = exe or eigene_exe()
    if exe is None:
        raise NetworkError("Es gibt keine Programmdatei zum Austauschen.")
    if not neu.is_file():
        raise NetworkError("Die neue Fassung wurde nicht gefunden.", str(neu))

    # Noch einmal prüfen, unmittelbar vor dem Tausch. Zwischen
    # Herunterladen und Umbenennen liegt ein Zeitfenster, in dem
    # jemand mit Schreibrecht im Ordner die geprüft Datei
    # austauschen könnte - und genau die würde dann laufen.
    if erwartet_sha256:
        jetzt_summe = summe(neu)
        if jetzt_summe != erwartet_sha256:
            neu.unlink(missing_ok=True)
            raise NetworkError(
                "Die vorbereitete Datei hat sich seit der Prüfung "
                "veraendert.",
                "Sie wurde verworfen, es wurde nichts ausgetauscht. "
                "Versuche es erneut.")

    alt = exe.with_name(exe.stem + ENDUNG_ALT)
    try:
        alt.unlink(missing_ok=True)
    except OSError as exc:
        # Meist hat jemand die alte Fassung noch offen. Ohne diesen
        # Hinweis stünde dort nur ein roher WinError 32, und jede weitere
        # Aktualisierung schlüge dauerhaft fehl.
        raise NetworkError(
            "Die vorige Fassung lässt sich nicht beiseiteräumen.",
            f"Vermutlich läuft sie noch oder wird von einem anderen "
            f"Programm festgehalten. Schließe sie und versuche es erneut - "
            f"oder lösche die Datei von Hand:\n{alt}\n\n"
            f"Technische Details: {exc}") from exc

    # Umbenennen darf man eine laufende EXE - überschreiben nicht.
    exe.rename(alt)
    try:
        neu.rename(exe)
    except OSError as urspruenglich:
        try:
            alt.rename(exe)          # Rückwärts, damit nichts fehlt.
        except OSError as auch_das:
            raise TauschNotstand(
                "Die Aktualisierung ist mitten im Austausch steckengeblieben.",
                f"Am gewohnten Platz liegt gerade KEINE startfähige "
                f"Programmdatei. So bekommst du sie zurück: Benenne\n"
                f"  {alt.name}\n"
                f"wieder in\n  {exe.name}\n"
                f"um. Beide liegen in:\n{exe.parent}\n\n"
                f"Technische Details: {urspruenglich} / {auch_das}"
            ) from urspruenglich
        raise
    return alt


def altlasten_entfernen(exe: Optional[Path] = None) -> int:
    """Räumt die beiseitegelegten Vorgängerfassungen weg.

    Erst beim nächsten Start möglich: Vorher lief die Datei ja noch.
    """
    exe = exe or eigene_exe()
    if exe is None:
        return 0
    weg = 0
    # Gezielt die eigenen Dateien - ein "*.alt.exe" träfe auch fremde.
    # Die App liegt oft im Download-Ordner, wo alles Mögliche daneben
    # liegt; dort bei jedem Start blind zu löschen wäre übergriffig.
    for endung in (ENDUNG_ALT, ENDUNG_NEU):
        kandidat = exe.with_name(exe.stem + endung)
        try:
            if kandidat.is_file():
                kandidat.unlink()
                weg += 1
        except OSError:                                # pragma: no cover
            continue
    return weg


def neu_starten(exe: Optional[Path] = None) -> bool:
    """Startet die getauschte Fassung und meldet, ob das gelang."""
    exe = exe or eigene_exe()
    if exe is None or not exe.is_file():
        return False
    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True,
                         **kwargs)
        return True
    except OSError as exc:                             # pragma: no cover
        _LOG.warning("Neustart fehlgeschlagen: %s", exc)
        return False


def jetzt() -> int:
    """Zeitstempel für "zuletzt nachgesehen"."""
    return int(time.time())
