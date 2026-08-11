"""Hängt die fertigen Dialektaufnahmen an die EXE an.

Wird von build_exe.ps1 nach embed_ffmpeg.py aufgerufen.

    python embed_dialekte.py [ordner] [exe]

Ohne Argumente werden die `*-Aufnahmen.zip` aus "Fertige Pakete"
genommen und an dist/DreameSprachpaket.exe gehängt.

Warum unkomprimiert: Der Inhalt sind Ogg-Dateien in ZIP-Archiven, also
bereits gepackt. LZMA darüber kostet beim Bauen Minuten und spart nichts
- gemessen unter einem Prozent.

Der Anhang ist ein gewöhnliches tar. Es liegt HINTER dem ffmpeg-Anhang;
dreamevoice/embedded.py liest die Kette vom Dateiende rückwärts und
findet beide.
"""

from __future__ import annotations

import io
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dreamevoice.embedded import MAGIC_DIALEKTE, TRAILER_SIZE  # noqa: E402

BASE = Path(__file__).resolve().parent
DEFAULT_ORDNER = BASE / "Fertige Pakete"
DEFAULT_EXE = BASE / "dist" / "DreameSprachpaket.exe"

MUSTER = "*-Aufnahmen.zip"
MINDESTGROESSE = 1_000_000


def schon_dran(exe: Path) -> bool:
    """Steckt am Ende der EXE bereits ein Dialekt-Anhang?"""
    if exe.stat().st_size <= TRAILER_SIZE:
        return False
    with exe.open("rb") as fh:
        fh.seek(-len(MAGIC_DIALEKTE), 2)
        return fh.read(len(MAGIC_DIALEKTE)) == MAGIC_DIALEKTE


def main() -> int:
    args = sys.argv[1:]
    ordner = Path(args[0]) if args else DEFAULT_ORDNER
    exe = Path(args[1]) if len(args) > 1 else DEFAULT_EXE

    if not exe.is_file():
        print(f"EXE nicht gefunden: {exe}")
        print("Zuerst PyInstaller laufen lassen.")
        return 1

    if schon_dran(exe):
        print("In dieser EXE stecken bereits Dialekte - nichts zu tun.")
        return 0

    if not ordner.is_dir():
        print(f"Ordner nicht gefunden: {ordner}")
        print("Die EXE funktioniert auch ohne diesen Schritt - dann bringt")
        print("sie keine fertigen Dialekte mit.")
        return 1

    archive = sorted(p for p in ordner.glob(MUSTER)
                     if p.stat().st_size >= MINDESTGROESSE)
    if not archive:
        print(f"Keine {MUSTER} in {ordner} gefunden.")
        return 1

    # Erst im Speicher aufbauen, damit eine halb geschriebene EXE gar
    # nicht erst entstehen kann.
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w") as tf:
        for archiv in archive:
            roh = archiv.read_bytes()
            info = tarfile.TarInfo(name=archiv.name)
            info.size = len(roh)
            info.mtime = int(time.time())
            tf.addfile(info, io.BytesIO(roh))
            print(f"  {archiv.name:<30} {len(roh) / 1024 / 1024:6.1f} MB")

    nutzlast = puffer.getvalue()
    vorher = exe.stat().st_size

    with exe.open("ab") as fh:
        fh.write(nutzlast)
        fh.write(len(nutzlast).to_bytes(8, "little"))
        fh.write(MAGIC_DIALEKTE)

    nachher = exe.stat().st_size
    print()
    print(f"{len(archive)} Dialekte angehaengt "
          f"({len(nutzlast) / 1024 / 1024:.1f} MB)")
    print(f"EXE vorher:  {vorher / 1024 / 1024:8.1f} MB")
    print(f"EXE nachher: {nachher / 1024 / 1024:8.1f} MB")
    print()
    print("Fertig. Weiterhin eine einzige portable Datei; ein Dialekt wird")
    print("beim ersten Bedarf einmalig in den Datenordner ausgepackt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
