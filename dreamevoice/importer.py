"""Ganze Ordner oder Archive auf einmal übernehmen.

Ansagen einzeln zuzuweisen ist bei knapp 600 Stück keine Freude. Wer seine
Dateien ohnehin schon vorliegen hat - selbst aufgenommen, mit einer
Sprachsynthese erzeugt oder aus einem fremden Paket entnommen - soll sie
in einem Rutsch übernehmen können.

Die Zuordnung läuft über den Dateinamen: **die Zahl im Namen ist die
Ansage-Nummer**. `7.ogg`, `007.wav`, `7 - Reinigung gestartet.mp3` und
`Ansage_7.ogg` landen alle bei Ansage 7. Ein Name ohne Zahl wird
übersprungen, damit nichts an der falschen Stelle landet.

Damit man weiß, wie zu benennen ist, kann die App einen Vorlagenordner
anlegen: darin liegt jede Originalansage bereits richtig benannt. Man
hört sie an, spricht sie unter demselben Namen neu ein - fertig.
"""

from __future__ import annotations

import logging
import re
import shutil
import tarfile
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from .audio import SUPPORTED_INPUT
from .errors import PackError
from .sounds import SoundCatalog

#: Obergrenzen beim Einlesen fremder Archive.
#:
#: Ein Archiv kommt von außen - aus einem Download, von einem
#: Bekannten, aus dem Netz. Beim Auspacken wird jede Datei ganz in den
#: Speicher gelesen; ohne Grenze reicht ein wenige Kilobyte großes,
#: extrem stark gepacktes Archiv ("Archivbombe"), um den Arbeitsspeicher
#: zu füllen. Eine Ansage ist ein paar Sekunden Sprache - alles
#: oberhalb dieser Grenzen ist keine.
MAX_EINTRAG_BYTES = 50 * 1024 * 1024        # eine einzelne Ansage
MAX_GESAMT_BYTES = 2 * 1024 * 1024 * 1024   # das ganze Archiv
MAX_EINTRAEGE = 5000                        # so viele Dateien höchstens
#: So viele Verwürfe werden einzeln ins Protokoll geschrieben. Der
#: Rest wird nur noch gezählt - sonst schreibt ein Archiv mit
#: hunderttausend Einträgen ein Protokoll von mehreren Megabyte.
MAX_MELDUNGEN = 20

#: Woran sich ein Dateityp am Anfang erkennen lässt.
#:
#: Gebraucht, weil `zipfile.is_zipfile()` erst am ENDE der Datei
#: nachsieht. Bricht ein Download ab, fehlt genau dieses Ende - die
#: Datei ist unverkennbar ein Zip, gilt aber als keines und landete
#: dann im tar-Zweig. Der Nutzer bekam fünf Zeilen englischer
#: tar-Fehler und die Auskunft, erwartet werde ein tar.gz- oder
#: zip-Archiv. Also genau das, was er hatte.
_KENNZEICHEN = (
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),          # ein Zip ganz ohne Inhalt
    (b"PK\x07\x08", "zip"),          # über mehrere Dateien verteilt
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"Rar!\x1a\x07", "rar"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"OggS", "ogg"),
    (b"RIFF", "riff"),                # wav
    (b"ID3", "mp3"),
    (b"\xff\xfb", "mp3"),
    (b"fLaC", "flac"),
    (b"%PDF", "pdf"),
)

#: Wie diese Typen im Klartext heißen.
_TYPNAME = {"rar": "RAR-Archiv", "7z": "7z-Archiv", "bzip2": "bzip2-Archiv",
            "xz": "xz-Archiv", "ogg": "Tondatei (OGG)",
            "riff": "Tondatei (WAV)", "mp3": "Tondatei (MP3)",
            "flac": "Tondatei (FLAC)", "pdf": "PDF-Dokument"}

#: Tondateien - die kommen erfahrungsgemäß am häufigsten aus Versehen
#: hier an, weil jemand statt des Archivs eine einzelne Ansage wählt.
_TONDATEI = ("ogg", "riff", "mp3", "flac")


