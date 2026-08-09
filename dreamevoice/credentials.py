"""Geheimnisse im Windows-Anmeldeinformationsspeicher ablegen.

Bisher lagen Passwort und Zugangsschlüssel DPAPI-verschlüsselt in der
`config.json`. Sicher ist das schon - der Schlüssel hängt am
Windows-Benutzerkonto -, aber es hat zwei Nachteile: Die Geheimnisse
stecken in einer Datei, die man versehentlich mitkopiert, und man sieht
nirgends zentral, was die App eigentlich gespeichert hat.

Der Anmeldeinformationsspeicher von Windows löst beides. Er ist unter
"Systemsteuerung > Anmeldeinformationsverwaltung > Windows-Anmeldeinformationen"
einsehbar, dort lässt sich jeder Eintrag von Hand löschen, und die
config.json bleibt frei von Geheimnissen.

Angesprochen wird er über die Windows-API (advapi32). Ein Fremdpaket
braucht es dafür nicht.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Optional

_LOG = logging.getLogger(__name__)

# Die Einträge tauchen unter diesen Namen in Windows auf.
TARGET_DREAME = "DreameSprachpaket:Dreamehome"
TARGET_ELEVENLABS = "DreameSprachpaket:ElevenLabs"

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def available() -> bool:
    """True, wenn der Anmeldespeicher benutzt werden kann."""
    if sys.platform != "win32":
        return False
    try:
        ctypes.windll.advapi32
        return True
    except Exception:
        return False


def save(target: str, secret: str, username: str = "") -> bool:
    """Legt ein Geheimnis ab. Ein leeres Geheimnis löscht den Eintrag."""
    if not available():
        return False
    if not secret:
        return delete(target)

    daten = secret.encode("utf-16-le")
    puffer = ctypes.create_string_buffer(daten, len(daten))

    eintrag = _CREDENTIAL()
    eintrag.Flags = 0
    eintrag.Type = CRED_TYPE_GENERIC
    eintrag.TargetName = target
    eintrag.Comment = "Dreame Sprachpaket-Manager"
    eintrag.CredentialBlobSize = len(daten)
    eintrag.CredentialBlob = ctypes.cast(puffer, ctypes.POINTER(ctypes.c_byte))
    eintrag.Persist = CRED_PERSIST_LOCAL_MACHINE
    eintrag.AttributeCount = 0
    eintrag.Attributes = None
    eintrag.TargetAlias = None
    eintrag.UserName = username or "DreameSprachpaket"

    try:
        erfolg = ctypes.windll.advapi32.CredWriteW(ctypes.byref(eintrag), 0)
    except Exception as exc:
        _LOG.warning("Anmeldespeicher nicht beschreibbar: %s", exc)
        return False

    if not erfolg:
        _LOG.warning("CredWriteW fehlgeschlagen (Fehler %s)",
                     ctypes.GetLastError())
        return False
    return True


def load(target: str) -> Optional[str]:
    """Liest ein Geheimnis. None, wenn es keins gibt."""
    if not available():
        return None

    zeiger = ctypes.POINTER(_CREDENTIAL)()
    try:
        erfolg = ctypes.windll.advapi32.CredReadW(
            target, CRED_TYPE_GENERIC, 0, ctypes.byref(zeiger))
    except Exception as exc:
        _LOG.debug("Anmeldespeicher nicht lesbar: %s", exc)
        return None

    if not erfolg:
        return None

    try:
        eintrag = zeiger.contents
        laenge = int(eintrag.CredentialBlobSize)
        if laenge <= 0:
            return None
        roh = ctypes.string_at(eintrag.CredentialBlob, laenge)
        return roh.decode("utf-16-le")
    except Exception as exc:
        _LOG.warning("Eintrag unlesbar: %s", exc)
        return None
    finally:
        try:
            ctypes.windll.advapi32.CredFree(zeiger)
        except Exception:
            pass


def delete(target: str) -> bool:
    """Entfernt ein Geheimnis. True auch dann, wenn es keins gab."""
    if not available():
        return False
    try:
        ctypes.windll.advapi32.CredDeleteW(target, CRED_TYPE_GENERIC, 0)
        return True
    except Exception as exc:
        _LOG.debug("Eintrag nicht löschbar: %s", exc)
        return False


def exists(target: str) -> bool:
    return load(target) is not None


def describe(target: str) -> str:
    """Wo der Eintrag in Windows zu finden ist."""
    return (f"Systemsteuerung > Anmeldeinformationsverwaltung > "
            f"Windows-Anmeldeinformationen > „{target}“")
