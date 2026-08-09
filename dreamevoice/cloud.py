"""Client für die Dreamehome-Cloud (dreamehome / MOVA Home / Trouver).

Warum Cloud und nicht python-miio?
----------------------------------
Aeltere Dreame-Modelle liefen über Xiaomi Mi Home. Dort gab es pro Gerät
eine lokale IP und ein 32-stelliges miio-Token, mit dem man das Gerät
direkt im LAN ansprechen konnte (python-miio, Klasse Device).

Modelle, die in der Dreamehome-App registriert sind - dazu gehört der
X50 Ultra Complete - verwenden dieses Verfahren nicht mehr. Sie stellen im
LAN keinen miio-Dienst bereit, und die Cloud gibt weder `localip` noch ein
lokales Token heraus. Die Referenz-Implementierung (Home-Assistant-
Integration `dreame-vacuum`) baut deshalb für Dreamehome-Konten gar keine
lokale Verbindung mehr auf, sondern schickt jeden Befehl über die Cloud.

Diese Datei bildet genau diesen Weg nach: anmelden, Geräte auflisten,
MIoT-Befehle als `set_properties` / `get_properties` über die Cloud
schicken. Der Roboter lädt das Sprachpaket anschließend selbst per HTTP
von der angegebenen URL - die kann durchaus im eigenen LAN liegen.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from .errors import LoginError, NetworkError

_LOG = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Protokollkonstanten der Dreamehome-App.
# Ermittelt aus der Home-Assistant-Integration Tasshack/dreame-vacuum
# (custom_components/dreame_vacuum/dreame/protocol.py, Branch dev).
# --------------------------------------------------------------------------

API_PORT = 13267
API_HOST_SUFFIX = {
    "dreame": ".iot.dreame.tech",
    "mova": ".iot.mova-tech.com",
    "trouver": ".iot.trouver-tech.com",
}
USER_AGENT = {
    "dreame": "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)",
    "mova": "Mova_Smarthome/1.2.4 (iPhone; iOS 18.4.1; Scale/3.00)",
    "trouver": "Trouver_Smarthome/1.0.9 (iPhone; iOS 18.4.1; Scale/3.00)",
}
TENANT_ID = {"dreame": "000000", "mova": "000002", "trouver": "000005"}

PASSWORD_SALT = "RAylYC%fmSKp7%Tq"
BASIC_AUTH = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
RLC_HEADER_CN = "1c80b3787b2266776bcdc481f37d8fa42ba10a30af81a6df-1"

PATH_LOGIN = "/dreame-auth/oauth/token"
PATH_DEVICE_LIST = "dreame-user-iot/iotuserbind/device/listV2"
PATH_DEVICE_INFO = "dreame-user-iot/iotuserbind/device/info"
PATH_OTC_INFO = "dreame-user-iot/iotstatus/devOTCInfo"
PATH_SEND_COMMAND = "device/sendCommand"

# Regionen, die die Dreamehome-App anbietet. "eu" ist für Deutschland
# richtig - "de" gibt es nur bei Mi-Home-Konten.
REGIONS = ["eu", "us", "sg", "ru", "kr", "cn"]
REGION_LABELS = {
    "eu": "Europa (Deutschland, Österreich, Schweiz)",
    "us": "Nord-/Südamerika",
    "sg": "Asien-Pazifik",
    "ru": "Russland",
    "kr": "Korea",
    "cn": "China (Festland)",
}

# MIoT-Adressen des Sprachpaket-Dienstes (Service 7).
SIID_VOICE = 7
PIID_VOICE_PACKET_ID = 2     # aktuell aktive Sprachpaket-Kennung, z. B. "DE"
PIID_VOICE_CHANGE_STATUS = 3  # Fortschritt/Zustand der Installation
PIID_VOICE_CHANGE = 4         # hierhin wird der Installationsauftrag geschrieben


class Device:
    """Ein Roboter aus dem Dreamehome-Konto."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.raw = raw
        self.did: str = str(raw.get("did", ""))
        self.model: str = raw.get("model", "")
        self.mac: str = raw.get("mac", "")
        self.bind_domain: str = raw.get("bindDomain", "") or ""
        self.master_uid: str = str(raw.get("masterUid", "") or "")
        info = raw.get("deviceInfo") or {}
        self.name: str = (raw.get("customName")
                          or info.get("displayName")
                          or self.model
                          or "Unbenannter Roboter")
        self.online: Optional[bool] = raw.get("online")

    @property
    def is_vacuum(self) -> bool:
        return ".vacuum." in self.model

    def __repr__(self) -> str:  # pragma: no cover - Debughilfe
        return f"<Device {self.name} {self.model} did={self.did}>"


