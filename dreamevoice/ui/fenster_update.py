"""Das Fenster für Aktualisierungen.

Bis hierher steckte das alles auf der Seite "Verbindung" - unter dem
Konto und der Roboterliste, wo es niemand vermutet. Aktualisieren hat
mit der Verbindung zum Roboter aber nichts zu tun; es betrifft die App
selbst. Deshalb ein eigenes Fenster, erreichbar über den Knopf oben
rechts, direkt neben "Hilfe" und "Über".

Der Schalter "beim Start nachsehen" steht mit im Fenster: Wer wissen
will, ob automatisch geprüft wird, sucht genau da - und nicht in einer
Seite, die er sonst nie öffnet.

Warum ausgeschaltet, bis jemand es einschaltet: Die Abfrage geht an
GitHub und verrät dadurch, dass hier jemand diese App benutzt. Das
gehört gefragt, nicht angenommen.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import __version__, aktualisierung
from .state import AppState, error_text, run_async, spaeter, to_main
from .theme import Theme
from .widgets import Card, show_error, show_info, show_warning


class UpdateFenster(tk.Toplevel):
    """Nachsehen, was es Neues gibt - und die App sich selbst ersetzen lassen.

    Das Fenster hält die ganze Kette: nachfragen, anbieten, laden,
    Prüfsumme kontrollieren, austauschen, neu starten. Vorher lag sie
    in `tab_connect`; von dort aus ließ sie sich nur erreichen, wenn
    diese Seite gebaut war.
    """

    def __init__(self, master, theme: Theme, state: AppState) -> None:
        super().__init__(master)
        self.theme = theme
        self.state = state

        self.title("Aktualisierung")
        self.configure(bg=theme.color("bg"))
        self.geometry("660x520")
        self.minsize(520, 420)
        self.transient(master)

        # Knopf zum Schließen zuerst, damit ihn ein langer Text nicht
        # aus dem Fenster schiebt.
        ttk.Button(self, text="Schließen", style="Accent.TButton",
                   command=self.destroy).pack(side="bottom", pady=(0, 14))

        karte = Card(self, theme, "Aktualisierung",
                     "Nachsehen, ob es eine neuere Fassung gibt")
        karte.pack(fill="both", expand=True, padx=16, pady=16)
        inhalt = karte.content

        ttk.Label(
            inhalt,
            text=(f"Diese Fassung: {__version__}\n\n"
                  "Die App fragt bei GitHub nach der neuesten Fassung. Dabei "
                  "wird nichts über dich oder deinen Roboter übermittelt - "
                  "aber wie bei jedem Seitenaufruf sieht die Gegenseite deine "
                  "IP-Adresse. Deshalb ist die Abfrage ausgeschaltet, solange "
                  "du sie nicht einschaltest."),
            style="Surface.TLabel", wraplength=580, justify="left").pack(anchor="w")

        self.var_update = tk.BooleanVar(
            value=bool(state.config["update_pruefen"]))
        ttk.Checkbutton(inhalt, style="Haken.TCheckbutton",
                        text="Beim Start nachsehen, ob es eine neuere Fassung gibt",
                        variable=self.var_update,
                        command=self._on_schalter).pack(anchor="w", pady=(12, 0))

        reihe = ttk.Frame(inhalt, style="Card.TFrame")
        reihe.pack(fill="x", pady=(12, 0))
        self.btn_update = ttk.Button(reihe, text="Jetzt nach Aktualisierung suchen",
                                     command=self._on_suchen)
        self.btn_update.pack(side="left")
        self.lbl_update = ttk.Label(reihe, text="", style="Muted.TLabel",
                                    wraplength=380, justify="left")
        self.lbl_update.pack(side="left", padx=(12, 0))

        ttk.Label(
            inhalt,
            text=("Gefunden wird nichts von selbst installiert. Die App zeigt, "
                  "was neu ist, und fragt. Erst dann lädt sie die neue Datei, "
                  "prüft ihre Prüfsumme und ersetzt sich selbst - ohne "
                  "Installation, ohne Administratorrechte. Dein Datenordner "
                  "bleibt unberührt."),
            style="Muted.TLabel", wraplength=580, justify="left"
        ).pack(anchor="w", pady=(14, 0))

    # ------------------------------------------------------------------
    def _on_schalter(self) -> None:
        self.state.config["update_pruefen"] = bool(self.var_update.get())
        self.state.save()

    def _on_suchen(self) -> None:
        """Von Hand nachsehen. Hier wird auch ein Fehler gezeigt."""
        self.btn_update.configure(state="disabled")
        self.lbl_update.configure(text="Sehe nach ...")

        def work(_task):
            return aktualisierung.pruefen()

        def ok(neuerung) -> None:
            self.state.config["update_zuletzt"] = aktualisierung.jetzt()
            self.state.save()
            if neuerung is None:
                self.lbl_update.configure(
                    text=f"{__version__} ist die neueste Fassung.")
                return
            self.lbl_update.configure(text=f"Version {neuerung.version} ist da.")
            self.anbieten(neuerung)

        def fail(exc: Exception) -> None:
            nachricht, hinweis = error_text(exc)
            self.lbl_update.configure(text=nachricht)
            show_error(self, self.theme, "Suche fehlgeschlagen", nachricht, hinweis)

        run_async(self, work, on_success=ok, on_error=fail,
                  on_finally=lambda: self.btn_update.configure(state="normal"))

    # ------------------------------------------------------------------
    def anbieten(self, neuerung) -> None:
        """Zeigt, was neu ist, und fragt - installiert wird nichts von selbst."""
        exe = aktualisierung.eigene_exe()
        notizen = (neuerung.notizen or "").strip()
        if len(notizen) > 900:
            notizen = notizen[:900].rsplit("\n", 1)[0] + "\n..."

        if exe is None:
            show_info(self, self.theme, f"Version {neuerung.version} ist da",
                      "Diese App läuft aus dem Quellcode - ein Austausch der "
                      "Programmdatei ergibt hier keinen Sinn.",
                      f"Hol dir die neue Fassung über git.\n\n{notizen}")
            return

        if not neuerung.pruefbar:
            show_warning(self, self.theme, f"Version {neuerung.version} ist da",
                         "Zu dieser Fassung liegt keine Prüfsumme vor.",
                         "Ohne sie wird nichts ausgetauscht - eine "
                         "Programmdatei ungeprüft über die eigene zu "
                         "schreiben, wäre genau der Weg, den man einem "
                         "Angreifer nicht offenlassen darf.\n\n"
                         f"Lade sie von der Projektseite:\n{neuerung.seite}")
            return

        if not aktualisierung.ordner_beschreibbar(exe):
            show_warning(self, self.theme, f"Version {neuerung.version} ist da",
                         "In diesem Ordner darf die App nichts schreiben.",
                         "Deshalb kann sie sich hier nicht selbst ersetzen. "
                         "Verschiebe sie in einen eigenen Ordner - etwa auf "
                         "den Schreibtisch - oder lade die neue Fassung von "
                         f"der Projektseite:\n{neuerung.seite}")
            return

        if not messagebox.askyesno(
                f"Version {neuerung.version} ist da",
                f"Du hast {__version__}, neu ist {neuerung.version} "
                f"({neuerung.groesse_mb:.0f} MB).\n\n"
                f"Die App lädt die neue Datei, prüft ihre Prüfsumme und legt "
                f"sich selbst beiseite. Danach startet sie neu. Dein "
                f"Datenordner und deine Pakete bleiben unberührt.\n\n"
                + (f"Was neu ist:\n{notizen}\n\n" if notizen else "")
                + "Jetzt aktualisieren?",
                parent=self):
            return

        self._holen(neuerung)

    def _holen(self, neuerung) -> None:
        self.btn_update.configure(state="disabled")
        self.lbl_update.configure(text="Lade ...")

        def melde(geladen: int, gesamt: int) -> None:
            if not gesamt:
                return
            text = f"Lade ... {geladen * 100 // gesamt} %"
            to_main(self, lambda t=text: self.lbl_update.configure(text=t))

        def work(task):
            neu = aktualisierung.herunterladen(
                neuerung, progress=melde, cancelled=lambda: task.cancelled)
            # Erst tauschen, wenn die Datei vollständig und geprüft ist.
            # Die Prüfsumme wird unmittelbar vor dem Tausch noch einmal
            # geprüft - zwischen Download und Umbenennen liegt sonst ein
            # Zeitfenster, in dem jemand die Datei austauschen könnte.
            aktualisierung.austauschen(neu, erwartet_sha256=neuerung.sha256)
            return True

        def ok(_ergebnis) -> None:
            self.lbl_update.configure(text=f"Version {neuerung.version} ist bereit.")
            if messagebox.askyesno(
                    "Fertig",
                    f"Version {neuerung.version} ist eingespielt.\n\n"
                    f"Jetzt neu starten? Die alte Fassung wird beim nächsten "
                    f"Start weggeräumt.",
                    parent=self):
                if aktualisierung.neu_starten():
                    haupt = self.master.winfo_toplevel()
                    spaeter(haupt, 200, haupt.destroy)
                else:
                    show_warning(self, self.theme, "Neustart",
                                 "Die neue Fassung ließ sich nicht starten.",
                                 "Schließe die App und starte sie von Hand.")

        def fail(exc: Exception) -> None:
            nachricht, hinweis = error_text(exc)
            self.lbl_update.configure(text=nachricht)
            # Im Notstand liegt tatsächlich keine startfähige Datei mehr
            # am Platz. "Es wurde nichts ausgetauscht" wäre dann das
            # Gegenteil der Wahrheit - und zwar genau in dem Moment, in
            # dem der Benutzer wissen muss, was zu tun ist.
            if isinstance(exc, aktualisierung.TauschNotstand):
                show_error(self, self.theme, "Bitte von Hand nachhelfen",
                           nachricht, hinweis)
                return
            show_error(self, self.theme, "Nicht aktualisiert", nachricht,
                       (hinweis + "\n\n" if hinweis else "")
                       + f"Es wurde nichts ausgetauscht. Die Datei liegt "
                         f"weiterhin auf der Projektseite bereit:\n"
                         f"{neuerung.seite}")

        run_async(self, work, on_success=ok, on_error=fail,
                  on_finally=lambda: self.btn_update.configure(state="normal"))
