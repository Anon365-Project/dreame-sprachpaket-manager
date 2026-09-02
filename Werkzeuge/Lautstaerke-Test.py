"""Geführter Test: Wann wird der Roboter leise, und was macht ihn wieder laut?

Führt Schritt für Schritt durch und fragt nach jedem Schritt, was zu
hören war. Am Ende steht ein Protokoll, aus dem hervorgeht, woran es
liegt.

    python Lautstärke-Test.py

Geschrieben wird nur die Lautstärke - und am Ende steht sie wieder auf
dem Ausgangswert.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreamevoice import paths                                  # noqa: E402

PROJEKT = Path(__file__).resolve().parent.parent
PIID_LAUTSTAERKE = 1


def _ablage() -> Path | None:
    for ordner in (PROJEKT / "dist" / "Daten", PROJEKT / "Daten"):
        try:
            if json.loads((ordner / "config.json").read_text(
                    encoding="utf-8")).get("email"):
                return ordner
        except (OSError, ValueError):
            continue
    return None


ABLAGE = _ablage()
if ABLAGE is not None:
    paths.data_dir = lambda: ABLAGE

from dreamevoice.cloud import DreameCloud, SIID_VOICE          # noqa: E402
from dreamevoice.config import Config                          # noqa: E402

protokoll: list[str] = []


def notiere(text: str) -> None:
    protokoll.append(text)


def frage(text: str) -> str:
    print()
    print(f"  >>> {text}")
    return input("      Antwort: ").strip()


def warte(text: str) -> None:
    print()
    print(f"  >>> {text}")
    input("      Weiter mit [Enter] ")


def schritt(nummer: int, titel: str) -> None:
    print()
    print("=" * 66)
    print(f"  Schritt {nummer}: {titel}")
    print("=" * 66)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    if ABLAGE is None:
        print("Keine Zugangsdaten gefunden - bitte in der App anmelden.")
        return 1

    cfg = Config.load()
    cloud = DreameCloud(cfg["account_type"])
    cloud.login_autodetect(cfg["email"], cfg.password, cfg["region"] or "eu")
    geraete = cloud.list_devices(only_vacuums=True)
    if not geraete:
        print("Kein Roboter gefunden.")
        return 1
    geraet = next((g for g in geraete if g.did == cfg["device_id"]), geraete[0])

    def lautstaerke() -> int:
        return cloud.get_property(geraet, SIID_VOICE, PIID_LAUTSTAERKE)

    def setze(wert: int) -> None:
        cloud.set_property(geraet, SIID_VOICE, PIID_LAUTSTAERKE, wert)

    def aktives_paket() -> str:
        return cloud.get_property(geraet, SIID_VOICE, 2) or "?"

    print()
    print(f"  Roboter: {geraet.name}  ({geraet.model})")
    ausgangswert = lautstaerke()
    print(f"  Lautstärke am Anfang: {ausgangswert}")
    print(f"  Aktives Sprachpaket:   {aktives_paket()}")
    notiere(f"Start: Lautstärke={ausgangswert}, Paket={aktives_paket()}")

    print()
    print("  Der Roboter wird mehrmals etwas sagen sollen. Am einfachsten")
    print("  in der Dreamehome-App auf 'Roboter finden' tippen.")
    warte("Bereit?")

    # ---------------------------------------------------------------
    schritt(1, "Ausgangslage - so klingt er JETZT")
    warte("Lass ihn sprechen und hör genau hin.")
    a1 = frage("Wie klingt er? (laut / mittel / leise)")
    notiere(f"1. Ausgangslage, Lautstärke={ausgangswert}: {a1}")

    # ---------------------------------------------------------------
    schritt(2, "Jetzt eine andere Stimme aufspielen")
    print()
    print("  Wechsle in der App auf 'Fertige Stimmen', wähle einen")
    print("  ANDEREN Dialekt als den aktuellen und spiele ihn auf.")
    print("  Warte, bis die App 'Erfolgreich aufgespielt' meldet.")
    print()
    print("  WICHTIG: Danach nichts weiter anfassen - nicht neu starten,")
    print("  keine Lautstärke ändern.")
    warte("Fertig aufgespielt?")

    nach_install = lautstaerke()
    paket = aktives_paket()
    print(f"      Lautstärke laut Roboter: {nach_install}")
    print(f"      Aktives Paket:            {paket}")
    notiere(f"2. Nach dem Aufspielen: Lautstärke={nach_install}, Paket={paket}")

    warte("Lass ihn jetzt sprechen.")
    a2 = frage("Wie klingt er jetzt? (laut / mittel / leise)")
    notiere(f"2. Klang nach dem Aufspielen: {a2}")

    if a2.lower().startswith("laut"):
        print()
        print("  Er ist also gar nicht leiser geworden. Dann tritt der Fehler")
        print("  nicht immer auf - notiere, was diesmal anders war.")

    # ---------------------------------------------------------------
    schritt(3, "Denselben Wert neu schreiben")
    print(f"  Es wird {nach_install} geschrieben - also genau der Wert, der")
    print("  ohnehin schon dort steht. Wenn das hilft, wendet der Roboter")
    print("  seine Einstellung nur nicht von selbst an.")
    setze(nach_install)
    time.sleep(2)
    print(f"      Lautstärke danach: {lautstaerke()}")
    notiere(f"3. Gleichen Wert ({nach_install}) neu geschrieben")

    warte("Lass ihn sprechen.")
    a3 = frage("Und jetzt? (laut / mittel / leise)")
    notiere(f"3. Klang nach Neuschreiben: {a3}")

    # ---------------------------------------------------------------
    schritt(4, "Einen anderen Wert und wieder zurück")
    print("  Falls das bloße Neuschreiben nichts bewirkt hat: Vielleicht")
    print("  braucht der Roboter einen echten Wertwechsel.")
    zwischen = 60 if nach_install > 60 else 100
    print(f"  Es geht auf {zwischen} und gleich wieder auf {ausgangswert}.")
    setze(zwischen)
    time.sleep(2)
    setze(ausgangswert)
    time.sleep(2)
    print(f"      Lautstärke danach: {lautstaerke()}")
    notiere(f"4. Wertwechsel {zwischen} -> {ausgangswert}")

    warte("Lass ihn sprechen.")
    a4 = frage("Und jetzt? (laut / mittel / leise)")
    notiere(f"4. Klang nach Wertwechsel: {a4}")

    # ---------------------------------------------------------------
    schritt(5, "Zum Vergleich: Neustart")
    print("  Nur noch zur Gegenprobe - wenn oben schon etwas geholfen hat,")
    print("  kannst du hier abbrechen (Strg+C).")
    warte("Roboter komplett neu starten, dann warten bis er bereit ist.")
    nach_neustart = lautstaerke()
    print(f"      Lautstärke nach Neustart: {nach_neustart}")
    notiere(f"5. Nach Neustart: Lautstärke={nach_neustart}")

    warte("Lass ihn sprechen.")
    a5 = frage("Und jetzt? (laut / mittel / leise)")
    notiere(f"5. Klang nach Neustart: {a5}")

    # ---------------------------------------------------------------
    print()
    print("=" * 66)
    print("  Ergebnis")
    print("=" * 66)
    for z in protokoll:
        print(f"  {z}")

    jetzt = lautstaerke()
    if jetzt != ausgangswert:
        setze(ausgangswert)
        print(f"\n  Lautstärke auf den Ausgangswert {ausgangswert} zurückgesetzt.")
    else:
        print(f"\n  Lautstärke steht auf {jetzt} - wie am Anfang.")

    ziel = PROJEKT / "Werkzeuge" / f"Lautstärke-Test-{datetime.now():%Y%m%d-%H%M}.txt"
    ziel.write_text("\n".join(protokoll) + "\n", encoding="utf-8")
    print(f"  Protokoll: {ziel.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
