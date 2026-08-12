"""Seite 'Bauen und Aufspielen': der ausfuehrliche Weg mit allen Schaltern."""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from .. import installer, library, official, packer, server
from ..paths import build_dir
from .state import AppState, Task, error_text, run_async, to_main
from .theme import Theme
from .widgets import (Card, InfoBanner, LogView, ScrollablePage, StatusBadge,
                      labeled_value, show_error, show_info, show_warning)


APP_HINWEIS = (
    "Wichtig zur Dreamehome-App: Dein Paket taucht dort unter 'Sprachton' "
    "NICHT auf. Die App listet nur Sprachen aus Dreames eigenem Katalog, und "
    "eine selbst vergebene Kennung steht da nicht drin.\n\n"
    "Dass die App beim Öffnen meldet, Roboter und App hätten verschiedene "
    "Spracheinstellungen, ist deshalb genau das erwartete Zeichen dafür, dass "
    "dein Paket läuft.\n\n"
    "Wähle in der Dreamehome-App jetzt KEINE Sprache aus - damit würde der "
    "Roboter das offizielle Paket nachladen und deines überschreiben.\n\n"
    "Wenn dein Paket dort auftauchen soll, installiere es unter der Kennung "
    "'DE'. Dann erscheint es als 'Deutsch' und ist auswählbar - es ersetzt "
    "dafür die mitgelieferte deutsche Stimme. Zurück geht es jederzeit über "
    "'Originalstimme wiederherstellen'."
)


