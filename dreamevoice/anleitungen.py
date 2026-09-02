"""Zugriff auf die ausführlichen Anleitungen im Ordner `docs`.

Die README wurde von 850 auf 232 Zeilen gekürzt; alles Ausführliche
liegt seither in `docs/`. Nur: Aus der App heraus war davon nichts zu
sehen. Wer die EXE geladen hat und im Hilfe-Fenster nicht weiterkam,
hatte keinen Hinweis darauf, dass es überhaupt mehr gibt.

Zwei Wege führen zum selben Text:

* Liegt der Ordner `docs` neben der App oder steckt er in der EXE, wird
  die Datei direkt geöffnet - offline, ohne Umweg.
* Sonst öffnet sich dieselbe Seite auf GitHub im Browser.

Deshalb sagt jeder Knopf vorher, was er tun wird: `verfuegbar()`
entscheidet das, nicht der Zufall.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import NamedTuple, Optional

from . import PROJEKT_URL
from .paths import app_dir, resource_dir

_LOG = logging.getLogger(__name__)

#: Zweig im Projekt, aus dem die Anleitungen online geholt werden.
ZWEIG = "main"


class Anleitung(NamedTuple):
    """Eine Anleitung: Dateiname, Überschrift, ein Satz Inhalt."""

    datei: str
    titel: str
    inhalt: str


#: Reihenfolge wie in der README - vom Häufigsten zum Seltensten.
ANLEITUNGEN = (
    Anleitung("Problemloesung.md", "Wenn etwas nicht klappt",
              "Der Roboter holt das Paket nicht ab, die Anmeldung "
              "scheitert, die Stimme ist zu leise."),
    Anleitung("Modelle.md", "Welche Roboter funktionieren",
              "Geprüfte Modelle und woran man erkennt, ob der eigene "
              "dazugehört."),
    Anleitung("Sicherheit.md", "Warum das den Roboter nicht beschädigt",
              "Was die App anfasst, was sie nicht anfasst und wie der "
              "Rückweg aussieht."),
    Anleitung("Eigene-Stimmen.md", "Eigene Stimmen und Dialekte",
              "Eigene Texte, eigene Aufnahmen, Windows-Sprachausgabe "
              "und ElevenLabs."),
    Anleitung("Technik.md", "Technische Hintergründe",
              "Paketformat, Cloud-Befehle und was beim Aufspielen "
              "wirklich passiert."),
    Anleitung("Entwicklung.md", "Entwicklung",
              "Aus dem Quellcode starten, Selbsttest, EXE bauen."),
)


def ordner() -> Optional[Path]:
    """Wo die Anleitungen liegen - oder None, wenn sie fehlen.

    Gesucht wird an drei Stellen: im Bündel der EXE, neben der EXE und
    im Projektordner. Die letzte Stelle greift beim Start aus dem
    Quellcode, wo `docs` eine Ebene über diesem Modul liegt.
    """
    for kandidat in (resource_dir() / "docs",
                     app_dir() / "docs",
                     Path(__file__).resolve().parent.parent / "docs"):
        if kandidat.is_dir():
            return kandidat
    return None


def pfad(datei: str) -> Optional[Path]:
    """Die örtliche Datei - oder None, wenn es sie hier nicht gibt."""
    # Nur der reine Name, nie ein Pfad: Der Aufrufer kommt zwar aus der
    # eigenen Liste, aber eine Datei außerhalb von `docs` zu öffnen
    # soll über diesen Weg grundsätzlich nicht möglich sein.
    name = Path(datei).name
    if not name or name != datei:
        return None
    heim = ordner()
    if heim is None:
        return None
    ziel = heim / name
    return ziel if ziel.is_file() else None


def netz_adresse(datei: str) -> str:
    """Dieselbe Anleitung auf GitHub."""
    name = Path(datei).name
    return f"{PROJEKT_URL.rstrip('/')}/blob/{ZWEIG}/docs/{name}"


def verfuegbar(datei: str) -> str:
    """"örtlich", "netz" oder "nein" - was ein Klick bewirken würde."""
    if pfad(datei) is not None:
        return "oertlich"
    if PROJEKT_URL:
        return "netz"
    return "nein"


def oeffnen(datei: str) -> str:
    """Anleitung anzeigen. Rückgabe wie bei `verfügbar`.

    Schlägt das Öffnen der örtlichen Datei fehl - kein Programm für
    `.md` eingerichtet, etwa auf einem frisch aufgesetzten Windows -
    wird auf die Netzfassung ausgewichen. Sonst passierte schlicht
    nichts, und der Knopf sähe kaputt aus.
    """
    ziel = pfad(datei)
    if ziel is not None and _oeffne_datei(ziel):
        return "oertlich"
    if PROJEKT_URL:
        try:
            webbrowser.open(netz_adresse(datei))
            return "netz"
        except Exception:                            # noqa: BLE001
            _LOG.exception("Anleitung ließ sich nicht im Browser öffnen")
    return "nein"


def _oeffne_datei(ziel: Path) -> bool:
    """Datei mit dem Programm öffnen, das das System dafür vorsieht."""
    try:
        if sys.platform == "win32":
            os.startfile(str(ziel))                  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(ziel)])
        else:
            subprocess.Popen(["xdg-open", str(ziel)])
        return True
    except OSError:
        _LOG.warning("Kein Programm für %s eingerichtet", ziel.name)
        return False
