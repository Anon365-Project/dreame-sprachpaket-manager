"""Tab 2: Originalpaket laden und eigene Ansagen zuweisen."""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from .. import audio, embedded, ffmpeg_setup, importer, official
from ..errors import DreameError
from ..paths import data_dir, preview_dir
from ..sounds import Sound
from .state import AppState, error_text, run_async, to_main
from .theme import Theme
from .widgets import (Card, InfoBanner, ScrollablePage, StatusBadge, show_error,
                      show_info, show_warning)


def open_folder(path: Path) -> None:
    """Öffnet einen Ordner im Explorer."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass

AUDIO_FILETYPES = [
    ("Audiodateien", "*.ogg *.wav *.mp3 *.m4a *.flac *.aac *.opus *.wma"),
    ("OGG Vorbis (bereits passend)", "*.ogg"),
    ("WAV", "*.wav"),
    ("MP3", "*.mp3"),
    ("Alle Dateien", "*.*"),
]

PAGE_SIZE = 100


def open_with_default_player(path: Path) -> None:
    """Spielt eine Datei mit dem Standardprogramm des Systems ab."""
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 - gewollt: Standardplayer des Nutzers
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class SoundRow(ttk.Frame):
    """Eine Zeile: Nummer, Beschreibung, Hörprobe, Dateiwahl."""

    def __init__(self, master, theme: Theme, tab: "BuilderTab", sound: Sound) -> None:
        super().__init__(master, style="Card.TFrame")
        self.theme = theme
        self.tab = tab
        self.sound = sound

        self.columnconfigure(1, weight=1)

        # Nummer
        num = ttk.Label(self, text=str(sound.id), style="Mono.TLabel",
                        width=5, anchor="e")
        num.grid(row=0, column=0, rowspan=2, sticky="ne", padx=(0, 10), pady=(4, 0))

        # Beschreibung
        title = ttk.Label(self, text=sound.title, style="Surface.TLabel",
                          anchor="w", wraplength=430, justify="left")
        title.grid(row=0, column=1, sticky="ew")

        sub_parts = [sound.group]
        if sound.de and sound.en:
            sub_parts.append(f"Original (EN): {sound.en}")
        elif not sound.de and not sound.en:
            sub_parts.append("keine Beschreibung bekannt - bitte anhören")
        subtitle = ttk.Label(self, text="  ·  ".join(sub_parts), style="Muted.TLabel",
                             anchor="w", wraplength=430, justify="left")
        subtitle.grid(row=1, column=1, sticky="ew", pady=(1, 0))

        # Bedienelemente
        controls = ttk.Frame(self, style="Card.TFrame")
        controls.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))

        self.btn_preview = ttk.Button(controls, text="Original anhören",
                                      style="Small.TButton",
                                      command=self._play_original)
        self.btn_preview.pack(side="left", padx=(0, 6))

        self.var_path = tk.StringVar(value=tab.state.config.assignment(sound.id))
        self.entry = ttk.Entry(controls, textvariable=self.var_path, width=34)
        self.entry.pack(side="left", padx=(0, 6))
        self.entry.bind("<FocusOut>", lambda _e: self._store())

        ttk.Button(controls, text="Durchsuchen ...", style="Small.TButton",
                   command=self._browse).pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="✕", style="Small.TButton", width=3,
                   command=self._clear).pack(side="left")

        self.hint = ttk.Label(self, text="", style="Muted.TLabel",
                              wraplength=760, justify="left")
        self.hint.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(2, 0))

        ttk.Frame(self, style="Separator.TFrame", height=1).grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=(8, 8))

        self._update_preview_state()
        self._update_hint()

    # ------------------------------------------------------------------
    def _update_preview_state(self) -> None:
        available = self.sound.id in self.tab.state.previews
        self.btn_preview.configure(state="normal" if available else "disabled")
        if not available:
            self.btn_preview.configure(text="Original anhören")

    def _play_original(self) -> None:
        path = self.tab.state.previews.get(self.sound.id)
        if not path or not path.is_file():
            messagebox.showinfo(
                "Keine Hörprobe",
                "Lade zuerst oben das offizielle Sprachpaket deines Roboters "
                "herunter - daraus stammen die Hörproben.",
                parent=self)
            return
        try:
            open_with_default_player(path)
        except OSError as exc:
            show_error(self, self.theme, "Wiedergabe nicht möglich",
                       f"Die Datei konnte nicht abgespielt werden.\n\n{path}\n\n{exc}")

    def _browse(self) -> None:
        initial = (self.tab.state.config["last_audio_dir"]
                   or str(Path.home() / "Music"))
        # Der vorgeschlagene Name ist genau der, den der Ordner-Import
        # später erwartet - so passt beides zusammen.
        chosen = filedialog.askopenfilename(
            parent=self,
            title=(f"Audiodatei für Ansage {self.sound.id} - {self.sound.title}"
                   f"   (erwarteter Name: {importer.suggested_filename(self.sound.id)})"),
            initialdir=initial if Path(initial).is_dir() else str(Path.home()),
            initialfile=importer.suggested_filename(self.sound.id),
            filetypes=AUDIO_FILETYPES,
        )
        if not chosen:
            return
        self.var_path.set(chosen)
        self.tab.state.config["last_audio_dir"] = str(Path(chosen).parent)
        self._store()

    def _clear(self) -> None:
        self.var_path.set("")
        self._store()

    def _store(self) -> None:
        value = self.var_path.get().strip().strip('"')
        self.var_path.set(value)
        self.tab.state.config.set_assignment(self.sound.id, value)
        # Sobald der Nutzer selbst etwas zuweist, gilt wieder sein eigenes Paket.
        self.tab.state.prebuilt = None
        self.tab.state.prebuilt_name = ""
        self.tab.state.save()
        self._update_hint()
        self.tab.refresh_counter()

    def _update_hint(self) -> None:
        value = self.var_path.get().strip()
        if not value:
            self.hint.configure(text="", style="Muted.TLabel")
            return

        path = Path(value)
        if not path.is_file():
            self.hint.configure(text="Diese Datei existiert nicht (mehr).",
                                style="Danger.TLabel")
            return

        warning = audio.check_input_file(path)
        if warning:
            self.hint.configure(text=warning, style="Warning.TLabel")
        else:
            size_kb = path.stat().st_size // 1024
            self.hint.configure(text=f"Bereit: {path.name} ({size_kb} KB)",
                                style="Success.TLabel")

    def refresh(self) -> None:
        self.var_path.set(self.tab.state.config.assignment(self.sound.id))
        self._update_preview_state()
        self._update_hint()


class BuilderTab(ttk.Frame):
    def __init__(self, master, theme: Theme, state: AppState) -> None:
        super().__init__(master, style="TFrame")
        self.theme = theme
        self.state = state
        self._rows: List[SoundRow] = []
        self._shown = PAGE_SIZE
        self._ffmpeg_busy = False
        self._build()
        state.subscribe("device_changed", self._on_device_changed)
        state.subscribe("base_pack_changed", self.rebuild_list)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.page = ScrollablePage(self, self.theme)
        self.page.pack(fill="both", expand=True)
        outer = self.page.body()

        InfoBanner(
            outer, self.theme,
            "Dein Paket entsteht als Kopie des offiziellen Sprachpakets deines "
            "Roboters - ausgetauscht wird nur, was du selbst zuweist. Alles andere "
            "bleibt auf der originalen deutschen Stimme. Deshalb ist der erste "
            "Schritt immer das Laden des Originalpakets.",
        ).pack(fill="x", pady=(0, 14))

        # ---- Basis -----------------------------------------------------
        base = Card(outer, self.theme, "Schritt 1: Originalpaket laden",
                    "Grundlage und zugleich Sicherheitsnetz - daraus kommen auch "
                    "die Hörproben.")
        base.pack(fill="x")

        row = ttk.Frame(base.content, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Sprache", style="Surface.TLabel").pack(side="left",
                                                                    padx=(0, 10))
        self.var_language = tk.StringVar(value="Deutsch (DE)")
        self.combo_language = ttk.Combobox(row, textvariable=self.var_language,
                                           state="readonly", width=34, values=[])
        self.combo_language.pack(side="left")

        self.btn_load_base = ttk.Button(row, text="Originalpaket herunterladen",
                                        style="Accent.TButton",
                                        command=self._on_load_base)
        self.btn_load_base.pack(side="left", padx=(12, 0))

        self.base_badge = StatusBadge(row, self.theme, "Noch nicht geladen")
        self.base_badge.pack(side="left", padx=(14, 0))

        self.base_progress = ttk.Progressbar(base.content, mode="determinate",
                                             maximum=100)

        # ---- ffmpeg ----------------------------------------------------
        self.ffmpeg_banner = ttk.Frame(base.content, style="Card.TFrame")
        self.ffmpeg_banner.pack(fill="x", pady=(12, 0))
        self.lbl_ffmpeg = ttk.Label(self.ffmpeg_banner, text="", style="Muted.TLabel",
                                    wraplength=820, justify="left")
        self.lbl_ffmpeg.pack(anchor="w")

        ffmpeg_actions = ttk.Frame(self.ffmpeg_banner, style="Card.TFrame")
        ffmpeg_actions.pack(anchor="w", pady=(6, 0))
        self.btn_ffmpeg = ttk.Button(ffmpeg_actions, text="ffmpeg automatisch einrichten",
                                     style="Small.TButton", command=self._on_setup_ffmpeg)
        self.ffmpeg_progress = ttk.Progressbar(ffmpeg_actions, mode="determinate",
                                               maximum=100, length=200)
        self._check_ffmpeg()

        # ---- Zuweisungen ------------------------------------------------
        assign = Card(outer, self.theme, "Schritt 2: Ansagen austauschen",
                      "Wähle je Ansage eine eigene Audiodatei. Formate wie mp3 "
                      "oder wav werden beim Bauen automatisch umgewandelt.")
        assign.pack(fill="both", expand=True, pady=(14, 0))

        filters = ttk.Frame(assign.content, style="Card.TFrame")
        filters.pack(fill="x", pady=(0, 10))

        ttk.Label(filters, text="Suche", style="Surface.TLabel").pack(side="left")
        self.var_search = tk.StringVar()
        search_entry = ttk.Entry(filters, textvariable=self.var_search, width=26)
        search_entry.pack(side="left", padx=(8, 16))
        search_entry.bind("<KeyRelease>", lambda _e: self._debounced_rebuild())

        ttk.Label(filters, text="Bereich", style="Surface.TLabel").pack(side="left")
        self.var_group = tk.StringVar(value="Alle Bereiche")
        self.combo_group = ttk.Combobox(filters, textvariable=self.var_group,
                                        state="readonly", width=20,
                                        values=["Alle Bereiche"])
        self.combo_group.pack(side="left", padx=(8, 16))
        self.combo_group.bind("<<ComboboxSelected>>", lambda _e: self.rebuild_list())

        self.var_common = tk.BooleanVar(value=True)
        ttk.Checkbutton(filters, text="nur die wichtigsten",
                        variable=self.var_common,
                        command=self.rebuild_list).pack(side="left", padx=(0, 12))

        self.var_assigned = tk.BooleanVar(value=False)
        ttk.Checkbutton(filters, text="nur bereits zugewiesene",
                        variable=self.var_assigned,
                        command=self.rebuild_list).pack(side="left")

        ttk.Button(filters, text="Alle Zuweisungen löschen", style="Small.TButton",
                   command=self._clear_all).pack(side="right")

        # ---- Massenzuweisung ---------------------------------------------
        bulk = ttk.Frame(assign.content, style="Card.TFrame")
        bulk.pack(fill="x", pady=(0, 10))

        ttk.Button(bulk, text="Ganzen Ordner importieren ...",
                   style="Accent.TButton",
                   command=self._on_import_folder).pack(side="left")
        ttk.Button(bulk, text="Aus Archiv importieren ...",
                   style="Small.TButton",
                   command=self._on_import_archive).pack(side="left", padx=(8, 0))
        ttk.Button(bulk, text="Vorlagenordner anlegen ...",
                   style="Small.TButton",
                   command=self._on_create_template).pack(side="left", padx=(8, 0))

        self.lbl_bulk = ttk.Label(
            bulk,
            text=("Die Zahl im Dateinamen ist die Ansage-Nummer: 7.ogg, 007.wav "
                  "oder '7 - Reinigung.mp3' landen alle bei Ansage 7."),
            style="Muted.TLabel", wraplength=420, justify="left")
        self.lbl_bulk.pack(side="left", padx=(14, 0))

        # Kein eigener Scrollbereich mehr: der ganze Tab scrollt. Zwei
        # ineinander liegende Bildlaufbereiche wären mit dem Mausrad kaum
        # zu bedienen.
        self.rows_frame = ttk.Frame(assign.content, style="Card.TFrame")
        self.rows_frame.pack(fill="both", expand=True)

        footer = ttk.Frame(assign.content, style="Card.TFrame")
        footer.pack(fill="x", pady=(10, 0))
        self.lbl_counter = ttk.Label(footer, text="", style="Muted.TLabel")
        self.lbl_counter.pack(side="left")
        self.btn_more = ttk.Button(footer, text="Weitere anzeigen",
                                   style="Small.TButton", command=self._show_more)

        self._search_job: Optional[str] = None
        self.rebuild_list()

    # ------------------------------------------------------------------
    def _check_ffmpeg(self, auto_extract: bool = True) -> None:
        found = audio.find_ffmpeg()
        self.state.ffmpeg = found

        if found:
            version = audio.ffmpeg_version(found)
            self.lbl_ffmpeg.configure(
                text=f"Audio-Umwandlung bereit ({version or found.name}).",
                style="Success.TLabel")
            self.btn_ffmpeg.pack_forget()
            return

        # In der EXE liegt ffmpeg bereits bei - dann muss nichts geladen
        # werden, es wird nur einmalig ausgepackt.
        if embedded.has_ffmpeg():
            self.btn_ffmpeg.pack_forget()
            if auto_extract and not self._ffmpeg_busy:
                self.lbl_ffmpeg.configure(
                    text="ffmpeg ist in der App enthalten und wird einmalig "
                         "ausgepackt ...",
                    style="Muted.TLabel")
                self._extract_embedded_ffmpeg()
            return

        self.lbl_ffmpeg.configure(
            text=("ffmpeg wurde nicht gefunden. Ohne ffmpeg lassen sich nur "
                  "fertige .ogg-Dateien (Vorbis, mono, 16000 Hz) verwenden - "
                  "mp3 und wav können dann nicht umgewandelt werden. "
                  "Abhilfe: entweder ffmpeg.exe in denselben Ordner wie diese "
                  "App legen, oder die Schaltfläche unten benutzen."),
            style="Warning.TLabel")
        self.btn_ffmpeg.pack(side="left")

    def _extract_embedded_ffmpeg(self) -> None:
        """Packt das mitgelieferte ffmpeg im Hintergrund aus."""
        self._ffmpeg_busy = True
        self.ffmpeg_progress.pack(side="left", padx=(10, 0))
        self.ffmpeg_progress.configure(value=0)

        def work(_task):
            return embedded.extract_ffmpeg(
                progress=lambda done, total: to_main(
                    self, self.ffmpeg_progress.configure,
                    {"value": (done / total * 100) if total else 0}))

        def ok(path):
            self._ffmpeg_busy = False
            if path:
                self._check_ffmpeg(auto_extract=False)
            else:
                self.lbl_ffmpeg.configure(
                    text=("Das mitgelieferte ffmpeg liess sich nicht auspacken. "
                          "Lege ersatzweise eine ffmpeg.exe neben die App."),
                    style="Warning.TLabel")
                self.btn_ffmpeg.pack(side="left")

        def fail(_exc):
            self._ffmpeg_busy = False
            self._check_ffmpeg(auto_extract=False)

        run_async(self, work, on_success=ok, on_error=fail,
                  on_finally=lambda: self.ffmpeg_progress.pack_forget())

    def _on_setup_ffmpeg(self) -> None:
        if not messagebox.askyesno("ffmpeg einrichten",
                                   ffmpeg_setup.describe_source()
                                   + "\n\nJetzt herunterladen?",
                                   parent=self):
            return

        self.btn_ffmpeg.configure(state="disabled")
        self.ffmpeg_progress.pack(side="left", padx=(10, 0))
        self.ffmpeg_progress.configure(value=0)
        self.lbl_ffmpeg.configure(text="Lade ffmpeg herunter (etwa 170 MB) ...",
                                  style="Muted.TLabel")

        def report(done: int, total: int) -> None:
            percent = (done / total * 100) if total else 0
            to_main(self, self.ffmpeg_progress.configure, {"value": percent})
            to_main(self, self.lbl_ffmpeg.configure,
                    {"text": f"Lade ffmpeg herunter ... "
                             f"{done // (1024 * 1024)} von "
                             f"{(total or 1) // (1024 * 1024)} MB"})

        def work(task):
            return ffmpeg_setup.download_and_install(
                progress=report,
                log=lambda m: to_main(self, self.lbl_ffmpeg.configure, {"text": m}),
                cancelled=lambda: task.cancelled,
            )

        def ok(_path):
            self._check_ffmpeg()
            messagebox.showinfo("ffmpeg eingerichtet",
                                "ffmpeg ist jetzt einsatzbereit. mp3-, wav- und "
                                "m4a-Dateien werden ab sofort automatisch "
                                "umgewandelt.", parent=self)

        def fail(exc):
            message, hint = error_text(exc)
            self._check_ffmpeg()
            show_error(self, self.theme, "ffmpeg-Einrichtung fehlgeschlagen",
                       message + (f"\n\n{hint}" if hint else ""))

        def done():
            self.btn_ffmpeg.configure(state="normal")
            self.ffmpeg_progress.pack_forget()

        run_async(self, work, on_success=ok, on_error=fail, on_finally=done)

    # ------------------------------------------------------------------
    def _on_device_changed(self) -> None:
        self.base_badge.set("Noch nicht geladen", "muted")
        self.state.base_pack_path = None
        self.state.official_packs = []
        self.combo_language.configure(values=[])
        self._load_catalog_async()

    def _load_catalog_async(self) -> None:
        model = self.state.model
        if not model:
            return

        def work(_task):
            return official.fetch_catalog(model)

        def ok(packs):
            self.state.official_packs = packs
            labels = [p.label for p in packs]
            self.combo_language.configure(values=labels)
            preferred = self.state.config["base_language"]
            match = official.find_pack(packs, preferred) or official.find_pack(packs, "DE")
            if match:
                self.var_language.set(match.label)
            elif labels:
                self.var_language.set(labels[0])
            self.base_badge.set(f"{len(packs)} offizielle Sprachen verfügbar", "muted")

        def fail(exc):
            message, hint = error_text(exc)
            self.base_badge.set("Sprachliste nicht abrufbar", "error")
            self.lbl_ffmpeg.configure(text=f"{message} {hint}".strip(),
                                      style="Warning.TLabel")

        run_async(self, work, on_success=ok, on_error=fail)

    def _selected_pack(self):
        label = self.var_language.get()
        for pack in self.state.official_packs:
            if pack.label == label:
                return pack
        return None

    def _on_load_base(self) -> None:
        if not self.state.model:
            messagebox.showwarning(
                "Kein Roboter ausgewählt",
                "Melde dich zuerst im Tab 'Verbindung' an und wähle deinen Roboter.",
                parent=self)
            return

        if not self.state.official_packs:
            self._load_catalog_async()
            messagebox.showinfo(
                "Sprachliste wird geladen",
                "Die Liste der offiziellen Sprachpakete wird gerade abgerufen. "
                "Bitte gleich noch einmal klicken.",
                parent=self)
            return

        pack = self._selected_pack()
        if pack is None:
            messagebox.showwarning("Keine Sprache gewählt",
                                   "Bitte wähle ein offizielles Sprachpaket aus.",
                                   parent=self)
            return

        model = self.state.model
        self.btn_load_base.configure(state="disabled")
        self.base_progress.pack(fill="x", pady=(10, 0))
        self.base_progress.configure(value=0)
        self.base_badge.set("Lade Originalpaket ...", "muted")

        def report(done: int, total: int) -> None:
            percent = (done / total * 100) if total else 0
            to_main(self, self.base_progress.configure, {"value": percent})

        def work(_task):
            path = official.download_pack(pack, model, progress=report)
            to_main(self, self.base_badge.set, "Entpacke Hörproben ...", "muted")
            previews = official.extract_previews(
                path, preview_dir() / f"{model}_{pack.id}")
            return pack, path, previews

        def ok(result):
            selected_pack, path, previews = result
            self.state.base_pack_path = path
            self.state.base_pack_info = selected_pack
            self.state.previews = previews
            self.state.config["base_language"] = selected_pack.id
            self.state.save()

            summary = official.describe_pack(path)
            self.base_badge.set(f"Bereit - {summary}", "ok")

            # Katalog auf die IDs beschränken, die dieses Modell wirklich kennt.
            ids = sorted(previews.keys())
            if ids:
                self.state.catalog = self.state.catalog.restrict_to(ids)
            self.state.notify("base_pack_changed")
            self.rebuild_list()

        def fail(exc):
            message, hint = error_text(exc)
            self.base_badge.set("Download fehlgeschlagen", "error")
            show_error(self, self.theme, "Originalpaket nicht geladen",
                       message + (f"\n\n{hint}" if hint else ""))

        def done():
            self.btn_load_base.configure(state="normal")
            self.base_progress.pack_forget()

        run_async(self, work, on_success=ok, on_error=fail, on_finally=done)

    # ------------------------------------------------------------------
    def _debounced_rebuild(self) -> None:
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(220, self.rebuild_list)

    def _visible_sounds(self) -> List[Sound]:
        group = self.var_group.get()
        group = "" if group == "Alle Bereiche" else group
        sounds = self.state.catalog.filtered(
            group=group,
            search=self.var_search.get(),
            only_common=self.var_common.get(),
        )
        if self.var_assigned.get():
            assigned = set(self.state.assignments().keys())
            sounds = [s for s in sounds if s.id in assigned]
        return sounds

    def rebuild_list(self) -> None:
        self._search_job = None

        groups = ["Alle Bereiche"] + self.state.catalog.groups()
        if list(self.combo_group.cget("values")) != groups:
            self.combo_group.configure(values=groups)
            if self.var_group.get() not in groups:
                self.var_group.set("Alle Bereiche")

        sounds = self._visible_sounds()
        self._shown = min(max(self._shown, PAGE_SIZE), max(len(sounds), PAGE_SIZE))

        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows = []

        if not sounds:
            ttk.Label(self.rows_frame,
                      text="Zu diesen Filtern gibt es keine Ansagen.",
                      style="Muted.TLabel").pack(anchor="w", pady=20, padx=4)
        else:
            for sound in sounds[:self._shown]:
                row = SoundRow(self.rows_frame, self.theme, self, sound)
                row.pack(fill="x", padx=4)
                self._rows.append(row)

        self.page.canvas.yview_moveto(0.0)
        self._update_footer(len(sounds))
        self.refresh_counter()

    def _update_footer(self, total: int) -> None:
        if total > self._shown:
            self.btn_more.configure(
                text=f"Weitere {min(PAGE_SIZE, total - self._shown)} anzeigen")
            self.btn_more.pack(side="right")
        else:
            self.btn_more.pack_forget()

    def _show_more(self) -> None:
        self._shown += PAGE_SIZE
        self.rebuild_list()

    def refresh_counter(self) -> None:
        assigned = len(self.state.assignments())
        total = len(self.state.catalog)
        missing = len(self.state.missing_assignments())

        text = f"{assigned} von {total} Ansagen ausgetauscht"
        shown = len(self._rows)
        if shown:
            text += f"  ·  {shown} angezeigt"
        if missing:
            text += f"  ·  {missing} Zuweisung(en) zeigen auf fehlende Dateien"

        self.lbl_counter.configure(
            text=text, style="Warning.TLabel" if missing else "Muted.TLabel")
        self.state.notify("assignments_changed")

    # ------------------------------------------------------------------
    def _on_import_folder(self) -> None:
        ordner = filedialog.askdirectory(
            parent=self, title="Ordner mit deinen Audiodateien wählen",
            initialdir=self.state.config["last_audio_dir"] or str(Path.home()))
        if ordner:
            self._import_from(lambda: importer.scan_folder(
                Path(ordner), self.state.catalog.ids()))

    def _on_import_archive(self) -> None:
        datei = filedialog.askopenfilename(
            parent=self, title="Sprachpaket oder Archiv wählen",
            initialdir=self.state.config["last_audio_dir"] or str(Path.home()),
            filetypes=[("Archive", "*.tar.gz *.tgz *.zip"),
                       ("Alle Dateien", "*.*")])
        if datei:
            self._import_from(lambda: importer.import_archive(
                Path(datei), data_dir() / "Importiert",
                self.state.catalog.ids()))

    def _import_from(self, arbeit) -> None:
        """Führt einen Import aus und meldet das Ergebnis verständlich."""
        def work(_task):
            return arbeit()

        def ok(ergebnis: importer.ImportResult) -> None:
            if not ergebnis.assigned:
                show_warning(
                    self, self.theme, "Nichts gefunden",
                    "In der Auswahl war keine verwertbare Audiodatei.",
                    "Die Dateien müssen die Ansage-Nummer im Namen tragen, "
                    "zum Beispiel 7.ogg oder 12.wav.\n\n"
                    + self._skipped_text(ergebnis))
                return

            vorher = set(self.state.assignments())
            neu = [i for i in ergebnis.assigned if i not in vorher]
            ersetzt = [i for i in ergebnis.assigned if i in vorher]

            frage = (f"{len(ergebnis.assigned)} Ansagen gefunden:\n\n"
                     f"· {len(neu)} neu zugewiesen\n"
                     f"· {len(ersetzt)} bereits zugewiesene werden überschrieben\n")
            if ergebnis.unknown_ids:
                frage += (f"· {len(ergebnis.unknown_ids)} Nummern kennt dein "
                          f"Modell nicht und werden ausgelassen\n")
            if ergebnis.skipped:
                frage += f"· {len(ergebnis.skipped)} Dateien übersprungen\n"
            frage += "\nÜbernehmen?"

            if not messagebox.askyesno("Import prüfen", frage, parent=self):
                return

            for sound_id, pfad in ergebnis.assigned.items():
                self.state.config.set_assignment(sound_id, str(pfad))
            self.state.prebuilt = None
            self.state.prebuilt_name = ""
            self.state.config["last_audio_dir"] = str(
                Path(next(iter(ergebnis.assigned.values()))).parent)
            self.state.save()

            self.rebuild_list()
            show_info(self, self.theme, "Import fertig",
                      ergebnis.summary(),
                      self._skipped_text(ergebnis))

        def fail(exc: Exception) -> None:
            message, hint = error_text(exc)
            show_error(self, self.theme, "Import fehlgeschlagen", message, hint)

        run_async(self, work, on_success=ok, on_error=fail)

    @staticmethod
    def _skipped_text(ergebnis: importer.ImportResult) -> str:
        zeilen = []
        if ergebnis.unknown_ids:
            nummern = sorted(set(ergebnis.unknown_ids))
            zeilen.append("Unbekannte Ansage-Nummern: "
                          + ", ".join(str(n) for n in nummern[:20])
                          + (" ..." if len(nummern) > 20 else ""))
        if ergebnis.skipped:
            zeilen.append("Übersprungen:")
            zeilen += [f"   · {n}" for n in ergebnis.skipped[:15]]
            if len(ergebnis.skipped) > 15:
                zeilen.append(f"   ... und {len(ergebnis.skipped) - 15} weitere")
        return "\n".join(zeilen)

    # ------------------------------------------------------------------
    def _on_create_template(self) -> None:
        """Legt einen Ordner mit allen Originalansagen zum Nachsprechen an."""
        if not self.state.previews:
            show_warning(
                self, self.theme, "Originalpaket fehlt",
                "Für den Vorlagenordner werden die Originalansagen gebraucht.",
                "Lade oben in Schritt 1 zuerst das offizielle Sprachpaket "
                "deines Roboters herunter.")
            return

        nur_wichtige = messagebox.askyesno(
            "Umfang wählen",
            f"Sollen nur die wichtigsten Ansagen in den Vorlagenordner?\n\n"
            f"Ja  = {len(self.state.catalog.filtered(only_common=True))} "
            f"Ansagen (empfohlen für den Anfang)\n"
            f"Nein = alle {len(self.state.previews)} Ansagen",
            parent=self)

        ziel = filedialog.askdirectory(
            parent=self, title="Wo soll der Vorlagenordner entstehen?",
            initialdir=self.state.config["last_audio_dir"] or str(Path.home()))
        if not ziel:
            return

        ordner = Path(ziel) / "Meine Ansagen"
        ids = ([s.id for s in self.state.catalog.filtered(only_common=True)]
               if nur_wichtige else None)

        def work(_task):
            return importer.create_template_folder(
                self.state.previews, self.state.catalog, ordner, ids)

        def ok(pfad: Path) -> None:
            anzahl = len(list(pfad.glob("*.ogg")))
            self.state.config["last_audio_dir"] = str(pfad)
            self.state.save()
            show_info(
                self, self.theme, "Vorlagenordner angelegt",
                f"{anzahl} Originalansagen liegen jetzt in:\n{pfad}",
                "So geht es weiter:\n"
                "1. Datei anhören, damit du weisst, was gesagt wird.\n"
                "2. Eigene Aufnahme unter genau demselben Namen speichern.\n"
                "3. Hier auf 'Ganzen Ordner importieren' klicken.\n\n"
                "Eine Anleitung liegt als _Anleitung.txt im Ordner. "
                "Der Ordner wird jetzt geöffnet.")
            open_folder(pfad)

        def fail(exc: Exception) -> None:
            message, hint = error_text(exc)
            show_error(self, self.theme, "Vorlagenordner fehlgeschlagen",
                       message, hint)

        run_async(self, work, on_success=ok, on_error=fail)

    def _clear_all(self) -> None:
        if not self.state.config["assignments"]:
            return
        if not messagebox.askyesno(
                "Wirklich löschen?",
                "Alle Zuweisungen werden entfernt. Deine Audiodateien selbst "
                "bleiben natürlich erhalten.",
                parent=self):
            return
        self.state.config.clear_assignments()
        self.state.save()
        self.rebuild_list()

    def refresh_rows(self) -> None:
        for row in self._rows:
            row.refresh()
