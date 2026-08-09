"""Prüfen und Umwandeln der Audiodateien.

Der Roboter erwartet in einem Sprachpaket ausschließlich **OGG Vorbis,
mono, 16000 Hz**. Das wurde durch Auslesen der offiziellen Pakete
bestätigt (X50 Ultra Complete DE, X40 Ultra) und deckt sich mit allen
funktionierenden Community-Paketen.

Eine mp3- oder wav-Datei muss deshalb zwingend umgewandelt werden. Dafür
wird ffmpeg benutzt: es wird neben der EXE, im Datenordner oder im
System-PATH gesucht. Ist es nicht da, sagt die App klar Bescheid, statt
still ein unbrauchbares Paket zu bauen.
"""

from __future__ import annotations

import json
import logging
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .errors import AudioError
from .paths import app_dir, data_dir

_LOG = logging.getLogger(__name__)

TARGET_CODEC = "vorbis"
TARGET_RATE = 16000
TARGET_CHANNELS = 1

# Lautstärke. Gemessen an den Originalansagen des X50 Ultra Complete:
# Median -15.9 LUFS, Spitzen bis +0.3 dBTP (also bewusst randvoll
# ausgesteuert). Damit eigene Ansagen nicht leiser klingen als die
# deutschen Originale, wird auf denselben Wert gefahren und nur ein
# Haar Luft nach oben gelassen, damit nichts übersteuert.
TARGET_LUFS = -15.5
# Grenze des Limiters. Sie steuert den Spitzenpegel; die Lautheit bleibt
# davon unberuehrt, weil eine Nachkorrektur die Verstaerkung anpasst.
# Nachgemessen an den ungünstigsten Ansagen: -0,5 dBFS ergab bis zu
# +2,3 dBTP, -1,0 dBFS ergibt im Mittel +0,7 dBTP. Die Originalansagen
# liegen bei +0,2 dBTP im Median. Tiefer zu gehen kostet Lautheit, ohne
# hoerbar etwas zu gewinnen.
TARGET_PEAK = -1.0
TARGET_LRA = 11.0

# Ab dieser Abweichung lohnt es, eine bereits passend formatierte Datei
# noch einmal anzufassen. Darunter hört man den Unterschied ohnehin nicht.
LOUDNESS_TOLERANCE = 1.0

SUPPORTED_INPUT = (".ogg", ".wav", ".mp3", ".m4a", ".aac", ".flac", ".opus", ".wma")

# Sehr große Einzeldateien deuten auf ein Missverständnis hin (z. B. ein
# ganzes Lied statt einer Ansage). Das Paket würde unnötig riesig.
WARN_SECONDS = 30
MAX_FILE_BYTES = 8 * 1024 * 1024


@dataclass
class OggInfo:
    codec: str
    channels: int
    rate: int

    @property
    def is_target_format(self) -> bool:
        return (self.codec == TARGET_CODEC
                and self.channels == TARGET_CHANNELS
                and self.rate == TARGET_RATE)

    def describe(self) -> str:
        return f"{self.codec}, {self.channels} Kanal/Kanäle, {self.rate} Hz"


# --------------------------------------------------------------------------
# Ogg-Kopfdaten lesen (ohne externe Bibliothek)
# --------------------------------------------------------------------------

def probe_ogg(path: Path) -> Optional[OggInfo]:
    """Liest Codec, Kanalzahl und Abtastrate aus der ersten Ogg-Seite."""
    try:
        with path.open("rb") as fh:
            head = fh.read(4096)
    except OSError:
        return None

    if len(head) < 28 or head[:4] != b"OggS":
        return None

    segment_count = head[26]
    body = head[27 + segment_count:]

    if body.startswith(b"\x01vorbis") and len(body) >= 16:
        channels = body[11]
        rate = struct.unpack("<I", body[12:16])[0]
        return OggInfo("vorbis", channels, rate)

    if body.startswith(b"OpusHead") and len(body) >= 16:
        channels = body[9]
        rate = struct.unpack("<I", body[12:16])[0]
        return OggInfo("opus", channels, rate)

    return OggInfo("unbekannt", 0, 0)


