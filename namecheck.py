"""Sucht Namen, die benutzt, aber nirgends definiert oder importiert werden.

Der Anlass: `show_info` wurde in `tab_store.py` benutzt, stand aber nicht in
der Import-Zeile. Python merkt das erst, wenn die Zeile wirklich ausgeführt
wird - hier beim Speichern geänderter Dialekttexte. Ein Tippfehler in einem
selten benutzten Zweig bleibt so beliebig lange unentdeckt.

Die Prüfung ist bewusst grob: alle Namen, die eine Datei irgendwo bindet
(Importe, Zuweisungen, Funktionen, Klassen, Parameter, Schleifenvariablen),
kommen in einen Topf, dazu die eingebauten Namen. Was dann noch übrig
bleibt, ist ein echter Fund. Verschachtelte Gültigkeitsbereiche werden also
absichtlich nicht auseinandergehalten - dadurch gibt es keine Fehlalarme,
nur eventuell übersehene Fälle. Für den Zweck reicht das.
"""

from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


def _gebundene_namen(baum: ast.AST) -> Set[str]:
    """Alles, was irgendwo in der Datei einen Namen bindet."""
    namen: Set[str] = set()

    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.Import, ast.ImportFrom)):
            for alias in knoten.names:
                namen.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            namen.add(knoten.name)
        elif isinstance(knoten, (ast.Global, ast.Nonlocal)):
            namen.update(knoten.names)
        elif isinstance(knoten, ast.Name) and isinstance(knoten.ctx,
                                                         (ast.Store, ast.Del)):
            namen.add(knoten.id)
        elif isinstance(knoten, ast.arg):
            namen.add(knoten.arg)
        elif isinstance(knoten, ast.ExceptHandler) and knoten.name:
            namen.add(knoten.name)
        elif isinstance(knoten, ast.MatchAs) and knoten.name:
            namen.add(knoten.name)
        elif isinstance(knoten, ast.MatchStar) and knoten.name:
            namen.add(knoten.name)
        elif isinstance(knoten, ast.MatchMapping) and knoten.rest:
            namen.add(knoten.rest)

    return namen


def pruefe_datei(pfad: Path) -> List[Tuple[int, str]]:
    """Rückgabe: Liste aus (Zeilennummer, unbekannter Name)."""
    try:
        # utf-8-sig: einige Dateien tragen eine Byte-Order-Markierung, die
        # ast.parse sonst als unerlaubtes Zeichen ansieht.
        quelle = pfad.read_text(encoding="utf-8-sig")
        baum = ast.parse(quelle, filename=str(pfad))
    except (OSError, SyntaxError) as exc:
        return [(0, f"nicht lesbar: {exc}")]

    bekannt = _gebundene_namen(baum) | set(dir(builtins)) | {
        "__file__", "__name__", "__doc__", "__package__", "__spec__",
    }

    funde: Dict[str, int] = {}
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Name) and isinstance(knoten.ctx, ast.Load):
            if knoten.id not in bekannt:
                funde.setdefault(knoten.id, knoten.lineno)

    return sorted((zeile, name) for name, zeile in funde.items())


def pruefe_ordner(wurzel: Path) -> Dict[Path, List[Tuple[int, str]]]:
    ergebnis: Dict[Path, List[Tuple[int, str]]] = {}
    for pfad in sorted(wurzel.rglob("*.py")):
        if "__pycache__" in pfad.parts or "build" in pfad.parts:
            continue
        funde = pruefe_datei(pfad)
        if funde:
            ergebnis[pfad] = funde
    return ergebnis


def main() -> int:
    wurzel = Path(__file__).resolve().parent
    ziele = [wurzel / "dreamevoice", wurzel / "main.py", wurzel / "selftest.py"]

    alle: Dict[Path, List[Tuple[int, str]]] = {}
    for ziel in ziele:
        if ziel.is_dir():
            alle.update(pruefe_ordner(ziel))
        elif ziel.is_file():
            funde = pruefe_datei(ziel)
            if funde:
                alle[ziel] = funde

    geprueft = sum(1 for _ in (wurzel / "dreamevoice").rglob("*.py")
                   if "__pycache__" not in _.parts) + 2
    print(f"{geprueft} Dateien geprüft.")

    if not alle:
        print("Keine unbekannten Namen gefunden.")
        return 0

    for pfad, funde in alle.items():
        print(f"\n{pfad.relative_to(wurzel)}")
        for zeile, name in funde:
            print(f"  Zeile {zeile}: {name}")
    print(f"\n{sum(len(f) for f in alle.values())} Fundstellen.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
