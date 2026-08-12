"""Lesen und Schreiben der config.json.

Das Passwort wird - falls der Nutzer es merken lässt - mit der Windows-
Datenschutz-API (DPAPI) verschlüsselt. Der Schlüssel hängt am Windows-
Benutzerkonto: eine kopierte config.json ist auf einem anderen Rechner
oder unter einem anderen Benutzer wertlos. Ist DPAPI nicht verfügbar
(z. B. Linux/Mac), wird das Passwort bewusst gar nicht gespeichert.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict

from . import credentials
from .paths import config_file

_LOG = logging.getLogger(__name__)

DEFAULTS: Dict[str, Any] = {
    "email": "",
    "password_enc": "",          # DPAPI-Blob, base64. Leer = nicht gespeichert.
    "remember_password": False,
    "region": "eu",              # Dreamehome-Regionen: eu, cn, us, ru, sg, kr
    "account_type": "dreame",    # dreame | mova | trouver
    "device_id": "",             # did des gewählten Roboters
    "device_model": "",          # z. B. dreame.vacuum.r2532h
    "device_name": "",
    "device_mac": "",
    "base_language": "DE",       # Sprache des offiziellen Basis-Pakets
    "custom_lang_id": "CUSTOM",  # Kennung, unter der das eigene Paket landet
    "last_pack_name": "",        # was zuletzt auf den Roboter ging
    "assignments": {},           # {"7": "C:/pfad/zu/datei.wav", ...}
    "last_audio_dir": "",
    "serve_port": 0,             # 0 = freien Port automatisch wählen
    "host_ip": "",               # leer = automatisch ermitteln
    "dark_mode": False,
    # Sprachsynthese für Dialektpakete
    "tts_engine": "windows",     # windows | elevenlabs
    "tts_voice": "",             # Name der Windows-Stimme, leer = erste deutsche
    "tts_rate": 0,               # Tempo der Windows-Stimme, Stufen -6..6
    "tts_pitch": 0,              # Tonhöhe der Windows-Stimme, Stufen -6..6
    "elevenlabs_key_enc": "",    # DPAPI-Blob, base64
    "elevenlabs_voice_id": "",
    "elevenlabs_voice_name": "",
    "elevenlabs_model": "",          # leer = eleven_multilingual_v2
    # True = Klangeinstellungen der Stimme verwenden (wie in der Vorschau).
    "elevenlabs_use_voice_settings": True,
    "elevenlabs_stability": 0.35,    # nur bei eigenen Einstellungen
    "elevenlabs_style": 0.45,
    # Selbst geänderte Dialekttexte: {"bayerisch": {"7": "eigener Text"}}
    "dialect_overrides": {},
}


# --------------------------------------------------------------------------
# DPAPI (nur Windows)
# --------------------------------------------------------------------------

def _dpapi_available() -> bool:
    try:
        import ctypes  # noqa: F401
        import sys
        return sys.platform == "win32"
    except Exception:
        return False


def _dpapi(encrypt: bool, data: bytes) -> bytes:
    """Ruft CryptProtectData / CryptUnprotectData auf."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    def to_blob(raw: bytes) -> DATA_BLOB:
        buf = ctypes.create_string_buffer(raw, len(raw))
        return DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def from_blob(blob: DATA_BLOB) -> bytes:
        out = ctypes.string_at(blob.pbData, blob.cbData)
        ctypes.windll.kernel32.LocalFree(blob.pbData)
        return out

    fn = (ctypes.windll.crypt32.CryptProtectData if encrypt
          else ctypes.windll.crypt32.CryptUnprotectData)

    src = to_blob(data)
    dst = DATA_BLOB()
    entropy = to_blob(b"DreameSprachpakete")
    ok = fn(ctypes.byref(src), None, ctypes.byref(entropy), None, None, 0, ctypes.byref(dst))
    if not ok:
        raise OSError("DPAPI-Aufruf fehlgeschlagen")
    return from_blob(dst)


def encrypt_password(plain: str) -> str:
    """Gibt einen base64-DPAPI-Blob zurück, oder "" wenn nicht möglich."""
    if not plain or not _dpapi_available():
        return ""
    try:
        return base64.b64encode(_dpapi(True, plain.encode("utf-8"))).decode("ascii")
    except Exception as exc:
        _LOG.warning("Passwort konnte nicht verschlüsselt werden: %s", exc)
        return ""


def decrypt_password(blob_b64: str) -> str:
    if not blob_b64 or not _dpapi_available():
        return ""
    try:
        return _dpapi(False, base64.b64decode(blob_b64)).decode("utf-8")
    except Exception as exc:
        _LOG.warning("Passwort konnte nicht entschlüsselt werden: %s", exc)
        return ""


# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------

