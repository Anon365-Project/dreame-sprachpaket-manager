"""Seite 'Verbindung': Anmeldung am Herstellerkonto und Wahl des Roboters."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .. import aktualisierung
from .. import __version__
from ..cloud import (MARKEN, MARKEN_LABELS, REGION_LABELS, REGIONS,
                     DreameCloud, regionen_fuer)
from ..errors import NoDeviceError
from .state import AppState, error_text, run_async, to_main
from .theme import Theme
from .widgets import (Card, InfoBanner, ScrollablePage, StatusBadge, autowrap,
                      labeled_value, show_error, show_info, show_warning)

DREAMEHOME_HELP = "https://www.dreametech.com/pages/support"


class ConnectTab(ttk.Frame):
    def __init__(self, master, theme: Theme, state: AppState) -> None:
        super().__init__(master, style="TFrame")
        self.theme = theme
        self.state = state
        self._build()
        self._load_from_config()
        #: Läuft gerade ein Neuaufbau der Liste? Dann ist die Auswahl im
        #: Baum eine Folge davon und keine Entscheidung des Benutzers.
        self._baue_liste = False

        # Bewusst KEINE Anmeldung auf "device_changed": Das ergab eine
        # Endlosschleife (liste_auffrischen -> selection_set ->
        # <<TreeviewSelect>> -> _on_select_device -> notify -> zurück),
        # und die App blieb beim Öffnen dieser Seite stehen. Nötig ist
        # sie auch nicht: Wer die Liste sehen will, öffnet die Seite,
        # und dabei läuft beim_zeigen ohnehin.

    # ------------------------------------------------------------------
    def _build(self) -> None:
        page = ScrollablePage(self, self.theme)
        page.pack(fill="both", expand=True)
        outer = page.body()

        InfoBanner(
            outer, self.theme,
            "Die App meldet sich mit denselben Zugangsdaten an, die du in "
            "deiner Handy-App benutzt - Dreamehome, MOVA Home oder Trouver. "
            "Welche es ist, stellst du unten unter 'App' ein. Die Daten gehen "
            "ausschließlich an Dreame (MOVA und Trouver gehören dazu), nicht "
            "an Dritte. Ohne Anmeldung kennt die App weder dein Robotermodell "
            "noch kann sie ihm etwas schicken.",
        ).pack(fill="x", pady=(0, 14))

        # ---- Konto ----------------------------------------------------
        account = Card(outer, self.theme, "Herstellerkonto",
                       "E-Mail und Passwort wie in deiner Hersteller-App.")
        account.pack(fill="x")
        body = account.content

        grid = ttk.Frame(body, style="Card.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        # Dreamehome, MOVA Home und Trouver sind verschiedene Mandanten
        # beim selben Anbieter - andere Adresse, andere Mandanten-ID.
        # Ohne diese Auswahl ging jede Anmeldung an den Dreame-Mandanten,
        # und MOVA- wie Trouver-Konten scheiterten ohne erkennbaren Grund.
        ttk.Label(grid, text="App", style="Surface.TLabel").grid(
            row=0, column=0, sticky="w", pady=6, padx=(0, 12))
        self.var_marke = tk.StringVar()
        self.combo_marke = ttk.Combobox(
            grid, textvariable=self.var_marke, state="readonly",
            values=[MARKEN_LABELS[m] for m in MARKEN], width=42)
        self.combo_marke.grid(row=0, column=1, sticky="w", pady=6)
        self.combo_marke.bind("<<ComboboxSelected>>", self._on_marke)

        ttk.Label(grid, text="E-Mail", style="Surface.TLabel").grid(
            row=1, column=0, sticky="w", pady=6, padx=(0, 12))
        self.var_email = tk.StringVar()
        ttk.Entry(grid, textvariable=self.var_email).grid(
            row=1, column=1, sticky="ew", pady=6)

        ttk.Label(grid, text="Passwort", style="Surface.TLabel").grid(
            row=2, column=0, sticky="w", pady=6, padx=(0, 12))
        pw_row = ttk.Frame(grid, style="Card.TFrame")
        pw_row.grid(row=2, column=1, sticky="ew", pady=6)
        self.var_password = tk.StringVar()
        self.entry_password = ttk.Entry(pw_row, textvariable=self.var_password, show="•")
        self.entry_password.pack(side="left", fill="x", expand=True)
        self.var_show_pw = tk.BooleanVar(value=False)
        ttk.Checkbutton(pw_row, text="zeigen", variable=self.var_show_pw,
                        command=self._toggle_password).pack(side="left", padx=(10, 0))

        ttk.Label(grid, text="Region", style="Surface.TLabel").grid(
            row=3, column=0, sticky="w", pady=6, padx=(0, 12))
        region_row = ttk.Frame(grid, style="Card.TFrame")
        region_row.grid(row=3, column=1, sticky="ew", pady=6)
        self.var_region = tk.StringVar(value=REGION_LABELS["eu"])
        self.combo_region = ttk.Combobox(
            region_row, textvariable=self.var_region, state="readonly",
            values=[REGION_LABELS[r] for r in REGIONS], width=42)
        self.combo_region.pack(side="left")
        self.var_autoregion = tk.BooleanVar(value=True)
        ttk.Checkbutton(region_row, text="automatisch suchen",
                        variable=self.var_autoregion).pack(side="left", padx=(12, 0))

        options = ttk.Frame(body, style="Card.TFrame")
        options.pack(fill="x", pady=(10, 0))
        self.var_remember = tk.BooleanVar(value=False)
        chk = ttk.Checkbutton(options, text="Passwort auf diesem PC merken",
                              variable=self.var_remember)
        chk.pack(side="left")
        if not self.state.config.can_remember_password():
            chk.configure(state="disabled")
            ttk.Label(options, text="(nur unter Windows verfügbar)",
                      style="Muted.TLabel").pack(side="left", padx=(8, 0))
        else:
            ttk.Label(options,
                      text="(verschlüsselt mit deinem Windows-Konto)",
                      style="Muted.TLabel").pack(side="left", padx=(8, 0))

        actions = ttk.Frame(body, style="Card.TFrame")
        actions.pack(fill="x", pady=(16, 0))
        self.btn_login = ttk.Button(actions, text="Anmelden und Roboter suchen",
                                    style="Accent.TButton", command=self._on_login)
        self.btn_login.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=160)
        self.badge = StatusBadge(actions, self.theme, "Nicht angemeldet")
        self.badge.pack(side="left", padx=(14, 0))

        # ---- Roboter ---------------------------------------------------
        devices = Card(outer, self.theme, "Gefundene Roboter",
                       "Wähle den Roboter aus, dessen Stimme du ändern willst.")
        devices.pack(fill="both", expand=True, pady=(14, 0))

        self.tree = ttk.Treeview(devices.content,
                                 columns=("name", "model", "did"),
                                 show="headings", height=5, selectmode="browse")
        self.tree.heading("name", text="Name")
        self.tree.heading("model", text="Modell")
        self.tree.heading("did", text="Geräte-ID")
        self.tree.column("name", width=240, anchor="w")
        self.tree.column("model", width=210, anchor="w")
        self.tree.column("did", width=150, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_device)

        self.lbl_empty = ttk.Label(
            devices.content,
            text="Noch keine Roboter geladen - melde dich oben an.",
            style="Muted.TLabel")
        self.lbl_empty.pack(anchor="w", pady=(8, 0))

        # ---- Details ---------------------------------------------------
        details = Card(outer, self.theme, "Ausgewählter Roboter")
        details.pack(fill="x", pady=(14, 0))
        self.val_name = labeled_value(details.content, self.theme, "Name")
        self.val_model = labeled_value(details.content, self.theme, "Modell-Kennung")
        self.val_did = labeled_value(details.content, self.theme, "Geräte-ID (did)")
        self.val_mac = labeled_value(details.content, self.theme, "MAC-Adresse")
        self.val_voice = labeled_value(details.content, self.theme, "Aktives Sprachpaket")

        note = ttk.Frame(details.content, style="Card.TFrame")
        note.pack(fill="x", pady=(12, 0))
        ttk.Label(
            note,
            text=("Kein lokales Token? Das ist richtig so. Modelle, die in der "
                  "Dreamehome-App laufen - wie der X50 Ultra - bieten im Heimnetz "
                  "keinen direkten Zugang mehr an und geben auch kein 32-stelliges "
                  "miio-Token heraus. Befehle laufen über die Dreame-Cloud, das "
                  "Sprachpaket selbst holt sich der Roboter danach direkt von "
                  "diesem PC."),
            style="Muted.TLabel", wraplength=820, justify="left").pack(anchor="w")

        link = ttk.Button(note, text="Dreame-Hilfeseite öffnen", style="Link.TButton",
                          command=lambda: webbrowser.open(DREAMEHOME_HELP))
        link.pack(anchor="w", pady=(6, 0))

        # ---- Weitergabe -------------------------------------------------
        # Passwort und Schlüssel liegen im Windows-Tresor und wandern
        # ohnehin nicht mit. Die config.json enthält aber die E-Mail, den
        # Namen und die MAC des Roboters und die IP dieses PCs - beim
        # Weitergeben samt Datenordner ginge das mit.

        # ---- Aktualisierung ------------------------------------------
        # Steht seit Version 1.3.0 in einem eigenen Fenster, erreichbar
        # über den Knopf oben rechts. Hier bleibt nur ein Verweis für
        # alle, die es an dieser Stelle gewohnt sind.
        akt = Card(outer, self.theme, "Aktualisierung",
                   "Nachsehen, ob es eine neuere Fassung gibt")
        akt.pack(fill="x", pady=(14, 0))

        ttk.Label(
            akt.content,
            text=(f"Diese Fassung: {__version__}\n\n"
                  "Das Nachsehen und der Schalter 'beim Start nachsehen' "
                  "stehen jetzt oben rechts unter 'Aktualisierung'."),
            style="Surface.TLabel", wraplength=780, justify="left").pack(anchor="w")

        ttk.Button(akt.content, text="Aktualisierung öffnen ...",
                   command=self._on_update_oeffnen).pack(anchor="w", pady=(12, 0))

        weiter = Card(outer, self.theme, "App weitergeben",
                      "Persönliche Spuren entfernen, bevor jemand anderes sie bekommt")
        weiter.pack(fill="x", pady=(14, 0))

        ttk.Label(
            weiter.content,
            text=("Dein Passwort und der ElevenLabs-Schlüssel liegen im "
                  "Windows-Anmeldeinformationsspeicher, nicht in einer Datei - "
                  "die wandern beim Kopieren also gar nicht erst mit.\n\n"
                  "Im Datenordner steht trotzdem einiges, was auf dich zeigt: "
                  "deine E-Mail-Adresse, Name, Geräte-ID und MAC deines "
                  "Roboters, die IP dieses PCs, die zuletzt benutzte "
                  "ElevenLabs-Stimme und das Protokoll. Der Knopf löscht "
                  "genau das."),
            style="Surface.TLabel", wraplength=780, justify="left").pack(anchor="w")

        ttk.Label(
            weiter.content,
            text=("Deine gebauten Sprachpakete, die Dialekttexte und die "
                  "mitgelieferten Aufnahmen bleiben erhalten - da steckt nichts "
                  "Persönliches drin."),
            style="Muted.TLabel", wraplength=780, justify="left"
        ).pack(anchor="w", pady=(8, 0))

        ttk.Button(weiter.content, text="Persönliche Daten entfernen ...",
                   command=self._on_forget_personal).pack(anchor="w", pady=(12, 0))


    # -- Aktualisierung --------------------------------------------------
    def _on_update_oeffnen(self) -> None:
        """Öffnet das Aktualisierungsfenster des Hauptfensters.

        Die Kette selbst - laden, prüfen, austauschen, neu starten -
        liegt in ui/fenster_update.py. Zweimal dieselbe Kette zu
        pflegen wäre der sichere Weg, sie irgendwann auseinanderlaufen
        zu lassen.
        """
        fenster = self.winfo_toplevel()
        oeffnen = getattr(fenster, "_show_update", None)
        if callable(oeffnen):
            oeffnen()

    # ------------------------------------------------------------------
    def _on_forget_personal(self) -> None:
        """Räumt alles weg, was auf den bisherigen Benutzer zeigt."""
        if not messagebox.askyesno(
                "Persönliche Daten entfernen?",
                "Entfernt werden:\n\n"
                "  • E-Mail-Adresse und gespeichertes Passwort\n"
                "  • der ElevenLabs-Schlüssel\n"
                "  • Name, Geräte-ID und MAC deines Roboters\n"
                "  • die IP-Adresse dieses PCs\n"
                "  • die zuletzt benutzte ElevenLabs-Stimme\n"
                "  • das Protokoll\n\n"
                "Deine gebauten Sprachpakete und Dialekttexte bleiben.\n\n"
                "Beim nächsten Start musst du dich neu anmelden. "
                "Fortfahren?",
                parent=self):
            return

        geleert = self.state.config.forget_personal()
        self.state.cloud = None
        self.state.device = None
        self.state.devices = []
        self.state.config.save()

        self.var_email.set("")
        self.var_password.set("")
        self.tree.delete(*self.tree.get_children())
        self.lbl_empty.pack(anchor="w", pady=(8, 0))
        self.badge.set("Nicht angemeldet", "muted")
        self._load_from_config()
        self.state.notify("device_changed")

        # Bewusst zwei Zeilen statt eines Bedingungsausdrucks: Der bände
        # sonst an den ganzen Text und ließe ohne Treffer auch die
        # Erklärung verschwinden.
        kopf = (f"{len(geleert)} Angaben entfernt." if geleert
                else "Es war nichts zu entfernen.")
        einzelheiten = ("Die App lässt sich jetzt samt Datenordner weitergeben, "
                        "ohne dass etwas über dich mitgeht.")
        if geleert:
            einzelheiten += "\n\nEntfernt: " + ", ".join(geleert)
        show_info(self, self.theme, "Erledigt", kopf, einzelheiten)

    # ------------------------------------------------------------------
    def _toggle_password(self) -> None:
        self.entry_password.configure(show="" if self.var_show_pw.get() else "•")

    def _marke_code(self) -> str:
        """Aus der Beschriftung zurück auf 'dreame'/'mova'/'trouver'."""
        gewaehlt = self.var_marke.get()
        for code, text in MARKEN_LABELS.items():
            if text == gewaehlt:
                return code
        return MARKEN[0]

    def _on_marke(self, _event=None) -> None:
        """Andere Marke: Die Regionenliste passt sich an."""
        marke = self._marke_code()
        self.state.config["account_type"] = marke
        erlaubt = regionen_fuer(marke)
        self.combo_region.configure(
            values=[REGION_LABELS[r] for r in erlaubt])
        if self._region_code() not in erlaubt:
            self.var_region.set(REGION_LABELS[erlaubt[0]])

    def _region_code(self) -> str:
        label = self.var_region.get()
        for code, text in REGION_LABELS.items():
            if text == label:
                return code
        return "eu"

    def _load_from_config(self) -> None:
        cfg = self.state.config
        self.var_marke.set(MARKEN_LABELS.get(cfg["account_type"],
                                             MARKEN_LABELS["dreame"]))
        self.var_email.set(cfg["email"])
        self.var_region.set(REGION_LABELS.get(cfg["region"], REGION_LABELS["eu"]))
        self.var_remember.set(bool(cfg["remember_password"]))
        if cfg["remember_password"]:
            stored = cfg.password
            if stored:
                self.var_password.set(stored)

        if cfg["device_id"]:
            self.val_name.configure(text=cfg["device_name"] or "-")
            self.val_model.configure(text=cfg["device_model"] or "-")
            self.val_did.configure(text=cfg["device_id"])
            self.val_mac.configure(text=cfg["device_mac"] or "-")
            self.badge.set("Zuletzt gespeicherter Roboter geladen", "muted")

    # ------------------------------------------------------------------
    def _busy(self, active: bool) -> None:
        if active:
            self.btn_login.configure(state="disabled")
            self.progress.pack(side="left", padx=(14, 0))
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.btn_login.configure(state="normal")

    def _on_login(self) -> None:
        email = self.var_email.get().strip()
        password = self.var_password.get()
        if not email or not password:
            messagebox.showwarning("Angaben fehlen",
                                   "Bitte E-Mail und Passwort eintragen.",
                                   parent=self)
            return

        region = self._region_code()
        auto = self.var_autoregion.get()

        self._busy(True)
        self.badge.set("Melde an ...", "muted")

        marke = self._marke_code()
        self.state.config["account_type"] = marke

        def work(_task):
            cloud = DreameCloud(marke)
            if auto:
                used_region = cloud.login_autodetect(email, password, region)
            else:
                cloud.login(email, password, region)
                used_region = region
            devices = cloud.list_devices(only_vacuums=True)
            return cloud, used_region, devices

        run_async(self, work, on_success=self._on_login_ok,
                  on_error=self._on_login_error,
                  on_finally=lambda: self._busy(False))

    def _on_login_ok(self, result) -> None:
        cloud, region, devices = result
        self.state.cloud = cloud
        self.state.devices = devices

        cfg = self.state.config
        cfg["email"] = self.var_email.get().strip()
        cfg["region"] = region
        cfg.set_password(self.var_password.get(), self.var_remember.get())
        self.var_region.set(REGION_LABELS.get(region, self.var_region.get()))
        self.state.save()

        self.liste_auffrischen(region)

    # ------------------------------------------------------------------
    def liste_auffrischen(self, region: str = "") -> None:
        """Zeigt die Roboter, die die App kennt.

        Nimmt die Geräte aus dem gemeinsamen Zustand, nicht aus einem
        Rückgabewert: Wer sich auf der Startseite anmeldet - der übliche
        Weg -, fand hier sonst eine leere Liste vor, obwohl oben
        "Zuletzt gespeicherter Roboter geladen" stand und die
        Detailfelder darunter ausgefüllt waren.
        """
        devices = list(self.state.devices or [])
        self._baue_liste = True
        try:
            self._liste_fuellen(devices, region)
        finally:
            self._baue_liste = False

    def _liste_fuellen(self, devices: list, region: str) -> None:
        """Der eigentliche Aufbau - immer unter dem Riegel oben."""
        self.tree.delete(*self.tree.get_children())

        if not devices:
            if self.state.connected:
                # Angemeldet, aber die Liste ist leer: Das kann nur ein
                # Konto ohne Saugroboter sein.
                self.badge.set("Angemeldet, aber kein Saugroboter gefunden",
                               "warn")
                self.lbl_empty.configure(
                    text=("In diesem Konto ist kein Saugroboter hinterlegt. "
                          "Prüfe, ob du dieselbe E-Mail wie in deiner "
                          "Hersteller-App nutzt und ob der Roboter dort "
                          "auftaucht."))
            elif self.state.config["device_id"]:
                # Nicht angemeldet, aber ein Roboter ist gemerkt. Das ist
                # der Normalfall beim Start - und kein Fehler.
                self.lbl_empty.configure(
                    text=("Der zuletzt benutzte Roboter steht unten. Für die "
                          "vollständige Liste oben anmelden."))
            else:
                self.lbl_empty.configure(
                    text="Noch keine Roboter geladen - melde dich oben an.")
            self.lbl_empty.pack(anchor="w", pady=(8, 0))
            return

        self.lbl_empty.pack_forget()
        for device in devices:
            self.tree.insert("", "end", iid=device.did,
                             values=(device.name, device.model, device.did))

        wo = f" ({region.upper()})" if region else ""
        self.badge.set(f"Angemeldet{wo} - {len(devices)} Roboter gefunden", "ok")

        # Zuletzt genutzten Roboter wieder auswählen, sonst den ersten.
        preferred = self.state.config["device_id"]
        target = (preferred if preferred in self.tree.get_children()
                  else devices[0].did)
        self.tree.selection_set(target)
        self.tree.focus(target)

    def beim_zeigen(self) -> None:
        """Beim Öffnen der Seite nachziehen, was inzwischen bekannt ist."""
        self.liste_auffrischen(self.state.config["region"] or "")

    def _on_login_error(self, exc: Exception) -> None:
        message, hint = error_text(exc)
        self.badge.set("Anmeldung fehlgeschlagen", "error")
        show_error(self, self.theme, "Anmeldung fehlgeschlagen",
                       message + (f"\n\n{hint}" if hint else ""))

    # ------------------------------------------------------------------
    def _on_select_device(self, _event=None) -> None:
        # Während die Liste neu aufgebaut wird, kommt die Auswahl von
        # uns selbst. Sie dann zu verarbeiten hieße: speichern,
        # "device_changed" melden, und über die Empfänger wieder hier
        # landen - eine Schleife, die die App zum Stehen brachte.
        if getattr(self, "_baue_liste", False):
            return
        selection = self.tree.selection()
        if not selection:
            return
        did = selection[0]
        device = next((d for d in self.state.devices if d.did == did), None)
        if device is None:
            return

        self.state.device = device
        cfg = self.state.config
        cfg["device_id"] = device.did
        cfg["device_model"] = device.model
        cfg["device_name"] = device.name
        cfg["device_mac"] = device.mac
        self.state.save()

        self.val_name.configure(text=device.name)
        self.val_model.configure(text=device.model)
        self.val_did.configure(text=device.did)
        self.val_mac.configure(text=device.mac or "-")
        self.val_voice.configure(text="wird abgefragt ...")

        self.state.notify("device_changed")
        self._refresh_voice_pack()

    def _refresh_voice_pack(self) -> None:
        cloud, device = self.state.cloud, self.state.device
        if not (cloud and device):
            return

        def work(_task):
            return cloud.current_voice_pack(device)

        def ok(value):
            self.val_voice.configure(text=str(value) if value else "unbekannt")

        def fail(_exc):
            self.val_voice.configure(text="nicht abfragbar (Roboter im Standby?)")

        run_async(self, work, on_success=ok, on_error=fail)

    def require_device(self) -> None:
        if not self.state.connected:
            raise NoDeviceError(
                "Es ist kein Roboter ausgewählt.",
                "Melde dich unter 'Verbindung' an und wähle deinen Roboter.",
            )