def needs_conversion(path: Path) -> bool:
    """True, wenn die Datei nicht bereits im Zielformat vorliegt."""
    if path.suffix.lower() != ".ogg":
        return True
    info = probe_ogg(path)
    return not (info and info.is_target_format)


# --------------------------------------------------------------------------
# ffmpeg
# --------------------------------------------------------------------------

def _candidate_paths() -> List[Path]:
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    return [
        app_dir() / exe,
        app_dir() / "ffmpeg" / exe,
        app_dir() / "ffmpeg" / "bin" / exe,
        data_dir() / "ffmpeg" / exe,
        data_dir() / "ffmpeg" / "bin" / exe,
    ]


def find_ffmpeg() -> Optional[Path]:
    """Sucht ffmpeg neben der App, im Datenordner und im PATH."""
    for candidate in _candidate_paths():
        if candidate.is_file():
            return candidate

    import shutil
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def _run(cmd: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
    kwargs = {}
    if sys.platform == "win32":
        # Verhindert, dass bei der EXE ein Konsolenfenster aufblitzt.
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, **kwargs)


def ffmpeg_version(ffmpeg: Optional[Path] = None) -> str:
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        return ""
    try:
        proc = _run([str(ffmpeg), "-version"], timeout=15)
        first = (proc.stdout or "").splitlines()
        return first[0] if first else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def measure_loudness(src: Path, ffmpeg: Optional[Path] = None) -> Optional[dict]:
    """Misst die Lautheit einer Datei (erster Durchgang von loudnorm).

    Rückgabe: die Messwerte von ffmpeg als Zahlen-Wörterbuch mit den
    Schlüsseln `input_i`, `input_tp`, `input_lra`, `input_thresh` - oder
    None, wenn die Messung nicht geklappt hat. `input_i` ist die
    integrierte Lautheit in LUFS, also das, was man als Lautstärke hört.
    """
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg or not src.is_file():
        return None

    cmd = [
        str(ffmpeg), "-hide_banner", "-nostats", "-i", str(src), "-vn",
        "-af", (f"loudnorm=I={TARGET_LUFS}:TP={TARGET_PEAK}:"
                f"LRA={TARGET_LRA}:print_format=json"),
        "-f", "null", "-",
    ]
    try:
        proc = _run(cmd)
    except (OSError, subprocess.SubprocessError):
        return None

    text = (proc.stderr or "") + (proc.stdout or "")
    start = text.rfind("{")
    ende = text.rfind("}")
    if start < 0 or ende < start:
        return None
    try:
        roh = json.loads(text[start:ende + 1])
    except ValueError:
        return None

    werte = {}
    for schluessel in ("input_i", "input_tp", "input_lra", "input_thresh"):
        try:
            wert = float(roh.get(schluessel))
        except (TypeError, ValueError):
            return None
        # Bei völliger Stille liefert ffmpeg -inf o. ä.
        if wert != wert or wert in (float("inf"), float("-inf")):
            return None
        werte[schluessel] = wert
    return werte


