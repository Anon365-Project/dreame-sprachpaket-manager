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
        self.ffmpeg: Optional[Path] = None
        self._mapping_cache: Dict[int, int] = {}
        self._mapping_cache_key: tuple = ()

        self._listeners: Dict[str, List[Callable[[], None]]] = {}

    # -- Ereignisse zwischen den Tabs -------------------------------------
    def subscribe(self, event: str, callback: Callable[[], None]) -> None:
        self._listeners.setdefault(event, []).append(callback)

    def notify(self, event: str) -> None:
        for callback in self._listeners.get(event, []):
            try:
                callback()
            except Exception:  # pragma: no cover - ein Tab darf andere nicht reissen
                _LOG.exception("Fehler im Listener für %r", event)

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
    Variante ohne Parameter: ein TypeError aus dem Inneren von `work` liesse
    sich sonst nicht von einer falschen Signatur unterscheiden, und die
    Arbeit würde im Fehlerfall ein zweites Mal laufen.
    """
    task = task or Task()

    def runner() -> None:
        try:
            result = work(task)
        except Exception as exc:  # noqa: BLE001 - wird an die GUI weitergereicht
            if not isinstance(exc, DreameError):
                _LOG.exception("Hintergrundvorgang fehlgeschlagen")
            if on_error:
                widget.after(0, lambda e=exc: on_error(e))
        else:
            if on_success:
                widget.after(0, lambda r=result: on_success(r))
        finally:
            if on_finally:
                widget.after(0, on_finally)

    threading.Thread(target=runner, daemon=True).start()
    return task


def to_main(widget: tk.Misc, fn: Callable[..., Any], *args: Any) -> None:
    """Ruft `fn` im Hauptthread auf (für Fortschritts-Rückmeldungen)."""
    try:
        widget.after(0, lambda: fn(*args))
    except (tk.TclError, RuntimeError):
        pass  # Fenster wurde bereits geschlossen


def error_text(exc: Exception) -> tuple[str, str]:
    """Zerlegt eine Ausnahme in (Meldung, Hinweis) für die Anzeige."""
    if isinstance(exc, DreameError):
        return exc.message, exc.hint
    return str(exc) or exc.__class__.__name__, ""
