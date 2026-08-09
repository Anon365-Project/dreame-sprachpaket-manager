"""Kurzlebiger Webserver, von dem der Roboter das Paket abholt.

Der Installationsbefehl enthält nur eine URL. Den Download macht der
Roboter selbst - er muss den PC also im Netzwerk erreichen können. Dieser
Server liefert genau eine Datei aus, nichts sonst, und läuft nur so
lange, wie die Installation dauert.
"""

from __future__ import annotations

import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .errors import InstallError

_LOG = logging.getLogger(__name__)

LogFn = Callable[[str], None]


def local_ip_for_internet() -> str:
    """Ermittelt die IP-Adresse, unter der der PC im LAN erreichbar ist.

    Es wird ein UDP-Socket "verbunden" (ohne dass Daten fliessen), damit
    das Betriebssystem die Schnittstelle wählt, über die es auch mit dem
    Router spricht. Das trifft bei mehreren Netzwerkkarten oder aktivem
    VPN deutlich zuverlässiger als ein Blick auf den Hostnamen.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(1.0)
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def candidate_ips() -> List[str]:
    """Alle plausiblen lokalen IPv4-Adressen, beste zuerst."""
    best = local_ip_for_internet()
    found = [best]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addr = info[4][0]
            if addr not in found and not addr.startswith("127."):
                found.append(addr)
    except OSError:
        pass
    return found


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


class _Handler(BaseHTTPRequestHandler):
    """Liefert ausschließlich die eine hinterlegte Datei aus."""

    server_version = "DreameVoiceHost/1.0"
    file_path: Path = Path()
    url_name: str = ""
    on_hit: Optional[Callable[[str, str], None]] = None

    def _serve(self, head_only: bool) -> None:
        requested = self.path.split("?", 1)[0].lstrip("/")
        client = self.client_address[0]

        if requested != self.url_name:
            self.send_error(404, "Not Found")
            if self.on_hit:
                self.on_hit(client, f"abgelehnt: /{requested}")
            return

        try:
            size = self.file_path.stat().st_size
        except OSError:
            self.send_error(500, "File unavailable")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/gzip")
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "none")
        self.end_headers()

        if self.on_hit:
            self.on_hit(client, "HEAD" if head_only else "GET")

        if head_only:
            return

        try:
            with self.file_path.open("rb") as fh:
                while True:
                    block = fh.read(1 << 16)
                    if not block:
                        break
                    self.wfile.write(block)
        except (OSError, ConnectionError) as exc:
            _LOG.warning("Auslieferung an %s abgebrochen: %s", client, exc)

    def do_GET(self) -> None:  # noqa: N802 - von BaseHTTPRequestHandler vorgegeben
        self._serve(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._serve(head_only=True)

    def log_message(self, fmt: str, *args) -> None:
        _LOG.debug("HTTP %s - %s", self.client_address[0], fmt % args)


class PackServer:
    """Startet und stoppt den Auslieferungsserver.

    Als Kontextmanager verwendbar, damit der Port auch bei einem Fehler
    wieder freigegeben wird.
    """

    def __init__(self, file_path: Path, port: int = 0,
                 host_ip: str = "", log: Optional[LogFn] = None) -> None:
        self.file_path = Path(file_path)
        if not self.file_path.is_file():
            raise InstallError(f"Die Paketdatei fehlt:\n{self.file_path}")

        self.port = port or free_port()
        self.host_ip = host_ip or local_ip_for_internet()
        self.url_name = self.file_path.name
        self._log = log or (lambda _: None)
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.hits: List[Tuple[str, str]] = []
        self._hit_event = threading.Event()

    # -- Steuerung ---------------------------------------------------------

    @property
    def url(self) -> str:
        return f"http://{self.host_ip}:{self.port}/{self.url_name}"

    def _record_hit(self, client: str, what: str) -> None:
        self.hits.append((client, what))
        self._log(f"Roboter ({client}) holt das Paket ab [{what}]")
        if what in ("GET", "HEAD"):
            self._hit_event.set()

    def start(self) -> str:
        handler = type("_BoundHandler", (_Handler,), {
            "file_path": self.file_path,
            "url_name": self.url_name,
            "on_hit": staticmethod(self._record_hit),
        })

        try:
            self._server = ThreadingHTTPServer(("0.0.0.0", self.port), handler)
        except OSError as exc:
            raise InstallError(
                f"Der Webserver konnte auf Port {self.port} nicht starten.",
                "Vermutlich ist der Port belegt. Wähle in den Einstellungen "
                f"einen anderen Port. Technische Details: {exc}",
            ) from exc

        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={"poll_interval": 0.2},
                                        daemon=True)
        self._thread.start()
        self._log(f"Webserver läuft auf {self.url}")
        return self.url

    def wait_for_download(self, timeout: float) -> bool:
        """Wartet, bis der Roboter die Datei angefordert hat."""
        return self._hit_event.wait(timeout)

    @property
    def was_downloaded(self) -> bool:
        return self._hit_event.is_set()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._log("Webserver beendet.")

    def __enter__(self) -> "PackServer":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()


def reachability_hint(port: int) -> str:
    """Hinweistext, wenn der Roboter den PC nicht erreicht."""
    return (
        "Der Roboter hat das Paket nicht abgeholt. Die häufigsten Gründe:\n\n"
        f"1. Die Windows-Firewall blockiert eingehende Verbindungen auf Port {port}. "
        "Beim ersten Start fragt Windows nach - dort muss 'Privates Netzwerk' "
        "erlaubt sein.\n"
        "2. PC und Roboter hängen in verschiedenen Netzen (z. B. Gast-WLAN, "
        "getrenntes IoT-WLAN, oder der PC ist per VPN verbunden).\n"
        "3. Der Roboter ist im Standby. Wecke ihn in der Dreamehome-App auf.\n\n"
        "Alternative: lade das Paket auf einen eigenen Webspace und trage die "
        "öffentliche URL im Feld 'Eigene URL' ein."
    )
