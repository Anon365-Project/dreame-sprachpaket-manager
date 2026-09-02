"""Das Hauptfenster: Seitenleiste links, jeweils eine Seite rechts."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tkinter as tk
import traceback
import webbrowser
from tkinter import messagebox, ttk

from .. import (APP_NAME, AUTOR, HAFTUNG, LIZENZ, PROJEKT_URL, SPENDEN_URL,
                __version__, textfiles)
from .. import aktualisierung, anleitungen
from ..paths import data_dir, icon_file, log_file
from .page_start import StartPage
from .page_voice import VoicePage
from .shell import NavShell
from .state import AppState, run_async, spaeter
from .tab_builder import BuilderTab
from .tab_connect import ConnectTab
from .tab_install import InstallTab
from .tab_store import StoreTab
from .fenster_update import UpdateFenster
from .theme import Theme
from .widgets import Card, show_error, show_warning

_LOG = logging.getLogger(__name__)

# Bewusst klein gehalten: die Tabs scrollen bei Bedarf, deshalb muss das
# Fenster nicht groß genug für den ganzen Inhalt sein. Ein zu großes
# Mindestmaß macht die App auf kleinen Notebooks unbenutzbar.
WINDOW_MIN = (860, 560)


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.state_obj = AppState()
        self._symbol_setzen()
        self.title(f"{APP_NAME}  {__version__}")
        self.minsize(*WINDOW_MIN)
        self._center(1180, 800)

        self.theme = Theme(self, dark=bool(self.state_obj.config["dark_mode"]))
        self._build()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.report_callback_exception = self._on_unhandled

        self._ensure_dialect_files()

        # Jetzt steht das Fenster - erst hier gibt es ein äußeres
        # Fenster, dem sich ein Symbol anheften lässt.
        if sys.platform == "win32":
            self.update_idletasks()
            self._symbol_scharf(icon_file())

    # ------------------------------------------------------------------
    def _symbol_setzen(self) -> None:
        """Setzt das Symbol des Fensters und in der Taskleiste.

        `app.ico` ging bisher nur an PyInstaller - das ist das Symbol
        der DATEI im Explorer. Das Fenster selbst zeigte weiter Tks
        eingebaute Feder.

        Unter Windows genügt das Symbol allein nicht: Ohne eigene
        "AppUserModelID" ordnet die Taskleiste das Fenster dem
        Python-Interpreter zu und nimmt dessen Symbol. Der Aufruf muss
        vor dem ersten Fenster passieren.

        Schlägt irgendetwas davon fehl, bleibt es beim Bisherigen -
        ein Symbol ist es nicht wert, dass die App nicht startet.
        """
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "Anon365Project.DreameSprachpaketManager")
            except Exception:                          # noqa: BLE001
                _LOG.debug("AppUserModelID nicht gesetzt", exc_info=True)

        pfad = icon_file()
        if pfad is None:
            _LOG.debug("Keine app.ico gefunden - Fenstersymbol bleibt leer")
            return
        try:
            # default=True gilt auch für alle späteren Fenster - Hilfe,
            # Über, Aktualisierung tragen damit dasselbe Symbol.
            self.iconbitmap(default=str(pfad))
        except tk.TclError:
            _LOG.debug("Fenstersymbol ließ sich nicht setzen", exc_info=True)

        # Unter Windows reicht das nicht: Tk lädt aus der ICO-Datei im
        # Wesentlichen EINE Größe, und Windows rechnet daraus alles
        # andere hoch - in der Taskleiste sieht man das sofort. Deshalb
        # zusätzlich die Fassungen holen, die das System gerade
        # anfordert, und sie direkt ans Fenster hängen.
        # Das passgenaue Symbol wird erst am Ende von __init__ gesetzt:
        # Vorher existiert das äußere Fenster noch nicht, an dem der
        # Taskleisteneintrag hängt - ein "after(0, ...)" feuerte zu
        # früh, und WM_GETICON meldete danach weiterhin "keines".

    def _symbol_scharf(self, pfad) -> None:
        """Hängt passgenaue Symbolgrößen ans Fenster (nur Windows).

        Muss nach dem Erzeugen des Fensters laufen - vorher gibt es
        kein Fensterhandle, an das sich etwas hängen ließe.
        """
        if pfad is None:
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.SendMessageW.restype = ctypes.c_void_p

            # ACHTUNG: winfo_id() liefert bei Tk das INNERE Fenster
            # (Klasse "TkChild"). Der Eintrag in der Taskleiste und die
            # Titelleiste hängen aber am äußeren ("TkTopLevel").
            # Ein Symbol an das innere Fenster zu hängen, bewirkt gar
            # nichts - WM_GETICON meldete danach weiterhin "keines".
            innen = wintypes.HWND(self.winfo_id())
            aussen = user32.GetParent(innen)
            handle = wintypes.HWND(aussen) if aussen else innen
            #: SM_CXSMICON / SM_CXICON - beide sind DPI-abhängig, das
            #: System nennt also von sich aus die richtige Größe.
            klein = user32.GetSystemMetrics(49)
            gross = user32.GetSystemMetrics(11)

            IMAGE_ICON, LR_LOADFROMFILE = 1, 0x00000010
            WM_SETICON = 0x0080
            #: Die Symbole bleiben absichtlich am Objekt hängen: Gibt
            #: Python sie frei, zeigt Windows wieder das alte Bild.
            self._symbole = []
            for kante, welches in ((klein, 0), (gross, 1)):
                bild = user32.LoadImageW(None, str(pfad), IMAGE_ICON,
                                         kante, kante, LR_LOADFROMFILE)
                if not bild:
                    continue
                self._symbole.append(bild)
                user32.SendMessageW(handle, WM_SETICON, welches, bild)
        except Exception:                              # noqa: BLE001
            _LOG.debug("Passgenaues Fenstersymbol nicht gesetzt", exc_info=True)

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
        """Setzt eine sinnvolle Startgröße - passend zum Bildschirm."""
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # Auf großen Bildschirmen bleibt es bei der Wunschgröße, auf
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

        Der Umweg über 'zoomed' ist nötig, weil ein bloßes geometry() auf
        Bildschirmgröße die Taskleiste überdeckt und das Fenster je nach
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
        # Kein "Vollbild"-Knopf mehr: Er tat nichts anderes als das
        # Viereck in der Fensterleiste von Windows - zwischen "zoomed"
        # und "normal" umschalten. Ein Knopf, der einen vorhandenen
        # Systemknopf verdoppelt, kostet Platz und Aufmerksamkeit und
        # bringt nichts dazu. Über F11 geht es weiterhin.
        # Aktualisierung gehört neben Hilfe und Über: Sie betrifft die
        # App selbst. Früher lag sie auf der Seite "Verbindung", unter
        # Konto und Roboterliste - dort sucht sie niemand, und der
        # Schalter "beim Start nachsehen" war damit ebenso versteckt.
        ttk.Button(right, text="Aktualisierung", style="Small.TButton",
                   command=self._show_update).pack(side="left", padx=(0, 8))
        ttk.Button(right, text="Hilfe", style="Small.TButton",
                   command=self._show_help).pack(side="left")
        ttk.Button(right, text="Über", style="Small.TButton",
                   command=self._show_about).pack(side="left", padx=(8, 0))

        self.bind("<F11>", lambda _e: self._toggle_maximize())

        self.shell = NavShell(self, self.theme)
        self.shell.pack(fill="both", expand=True, padx=(0, 0), pady=(14, 0))

        buehne = self.shell.buehne
        # Die beiden Seiten, die jeder sieht, entstehen sofort. Die
        # vier unter "Erweitert" erst beim ersten Öffnen - sie machen
        # den Großteil der über tausend Bedienelemente aus, und die
        # meisten Benutzer sehen keine davon je an.
        self.page_start = StartPage(buehne, self.theme, self.state_obj,
                                    gehe_zu=self.shell.show)
        self.page_voice = VoicePage(buehne, self.theme, self.state_obj,
                                    gehe_zu=self.shell.show)

        # Oben, was man ständig tut - darunter, was selten vorkommt.
        # "Fertige Stimmen" fasst zusammen, was früher auf Tab 4 (aussuchen)
        # und Tab 3 (aufspielen) verteilt war - siehe page_voice.py.
        self.shell.add("start", "Start", "🏠", self.page_start,
                       beim_zeigen=self.page_start.refresh)
        self.shell.add("stimme", "Fertige Stimmen", "🔊", self.page_voice,
                       beim_zeigen=self.page_voice.refresh)
        self.shell.add("eigene", "Eigene Stimmen", "🎙",
                       bauen=lambda: StoreTab(buehne, self.theme,
                                              self.state_obj),
                       section="Erweitert", beim_zeigen=self._beim_eigene)
        self.shell.add("ansagen", "Einzelne Ansagen", "🧩",
                       bauen=lambda: BuilderTab(buehne, self.theme,
                                                self.state_obj),
                       section="Erweitert", beim_zeigen=self._beim_ansagen)
        self.shell.add("aufspielen", "Bauen und Aufspielen", "⬆",
                       bauen=lambda: InstallTab(buehne, self.theme,
                                                self.state_obj),
                       section="Erweitert",
                       beim_zeigen=lambda: self.tab_install.refresh_summary())
        self.shell.add("verbindung", "Verbindung", "🔌",
                       bauen=lambda: ConnectTab(buehne, self.theme,
                                                self.state_obj),
                       section="Erweitert",
                       beim_zeigen=lambda: self.tab_connect.beim_zeigen())

        self.shell.show("start")
        self._zustand_spiegeln()
        for ereignis in ("device_changed", "base_pack_changed"):
            self.state_obj.subscribe(ereignis, self._zustand_spiegeln)

        status = ttk.Frame(self, style="TFrame")
        status.pack(fill="x", padx=20, pady=(6, 12))
        # Früher stand hier der volle Pfad des Datenordners. Der ist auf
        # jedem Rechner anders lang, schiebt sich über die halbe
        # Fensterbreite und sagt einem Laien nichts - er will nicht
        # wissen, WO die Dateien liegen, sondern hinkommen. Also ein
        # Knopf statt einer Zeile Text; den Pfad zeigt der Hinweis beim
        # Darüberfahren.
        ttk.Button(status, text="Datenordner öffnen", style="Link.TButton",
                   command=self._datenordner_oeffnen).pack(side="left")
        ttk.Label(status,
                  text="hier liegen Einstellungen, Pakete und Aufnahmen",
                  style="MutedBg.TLabel").pack(side="left", padx=(10, 0))

        # Die beiseitegelegte Vorgängerfassung kann erst jetzt weg -
        # beim Tausch lief sie noch. Kostet nichts und fällt nicht auf.
        try:
            aktualisierung.altlasten_entfernen()
        except Exception:                              # noqa: BLE001
            _LOG.debug("Aufräumen alter Fassungen fehlgeschlagen",
                       exc_info=True)

        # spaeter() statt after(): Der Auftrag wird beim Zerstören des
        # Fensters abbestellt. Ohne das feuert er ins Leere, und Tk
        # meldet "invalid command name ...".
        spaeter(self, 2500, self._update_still_pruefen)

    # ------------------------------------------------------------------
    # Die vier Seiten unter "Erweitert" entstehen erst beim ersten
    # Zugriff. Über diese Eigenschaften bleibt jeder bisherige
    # Aufruf unverändert gültig - er baut die Seite eben, wenn er
    # der erste ist.
    @property
    def tab_store(self):
        return self.shell.seite("eigene")

    @property
    def tab_builder(self):
        return self.shell.seite("ansagen")

    @property
    def tab_install(self):
        return self.shell.seite("aufspielen")

    @property
    def tab_connect(self):
        return self.shell.seite("verbindung")

    # ------------------------------------------------------------------
    def _update_still_pruefen(self) -> None:
        """Beim Start nachsehen - nur wenn eingeschaltet, und leise.

        Leise heißt: Ein ausgefallener Server, kein Netz oder eine
        Zeitüberschreitung sind kein Grund, jemandem beim Start ein
        Fehlerfenster hinzustellen. Gemeldet wird nur, was es Neues
        gibt.
        """
        cfg = self.state_obj.config
        if not cfg["update_pruefen"]:
            return
        # Höchstens einmal am Tag - sonst fragt die App bei jedem
        # Start nach, ohne dass sich etwas geändert haben könnte.
        if aktualisierung.jetzt() - int(cfg["update_zuletzt"] or 0) < 86400:
            return

        def work(_task):
            return aktualisierung.pruefen()

        def ok(neuerung) -> None:
            cfg["update_zuletzt"] = aktualisierung.jetzt()
            self.state_obj.save()
            if neuerung is None:
                return
            if neuerung.version == (cfg["update_uebersprungen"] or ""):
                return
            self._update_melden(neuerung)

        def still(_exc: Exception) -> None:
            # Auch ein Fehlschlag zählt als "nachgesehen". Sonst
            # versucht es die App bei JEDEM Start neu und arbeitet
            # damit gegen das Ratenlimit, das den Fehler ausgelöst
            # haben könnte.
            cfg["update_zuletzt"] = aktualisierung.jetzt()
            self.state_obj.save()
            _LOG.info("Suche nach Aktualisierungen fehlgeschlagen: %s", _exc)

        run_async(self, work, on_success=ok, on_error=still)

    def _update_melden(self, neuerung) -> None:
        """Fragt einmal nach - und merkt sich ein Nein."""
        antwort = messagebox.askyesnocancel(
            f"Version {neuerung.version} ist da",
            f"Du hast {__version__}, neu ist {neuerung.version}.\n\n"
            f"Jetzt ansehen?\n\n"
            f"'Nein' fragt beim nächsten Mal wieder, 'Abbrechen' "
            f"überspringt diese Fassung.",
            parent=self)
        if antwort is None:
            self.state_obj.config["update_uebersprungen"] = neuerung.version
            self.state_obj.save()
            return
        if not antwort:
            return
        self._show_update(neuerung)

    def _beim_ansagen(self) -> None:
        self.tab_builder.refresh_rows()
        self.tab_builder.refresh_counter()

    def _beim_eigene(self) -> None:
        if hasattr(self.tab_store, "beim_zeigen"):
            self.tab_store.beim_zeigen()
        if hasattr(self.tab_store, "refresh_saved_packs"):
            self.tab_store.refresh_saved_packs()

    def _zustand_spiegeln(self) -> None:
        """Sperrt, was ohne Anmeldung oder Originalpaket sinnlos wäre.

        Die Einträge bleiben sichtbar - sie sollen ja verraten, dass es
        sie gibt. Wer darauf klickt, erfährt, woran es liegt.
        """
        verbunden = self.state_obj.connected
        basis = self.state_obj.has_base_pack

        self.shell.set_dot("verbindung", "ok" if verbunden else "warn")

        ohne_anmeldung = ("Dafür muss die App erst wissen, welches Modell dein "
                          "Roboter ist. Melde dich auf der Startseite an.")
        ohne_basis = ("Dafür fehlt noch das offizielle Sprachpaket deines "
                      "Roboters. Es wird auf der Startseite einmalig geholt.")

        for key in ("stimme", "eigene", "ansagen", "aufspielen"):
            self.shell.set_enabled(key, verbunden and basis,
                                   ohne_anmeldung if not verbunden else ohne_basis)

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
        window.geometry("640x440")
        window.transient(self)

        card = Card(window, self.theme, f"{APP_NAME} {__version__}",
                    f"von {AUTOR} · {LIZENZ}-Lizenz")
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Text und Bildlaufleiste nebeneinander in einem eigenen Rahmen.
        # Vorher war der Text mit side="top" und expand=True gepackt - er
        # nahm damit die ganze Fläche, und für die Leiste blieb unten
        # rechts ein sinnloser Stummel übrig.
        feld = ttk.Frame(card.content, style="Card.TFrame")
        feld.pack(fill="both", expand=True)

        text = tk.Text(feld, wrap="word", relief="flat", borderwidth=0,
                       background=self.theme.color("surface"),
                       foreground=self.theme.color("text"),
                       highlightthickness=0,
                       font=self.theme.font_body, padx=4, pady=4, height=14)
        scroll = ttk.Scrollbar(feld, orient="vertical", command=text.yview)
        text.pack(side="left", fill="both", expand=True)

        # Die Leiste erscheint nur, wenn der Text wirklich länger ist als
        # das Fenster. Beim Haftungstext ist er das meistens nicht.
        def leiste_zeigen(erster: str, letzter: str) -> None:
            noetig = not (float(erster) <= 0.0 and float(letzter) >= 1.0)
            if noetig and not scroll.winfo_ismapped():
                scroll.pack(side="right", fill="y")
            elif not noetig and scroll.winfo_ismapped():
                scroll.pack_forget()
            scroll.set(erster, letzter)

        text.configure(yscrollcommand=leiste_zeigen)
        text.insert("1.0", HAFTUNG)
        text.configure(state="disabled")

        unten = ttk.Frame(window, style="TFrame")
        unten.pack(fill="x", padx=16, pady=(0, 16))

        knoepfe = ttk.Frame(unten, style="TFrame")
        knoepfe.pack(fill="x")

        if PROJEKT_URL:
            ttk.Button(knoepfe, text="Projektseite öffnen",
                       command=lambda: webbrowser.open(PROJEKT_URL)
                       ).pack(side="left")
        if SPENDEN_URL:
            ttk.Button(
                knoepfe, text="Trinkgeld dalassen (freiwillig)",
                command=lambda: webbrowser.open(SPENDEN_URL)
            ).pack(side="left", padx=(8, 0))

        ttk.Button(knoepfe, text="Schließen", style="Accent.TButton",
                   command=window.destroy).pack(side="right")

        # Der Hinweis steht unter den Knöpfen, nicht daneben: dazwischen
        # gequetscht brach er mitten im Satz um.
        if SPENDEN_URL:
            ttk.Label(unten,
                      text=("Freiwillig, ohne Gegenleistung - die App bleibt "
                            "für alle gleich."),
                      style="MutedBg.TLabel").pack(anchor="w", pady=(10, 0))

    # ------------------------------------------------------------------
    def _datenordner_oeffnen(self) -> None:
        """Öffnet den Datenordner im Explorer.

        Schlägt das fehl - kein Explorer, gesperrter Ordner -, wird der
        Pfad wenigstens genannt, statt dass der Knopf stumm bleibt.
        """
        ordner = data_dir()
        try:
            if sys.platform == "win32":
                os.startfile(str(ordner))              # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(ordner)])
            else:
                subprocess.Popen(["xdg-open", str(ordner)])
        except OSError as exc:
            _LOG.warning("Datenordner ließ sich nicht öffnen: %s", exc)
            show_warning(self, self.theme, "Ordner nicht geöffnet",
                         "Der Datenordner ließ sich nicht öffnen.",
                         f"Du findest ihn hier:\n{ordner}")

    # ------------------------------------------------------------------
    def _show_update(self, neuerung=None):
        """Öffnet das Aktualisierungsfenster - höchstens eines davon.

        Ein zweites Fenster daneben hätte zwei Schalter für dieselbe
        Einstellung und zwei Knöpfe, die denselben Download starten.
        """
        offen = getattr(self, "_fenster_update", None)
        if offen is not None and offen.winfo_exists():
            offen.deiconify()
            offen.lift()
            offen.focus_force()
        else:
            offen = UpdateFenster(self, self.theme, self.state_obj)
            self._fenster_update = offen
        if neuerung is not None:
            spaeter(offen, 120, lambda: offen.anbieten(neuerung))
        return offen

    # ------------------------------------------------------------------
    def _show_help(self) -> None:
        window = tk.Toplevel(self)
        window.title("Hilfe und Sicherheitshinweise")
        window.configure(bg=self.theme.color("bg"))
        window.geometry("760x740")
        window.minsize(560, 420)
        window.transient(self)

        # Von unten nach oben packen: Der Knopf zum Schließen und die
        # Anleitungen bekommen ihren Platz zuerst, der lange Text nimmt
        # den Rest. Andersherum schob er beide aus dem Fenster - auf
        # einem kleineren Bildschirm war das Fenster dann ohne
        # sichtbaren Ausgang.
        ttk.Button(window, text="Schließen", style="Accent.TButton",
                   command=window.destroy).pack(side="bottom", pady=(0, 16))
        self._bau_anleitungen(window)

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

    # ------------------------------------------------------------------
    def _bau_anleitungen(self, fenster) -> None:
        """Die ausführlichen Anleitungen als Knöpfe darunter.

        Ohne diese Liste war `docs/` aus der App heraus unsichtbar - wer
        nur die EXE hat, konnte nicht ahnen, dass es zu jedem Thema noch
        mehrere Seiten gibt. Der Knopf sagt vorher, was er tut: Datei
        oder Browser, je nachdem, was wirklich da ist.
        """
        karte = Card(fenster, self.theme, "Ausführlich nachlesen")
        karte.pack(side="bottom", fill="x", padx=16, pady=(0, 12))
        inhalt = karte.content

        art = {a.datei: anleitungen.verfuegbar(a.datei)
               for a in anleitungen.ANLEITUNGEN}
        online = [d for d, w in art.items() if w == "netz"]
        fehlt = [d for d, w in art.items() if w == "nein"]

        if fehlt and len(fehlt) == len(art):
            # Weder Dateien noch eine Projektadresse: dann lieber ein
            # ehrlicher Satz als sechs Knöpfe, die nichts tun.
            ttk.Label(inhalt, style="Muted.TLabel", justify="left",
                      wraplength=660,
                      text=("Die ausführlichen Anleitungen liegen im Ordner "
                            "'docs' beim Quellcode des Projekts.")).pack(anchor="w")
            return

        ttk.Label(inhalt, style="Muted.TLabel", justify="left", wraplength=660,
                  text=("Öffnet sich im Browser."
                        if online and len(online) == len(art)
                        else "Öffnet sich als Textdatei auf diesem PC.")
                  ).pack(anchor="w", pady=(0, 8))

        # Raster statt nebeneinander gepackter Zeilen: Sonst beginnt
        # jede Erklärung an einer anderen Stelle, weil die Knöpfe
        # unterschiedlich breit sind - das las sich wie ein Zaun.
        gitter = ttk.Frame(inhalt, style="Card.TFrame")
        gitter.pack(fill="x")
        gitter.columnconfigure(1, weight=1)
        reihe = 0
        for eintrag in anleitungen.ANLEITUNGEN:
            if art[eintrag.datei] == "nein":
                continue
            ttk.Button(gitter, text=eintrag.titel, style="Link.TButton",
                       command=lambda d=eintrag.datei: self._zeige_anleitung(d)
                       ).grid(row=reihe, column=0, sticky="w", pady=1)
            ttk.Label(gitter, text=eintrag.inhalt, style="Muted.TLabel",
                      wraplength=420, justify="left").grid(
                row=reihe, column=1, sticky="w", padx=(14, 0), pady=1)
            reihe += 1

    # ------------------------------------------------------------------
    def _zeige_anleitung(self, datei: str) -> None:
        """Anleitung öffnen und Bescheid geben, wenn es nicht klappt."""
        if anleitungen.oeffnen(datei) != "nein":
            return
        show_warning(
            self, self.theme, "Anleitung nicht erreichbar",
            f"'{datei}' ließ sich nicht öffnen.",
            "Die Datei liegt im Ordner 'docs' beim Quellcode des "
            "Projekts. Ist kein Programm für .md-Dateien eingerichtet, "
            "öffnet sie jeder Texteditor.")

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
DER KURZE WEG

Wer einfach nur einen bayerisch sprechenden Roboter will, braucht genau
zwei Seiten:

1. Start
   Beim ersten Mal steht hier das Anmeldeformular - dieselben
   Zugangsdaten wie in der Dreamehome-App. Danach holt die App einmalig
   das offizielle Sprachpaket deines Roboters; das ist die Grundlage für
   alles Weitere und bleibt gespeichert.
   Ab dem zweiten Start zeigt die Seite nur noch, was der Roboter gerade
   spricht.

2. Fertige Stimmen
   Bayerisch, Hessisch, Wienerisch oder Berlinerisch aussuchen, mit
   "Anhören" vier typische Ansagen probehören, dann "Aufspielen". Die
   Dialektstimmen stecken in der Programmdatei - es wird nichts
   heruntergeladen.

Das war es. Alles andere steht unter "Erweitert" und wird nur gebraucht,
wenn man mehr will:

- Eigene Stimmen: eigene Texte, andere Dialekte, Sprachsynthese über
  Windows oder ElevenLabs
- Einzelne Ansagen: Ansage für Ansage eine eigene Datei zuweisen
- Bauen und Aufspielen: der ausführliche Weg mit allen Schaltern,
  Netzwerkeinstellungen und dem Rückweg zur Originalstimme
- Verbindung: Konto oder Region wechseln

Graue Einträge in der Leiste sind nicht kaputt - sie brauchen nur erst
die Anmeldung. Ein Klick darauf verrät, was fehlt.


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

- Kennung. Dein Paket landet immer unter CUSTOM und überschreibt damit
  nicht die mitgelieferte deutsche Stimme. Das ist fest so: Der Roboter
  legt je Kennung einen eigenen Ordner an, und löschen kann man die
  über die Cloud nicht. Eine einzige Kennung überschreibt sich selbst.


DAS PAKET STEHT NICHT IN DER DREAMEHOME-APP

Das ist normal und kein Fehler. Die Dreamehome-App zeigt unter
"Sprachton" nur Sprachen aus Dreames eigenem Katalog. Die Kennung
CUSTOM steht dort nicht drin - also kann die App sie nicht anzeigen.

Meldet die App beim Öffnen, Roboter und App hätten verschiedene
Spracheinstellungen, ist das genau das Zeichen dafür, dass dein Paket
läuft: Der Roboter meldet eine Kennung, die die App nicht kennt.

Zwei Dinge dazu:

- Wähle in der Dreamehome-App keine Sprache aus, solange dein Paket
  laufen soll. Damit lädt der Roboter das offizielle Paket nach und
  überschreibt deines.
- In der Liste auftauchen kann es nicht. Die Kennung ist fest CUSTOM,
  und Dreames Katalog kennt sie nicht. Das ist Absicht: Der Roboter
  legt je Kennung einen eigenen Ordner an, und löschen kann man den
  über die Cloud nicht.
- Zurück zur Originalstimme geht es jederzeit über "Bauen und
  Aufspielen" > "Originalstimme wiederherstellen".

Ob dein Paket läuft, verrät der Knopf "Am Roboter abfragen" auf der
Startseite - unter "Bauen und Aufspielen" heißt derselbe Knopf
"Sprachpaket am Roboter abfragen". Die Antwort kommt direkt vom
Gerät, nicht aus der App.


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


EIGENE STIMMEN UND DIALEKTE

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
  Konto. Ein vollständiges Dialektpaket kostet je nach Dialekt 22.700
  bis 25.000 Zeichen - das Freikontingent von 10.000 im Monat reicht
  dafür nicht, ein bezahlter Tarif schon. Einzelne Ansagen gehen auch
  gratis: eine kostet im Mittel 40 Zeichen.

Vor dem Erzeugen lohnt sich "Kostprobe anhören": drei Sätze mit der
gerade gewählten Stimme, damit du weißt, worauf du dich einlässt.

Läuft das ElevenLabs-Kontingent mitten in der Erzeugung leer, geht nichts
verloren. Das Gesprochene bleibt gespeichert, das Paket wird mit dem
fertigen Teil gebaut, und beim nächsten Versuch macht die App genau dort
weiter.


AUDIODATEIEN

Der Roboter versteht nur OGG Vorbis, mono, 16000 Hz. mp3- und wav-Dateien
werden beim Bauen automatisch umgewandelt.

Dafür wird ffmpeg gebraucht - und das steckt in der Programmdatei mit
drin. Beim ersten Bedarf packt die App es einmalig in den Datenordner
aus, danach ist es einfach da. Du musst dich darum nicht kümmern.

Nur wer die App aus dem Quellcode startet, hat es nicht automatisch
dabei: Dann sucht sie eine ffmpeg.exe neben der App, im Datenordner oder
im System-PATH und bietet sonst an, sie herunterzuladen.

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
