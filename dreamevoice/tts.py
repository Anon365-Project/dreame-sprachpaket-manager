"""Sprachsynthese über die in Windows eingebauten Stimmen.

Windows bringt seit jeher deutsche Sprachausgabe mit (Hedda, Katja,
Stefan). Die App nutzt sie über System.Speech, angesprochen per
PowerShell - das kommt ohne zusätzliche Python-Pakete aus und
funktioniert auch in der gepackten EXE.

Damit lassen sich Sprachpakete komplett offline erzeugen: kein
Cloud-Dienst, keine Anmeldung, keine Kosten, und es verlässt kein Text
den Rechner.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .errors import AudioError

_LOG = logging.getLogger(__name__)

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int], None]


ENGINE_SAPI = "sapi"          # System.Speech, die klassischen "Desktop"-Stimmen
ENGINE_ONECORE = "onecore"    # Windows.Media.SpeechSynthesis, neuere Stimmen


@dataclass
class Voice:
    name: str
    culture: str
    gender: str
    engine: str = ENGINE_SAPI

    @property
    def is_german(self) -> bool:
        return self.culture.lower().startswith("de")

    @property
    def is_male(self) -> bool:
        return self.gender.lower().startswith("m")

    @property
    def label(self) -> str:
        geschlecht = "männlich" if self.is_male else "weiblich"
        return f"{self.name} ({geschlecht})"


def _powershell_exe() -> str:
    """Der volle Pfad zu powershell.exe.

    Ohne Pfad sucht Windows zuerst im Verzeichnis der laufenden Anwendung.
    Bei einer heruntergeladenen EXE ist das oft der Download-Ordner - und
    eine dort abgelegte powershell.exe würde dann anstelle der echten
    starten. Mit vollem Pfad ist das ausgeschlossen.
    """
    wurzel = os.environ.get("SystemRoot") or r"C:\Windows"
    pfad = Path(wurzel) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(pfad) if pfad.is_file() else "powershell"


def _powershell(script: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """Führt ein PowerShell-Skript aus, ohne ein Fenster aufblitzen zu lassen."""
    kwargs = {}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    return subprocess.run(
        [_powershell_exe(), "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, **kwargs)


def available() -> bool:
    return sys.platform == "win32"


_LIST_SCRIPT = r"""
$ErrorActionPreference = 'Continue'

# Klassische SAPI5-Stimmen
try {
    Add-Type -AssemblyName System.Speech
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.GetInstalledVoices() | ForEach-Object {
        $i = $_.VoiceInfo
        Write-Output ('sapi|' + $i.Name + '|' + $i.Culture + '|' + $i.Gender)
    }
    $s.Dispose()
} catch { }

