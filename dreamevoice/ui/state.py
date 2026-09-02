"""Gemeinsamer Zustand aller Tabs und Hilfen für Hintergrundarbeit.

Tkinter ist nicht threadsicher: Widgets dürfen ausschließlich aus dem
Hauptthread verändert werden. Netzwerk- und Dateiarbeit gehört aber
keinesfalls in den Hauptthread, sonst friert das Fenster ein.

`run_async` löst das: die eigentliche Arbeit läuft in einem Thread, alle
Rückmeldungen werden über `widget.after(0, ...)` in den Hauptthread
zurückgereicht.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import audio
from ..cloud import DreameCloud, Device
from ..config import Config
from ..errors import DreameError
from ..official import VoicePackInfo
from ..packer import BuildResult
from ..sounds import SoundCatalog

_LOG = logging.getLogger(__name__)


class AppState:
    """Alles, was mehrere Tabs gemeinsam brauchen."""

    def __init__(self) -> None:
        self.config: Config = Config.load()
        self.cloud: Optional[DreameCloud] = None
        self.device: Optional[Device] = None
        self.devices: List[Device] = []

        self.catalog: SoundCatalog = SoundCatalog.load()
        self.official_packs: List[VoicePackInfo] = []
        self.base_pack_path: Optional[Path] = None
        self.base_pack_info: Optional[VoicePackInfo] = None
        self.previews: Dict[int, Path] = {}

        self.last_build: Optional[BuildResult] = None
        # Fertiges Paket aus dem Community-Tab: wird direkt installiert,
        # ohne aus den eigenen Zuweisungen neu gebaut zu werden.
        self.prebuilt: Optional[BuildResult] = None
        self.prebuilt_name: str = ""
        self._ffmpeg: Optional[Path] = None
        self._mapping_cache: Dict[int, int] = {}
        self._mapping_cache_key: tuple = ()

        self._listeners: Dict[str, List[Callable[[], None]]] = {}

    # -- ffmpeg -----------------------------------------------------------
    @property
    def ffmpeg(self) -> Optional[Path]:
        """Wo ffmpeg liegt - selbst gesucht, nicht von einer Seite gesetzt.

        Früher setzte allein die Seite "Einzelne Ansagen" diesen Wert.
        Seit die Seiten erst beim Öffnen gebaut werden, blieb er None,
        wenn man sie nie aufschlug - "Anhören" scheiterte dann bei
        jeder Stimme, und der Hinweis schob es auf ein fehlendes
        ffmpeg, das längst im Datenordner lag.

        Gesucht wird höchstens einmal mit Erfolg: Ein gefundener Pfad
        wird gemerkt, ein erfolgloser nicht - sonst bliebe die Suche
        auch dann erfolglos, wenn ffmpeg zwischendurch ausgepackt wird.
        """
        if self._ffmpeg is None:
            self._ffmpeg = audio.find_ffmpeg()
        return self._ffmpeg

    @ffmpeg.setter
    def ffmpeg(self, wert: Optional[Path]) -> None:
        """Nach dem Auspacken trägt BuilderTab den frischen Pfad ein."""
        self._ffmpeg = wert

    # -- Ereignisse zwischen den Tabs -------------------------------------
    def subscribe(self, event: str, callback: Callable[[], None]) -> None:
        self._listeners.setdefault(event, []).append(callback)

    def notify(self, event: str) -> None:
        # Beim Roboterwechsel gehört alles verworfen, was zum alten
        # Modell gehört - und zwar HIER, nicht in einer Seite.
        #
        # Früher stand das in "Einzelne Ansagen". Seit die Seiten erst
        # beim ersten Öffnen entstehen, lief es bei den meisten
        # Benutzern nie: Wer die Seite nie aufmacht, behält nach einem
        # Gerätewechsel das Originalpaket und die Sprachliste des
        # vorigen Modells - und schickt im schlimmsten Fall dessen
        # Paket an den neuen Roboter.
        # "device_changed" heißt: ein ANDERER Roboter. Nicht: derselbe
        # Roboter spricht jetzt anders. Für das Zweite gibt es
        # "pack_installed" - es verwirft nichts, sondern lässt die
        # Seiten nur ihre Anzeige auffrischen. page_voice hat früher
        # das falsche der beiden gemeldet und sich damit nach jeder
        # erfolgreichen Installation selbst den Boden weggezogen.
        if event == "device_changed":
            self._geraetestand_verwerfen()
        for callback in self._listeners.get(event, []):
            try:
                callback()
            except Exception:  # pragma: no cover - ein Tab darf andere nicht reißen
                _LOG.exception("Fehler im Listener für %r", event)

    def _geraetestand_verwerfen(self) -> None:
        """Alles vergessen, was nur zum bisherigen Roboter passt."""
        self.base_pack_path = None
        self.official_packs = []

    # -- Abgeleitete Angaben ----------------------------------------------
    @property
    def connected(self) -> bool:
        return bool(self.cloud and self.cloud.logged_in and self.device)

    @property
    def model(self) -> str:
        return self.device.model if self.device else self.config["device_model"]

    @property
    def has_base_pack(self) -> bool:
        return bool(self.base_pack_path and self.base_pack_path.is_file())

    def voice_mapping(self) -> Dict[int, int]:
        """Nummern-Umsetzung des eigenen Modells (siehe official.read_voice_mapping).

        Wird gepuffert: die Datei liegt im Originalpaket und ändert sich
        während einer Sitzung nicht.
        """
        if not self.has_base_pack or not self.model:
            return {}
        schluessel = (str(self.base_pack_path), self.model)
        if self._mapping_cache_key != schluessel:
            from ..official import read_voice_mapping
            self._mapping_cache = read_voice_mapping(self.base_pack_path, self.model)
            self._mapping_cache_key = schluessel
        return self._mapping_cache

    def assignments(self) -> Dict[int, Path]:
        """Zuordnungen aus der Konfiguration, nur mit existierenden Dateien."""
        result: Dict[int, Path] = {}
        for key, value in self.config["assignments"].items():
            try:
                sound_id = int(key)
            except (TypeError, ValueError):
                continue
            path = Path(value)
            if path.is_file():
                result[sound_id] = path
        return result

    def missing_assignments(self) -> List[tuple[int, str]]:
        """Zuordnungen, deren Datei inzwischen fehlt."""
        missing = []
        for key, value in self.config["assignments"].items():
            if not Path(value).is_file():
                try:
                    missing.append((int(key), value))
                except (TypeError, ValueError):
                    continue
        return sorted(missing)

    def save(self) -> None:
        self.config.save()


class Task:
    """Griff auf einen laufenden Hintergrundvorgang."""

    def __init__(self) -> None:
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()


def run_async(widget: tk.Misc,
              work: Callable[..., Any],
              on_success: Optional[Callable[[Any], None]] = None,
              on_error: Optional[Callable[[Exception], None]] = None,
              on_finally: Optional[Callable[[], None]] = None,
              task: Optional[Task] = None) -> Task:
    """Führt `work` in einem Thread aus und meldet sich im Hauptthread zurück.

    `work` bekommt den Task als einziges Argument und kann darüber prüfen,
    ob der Benutzer abgebrochen hat. Absichtlich keine Bequemlichkeits-
    Variante ohne Parameter: ein TypeError aus dem Inneren von `work` ließe
    sich sonst nicht von einer falschen Signatur unterscheiden, und die
    Arbeit würde im Fehlerfall ein zweites Mal laufen.
    """
    task = task or Task()

    def zurueck(fn: Callable[[], None]) -> None:
        """Rückmeldung in den Hauptthread - oder still verwerfen.

        Ist das Fenster inzwischen zu, gibt es niemanden mehr, dem man
        etwas melden könnte. Ohne diese Schranke meldete Tk dann
        "invalid command name ..." - im Bauprotokoll gut zu sehen, weil
        die Testsuite viele Fenster öffnet und schließt, während
        Hintergrundarbeit noch läuft. Beim Benutzer wäre es dasselbe,
        wenn er die App während eines Downloads beendet.
        """
        try:
            if widget.winfo_exists():
                # spaeter() statt after(): Die Prüfung oben greift beim
                # PLANEN. Wird das Fenster danach geschlossen - und genau
                # das passiert, wenn jemand die App während eines
                # Downloads beendet -, feuert der Auftrag trotzdem ins
                # Leere. spaeter() bestellt ihn beim Zerstören ab.
                spaeter(widget, 0, fn)
        except (tk.TclError, RuntimeError):
            pass

    def runner() -> None:
        try:
            result = work(task)
        except Exception as exc:  # noqa: BLE001 - wird an die GUI weitergereicht
            if not isinstance(exc, DreameError):
                _LOG.exception("Hintergrundvorgang fehlgeschlagen")
            if on_error:
                zurueck(lambda e=exc: on_error(e))
        else:
            if on_success:
                zurueck(lambda r=result: on_success(r))
        finally:
            if on_finally:
                zurueck(on_finally)

    threading.Thread(target=runner, daemon=True).start()
    return task


def spaeter(widget: tk.Misc, ms: int, fn: Callable[[], Any]):
    """Wie `widget.after()`, aber der Auftrag verfällt mit dem Widget.

    Tk löscht beim Zerstören den registrierten Befehl - der Zeitauftrag
    bleibt aber stehen und feuert ins Leere. Tk meldet dann
    "invalid command name ...". Eine Prüfung IM Rückruf hilft nicht,
    weil Tk ihn gar nicht mehr aufrufen kann; der Auftrag muss
    abbestellt werden.

    Sichtbar wurde das im Bauprotokoll, wo die Testsuite viele Fenster
    öffnet und schließt. Beim Benutzer steht es im Protokoll, wenn er
    die App während einer laufenden Abfrage beendet.
    """
    kennung = widget.after(ms, fn)

    def _abbestellen(ereignis, _k=kennung, _w=widget):
        # Nur das eigene Zerstören zählt: <Destroy> steigt auch von
        # Kindwidgets auf, und deren Ende darf den Auftrag nicht
        # vorzeitig löschen.
        if ereignis.widget is _w:
            try:
                _w.after_cancel(_k)
            except (tk.TclError, ValueError):
                pass

    widget.bind("<Destroy>", _abbestellen, add="+")
    return kennung


def to_main(widget: tk.Misc, fn: Callable[..., Any], *args: Any) -> None:
    """Ruft `fn` im Hauptthread auf (für Fortschritts-Rückmeldungen)."""
    try:
        spaeter(widget, 0, lambda: fn(*args))
    except (tk.TclError, RuntimeError):
        pass  # Fenster wurde bereits geschlossen


def error_text(exc: Exception) -> tuple[str, str]:
    """Zerlegt eine Ausnahme in (Meldung, Hinweis) für die Anzeige."""
    if isinstance(exc, DreameError):
        return exc.message, exc.hint
    return str(exc) or exc.__class__.__name__, ""
