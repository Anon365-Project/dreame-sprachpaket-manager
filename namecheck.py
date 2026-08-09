"""Zwei statische Prüfungen, die Python selbst erst zur Laufzeit macht.

**Unbekannte Namen.** Anlass: `show_info` wurde in `tab_store.py` benutzt,
stand aber nicht in der Import-Zeile. Python merkt das erst, wenn die Zeile
wirklich ausgeführt wird - hier beim Speichern geänderter Dialekttexte. Ein
Tippfehler in einem selten benutzten Zweig bleibt so beliebig lange
unentdeckt.

Die Prüfung ist bewusst grob: alle Namen, die eine Datei irgendwo bindet
(Importe, Zuweisungen, Funktionen, Klassen, Parameter, Schleifenvariablen),
kommen in einen Topf, dazu die eingebauten Namen. Was dann noch übrig
bleibt, ist ein echter Fund. Verschachtelte Gültigkeitsbereiche werden also
absichtlich nicht auseinandergehalten - dadurch gibt es keine Fehlalarme,
nur eventuell übersehene Fälle.

**Unbekannte Schlüsselwörter.** Anlass: `dialect.generate(out_name=...)` -
den Parameter gab es gar nicht. Der Name `out_name` ist gültig, deshalb
schlug die erste Prüfung nicht an; erst beim Erzeugen eines Pakets kam
"unexpected keyword argument". Geprüft werden Aufrufe der Form
`modul.funktion(...)` in Module dieses Projekts: Nimmt die Funktion das
Schlüsselwort überhaupt entgegen?
"""

from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


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


# --------------------------------------------------------------------------
# Schlüsselwörter beim Aufruf
# --------------------------------------------------------------------------

def _signaturen(wurzel: Path) -> Dict[str, Dict[str, Set[str]]]:
    """{modulname: {funktionsname: erlaubte Schlüsselwörter}}.

    Nimmt eine Funktion `**kwargs` entgegen, wird sie mit None vermerkt -
    dann ist jedes Schlüsselwort erlaubt.
    """
    raus: Dict[str, Dict[str, Set[str]]] = {}
    for pfad in sorted(wurzel.rglob("*.py")):
        if "__pycache__" in pfad.parts:
            continue
        try:
            baum = ast.parse(pfad.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError):
            continue
        modul: Dict[str, Set[str]] = {}
        for knoten in baum.body:           # nur oberste Ebene: modul.funktion()
            if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            a = knoten.args
            if a.kwarg is not None:        # **kwargs schluckt alles
                modul[knoten.name] = None
                continue
            erlaubt = {p.arg for p in
                       list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)}
            modul[knoten.name] = erlaubt
        raus[pfad.stem] = modul
    return raus


def _eindeutige_namen(wurzel: Path) -> Dict[str, Set[str]]:
    """Funktionsnamen, die es im Projekt nur einmal gibt.

    Nur die lassen sich bei einem Aufruf ohne Modulpräfix sicher
    zuordnen - `run_async(...)` etwa. Kommt ein Name in mehreren Modulen
    vor, wird er uebergangen, damit es keine Fehlalarme gibt.
    """
    zaehler: Dict[str, List[Set[str]]] = {}
    for modul in _signaturen(wurzel).values():
        for name, erlaubt in modul.items():
            zaehler.setdefault(name, []).append(erlaubt)
    return {name: liste[0] for name, liste in zaehler.items()
            if len(liste) == 1 and liste[0] is not None}


def pruefe_aufrufe(wurzel: Path) -> Dict[Path, List[Tuple[int, str]]]:
    """Sucht Aufrufe mit einem Schlüsselwort, das die Funktion nicht kennt.

    Erfasst zwei Formen:
      * `modul.funktion(schluessel=...)`
      * `funktion(schluessel=...)` bei direkt importierten Funktionen,
        deren Name im Projekt eindeutig ist
    """
    bekannt = _signaturen(wurzel)
    einzeln = _eindeutige_namen(wurzel)
    funde: Dict[Path, List[Tuple[int, str]]] = {}

    for pfad in sorted(wurzel.rglob("*.py")):
        if "__pycache__" in pfad.parts:
            continue
        try:
            baum = ast.parse(pfad.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError):
            continue

        # Was diese Datei direkt importiert hat: from ... import name
        importiert: Set[str] = set()
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.ImportFrom):
                for alias in knoten.names:
                    if alias.asname is None:
                        importiert.add(alias.name)

        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue

            ziel = knoten.func
            if isinstance(ziel, ast.Attribute) and isinstance(ziel.value, ast.Name):
                modul = bekannt.get(ziel.value.id)
                if modul is None:
                    continue
                erlaubt = modul.get(ziel.attr, "fehlt")
                beschriftung = f"{ziel.value.id}.{ziel.attr}()"
            elif isinstance(ziel, ast.Name) and ziel.id in importiert:
                erlaubt = einzeln.get(ziel.id, "fehlt")
                beschriftung = f"{ziel.id}()"
            else:
                continue

            if erlaubt in ("fehlt", None):
                continue                   # unbekannte Funktion oder **kwargs

            for schluesselwort in knoten.keywords:
                if schluesselwort.arg is None:      # **etwas
                    break
                if schluesselwort.arg not in erlaubt:
                    funde.setdefault(pfad, []).append(
                        (knoten.lineno,
                         f"{beschriftung} kennt kein "
                         f"'{schluesselwort.arg}'"))
    return funde


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

    # Zweite Prüfung: Schlüsselwörter, die es in der Funktion nicht gibt.
    for pfad, funde in pruefe_aufrufe(wurzel / "dreamevoice").items():
        alle.setdefault(pfad, []).extend(funde)

    geprueft = sum(1 for _ in (wurzel / "dreamevoice").rglob("*.py")
                   if "__pycache__" not in _.parts) + 2
    print(f"{geprueft} Dateien geprüft.")

    if not alle:
        print("Keine unbekannten Namen, keine unbekannten Schlüsselwörter.")
        return 0

    for pfad, funde in sorted(alle.items()):
        print(f"\n{pfad.relative_to(wurzel)}")
        for zeile, name in sorted(funde):
            print(f"  Zeile {zeile}: {name}")
    print(f"\n{sum(len(f) for f in alle.values())} Fundstellen.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
