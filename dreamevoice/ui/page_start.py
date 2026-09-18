"""Die Startseite - sie richtet sich danach, was gerade fehlt.

Drei Zustände, eine Seite:

1. **Nicht angemeldet.** Dann steht das Anmeldeformular mitten auf der
   Seite. Kein Menüpunkt, den man erst finden muss - wer die App zum
   ersten Mal öffnet, sieht genau das eine Formular, das er ausfüllen
   muss.
2. **Angemeldet, aber ohne Originalpaket.** Der einmalige Zwischenschritt.
   Er läuft von selbst; hier steht nur, dass er läuft und warum.
3. **Alles bereit.** Oben groß, was der Roboter gerade spricht, darunter
   die Handlungen. Ab dem zweiten Start sieht man nur noch das.

Der Zustand wird nicht geraten, sondern bei jedem Anzeigen aus `AppState`
abgelesen (`refresh`). Damit ist ausgeschlossen, dass die Seite etwas
anderes behauptet, als tatsächlich der Fall ist.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk

from .. import installer, official
from ..cloud import (MARKEN, MARKEN_LABELS, REGION_LABELS, REGIONS,
                     DreameCloud, regionen_fuer)
from ..paths import preview_dir
from .state import AppState, error_text, run_async, spaeter, to_main
from .theme import Theme
from .widgets import (Card, ScrollablePage, StatusBadge, show_error,
                      show_info, show_warning)

_LOG = logging.getLogger(__name__)

ZUSTAND_ANMELDEN = "anmelden"
ZUSTAND_ROBOTER = "roboter"
ZUSTAND_ORIGINAL = "original"
ZUSTAND_BEREIT = "bereit"


class StartPage(ttk.Frame):
    """Begrüßung, Anmeldung und Zustandsanzeige in einem."""

    def __init__(self, master, theme: Theme, state: AppState,
                 gehe_zu=None) -> None:
        super().__init__(master, style="TFrame")
        self.theme = theme
        self.state = state
        self.gehe_zu = gehe_zu or (lambda _key: None)

        self._zustand = ""
        self._laedt_original = False

        # Dreamehome, MOVA Home oder Trouver: verschiedene
        # Mandanten beim selben Anbieter. Ohne diese Auswahl
        # ging jede Anmeldung an den Dreame-Mandanten - für
        # MOVA- und Trouver-Konten scheiterte sie dadurch.
        self.var_marke = tk.StringVar()
        self.var_email = tk.StringVar()
        self.var_password = tk.StringVar()
        self.var_region = tk.StringVar()
        self.var_remember = tk.BooleanVar(value=True)
        self.var_autoregion = tk.BooleanVar(value=True)
        self.var_device = tk.StringVar()

        self._build()
        self._aus_config()
        self.refresh()

        self.state.subscribe("device_changed", self.refresh)
        self.state.subscribe("base_pack_changed", self.refresh)
        # Nach dem Aufspielen soll hier der neue Paketname stehen -
        # ohne dass dafür der ganze Gerätestand verworfen wird.
        self.state.subscribe("pack_installed", self.refresh)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        page = ScrollablePage(self, self.theme)
        page.pack(fill="both", expand=True)
        self.outer = page.body()

        self.kopf = ttk.Label(self.outer, text="", style="Title.TLabel")
        self.kopf.pack(anchor="w")
        self.unterzeile = ttk.Label(self.outer, text="", style="MutedBg.TLabel",
                                    wraplength=760, justify="left")
        self.unterzeile.pack(anchor="w", pady=(3, 16))

        # Jeder Zustand bekommt einen eigenen Rahmen. Angezeigt wird immer
        # genau einer - so kann keine halb ausgefüllte Ansicht stehen
        # bleiben, wenn sich der Zustand ändert.
        self.rahmen = {
            ZUSTAND_ANMELDEN: self._bau_anmelden(),
            ZUSTAND_ROBOTER: self._bau_roboter(),
            ZUSTAND_ORIGINAL: self._bau_original(),
            ZUSTAND_BEREIT: self._bau_bereit(),
        }

    # -- Zustand 1: Anmelden ------------------------------------------
    def _bau_anmelden(self) -> ttk.Frame:
        rahmen = ttk.Frame(self.outer, style="TFrame")

        card = Card(rahmen, self.theme, "Beim Hersteller-Konto anmelden",
                    "Dieselben Zugangsdaten wie in deiner Handy-App")
        card.pack(fill="x")
        inhalt = card.content

        # Ein Raster statt gestapelter Zeilen: nur so stehen Beschriftungen
        # und Felder wirklich auf einer Flucht, egal wie lang die Wörter
        # sind. Die Felder gehören dabei ins Raster - werden sie einem
        # anderen Elternteil zugewiesen, landen sie nebeneinander.
        # Nicht die volle Kartenbreite: Ein Eingabefeld, das sich über 900
        # Pixel zieht, sieht nach Datenbankmaske aus - und eine E-Mail
        # braucht keine 900 Pixel.
        raster = ttk.Frame(inhalt, style="Card.TFrame")
        raster.pack(anchor="w")
        raster.columnconfigure(1, minsize=340)

        def beschriftung(zeile: int, text: str) -> None:
            ttk.Label(raster, text=text, style="Surface.TLabel", anchor="w"
                      ).grid(row=zeile, column=0, sticky="w",
                             padx=(0, 12), pady=5)

        beschriftung(0, "App")
        self.combo_marke = ttk.Combobox(
            raster, textvariable=self.var_marke, state="readonly",
            values=[MARKEN_LABELS[m] for m in MARKEN], width=26)
        self.combo_marke.grid(row=0, column=1, sticky="w", pady=5)
        self.combo_marke.bind("<<ComboboxSelected>>", self._on_marke)

        beschriftung(1, "E-Mail")
        ttk.Entry(raster, textvariable=self.var_email).grid(
            row=1, column=1, sticky="ew", pady=5)

        beschriftung(2, "Passwort")
        ttk.Entry(raster, textvariable=self.var_password, show="•").grid(
            row=2, column=1, sticky="ew", pady=5)

        beschriftung(3, "Region")
        region_zelle = ttk.Frame(raster, style="Card.TFrame")
        region_zelle.grid(row=3, column=1, sticky="ew", pady=5)
        self.combo_region = ttk.Combobox(
            region_zelle, textvariable=self.var_region, state="readonly",
            values=[REGION_LABELS[r] for r in REGIONS], width=26)
        self.combo_region.pack(side="left")
        ttk.Checkbutton(region_zelle, text="selbst erkennen",
                        style="TCheckbutton",
                        variable=self.var_autoregion).pack(side="left", padx=(10, 0))

        ttk.Checkbutton(raster, text="Zugangsdaten im Windows-Tresor merken",
                        style="TCheckbutton", variable=self.var_remember
                        ).grid(row=4, column=1, sticky="w", pady=(8, 0))

        knoepfe = ttk.Frame(inhalt, style="Card.TFrame")
        knoepfe.pack(fill="x", pady=(14, 0))
        self.btn_login = ttk.Button(knoepfe, text="Anmelden und Roboter suchen",
                                    style="Accent.TButton", command=self._on_login)
        self.btn_login.pack(side="left")
        self.badge_login = StatusBadge(knoepfe, self.theme, "Noch nicht verbunden")
        self.badge_login.pack(side="left", padx=(12, 0))

        ttk.Label(
            inhalt,
            text=("Die Daten gehen ausschließlich an Dreame und werden im "
                  "Windows-Tresor abgelegt, nicht in einer Datei. Es gibt kein "
                  "Konto bei diesem Programm und keine Weitergabe an Dritte."),
            style="Muted.TLabel", wraplength=700, justify="left"
        ).pack(anchor="w", pady=(14, 0))

        return rahmen

    # -- Zustand 2: Roboter wählen -------------------------------------
    def _bau_roboter(self) -> ttk.Frame:
        rahmen = ttk.Frame(self.outer, style="TFrame")
        card = Card(rahmen, self.theme, "Welcher Roboter?",
                    "In deinem Konto steht mehr als ein Gerät")
        card.pack(fill="x")

        self.combo_device = ttk.Combobox(card.content, textvariable=self.var_device,
                                         state="readonly", width=52)
        self.combo_device.pack(anchor="w", pady=(4, 0))
        self.combo_device.bind("<<ComboboxSelected>>", self._on_pick_device)

        self.lbl_kein_geraet = ttk.Label(
            card.content, text="", style="Muted.TLabel",
            wraplength=700, justify="left")
        self.lbl_kein_geraet.pack(anchor="w", pady=(10, 0))
        return rahmen

    # -- Zustand 3: Originalpaket --------------------------------------
    def _bau_original(self) -> ttk.Frame:
        rahmen = ttk.Frame(self.outer, style="TFrame")
        card = Card(rahmen, self.theme, "Einen Moment",
                    "Das offizielle Sprachpaket wird geholt")
        card.pack(fill="x")

        ttk.Label(
            card.content,
            text=("Jedes eigene Paket entsteht als Kopie des offiziellen - nur so "
                  "bleibt keine Ansage auf der Strecke. Deshalb wird es einmalig "
                  "heruntergeladen und danach wiederverwendet."),
            style="Surface.TLabel", wraplength=700, justify="left"
        ).pack(anchor="w")

        self.progress_original = ttk.Progressbar(card.content, mode="determinate",
                                                 maximum=100)
        self.progress_original.pack(fill="x", pady=(14, 6))
        self.badge_original = StatusBadge(card.content, self.theme, "")
        self.badge_original.pack(anchor="w")

        self.btn_original = ttk.Button(card.content, text="Jetzt herunterladen",
                                       style="Accent.TButton",
                                       command=self._on_load_base)
        self.btn_original.pack(anchor="w", pady=(12, 0))
        return rahmen

    # -- Zustand 4: Bereit ---------------------------------------------
    def _bau_bereit(self) -> ttk.Frame:
        rahmen = ttk.Frame(self.outer, style="TFrame")

        card = Card(rahmen, self.theme, "Auf dem Roboter")
        card.pack(fill="x")

        oben = ttk.Frame(card.content, style="Card.TFrame")
        oben.pack(fill="x")

        links = ttk.Frame(oben, style="Card.TFrame")
        links.pack(side="left", fill="x", expand=True)
        self.lbl_stimme = ttk.Label(links, text="—", style="Title.TLabel")
        self.lbl_stimme.pack(anchor="w")
        self.lbl_stimme_detail = ttk.Label(links, text="", style="Muted.TLabel",
                                           wraplength=520, justify="left")
        self.lbl_stimme_detail.pack(anchor="w", pady=(2, 0))

        rechts = ttk.Frame(oben, style="Card.TFrame")
        rechts.pack(side="right")
        self.btn_abfragen = ttk.Button(rechts, text="Am Roboter abfragen",
                                       style="Small.TButton",
                                       command=self._on_query)
        self.btn_abfragen.pack(anchor="e")

        knoepfe = ttk.Frame(card.content, style="Card.TFrame")
        knoepfe.pack(fill="x", pady=(16, 0))
        ttk.Button(knoepfe, text="Andere Stimme wählen", style="Accent.TButton",
                   command=lambda: self.gehe_zu("stimme")).pack(side="left")
        # Der Rückweg passiert hier, nicht auf einer anderen Seite. Wer
        # ihn drückt, will die Stimme loswerden - und nicht erst auf
        # einer Seite voller Prüfsummen und Ports den richtigen
        # Abschnitt suchen (bis 1.3.0 genau so).
        self.btn_original_zurueck = ttk.Button(
            knoepfe, text="Originalstimme wiederherstellen",
            command=self._on_original_zurueck)
        self.btn_original_zurueck.pack(side="left", padx=(8, 0))
        self.badge_zurueck = StatusBadge(knoepfe, self.theme, "")
        self.badge_zurueck.pack(side="left", padx=(12, 0))

        self.lbl_geraet = ttk.Label(rahmen, text="", style="MutedBg.TLabel",
                                    wraplength=760, justify="left")
        self.lbl_geraet.pack(anchor="w", pady=(14, 0))
        return rahmen

    # ------------------------------------------------------------------
    def _on_original_zurueck(self) -> None:
        """Lässt den Roboter sein offizielles Paket direkt bei Dreame holen.

        Dieser PC ist dabei nicht beteiligt - deshalb klappt es auch
        dann, wenn das Aufspielen an Firewall oder Netz gescheitert ist.
        """
        if not self.state.connected:
            show_warning(self, self.theme, "Nicht verbunden",
                         "Melde dich zuerst oben an und wähle deinen Roboter.")
            return

        paket = official.find_pack(self.state.official_packs, "DE")
        if paket is None and self.state.official_packs:
            paket = self.state.official_packs[0]
        if paket is None:
            show_warning(
                self, self.theme, "Sprachliste fehlt",
                "Die Liste der offiziellen Sprachpakete ist noch nicht da.",
                "Sie kommt von Dreame, sobald der Roboter bekannt ist - "
                "einen Moment warten und erneut versuchen.")
            return

        if not messagebox.askyesno(
                "Originalstimme wiederherstellen",
                f"Der Roboter holt '{paket.label}' direkt bei Dreame und "
                f"spricht danach wieder wie ab Werk.\n\n"
                f"Dein eigenes Paket bleibt auf diesem PC erhalten - du "
                f"kannst es jederzeit wieder aufspielen.\n\nFortfahren?",
                parent=self):
            return

        cloud, geraet = self.state.cloud, self.state.device
        self.btn_original_zurueck.configure(text="Abbrechen",
                                            command=self._zurueck_abbrechen)
        self.badge_zurueck.set("Stelle wieder her ...", "muted")

        def work(task):
            return installer.restore_official(
                cloud=cloud, device=geraet, pack=paket,
                log=lambda m: _LOG.info("%s", m),
                cancelled=lambda: task.cancelled)

        def ok(ergebnis) -> None:
            # Belegt oder nur wahrscheinlich - der Unterschied zählt
            # gerade hier: Diesen Weg geht jemand, WEIL etwas nicht
            # stimmt. Ein grünes "wieder aktiv" ohne Nachweis wäre die
            # schädlichste aller Meldungen.
            gut = ergebnis.success and ergebnis.bestaetigt
            self.badge_zurueck.set(
                "Originalstimme ist wieder aktiv" if gut
                else ergebnis.message, "ok" if gut else "warn")
            if ergebnis.success:
                show_info(self, self.theme,
                          "Fertig" if gut else "Auftrag ist raus",
                          ergebnis.message,
                          ergebnis.hint or installer.NEUSTART_HINWEIS)
            else:
                show_warning(self, self.theme, "Nicht wiederhergestellt",
                             ergebnis.message, ergebnis.hint or "")
            self._on_query(still=True)

        def fail(exc: Exception) -> None:
            nachricht, hinweis = error_text(exc)
            self.badge_zurueck.set("Fehlgeschlagen", "error")
            show_error(self, self.theme, "Nicht wiederhergestellt",
                       nachricht, hinweis)

        def zum_schluss() -> None:
            self._zurueck_task = None
            self.btn_original_zurueck.configure(
                text="Originalstimme wiederherstellen", state="normal",
                command=self._on_original_zurueck)

        self._zurueck_task = run_async(self, work, on_success=ok,
                                       on_error=fail, on_finally=zum_schluss)

    def _zurueck_abbrechen(self) -> None:
        """Bricht das Wiederherstellen ab, solange es noch läuft.

        Der Auftrag selbst ist beim Roboter möglicherweise schon
        angekommen - abgebrochen wird das Warten darauf. Das steht auch
        in der Meldung, damit niemand glaubt, nichts sei passiert.
        """
        aufgabe = getattr(self, "_zurueck_task", None)
        if aufgabe is None or aufgabe.cancelled:
            return
        aufgabe.cancel()
        self.badge_zurueck.set("Wird abgebrochen ...", "warn")

    # ------------------------------------------------------------------
    def _aus_config(self) -> None:
        cfg = self.state.config
        self.var_marke.set(MARKEN_LABELS.get(cfg["account_type"],
                                             MARKEN_LABELS["dreame"]))
        self.var_email.set(cfg["email"] or "")
        gespeichert = cfg.password
        if gespeichert:
            self.var_password.set(gespeichert)
        code = cfg["region"] or REGIONS[0]
        self.var_region.set(REGION_LABELS.get(code, REGION_LABELS[REGIONS[0]]))

    def _marke_code(self) -> str:
        """Aus der Beschriftung zurück auf 'dreame'/'mova'/'trouver'."""
        gewaehlt = self.var_marke.get()
        for code, text in MARKEN_LABELS.items():
            if text == gewaehlt:
                return code
        return MARKEN[0]

    def _on_marke(self, _event=None) -> None:
        """Andere Marke: Die Regionenliste passt sich an.

        Trouver betreibt Korea und China nicht - wer sie dort wählen
        könnte, liefe in einen DNS-Fehler statt in eine Auskunft.
        """
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
        return REGIONS[0]

    # ------------------------------------------------------------------
    def _ermittle_zustand(self) -> str:
        if not (self.state.cloud and self.state.cloud.logged_in):
            return ZUSTAND_ANMELDEN
        if not self.state.device:
            return ZUSTAND_ROBOTER
        if not self.state.has_base_pack:
            return ZUSTAND_ORIGINAL
        return ZUSTAND_BEREIT

    def refresh(self) -> None:
        """Liest den Zustand ab und zeigt den passenden Rahmen."""
        zustand = self._ermittle_zustand()
        for key, rahmen in self.rahmen.items():
            if key == zustand:
                rahmen.pack(fill="x")
            else:
                rahmen.pack_forget()

        gewechselt = zustand != self._zustand
        self._zustand = zustand

        if zustand == ZUSTAND_ANMELDEN:
            self.kopf.configure(text="Willkommen")
            self.unterzeile.configure(
                text=("Zuerst die Anmeldung - ohne sie weiß die App nicht, welches "
                      "Modell dein Roboter ist, und kann ihm auch nichts schicken."))
        elif zustand == ZUSTAND_ROBOTER:
            self.kopf.configure(text="Fast geschafft")
            self.unterzeile.configure(text="Wähle den Roboter, der sprechen soll.")
            self._fuelle_geraete()
        elif zustand == ZUSTAND_ORIGINAL:
            self.kopf.configure(text="Einen Moment")
            self.unterzeile.configure(
                text=f"{self._geraetename()} gefunden. Es fehlt nur noch das "
                     f"offizielle Sprachpaket - das kommt einmalig und bleibt dann da.")
            if gewechselt and not self._laedt_original:
                spaeter(self, 400, self._on_load_base)
        else:
            self.kopf.configure(text="Start")
            self.unterzeile.configure(text="")
            self._zeige_bereit(frisch_abfragen=gewechselt)

    def _geraetename(self) -> str:
        d = self.state.device
        return d.name if d and d.name else (d.model if d else "Dein Roboter")

    # -- Roboterauswahl -------------------------------------------------
    def _fuelle_geraete(self) -> None:
        geraete = self.state.devices
        if not geraete:
            self.combo_device.configure(values=[])
            self.lbl_kein_geraet.configure(
                text=("In diesem Konto ist kein Saugroboter hinterlegt. Prüfe, ob "
                      "du dieselbe E-Mail wie in der Dreamehome-App verwendest "
                      "und ob der Roboter dort auftaucht."))
            return
        self.lbl_kein_geraet.configure(text="")
        beschriftungen = [f"{d.name or d.model}  ·  {d.model}" for d in geraete]
        self.combo_device.configure(values=beschriftungen)
        if not self.var_device.get() and beschriftungen:
            self.var_device.set(beschriftungen[0])

    def _on_pick_device(self, _event=None) -> None:
        index = self.combo_device.current()
        if index < 0 or index >= len(self.state.devices):
            return
        self.state.device = self.state.devices[index]
        cfg = self.state.config
        cfg["device_id"] = self.state.device.did
        cfg["device_model"] = self.state.device.model
        self.state.save()
        self.state.notify("device_changed")
        self.refresh()

    # -- Anmeldung ------------------------------------------------------
    def _on_login(self) -> None:
        email = self.var_email.get().strip()
        passwort = self.var_password.get()
        if not email or not passwort:
            show_warning(self, self.theme, "Angaben fehlen",
                         "Bitte E-Mail und Passwort eintragen.")
            return

        region = self._region_code()
        auto = self.var_autoregion.get()

        self.btn_login.configure(state="disabled")
        self.badge_login.set("Melde an ...", "muted")

        marke = self._marke_code()
        self.state.config["account_type"] = marke

        def work(_task):
            cloud = DreameCloud(marke)
            if auto:
                benutzt = cloud.login_autodetect(email, passwort, region)
            else:
                cloud.login(email, passwort, region)
                benutzt = region
            return cloud, benutzt, cloud.list_devices(only_vacuums=True)

        def ok(ergebnis) -> None:
            cloud, benutzt, geraete = ergebnis
            self.state.cloud = cloud
            self.state.devices = geraete

            cfg = self.state.config
            cfg["email"] = email
            cfg["region"] = benutzt
            cfg.set_password(passwort, self.var_remember.get())
            self.var_region.set(REGION_LABELS.get(benutzt, self.var_region.get()))

            # Den zuletzt benutzten Roboter gleich wieder nehmen - wer nur
            # einen hat, soll die Auswahl nie zu sehen bekommen.
            gemerkt = cfg["device_id"]
            treffer = next((d for d in geraete if d.did == gemerkt), None)
            if treffer is None and len(geraete) == 1:
                treffer = geraete[0]
            if treffer is not None:
                self.state.device = treffer
                cfg["device_id"] = treffer.did
                cfg["device_model"] = treffer.model
            self.state.save()

            self.badge_login.set(f"Angemeldet ({benutzt.upper()})", "ok")
            self.state.notify("device_changed")
            self.refresh()

        def fail(exc: Exception) -> None:
            nachricht, hinweis = error_text(exc)
            self.badge_login.set("Anmeldung fehlgeschlagen", "error")
            show_error(self, self.theme, "Anmeldung fehlgeschlagen",
                       nachricht, hinweis)

        run_async(self, work, on_success=ok, on_error=fail,
                  on_finally=lambda: self.btn_login.configure(state="normal"))

    # -- Originalpaket ---------------------------------------------------
    def _on_load_base(self) -> None:
        if self._laedt_original or not self.state.model:
            return
        self._laedt_original = True
        self.btn_original.configure(state="disabled")
        self.progress_original.configure(value=0)
        self.badge_original.set("Suche das passende Paket ...", "muted")

        modell = self.state.model

        def melde(fertig: int, gesamt: int) -> None:
            anteil = (fertig / gesamt * 100) if gesamt else 0
            to_main(self, self.progress_original.configure, {"value": anteil})

        def work(_task):
            pakete = official.fetch_catalog(modell)
            bevorzugt = self.state.config["base_language"] or "DE"
            paket = official.find_pack(pakete, bevorzugt) \
                or official.find_pack(pakete, "DE") \
                or (pakete[0] if pakete else None)
            if paket is None:
                raise RuntimeError(
                    "Für dieses Modell ist kein offizielles Sprachpaket "
                    "hinterlegt.")
            to_main(self, self.badge_original.set,
                    f"Lade {paket.label} ...", "muted")
            pfad = official.download_pack(paket, modell, progress=melde)
            to_main(self, self.badge_original.set, "Entpacke Hörproben ...", "muted")
            proben = official.extract_previews(
                pfad, preview_dir() / f"{modell}_{paket.id}")
            return pakete, paket, pfad, proben

        def ok(ergebnis) -> None:
            pakete, paket, pfad, proben = ergebnis
            self.state.official_packs = pakete
            self.state.base_pack_path = pfad
            self.state.base_pack_info = paket
            self.state.previews = proben
            self.state.config["base_language"] = paket.id
            self.state.save()
            self.badge_original.set("Fertig", "ok")
            self.state.notify("base_pack_changed")
            self.state.notify("assignments_changed")
            self.refresh()

        def fail(exc: Exception) -> None:
            nachricht, hinweis = error_text(exc)
            self.badge_original.set("Nicht geladen", "error")
            self.btn_original.configure(state="normal",
                                        text="Erneut versuchen")
            show_error(self, self.theme, "Originalpaket nicht geladen",
                       nachricht, hinweis)

        def fertig() -> None:
            self._laedt_original = False

        run_async(self, work, on_success=ok, on_error=fail, on_finally=fertig)

    # -- Bereit ----------------------------------------------------------
    def _zeige_bereit(self, frisch_abfragen: bool = False) -> None:
        name = self.state.prebuilt_name or self.state.config["last_pack_name"] or ""

        # Die Kennung stand hier früher mit dabei. Sie ist inzwischen
        # für jedes Paket dieselbe und sagt damit nichts mehr aus -
        # schlimmer noch, sie zeigte zeitweise eine Kennung an, die der
        # Roboter gar nicht führt.
        if name:
            self.lbl_stimme.configure(text=name)
            self.lbl_stimme_detail.configure(text="zuletzt von hier aufgespielt")
        else:
            self.lbl_stimme.configure(text="Deutsch")
            self.lbl_stimme_detail.configure(
                text="Noch nichts Eigenes aufgespielt - der Roboter spricht "
                     "die mitgelieferte Stimme.")

        paket = self.state.base_pack_info
        self.lbl_geraet.configure(
            text=f"{self._geraetename()} · {self.state.model} · "
                 f"{len(self.state.previews)} Ansagen bekannt"
                 + (f" · Grundlage {paket.label}" if paket else ""))

        if frisch_abfragen:
            spaeter(self, 600, lambda: self._on_query(still=True))

    def _on_query(self, still: bool = False) -> None:
        """Fragt den Roboter, welches Paket er gerade führt."""
        if not self.state.connected:
            return
        cloud, geraet = self.state.cloud, self.state.device
        self.btn_abfragen.configure(state="disabled")

        def work(_task):
            return cloud.current_voice_pack(geraet)

        def ok(aktiv) -> None:
            if not aktiv:
                if not still:
                    show_warning(
                        self, self.theme, "Keine Antwort",
                        "Der Roboter hat nicht geantwortet.",
                        "Vermutlich schläft er. Wecke ihn in der "
                        "Dreamehome-App und versuche es noch einmal.")
                return
            offiziell = {p.id: p for p in self.state.official_packs}
            treffer = offiziell.get(aktiv)
            if treffer is not None:
                self.lbl_stimme.configure(text=treffer.label)
                self.lbl_stimme_detail.configure(
                    text=f"offizielles Paket von Dreame · Kennung {aktiv}")
            else:
                name = self.state.prebuilt_name \
                    or self.state.config["last_pack_name"] or "Eigenes Paket"
                self.lbl_stimme.configure(text=name)
                self.lbl_stimme_detail.configure(
                    text=f"eigenes Paket · Kennung {aktiv} · "
                         f"in der Dreamehome-App nicht sichtbar, das ist normal")

        def fail(exc: Exception) -> None:
            if still:
                _LOG.info("Abfrage im Hintergrund fehlgeschlagen: %s", exc)
                return
            nachricht, hinweis = error_text(exc)
            show_error(self, self.theme, "Abfrage fehlgeschlagen",
                       nachricht, hinweis)

        run_async(self, work, on_success=ok, on_error=fail,
                  on_finally=lambda: self.btn_abfragen.configure(state="normal"))
