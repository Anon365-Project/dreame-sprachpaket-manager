"""Dialektpakete, die die App selbst erzeugt.

Fertige bayerische Sprachpakete für Saugroboter gibt es nirgends zum
Herunterladen - weder für Dreame noch für Roborock, Xiaomi oder Valetudo.
In den einschlägigen Foren wurde Bayerisch zwar immer wieder gewünscht,
gebaut hat es niemand. Vorhanden ist lediglich ein Schweizerdeutsch-Paket
für den Roborock S5. Es gibt also kein Fremdpaket, das sich umbauen
liesse.

Deshalb entstehen die Texte hier neu und werden mit der in Windows
eingebauten deutschen Sprachausgabe gesprochen. Alles läuft offline.

Zur Klarheit über das Ergebnis: der Dialekt steckt in der Wortwahl und in
der lautgetreuen Schreibweise ("i fang zum Saugn o"), nicht in einer
echten bayerischen Stimme - Windows bringt nur Hochdeutsch mit. Es klingt
also nach einer Hochdeutsch-Sprecherin, die Bayerisch vorliest. Wer es
echter will, nimmt die Ansagen mit dem eigenen Mikrofon auf und weist sie
in Tab 2 zu; die Textliste unten ist dafür eine brauchbare Vorlage.

Die Nummern sind die Ansage-IDs des X50 Ultra Complete.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from . import dialects, tts
from .audio import concat_with_pauses, convert_to_pack_format
from .loudness import reference_levels, target_for
from .official import list_sound_ids
from .errors import AudioError, PackError
from .packer import BuildResult, build_pack
from .paths import build_dir

_LOG = logging.getLogger(__name__)

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int], None]

ENGINE_WINDOWS = "windows"
ENGINE_ELEVENLABS = "elevenlabs"

NOTE_WINDOWS = (
    "Mit der Windows-Stimme steckt der Dialekt nur in Wortwahl und "
    "Schreibweise - die Aussprache bleibt hochdeutsch. Für echten Dialekt "
    "unten auf ElevenLabs umschalten."
)


@dataclass
class DialectPack:
    """Ein Dialektpaket, das die App erzeugen kann."""

    key: str
    name: str
    description: str
    lang_id: str
    texts: Dict[int, str] = field(default_factory=dict)
    # Normaltempo und normale Tonhöhe. Beide lassen sich in der
    # Oberfläche einstellen; langsamer sprechen klingt bei den ohnehin
    # nüchternen Windows-Stimmen schleppend, nicht deutlicher.
    rate: int = 0
    pitch: int = 0
    notes: str = NOTE_WINDOWS

    @property
    def count(self) -> int:
        return len(self.texts)

    def sample(self, sound_id: int) -> str:
        return self.texts.get(sound_id, "")


DIALECTS: List[DialectPack] = [
    DialectPack(key=module.KEY, name=module.NAME,
                description=module.BESCHREIBUNG, lang_id=module.LANG_ID,
                texts=module.TEXTE)
    for module in dialects.MODULES
]


def get(key: str) -> Optional[DialectPack]:
    for pack in DIALECTS:
        if pack.key == key:
            return pack
    return None


def with_overrides(pack: DialectPack,
                   overrides: Optional[Dict[int, str]]) -> DialectPack:
    """Liefert den Dialekt mit den selbst geänderten Texten.

    Das Original bleibt unangetastet: es wird eine Kopie erzeugt. So lassen
    sich Änderungen jederzeit wieder verwerfen, und eine neue Fassung der
    App bringt verbesserte Standardtexte für alles mit, was der Nutzer
    nicht selbst angefasst hat.
    """
    if not overrides:
        return pack
    texte = dict(pack.texts)
    for sound_id, text in overrides.items():
        if str(text).strip():
            texte[int(sound_id)] = str(text).strip()
    return replace(pack, texts=texte)


def changed_ids(pack: DialectPack, overrides: Dict[int, str]) -> List[int]:
    """Nummern, deren Text vom mitgelieferten abweicht."""
    return sorted(i for i, t in (overrides or {}).items()
                  if str(t).strip() and pack.texts.get(int(i)) != str(t).strip())


def cache_dirs(pack: DialectPack) -> List[Path]:
    """Alle Zwischenspeicher, die zu diesem Dialekt gehören."""
    wurzel = build_dir() / "_dialekt"
    if not wurzel.is_dir():
        return []
    return [p for p in wurzel.iterdir()
            if p.is_dir() and p.name.startswith(f"{pack.key}_")]


MANIFEST = "_inhalt.json"


def _text_fingerprint(text: str) -> str:
    return hashlib.md5(str(text).strip().encode("utf-8")).hexdigest()[:12]


def _manifest_path(work_dir: Path) -> Path:
    return Path(work_dir) / "gesprochen" / MANIFEST


def read_manifest(work_dir: Path) -> Dict[int, str]:
    """Was laut Verzeichnis mit welchem Text gesprochen wurde."""
    pfad = _manifest_path(work_dir)
    if not pfad.is_file():
        return {}
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    ergebnis: Dict[int, str] = {}
    for k, v in (roh.get("texte") or {}).items():
        try:
            ergebnis[int(k)] = str(v)
        except (TypeError, ValueError):
            continue
    return ergebnis


def write_manifest(work_dir: Path, texte: Dict[int, str]) -> None:
    """Hält fest, welcher Text zu welcher Aufnahme gehört.

    Ohne dieses Verzeichnis wäre eine vorhandene Datei nur ein Hinweis
    darauf, dass *irgendwann irgendetwas* gesprochen wurde. Kopiert
    jemand Aufnahmen aus einem früheren Versuch herein oder ändert sich
    ein Text, würde die App stillschweigend die falsche Aufnahme
    weiterverwenden.
    """
    pfad = _manifest_path(work_dir)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    bestand = read_manifest(work_dir)
    bestand.update({i: _text_fingerprint(t) for i, t in texte.items()})
    try:
        pfad.write_text(
            json.dumps({"version": 1,
                        "texte": {str(i): h for i, h in sorted(bestand.items())}},
                       ensure_ascii=False, indent=1),
            encoding="utf-8")
    except OSError as exc:
        _LOG.warning("Verzeichnis konnte nicht geschrieben werden: %s", exc)


def classify_recordings(pack: DialectPack, work_dir: Path):
    """Teilt vorhandene Aufnahmen in passend, übernommen und veraltet.

    Die Regel ist bewusst grosszügig, damit selbst eingespielte oder aus
    einer Sicherung zurückkopierte Aufnahmen erhalten bleiben:

    * Der Vermerk passt zum aktuellen Text  -> passend, wird verwendet.
    * Es gibt gar keinen Vermerk            -> übernommen. Das ist der
      Fall bei Dateien aus einer Sicherung oder aus einem früheren
      Programmstand. Sie werden benutzt und nachträglich vermerkt.
    * Der Vermerk nennt einen anderen Text  -> veraltet. Nur hier ist
      belegt, dass die Aufnahme nicht mehr zum Text gehört.

    Wer eine einzelne Datei von Hand überschreibt, behält sie also: Der
    Text hat sich nicht geändert, der Vermerk passt weiterhin.
    """
    ordner = Path(work_dir) / "gesprochen"
    passend: Dict[int, Path] = {}
    uebernommen: Dict[int, Path] = {}
    veraltet: List[int] = []

    if not ordner.is_dir():
        return passend, uebernommen, veraltet

    verzeichnis = read_manifest(work_dir)

    for datei in sorted(ordner.iterdir()):
        if not (datei.is_file() and datei.stem.isdigit()
                and datei.suffix.lower() in (".wav", ".mp3")):
            continue
        if datei.stat().st_size <= 500:
            continue

        sound_id = int(datei.stem)
        text = pack.texts.get(sound_id)
        if text is None:
            continue          # Ansage gehört nicht zu diesem Dialekt

        vermerkt = verzeichnis.get(sound_id)
        if vermerkt is None:
            uebernommen[sound_id] = datei
        elif vermerkt == _text_fingerprint(text):
            passend[sound_id] = datei
        else:
            veraltet.append(sound_id)

    return passend, uebernommen, veraltet


def usable_recordings(pack: DialectPack, work_dir: Path) -> Dict[int, Path]:
    """Alle Aufnahmen, die weiterverwendet werden können."""
    passend, uebernommen, _ = classify_recordings(pack, work_dir)
    return {**passend, **uebernommen}


def spoken_count(work_dir: Path, pack: Optional[DialectPack] = None) -> int:
    """Wie viele Ansagen brauchbar vorliegen.

    Ohne `pack` wird nur gezählt, was an Dateien da ist - das genügt für
    eine grobe Anzeige. Mit `pack` wird zusätzlich geprüft, ob die
    Aufnahmen zum aktuellen Text gehören.
    """
    if pack is not None:
        return len(usable_recordings(pack, work_dir))

    ordner = Path(work_dir) / "gesprochen"
    if not ordner.is_dir():
        return 0
    return len([p for p in ordner.iterdir()
                if p.is_file() and p.suffix.lower() in (".wav", ".mp3")
                and p.stem.isdigit() and p.stat().st_size > 500])


def remaining_texts(pack: DialectPack, work_dir: Path) -> Dict[int, str]:
    """Die Ansagen, die noch gesprochen werden müssen."""
    fertig = set(usable_recordings(pack, work_dir))
    return {i: t for i, t in pack.texts.items() if i not in fertig}


def stale_recordings(pack: DialectPack, work_dir: Path) -> List[int]:
    """Aufnahmen, deren Text sich nachweislich geändert hat."""
    return classify_recordings(pack, work_dir)[2]


def forget_cached_audio(pack: DialectPack, sound_ids: Iterable[int]) -> int:
    """Wirft gespeicherte Aufnahmen weg, deren Text sich geändert hat.

    Ohne das würde die App den alten Ton weiterverwenden - der Text wäre
    geändert, die Ansage aber unverändert.
    """
    entfernt = 0
    for ordner in cache_dirs(pack):
        for sound_id in sound_ids:
            for unterordner in ("gesprochen", "umgewandelt"):
                for endung in (".wav", ".mp3", ".ogg"):
                    datei = ordner / unterordner / f"{sound_id}{endung}"
                    if datei.is_file():
                        datei.unlink(missing_ok=True)
                        entfernt += 1
    return entfernt


def _noop_log(_: str) -> None:
    pass


def generate(dialect: DialectPack,
             base_pack: Path,
             work_dir: Path,
             ffmpeg: Optional[Path] = None,
             voice: str = "",
             engine: str = ENGINE_WINDOWS,
             api_key: str = "",
             voice_id: str = "",
             model: str = "",
             voice_settings: Optional[Dict[str, float]] = None,
             use_voice_settings: bool = True,
             mapping: Optional[Dict[int, int]] = None,
             rate: Optional[int] = None,
             pitch: Optional[int] = None,
             log: LogFn = _noop_log,
             progress: Optional[ProgressFn] = None,
             cancelled: Optional[Callable[[], bool]] = None) -> BuildResult:
    """Spricht die Texte, wandelt sie um und baut daraus ein Sprachpaket.

    `engine` entscheidet, wer spricht: die Windows-Sprachausgabe (offline,
    aber hochdeutsche Aussprache) oder ElevenLabs (echter bayerischer
    Akzent, benötigt einen eigenen Zugangsschlüssel).
    """
    cancelled = cancelled or (lambda: False)
    rate = dialect.rate if rate is None else rate
    pitch = dialect.pitch if pitch is None else pitch

    if not base_pack or not Path(base_pack).is_file():
        raise PackError(
            "Das Originalpaket deines Roboters fehlt.",
            "Lade es in Tab 2 herunter - es ist die Grundlage jedes Pakets.")

    if ffmpeg is None:
        raise AudioError(
            "Für die Umwandlung wird ffmpeg gebraucht.",
            "Richte ffmpeg in Tab 2 ein - ohne den Vorbis-Kodierer lässt sich "
            "aus der Sprachausgabe kein Sprachpaket bauen.")

    work_dir = Path(work_dir)
    wav_dir = work_dir / "gesprochen"
    ogg_dir = work_dir / "umgewandelt"
    wav_dir.mkdir(parents=True, exist_ok=True)
    ogg_dir.mkdir(parents=True, exist_ok=True)

    # Der X50 Ultra Complete gibt es in zwei Varianten: r2532h mit 558
    # Ansagen, r2532v mit 613. Die Dialekttexte decken beide ab - gesprochen
    # wird aber nur, was im Originalpaket dieses Roboters wirklich vorkommt.
    # Das spart Zeit und, bei ElevenLabs, bares Kontingent.
    vorhandene_ids = set(list_sound_ids(Path(base_pack)))
    ueberzaehlig = set(dialect.texts) - vorhandene_ids if vorhandene_ids else set()
    if ueberzaehlig:
        dialect = replace(dialect, texts={
            i: t for i, t in dialect.texts.items() if i in vorhandene_ids})
        log(f"{len(ueberzaehlig)} Ansagen gibt es bei diesem Modell nicht "
            f"und werden übersprungen.")

    # ---- 1. Sprechen -------------------------------------------------
    # Nur das sprechen, was fehlt oder nachweislich nicht mehr passt.
    passend, uebernommen, veraltet = classify_recordings(dialect, work_dir)

    if uebernommen:
        log(f"{len(uebernommen)} vorhandene Aufnahmen ohne Herkunftsvermerk "
            f"übernommen (z. B. aus einer Sicherung) - sie werden nicht neu "
            f"gesprochen.")
        # Nachtragen, damit sie ab jetzt zugeordnet sind.
        write_manifest(work_dir, {i: dialect.texts[i] for i in uebernommen})

    if veraltet:
        log(f"{len(veraltet)} Aufnahmen gehören zu einem inzwischen geänderten "
            f"Text und werden neu gesprochen.")
        for sound_id in veraltet:
            for endung in (".wav", ".mp3"):
                (wav_dir / f"{sound_id}{endung}").unlink(missing_ok=True)

    brauchbar = {**passend, **uebernommen}
    offen = {i: t for i, t in dialect.texts.items() if i not in brauchbar}
    if brauchbar:
        log(f"{len(brauchbar)} Ansagen liegen schon vor, "
            f"{len(offen)} sind zu sprechen.")

    log(f"Spreche {len(offen)} von {dialect.count} Ansagen auf "
        f"{dialect.name} ...")

    if not offen:
        log("Alle Ansagen liegen bereits vor - es wird nichts neu gesprochen.")
        wavs = dict(brauchbar)
    elif engine == ENGINE_ELEVENLABS:
        from . import elevenlabs
        log(f"Sprachdienst: ElevenLabs "
            f"({elevenlabs.estimate_characters(offen)} Zeichen)")
        neu = elevenlabs.synthesize(
            offen, wav_dir, api_key=api_key, voice_id=voice_id,
            log=log,
            progress=lambda done, total: (
                progress(len(brauchbar) + done, dialect.count * 2)
                if progress else None),
            cancelled=cancelled,
            model=model,
            voice_settings=voice_settings,
            use_voice_settings=use_voice_settings,
        )
        write_manifest(work_dir, {i: offen[i] for i in neu if i in offen})
        wavs = {**brauchbar, **neu}
    else:
        neu = tts.synthesize(
            offen, wav_dir, voice=voice, rate=rate, pitch=pitch,
            log=log,
            progress=lambda done, total: (
                progress(len(brauchbar) + done, dialect.count * 2)
                if progress else None),
        )
        write_manifest(work_dir, {i: offen[i] for i in neu if i in offen})
        wavs = {**brauchbar, **neu}

    if cancelled():
        raise PackError("Vom Benutzer abgebrochen.")

    # ---- 2. Umwandeln -------------------------------------------------
    log("Wandle in das Format des Roboters um (OGG Vorbis, mono, 16 kHz) ...")
    # Jede neue Ansage bekommt die Lautheit der deutschen Originalansage,
    # die sie ersetzt. Sonst klingt der Dialekt neben den verbliebenen
    # Originalen leiser.
    pegel = reference_levels(Path(base_pack), ffmpeg, log=log, cancelled=cancelled)
    assignments: Dict[int, Path] = {}
    total = len(wavs)
    for index, (sound_id, wav) in enumerate(sorted(wavs.items()), 1):
        if cancelled():
            raise PackError("Vom Benutzer abgebrochen.")
        target = ogg_dir / f"{sound_id}.ogg"
        convert_to_pack_format(wav, target, ffmpeg,
                               target_lufs=target_for(pegel, sound_id))
        assignments[sound_id] = target
        if progress:
            progress(total + index, total * 2)

    log(f"{len(assignments)} Ansagen umgewandelt.")

    fehlend = dialect.count - len(assignments)
    if fehlend > 0:
        log(f"Hinweis: {fehlend} Ansagen fehlen noch und bleiben auf der "
            f"deutschen Originalstimme.")

    # ---- 3. Paket bauen ------------------------------------------------
    result = build_pack(
        base_pack=Path(base_pack),
        assignments=assignments,
        out_name=f"dialekt_{dialect.key}.tar.gz",
        ffmpeg=ffmpeg,
        work_dir=work_dir / "paket",
        mapping=mapping,
        log=log,
    )
    if fehlend > 0:
        result.warnings.append(
            f"{fehlend} von {dialect.count} Ansagen konnten nicht gesprochen "
            f"werden und bleiben Hochdeutsch. Starte die Erzeugung später "
            f"einfach erneut - die App macht dort weiter, wo sie aufgehört hat.")
    log(f"Fertig: {result.summary()}")
    return result


def preview_texts(dialect: DialectPack, limit: int = 8) -> List[str]:
    """Ein paar Beispielsätze für die Anzeige in der Oberfläche."""
    lines: List[str] = []
    for sound_id in HIGHLIGHTS:
        text = dialect.texts.get(sound_id)
        if text:
            lines.append(f"{sound_id}: {text}")
        if len(lines) >= limit:
            break
    return lines


# Ansagen, die eine Kostprobe gut abbilden: Start, Ende, Fehler, Nachfrage.
HIGHLIGHTS = [7, 12, 40, 13, 111, 515, 421, 247, 20, 331]


def sample_texts(dialect: DialectPack, count: int = 3) -> Dict[int, str]:
    """Die Sätze, die für eine Hörprobe gesprochen werden.

    Bewusst kurz gehalten: bei ElevenLabs kostet jede Hörprobe Zeichen aus
    dem Monatskontingent, und drei Sätze reichen, um den Klang zu beurteilen.
    """
    chosen: Dict[int, str] = {}
    for sound_id in HIGHLIGHTS:
        text = dialect.texts.get(sound_id)
        if text:
            chosen[sound_id] = text
        if len(chosen) >= count:
            break
    return chosen


def speak_one(text: str,
              work_dir: Path,
              engine: str = ENGINE_WINDOWS,
              voice: str = "",
              api_key: str = "",
              voice_id: str = "",
              model: str = "",
              voice_settings: Optional[Dict[str, float]] = None,
              use_voice_settings: bool = True,
              rate: int = 0,
              pitch: int = 0,
              log: LogFn = _noop_log) -> Path:
    """Spricht einen einzelnen Satz - zum Anhören beim Texte-Ändern.

    Damit lässt sich eine umformulierte Ansage sofort mit der Stimme
    prüfen, die später auch das ganze Paket spricht.
    """
    text = (text or "").strip()
    if not text:
        raise AudioError("Der Text ist leer.")

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Eigener Name je Text, damit eine Änderung nicht die alte Aufnahme trifft.
    kennung = hashlib.md5(
        f"{engine}|{voice}|{voice_id}|{model}|{rate}|{pitch}|{text}"
        .encode("utf-8")).hexdigest()[:10]
    ziel = work_dir / f"probe_{kennung}"

    if engine == ENGINE_ELEVENLABS:
        from . import elevenlabs
        fertig = ziel.with_suffix(".mp3")
        if fertig.is_file() and fertig.stat().st_size > 500:
            return fertig
        dateien = elevenlabs.synthesize(
            {0: text}, work_dir / f"_{kennung}", api_key=api_key,
            voice_id=voice_id, model=model, voice_settings=voice_settings,
            use_voice_settings=use_voice_settings, log=log)
    else:
        fertig = ziel.with_suffix(".wav")
        if fertig.is_file() and fertig.stat().st_size > 500:
            return fertig
        dateien = tts.synthesize({0: text}, work_dir / f"_{kennung}",
                                 voice=voice, rate=rate, pitch=pitch, log=log)

    if not dateien:
        raise AudioError("Der Satz konnte nicht gesprochen werden.")

    quelle = next(iter(dateien.values()))
    fertig.write_bytes(quelle.read_bytes())
    return fertig


def preview(dialect: DialectPack,
            work_dir: Path,
            engine: str = ENGINE_WINDOWS,
            voice: str = "",
            api_key: str = "",
            voice_id: str = "",
            model: str = "",
            voice_settings: Optional[Dict[str, float]] = None,
            use_voice_settings: bool = True,
            rate: Optional[int] = None,
            pitch: Optional[int] = None,
            ffmpeg: Optional[Path] = None,
            count: int = 3,
            log: LogFn = _noop_log) -> List[Path]:
    """Spricht ein paar Sätze zur Probe und gibt die Dateien zurück.

    Wird gebraucht, damit man vor dem Erzeugen des ganzen Pakets hören
    kann, wie das Ergebnis klingt - und ob einem Stimme und Dialekt
    überhaupt gefallen.
    """
    texts = sample_texts(dialect, count)
    if not texts:
        raise AudioError("Für diesen Dialekt gibt es keine Beispielsätze.")

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    if engine == ENGINE_ELEVENLABS:
        from . import elevenlabs
        chars = sum(len(t) for t in texts.values())
        log(f"Hörprobe über ElevenLabs ({chars} Zeichen)")
        files = elevenlabs.synthesize(texts, work_dir, api_key=api_key,
                                      voice_id=voice_id, log=log,
                                      model=model,
                                      voice_settings=voice_settings,
                                      use_voice_settings=use_voice_settings)
    else:
        log("Hörprobe über die Windows-Sprachausgabe")
        files = tts.synthesize(
            texts, work_dir, voice=voice,
            rate=dialect.rate if rate is None else rate,
            pitch=dialect.pitch if pitch is None else pitch, log=log)

    einzeln = [files[i] for i in sorted(files)]
    if len(einzeln) < 2:
        return einzeln

    # Zu einer Datei zusammenfügen: der Standardplayer spielt sonst nur
    # die erste Aufnahme ab.
    zusammen = concat_with_pauses(einzeln, work_dir / "kostprobe.wav", ffmpeg)
    if zusammen not in einzeln:
        log(f"{len(einzeln)} Sätze zu einer Hörprobe zusammengefügt.")
        return [zusammen]

    log("Sätze konnten nicht zusammengefügt werden - es läuft nur der erste.")
    return einzeln