def archiv_art(archive: Path) -> str:
    """Was wirklich am Anfang der Datei steht.

    Nicht, was ihr Name behauptet: Eine `.zip`, die in Wahrheit ein
    RAR ist, oder eine `.tar.gz`, die nur eine Fehlerseite des Servers
    enthält, sind häufiger als man denkt.

    Rückgabe: "zip", "gzip", "rar", ... , "leer" wenn die Datei nichts
    enthält, oder "unbekannt". Ein unkomprimiertes tar fällt unter
    "unbekannt" - sein Kennzeichen steht erst bei Byte 257.
    """
    try:
        with open(archive, "rb") as datei:
            kopf = datei.read(8)
    except OSError:
        return "unbekannt"
    if not kopf:
        return "leer"
    for muster, art in _KENNZEICHEN:
        if kopf.startswith(muster):
            return art
    return "unbekannt"


_LOG = logging.getLogger(__name__)

LogFn = Callable[[str], None]

# Zahl irgendwo im Dateinamen - die erste zusammenhängende Ziffernfolge.
_ZAHL = re.compile(r"(\d+)")


@dataclass
class ImportResult:
    """Was ein Import ergeben hat."""

    assigned: Dict[int, Path] = field(default_factory=dict)
    unknown_ids: List[int] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    source: str = ""

    @property
    def count(self) -> int:
        return len(self.assigned)

    def summary(self) -> str:
        teile = [f"{self.count} Ansagen übernommen"]
        if self.unknown_ids:
            teile.append(f"{len(self.unknown_ids)} Nummern kennt dein Modell nicht")
        if self.skipped:
            teile.append(f"{len(self.skipped)} Dateien übersprungen")
        return ", ".join(teile)


def sound_id_from_name(name: str) -> Optional[int]:
    """Liest die Ansage-Nummer aus einem Dateinamen."""
    stamm = Path(name).stem
    treffer = _ZAHL.search(stamm)
    if not treffer:
        return None
    try:
        return int(treffer.group(1))
    except ValueError:
        return None


def scan_folder(folder: Path, known_ids: Optional[Iterable[int]] = None,
                log: Optional[LogFn] = None) -> ImportResult:
    """Durchsucht einen Ordner nach Audiodateien mit Nummern im Namen."""
    folder = Path(folder)
    if not folder.is_dir():
        raise PackError(f"Das ist kein Ordner:\n{folder}")

    bekannt = set(known_ids) if known_ids is not None else None
    ergebnis = ImportResult(source=str(folder))

    # Unterordner werden mitgenommen, aber flach ausgewertet.
    dateien = sorted(p for p in folder.rglob("*") if p.is_file())

    for pfad in dateien:
        if pfad.suffix.lower() not in SUPPORTED_INPUT:
            ergebnis.skipped.append(f"{pfad.name} (kein bekanntes Audioformat)")
            continue

        sound_id = sound_id_from_name(pfad.name)
        if sound_id is None:
            ergebnis.skipped.append(f"{pfad.name} (keine Nummer im Namen)")
            continue

        if bekannt is not None and sound_id not in bekannt:
            ergebnis.unknown_ids.append(sound_id)
            continue

        # Bei doppelten Nummern gewinnt die erste Datei - sonst hängt das
        # Ergebnis von der Sortierung des Dateisystems ab.
        if sound_id not in ergebnis.assigned:
            ergebnis.assigned[sound_id] = pfad

    if log:
        log(ergebnis.summary())
    return ergebnis


