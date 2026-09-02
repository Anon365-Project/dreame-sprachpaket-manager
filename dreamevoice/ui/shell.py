"""Seitenleiste statt Reiter.

Vier Reiter waren zu wenig Struktur für das, was die App inzwischen kann,
und gleichzeitig zu viel Weg für das, was die meisten wollen: eine andere
Stimme auf dem Roboter. Wer das wollte, musste durch Tab 1 (anmelden),
Tab 2 (Originalpaket), Tab 4 (Dialekt) und Tab 3 (installieren) - und die
Reihenfolge stand nirgends.

Die Seitenleiste ordnet nicht mehr nach Ablauf, sondern nach Häufigkeit:
oben, was man ständig tut, darunter das Seltene. Sie steht dabei still -
was sich ändert, ist nur der Inhalt rechts. So verliert man die
Orientierung nicht, auch wenn eine Seite ganz anders aussieht als die
vorige.

Einträge lassen sich sperren (`set_enabled`) und mit einem Statuspunkt
versehen (`set_dot`). Beides zusammen macht ohne ein Wort klar, was gerade
geht und was nicht: Ohne Anmeldung ist fast alles grau, und der Punkt an
"Verbindung" sagt, woran es liegt.
"""

from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from .theme import Theme

_LOG = logging.getLogger(__name__)

RAIL_WIDTH = 208

#: Farbschlüssel des Themes für die Statuspunkte.
PUNKT_FARBEN = {
    "ok": "success",
    "warn": "warning",
    "fehler": "danger",
    "aus": "",
}


@dataclass
class Eintrag:
    """Ein Punkt in der Seitenleiste."""

    key: str
    label: str
    icon: str
    #: Die fertige Seite - oder None, solange sie noch nicht gebaut
    #: wurde. Vier der sechs Seiten sieht ein Benutzer nie an; sie
    #: beim Start mitzubauen kostete über eine Sekunde.
    seite: Optional[ttk.Frame] = None
    #: Baut die Seite auf Zuruf. Genau einmal.
    bauen: Optional[Callable[[], ttk.Frame]] = None
    section: str = ""
    enabled: bool = True
    grund: str = ""
    dot: str = "aus"
    zeile: Optional[tk.Frame] = None
    beschriftung: Optional[tk.Label] = None
    punkt: Optional[tk.Canvas] = None
    beim_zeigen: Optional[Callable[[], None]] = None


