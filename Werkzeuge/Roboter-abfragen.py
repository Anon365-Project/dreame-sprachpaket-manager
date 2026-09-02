"""Fragt den Roboter aus - nur lesend, es wird nichts verändert.

Beantwortet zwei Fragen:

1. Was liegt in siid 7? Die App kennt piid 2 (aktives Paket), 3 (Zustand)
   und 4 (Auftrag). piid 1 ist unbelegt - bei Dreame liegt dort üblich
   die Lautstärke. Wenn ja, erklärt das, warum der Roboter nach einem
   Stimmwechsel leiser ist.

2. Verrät irgendeine Eigenschaft, welche Pakete gespeichert sind? Dann
   wüssten wir, ob wiederholtes Wechseln sie anhäuft.

    python Roboter-abfragen.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreamevoice import paths                                  # noqa: E402

PROJEKT = Path(__file__).resolve().parent.parent


def _ablage_finden() -> Path | None:
    r"""Wo liegt die Konfiguration mit den Zugangsdaten?

    Die EXE legt ihren Datenordner neben sich ab, also unter dist\Daten.
    Wer aus dem Quellcode startet, hat ihn im Projektordner. Beide
    können nebeneinander existieren - gesucht wird die, in der wirklich
    eine E-Mail steht.
    """
    import json
    for ordner in (PROJEKT / "dist" / "Daten", PROJEKT / "Daten"):
        datei = ordner / "config.json"
        try:
            if json.loads(datei.read_text(encoding="utf-8")).get("email"):
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

    if ABLAGE is None:
        print("Keine Konfiguration mit Zugangsdaten gefunden.")
        print("Gesucht in:")
        print(f"  {PROJEKT / 'dist' / 'Daten' / 'config.json'}")
        print(f"  {PROJEKT / 'Daten' / 'config.json'}")
        print()
        print("Melde dich zuerst in der App an.")
        return 1
    print(f"Konfiguration: {ABLAGE / 'config.json'}")

    cfg = Config.load()
    if not cfg["email"]:
        print("Dort steht keine E-Mail-Adresse.")
        return 1
    if not cfg.password:
        print("Kein Passwort im Windows-Tresor - in der App neu anmelden")
        print("und dabei 'Zugangsdaten merken' angehakt lassen.")
        return 1

    cloud = DreameCloud(cfg["account_type"])
    region = cloud.login_autodetect(cfg["email"], cfg.password,
                                    cfg["region"] or "eu")
    geraete = cloud.list_devices(only_vacuums=True)
    if not geraete:
        print("Kein Roboter im Konto gefunden.")
        return 1
    geraet = next((g for g in geraete if g.did == cfg["device_id"]), geraete[0])
    print(f"{geraet.name}  ({geraet.model})   Region {region.upper()}")
    print()

    print("Sprachdienst, siid 7")
    print("-" * 66)
    bedeutung = {
        1: "unbelegt in der App  <-- Lautstärke?",
        2: "aktives Sprachpaket",
        3: "Zustand der Installation",
        4: "Auftrag (nur schreiben)",
    }
    for piid in range(1, 9):
        try:
            wert = cloud.get_property(geraet, SIID_VOICE, piid)
            text = repr(wert)
            if len(text) > 40:
                text = text[:37] + "..."
            print(f"  piid {piid}  {text:<42} {bedeutung.get(piid, '')}")
        except Exception as exc:                     # noqa: BLE001
            kurz = str(exc).split("\n")[0][:38]
            print(f"  piid {piid}  {'-':<42} {kurz}")

    # Ein paar Dienste, in denen bei Dreame sonst noch Ton- oder
    # Speicherangaben stehen. Nur lesen, nur zur Orientierung.
    print()
    print("Weitere Dienste (Stichprobe)")
    print("-" * 66)
    for siid in (2, 3, 4, 5, 6, 8, 9, 10):
        treffer = []
        for piid in range(1, 6):
            try:
                wert = cloud.get_property(geraet, siid, piid)
            except Exception:                        # noqa: BLE001
                continue
            if wert is None:
                continue
            text = repr(wert)
            treffer.append(f"piid {piid}={text[:26]}")
        if treffer:
            print(f"  siid {siid:>2}  " + "  ".join(treffer[:4]))

    print()
    print("Nichts wurde verändert - alle Aufrufe waren Abfragen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
