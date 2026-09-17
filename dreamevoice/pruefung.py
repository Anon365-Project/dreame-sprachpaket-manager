"""Fremde Pakete prüfen, bevor die App sie anfasst.

Warum das nötig ist, obwohl Windows einen Virenscanner hat: **Der
Defender sucht Windows-Schädlinge.** Ein Sprachpaket landet aber auf
einem Saugroboter, und der läuft unter Linux. Ein ELF-Programm oder ein
Shell-Skript zwischen den Ansagen ist für Windows eine unauffällige
Datei - für den Roboter wäre es ausführbarer Code.

Deshalb wird hier nicht nach Bekanntem gesucht, sondern gegen ein
**Sollbild** geprüft: In einem Sprachpaket stecken Tondateien und ein
paar Steuerdateien. Sonst nichts. Alles andere hat dort nichts zu
suchen - auch etwas, das noch nie jemand gesehen hat.

Geprüft wird rein lesend: Es wird nichts entpackt, nichts ausgeführt,
nichts ins Netz geschickt. Die Idee und ein Teil der Merkmale stammen
aus dem Virenscanner-Projekt desselben Autors; hier steht bewusst nur
der Teil, der für Sprachpakete zählt.

Was hier NICHT passiert: Es gibt keine Stufe "sicher". Wenn nichts
gefunden wurde, heißt das nur das - nicht, dass nichts drin ist.
"""

from __future__ import annotations

import logging
import stat
import tarfile
import zipfile
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import List, Optional, Tuple

_LOG = logging.getLogger(__name__)


class Stufe(IntEnum):
    """Wie ernst ein Fund ist. Die Reihenfolge zählt: das Maximum gewinnt."""

    NICHTS = 0
    #: Erwähnenswert, für sich genommen harmlos.
    HINWEIS = 1
    #: Man sollte wissen, woher das Paket kommt, bevor man es benutzt.
    VERDACHT = 2
    #: Nur mit Absicht zu erklären - so etwas wird nicht eingelesen.
    GEFAHR = 3


#: Kennzeichen am Dateianfang, die in einem Sprachpaket nichts zu suchen
#: haben. `elf` steht hier an erster Stelle: Das ist das Format, das ein
#: Saugroboter wirklich ausführen könnte.
_AUSFUEHRBAR: List[Tuple[bytes, str]] = [
    (b"\x7fELF", "ein Linux-Programm"),
    (b"MZ", "ein Windows-Programm"),
    (b"\xfe\xed\xfa", "ein macOS-Programm"),
    (b"\xcf\xfa\xed\xfe", "ein macOS-Programm"),
    (b"\xca\xfe\xba\xbe", "ein Java- oder macOS-Programm"),
    (b"#!", "ein Skript mit Interpreter-Zeile"),
    (b"\x1b\x5b", "eine Datei mit Terminal-Steuerzeichen"),
]

#: Endungen, die in einem Sprachpaket nie vorkommen und ausgeführt
#: werden können - auf dem PC oder auf dem Roboter.
_GEFAEHRLICHE_ENDUNGEN = {
    ".exe", ".dll", ".sys", ".scr", ".com", ".pif", ".msi", ".msp",
    ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse",
    ".wsf", ".wsh", ".hta", ".lnk", ".url", ".reg", ".jar", ".apk",
    ".sh", ".bash", ".zsh", ".py", ".pl", ".rb", ".elf", ".so", ".ko",
    ".service", ".desktop",
}

#: Unsichtbare Zeichen, mit denen sich eine Endung verstecken lässt.
_TARNZEICHEN = {
    "\u202e": "dreht die Leserichtung um",
    "\u202d": "dreht die Leserichtung um",
    "\u200b": "Breite null",
    "\u200e": "unsichtbare Leserichtungsmarke",
    "\u200f": "unsichtbare Leserichtungsmarke",
    "\u2066": "unsichtbare Leserichtungsmarke",
    "\u2067": "unsichtbare Leserichtungsmarke",
    "\u0000": "Nullzeichen",
}

#: Was in einem Sprachpaket sein darf.
_ERLAUBTE_ENDUNGEN = {".ogg", ".wav", ".mp3", ".m4a", ".aac", ".flac",
                      ".opus", ".wma", ".json", ".txt", ".md"}

