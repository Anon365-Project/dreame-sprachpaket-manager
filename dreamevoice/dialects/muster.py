"""Schematische Ansagen, die sich aus einem Muster erzeugen lassen.

Von den 558 Ansagen des X50 sind 117 reine Fleissarbeit: 101-mal
"Akkustand X Prozent" und 16 Raumbestätigungen, die sich nur im Raumnamen
unterscheiden. Die von Hand zu schreiben wäre in sieben Dialekten
sinnlose Tipparbeit - und fehleranfällig obendrein.

Jeder Dialekt hinterlegt stattdessen zwei Satzmuster und die Raumnamen in
seiner Schreibweise; den Rest erzeugt dieses Modul.
"""

from __future__ import annotations

from typing import Dict

# Ansage 526 = 100 %, Ansage 626 = 0 %. Dazwischen jeweils ein Prozent
# weniger - nachgeprüft am offiziellen deutschen Paket.
AKKU_ERSTE_ID = 526
AKKU_LETZTE_ID = 626

# Die Raumbestätigungen des Sprachassistenten.
RAUM_IDS = {
    492: "wohnzimmer",
    493: "schlafzimmer",
    494: "hauptschlafzimmer",
    495: "gaestezimmer",
    496: "arbeitszimmer",
    497: "kueche",
    498: "esszimmer",
    499: "bad",
    500: "balkon",
    501: "flur",
    502: "hauswirtschaftsraum",
    503: "abstellraum",
    504: "salon",
    505: "buero",
    506: "gym",
    507: "freizeitraum",
}


def akku_prozent(sound_id: int) -> int:
    """Der Ladestand, den eine Akku-Ansage meldet."""
    return AKKU_LETZTE_ID - sound_id


def erzeuge(akku_muster: str, raum_muster: str,
            raum_namen: Dict[str, str]) -> Dict[int, str]:
    """Baut die schematischen Ansagen für einen Dialekt.

    `akku_muster` enthält `{p}` als Platzhalter für die Prozentzahl,
    `raum_muster` enthält `{raum}` für den Raumnamen.
    """
    texte: Dict[int, str] = {}

    for sound_id in range(AKKU_ERSTE_ID, AKKU_LETZTE_ID + 1):
        texte[sound_id] = akku_muster.format(p=akku_prozent(sound_id))

    for sound_id, schluessel in RAUM_IDS.items():
        name = raum_namen.get(schluessel)
        if name:
            texte[sound_id] = raum_muster.format(raum=name)

    return texte