class Config:
    """Schlanker Wrapper um die config.json."""

    def __init__(self, values: Dict[str, Any] | None = None) -> None:
        self._values: Dict[str, Any] = dict(DEFAULTS)
        if values:
            # Nur bekannte Schlüssel übernehmen, damit alte Dateien nicht stören.
            self._values.update({k: v for k, v in values.items() if k in DEFAULTS})

    # -- Zugriff ----------------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._values[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._values)

    # -- Passwort ---------------------------------------------------------
    @property
    def password(self) -> str:
        if not self._values.get("remember_password"):
            return ""
        aus_speicher = credentials.load(credentials.TARGET_DREAME)
        if aus_speicher:
            return aus_speicher
        return decrypt_password(self._values.get("password_enc", ""))

    def set_password(self, plain: str, remember: bool) -> None:
        """Merkt das Passwort - bevorzugt im Windows-Anmeldespeicher."""
        merken = bool(remember and (credentials.available() or _dpapi_available()))
        self._values["remember_password"] = merken

        if not merken:
            credentials.delete(credentials.TARGET_DREAME)
            self._values["password_enc"] = ""
            return

        if credentials.available() and credentials.save(
                credentials.TARGET_DREAME, plain,
                username=self._values.get("email", "")):
            self._values["password_enc"] = ""
            return

        self._values["password_enc"] = encrypt_password(plain)

    @property
    def password_location(self) -> str:
        if credentials.exists(credentials.TARGET_DREAME):
            return "Windows-Anmeldeinformationsspeicher"
        if self._values.get("password_enc"):
            return "config.json (verschlüsselt mit deinem Windows-Konto)"
        return "nicht gespeichert"

    @staticmethod
    def can_remember_password() -> bool:
        return credentials.available() or _dpapi_available()

    # -- Zugangsschlüssel für ElevenLabs ----------------------------------
    @property
    def elevenlabs_key(self) -> str:
        """Erst im Anmeldespeicher nachsehen, dann in der config.json."""
        aus_speicher = credentials.load(credentials.TARGET_ELEVENLABS)
        if aus_speicher:
            return aus_speicher
        return decrypt_password(self._values.get("elevenlabs_key_enc", ""))

    def set_elevenlabs_key(self, plain: str) -> None:
        """Legt den Schlüssel ab - bevorzugt im Windows-Anmeldespeicher.

        Dort ist er zentral einsehbar und lässt sich von Hand entfernen,
        und die config.json bleibt frei von Geheimnissen. Steht der
        Anmeldespeicher nicht zur Verfügung, greift die
        DPAPI-Verschlüsselung in der Konfigurationsdatei.
        """
        if credentials.available():
            if credentials.save(credentials.TARGET_ELEVENLABS, plain):
                # Eine eventuell ältere Kopie in der Datei entfernen.
                self._values["elevenlabs_key_enc"] = ""
                return
        self._values["elevenlabs_key_enc"] = encrypt_password(plain) if plain else ""

    @property
    def elevenlabs_key_location(self) -> str:
        """Wo der Schlüssel liegt - für die Anzeige."""
        if credentials.exists(credentials.TARGET_ELEVENLABS):
            return "Windows-Anmeldeinformationsspeicher"
        if self._values.get("elevenlabs_key_enc"):
            return "config.json (verschlüsselt mit deinem Windows-Konto)"
        return "nicht gespeichert"

    def forget_elevenlabs_key(self) -> None:
        credentials.delete(credentials.TARGET_ELEVENLABS)
        self._values["elevenlabs_key_enc"] = ""

    # -- Zuordnungen (Sound-ID -> Audiodatei) ------------------------------
    def assignment(self, sound_id: int) -> str:
        return self._values["assignments"].get(str(sound_id), "")

    def set_assignment(self, sound_id: int, path: str) -> None:
        key = str(sound_id)
        if path:
            self._values["assignments"][key] = path
        else:
            self._values["assignments"].pop(key, None)

    def clear_assignments(self) -> None:
        self._values["assignments"] = {}

    # -- Eigene Dialekttexte ----------------------------------------------
    def dialect_overrides(self, key: str) -> Dict[int, str]:
        """Die selbst geänderten Texte eines Dialekts."""
        roh = self._values["dialect_overrides"].get(key, {})
        ergebnis: Dict[int, str] = {}
        for k, v in roh.items():
            try:
                ergebnis[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
        return ergebnis

    def set_dialect_overrides(self, key: str, texte: Dict[int, str]) -> None:
        """Speichert Abweichungen vom mitgelieferten Text.

        Nur echte Änderungen werden abgelegt - so bleiben Verbesserungen an
        den mitgelieferten Texten bei einer neuen Programmfassung wirksam.
        """
        if texte:
            self._values["dialect_overrides"][key] = {
                str(i): t for i, t in sorted(texte.items())}
        else:
            self._values["dialect_overrides"].pop(key, None)

    # -- Datei ------------------------------------------------------------
    @classmethod
    def load(cls) -> "Config":
        path = config_file()
        if not path.exists():
            return cls()
        try:
            with path.open("r", encoding="utf-8") as fh:
                return cls(json.load(fh))
        except (OSError, ValueError) as exc:
            _LOG.warning("config.json unlesbar (%s), starte mit Standardwerten", exc)
            return cls()

    def save(self) -> None:
        path = config_file()
        tmp = path.with_suffix(".json.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self._values, fh, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except OSError as exc:
            _LOG.error("config.json konnte nicht gespeichert werden: %s", exc)