#: Tondateien müssen auch Ton sein. Die Kennzeichen der Formate, die die
#: App entgegennimmt.
_TON_KENNZEICHEN = [b"OggS", b"RIFF", b"ID3", b"\xff\xfb", b"\xff\xf3",
                    b"\xff\xf2", b"\xff\xf1", b"fLaC", b"\x00\x00\x00",
                    b"\x1a\x45\xdf\xa3"]

#: Kennzeichen von Archiven. Ein Sprachpaket enthält keine - taucht
#: doch eines auf, wird es geöffnet und genauso geprüft wie das äußere.
#: Sonst genügte es, die Schaddatei einmal einzupacken.
_ARCHIV_KENNZEICHEN: List[Tuple[bytes, str]] = [
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"Rar!\x1a\x07", "rar"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"MSCF", "cab"),
]

#: Formate, die diese App nicht öffnen kann. Sie werden gemeldet, statt
#: stillschweigend übergangen zu werden - ungeprüft ist nicht harmlos.
_NICHT_OEFFENBAR = {"rar", "7z", "cab"}

#: So tief wird in Archive im Archiv hineingesehen. Drei Ebenen decken
#: alles ab, was je an Sprachpaketen kursiert; tiefer geschachtelt ist
#: für sich genommen schon ein Befund.
MAX_TIEFE = 3

#: So viel wird aus einem inneren Archiv höchstens gelesen. Auch das
#: begrenzt, was eine Archivbombe anrichten kann: Sie fliegt vorher auf.
MAX_INNEN_BYTES = 64 * 1024 * 1024

#: Ab hier gilt ein Archiv als Bombe: Es verspricht mehr als das
#: Zweihundertfache seiner Größe und über 200 MB.
_BOMBE_VERHAELTNIS = 200
_BOMBE_BYTES = 200 * 1024 * 1024

#: So viele Einträge werden angesehen. Ein Sprachpaket hat gut 600.
_MAX_EINTRAEGE = 5000
#: So viele Bytes werden je Eintrag gelesen, um den Typ zu bestimmen.
_PROBE = 8


@dataclass
class Fund:
    """Ein einzelner Befund - in einem Satz, den ein Laie versteht."""

    stufe: Stufe
    was: str
    bedeutung: str


@dataclass
class Befund:
    """Das Ergebnis einer Prüfung."""

    stufe: Stufe = Stufe.NICHTS
    funde: List[Fund] = field(default_factory=list)
    eintraege: int = 0
    #: Fehlgeschlagene Prüfung ist kein Freispruch - hier steht, warum.
    luecke: str = ""

    @property
    def sauber(self) -> bool:
        """Nichts gefunden - ausdrücklich nicht dasselbe wie "sicher"."""
        return self.stufe == Stufe.NICHTS and not self.luecke

    def melden(self, stufe: Stufe, was: str, bedeutung: str) -> None:
        # Jede Art von Fund nur einmal: Ein Archiv mit 300 Skripten
        # ergibt sonst 300 gleichlautende Zeilen.
        if not any(f.was == was for f in self.funde):
            self.funde.append(Fund(stufe, was, bedeutung))
        self.stufe = max(self.stufe, stufe)

    def text(self) -> str:
        """Kurzer Bericht für Protokoll und Rückfrage."""
        zeilen = [f"- {f.was}: {f.bedeutung}" for f in self.funde]
        if self.luecke:
            zeilen.append(f"- Nicht zu Ende geprüft: {self.luecke}")
        return "\n".join(zeilen)


# --------------------------------------------------------------------------
# Namen
# --------------------------------------------------------------------------

def _ausbruch(name: str) -> bool:
    """Bricht dieser Name beim Auspacken aus dem Zielordner aus?"""
    glatt = name.replace("\\", "/")
    if glatt.startswith("/") or glatt.startswith("//"):
        return True
    if len(glatt) >= 2 and glatt[1] == ":":
        return True
    return any(teil == ".." for teil in glatt.split("/"))