def open_folder(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass


class InstallTab(ttk.Frame):
    def __init__(self, master, theme: Theme, state: AppState) -> None:
        super().__init__(master, style="TFrame")
        self.theme = theme
        self.state = state
        self._task: Optional[Task] = None
        self._build()

        state.subscribe("device_changed", self.refresh_summary)
        state.subscribe("base_pack_changed", self.refresh_summary)
        state.subscribe("assignments_changed", self.refresh_summary)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        page = ScrollablePage(self, self.theme)
        page.pack(fill="both", expand=True)
        outer = page.body()

        InfoBanner(
            outer, self.theme,
            "So läuft die Installation: Die App baut das Paket, startet kurz "
            "einen kleinen Webserver auf diesem PC und schickt dem Roboter über "
            "die Dreame-Cloud den Auftrag, es dort abzuholen. Der Roboter prüft "
            "die Prüfsumme selbst - passt sie nicht, verwirft er das Paket und "
            "behält seine bisherige Stimme.\n"
            "Dein Paket erscheint danach NICHT in der Dreamehome-App unter "
            "'Sprachton' - die zeigt nur Dreames eigene Sprachen. Ob es läuft, "
            "verrät der Knopf 'Sprachpaket am Roboter abfragen'.",
        ).pack(fill="x", pady=(0, 14))

        top = ttk.Frame(outer, style="TFrame")
        top.pack(fill="x")
        top.columnconfigure(0, weight=3, uniform="cols")
        top.columnconfigure(1, weight=2, uniform="cols")

        # ---- Zusammenfassung -------------------------------------------
        summary = Card(top, self.theme, "Übersicht")
        summary.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.val_device = labeled_value(summary.content, self.theme, "Roboter")
        self.val_base = labeled_value(summary.content, self.theme, "Originalpaket")
        self.val_count = labeled_value(summary.content, self.theme, "Eigene Ansagen")
        self.val_pack = labeled_value(summary.content, self.theme, "Gebautes Paket")
        self.val_md5 = labeled_value(summary.content, self.theme, "MD5-Prüfsumme")

        self.prebuilt_row = ttk.Frame(summary.content, style="Card.TFrame")
        self.lbl_prebuilt = ttk.Label(self.prebuilt_row, text="", style="Warning.TLabel",
                                      wraplength=430, justify="left")
        self.lbl_prebuilt.pack(anchor="w")
        ttk.Button(self.prebuilt_row, text="Stattdessen mein eigenes Paket bauen",
                   style="Small.TButton",
                   command=self._clear_prebuilt).pack(anchor="w", pady=(6, 0))

        # ---- Gespeicherte Pakete ---------------------------------------
        # Wer mehrere Fassungen desselben Dialekts gebaut hat - eine mit der
        # bezahlten ElevenLabs-Stimme, eine zum Ausprobieren mit Windows -
        # muss hier sehen und wählen können, welche installiert wird.
        self.pack_row = ttk.Frame(summary.content, style="Card.TFrame")
        self.pack_row.pack(fill="x", pady=(12, 0))
        ttk.Label(self.pack_row, text="Gespeicherte Pakete",
                  style="Surface.TLabel").pack(anchor="w")
        self.var_saved = tk.StringVar()
        self.combo_saved = ttk.Combobox(self.pack_row, textvariable=self.var_saved,
                                        state="readonly", width=52)
        self.combo_saved.pack(fill="x", pady=(4, 0))
        self.combo_saved.bind("<<ComboboxSelected>>", self._on_pick_saved)
        self.lbl_saved = ttk.Label(self.pack_row, text="", style="Muted.TLabel",
                                   wraplength=430, justify="left")
        self.lbl_saved.pack(anchor="w", pady=(4, 0))
        self._saved: list = []

        # ---- Einstellungen ---------------------------------------------
        settings = Card(top, self.theme, "Einstellungen")
        settings.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        body = settings.content
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Kennung", style="Surface.TLabel").grid(
            row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_lang = tk.StringVar(value=self.state.config["custom_lang_id"])
        ttk.Entry(body, textvariable=self.var_lang, width=12).grid(
            row=0, column=1, sticky="w", pady=4)

        ttk.Label(body, text="PC-Adresse", style="Surface.TLabel").grid(
            row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_ip = tk.StringVar(value=self.state.config["host_ip"])
        self.combo_ip = ttk.Combobox(body, textvariable=self.var_ip, width=18,
                                     values=server.candidate_ips())
        self.combo_ip.grid(row=1, column=1, sticky="w", pady=4)
        if not self.var_ip.get():
            ips = server.candidate_ips()
            if ips:
                self.var_ip.set(ips[0])

        ttk.Label(body, text="Port", style="Surface.TLabel").grid(
            row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        self.var_port = tk.StringVar(value=str(self.state.config["serve_port"] or ""))
        ttk.Entry(body, textvariable=self.var_port, width=10).grid(
            row=2, column=1, sticky="w", pady=4)
        ttk.Label(body, text="leer = automatisch", style="Muted.TLabel").grid(
            row=3, column=1, sticky="w")

        ttk.Label(body, text="Eigene URL", style="Surface.TLabel").grid(
            row=4, column=0, sticky="w", pady=(10, 4), padx=(0, 8))
        self.var_url = tk.StringVar()
        ttk.Entry(body, textvariable=self.var_url).grid(
            row=4, column=1, sticky="ew", pady=(10, 4))
        ttk.Label(body,
                  text=("nur nötig, wenn der Roboter diesen PC nicht "
                        "erreicht (dann Paket selbst hochladen)"),
                  style="Muted.TLabel", wraplength=230,
                  justify="left").grid(row=5, column=1, sticky="w")

        # ---- Aktionen ---------------------------------------------------
        actions = Card(outer, self.theme, "Schritt 3: Auf den Roboter übertragen")
        actions.pack(fill="x", pady=(14, 0))

        button_row = ttk.Frame(actions.content, style="Card.TFrame")
        button_row.pack(fill="x")

        self.btn_install = ttk.Button(
            button_row, text="Sprachpaket auf Roboter installieren",
            style="Big.TButton", command=self._on_install)
        self.btn_install.pack(side="left")

        self.btn_build_only = ttk.Button(
            button_row, text="Nur bauen", command=self._on_build_only)
        self.btn_build_only.pack(side="left", padx=(10, 0))

        self.btn_cancel = ttk.Button(button_row, text="Abbrechen",
                                     command=self._on_cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=(10, 0))

        ttk.Button(button_row, text="Paketordner öffnen", style="Small.TButton",
                   command=lambda: open_folder(build_dir())).pack(side="right")
        # Bewusst "Gebautes Paket": unter 'Eigene Stimmen' gibt es einen Knopf zum Einlesen
        # von Aufnahmen, und "Fertiges Paket" hat für beides gepasst.
        ttk.Button(button_row, text="Gebautes Paket (.tar.gz) wählen ...",
                   style="Small.TButton",
                   command=self._on_pick_pack).pack(side="right", padx=(0, 8))

        self.progress = ttk.Progressbar(actions.content, mode="determinate",
                                        maximum=100)
        self.progress.pack(fill="x", pady=(14, 6))

        status_row = ttk.Frame(actions.content, style="Card.TFrame")
        status_row.pack(fill="x")
        self.badge = StatusBadge(status_row, self.theme, "Bereit")
        self.badge.pack(side="left")
        self.btn_status = ttk.Button(
            status_row, text="Sprachpaket am Roboter abfragen",
            style="Small.TButton", command=self._on_query_status)
        self.btn_status.pack(side="right")

        self.log = LogView(actions.content, self.theme, height=13)
        self.log.pack(fill="both", expand=True, pady=(12, 0))

        # ---- Wiederherstellen -------------------------------------------
        restore = Card(outer, self.theme, "Notausgang: Originalstimme zurückholen",
                       "Installiert das offizielle Dreame-Sprachpaket erneut - der "
                       "Roboter lädt es direkt beim Hersteller, dieser PC ist "
                       "dabei gar nicht beteiligt.")
        restore.pack(fill="x", pady=(14, 0))

        restore_row = ttk.Frame(restore.content, style="Card.TFrame")
        restore_row.pack(fill="x")
        ttk.Label(restore_row, text="Sprache", style="Surface.TLabel").pack(
            side="left", padx=(0, 10))
        self.var_restore = tk.StringVar()
        self.combo_restore = ttk.Combobox(restore_row, textvariable=self.var_restore,
                                          state="readonly", width=34, values=[])
        self.combo_restore.pack(side="left")
        self.btn_restore = ttk.Button(restore_row, text="Originalstimme wiederherstellen",
                                      command=self._on_restore)
        self.btn_restore.pack(side="left", padx=(12, 0))

        self.refresh_summary()

    # ------------------------------------------------------------------
    def refresh_saved_packs(self) -> None:
        """Liest die gebauten Pakete neu ein und füllt die Auswahl."""
        try:
            self._saved = library.list_packs()
        except OSError:
            self._saved = []

        beschriftungen = [i.label for i in self._saved]
        self.combo_saved.configure(values=beschriftungen)

        if not self._saved:
            self.var_saved.set("")
            self.lbl_saved.configure(
                text=("Noch keine Pakete gebaut. Unter 'Eigene Stimmen' entsteht ein "
                      "Dialektpaket, unter 'Einzelne Ansagen' ein eigenes."))
            self.combo_saved.configure(state="disabled")
            return

        self.combo_saved.configure(state="readonly")
        aktuell = self.state.last_build
        if aktuell is not None:
            for i, info in enumerate(self._saved):
                if info.path == aktuell.path:
                    self.var_saved.set(beschriftungen[i])
                    break
        self.lbl_saved.configure(
            text=(f"{len(self._saved)} gespeicherte Pakete. Jede Stimme liegt "
                  f"in einer eigenen Datei - eine neue Fassung überschreibt "
                  f"nie eine ältere."))

    def _on_pick_saved(self, _event=None) -> None:
        """Ein gespeichertes Paket zum Installieren auswählen."""
        wahl = self.var_saved.get()
        info = next((i for i in self._saved if i.label == wahl), None)
        if info is None:
            return

        try:
            build = packer.load_existing(info.path)
        except Exception as exc:                       # noqa: BLE001
            self._on_error(exc)
            return

        self.state.prebuilt = build
        self.state.prebuilt_name = info.dialect or info.path.name
        self.state.last_build = build
        if info.lang_id:
            self.var_lang.set(info.lang_id)
        self.refresh_summary()
        self.log.append(f"Ausgewählt: {info.path.name}", "ok")
        if info.voice:
            self.log.append(f"Stimme: {info.voice}", "muted")

    def refresh_summary(self) -> None:
        self.refresh_saved_packs()
        device = self.state.device
        self.val_device.configure(
            text=f"{device.name} ({device.model})" if device else "nicht ausgewählt")

        if self.state.base_pack_info and self.state.has_base_pack:
            info = self.state.base_pack_info
            self.val_base.configure(
                text=f"{info.label} - {info.size / (1024 * 1024):.1f} MB")
        else:
            self.val_base.configure(text="noch nicht geladen")

        assigned = len(self.state.assignments())
        missing = len(self.state.missing_assignments())
        text = str(assigned)
        if missing:
            text += f"  ({missing} Datei(en) fehlen!)"
        self.val_count.configure(text=text)

        build = self.state.last_build
        if build:
            self.val_pack.configure(
                text=f"{build.path.name} - {build.size_mb:.1f} MB")
            self.val_md5.configure(text=build.md5)
        else:
            self.val_pack.configure(text="noch nicht gebaut")
            self.val_md5.configure(text="-")

        if self.state.prebuilt is not None:
            self.lbl_prebuilt.configure(
                text=(f"Fertiges Paket '{self.state.prebuilt_name}' liegt bereit und "
                      f"wird installiert. Deine eigenen Zuweisungen bleiben "
                      f"gespeichert, werden aber gerade nicht verwendet."))
            self.prebuilt_row.pack(fill="x", pady=(10, 0))
        else:
            self.prebuilt_row.pack_forget()

        packs = self.state.official_packs
        labels = [p.label for p in packs]
        if list(self.combo_restore.cget("values")) != labels:
            self.combo_restore.configure(values=labels)
            match = official.find_pack(packs, "DE")
            if match:
                self.var_restore.set(match.label)
            elif labels:
                self.var_restore.set(labels[0])

    # ------------------------------------------------------------------
    def _on_query_status(self) -> None:
        """Fragt den Roboter, welches Sprachpaket er gerade benutzt.

        Die Dreamehome-App kann eigene Pakete nicht anzeigen - hier kommt
        die Antwort direkt vom Roboter.
        """
        if not self.state.connected:
            show_warning(self, self.theme, "Kein Roboter ausgewählt",
                         "Melde dich zuerst unter 'Verbindung' an.")
            return

        cloud, device = self.state.cloud, self.state.device
        self.btn_status.configure(state="disabled")
        self.badge.set("Frage den Roboter ...", "muted")

        def work(_task):
            return (cloud.current_voice_pack(device),
                    cloud.voice_change_status(device))

        def ok(antwort) -> None:
            aktiv, zustand = antwort
            self.log.append(f"Aktives Sprachpaket laut Roboter: {aktiv or 'unbekannt'}",
                            "ok" if aktiv else "warn")
            if zustand:
                self.log.append(f"Zustand: {zustand}", "info")

            offiziell = {p.id for p in self.state.official_packs}
            if not aktiv:
                self.badge.set("Keine Antwort - Roboter im Standby?", "warn")
                show_warning(
                    self, self.theme, "Keine Antwort",
                    "Der Roboter hat nicht geantwortet.",
                    "Wecke ihn in der Dreamehome-App auf und versuche es erneut.")
                return

            self.badge.set(f"Aktiv: {aktiv}", "ok")
            if str(aktiv).upper() in offiziell:
                show_info(
                    self, self.theme, "Offizielles Paket aktiv",
                    f"Der Roboter benutzt gerade '{aktiv}' - ein Paket von Dreame.",
                    "Dein eigenes Paket ist damit nicht aktiv. Das passiert, "
                    "wenn in der Dreamehome-App eine Sprache ausgewählt wurde: "
                    "der Roboter lädt sie dann nach und überschreibt das eigene "
                    "Paket. Installiere es einfach erneut.")
            else:
                show_info(
                    self, self.theme, "Dein Paket ist aktiv",
                    f"Der Roboter benutzt gerade '{aktiv}' - das ist deine "
                    f"eigene Kennung, kein Paket von Dreame.",
                    APP_HINWEIS)

        def fail(exc: Exception) -> None:
            message, hint = error_text(exc)
            self.badge.set("Abfrage fehlgeschlagen", "error")
            show_error(self, self.theme, "Abfrage fehlgeschlagen", message, hint)

        run_async(self, work, on_success=ok, on_error=fail,
                  on_finally=lambda: self.btn_status.configure(state="normal"))

    def _on_pick_pack(self) -> None:
        """Ein bereits gebautes Sprachpaket von der Festplatte übernehmen."""
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Gebautes Sprachpaket wählen (.tar.gz)",
            initialdir=str(build_dir()),
            filetypes=[("Gebautes Sprachpaket", "*.tar.gz *.tgz"),
                       ("Alle Dateien", "*.*")],
        )
        if not chosen:
            return

        # Die Aufnahmen-Archive aus dem Projekt sind ZIPs und gehören nach
        # 'Eigene Stimmen' - hier würden sie nur mit einer Formatmeldung scheitern.
        if Path(chosen).suffix.lower() == ".zip":
            show_warning(
                self, self.theme, "Das sind Aufnahmen, kein fertiges Paket",
                f"{Path(chosen).name} enthält einzelne Sprachdateien. Hier "
                f"wird ein bereits gebautes Paket erwartet - eine "
                f".tar.gz-Datei.",
                "So kommst du weiter: Sind es die Aufnahmen von der"
                " Projektseite, stehen sie ohnehin schon bereit."
                " Nimm dafür in der Leiste 'Fertige Stimmen'"
                " - dort aussuchen, anhören, aufspielen.\n\n"
                "Sind es eigene Aufnahmen, nimm 'Eigene Stimmen' und klicke"
                " dort 'Aufnahmen einlesen ...'. Die App baut daraus das"
                " Paket für dein Modell; danach steht es auch hier zur"
                " Auswahl. Entpacken musst du nichts.")
            return

        try:
            build = packer.load_existing(Path(chosen))
        except Exception as exc:
            self._on_error(exc)
            return

        self.state.prebuilt = build
        self.state.prebuilt_name = Path(chosen).name
        self.state.last_build = build
        self.refresh_summary()

        self.log.clear()
        self.log.append(f"Übernommen: {build.path.name}", "ok")
        self.log.append(f"{len(build.replaced)} Ansagen, {build.size_mb:.1f} MB, "
                        f"MD5 {build.md5}", "info")
        for warning in build.warnings:
            self.log.append(warning, "warn")
        self.badge.set("Paket übernommen - bereit zur Installation", "ok")

    def _clear_prebuilt(self) -> None:
        self.state.prebuilt = None
        self.state.prebuilt_name = ""
        self.state.last_build = None
        self.refresh_summary()

    def _busy(self, active: bool) -> None:
        state = "disabled" if active else "normal"
        self.btn_install.configure(state=state)
        self.btn_build_only.configure(state=state)
        self.btn_restore.configure(state=state)
        self.btn_cancel.configure(state="normal" if active else "disabled")

    def _log(self, message: str, kind: str = "info") -> None:
        to_main(self, self.log.append, message, kind)

    def _step(self, message: str, fraction: float) -> None:
        def apply() -> None:
            self.progress.configure(value=max(0.0, min(1.0, fraction)) * 100)
            self.badge.set(message, "muted")
        to_main(self, apply)

    def _on_cancel(self) -> None:
        if self._task:
            self._task.cancel()
            self.log.append("Abbruch angefordert ...", "warn")

    # ------------------------------------------------------------------
    def _preflight(self, need_device: bool = True) -> bool:
        if need_device and not self.state.connected:
            messagebox.showwarning(
                "Kein Roboter ausgewählt",
                "Melde dich unter 'Verbindung' an und wähle deinen Roboter aus.",
                parent=self)
            return False

        if not self.state.has_base_pack:
            messagebox.showwarning(
                "Originalpaket fehlt",
                "Lade unter 'Einzelne Ansagen' zuerst das offizielle "
                "Sprachpaket deines Roboters herunter. Es ist die Grundlage "
                "deines eigenen Pakets.",
                parent=self)
            return False

        if self.state.prebuilt is not None:
            # Fertiges Community-Paket - es muss nichts gebaut werden.
            return True

        if not self.state.assignments():
            messagebox.showwarning(
                "Nichts zu tun",
                "Es ist noch keine einzige Ansage ausgetauscht. Weise im Tab "
                "'Sprachpaket erstellen' mindestens einer Ansage eine Audiodatei zu "
                "- oder hole dir unter 'Eigene Stimmen' ein vorgefertigtes Paket.",
                parent=self)
            return False

        missing = self.state.missing_assignments()
        if missing:
            preview = "\n".join(f"  Ansage {i}: {p}" for i, p in missing[:6])
            more = f"\n  ... und {len(missing) - 6} weitere" if len(missing) > 6 else ""
            if not messagebox.askyesno(
                    "Dateien fehlen",
                    f"{len(missing)} zugewiesene Datei(en) existieren nicht mehr:\n\n"
                    f"{preview}{more}\n\nDiese Ansagen bleiben auf der Originalstimme. "
                    f"Trotzdem fortfahren?",
                    parent=self):
                return False
        return True

    def _build_pack(self, task: Task):
        prebuilt = self.state.prebuilt
        if prebuilt is not None and prebuilt.path.is_file():
            self._log(f"Verwende das vorbereitete Paket '{self.state.prebuilt_name}'.",
                      "info")
            self._log("Es wurde bereits auf dein Modell angepasst - es muss nichts "
                      "neu gebaut werden.", "info")
            return prebuilt

        return packer.build_pack(
            base_pack=self.state.base_pack_path,
            assignments=self.state.assignments(),
            out_name="mein_sprachpaket.tar.gz",
            ffmpeg=self.state.ffmpeg,
            mapping=self.state.voice_mapping(),
            log=lambda m: self._log(m),
            progress=lambda done, total: self._step(
                "Baue Paket", 0.05 + 0.35 * (done / total if total else 0)),
        )

    # ------------------------------------------------------------------
    def _on_build_only(self) -> None:
        if not self._preflight(need_device=False):
            return

        self.log.clear()
        self.log.append("Baue Paket (ohne Installation) ...", "step")
        self._busy(True)
        self.progress.configure(value=0)

        def work(task):
            return self._build_pack(task)

        def ok(build):
            self.state.last_build = build
            self.refresh_summary()
            self.progress.configure(value=100)
            self.badge.set("Paket gebaut", "ok")
            self.log.append(build.summary(), "ok")
            for warning in build.warnings:
                self.log.append(warning, "warn")
            self.log.append(f"Gespeichert unter: {build.path}", "info")

        run_async(self, work, on_success=ok, on_error=self._on_error,
                  on_finally=lambda: self._busy(False))

    def _on_install(self) -> None:
        if not self._preflight():
            return

        lang_id = self.var_lang.get().strip().upper() or "CUSTOM"
        try:
            lang_id, warning = installer.validate_lang_id(lang_id)
        except Exception as exc:
            self._on_error(exc)
            return

        if warning and not messagebox.askyesno(
                "Offizielle Kennung", warning + "\n\nTrotzdem fortfahren?",
                parent=self):
            return

        try:
            port = int(self.var_port.get().strip() or 0)
        except ValueError:
            messagebox.showwarning("Ungültiger Port",
                                   "Der Port muss eine Zahl sein (oder leer bleiben).",
                                   parent=self)
            return

        self.state.config["custom_lang_id"] = lang_id
        self.state.config["host_ip"] = self.var_ip.get().strip()
        self.state.config["serve_port"] = port
        self.state.save()
        self.var_lang.set(lang_id)

        cloud, device = self.state.cloud, self.state.device
        public_url = self.var_url.get().strip()
        host_ip = self.var_ip.get().strip()

        self.log.clear()
        self.log.append("Starte Installation", "step")
        self._busy(True)
        self.progress.configure(value=0)

        def work(task):
            build = self._build_pack(task)
            self.state.last_build = build
            to_main(self, self.refresh_summary)
            for warning_text in build.warnings:
                self._log(warning_text, "warn")

            self._log("", "info")
            self._log("Übertrage auf den Roboter", "step")
            return installer.install_pack(
                cloud=cloud, device=device, build=build, lang_id=lang_id,
                port=port, host_ip=host_ip, public_url=public_url,
                log=lambda m: self._log(m),
                step=self._step,
                cancelled=lambda: task.cancelled,
            )

        def ok(outcome: installer.InstallOutcome) -> None:
            if outcome.success:
                self.progress.configure(value=100)
                self.badge.set("Erfolgreich installiert", "ok")
                self.log.append(outcome.message, "ok")
                self.log.append(APP_HINWEIS, "warn")
                show_info(
                    self, self.theme, "Fertig",
                    outcome.message + "\n\nProbier es aus: lass den Roboter eine "
                    "Reinigung starten - er sollte jetzt anders klingen.",
                    APP_HINWEIS)
            else:
                self.badge.set(outcome.message, "error")
                self.log.append(outcome.message, "error")
                if outcome.hint:
                    self.log.append(outcome.hint, "warn")
                messagebox.showwarning(
                    "Nicht abgeschlossen",
                    outcome.message + (f"\n\n{outcome.hint}" if outcome.hint else ""),
                    parent=self)

        self._task = run_async(self, work, on_success=ok, on_error=self._on_error,
                               on_finally=self._install_done)

    def _install_done(self) -> None:
        self._busy(False)
        self._task = None

    # ------------------------------------------------------------------
    def _on_restore(self) -> None:
        if not self.state.connected:
            messagebox.showwarning("Kein Roboter ausgewählt",
                                   "Melde dich zuerst unter 'Verbindung' an.",
                                   parent=self)
            return

        pack = next((p for p in self.state.official_packs
                     if p.label == self.var_restore.get()), None)
        if pack is None:
            messagebox.showwarning("Keine Sprache gewählt",
                                   "Bitte wähle das wiederherzustellende Paket aus.",
                                   parent=self)
            return

        if not messagebox.askyesno(
                "Originalstimme wiederherstellen",
                f"Der Roboter lädt '{pack.label}' direkt von Dreame und stellt "
                f"damit die Originalstimme wieder her.\n\nFortfahren?",
                parent=self):
            return

        cloud, device = self.state.cloud, self.state.device
        self.log.clear()
        self.log.append("Stelle Originalstimme wieder her", "step")
        self._busy(True)
        self.progress.configure(value=0)

        def work(_task):
            return installer.restore_official(
                cloud=cloud, device=device, pack=pack,
                log=lambda m: self._log(m), step=self._step)

        def ok(outcome: installer.InstallOutcome) -> None:
            kind = "ok" if outcome.success else "warn"
            self.badge.set(outcome.message, kind if outcome.success else "warn")
            self.log.append(outcome.message, kind)
            if outcome.hint:
                self.log.append(outcome.hint, "warn")
            self.progress.configure(value=100 if outcome.success else 0)

        run_async(self, work, on_success=ok, on_error=self._on_error,
                  on_finally=lambda: self._busy(False))

    # ------------------------------------------------------------------
    def _on_error(self, exc: Exception) -> None:
        message, hint = error_text(exc)
        self.badge.set("Fehlgeschlagen", "error")
        self.log.append(message, "error")
        if hint:
            self.log.append(hint, "warn")
        show_error(self, self.theme, "Fehler",
                       message + (f"\n\n{hint}" if hint else ""))