def _kein_archiv(archive: Path, art: str) -> PackError:
    """Erklärt in einem Satz, was der Nutzer stattdessen erwischt hat.

    Wichtig ist dabei nicht der technische Grund, sondern der nächste
    Schritt: neu herunterladen, neu einpacken oder gleich den Ordner
    wählen. Ohne das stand hier eine englische Fehlerzeile aus tarfile,
    mit der niemand etwas anfangen kann.
    """
    roh = archive.stat().st_size if archive.is_file() else 0
    # Ein abgebrochener Download wiegt oft nur ein paar Kilobyte -
    # "0.0 MB" hilft dann niemandem weiter.
    if roh >= 1024 * 1024:
        groesse = f"{roh / 1024 / 1024:.1f} MB"
    elif roh >= 1024:
        groesse = f"{roh / 1024:.0f} KB"
    else:
        groesse = f"{roh} Byte"

    if art == "leer":
        return PackError(
            "Die Datei ist leer.",
            f"'{archive.name}' hat 0 Byte. Vermutlich ist der Download "
            "gescheitert oder wurde abgebrochen. Lade die Datei bitte "
            "noch einmal herunter.")

    if art == "zip":
        # is_zipfile() sieht am ENDE der Datei nach. Fehlt das Ende,
        # ist die Übertragung abgebrochen - der häufigste Fall.
        return PackError(
            "Das Zip-Archiv ist unvollständig.",
            "Der Anfang der Datei ist ein Zip-Archiv, aber sein "
            "Inhaltsverzeichnis am Ende fehlt. Genau so sieht eine "
            "abgebrochene Übertragung aus.\n\n"
            "Lade die Datei bitte noch einmal herunter und warte, bis "
            "der Download wirklich fertig ist.\n\n"
            f"Datei: {archive.name} ({groesse})")

    if art in ("rar", "7z"):
        name = _TYPNAME[art]
        return PackError(
            f"Das ist ein {name} - damit kann die App nicht umgehen.",
            "Entpacke es bitte selbst und wähle danach entweder den "
            "entpackten Ordner oder packe die Ansagen als ZIP neu ein. "
            "ZIP und tar.gz versteht die App.")

    if art in _TONDATEI:
        return PackError(
            f"Das ist eine einzelne {_TYPNAME[art]}, kein Archiv.",
            "Hier wird ein ganzes Paket erwartet. Zwei Wege führen zum "
            "Ziel: Lege alle Ansagen in einen Ordner und wähle 'Ordner "
            "übernehmen' - oder packe den Ordner vorher als ZIP ein.")

    if art == "pdf":
        return PackError(
            "Das ist ein PDF-Dokument, kein Sprachpaket.",
            "Erwartet wird ein ZIP- oder tar.gz-Archiv mit Ansagen, "
            "benannt wie 7.ogg oder 12.wav.")

    return PackError(
        "Die Datei ist kein Archiv, das die App lesen kann.",
        f"'{archive.name}' beginnt weder wie ein ZIP noch wie ein "
        "tar.gz. Möglich ist auch, dass statt des Archivs eine "
        "Fehlerseite des Servers heruntergeladen wurde - dann hilft "
        "nur, sie noch einmal zu holen.")