def _name_pruefen(befund: Befund, name: str) -> None:
    kurz = Path(name.replace("\\", "/")).name
    endung = Path(kurz).suffix.lower()

    if _ausbruch(name):
        befund.melden(
            Stufe.GEFAHR, "Eintrag bricht aus dem Zielordner aus",
            f"'{name}' würde beim Auspacken an anderer Stelle landen. "
            f"Ein ehrliches Sprachpaket tut das nie.")
    for zeichen, bedeutung in _TARNZEICHEN.items():
        if zeichen in name:
            befund.melden(
                Stufe.VERDACHT, "Unsichtbares Zeichen im Dateinamen",
                f"U+{ord(zeichen):04X} ({bedeutung}) versteckt, wie die "
                f"Datei wirklich heißt.")
    if endung in _GEFAEHRLICHE_ENDUNGEN:
        befund.melden(
            Stufe.GEFAHR, f"Ausführbare Datei im Paket ({endung})",
            f"'{kurz}' ist keine Ansage. In einem Sprachpaket stehen "
            f"Tondateien und ein paar Steuerdateien - sonst nichts.")
    teile = kurz.split(".")
    if len(teile) >= 3 and f".{teile[-1].lower()}" in _GEFAEHRLICHE_ENDUNGEN:
        befund.melden(
            Stufe.VERDACHT, "Doppelte Dateiendung",
            f"'{kurz}' sieht vorne harmlos aus, endet aber auf "
            f".{teile[-1].lower()}.")
    elif endung and endung not in _ERLAUBTE_ENDUNGEN:
        befund.melden(
            Stufe.HINWEIS, f"Unerwarteter Dateityp im Paket ({endung})",
            "Er wird beim Einlesen übergangen - im Paket landet er nicht.")


def _archivart(kopf: bytes) -> str:
    """Ist das hier selbst wieder ein Archiv? Dann welches?"""
    for muster, art in _ARCHIV_KENNZEICHEN:
        if kopf.startswith(muster):
            return art
    return ""


def _inhalt_pruefen(befund: Befund, name: str, kopf: bytes) -> None:
    """Was am Anfang der Datei steht, zählt mehr als ihr Name."""
    if not kopf:
        return
    for muster, was in _AUSFUEHRBAR:
        if kopf.startswith(muster):
            befund.melden(
                Stufe.GEFAHR, f"Programmcode im Paket ({was})",
                f"'{name}' beginnt wie {was}. Auf dem Roboter läuft "
                f"Linux - solcher Inhalt hat in einem Sprachpaket nichts "
                f"zu suchen.")
            return
    endung = Path(name.replace("\\", "/")).name.rsplit(".", 1)
    if len(endung) == 2 and f".{endung[1].lower()}" in {
            ".ogg", ".wav", ".mp3", ".m4a", ".flac", ".opus", ".aac", ".wma"}:
        if not any(kopf.startswith(k) for k in _TON_KENNZEICHEN):
            befund.melden(
                Stufe.VERDACHT, "Tondatei ohne Toninhalt",
                f"'{name}' heißt wie eine Aufnahme, beginnt aber nicht "
                f"wie eine. Entweder ist sie beschädigt - oder sie ist "
                f"etwas anderes.")


def _bombe_pruefen(befund: Befund, gepackt: int, entpackt: int) -> None:
    if entpackt <= _BOMBE_BYTES or not gepackt:
        return
    verhaeltnis = entpackt / gepackt
    if verhaeltnis >= _BOMBE_VERHAELTNIS:
        befund.melden(
            Stufe.GEFAHR, "Das Archiv bläht sich beim Auspacken auf",
            f"Aus {gepackt / 1048576:.1f} MB würden "
            f"{entpackt / 1048576:.0f} MB. So etwas füllt die Festplatte, "
            f"statt Ansagen zu liefern.")


# --------------------------------------------------------------------------
# Die Prüfungen
# --------------------------------------------------------------------------

def pruefe_datei(pfad: Path) -> Befund:
    """Eine einzelne Audiodatei, wie sie einzeln zugewiesen wird."""
    befund = Befund()
    pfad = Path(pfad)
    try:
        with pfad.open("rb") as fh:
            kopf = fh.read(_PROBE)
    except OSError as exc:
        befund.luecke = f"Die Datei ließ sich nicht lesen ({exc})."
        return befund
    befund.eintraege = 1
    _name_pruefen(befund, pfad.name)
    _inhalt_pruefen(befund, pfad.name, kopf)
    return befund


