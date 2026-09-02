"""Liest und setzt die Lautstärke des Roboters (siid 7, piid 1).

    python Lautstärke.py             nur lesen
    python Lautstärke.py 50          auf 50 setzen
    python Lautstärke.py --testton   nur den Testton auslösen
    python Lautstärke.py 100 --testton   setzen und danach hören

Der vorherige Wert wird immer zuerst gelesen und angezeigt, damit man
ihn zurückstellen kann.

Der Testton ist die Aktion siid 7 / aiid 2 der offiziellen
MIoT-Spezifikation. Die Referenz-Integrationen lösen sie nach jedem
Schreiben der Lautstärke aus - offenbar übernimmt die Firmware den
Wert erst dadurch hörbar.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreamevoice import paths                                  # noqa: E402

PROJEKT = Path(__file__).resolve().parent.parent
PIID_LAUTSTAERKE = 1


def _ablage_finden() -> Path | None:
    for ordner in (PROJEKT / "dist" / "Daten", PROJEKT / "Daten"):
        try:
            if json.loads((ordner / "config.json").read_text(
                    encoding="utf-8")).get("email"):
                return ordner
        except (OSError, ValueError):
            continue
    return None


ABLAGE = _ablage_finden()
if ABLAGE is not None:
    paths.data_dir = lambda: ABLAGE

from dreamevoice.cloud import DreameCloud, SIID_VOICE          # noqa: E402
from dreamevoice.config import Config                          # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    argumente = [a for a in sys.argv[1:] if a != "--testton"]
    testton = "--testton" in sys.argv

    neu = None
    if argumente:
        try:
            neu = int(argumente[0])
        except ValueError:
            print(f"Keine Zahl: {argumente[0]}")
            return 1
        if not 0 <= neu <= 100:
            print("Erlaubt sind 0 bis 100.")
            return 1

    if ABLAGE is None:
        print("Keine Zugangsdaten gefunden - in der App anmelden.")
        return 1

    cfg = Config.load()
    cloud = DreameCloud(cfg["account_type"])
    cloud.login_autodetect(cfg["email"], cfg.password, cfg["region"] or "eu")
    geraete = cloud.list_devices(only_vacuums=True)
    if not geraete:
        print("Kein Roboter gefunden.")
        return 1
    geraet = next((g for g in geraete if g.did == cfg["device_id"]), geraete[0])

    vorher = cloud.get_property(geraet, SIID_VOICE, PIID_LAUTSTAERKE)
    print(f"{geraet.name}")
    print(f"  Lautstärke jetzt:  {vorher}")

    if neu is None and not testton:
        print()
        print("  (nur gelesen, nichts verändert)")
        return 0

    if neu is None:
        print("  Testton wird ausgelöst ...")
        cloud.play_voice_test(geraet)
        print()
        print("  Der Roboter sollte sich jetzt gemeldet haben.")
        return 0

    print(f"  setze auf:          {neu}")
    cloud.set_property(geraet, SIID_VOICE, PIID_LAUTSTAERKE, neu)

    nachher = cloud.get_property(geraet, SIID_VOICE, PIID_LAUTSTAERKE)
    print(f"  Lautstärke danach: {nachher}")
    print()
    if testton:
        print("  Testton wird ausgelöst ...")
        cloud.play_voice_test(geraet)
        print()

    if nachher == neu:
        print(f"  Übernommen. Zurücksetzen mit:  python Lautstärke.py {vorher}")
    else:
        print(f"  Der Roboter hat den Wert NICHT übernommen (steht auf {nachher}).")
        print("  Dann ist piid 1 vermutlich nicht die Lautstärke.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
