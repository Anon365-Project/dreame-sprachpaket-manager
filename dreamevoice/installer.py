"""Der eigentliche Installationsablauf.

Reihenfolge:

1. Webserver starten, der genau das gebaute Paket ausliefert.
2. Über die Dreame-Cloud den Auftrag an den Roboter schicken
   (MIoT-Eigenschaft 7/4) - mit URL, MD5 und Größe.
3. Warten, bis der Roboter die Datei tatsächlich abholt.
4. Den Installationszustand abfragen, bis er fertig meldet.
5. Webserver in jedem Fall wieder schließen.

Der Roboter prüft das Archiv selbst gegen MD5 und Größe. Stimmt etwas
nicht, verwirft er es und behält die bisherige Stimme - genau das macht
den Vorgang unkritisch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .cloud import DreameCloud, Device
from .errors import InstallError, NetworkError
from .official import VoicePackInfo
from .packer import BuildResult
from .server import PackServer, reachability_hint

_LOG = logging.getLogger(__name__)

LogFn = Callable[[str], None]
StepFn = Callable[[str, float], None]   # (Beschreibung, Fortschritt 0..1)

# Kennungen, die Dreame selbst vergibt. Wer eine davon überschreibt,
# verliert die Möglichkeit, per Knopfdruck dorthin zurückzukehren.
OFFICIAL_LANG_IDS = {
    "ZH", "EN", "DE", "RU", "FR", "KO", "ES", "IT", "JA", "PL",
    "TR", "SV", "DA", "NB", "PT", "THA", "VI", "UK", "HE",
}
DEFAULT_CUSTOM_LANG_ID = "CUSTOM"


def validate_lang_id(lang_id: str) -> tuple[str, str]:
    """Prüft die Paketkennung. Rückgabe: (bereinigt, Warnung oder "")."""
    cleaned = (lang_id or "").strip().upper()
    if not cleaned:
        return DEFAULT_CUSTOM_LANG_ID, ""
    if not cleaned.isalnum() or len(cleaned) > 8:
        raise InstallError(
            f"Die Paketkennung '{lang_id}' ist ungültig.",
            "Erlaubt sind bis zu 8 Buchstaben oder Ziffern, z. B. CUSTOM oder BAYERN.",
        )
    if cleaned in OFFICIAL_LANG_IDS:
        return cleaned, (
            f"'{cleaned}' ist eine offizielle Dreame-Kennung. Dein Paket "
            f"überschreibt damit die mitgelieferte Sprache. Zum Zurückwechseln "
            f"musst du das Originalpaket erneut installieren - das kann diese "
            f"App, aber eine eigene Kennung wie CUSTOM ist bequemer."
        )
    return cleaned, ""


@dataclass
class InstallOutcome:
    success: bool
    message: str
    downloaded: bool = False
    final_status: Optional[str] = None
    hint: str = ""


def _noop_log(_: str) -> None:
    pass


def _noop_step(_msg: str, _p: float) -> None:
    pass


def install_pack(cloud: DreameCloud,
                 device: Device,
                 build: BuildResult,
                 lang_id: str,
                 port: int = 0,
                 host_ip: str = "",
                 public_url: str = "",
                 log: LogFn = _noop_log,
                 step: StepFn = _noop_step,
                 download_timeout: float = 120.0,
                 install_timeout: float = 420.0,
                 cancelled: Optional[Callable[[], bool]] = None) -> InstallOutcome:
    """Installiert ein gebautes Paket auf dem Roboter."""

    cancelled = cancelled or (lambda: False)
    lang_id, warning = validate_lang_id(lang_id)
    if warning:
        log(f"Hinweis: {warning}")

    log(f"Paket:  {build.path.name}")
    log(f"Größe: {build.size} Bytes ({build.size_mb:.1f} MB)")
    log(f"MD5:    {build.md5}")
    log(f"Kennung: {lang_id}")

    server: Optional[PackServer] = None
    try:
        # ---- 1. Auslieferung vorbereiten -------------------------------
        if public_url:
            url = public_url.strip()
            log(f"Verwende eigene URL: {url}")
            step("Eigene URL wird verwendet", 0.15)
        else:
            step("Webserver wird gestartet", 0.05)
            server = PackServer(build.path, port=port, host_ip=host_ip, log=log)
            url = server.start()
            step("Webserver läuft", 0.15)

        # ---- 2. Auftrag senden ------------------------------------------
        step("Roboter wird geprüft", 0.20)
        log("Frage beim Roboter nach, ob er Sprachpakete auf dem üblichen "
            "Weg entgegennimmt ...")
        if not cloud.supports_voice_service(device):
            return InstallOutcome(
                False,
                "Dieser Roboter meldet keinen Sprachpaket-Dienst.",
                hint=("Die App hat vorsichtshalber nichts gesendet. Der "
                      "Installationsauftrag geht bei Dreame- und "
                      "MOVA-Saugrobotern immer an dieselbe Stelle "
                      "(MIoT siid 7, piid 4); dein Gerät antwortet dort "
                      "aber nicht. Das spricht dafür, dass es Sprachpakete "
                      "gar nicht kennt - etwa bei Mährobotern oder sehr "
                      "alten Modellen aus der Mi-Home-App.\n\n"
                      "Prüfe, ob du in der Dreamehome-App unter "
                      "'Sprachton' überhaupt Sprachen auswählen kannst. "
                      "Geht das dort nicht, kann es diese App auch nicht."),
            )
        log("Der Roboter kennt den Sprachpaket-Dienst.")

        step("Auftrag wird an den Roboter geschickt", 0.25)
        log("Sende Installationsauftrag über die Dreame-Cloud ...")
        try:
            cloud.install_voice_pack(device, lang_id, url, build.md5, build.size)
        except NetworkError as exc:
            return InstallOutcome(
                False,
                "Der Roboter hat den Auftrag nicht angenommen.",
                hint=str(exc),
            )
        log("Auftrag angenommen.")

        # ---- 3. Auf den Download warten ---------------------------------
        if server is not None:
            step("Roboter lädt das Paket herunter", 0.4)
            log(f"Warte bis zu {int(download_timeout)} Sekunden auf den Download ...")

            deadline = time.time() + download_timeout
            while time.time() < deadline and not server.was_downloaded:
                if cancelled():
                    return InstallOutcome(False, "Vom Benutzer abgebrochen.")
                server.wait_for_download(1.0)

            if not server.was_downloaded:
                return InstallOutcome(
                    False,
                    "Der Roboter hat das Sprachpaket nicht abgeholt.",
                    hint=reachability_hint(server.port),
                )
            log("Download durch den Roboter bestätigt.")
            step("Paket übertragen", 0.6)
        else:
            step("Warte auf den Roboter", 0.4)
            time.sleep(5)

        # ---- 4. Installation beobachten ---------------------------------
        step("Roboter installiert das Paket", 0.7)
        log("Warte auf die Rückmeldung des Roboters ...")

        deadline = time.time() + install_timeout
        last_status = None
        active_pack = None

        while time.time() < deadline:
            if cancelled():
                return InstallOutcome(False, "Vom Benutzer abgebrochen.",
                                      downloaded=True)
            time.sleep(6)

            status = cloud.voice_change_status(device)
            if status != last_status and status is not None:
                log(f"Zustand: {status}")
                last_status = status

            active_pack = cloud.current_voice_pack(device)
            if active_pack and str(active_pack).upper() == lang_id:
                step("Fertig", 1.0)
                log(f"Der Roboter meldet '{active_pack}' als aktives Sprachpaket.")
                return InstallOutcome(
                    True,
                    f"Das Sprachpaket '{lang_id}' ist installiert und aktiv.",
                    downloaded=True,
                    final_status=str(last_status) if last_status is not None else None,
                )

            progress = 0.7 + min(0.25, (time.time() - (deadline - install_timeout)) / install_timeout * 0.25)
            step("Roboter installiert das Paket", progress)

        # Zeit abgelaufen, aber der Download hat geklappt.
        return InstallOutcome(
            False,
            "Der Roboter hat die Installation nicht innerhalb der Wartezeit bestätigt.",
            downloaded=True,
            final_status=str(last_status) if last_status is not None else None,
            hint=("Das Paket wurde nachweislich heruntergeladen. Sehr wahrscheinlich "
                  "läuft die Installation noch oder ist bereits fertig. Der Roboter "
                  "sagt bei Erfolg 'Sprache erfolgreich gewechselt'. Prüfe die "
                  "Stimme am Gerät; falls sie unverändert ist, starte den Vorgang "
                  "einfach erneut."),
        )

    except InstallError:
        raise
    except Exception as exc:  # pragma: no cover - unerwartete Fälle
        _LOG.exception("Installation fehlgeschlagen")
        return InstallOutcome(False, "Unerwarteter Fehler bei der Installation.",
                              hint=str(exc))
    finally:
        if server is not None:
            server.stop()


def restore_official(cloud: DreameCloud,
                     device: Device,
                     pack: VoicePackInfo,
                     log: LogFn = _noop_log,
                     step: StepFn = _noop_step,
                     timeout: float = 420.0) -> InstallOutcome:
    """Stellt ein offizielles Sprachpaket wieder her.

    Hier wird bewusst Dreames eigene Download-URL benutzt - der Roboter
    lädt also direkt beim Hersteller, ganz ohne PC im Spiel. Das ist
    derselbe Vorgang, den die Dreamehome-App beim Sprachwechsel auslöst.
    """
    log(f"Stelle das offizielle Paket '{pack.label}' wieder her.")
    log(f"Quelle: {pack.url}")
    log(f"Größe: {pack.size} Bytes, MD5: {pack.md5}")

    step("Auftrag wird geschickt", 0.2)
    try:
        cloud.install_voice_pack(device, pack.id, pack.url, pack.md5, pack.size)
    except NetworkError as exc:
        return InstallOutcome(False, "Der Roboter hat den Auftrag nicht angenommen.",
                              hint=str(exc))

    log("Auftrag angenommen. Der Roboter lädt jetzt direkt bei Dreame.")
    step("Roboter lädt bei Dreame", 0.5)

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(6)
        active = cloud.current_voice_pack(device)
        if active and str(active).upper() == pack.id.upper():
            step("Fertig", 1.0)
            return InstallOutcome(True, f"Das Originalpaket '{pack.id}' ist wieder aktiv.",
                                  downloaded=True)

    return InstallOutcome(
        False,
        "Keine Bestätigung innerhalb der Wartezeit.",
        hint=("Der Auftrag wurde angenommen. Prüfe die Stimme am Roboter - "
              "oft ist die Installation trotzdem durchgelaufen. Alternativ "
              "lässt sich die Sprache jederzeit in der Dreamehome-App unter "
              "Einstellungen > Sprachpaket umstellen."),
    )