def _zip_pruefen(befund: Befund, pfad: Path, tiefe: int = 0) -> None:
    gepackt = pfad.stat().st_size
    entpackt = 0
    with zipfile.ZipFile(pfad) as zf:
        infos = zf.infolist()
        if len(infos) > _MAX_EINTRAEGE:
            befund.melden(
                Stufe.VERDACHT, "Sehr viele Einträge",
                f"{len(infos)} Dateien - ein Sprachpaket hat gut 600.")
        for info in infos[:_MAX_EINTRAEGE]:
            befund.eintraege += 1
            _name_pruefen(befund, info.filename)
            if info.is_dir():
                continue
            entpackt += info.file_size
            art = info.external_attr >> 16
            if art and stat.S_ISLNK(art):
                befund.melden(
                    Stufe.GEFAHR, "Verweis auf eine andere Datei im Archiv",
                    f"'{info.filename}' ist kein Inhalt, sondern zeigt "
                    f"woanders hin. Das ist ein Weg, Dateien außerhalb "
                    f"des Zielordners zu treffen.")
                continue
            if info.flag_bits & 0x1:
                befund.melden(
                    Stufe.VERDACHT, "Verschlüsselter Eintrag im Archiv",
                    f"'{info.filename}' ist mit einem Kennwort geschützt "
                    f"und lässt sich nicht ansehen. Ein Sprachpaket hat "
                    f"dafür keinen Grund; Schadsoftware wird oft so "
                    f"versteckt.")
                continue
            try:
                with zf.open(info) as strom:
                    daten = strom.read(_PROBE)
                    _inhalt_pruefen(befund, info.filename, daten)
                    art = _archivart(daten)
                    if art:
                        _innen_pruefen(befund, info.filename, art, tiefe,
                                       lambda: zf.open(info))
            except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError) as exc:
                befund.luecke = f"Ein Eintrag ließ sich nicht lesen ({exc})."
    _bombe_pruefen(befund, gepackt, entpackt)


def _tar_pruefen(befund: Befund, pfad: Path, tiefe: int = 0) -> None:
    gepackt = pfad.stat().st_size
    entpackt = 0
    with tarfile.open(pfad, "r:*") as tf:
        for nummer, member in enumerate(tf, start=1):
            if nummer > _MAX_EINTRAEGE:
                befund.melden(
                    Stufe.VERDACHT, "Sehr viele Einträge",
                    f"mehr als {_MAX_EINTRAEGE} - ein Sprachpaket hat "
                    f"gut 600.")
                break
            befund.eintraege += 1
            _name_pruefen(befund, member.name)
            if member.issym() or member.islnk():
                befund.melden(
                    Stufe.GEFAHR, "Verweis auf eine andere Datei im Archiv",
                    f"'{member.name}' zeigt auf '{member.linkname}'. So "
                    f"lassen sich beim Auspacken fremde Dateien treffen.")
                continue
            if member.isdev() or member.isfifo():
                befund.melden(
                    Stufe.GEFAHR, "Gerätedatei im Archiv",
                    f"'{member.name}' ist keine Datei, sondern ein "
                    f"Geräteknoten. In einem Sprachpaket gibt es so "
                    f"etwas nicht.")
                continue
            if not member.isfile():
                continue
            entpackt += member.size
            try:
                strom = tf.extractfile(member)
                if strom is not None:
                    daten = strom.read(_PROBE)
                    _inhalt_pruefen(befund, member.name, daten)
                    art = _archivart(daten)
                    if art:
                        _innen_pruefen(befund, member.name, art, tiefe,
                                       lambda m=member: tf.extractfile(m))
            except (tarfile.TarError, OSError, EOFError) as exc:
                befund.luecke = f"Ein Eintrag ließ sich nicht lesen ({exc})."
    _bombe_pruefen(befund, gepackt, entpackt)


