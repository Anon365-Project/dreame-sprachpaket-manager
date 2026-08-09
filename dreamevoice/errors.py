"""Fehlertypen mit Klartext-Meldungen für die Oberfläche.

Jede Ausnahme trägt eine deutschsprachige Meldung, die direkt angezeigt
werden kann, und optional einen Hinweis, was der Nutzer tun soll.
"""


class DreameError(Exception):
    """Basis aller App-Fehler. `hint` erklärt den nächsten Schritt."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        return self.message if not self.hint else f"{self.message}\n\n{self.hint}"


class LoginError(DreameError):
    """Anmeldung an der Dreame-Cloud fehlgeschlagen."""


class NetworkError(DreameError):
    """Netzwerk- oder Serverproblem."""


class NoDeviceError(DreameError):
    """Kein passender Roboter im Konto gefunden."""


class PackError(DreameError):
    """Sprachpaket konnte nicht gebaut oder geprüft werden."""


class AudioError(DreameError):
    """Audiodatei ist ungeeignet oder konnte nicht konvertiert werden."""


class InstallError(DreameError):
    """Installation auf dem Roboter fehlgeschlagen."""
