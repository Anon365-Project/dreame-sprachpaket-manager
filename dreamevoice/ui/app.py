"""Das Hauptfenster mit den vier Tabs."""

from __future__ import annotations

import logging
import tkinter as tk
import traceback
import webbrowser
from tkinter import messagebox, ttk

from .. import (APP_NAME, AUTOR, HAFTUNG, LIZENZ, PROJEKT_URL, SPENDEN_URL,
                __version__, textfiles)
from ..paths import data_dir, log_file
from .state import AppState
from .tab_builder import BuilderTab
from .tab_connect import ConnectTab
from .tab_install import InstallTab
from .tab_store import StoreTab
from .theme import Theme
from .widgets import Card, show_error

_LOG = logging.getLogger(__name__)

# Bewusst klein gehalten: die Tabs scrollen bei Bedarf, deshalb muss das
# Fenster nicht gross genug für den ganzen Inhalt sein. Ein zu grosses
# Mindestmass macht die App auf kleinen Notebooks unbenutzbar.
WINDOW_MIN = (860, 560)


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.state_obj = AppState()
        self.title(f"{APP_NAME}  {__version__}")
        self.minsize(*WINDOW_MIN)
        self._center(1180, 800)

        self.theme = Theme(self, dark=bool(self.state_obj.config["dark_mode"]))
        self._build()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.report_callback_exception = self._on_unhandled

        self._ensure_dialect_files()

    # ------------------------------------------------------------------
    def _ensure_dialect_files(self) -> None:
        """Legt die Dialekt-Textdateien an, falls sie noch fehlen.

        Sie sollen einfach da sein, ohne dass man erst einen Knopf sucht.
        Vorhandene Dateien werden nicht angefasst - eine eigene
        Überarbeitung darf beim Start nicht verlorengehen.
        """
        try:
            neu = textfiles.ensure_files(self.state_obj.config.dialect_overrides)
        except OSError as exc:
            _LOG.warning("Dialekt-Textdateien nicht angelegt: %s", exc)
            return
        if neu:
            _LOG.info("%d Dialekt-Textdateien angelegt", len(neu))

    # ------------------------------------------------------------------
    def _center(self, width: int, height: int) -> None:
        """Setzt eine sinnvolle Startgrösse - passend zum Bildschirm."""
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # Auf grossen Bildschirmen bleibt es bei der Wunschgrösse, auf
        # kleinen wird so viel genommen, wie da ist.
        width = max(WINDOW_MIN[0], min(width, screen_w - 100))
        height = max(WINDOW_MIN[1], min(height, screen_h - 120))

        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.resizable(True, True)

        # Passt das Fenster ohnehin kaum auf den Bildschirm, startet es
        # gleich maximiert.
        if screen_h - 120 <= height or screen_w - 100 <= width:
            self._maximize()

    def _maximize(self) -> None:
        """Maximiert über den ganzen Bildschirm.

        Der Umweg über 'zoomed' ist nötig, weil ein blosses geometry() auf
        Bildschirmgrösse die Taskleiste überdeckt und das Fenster je nach
        Skalierung trotzdem nicht ausfüllt.
        """
        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)      # Linux-Fenstermanager
            except tk.TclError:
                self.geometry(f"{self.winfo_screenwidth()}x"
                              f"{self.winfo_screenheight()}+0+0")

    def _toggle_maximize(self) -> None:
        if self.state() == "zoomed":
            self.state("normal")
        else:
            self._maximize()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        header = ttk.Frame(self, style="TFrame")
        header.pack(fill="x", padx=20, pady=(16, 0))

        left = ttk.Frame(header, style="TFrame")
        left.pack(side="left")
        ttk.Label(left, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(left,
                  text=("Eigene Stimmen für Dreame-Saugroboter - entwickelt und "
                        "geprüft am X50 Ultra Complete"),
                  style="MutedBg.TLabel").pack(anchor="w", pady=(2, 0))

        right = ttk.Frame(header, style="TFrame")
        right.pack(side="right")
        self.var_dark = tk.BooleanVar(value=bool(self.state_obj.config["dark_mode"]))
        ttk.Checkbutton(right, text="Dunkles Design", style="Bg.TCheckbutton",
                        variable=self.var_dark,
                        command=self._toggle_theme).pack(side="left", padx=(0, 12))
        ttk.Button(right, text="Vollbild", style="Small.TButton",
                   command=self._toggle_maximize).pack(side="left", padx=(0, 8))
        ttk.Button(right, text="Hilfe", style="Small.TButton",
                   command=self._show_help).pack(side="left")
        ttk.Button(right, text="Über", style="Small.TButton",
                   command=self._show_about).pack(side="left", padx=(8, 0))

        self.bind("<F11>", lambda _e: self._toggle_maximize())

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(14, 0))

        self.tab_connect = ConnectTab(self.notebook, self.theme, self.state_obj)
        self.tab_builder = BuilderTab(self.notebook, self.theme, self.state_obj)
        self.tab_install = InstallTab(self.notebook, self.theme, self.state_obj)
        self.tab_store = StoreTab(self.notebook, self.theme, self.state_obj)

        self.notebook.add(self.tab_connect, text="1 · Verbindung")
        self.notebook.add(self.tab_builder, text="2 · Sprachpaket erstellen")
        self.notebook.add(self.tab_install, text="3 · Upload & Installation")
        self.notebook.add(self.tab_store, text="4 · Fertige Pakete")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        status = ttk.Frame(self, style="TFrame")
        status.pack(fill="x", padx=20, pady=(6, 12))
        ttk.Label(status, text=f"Einstellungen und Downloads: {data_dir()}",
                  style="MutedBg.TLabel").pack(side="left")

    # ------------------------------------------------------------------
    def _on_tab_changed(self, _event=None) -> None:
        current = self.notebook.index(self.notebook.select())
        if current == 1:
            self.tab_builder.refresh_rows()
            self.tab_builder.refresh_counter()
        elif current == 2:
            self.tab_install.refresh_summary()

    def _toggle_theme(self) -> None:
        messagebox.showinfo(
            "Design wechseln",
            "Das dunkle Design wird beim nächsten Start der App verwendet.\n\n"
            "Ein Wechsel im laufenden Betrieb würde alle Ansichten neu aufbauen "
            "und dabei ungespeicherte Eingaben verlieren.",
            parent=self)
        self.state_obj.config["dark_mode"] = self.var_dark.get()
        self.state_obj.save()

    # ------------------------------------------------------------------
    def _show_about(self) -> None:
        """Lizenz, Haftungsausschluss und - falls hinterlegt - die Links."""
        window = tk.Toplevel(self)
        window.title(f"Über {APP_NAME}")
        window.configure(bg=self.theme.color("bg"))
        window.geometry("640x560")
        window.transient(self)

        card = Card(window, self.theme, f"{APP_NAME} {__version__}",
                    f"von {AUTOR} · {LIZENZ}-Lizenz")
        card.pack(fill="both", expand=True, padx=16, pady=16)

        text = tk.Text(card.content, wrap="word", relief="flat", borderwidth=0,
                       background=self.theme.color("surface"),
                       foreground=self.theme.color("text"),
                       font=self.theme.font_body, padx=4, pady=4, height=16)
        scroll = ttk.Scrollbar(card.content, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="top", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.insert("1.0", HAFTUNG)
        text.configure(state="disabled")

        knoepfe = ttk.Frame(window, style="TFrame")
        knoepfe.pack(fill="x", padx=16, pady=(0, 16))

        if PROJEKT_URL:
            ttk.Button(knoepfe, text="Projektseite öffnen",
                       command=lambda: webbrowser.open(PROJEKT_URL)
                       ).pack(side="left")
        if SPENDEN_URL:
            ttk.Button(
                knoepfe, text="Trinkgeld dalassen (freiwillig)",
                command=lambda: webbrowser.open(SPENDEN_URL)
            ).pack(side="left", padx=(8, 0))
            ttk.Label(knoepfe,
                      text=("Freiwillig, ohne Gegenleistung - die App bleibt "
                            "für alle gleich."),
                      style="MutedBg.TLabel", wraplength=300,
                      justify="left").pack(side="left", padx=(10, 0))

        ttk.Button(knoepfe, text="Schließen", style="Accent.TButton",
                   command=window.destroy).pack(side="right")

    # ------------------------------------------------------------------
    def _show_help(self) -> None:
        window = tk.Toplevel(self)
        window.title("Hilfe und Sicherheitshinweise")
        window.configure(bg=self.theme.color("bg"))
        window.geometry("760x620")
        window.transient(self)

        card = Card(window, self.theme, "So funktioniert es")
        card.pack(fill="both", expand=True, padx=16, pady=16)

        text = tk.Text(card.content, wrap="word", relief="flat", borderwidth=0,
                       background=self.theme.color("surface"),
                       foreground=self.theme.color("text"),
                       font=self.theme.font_body, padx=4, pady=4)
        scroll = ttk.Scrollbar(card.content, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        text.insert("1.0", HELP_TEXT)
        text.configure(state="disabled")

        ttk.Button(window, text="Schließen", style="Accent.TButton",
                   command=window.destroy).pack(pady=(0, 16))

    # ------------------------------------------------------------------
    def _on_unhandled(self, art, wert, spur) -> None:
        """Zeigt Fehler, die sonst spurlos verschwinden würden.

        Tkinter fängt Ausnahmen aus Schaltflächen ab und schreibt sie
        bestenfalls auf die Konsole - bei einer Fensteranwendung sieht die
        niemand. Für den Benutzer sieht es dann so aus, als täte der Knopf
        einfach nichts. Deshalb landet hier alles Unerwartete sichtbar auf
        dem Bildschirm und zusätzlich im Protokoll.
        """
        text = "".join(traceback.format_exception(art, wert, spur))
        _LOG.error("Unbehandelter Fehler in der Oberfläche:\n%s", text)
        try:
            show_error(
                self, self.theme, "Unerwarteter Fehler",
                f"{art.__name__}: {wert}",
                "Das hätte nicht passieren dürfen. Die App läuft weiter, der "
                "Vorgang wurde aber abgebrochen.\n\n"
                "Technische Einzelheiten (mit 'Text kopieren' weitergeben):\n\n"
                + text)
        except Exception:      # pragma: no cover - Notnagel
            pass

    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        try:
            self.state_obj.save()
        except Exception:  # pragma: no cover
            _LOG.exception("Konfiguration konnte beim Beenden nicht gespeichert werden")
        self.destroy()


HELP_TEXT = """\
ABLAUF IN DREI SCHRITTEN

1. Verbindung
   Melde dich mit deinen Dreamehome-Zugangsdaten an und wähle deinen
   Roboter aus. Die App erfährt dadurch die genaue Modellkennung - die
   braucht sie, um das passende Originalpaket zu finden.

2. Sprachpaket erstellen
   Lade zuerst das offizielle Sprachpaket deines Roboters herunter. Es ist
   die Grundlage deines eigenen Pakets und liefert zugleich die
   Hörproben, damit du weißt, welche Nummer welche Ansage ist.
   Danach weist du einzelnen Ansagen eigene Audiodateien zu.

3. Upload & Installation
   Die App baut das Paket, startet kurz einen kleinen Webserver und
   schickt dem Roboter den Auftrag, es dort abzuholen.


WARUM DAS DEN ROBOTER NICHT BESCHÄDIGT

- Es wird keine Firmware angefasst. Sprachpakete zu wechseln ist eine
  ganz normale, vom Hersteller vorgesehene Funktion - die Dreamehome-App
  macht beim Sprachwechsel exakt dasselbe.

- Dein Paket ist eine Kopie des offiziellen Pakets. Nur die Ansagen, die
  du selbst zuweist, werden ersetzt. Alle Steuerdateien und alle übrigen
  Ansagen bleiben unverändert - der Roboter wird also nirgends stumm.

- Der Roboter prüft selbst. Zusammen mit der URL bekommt er Größe und
  MD5-Prüfsumme. Passt etwas nicht, verwirft er das Paket und behält
  seine bisherige Stimme.

- Es gibt einen Rückweg. Der Knopf "Originalstimme wiederherstellen"
  lässt den Roboter das offizielle Paket direkt bei Dreame laden.
  Genauso funktioniert der Sprachwechsel in der Handy-App.

- Eigene Kennung. Standardmäßig landet dein Paket unter der Kennung
  CUSTOM und überschreibt damit nicht die mitgelieferte deutsche Stimme.


DAS PAKET STEHT NICHT IN DER DREAMEHOME-APP

Das ist normal und kein Fehler. Die Dreamehome-App zeigt unter
"Sprachton" nur Sprachen aus Dreames eigenem Katalog. Eine selbst
vergebene Kennung wie CUSTOM oder BAYERN steht dort nicht drin - also
kann die App sie nicht anzeigen.

Meldet die App beim Öffnen, Roboter und App haetten verschiedene
Spracheinstellungen, ist das genau das Zeichen dafuer, dass dein Paket
laeuft: Der Roboter meldet eine Kennung, die die App nicht kennt.

Zwei Dinge dazu:

- Waehle in der Dreamehome-App keine Sprache aus, solange dein Paket
  laufen soll. Damit laedt der Roboter das offizielle Paket nach und
  ueberschreibt deines.
- Wer es doch in der Liste haben will, installiert unter der Kennung
  "DE". Dann erscheint es als "Deutsch" und ist auswaehlbar - dafuer
  ersetzt es die mitgelieferte deutsche Stimme. Zurueck geht es
  jederzeit ueber "Originalstimme wiederherstellen".

Ob dein Paket laeuft, verraet in Tab 3 der Knopf "Sprachpaket am
Roboter abfragen". Die Antwort kommt direkt vom Geraet.


WENN DER ROBOTER DAS PAKET NICHT ABHOLT

Das ist der häufigste Stolperstein. Der Roboter muss diesen PC im
Netzwerk erreichen können:

- Die Windows-Firewall muss eingehende Verbindungen erlauben. Beim ersten
  Start fragt Windows nach - dort "Privates Netzwerk" anhaken.
- PC und Roboter müssen im selben Netz hängen. Ein getrenntes IoT- oder
  Gast-WLAN verhindert die Verbindung.
- Ein aktives VPN auf dem PC leitet die Antwort ins Leere. Kurz trennen.
- Der Roboter darf nicht im Tiefschlaf sein - in der Dreamehome-App
  aufwecken.

Alternativ lädst du das gebaute Paket auf einen eigenen Webspace und
trägst dessen öffentliche Adresse im Feld "Eigene URL" ein.


DIALEKTPAKETE (TAB 4)

Sieben Dialekte, jeder mit allen 593 sprachlichen Ansagen: Bayerisch,
Hessisch, Schwäbisch, Sächsisch, Berlinerisch, Wienerisch und Kölsch.
Im Original bleiben nur Klänge ohne Sprache - Startton, Piepser,
Tierlaute. Fertig herunterladen kann man so etwas nirgends - es gibt
für keinen Saugroboter Dialektpakete.

Wer spricht, wählst du selbst:

- Windows-Sprachausgabe: offline und kostenlos. Der Dialekt steckt aber
  nur in den Worten, die Aussprache bleibt hochdeutsch. Männliche und
  weibliche Stimmen stehen zur Auswahl.
- ElevenLabs: echter Dialekt auch in der Aussprache, braucht ein eigenes
  kostenloses Konto. 10.000 Zeichen im Monat sind frei, ein Dialektpaket
  braucht rund 7.500.

Vor dem Erzeugen lohnt sich "Kostprobe anhören": drei Sätze mit der
gerade gewählten Stimme, damit du weisst, worauf du dich einlässt.

Läuft das ElevenLabs-Kontingent mitten in der Erzeugung leer, geht nichts
verloren. Das Gesprochene bleibt gespeichert, das Paket wird mit dem
fertigen Teil gebaut, und beim nächsten Versuch macht die App genau dort
weiter.


AUDIODATEIEN

Der Roboter versteht nur OGG Vorbis, mono, 16000 Hz. mp3- und wav-Dateien
werden beim Bauen automatisch umgewandelt - dafür muss ffmpeg vorhanden
sein (einfach ffmpeg.exe neben die App legen). Fertige .ogg-Dateien im
richtigen Format funktionieren auch ohne ffmpeg.

Halte die Ansagen kurz - die Originale sind meist zwei bis sechs Sekunden
lang.
"""


def run() -> None:
    """Startet die Anwendung."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file(), encoding="utf-8")],
    )
    _LOG.info("Start %s %s", APP_NAME, __version__)

    window = MainWindow()
    window.mainloop()
