"""Klärt die eine offene Frage: Was spielt `play_voice_test` eigentlich ab?

In `cloud.py` steht die Aktion `siid 7 / aiid 2` bereit, aber niemand
ruft sie auf - und der Kommentar dort sagt ehrlich, dass unklar ist, ob
der Roboter dabei eine **Ansage in der aufgespielten Stimme** abspielt
oder nur einen festen Piepser der Firmware.

Davon hängt ab, ob ein Knopf "Roboter jetzt sprechen lassen" hält, was
er verspricht. Die Frage lässt sich nicht aus dem Code beantworten -
nur durch Hinhören. Dieses Werkzeug führt genau einen Versuch durch und
fragt danach, was zu hören war.

    python Werkzeuge/Testton-prüfen.py

Geschrieben wird **nichts**. Es wird ausschließlich die Aktion
ausgelöst; kein Sprachpaket, keine Lautstärke, keine Einstellung wird
verändert.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreamevoice import config as _config                      # noqa: E402
from dreamevoice import paths                                  # noqa: E402
from dreamevoice.cloud import DreameCloud                      # noqa: E402
from dreamevoice.config import Config                          # noqa: E402
from dreamevoice.errors import DreameError                     # noqa: E402


def datenordner_waehlen() -> Path:
    """Der Ordner, in dem wirklich Zugangsdaten stehen.

    Aus dem Quellcode gestartet zeigt `data_dir()` auf `Daten` neben
    dem Projekt. Wer die App als EXE benutzt, hat seine Daten aber in
    `dist/Daten`. Ohne diese Wahl meldete das Werkzeug "keine
    Zugangsdaten" und war sofort fertig - von außen sah das aus, als
    passiere gar nichts.
    """
    projekt = Path(__file__).resolve().parent.parent
    kandidaten = [paths.data_dir(), projekt / "Daten", projekt / "dist" / "Daten"]
    for ordner in kandidaten:
        datei = ordner / "config.json"
        if not datei.is_file():
            continue
        try:
            import json
            if (json.loads(datei.read_text(encoding="utf-8")).get("email") or ""):
                return ordner
        except (OSError, ValueError):
            continue
    return paths.data_dir()


def frage(text: str, moeglich: tuple) -> str:
    """Fragt so lange, bis eine der vorgesehenen Antworten kommt."""
    hinweis = "/".join(moeglich)
    while True:
        antwort = input(f"{text} [{hinweis}] ").strip().lower()
        if antwort in moeglich:
            return antwort
        print(f"   Bitte eine dieser Antworten: {hinweis}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    print()
    print("Testton-Probe")
    print("=" * 66)
    print("Es wird nichts geschrieben - nur ein Ton ausgelöst.")
    print()
    print("WICHTIG: Stell dich in Hörweite des Roboters, bevor es losgeht.")
    print()

    ordner = datenordner_waehlen()
    _config.config_file = lambda: ordner / "config.json"
    print(f"Datenordner: {ordner}")
    print()

    # Config() liefert nur die Standardwerte - gelesen wird mit load().
    cfg = Config.load()
    if not cfg["email"] or not cfg.password:
        print("Keine gespeicherten Zugangsdaten gefunden.")
        print("Melde dich einmal in der App an und lass 'Zugangsdaten")
        print("merken' angehakt.")
        return 1

    try:
        cloud = DreameCloud(cfg["account_type"])
        region = cloud.login_autodetect(cfg["email"], cfg.password,
                                        cfg["region"] or "eu")
        geraete = cloud.list_devices(only_vacuums=True)
    except DreameError as exc:
        print(f"Anmeldung fehlgeschlagen: {exc}")
        return 1

    if not geraete:
        print("Kein Roboter im Konto gefunden.")
        return 1
    geraet = next((g for g in geraete if g.did == cfg["device_id"]), geraete[0])
    print(f"Roboter: {geraet.name} ({geraet.model}), Region {region.upper()}")

    # Was gerade drauf ist - das ist der Vergleichsmaßstab.
    zustand = cloud.voice_state(geraet)
    aktiv = zustand.get((7, 2))
    print(f"Aktives Sprachpaket laut Roboter: {aktiv or 'unbekannt'}")
    print()

    if frage("Bist du in Hörweite und bereit?", ("j", "n")) != "j":
        print("Abgebrochen. Es wurde nichts ausgelöst.")
        return 0

    print()
    print("Jetzt kommt der Ton ...")
    time.sleep(1)
    erfolg = cloud.play_voice_test(geraet)
    if not erfolg:
        print("Der Roboter hat die Aktion nicht angenommen.")
        print("Damit ist die Frage auch beantwortet: Der Knopf hätte")
        print("nichts zu tun - wir lassen ihn weg.")
        return 0

    print("Ausgelöst. Warte kurz ...")
    time.sleep(4)
    print()

    was = frage("Was war zu hören?",
                ("stimme", "piepser", "nichts"))

    print()
    print("=" * 66)
    if was == "stimme":
        sprache = frage("War es die aufgespielte Stimme (z. B. Dialekt)?",
                        ("j", "n"))
        if sprache == "j":
            print("ERGEBNIS: Der Roboter spricht mit der aufgespielten Stimme.")
            print("Der Knopf 'Roboter jetzt sprechen lassen' hält, was er")
            print("verspricht - und beweist dem Nutzer in drei Sekunden,")
            print("dass die Installation gewirkt hat.")
        else:
            print("ERGEBNIS: Es kommt eine Ansage, aber nicht in der neuen")
            print("Stimme. Als Beweis für die Installation taugt der Knopf")
            print("damit NICHT. Er bliebe höchstens eine Lautstärkeprobe -")
            print("und müsste dann auch so heißen.")
    elif was == "piepser":
        print("ERGEBNIS: Nur ein fester Ton der Firmware.")
        print("Als Beweis für die Installation taugt er nicht. Sinnvoll")
        print("wäre er dann nur als 'Lautstärke prüfen' - ehrlich benannt.")
    else:
        print("ERGEBNIS: Der Roboter nimmt die Aktion an, tut aber hörbar")
        print("nichts. Dann bauen wir den Knopf nicht ein - ein Knopf, der")
        print("nichts bewirkt, ist schlimmer als keiner.")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
