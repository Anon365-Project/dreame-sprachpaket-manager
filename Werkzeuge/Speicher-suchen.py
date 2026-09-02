"""Sucht am Roboter nach einer Speicher- oder Paketlisten-Angabe.

Ausgangslage: Über die Cloud gibt es nur MIoT-Eigenschaften. Die
Referenz-Integration (Tasshack/dreame-vacuum) kennt für den
Sprachdienst 23 Eigenschaften - keine davon nennt Speicher oder listet
installierte Pakete auf. Der r2532v ist aber neuer als alles, was dort
erfasst ist. Dieses Werkzeug sieht deshalb am Gerät selbst nach.

    python Speicher-suchen.py           Sprachdienst vollständig
    python Speicher-suchen.py --breit   dazu alle Dienste 1-30

Es wird ausschließlich gelesen. Keine Eigenschaft wird geschrieben,
keine Aktion ausgelöst - der Roboter tut währenddessen nichts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreamevoice import paths                                  # noqa: E402

PROJEKT = Path(__file__).resolve().parent.parent


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

#: Was die Referenz-Integration für den Sprachdienst kennt. Alles, was
#: der Roboter darüber hinaus liefert, ist interessant - genau danach
#: wird gesucht.
BEKANNT = {
    1: "Lautstärke",
    2: "aktives Sprachpaket",
    3: "Zustand der Installation",
    4: "Auftrag (nur schreiben)",
    5: "Sprachassistent an/aus",
    6: "EMPTY_STAMP (unbekannt)",
    7: "aktueller Ort",
    9: "VOICE_TEST",
    10: "Sprache des Assistenten",
    11: "BAIDU_LOG",
    12: "Antwortwort",
    14: "DreameGPT",
    15: "Hörsprache",
    16: "Zustand der Hörsprache",
    17: "Sprachsteuerung",
    18: "Gegensprechen",
    19: "Weckwort abschalten",
    20: "eigenes Weckwort",
    21: "eigenes Weckwort (Text)",
    22: "Zustand des Weckworts",
    23: "Weckwort-Befehl",
}

#: Woran man eine Speicher- oder Listenangabe erkennen würde.
VERDAECHTIG = ("voice", "personalized", "pack", "storage", "space", "free",
               "used", "total", "size", "capacity", "/data", ".tar", ".gz")

#: So viele Stellen gehen in einer Anfrage. Mehr nimmt der Roboter
#: erfahrungsgemäß nicht zuverlässig an.
BUENDEL = 15


def kurz(wert: object, breite: int = 46) -> str:
    text = repr(wert)
    return text if len(text) <= breite else text[:breite - 3] + "..."


def auffaellig(wert: object) -> str:
    """Sagt, warum ein Wert einen zweiten Blick verdient - oder nichts."""
    if isinstance(wert, (dict, list)):
        return "strukturierte Antwort"
    if isinstance(wert, str):
        klein = wert.lower()
        for wort in VERDAECHTIG:
            if wort in klein:
                return f"enthält '{wort}'"
        if wert.startswith("{") or wert.startswith("["):
            return "sieht nach JSON aus"
    if isinstance(wert, int) and not isinstance(wert, bool) and wert > 100000:
        return "große Zahl - Bytes?"
    return ""


def lesen(cloud, geraet, specs: list) -> dict:
    """Liest gebündelt und fängt Ausfälle je Bündel ab."""
    werte = {}
    for start in range(0, len(specs), BUENDEL):
        teil = specs[start:start + BUENDEL]
        try:
            werte.update(cloud.get_properties(geraet, teil))
        except Exception as exc:                     # noqa: BLE001
            print(f"    (Bündel ab siid {teil[0][0]} piid {teil[0][1]} "
                  f"ohne Antwort: {str(exc).splitlines()[0][:40]})")
    return werte


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    breit = "--breit" in sys.argv

    if ABLAGE is None:
        print("Keine Zugangsdaten gefunden - zuerst in der App anmelden.")
        return 1

    cfg = Config.load()
    cloud = DreameCloud(cfg["account_type"])
    cloud.login_autodetect(cfg["email"], cfg.password, cfg["region"] or "eu")
    geraete = cloud.list_devices(only_vacuums=True)
    if not geraete:
        print("Kein Roboter gefunden.")
        return 1
    geraet = next((g for g in geraete if g.did == cfg["device_id"]), geraete[0])

    print(f"{geraet.name}  ({geraet.model})")
    print()
    print(f"Sprachdienst siid {SIID_VOICE}, Stellen 1 bis 40")
    print("=" * 74)

    treffer = []
    werte = lesen(cloud, geraet, [(SIID_VOICE, p) for p in range(1, 41)])
    for piid in range(1, 41):
        if (SIID_VOICE, piid) not in werte:
            continue
        wert = werte[(SIID_VOICE, piid)]
        name = BEKANNT.get(piid, ">>> in der Referenz unbekannt <<<")
        hinweis = auffaellig(wert)
        print(f"  piid {piid:>2}  {kurz(wert):<48} {name}")
        if hinweis:
            print(f"           ^-- {hinweis}")
            treffer.append((SIID_VOICE, piid, wert, hinweis))

    unbekannt = [p for p in range(1, 41)
                 if (SIID_VOICE, p) in werte and p not in BEKANNT]
    print()
    print(f"  Beantwortet: {len(werte)} Stellen, davon {len(unbekannt)} "
          f"der Referenz unbekannt {unbekannt if unbekannt else ''}")

    if breit:
        print()
        print("Alle Dienste 1 bis 30, Stellen 1 bis 30")
        print("=" * 74)
        specs = [(s, p) for s in range(1, 31) for p in range(1, 31)
                 if s != SIID_VOICE]
        print(f"  {len(specs)} Stellen werden gebündelt abgefragt, "
              f"das dauert eine Weile ...")
        alle = lesen(cloud, geraet, specs)
        for (s, p), wert in sorted(alle.items()):
            hinweis = auffaellig(wert)
            if hinweis:
                print(f"  siid {s:>2} piid {p:>2}  {kurz(wert):<46} <-- {hinweis}")
                treffer.append((s, p, wert, hinweis))
        print(f"  {len(alle)} Stellen beantwortet.")

    print()
    print("=" * 74)
    if treffer:
        print(f"{len(treffer)} Stelle(n) verdienen einen zweiten Blick:")
        for s, p, wert, hinweis in treffer:
            print(f"  siid {s} piid {p}  ({hinweis})")
            print(f"    {wert!r}"[:300])
    else:
        print("Nichts gefunden, was nach Speicherbelegung oder einer Liste")
        print("installierter Pakete aussieht. Dann gibt der Weg über die")
        print("Cloud das nicht her - eine Anzeige wäre geraten, nicht")
        print("gemessen.")
    print()
    print("Es wurde ausschließlich gelesen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