def extract_archive(archive: Path, target: Path,
                    log: Optional[LogFn] = None) -> Path:
    """Packt ein tar.gz- oder zip-Archiv in einen Ordner aus.

    Es werden nur Audiodateien entnommen, und zwar ausschließlich anhand
    ihres Dateinamens ohne die Pfade aus dem Archiv - ein manipuliertes
    Archiv kann so nichts an anderer Stelle ablegen.
    """
    archive = Path(archive)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)

    def behalten(roh: str) -> Optional[str]:
        name = Path(roh.replace("\\", "/")).name
        if not name or name.startswith("."):
            return None
        return name if Path(name).suffix.lower() in SUPPORTED_INPUT else None

    anzahl = 0
    gesamt = 0
    verworfen: List[tuple] = []
    #: Schon geschriebene Namen. Zwei Dateien aus verschiedenen
    #: Unterordnern können denselben Namen tragen - dann gewinnt die
    #: erste, wie beim Einlesen eines Ordners auch. Gezählt wurde
    #: vorher jede, obwohl sie sich gegenseitig überschrieben.
    geschrieben: set = set()

    def verwerfen(was: str, warum: str) -> None:
        """Ein übersprungener Eintrag - sichtbar, nicht nur im Protokoll.

        Früher ging das nur an _LOG. Der Nutzer sah "N Dateien entpackt"
        und bekam still ein unvollständiges Paket.
        """
        _LOG.warning("übersprungen (%s): %s", warum, was)
        verworfen.append((was, warum))

    def zuviel(rest, name_von) -> None:
        """Die übergangenen ANSAGEN melden - nicht jeden Eintrag.

        Zwei Fehler stecken hier drin, die schon dagewesen sind:

        Erst wurde nur einer vermerkt und dann abgebrochen - bei 5020
        Ansagen meldete die App "1 übersprungen", tatsächlich
        fehlten 20. Danach wurde der ganze Rest gezählt, also auch
        Ordner, Beipackzettel und Bilder: Ein Archiv mit 50 000
        Ordnereinträgen meldete "50000 übersprungen", obwohl keine
        einzige Ansage fehlte - und das Protokoll wuchs auf 9 MB.

        Gezählt wird deshalb nur, was überhaupt eine Ansage wäre,
        und einzeln vermerkt nur die ersten paar.
        """
        for eintrag in rest:
            name = name_von(eintrag)
            if not behalten(name):
                continue
            if len(verworfen) < MAX_MELDUNGEN:
                verwerfen(name, "mehr als erwartet")
            else:
                verworfen.append((name, "mehr als erwartet"))

    def passt(entpackt: int, name: str) -> bool:
        """Darf dieser Eintrag noch mit?

        Das Gesamtbudget wird nur um das erhöht, was auch wirklich
        geschrieben wird. Würde es schon für den Ausschuss mitzählen,
        risse ein einziger übergroßer Eintrag das Budget - und alle
        folgenden, völlig harmlosen Ansagen flogen mit raus.
        """
        nonlocal gesamt
        if entpackt > MAX_EINTRAG_BYTES:
            verwerfen(name, "zu groß")
            return False
        if gesamt + entpackt > MAX_GESAMT_BYTES:
            verwerfen(name, "Archiv insgesamt zu groß")
            return False
        gesamt += entpackt
        return True

    # Was wirklich in der Datei steht, entscheidet - nicht ihre Endung.
    art = archiv_art(archive)

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            eintraege = zf.infolist()
            for nummer, info in enumerate(eintraege):
                if anzahl >= MAX_EINTRAEGE:
                    zuviel(eintraege[nummer:], lambda i: i.filename)
                    break
                if info.is_dir():
                    continue
                name = behalten(info.filename)
                if not name:
                    continue
                if name in geschrieben:
                    continue
                # Bit 0 im Kopfsatz heißt: verschlüsselt. Ohne diese
                # Abfrage warf zipfile später einen RuntimeError, und
                # der Nutzer bekam die Auskunft, sein Archiv sei
                # beschädigt - dabei fehlte nur das Kennwort.
                if info.flag_bits & 0x1:
                    raise PackError(
                        "Das Archiv ist mit einem Kennwort geschützt.",
                        "Kennwortgeschützte Archive kann die App nicht "
                        "öffnen. Entpacke es bitte selbst und wähle "
                        "danach den entpackten Ordner - oder packe die "
                        "Ansagen ohne Kennwort neu ein.\n\n"
                        f"Betroffen: {info.filename}")
                # Die angekündigte Größe zuerst prüfen, damit gar
                # nicht erst gelesen wird, was zu groß ist.
                if not passt(info.file_size, info.filename):
                    continue
                # Nur das Lesen aus dem Archiv wird übersetzt. Würde
                # write_bytes mit im try stehen, bekäme der Nutzer bei
                # voller Platte oder gesperrtem Ordner die Auskunft, sein
                # Archiv sei beschädigt - und lädt es ewig neu.
                try:
                    # Gebündelt lesen statt zf.read(): Die Größe im
                    # Verzeichnis eines Archivs ist eine BEHAUPTUNG.
                    # zf.read() entpackt den ganzen Strom, egal was
                    # dort steht - ein 299 kB großes Archiv mit
                    # gefälschtem Kopfsatz belegte damit 600 MB
                    # Arbeitsspeicher, obwohl die Grenze bei 50 MB liegt.
                    with zf.open(info) as strom:
                        roh = strom.read(MAX_EINTRAG_BYTES + 1)
                    if len(roh) > MAX_EINTRAG_BYTES:
                        verwerfen(info.filename, "größer als angekündigt")
                        gesamt -= info.file_size
                        continue
                # zlib.error trifft den häufigsten Fall überhaupt:
                # heiles Verzeichnis, kaputte Nutzdaten - also ein
                # unvollständig heruntergeladenes Archiv. RuntimeError
                # kommt bei verschlüsselten Archiven.
                except (zipfile.BadZipFile, zlib.error, RuntimeError,
                        EOFError, OSError) as exc:
                    raise PackError(
                        "Das Archiv lässt sich nicht vollständig lesen.",
                        "Das Inhaltsverzeichnis ist da, die Daten "
                        "dahinter sind es nicht. So sieht ein "
                        "unvollständig heruntergeladenes oder "
                        "beschädigtes Archiv aus - lade es bitte noch "
                        "einmal herunter.\n\n"
                        f"Betroffen: {info.filename}\n"
                        f"Technischer Grund: {exc}") from exc
                try:
                    (target / name).write_bytes(roh)
                except OSError as exc:
                    # Überlange oder unmögliche Namen, volle Platte,
                    # gesperrter Ordner. Vorher flog das roh bis in
                    # den Dialog.
                    raise PackError(
                        "Eine Datei aus dem Archiv ließ sich nicht "
                        "ablegen.",
                        f"Betroffen: {name}\n\nMögliche Gründe: der Name "
                        f"ist zu lang, die Platte ist voll, oder der "
                        f"Zielordner ist gesperrt.\n\nTechnische Details: "
                        f"{exc}") from exc
                geschrieben.add(name)
                anzahl += 1
    elif art not in ("gzip", "bzip2", "xz", "unbekannt"):
        # Zip ohne Inhaltsverzeichnis, RAR, eine einzelne Tondatei, ein
        # PDF: alles Dinge, die tarfile nur mit einer englischen
        # Fehlerzeile quittiert hätte. Ein unkomprimiertes tar fällt
        # unter "unbekannt" - sein Kennzeichen steht erst bei Byte 257 -
        # und geht deshalb weiter unten durch.
        raise _kein_archiv(archive, art)
    else:
        try:
            with tarfile.open(archive, "r:*") as tf:
                mitglieder = tf.getmembers()
                for nummer, member in enumerate(mitglieder):
                    if anzahl >= MAX_EINTRAEGE:
                        zuviel(mitglieder[nummer:], lambda m: m.name)
                        break
                    # isfile() schließt Verweise und Gerätedateien aus -
                    # nur echte Dateien werden angefasst.
                    if not member.isfile():
                        continue
                    name = behalten(member.name)
                    if not name:
                        continue
                    if name in geschrieben:
                        continue
                    if not passt(member.size, member.name):
                        continue
                    quelle = tf.extractfile(member)
                    if quelle is None:
                        # Nichts gelesen, also auch nichts verbraucht.
                        gesamt -= member.size
                        continue
                    roh = quelle.read()
                    # Gebucht wird, was tatsächlich ankam. Ein Archiv
                    # mit aufgeblähten Größenangaben würde sonst
                    # Budget verbrauchen, das es gar nicht belegt - und
                    # damit spätere, harmlose Ansagen verdrängen.
                    gesamt += len(roh) - member.size
                    (target / name).write_bytes(roh)
                    geschrieben.add(name)
                    anzahl += 1
        # EOFError fällt bei einer abgeschnittenen .tar.gz an und ist
        # kein TarError - der ging bisher roh an die Oberfläche.
        except (tarfile.TarError, EOFError, zlib.error) as exc:
            if art in ("gzip", "bzip2", "xz"):
                # Der Anfang stimmt, der Rest nicht: abgebrochener
                # Download. Früher stand hier "erwartet wird ein
                # tar.gz-Archiv" - genau das, was der Nutzer hatte.
                raise PackError(
                    "Das Archiv ist unvollständig oder beschädigt.",
                    "Der Anfang der Datei ist ein gepacktes Archiv, "
                    "aber es lässt sich nicht bis zum Ende entpacken. "
                    "Am häufigsten liegt das an einem abgebrochenen "
                    "Download - lade die Datei bitte noch einmal "
                    "herunter.\n\n"
                    f"Technischer Grund: {exc}") from exc
            raise _kein_archiv(archive, art) from exc

    if anzahl == 0:
        hinweis = "Erwartet werden Dateien wie 7.ogg oder 12.wav."
        if verworfen:
            hinweis = (f"{len(verworfen)} Einträge wurden verworfen. Der erste: "
                       f"'{verworfen[0][0]}' ({verworfen[0][1]}). Ein "
                       f"Sprachpaket besteht aus kurzen Ansagen von wenigen "
                       f"Sekunden.")
        raise PackError("In dem Archiv waren keine brauchbaren Audiodateien.",
                        hinweis)

    if log:
        log(f"{anzahl} Dateien aus {archive.name} entpackt.")
        if verworfen:
            log(f"Achtung: {len(verworfen)} Einträge wurden übersprungen "
                f"({verworfen[0][1]}, zuerst '{verworfen[0][0]}'). Das Paket "
                f"ist dadurch unvollständig.")
    return target