# Neuere OneCore-Stimmen. System.Speech sieht sie nicht - dort taucht unter
# Deutsch nur Hedda auf. Über die Windows-Runtime sind sie aber ohne
# Adminrechte erreichbar, und dort gibt es auch männliche Stimmen (Stefan).
try {
    [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media, ContentType = WindowsRuntime] | Out-Null
    foreach ($v in [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices) {
        Write-Output ('onecore|' + $v.DisplayName + '|' + $v.Language + '|' + $v.Gender)
    }
} catch { }
"""


def list_voices() -> List[Voice]:
    """Alle installierten Sprachausgabe-Stimmen, beide Windows-Generationen."""
    if not available():
        return []

    try:
        proc = _powershell(_LIST_SCRIPT, timeout=90)
    except (OSError, subprocess.SubprocessError) as exc:
        _LOG.warning("Stimmen konnten nicht ermittelt werden: %s", exc)
        return []

    voices: List[Voice] = []
    seen = set()
    for line in (proc.stdout or "").splitlines():
        parts = line.strip().split("|")
        if len(parts) != 4 or not parts[1]:
            continue
        engine, name, culture, gender = parts
        key = (name, engine)
        if key in seen:
            continue
        seen.add(key)
        voices.append(Voice(name=name, culture=culture, gender=gender,
                            engine=engine))
    return voices


def german_voices() -> List[Voice]:
    """Deutsche Stimmen, männliche zuerst.

    Die Reihenfolge ist Absicht: die einzige deutsche Stimme, die
    System.Speech kennt, ist die weibliche Hedda. Wer eine Männerstimme
    will, soll sie nicht suchen müssen.
    """
    german = [v for v in list_voices() if v.is_german]
    return sorted(german, key=lambda v: (not v.is_male, v.name.lower()))


def pick_german_voice(preferred: str = "") -> Optional[Voice]:
    voices = german_voices()
    if not voices:
        return None
    if preferred:
        for voice in voices:
            if voice.name == preferred:
                return voice
    return voices[0]


def synthesize(texts: Dict[int, str],
               out_dir: Path,
               voice: str = "",
               rate: int = 0,
               pitch: int = 0,
               volume: int = 100,
               log: Optional[LogFn] = None,
               progress: Optional[ProgressFn] = None) -> Dict[int, Path]:
    """Erzeugt für jeden Text eine WAV-Datei.

    `rate` steuert das Tempo, `pitch` die Tonhöhe - beide in Stufen von
    -10 bis 10. Beides läuft über SSML und wirkt dadurch bei den alten
    SAPI-Stimmen genauso wie bei den neueren OneCore-Stimmen; ohne SSML
    ließe sich die Tonhöhe gar nicht steuern.
    """
    if not available():
        raise AudioError(
            "Sprachsynthese ist nur unter Windows verfügbar.",
            "Auf diesem System lässt sich kein Paket automatisch erzeugen. "
            "Du kannst Ansagen aber selbst aufnehmen und zuweisen.")
    if not texts:
        raise AudioError("Es wurden keine Texte übergeben.")

    chosen = pick_german_voice(voice)
    if chosen is None:
        raise AudioError(
            "Es ist keine deutsche Sprachausgabe-Stimme installiert.",
            "Windows-Einstellungen > Zeit und Sprache > Sprache > Deutsch > "
            "Optionen > Sprachausgabe hinzufügen. Danach die App neu starten.")

    out_dir.mkdir(parents=True, exist_ok=True)
    if log:
        log(f"Stimme: {chosen.label}")

    jobs = []
    for sound_id, text in sorted(texts.items()):
        if not (text or "").strip():
            continue
        jobs.append({"file": str(out_dir / f"{sound_id}.wav"), "text": text})

    # Auftragsliste als Datei übergeben - so gibt es keine Probleme mit
    # Anführungszeichen oder Umlauten in der Kommandozeile.
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8-sig") as fh:
        json.dump(jobs, fh, ensure_ascii=False)
        job_file = Path(fh.name)

    # Beide Wege benutzen SSML, damit Tempo und Tonhöhe gleich wirken.
    if chosen.engine == ENGINE_ONECORE:
        script = _ONECORE_SCRIPT.format(voice=_ps_quote(chosen.name),
                                        jobs=_ps_quote(str(job_file)),
                                        rate=_ssml_prozent(rate),
                                        pitch=_ssml_prozent(pitch))
    else:
        script = _SAPI_SCRIPT.format(voice=_ps_quote(chosen.name),
                                     volume=int(volume),
                                     jobs=_ps_quote(str(job_file)),
                                     rate=_ssml_prozent(rate),
                                     pitch=_ssml_prozent(pitch))

    try:
        proc = _powershell(script, timeout=max(120, len(jobs) * 6))
    except subprocess.TimeoutExpired as exc:
        raise AudioError("Die Sprachsynthese hat zu lange gedauert.") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise AudioError("Die Sprachsynthese konnte nicht gestartet werden.",
                         f"Technische Details: {exc}") from exc
    finally:
        job_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        raise AudioError("Die Sprachsynthese ist fehlgeschlagen.",
                         (proc.stderr or "").strip()[:400])

    result: Dict[int, Path] = {}
    total = len(jobs)
    for sound_id, _text in sorted(texts.items()):
        path = out_dir / f"{sound_id}.wav"
        if path.is_file() and path.stat().st_size > 512:
            result[sound_id] = path
            if progress:
                progress(len(result), total)

    if not result:
        raise AudioError(
            "Es wurde keine einzige Sprachdatei erzeugt.",
            (proc.stderr or proc.stdout or "").strip()[:400])

    if log:
        log(f"{len(result)} von {total} Ansagen gesprochen.")
    return result


def _ps_quote(value: str) -> str:
    """Setzt einen Wert sicher in einfache Anführungszeichen für PowerShell."""
    return "'" + value.replace("'", "''") + "'"


def _ssml_prozent(stufe: int) -> str:
    """Rechnet eine Stufe (-10..10) in eine SSML-Prozentangabe um.

    Eine Stufe entspricht zehn Prozent, begrenzt auf ±50 % - darüber
    hinaus klingen die Windows-Stimmen nur noch verzerrt.
    """
    prozent = max(-50, min(50, int(stufe) * 10))
    return f"{prozent:+d}%"


# --------------------------------------------------------------------------
# Die beiden Sprech-Skripte
# --------------------------------------------------------------------------

_SAPI_SCRIPT = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice({voice})
$synth.Volume = {volume}
$jobs = Get-Content -Raw -Encoding UTF8 {jobs} | ConvertFrom-Json
$done = 0
foreach ($job in $jobs) {{
    $sicher = [System.Security.SecurityElement]::Escape($job.text)
    $ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'" +
            " xml:lang='de-DE'><prosody rate='{rate}' pitch='{pitch}'>" +
            $sicher + "</prosody></speak>"
    $synth.SetOutputToWaveFile($job.file)
    $synth.SpeakSsml($ssml)
    $done = $done + 1
}}
$synth.SetOutputToNull()
$synth.Dispose()
Write-Output ("FERTIG|" + $done)
"""

# Die Windows-Runtime arbeitet asynchron. In PowerShell 5.1 gibt es kein
# 'await', deshalb wird die Aufgabe über AsTask in eine .NET-Task
# umgewandelt und abgewartet.
#
# Die Meldungen IM Skript kommen ohne Umlaute aus, und das mit Absicht:
# PowerShell 5.1 schreibt seine Fehlerausgabe in der Codepage der
# Konsole, gelesen wird sie hier als UTF-8. Ein "ü" käme also als
# Fragezeichen beim Benutzer an. Ein umlautfreier Satz ist besser als
# ein zerlegter.
_ONECORE_SCRIPT = """
$ErrorActionPreference = 'Stop'
[Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataReader, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
}})[0]

function Await($op, $type) {{
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    if (-not $task.Wait(60000)) {{ throw 'Die Sprachausgabe hat zu lange gedauert' }}
    $task.Result
}}

$voice = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices |
         Where-Object {{ $_.DisplayName -eq {voice} }} | Select-Object -First 1
if (-not $voice) {{ throw ('Stimme nicht gefunden: ' + {voice}) }}

$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$synth.Voice = $voice

$jobs = Get-Content -Raw -Encoding UTF8 {jobs} | ConvertFrom-Json
$done = 0
foreach ($job in $jobs) {{
    $sicher = [System.Security.SecurityElement]::Escape($job.text)
    $ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'" +
            " xml:lang='de-DE'><prosody rate='{rate}' pitch='{pitch}'>" +
            $sicher + "</prosody></speak>"
    $op = $synth.SynthesizeSsmlToStreamAsync($ssml)
    $stream = Await $op ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
    Await $reader.LoadAsync([uint32]$stream.Size) ([uint32]) | Out-Null
    $bytes = New-Object byte[] $stream.Size
    $reader.ReadBytes($bytes)
    [IO.File]::WriteAllBytes($job.file, $bytes)
    $reader.Dispose()
    $stream.Dispose()
    $done = $done + 1
}}
$synth.Dispose()
Write-Output ("FERTIG|" + $done)
"""