def convert_to_pack_format(src: Path, dst: Path,
                           ffmpeg: Optional[Path] = None,
                           normalize: bool = True,
                           target_lufs: Optional[float] = None) -> Path:
    """Wandelt eine beliebige Audiodatei in OGG Vorbis mono 16 kHz um.

    `normalize` gleicht die Lautstärke an das Niveau der Originalansagen
    an - sonst sind selbst gebaute Ansagen oft deutlich leiser oder lauter
    als die übrigen. Das geschieht in **zwei Durchgängen**: erst messen,
    dann gezielt anheben. Der einstufige Weg schätzt die Lautheit im
    Vorbeilaufen und liegt bei kurzen Ansagen regelmäßig um mehrere
    Dezibel daneben - genau das lässt einzelne Ansagen dann deutlich
    leiser klingen als die deutschen Originale.

    `target_lufs` erlaubt es, die Lautheit der Originalansage vorzugeben,
    die ersetzt wird. Dann ist die neue Ansage exakt so laut wie die, die
    sie ablöst.
    """
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise AudioError(
            "ffmpeg wurde nicht gefunden.",
            "ffmpeg wird gebraucht, um deine Audiodatei in das Format zu "
            "bringen, das der Roboter versteht (OGG Vorbis, mono, 16 kHz). "
            "Lege ffmpeg.exe einfach neben die App - oder wähle bereits "
            "passend vorbereitete .ogg-Dateien aus.",
        )

    if not src.is_file():
        raise AudioError(f"Die Datei wurde nicht gefunden:\n{src}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    gain_db: Optional[float] = None
    ziel = TARGET_LUFS
    if normalize:
        ziel = TARGET_LUFS if target_lufs is None else float(target_lufs)
        # Unsinnige Vorgaben (z. B. aus einer kaputten Messung) abfangen.
        ziel = max(-30.0, min(-8.0, ziel))
        gemessen = measure_loudness(src, ffmpeg)
        if gemessen:
            gain_db = ziel - gemessen["input_i"]

    def durchgang(gain: Optional[float]) -> None:
        filters = ["aresample=16000", "aformat=channel_layouts=mono"]
        if gain is not None:
            # Erst der nötige Pegel, dann ein Limiter als Sicherheitsnetz.
            # Die Originalansagen sind randvoll ausgesteuert; ohne Limiter
            # kommt man an ihre Lautheit gar nicht heran, weil einzelne
            # Spitzen den ganzen Pegel ausbremsen.
            filters.append(f"volume={gain:.2f}dB")
            filters.append(
                f"alimiter=limit={10 ** (TARGET_PEAK / 20):.4f}"
                f":attack=5:release=50:level=disabled")
        elif normalize:
            # Messung fehlgeschlagen (sehr kurze oder stille Datei):
            # lieber einstufig angleichen als gar nicht.
            filters.append(f"loudnorm=I={ziel}:TP={TARGET_PEAK}:LRA={TARGET_LRA}")

        cmd = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            "-vn",
            "-af", ",".join(filters),
            "-ar", str(TARGET_RATE),
            "-ac", str(TARGET_CHANNELS),
            "-c:a", "libvorbis", "-q:a", "3",
            str(dst),
        ]

        try:
            proc = _run(cmd)
        except subprocess.TimeoutExpired as exc:
            raise AudioError(
                f"Die Umwandlung von {src.name} hat zu lange gedauert.") from exc
        except OSError as exc:
            raise AudioError(f"ffmpeg konnte nicht gestartet werden: {exc}") from exc

        if proc.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
            detail = (proc.stderr or "").strip()[:400]
            raise AudioError(
                f"Die Datei {src.name} konnte nicht umgewandelt werden.",
                detail or "ffmpeg hat keine Begründung geliefert. Ist die Datei "
                          "vielleicht beschädigt oder gar keine Audiodatei?",
            )

    durchgang(gain_db)

    if gain_db is not None:
        # Der Limiter nimmt etwas Pegel weg. Nachmessen und, wenn es sich
        # lohnt, mit korrigierter Verstärkung neu aus der Originaldatei
        # umwandeln (nicht aus dem Ergebnis - sonst käme noch eine
        # Kompression obendrauf). Zwei Korrekturen reichen; danach ist der
        # Rest kleiner als das, was ein Ohr unterscheiden kann.
        for _ in range(2):
            ergebnis = measure_loudness(dst, ffmpeg)
            if not ergebnis:
                break
            rest = ziel - ergebnis["input_i"]
            if abs(rest) < LOUDNESS_TOLERANCE / 4:
                break
            gain_db += rest
            durchgang(gain_db)

    info = probe_ogg(dst)
    if not info or info.codec != TARGET_CODEC:
        raise AudioError(
            f"Das Ergebnis für {src.name} ist kein OGG Vorbis.",
            "Vermutlich fehlt deinem ffmpeg der Vorbis-Encoder (libvorbis). "
            "Nutze einen vollständigen ffmpeg-Build.",
        )
    return dst


