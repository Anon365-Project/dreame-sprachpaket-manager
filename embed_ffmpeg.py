"""Hängt ffmpeg.exe komprimiert an die fertige EXE an.

Wird von build_exe.ps1 nach PyInstaller aufgerufen. Getrennt gehalten,
damit man den Schritt auch einzeln ausführen oder weglassen kann.

    python embed_ffmpeg.py <ffmpeg.exe> [exe]

Ohne Argumente sucht das Skript ffmpeg.exe im Projektordner und arbeitet
auf dist/DreameSprachpaket.exe.
"""

from __future__ import annotations

import lzma
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dreamevoice.embedded import MAGIC, TRAILER_SIZE  # noqa: E402

BASE = Path(__file__).resolve().parent
DEFAULT_EXE = BASE / "dist" / "DreameSprachpaket.exe"


def find_ffmpeg() -> Path | None:
    for candidate in (BASE / "ffmpeg.exe",
                      BASE / "ffmpeg" / "ffmpeg.exe",
                      BASE / "ffmpeg" / "bin" / "ffmpeg.exe"):
        if candidate.is_file():
            return candidate
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def already_embedded(exe: Path) -> bool:
    if exe.stat().st_size <= TRAILER_SIZE:
        return False
    with exe.open("rb") as fh:
        fh.seek(-len(MAGIC), 2)
        return fh.read(len(MAGIC)) == MAGIC


def main() -> int:
    args = sys.argv[1:]
    ffmpeg = Path(args[0]) if args else find_ffmpeg()
    exe = Path(args[1]) if len(args) > 1 else DEFAULT_EXE

    if ffmpeg is None or not ffmpeg.is_file():
        print("ffmpeg.exe nicht gefunden.")
        print("Lege ffmpeg.exe in den Projektordner oder gib den Pfad an:")
        print("    python embed_ffmpeg.py C:\\Pfad\\zu\\ffmpeg.exe")
        print()
        print("Bezugsquelle: https://github.com/BtbN/FFmpeg-Builds/releases")
        print("Die EXE funktioniert auch ohne diesen Schritt - dann kann sie")
        print("ffmpeg auf Wunsch zur Laufzeit nachladen.")
        return 1

    if not exe.is_file():
        print(f"EXE nicht gefunden: {exe}")
        print("Zuerst PyInstaller laufen lassen.")
        return 1

    if already_embedded(exe):
        print("In dieser EXE steckt bereits ein ffmpeg - nichts zu tun.")
        return 0

    raw = ffmpeg.read_bytes()
    print(f"ffmpeg.exe:  {len(raw) / 1024 / 1024:8.1f} MB")
    print("Komprimiere (dauert etwa eine Minute) ...")

    payload = lzma.compress(raw, preset=6)
    print(f"komprimiert: {len(payload) / 1024 / 1024:8.1f} MB "
          f"({len(payload) * 100 // len(raw)} %)")

    before = exe.stat().st_size
    with exe.open("ab") as fh:
        fh.write(payload)
        fh.write(len(payload).to_bytes(8, "little"))
        fh.write(MAGIC)

    after = exe.stat().st_size
    print()
    print(f"EXE vorher:  {before / 1024 / 1024:8.1f} MB")
    print(f"EXE nachher: {after / 1024 / 1024:8.1f} MB")
    print()
    print("Fertig. Weiterhin eine einzige portable Datei; ffmpeg wird beim")
    print("ersten Bedarf einmalig in den Datenordner ausgepackt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