def _innen_pruefen(befund: Befund, name: str, art: str, tiefe: int,
                   oeffnen) -> None:
    """Prüft ein Archiv, das in einem Archiv steckt.

    Ohne das genügte es, die Schaddatei einmal mehr einzupacken: Die
    äußere Prüfung sähe dann nur ein unauffälliges "zusatz.zip".

    Das innere Archiv wird dafür in eine temporäre Datei geschrieben -
    bis zu einer Grenze, die eine Archivbombe vorher auffliegen lässt -
    und danach sofort gelöscht. Ausgepackt wird nichts.
    """
    befund.melden(
        Stufe.HINWEIS, "Archiv im Archiv",
        f"'{name}' ist selbst ein Archiv ({art}). Es wird mitgeprüft; "
        f"in einem Sprachpaket hat es nichts zu suchen.")

    if art in _NICHT_OEFFENBAR:
        befund.melden(
            Stufe.VERDACHT, f"Nicht prüfbares Archiv im Paket ({art})",
            f"'{name}' lässt sich mit Bordmitteln nicht öffnen. Was "
            f"darin steckt, ist ungeprüft - das ist kein Freispruch.")
        return

    if tiefe + 1 >= MAX_TIEFE:
        befund.melden(
            Stufe.VERDACHT, "Zu tief geschachtelte Archive",
            f"Bei '{name}' ist die {MAX_TIEFE}. Ebene erreicht. So weit "
            f"schachtelt niemand aus Versehen.")
        return

    import tempfile

    tmp = None
    try:
        strom = oeffnen()
        if strom is None:
            return
        with strom:
            with tempfile.NamedTemporaryFile(prefix="dreamevoice_pruef_",
                                             suffix=".bin",
                                             delete=False) as ziel:
                tmp = Path(ziel.name)
                gelesen = 0
                while True:
                    block = strom.read(1 << 20)
                    if not block:
                        break
                    gelesen += len(block)
                    if gelesen > MAX_INNEN_BYTES:
                        befund.melden(
                            Stufe.VERDACHT, "Sehr großes Archiv im Archiv",
                            f"'{name}' ist größer als "
                            f"{MAX_INNEN_BYTES // (1024 * 1024)} MB und "
                            f"wurde nicht zu Ende geprüft.")
                        return
                    ziel.write(block)
        innen = Befund()
        if zipfile.is_zipfile(tmp):
            _zip_pruefen(innen, tmp, tiefe + 1)
        else:
            _tar_pruefen(innen, tmp, tiefe + 1)
        for fund in innen.funde:
            befund.melden(fund.stufe, f"{fund.was} (in {name})",
                          fund.bedeutung)
        if innen.luecke:
            befund.luecke = f"in {name}: {innen.luecke}"
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError,
            ValueError) as exc:
        befund.luecke = f"'{name}' ließ sich nicht prüfen ({exc})."
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:                            # pragma: no cover
                pass


def pruefe_archiv(pfad: Path, tiefe: int = 0) -> Befund:
    """Sieht in ein zip- oder tar.gz-Archiv hinein, ohne es auszupacken."""
    befund = Befund()
    pfad = Path(pfad)
    try:
        if zipfile.is_zipfile(pfad):
            _zip_pruefen(befund, pfad, tiefe)
        else:
            _tar_pruefen(befund, pfad, tiefe)
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError,
            ValueError) as exc:
        # Kein Freispruch: Was sich nicht lesen lässt, ist ungeprüft.
        befund.luecke = f"{type(exc).__name__}: {exc}"
        _LOG.warning("Archiv nicht prüfbar (%s): %s", pfad, exc)
    return befund


def pruefe_ordner(pfad: Path, hoechstens: int = _MAX_EINTRAEGE) -> Befund:
    """Dasselbe für einen Ordner voller Aufnahmen."""
    befund = Befund()
    pfad = Path(pfad)
    try:
        dateien = [p for p in sorted(pfad.rglob("*")) if p.is_file()]
    except OSError as exc:
        befund.luecke = f"Der Ordner ließ sich nicht lesen ({exc})."
        return befund
    for datei in dateien[:hoechstens]:
        befund.eintraege += 1
        _name_pruefen(befund, datei.name)
        try:
            with datei.open("rb") as fh:
                kopf = fh.read(_PROBE)
        except OSError as exc:
            befund.luecke = f"'{datei.name}' ließ sich nicht lesen ({exc})."
            continue
        _inhalt_pruefen(befund, datei.name, kopf)
        if _archivart(kopf):
            innen = pruefe_archiv(datei, tiefe=1)
            for fund in innen.funde:
                befund.melden(fund.stufe, f"{fund.was} (in {datei.name})",
                              fund.bedeutung)
            if innen.luecke:
                befund.luecke = f"in {datei.name}: {innen.luecke}"
    return befund


def pruefe_quelle(pfad: Optional[Path]) -> Befund:
    """Archiv oder Ordner - je nachdem, was übergeben wurde."""
    if pfad is None:
        befund = Befund()
        befund.luecke = "Es wurde nichts übergeben."
        return befund
    pfad = Path(pfad)
    return pruefe_ordner(pfad) if pfad.is_dir() else pruefe_archiv(pfad)