def prepare(src: Path, dst: Path, ffmpeg: Optional[Path] = None,
            target_lufs: Optional[float] = None) -> Tuple[Path, bool]:
    """Stellt sicher, dass eine Datei im Zielformat vorliegt.

    `target_lufs` ist die Lautheit der Originalansage, die ersetzt wird.
    Ist die Datei zwar schon im richtigen Format, aber deutlich leiser
    oder lauter als das Original, wird sie trotzdem umgewandelt - sonst
    fällt genau diese eine Ansage am Roboter aus dem Rahmen.

    Rückgabe: (verwendbare Datei, ob umgewandelt wurde).
    """
    if not src.is_file():
        raise AudioError(f"Die Datei wurde nicht gefunden:\n{src}")

    if src.stat().st_size > MAX_FILE_BYTES:
        raise AudioError(
            f"{src.name} ist mit {src.stat().st_size // 1024} KB sehr groß.",
            "Ansagen des Roboters sind nur wenige Sekunden lang. Bitte kürze "
            "die Datei, bevor du sie verwendest.",
        )

    if not needs_conversion(src):
        if target_lufs is None:
            return src, False
        gemessen = measure_loudness(src, ffmpeg)
        if not gemessen:
            return src, False
        if abs(gemessen["input_i"] - float(target_lufs)) < LOUDNESS_TOLERANCE:
            return src, False

    return convert_to_pack_format(src, dst, ffmpeg, target_lufs=target_lufs), True


def concat_with_pauses(files: List[Path], out: Path,
                       ffmpeg: Optional[Path] = None,
                       pause: float = 0.7) -> Path:
    """Hängt mehrere Aufnahmen mit kurzer Pause zu einer Datei zusammen.

    Für die Hörprobe unerlässlich: Ruft man den Standardplayer dreimal
    hintereinander auf, spielt er nur die erste Datei - die übrigen gehen
    unter. Eine einzige Datei wird dagegen zuverlässig komplett
    abgespielt.

    Die Stille zwischen den Sätzen kommt aus `anullsrc`; jede Pause
    bekommt eine eigene Eingabe, weil ein Eingang im Filter nur einmal
    verwendet werden darf.
    """
    files = [Path(f) for f in files if Path(f).is_file()]
    if not files:
        raise AudioError("Es gibt nichts zusammenzufügen.")
    if len(files) == 1:
        return files[0]

    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        # Ohne ffmpeg bleibt nur die erste Aufnahme.
        return files[0]

    out.parent.mkdir(parents=True, exist_ok=True)
    luecken = len(files) - 1

    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y"]
    for datei in files:
        cmd += ["-i", str(datei)]
    for _ in range(luecken):
        cmd += ["-f", "lavfi", "-t", str(pause),
                "-i", f"anullsrc=r={TARGET_RATE}:cl=mono"]

    teile = []
    for index in range(len(files)):
        teile.append(f"[{index}:a]")
        if index < luecken:
            teile.append(f"[{len(files) + index}:a]")
    filter_text = "".join(teile) + f"concat=n={len(files) + luecken}:v=0:a=1[out]"

    cmd += ["-filter_complex", filter_text, "-map", "[out]",
            "-ar", str(TARGET_RATE), "-ac", str(TARGET_CHANNELS), str(out)]

    try:
        proc = _run(cmd, timeout=90)
    except (OSError, subprocess.SubprocessError) as exc:
        _LOG.warning("Zusammenfügen fehlgeschlagen: %s", exc)
        return files[0]

    if proc.returncode != 0 or not out.is_file() or out.stat().st_size < 1000:
        _LOG.warning("Zusammenfügen fehlgeschlagen: %s",
                     (proc.stderr or "")[:200])
        return files[0]
    return out


def check_input_file(path: Path) -> str:
    """Gibt eine Warnung zurück, wenn etwas auffällig ist (sonst "")."""
    if path.suffix.lower() not in SUPPORTED_INPUT:
        return (f"Das Format {path.suffix or '(ohne Endung)'} ist nicht "
                f"vorgesehen. Erwartet werden z. B. "
                f"{', '.join(SUPPORTED_INPUT[:4])}.")
    if path.stat().st_size > MAX_FILE_BYTES:
        return "Die Datei ist sehr groß - Ansagen sollten nur Sekunden dauern."
    if path.suffix.lower() == ".ogg":
        info = probe_ogg(path)
        if info and not info.is_target_format:
            return (f"Die Datei ist {info.describe()}. Sie wird beim Bauen "
                    f"automatisch nach mono/16000 Hz umgewandelt.")
        if info is None:
            return "Die Datei sieht nicht wie eine gültige Ogg-Datei aus."
    return ""