def import_archive(archive: Path, work_dir: Path,
                   known_ids: Optional[Iterable[int]] = None,
                   log: Optional[LogFn] = None) -> ImportResult:
    """Archiv auspacken und gleich zuordnen."""
    ziel = Path(work_dir) / Path(archive).stem.replace(".tar", "")
    extract_archive(archive, ziel, log=log)
    ergebnis = scan_folder(ziel, known_ids, log=log)
    ergebnis.source = str(archive)
    return ergebnis


def create_template_folder(previews: Dict[int, Path],
                           catalog: SoundCatalog,
                           target: Path,
                           only_ids: Optional[Iterable[int]] = None,
                           log: Optional[LogFn] = None) -> Path:
    """Legt einen Ordner mit allen Originalansagen an - richtig benannt.

    Der bequemste Weg zu einem eigenen Paket: Ordner anlegen lassen, jede
    Datei anhören, sie unter demselben Namen neu einsprechen, danach den
    Ordner mit einem Klick importieren.
    """
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)

    ids = sorted(set(only_ids) & set(previews)) if only_ids is not None \
        else sorted(previews)
    if not ids:
        raise PackError(
            "Es stehen keine Originalansagen bereit.",
            "Melde dich zuerst unter 'Start' an - das Originalpaket deines "
            "Roboters holt die App danach von selbst.")

    zeilen = [
        "So baust du dein eigenes Sprachpaket",
        "=" * 38,
        "",
        "In diesem Ordner liegt jede Ansage deines Roboters - bereits richtig",
        "benannt. Die Zahl im Dateinamen ist die Ansage-Nummer.",
        "",
        "1. Datei anhören, damit du weißt, was gesagt wird.",
        "2. Eigene Aufnahme unter GENAU DEMSELBEN NAMEN speichern.",
        "   (mp3, wav, m4a und flac gehen auch - die App wandelt um.)",
        "3. Was du nicht ersetzt, einfach liegen lassen: diese Ansagen",
        "   bleiben auf der deutschen Originalstimme.",
        "4. In der App auf 'Ganzen Ordner importieren' klicken und diesen",
        "   Ordner auswählen.",
        "",
        "Halte die Aufnahmen kurz - die Originale sind zwei bis sechs Sekunden.",
        "",
        "-" * 38,
        "",
    ]

    kopiert = 0
    for sound_id in ids:
        quelle = previews[sound_id]
        ziel = target / f"{sound_id}.ogg"
        if not ziel.exists():
            shutil.copy2(quelle, ziel)
        kopiert += 1

        eintrag = catalog.get(sound_id)
        beschreibung = eintrag.title if eintrag else "(unbekannt)"
        zeilen.append(f"{sound_id}.ogg  =  {beschreibung}")

    (target / "_Anleitung.txt").write_text("\n".join(zeilen) + "\n",
                                           encoding="utf-8")

    if log:
        log(f"{kopiert} Originalansagen nach {target} kopiert.")
    return target


def suggested_filename(sound_id: int, suffix: str = ".ogg") -> str:
    """Der Dateiname, den die App für eine Ansage erwartet."""
    return f"{sound_id}{suffix}"
