"""Vergleicht die Lautheit unserer Ansagen mit den Originalen.

Beantwortet ohne Roboter: Sind die aufgespielten Ansagen tatsächlich
leiser als die deutschen Originale, die sie ersetzen? Gemessen wird die
integrierte Lautheit (LUFS) - das, was man als Lautstärke wahrnimmt.

    python Lautheit-vergleichen.py [anzahl]
"""

from __future__ import annotations

import json
import statistics
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJEKT = Path(__file__).resolve().parent.parent
ANZAHL = int(sys.argv[1]) if len(sys.argv) > 1 else 40

from dreamevoice import audio                                  # noqa: E402

FFMPEG = PROJEKT / "dist" / "Daten" / "ffmpeg" / "ffmpeg.exe"
ORIGINAL = PROJEKT / "dist" / "Daten" / "Originalpakete" / "dreame.vacuum.r2532v_DE.tar.gz"
DIALEKT = PROJEKT / "Fertige Pakete" / "Bayerisch-Aufnahmen.zip"
GEBAUT = PROJEKT / "dist" / "Daten" / "Meine Pakete"


def aus_tar(pfad: Path, ziel: Path, ids: set[int]) -> dict[int, Path]:
    ziel.mkdir(parents=True, exist_ok=True)
    heraus = {}
    with tarfile.open(pfad, "r:*") as tf:
        for m in tf.getmembers():
            name = Path(m.name).name
            if not name.endswith(".ogg"):
                continue
            try:
                n = int(name[:-4])
            except ValueError:
                continue
            if n not in ids:
                continue
            fh = tf.extractfile(m)
            if fh is None:
                continue
            p = ziel / f"{n}.ogg"
            p.write_bytes(fh.read())
            heraus[n] = p
    return heraus


def aus_zip(pfad: Path, ziel: Path, ids: set[int]) -> dict[int, Path]:
    ziel.mkdir(parents=True, exist_ok=True)
    heraus = {}
    with zipfile.ZipFile(pfad) as zf:
        for info in zf.infolist():
            name = Path(info.filename).name
            if not name.endswith(".ogg"):
                continue
            try:
                n = int(name[:-4])
            except ValueError:
                continue
            if n not in ids:
                continue
            p = ziel / f"{n}.ogg"
            p.write_bytes(zf.read(info.filename))
            heraus[n] = p
    return heraus


def messen(dateien: dict[int, Path]) -> dict[int, float]:
    werte = {}
    for n, p in sorted(dateien.items()):
        w = audio.measure_loudness(p, FFMPEG)
        if w:
            werte[n] = w["input_i"]
    return werte


def bericht(name: str, werte: dict[int, float]) -> None:
    v = sorted(werte.values())
    if not v:
        print(f"  {name:<28} keine Messwerte")
        return
    print(f"  {name:<28} n={len(v):>3}  Median {statistics.median(v):>7.2f}  "
          f"Mittel {statistics.mean(v):>7.2f}  "
          f"von {min(v):>7.2f} bis {max(v):>7.2f} LUFS")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not FFMPEG.is_file():
        print(f"ffmpeg fehlt: {FFMPEG}")
        return 1

    arbeit = Path(tempfile.mkdtemp(prefix="lautheit_"))

    # Welche Nummern vergleichen wir? Die ersten, die in beiden vorkommen.
    with tarfile.open(ORIGINAL, "r:*") as tf:
        orig_ids = {int(Path(m.name).name[:-4]) for m in tf.getmembers()
                    if Path(m.name).name.endswith(".ogg")
                    and Path(m.name).name[:-4].isdigit()}
    with zipfile.ZipFile(DIALEKT) as zf:
        dia_ids = {int(Path(i.filename).name[:-4]) for i in zf.infolist()
                   if Path(i.filename).name.endswith(".ogg")
                   and Path(i.filename).name[:-4].isdigit()}
    gemeinsam = sorted(orig_ids & dia_ids)[:ANZAHL]
    ids = set(gemeinsam)
    print(f"Vergleiche {len(ids)} Ansagen\n")

    print("Gemessene Lautheit (höher = lauter)")
    print("-" * 76)

    o = messen(aus_tar(ORIGINAL, arbeit / "orig", ids))
    bericht("Original Dreame (deutsch)", o)

    d = messen(aus_zip(DIALEKT, arbeit / "dia", ids))
    bericht("unsere Aufnahmen (roh)", d)

    # Und das, was wirklich auf dem Roboter landet.
    gebaut = sorted(GEBAUT.glob("*.tar.gz"))
    for g in gebaut[:3]:
        b = messen(aus_tar(g, arbeit / f"b_{g.stem}", ids))
        bericht(f"gebaut: {g.stem[:22]}", b)

    print()
    print("Abweichung je Ansage (unsere Aufnahme minus Original)")
    print("-" * 76)
    diffs = [d[n] - o[n] for n in gemeinsam if n in o and n in d]
    if diffs:
        leiser = [x for x in diffs if x < -1.0]
        lauter = [x for x in diffs if x > 1.0]
        print(f"  Median      {statistics.median(diffs):>+7.2f} LU")
        print(f"  Mittelwert  {statistics.mean(diffs):>+7.2f} LU")
        print(f"  Spanne      {min(diffs):>+7.2f} bis {max(diffs):>+7.2f} LU")
        print(f"  mehr als 1 LU leiser als das Original:  {len(leiser)} von {len(diffs)}")
        print(f"  mehr als 1 LU lauter als das Original:  {len(lauter)} von {len(diffs)}")
        print()
        if statistics.median(diffs) < -1.0:
            print("  ==> Unsere Ansagen sind messbar leiser. Das erklärt es.")
        elif statistics.median(diffs) > 1.0:
            print("  ==> Unsere Ansagen sind sogar lauter als die Originale.")
        else:
            print("  ==> Kein nennenswerter Unterschied. Die Ursache liegt")
            print("      NICHT in unseren Aufnahmen, sondern am Roboter.")

    import shutil
    shutil.rmtree(arbeit, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
