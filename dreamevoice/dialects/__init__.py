"""Die Textsammlungen der einzelnen Dialekte.

Jedes Modul enthält ein Wörterbuch `TEXTE`, das Ansage-Nummern des X50
Ultra Complete auf den jeweiligen Dialekttext abbildet. Alle Dialekte
decken dieselben Nummern ab, damit sich die Pakete direkt vergleichen
lassen.

Die Texte sind neu geschrieben, nicht übersetzt: eine wörtliche
Übertragung klingt in keinem Dialekt natürlich. Geschrieben wird
lautgetreu, weil die Sprachausgabe der Schreibweise folgt - "isch hab"
klingt anders als "ich habe", selbst bei einer hochdeutschen Stimme.
"""

from __future__ import annotations

from typing import Dict, List

from . import bayerisch, berlinerisch, hessisch, koelsch, saechsisch, schwaebisch, wienerisch

MODULES = [bayerisch, hessisch, schwaebisch, saechsisch, berlinerisch,
           wienerisch, koelsch]


def all_texts() -> Dict[str, Dict[int, str]]:
    return {m.KEY: m.TEXTE for m in MODULES}


def ids() -> List[int]:
    """Die Ansage-Nummern, die alle Dialekte abdecken."""
    return sorted(bayerisch.TEXTE.keys())