class DreameCloud:
    """Minimaler, synchroner Client für die Dreamehome-Cloud."""

    def __init__(self, account_type: str = "dreame") -> None:
        if account_type not in API_HOST_SUFFIX:
            account_type = "dreame"
        self.account_type = account_type
        self.region = "eu"
        self.session = requests.Session()
        self.access_token: str = ""
        self.refresh_token: str = ""
        self.uid: str = ""
        self.tenant_id: str = TENANT_ID[account_type]
        self._expires_at: float = 0.0
        self._email = ""
        self._password = ""
        self._msg_id = random.randint(1, 100)

    # -- URLs und Header ---------------------------------------------------

    def _base_url(self, region: Optional[str] = None) -> str:
        r = region or self.region
        return f"https://{r}{API_HOST_SUFFIX[self.account_type]}:{API_PORT}"

    def _headers(self, json_body: bool) -> Dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "de-DE;q=0.9,en-US;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": USER_AGENT[self.account_type],
            "Authorization": BASIC_AUTH,
            "Tenant-Id": self.tenant_id,
            "Content-Type": "application/json" if json_body
                            else "application/x-www-form-urlencoded",
        }
        if self.access_token:
            headers["Dreame-Auth"] = self.access_token
        if self.region == "cn":
            headers["Dreame-Rlc"] = RLC_HEADER_CN
        return headers

    # -- Anmeldung ---------------------------------------------------------

    @staticmethod
    def hash_password(password: str) -> str:
        """Dreame hängt ein festes Salz an und schickt den MD5-Hex-Wert."""
        return hashlib.md5((password + PASSWORD_SALT).encode("utf-8")).hexdigest()

    def login(self, email: str, password: str, region: str) -> None:
        """Meldet an. Wirft LoginError/NetworkError mit Klartextmeldung."""
        email = (email or "").strip()
        if not email or not password:
            raise LoginError("E-Mail und Passwort dürfen nicht leer sein.")
        if region not in REGIONS:
            region = "eu"

        self.region = region
        self._email, self._password = email, password

        body = (
            "platform=IOS&scope=all&grant_type=password"
            f"&username={quote(email, safe='@.-_+')}"
            f"&password={self.hash_password(password)}"
            "&type=account"
        )

        try:
            resp = self.session.post(
                self._base_url() + PATH_LOGIN,
                headers=self._headers(json_body=False),
                data=body,
                timeout=15,
            )
        except requests.exceptions.SSLError as exc:
            raise NetworkError(
                "Die gesicherte Verbindung zum Dreame-Server kam nicht zustande.",
                "Prüfe, ob eine Firewall, ein VPN oder ein Virenscanner mit "
                "HTTPS-Scan dazwischenfunkt.",
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise NetworkError(
                "Der Dreame-Server hat nicht rechtzeitig geantwortet.",
                "Prüfe deine Internetverbindung und versuche es erneut.",
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise NetworkError(
                "Der Dreame-Server ist nicht erreichbar.",
                f"Technische Details: {exc}",
            ) from exc

        self._apply_login_response(resp)

    def _apply_login_response(self, resp: requests.Response) -> None:
        if resp.status_code != 200:
            detail = ""
            try:
                data = resp.json()
                detail = str(data.get("error_description") or data.get("error") or "")
            except ValueError:
                detail = (resp.text or "")[:200]

            low = detail.lower()
            if resp.status_code in (400, 401) and ("bad credentials" in low
                                                   or "password" in low
                                                   or "user" in low
                                                   or not detail):
                raise LoginError(
                    "E-Mail oder Passwort wurde nicht akzeptiert.",
                    "Prüfe die Zugangsdaten in der Dreamehome-App. Achte auch "
                    "auf die richtige Region: Konten aus Deutschland liegen "
                    "fast immer auf 'Europa'.",
                )
            raise LoginError(
                f"Die Anmeldung wurde abgelehnt (HTTP {resp.status_code}).",
                detail or "Keine nähere Begründung vom Server.",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise LoginError("Die Antwort des Servers war unlesbar.") from exc

        token = data.get("access_token")
        if not token:
            raise LoginError(
                "Der Server hat kein Zugriffstoken geliefert.",
                f"Antwort: {json.dumps(data)[:300]}",
            )

        self.access_token = token
        self.refresh_token = data.get("refresh_token", "")
        self.uid = str(data.get("uid", "") or "")
        self.tenant_id = str(data.get("tenant_id", self.tenant_id) or self.tenant_id)
        self._expires_at = time.time() + float(data.get("expires_in", 3600)) - 120

        server_region = data.get("region")
        if server_region and server_region != self.region:
            _LOG.info("Server meldet Region %r statt %r", server_region, self.region)

    def login_autodetect(self, email: str, password: str, preferred: str = "eu") -> str:
        """Probiert Regionen durch und gibt die erfolgreiche zurück."""
        order = [preferred] + [r for r in REGIONS if r != preferred]
        last: Exception | None = None
        for region in order:
            try:
                self.login(email, password, region)
                return region
            except LoginError as exc:
                last = exc
            except NetworkError as exc:
                last = exc
        if isinstance(last, Exception):
            raise last
        raise LoginError("Anmeldung in keiner Region erfolgreich.")

    def _ensure_token(self) -> None:
        if self.access_token and time.time() < self._expires_at:
            return
        if self._email and self._password:
            self.login(self._email, self._password, self.region)
        elif not self.access_token:
            raise LoginError("Nicht angemeldet.")

    @property
    def logged_in(self) -> bool:
        return bool(self.access_token)

    # -- Allgemeiner API-Aufruf -------------------------------------------

    def _api(self, path: str, params: Optional[Dict[str, Any]] = None,
             timeout: int = 15, retries: int = 2) -> Dict[str, Any]:
        self._ensure_token()
        url = f"{self._base_url()}/{path.lstrip('/')}"
        body = json.dumps(params, separators=(",", ":")) if params is not None else None

        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self.session.post(url, headers=self._headers(json_body=True),
                                         data=body, timeout=timeout)
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                continue

            if resp.status_code == 401 and attempt < retries:
                self.access_token = ""
                self._ensure_token()
                continue
            if resp.status_code != 200:
                raise NetworkError(
                    f"Der Dreame-Server antwortete mit HTTP {resp.status_code}.",
                    (resp.text or "")[:300],
                )
            try:
                return resp.json()
            except ValueError as exc:
                last_exc = exc

        raise NetworkError(
            "Die Anfrage an den Dreame-Server ist fehlgeschlagen.",
            f"Technische Details: {last_exc}",
        )

    # -- Geräte -----------------------------------------------------------

    def list_devices(self, only_vacuums: bool = True) -> List[Device]:
        data = self._api(PATH_DEVICE_LIST)
        if data.get("code") != 0 or "data" not in data:
            raise NetworkError(
                "Die Geräteliste konnte nicht geladen werden.",
                f"Antwort des Servers: {json.dumps(data)[:300]}",
            )
        records = (((data.get("data") or {}).get("page") or {}).get("records")) or []
        devices = [Device(r) for r in records]
        return [d for d in devices if d.is_vacuum] if only_vacuums else devices

    def device_info(self, did: str) -> Dict[str, Any]:
        data = self._api(PATH_DEVICE_INFO, {"did": str(did)})
        if data.get("code") != 0:
            raise NetworkError("Die Gerätedaten konnten nicht geladen werden.")
        return data.get("data") or {}

    # -- MIoT-Befehle ------------------------------------------------------

    def _command_path(self, bind_domain: str) -> str:
        """sendCommand läuft über einen regionalen Unterdienst."""
        prefix = ""
        if bind_domain:
            host = bind_domain.split(":")[0]
            first = host.split(".")[0]
            if first:
                prefix = f"-{first}"
        return f"dreame-iot-com{prefix}/{PATH_SEND_COMMAND}"

    def send(self, device: Device, method: str, params: Any,
             timeout: int = 20) -> Any:
        """Schickt einen MIoT-Aufruf an den Roboter und gibt `result` zurück."""
        self._msg_id += 1
        payload = {
            "did": device.did,
            "id": self._msg_id,
            "data": {"did": device.did, "id": self._msg_id,
                     "method": method, "params": params},
        }
        data = self._api(self._command_path(device.bind_domain), payload, timeout=timeout)
        inner = data.get("data")
        if not inner or "result" not in inner:
            raise NetworkError(
                "Der Roboter hat auf den Befehl nicht geantwortet.",
                "Er ist vermutlich offline oder im Standby. Wecke ihn in der "
                "Dreamehome-App auf und versuche es erneut.",
            )
        return inner["result"]

    def get_property(self, device: Device, siid: int, piid: int) -> Any:
        result = self.send(device, "get_properties",
                           [{"did": device.did, "siid": siid, "piid": piid}])
        if isinstance(result, list) and result:
            return result[0].get("value")
        return None

    def set_property(self, device: Device, siid: int, piid: int, value: Any) -> Any:
        return self.send(device, "set_properties",
                         [{"did": device.did, "siid": siid, "piid": piid, "value": value}])

    # -- Sprachpaket -------------------------------------------------------

    def current_voice_pack(self, device: Device) -> Optional[str]:
        """Kennung des aktuell aktiven Sprachpakets, z. B. "DE"."""
        try:
            return self.get_property(device, SIID_VOICE, PIID_VOICE_PACKET_ID)
        except (NetworkError, LoginError):
            return None

    def voice_change_status(self, device: Device) -> Any:
        try:
            return self.get_property(device, SIID_VOICE, PIID_VOICE_CHANGE_STATUS)
        except (NetworkError, LoginError):
            return None

    def supports_voice_service(self, device: Device) -> bool:
        """Hat dieser Roboter den Sprachpaket-Dienst an der erwarteten Stelle?

        Die Nummern siid 7 / piid 2-4 sind bei allen geprüften Dreame- und
        MOVA-Saugrobotern gleich, aber nicht bei jedem Gerät des Herstellers
        (Mähroboter, ältere Mi-Home-Modelle). Bevor die App etwas schreibt,
        liest sie deshalb die Kennung des aktiven Pakets. Antwortet das
        Gerät darauf nicht, wird gar nichts gesendet - lieber keine neue
        Stimme als ein Schreibzugriff auf eine unbekannte Eigenschaft.
        """
        try:
            wert = self.get_property(device, SIID_VOICE, PIID_VOICE_PACKET_ID)
        except (NetworkError, LoginError) as exc:
            _LOG.warning("Sprachdienst nicht abfragbar: %s", exc)
            return False
        # Erwartet wird eine Sprachkennung wie "DE", "EN", "CUSTOM".
        return isinstance(wert, str) and 1 <= len(wert.strip()) <= 16

    def install_voice_pack(self, device: Device, lang_id: str, url: str,
                           md5: str, size: int) -> Any:
        """Weist den Roboter an, ein Sprachpaket von `url` zu laden.

        Der Roboter prüft die Datei selbst gegen `md5` und `size` und
        verwirft sie bei Abweichung - deshalb müssen beide Werte exakt zum
        Archiv passen.
        """
        payload = json.dumps(
            {"id": lang_id, "url": url, "md5": md5, "size": int(size)},
            separators=(",", ":"),
        )
        _LOG.info("Installationsauftrag: %s", payload)
        return self.set_property(device, SIID_VOICE, PIID_VOICE_CHANGE, payload)
