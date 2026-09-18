"""Einzelne Ansagen austauschen - als Fenster aus "Eigene Stimmen" heraus.

Bis 1.3.0 war das eine eigene Seite ("Einzelne Ansagen"). Sie bot
dieselben Knöpfe zum Einlesen wie "Eigene Stimmen", verlangte als ersten
Schritt das Laden des Originalpakets (das die Startseite längst selbst
holt) - und wer dort Ansagen zugewiesen hatte, musste es erst einmal
herausfinden: Gebaut wurde auf einer dritten Seite.

Seit 1.4.0 gibt es dafür nur noch diesen einen Ort. Er macht genau eine
Sache: einzelnen Ansagen eigene Audiodateien zuweisen und daraus ein
Paket bauen. Alles andere - Originalpaket, ffmpeg, Einlesen ganzer
Ordner, Aufspielen - steht dort, wo es hingehört.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List, Optional

from .. import audio, importer, pruefung
from ..sounds import Sound
from .state import AppState, error_text, run_async, spaeter
from .theme import Theme
from .widgets import Card, ScrollablePage, show_error, show_info

#: So viele Zeilen auf einmal. Alle 616 gleichzeitig zu bauen dauert
#: spürbar und niemand liest sie am Stück.
PAGE_SIZE = 100

AUDIO_FILETYPES = [
    ("Audiodateien", "*.ogg *.wav *.mp3 *.m4a *.flac *.aac *.opus *.wma"),
    ("OGG Vorbis (bereits passend)", "*.ogg"),
    ("WAV", "*.wav"),
    ("MP3", "*.mp3"),
    ("Alle Dateien", "*.*"),
]

#: Wie breit der Text einer Ansagezeile umbrechen darf. Gemessen, nicht
#: geschätzt: Die Spalte ist 272 Pixel breit. Vorher stand hier 430 -
#: der Text lief über den Rand hinaus und brach mitten im Wort ab.
ZEILENBREITE = 262


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

    def __init__(self, master, theme: Theme, liste: "AnsagenListe",
                 sound: Sound) -> None:
        super().__init__(master, style="Card.TFrame")
        self.theme = theme
        self.liste = liste
        self.sound = sound

        self.columnconfigure(1, weight=1)

        num = ttk.Label(self, text=str(sound.id), style="Mono.TLabel",
                        width=5, anchor="e")
        num.grid(row=0, column=0, rowspan=2, sticky="ne", padx=(0, 10), pady=(4, 0))

        title = ttk.Label(self, text=sound.title, style="Surface.TLabel",
                          anchor="w", wraplength=ZEILENBREITE, justify="left")
        title.grid(row=0, column=1, sticky="ew")

        sub_parts = [sound.group]
        if sound.de and sound.en:
            sub_parts.append(f"Original (EN): {sound.en}")
        elif not sound.de and not sound.en:
            sub_parts.append("keine Beschreibung bekannt - bitte anhören")
        subtitle = ttk.Label(self, text="  ·  ".join(sub_parts), style="Muted.TLabel",
                             anchor="w", wraplength=ZEILENBREITE, justify="left")
        subtitle.grid(row=1, column=1, sticky="ew", pady=(1, 0))

        controls = ttk.Frame(self, style="Card.TFrame")
        controls.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))

        self.btn_preview = ttk.Button(controls, text="Original anhören",
                                      style="Small.TButton",
                                      command=self._play_original)
        self.btn_preview.pack(side="left", padx=(0, 6))

        self.var_path = tk.StringVar(value=liste.state.config.assignment(sound.id))
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
        available = self.sound.id in self.liste.state.previews
        self.btn_preview.configure(state="normal" if available else "disabled")

    def _play_original(self) -> None:
        path = self.liste.state.previews.get(self.sound.id)
        if not path or not path.is_file():
            messagebox.showinfo(
                "Keine Hörprobe",
                "Die Hörproben stammen aus dem Originalpaket deines Roboters. "
                "Es wird auf der Startseite einmalig geholt.",
                parent=self)
            return
        try:
            open_with_default_player(path)
        except OSError as exc:
            show_error(self, self.theme, "Wiedergabe nicht möglich",
                       f"Die Datei konnte nicht abgespielt werden.\n\n{path}\n\n{exc}")

    def _browse(self) -> None:
        initial = (self.liste.state.config["last_audio_dir"]
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
        self.liste.state.config["last_audio_dir"] = str(Path(chosen).parent)
        self._store()

    def _clear(self) -> None:
        self.var_path.set("")
        self._store()

    def _store(self) -> None:
        # Tk schickt beim Zerstören des Fensters noch ein <FocusOut>.
        # Dann gibt es die Zeile schon nicht mehr, und jeder Zugriff auf
        # ein Geschwister-Widget endete in einem Fehlerfenster.
        if not self.winfo_exists():
            return
        value = self.var_path.get().strip().strip('"')
        self.var_path.set(value)
        self.liste.state.config.set_assignment(self.sound.id, value)
        # Sobald der Nutzer selbst etwas zuweist, gilt wieder sein eigenes Paket.
        self.liste.state.prebuilt = None
        self.liste.state.prebuilt_name = ""
        self.liste.state.save()
        self._update_hint()
        self.liste.refresh_counter()

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

        # Erst der Inhalt: Eine "7.ogg", die in Wahrheit ein Programm
        # ist, soll gar nicht erst in ein Paket wandern.
        befund = pruefung.pruefe_datei(path)
        if befund.funde:
            self.hint.configure(
                text=f"{befund.funde[0].was}: {befund.funde[0].bedeutung}",
                style=("Danger.TLabel"
                       if befund.stufe >= pruefung.Stufe.GEFAHR
                       else "Warning.TLabel"))
            return

        warnung = audio.check_input_file(path)
        if warnung:
            self.hint.configure(text=warnung, style="Warning.TLabel")
        else:
            size_kb = path.stat().st_size // 1024
            self.hint.configure(text=f"Bereit: {path.name} ({size_kb} KB)",
                                style="Success.TLabel")

    def refresh(self) -> None:
        self.var_path.set(self.liste.state.config.assignment(self.sound.id))
        self._update_preview_state()
        self._update_hint()


class AnsagenListe(ttk.Frame):
    """Die durchsuchbare Liste aller Ansagen mit Dateizuweisung."""

    def __init__(self, master, theme: Theme, state: AppState,
                 seite: ScrollablePage) -> None:
        super().__init__(master, style="Card.TFrame")
        self.theme = theme
        self.state = state
        self.seite = seite
        self._rows: List[SoundRow] = []
        self._shown = PAGE_SIZE
        self._search_job: Optional[str] = None
        self._build()
        self.rebuild_list()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        filters = ttk.Frame(self, style="Card.TFrame")
        filters.pack(fill="x", pady=(0, 10))

        ttk.Label(filters, text="Suche", style="Surface.TLabel").pack(side="left")
        self.var_search = tk.StringVar()
        feld = ttk.Entry(filters, textvariable=self.var_search, width=26)
        feld.pack(side="left", padx=(8, 16))
        feld.bind("<KeyRelease>", lambda _e: self._debounced_rebuild())

        ttk.Label(filters, text="Bereich", style="Surface.TLabel").pack(side="left")
        self.var_group = tk.StringVar(value="Alle Bereiche")
        self.combo_group = ttk.Combobox(filters, textvariable=self.var_group,
                                        state="readonly", width=20,
                                        values=["Alle Bereiche"])
        self.combo_group.pack(side="left", padx=(8, 16))
        self.combo_group.bind("<<ComboboxSelected>>", lambda _e: self.rebuild_list())

        # Zweite Zeile: In einer einzigen wurde es zu eng - bei der
        # Startgröße des Fensters stand dort "Alle Zuwe", der Rest war
        # abgeschnitten. Ausgerechnet bei einem Knopf, der etwas löscht,
        # muss lesbar sein, WAS er löscht.
        filter2 = ttk.Frame(self, style="Card.TFrame")
        filter2.pack(fill="x", pady=(0, 10))

        self.var_common = tk.BooleanVar(value=True)
        ttk.Checkbutton(filter2, text="nur die wichtigsten",
                        variable=self.var_common,
                        command=self.rebuild_list).pack(side="left", padx=(0, 16))

        self.var_assigned = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter2, text="nur bereits zugewiesene",
                        variable=self.var_assigned,
                        command=self.rebuild_list).pack(side="left")

        ttk.Button(filter2, text="Alle Zuweisungen löschen",
                   style="Small.TButton",
                   command=self._clear_all).pack(side="right")

        self.rows_frame = ttk.Frame(self, style="Card.TFrame")
        self.rows_frame.pack(fill="both", expand=True)

        footer = ttk.Frame(self, style="Card.TFrame")
        footer.pack(fill="x", pady=(10, 0))
        self.lbl_counter = ttk.Label(footer, text="", style="Muted.TLabel")
        self.lbl_counter.pack(side="left")
        self.btn_more = ttk.Button(footer, text="Weitere anzeigen",
                                   style="Small.TButton", command=self._show_more)

    # ------------------------------------------------------------------
    def _debounced_rebuild(self) -> None:
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = spaeter(self, 220, self.rebuild_list)

    def _visible_sounds(self) -> List[Sound]:
        gruppe = self.var_group.get()
        gruppe = "" if gruppe == "Alle Bereiche" else gruppe
        sounds = self.state.catalog.filtered(
            group=gruppe,
            search=self.var_search.get(),
            only_common=self.var_common.get(),
        )
        if self.var_assigned.get():
            zugewiesen = set(self.state.assignments().keys())
            sounds = [s for s in sounds if s.id in zugewiesen]
        return sounds

    def rebuild_list(self) -> None:
        self._search_job = None

        gruppen = ["Alle Bereiche"] + self.state.catalog.groups()
        if list(self.combo_group.cget("values")) != gruppen:
            self.combo_group.configure(values=gruppen)
            if self.var_group.get() not in gruppen:
                self.var_group.set("Alle Bereiche")

        sounds = self._visible_sounds()
        self._shown = min(max(self._shown, PAGE_SIZE), max(len(sounds), PAGE_SIZE))

        for kind in self.rows_frame.winfo_children():
            kind.destroy()
        self._rows = []

        if not sounds:
            ttk.Label(self.rows_frame,
                      text="Zu diesen Filtern gibt es keine Ansagen.",
                      style="Muted.TLabel").pack(anchor="w", pady=20, padx=4)
        else:
            for sound in sounds[:self._shown]:
                zeile = SoundRow(self.rows_frame, self.theme, self, sound)
                zeile.pack(fill="x", padx=4)
                self._rows.append(zeile)

        self.seite.canvas.yview_moveto(0.0)
        self._update_footer(len(sounds))
        self.refresh_counter()

    def _update_footer(self, gesamt: int) -> None:
        if gesamt > self._shown:
            self.btn_more.configure(
                text=f"Weitere {min(PAGE_SIZE, gesamt - self._shown)} anzeigen")
            self.btn_more.pack(side="right")
        else:
            self.btn_more.pack_forget()

    def _show_more(self) -> None:
        self._shown += PAGE_SIZE
        self.rebuild_list()

    def refresh_counter(self) -> None:
        if not self.lbl_counter.winfo_exists():
            return
        zugewiesen = len(self.state.assignments())
        gesamt = len(self.state.catalog)
        fehlend = len(self.state.missing_assignments())

        text = f"{zugewiesen} von {gesamt} Ansagen ausgetauscht"
        gezeigt = len(self._rows)
        if gezeigt:
            text += f"  ·  {gezeigt} angezeigt"
        if fehlend:
            text += f"  ·  {fehlend} Zuweisung(en) zeigen auf fehlende Dateien"

        self.lbl_counter.configure(
            text=text, style="Warning.TLabel" if fehlend else "Muted.TLabel")
        self.state.notify("assignments_changed")

    def refresh_rows(self) -> None:
        for zeile in self._rows:
            zeile.refresh()

    def _clear_all(self) -> None:
        if not self.state.assignments():
            return
        if not messagebox.askyesno(
                "Alle Zuweisungen löschen?",
                "Damit sind alle zugewiesenen Audiodateien wieder frei. "
                "Die Dateien selbst bleiben, wo sie sind.",
                parent=self):
            return
        self.state.config.clear_assignments()
        self.state.prebuilt = None
        self.state.prebuilt_name = ""
        self.state.save()
        # Neu aufbauen, nicht nur auffrischen: Steht der Filter auf "nur
        # bereits zugewiesene", gehören die Zeilen jetzt nicht mehr in
        # die Liste - sie blieben sonst leer stehen.
        self.rebuild_list()


class AnsagenFenster(tk.Toplevel):
    """Das Fenster: Liste, Vorlagenordner, und der Weg zum fertigen Paket."""

    def __init__(self, master, theme: Theme, state: AppState,
                 bauen: Callable[[dict, str, str], None]) -> None:
        super().__init__(master)
        self.theme = theme
        self.state = state
        self._bauen = bauen
        self.title("Ansagen einzeln austauschen")
        self.configure(bg=theme.color("bg"))
        self.transient(master.winfo_toplevel())
        self.geometry("1020x760")

        seite = ScrollablePage(self, theme)
        seite.pack(fill="both", expand=True)
        außen = seite.body()

        karte = Card(außen, theme, "Ansagen einzeln austauschen",
                     "Jede Ansage kann eine eigene Audiodatei bekommen. Alles, "
                     "was du nicht zuweist, bleibt auf der deutschen "
                     "Originalstimme.")
        karte.pack(fill="both", expand=True)

        self.liste = AnsagenListe(karte.content, theme, state, seite)
        self.liste.pack(fill="both", expand=True)

        leiste = ttk.Frame(self, style="TFrame")
        leiste.pack(fill="x", padx=16, pady=(0, 14))
        ttk.Button(leiste, text="Paket aus diesen Ansagen bauen",
                   style="Accent.TButton", command=self._on_bauen).pack(side="left")
        ttk.Button(leiste, text="Vorlagenordner anlegen ...",
                   style="Small.TButton",
                   command=self._on_vorlage).pack(side="left", padx=(8, 0))
        ttk.Button(leiste, text="Schließen",
                   command=self.destroy).pack(side="right")

        self.state.subscribe("base_pack_changed", self.liste.rebuild_list)

    # ------------------------------------------------------------------
    def destroy(self) -> None:
        # Abmelden, bevor das Fenster weg ist - sonst meldet der Zustand
        # später an ein zerstörtes Widget.
        self.state.unsubscribe("base_pack_changed", self.liste.rebuild_list)
        super().destroy()

    def _on_bauen(self) -> None:
        zuordnung = self.state.assignments()
        if not zuordnung:
            show_info(self, self.theme, "Noch nichts zugewiesen",
                      "Weise mindestens einer Ansage eine Audiodatei zu.",
                      "Über 'Durchsuchen ...' in der Zeile der Ansage - oder "
                      "lege dir mit 'Vorlagenordner anlegen' einen Ordner an, "
                      "in dem jede Datei schon richtig heißt.")
            return
        fehlend = self.state.missing_assignments()
        if fehlend:
            liste = ", ".join(str(nummer) for nummer, _ in fehlend[:5])
            if not messagebox.askyesno(
                    "Dateien fehlen",
                    f"{len(fehlend)} zugewiesene Datei(en) gibt es nicht mehr "
                    f"(Ansage {liste}).\n\nDiese Ansagen bleiben auf der "
                    f"Originalstimme. Trotzdem bauen?",
                    parent=self):
                return
        # Der Bau läuft auf der Seite "Eigene Stimmen" - dort steht das
        # Protokoll, und dort landet das fertige Paket in der Liste.
        self.destroy()
        self._bauen(zuordnung, "eigene_ansagen", "einzeln zugewiesen")

    def _on_vorlage(self) -> None:
        """Legt einen Ordner an, in dem jede Datei schon richtig heißt."""
        if not self.state.previews:
            show_info(self, self.theme, "Noch keine Hörproben",
                      "Die Vorlagen entstehen aus dem Originalpaket deines "
                      "Roboters.",
                      "Es wird auf der Startseite einmalig geholt.")
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
                "1. Datei anhören, damit du weißt, was gesagt wird.\n"
                "2. Eigene Aufnahme unter genau demselben Namen speichern.\n"
                "3. Den Ordner unter 'Eigene Stimmen' einlesen - oder die "
                "Dateien hier einzeln zuweisen.\n\n"
                "Eine Anleitung liegt als _Anleitung.txt im Ordner. "
                "Der Ordner wird jetzt geöffnet.")
            try:
                open_with_default_player(pfad)
            except OSError:
                pass

        def fail(exc: Exception) -> None:
            nachricht, hinweis = error_text(exc)
            show_error(self, self.theme, "Vorlagenordner nicht angelegt",
                       nachricht, hinweis)

        run_async(self, work, on_success=ok, on_error=fail)


def fenster_zeigen(master, theme: Theme, state: AppState,
                   bauen: Callable[[dict, str, str], None]) -> AnsagenFenster:
    """Öffnet das Fenster - oder holt ein schon offenes nach vorn."""
    offen = getattr(master, "_ansagen_fenster", None)
    if offen is not None and offen.winfo_exists():
        offen.deiconify()
        offen.lift()
        return offen
    fenster = AnsagenFenster(master, theme, state, bauen)
    master._ansagen_fenster = fenster
    return fenster