class NavShell(ttk.Frame):
    """Container mit Seitenleiste links und genau einer sichtbaren Seite."""

    def __init__(self, master, theme: Theme) -> None:
        super().__init__(master, style="TFrame")
        self.theme = theme
        self._eintraege: Dict[str, Eintrag] = {}
        self._reihenfolge: List[str] = []
        self._aktuell: str = ""
        self._abschnitte: Dict[str, tk.Label] = {}

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.rail = tk.Frame(self, bg=self.theme.color("surface_alt"),
                             width=RAIL_WIDTH)
        self.rail.grid(row=0, column=0, sticky="ns")
        self.rail.grid_propagate(False)

        trenner = tk.Frame(self, bg=self.theme.color("border"), width=1)
        trenner.grid(row=0, column=0, sticky="nse")

        self.buehne = ttk.Frame(self, style="TFrame")
        self.buehne.grid(row=0, column=1, sticky="nsew")
        self.buehne.columnconfigure(0, weight=1)
        self.buehne.rowconfigure(0, weight=1)

    # ------------------------------------------------------------------
    def add(self, key: str, label: str, icon: str,
            seite: Optional[ttk.Frame] = None,
            section: str = "",
            beim_zeigen: Optional[Callable[[], None]] = None,
            bauen: Optional[Callable[[], ttk.Frame]] = None) -> None:
        """Nimmt eine Seite auf - fertig gebaut oder als Bauplan.

        Mit `bauen` entsteht die Seite erst, wenn sie zum ersten Mal
        angezeigt wird. Beim Start werden sonst alle sechs Seiten
        gebaut - gemessen über tausend Bedienelemente, von denen
        die meisten nie jemand zu Gesicht bekommt.
        """
        if key in self._eintraege:
            raise ValueError(f"Der Eintrag '{key}' ist schon vergeben.")
        if seite is None and bauen is None:
            raise ValueError("Es braucht eine Seite oder einen Bauplan.")

        if seite is not None:
            seite.grid(row=0, column=0, sticky="nsew", in_=self.buehne)
            seite.grid_remove()

        eintrag = Eintrag(key=key, label=label, icon=icon, seite=seite,
                          bauen=bauen, section=section,
                          beim_zeigen=beim_zeigen)
        self._eintraege[key] = eintrag
        self._reihenfolge.append(key)
        self._zeile_bauen(eintrag)

    def seite(self, key: str) -> Optional[ttk.Frame]:
        """Die Seite zu einem Eintrag - baut sie, falls nötig."""
        eintrag = self._eintraege.get(key)
        if eintrag is None:
            return None
        if eintrag.seite is None and eintrag.bauen is not None:
            eintrag.seite = eintrag.bauen()
            eintrag.seite.grid(row=0, column=0, sticky="nsew",
                               in_=self.buehne)
            eintrag.seite.grid_remove()
        return eintrag.seite

    def _zeile_bauen(self, eintrag: Eintrag) -> None:
        if eintrag.section and eintrag.section not in self._abschnitte:
            kopf = tk.Label(self.rail, text=eintrag.section.upper(),
                            bg=self.theme.color("surface_alt"),
                            fg=self.theme.color("muted"),
                            font=self.theme.font_small, anchor="w")
            kopf.pack(fill="x", padx=16, pady=(14, 4))
            self._abschnitte[eintrag.section] = kopf

        zeile = tk.Frame(self.rail, bg=self.theme.color("surface_alt"),
                         cursor="hand2")
        zeile.pack(fill="x")

        # Der farbige Balken links markiert die aktive Seite. Er ist immer
        # da, nur meistens in der Hintergrundfarbe - sonst würde die
        # Beschriftung beim Wechseln um drei Pixel springen.
        balken = tk.Frame(zeile, bg=self.theme.color("surface_alt"), width=3)
        balken.pack(side="left", fill="y")

        beschriftung = tk.Label(
            zeile, text=f"{eintrag.icon}  {eintrag.label}",
            bg=self.theme.color("surface_alt"),
            fg=self.theme.color("text"),
            font=self.theme.font_body, anchor="w", padx=13, pady=7)
        beschriftung.pack(side="left", fill="x", expand=True)

        punkt = tk.Canvas(zeile, width=14, height=14, highlightthickness=0,
                          bg=self.theme.color("surface_alt"))
        punkt.pack(side="right", padx=(0, 12))

        eintrag.zeile = zeile
        eintrag.beschriftung = beschriftung
        eintrag.punkt = punkt
        eintrag._balken = balken           # type: ignore[attr-defined]

        for widget in (zeile, beschriftung, punkt):
            widget.bind("<Button-1>", lambda _e, k=eintrag.key: self._geklickt(k))
            widget.bind("<Enter>", lambda _e, k=eintrag.key: self._hover(k, True))
            widget.bind("<Leave>", lambda _e, k=eintrag.key: self._hover(k, False))

        self._zeile_faerben(eintrag)

    # ------------------------------------------------------------------
    def _geklickt(self, key: str) -> None:
        eintrag = self._eintraege.get(key)
        if eintrag is None:
            return
        if not eintrag.enabled:
            # Nicht stumm schlucken: Wer auf einen grauen Punkt klickt,
            # will wissen, warum er grau ist.
            if eintrag.grund:
                from .widgets import show_info
                show_info(self, self.theme, f"{eintrag.label} geht noch nicht",
                          eintrag.grund)
            return
        self.show(key)

    def _hover(self, key: str, drin: bool) -> None:
        eintrag = self._eintraege.get(key)
        if eintrag is None or key == self._aktuell or not eintrag.enabled:
            return
        farbe = self.theme.color("selection") if drin \
            else self.theme.color("surface_alt")
        self._flaeche_setzen(eintrag, farbe)

    def _flaeche_setzen(self, eintrag: Eintrag, farbe: str) -> None:
        for widget in (eintrag.zeile, eintrag.beschriftung, eintrag.punkt):
            if widget is not None:
                widget.configure(bg=farbe)

    def _zeile_faerben(self, eintrag: Eintrag) -> None:
        aktiv = eintrag.key == self._aktuell
        flaeche = self.theme.color("surface") if aktiv \
            else self.theme.color("surface_alt")
        self._flaeche_setzen(eintrag, flaeche)

        if not eintrag.enabled:
            schrift = self.theme.color("muted")
        elif aktiv:
            schrift = self.theme.color("text")
        else:
            schrift = self.theme.color("text")
        if eintrag.beschriftung is not None:
            eintrag.beschriftung.configure(
                fg=schrift,
                font=self.theme.font_bold if aktiv else self.theme.font_body)

        balken = getattr(eintrag, "_balken", None)
        if balken is not None:
            balken.configure(bg=self.theme.color("accent") if aktiv else flaeche)

        self._punkt_zeichnen(eintrag, flaeche)

    def _punkt_zeichnen(self, eintrag: Eintrag, flaeche: str) -> None:
        if eintrag.punkt is None:
            return
        eintrag.punkt.delete("all")
        schluessel = PUNKT_FARBEN.get(eintrag.dot, "")
        if not schluessel:
            return
        eintrag.punkt.create_oval(4, 4, 11, 11,
                                  fill=self.theme.color(schluessel),
                                  outline="")

    # ------------------------------------------------------------------
    def show(self, key: str) -> None:
        """Blendet eine Seite ein und die bisherige aus."""
        eintrag = self._eintraege.get(key)
        if eintrag is None:
            _LOG.warning("Unbekannte Seite: %s", key)
            return

        seite = self.seite(key)
        if seite is None:
            _LOG.warning("Seite %r ließ sich nicht bauen", key)
            return

        vorher = self._eintraege.get(self._aktuell)
        if (vorher is not None and vorher.key != key
                and vorher.seite is not None):
            vorher.seite.grid_remove()

        self._aktuell = key
        seite.grid()

        for e in self._eintraege.values():
            self._zeile_faerben(e)

        if eintrag.beim_zeigen is not None:
            try:
                eintrag.beim_zeigen()
            except Exception:      # pragma: no cover - eine Seite darf nicht reißen
                _LOG.exception("Fehler beim Anzeigen von %r", key)

    @property
    def current(self) -> str:
        return self._aktuell

    # ------------------------------------------------------------------
    def set_enabled(self, key: str, enabled: bool, grund: str = "") -> None:
        """Sperrt oder entsperrt einen Eintrag.

        Ein gesperrter Eintrag bleibt sichtbar - er soll ja verraten, dass
        es ihn gibt. Wer darauf klickt, bekommt `grund` zu lesen.
        """
        eintrag = self._eintraege.get(key)
        if eintrag is None:
            return
        eintrag.enabled = enabled
        eintrag.grund = grund
        if not enabled and self._aktuell == key:
            # Nicht auf einer Seite stehen bleiben, die gerade zugeht.
            ersatz = next((k for k in self._reihenfolge
                           if self._eintraege[k].enabled), "")
            if ersatz:
                self.show(ersatz)
                return
        self._zeile_faerben(eintrag)

    def set_dot(self, key: str, art: str) -> None:
        """Setzt den Statuspunkt: 'ok', 'warn', 'fehler' oder 'aus'."""
        eintrag = self._eintraege.get(key)
        if eintrag is None:
            return
        eintrag.dot = art if art in PUNKT_FARBEN else "aus"
        self._zeile_faerben(eintrag)

    def page(self, key: str) -> Optional[ttk.Frame]:
        eintrag = self._eintraege.get(key)
        return eintrag.seite if eintrag else None

    def keys(self) -> List[str]:
        return list(self._reihenfolge)
