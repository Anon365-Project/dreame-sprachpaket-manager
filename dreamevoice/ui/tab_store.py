"""Seite 'Eigene Stimmen': Dialekte, eigene Pakete und Sprachsynthese."""

from __future__ import annotations

import hashlib
import shutil
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from .. import (community, custom, dialect, elevenlabs, importer, installer,
                library, packer, textfiles, tts)
from ..community import CommunityPack
from ..paths import build_dir
from .state import AppState, error_text, run_async, to_main
from .tab_builder import open_with_default_player
from .theme import Theme
from .widgets import (Card, InfoBanner, LogView, ScrollableList, ScrollablePage,
                      StatusBadge, show_error, show_info, show_warning)


# Die beiden Wege zu eigenen Aufnahmen. Der ZIP-Fall steht zuerst und wird
# beim Namen genannt: so heissen die Dateien auf der Projektseite.
WAHL_ARCHIV = "ZIP-Datei oder fertiges Paket (.tar.gz)"
WAHL_ORDNER = "Ordner mit mp3-, wav- oder ogg-Dateien"

# Was passiert, wenn der gewaehlte Name schon vergeben ist. Das Danebenlegen
# steht zuerst und ist die Vorgabe - ein Paket, das Kontingent gekostet hat,
# soll nicht mit einem Klick verschwinden.
WAHL_DANEBEN = "Daneben speichern - das vorhandene bleibt"
WAHL_ERSETZEN = "Das vorhandene ersetzen"


class PackCard(ttk.Frame):
    """Ein Community-Paket als Kachel."""

    def __init__(self, master, theme: Theme, tab: "StoreTab",
                 pack: CommunityPack) -> None:
        super().__init__(master, style="Card.TFrame")
        self.theme = theme
        self.tab = tab
        self.pack_info = pack

        self.columnconfigure(0, weight=1)

        head = ttk.Frame(self, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text=pack.name, style="Heading.TLabel").pack(side="left")

        meta = f"{pack.language}  ·  ca. {pack.approx_sounds} Ansagen"
        if pack.size_mb:
            meta += f"  ·  {pack.size_mb:.1f} MB"
        ttk.Label(head, text=meta, style="Muted.TLabel").pack(side="left", padx=(12, 0))

        ttk.Label(self, text=pack.description, style="Surface.TLabel",
                  wraplength=700, justify="left").grid(row=1, column=0, sticky="ew",
                                                       pady=(4, 0))

        source = f"Quelle: {pack.author}  ·  Lizenz: {pack.license}"
        ttk.Label(self, text=source, style="Muted.TLabel").grid(
            row=2, column=0, sticky="w", pady=(4, 0))

        if pack.notes:
            ttk.Label(self, text=pack.notes, style="Warning.TLabel",
                      wraplength=700, justify="left").grid(row=3, column=0,
                                                           sticky="ew", pady=(4, 0))

        buttons = ttk.Frame(self, style="Card.TFrame")
        buttons.grid(row=4, column=0, sticky="w", pady=(10, 0))

        self.btn_use = ttk.Button(buttons, text="Herunterladen und anpassen",
                                  style="Accent.TButton",
                                  command=lambda: tab.use_pack(pack))
        self.btn_use.pack(side="left")

        ttk.Button(buttons, text="Projektseite ansehen", style="Small.TButton",
                   command=lambda: webbrowser.open(pack.project_url)).pack(
            side="left", padx=(8, 0))

        ttk.Frame(self, style="Separator.TFrame", height=1).grid(
            row=5, column=0, sticky="ew", pady=(14, 12))


class StoreTab(ttk.Frame):
    def __init__(self, master, theme: Theme, state: AppState) -> None:
        super().__init__(master, style="TFrame")
        self.theme = theme
        self.state = state
        self._dialect_buttons: list[ttk.Button] = []
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.page = ScrollablePage(self, self.theme)
        self.page.pack(fill="both", expand=True)
        outer = self.page.body()

        InfoBanner(
            outer, self.theme,
            "Ehrlich gesagt: einen richtigen Store gibt es nicht. Was hier steht, "
            "sind die wenigen frei verfügbaren Bastelprojekte, die tatsächlich "
            "existieren und deren Dateien geprüft wurden. Jedes Paket wird beim "
            "Herunterladen gegen seine Prüfsumme geprüft und anschließend auf "
            "das offizielle Paket deines Modells gelegt - alles, was das "
            "Fremdpaket nicht abdeckt, bleibt auf der deutschen Originalstimme.",
        ).pack(fill="x", pady=(0, 14))

        self._build_dialect_card(outer)

        listing = Card(outer, self.theme, "Verfügbare Pakete")
        listing.pack(fill="both", expand=True, pady=(14, 0))

        # Der ganze Tab scrollt bereits - hier kein zweiter Bildlaufbereich.
        self.list_frame = ttk.Frame(listing.content, style="Card.TFrame")
        self.list_frame.pack(fill="both", expand=True)

        for pack in community.PACKS:
            card = PackCard(self.list_frame, self.theme, self, pack)
            card.pack(fill="x", padx=4)

        status = ttk.Frame(listing.content, style="Card.TFrame")
        status.pack(fill="x", pady=(10, 0))
        self.badge = StatusBadge(status, self.theme, "Bereit")
        self.badge.pack(side="left")
        self.progress = ttk.Progressbar(status, mode="determinate", maximum=100,
                                        length=220)

        self.log = LogView(listing.content, self.theme, height=8)
        self.log.pack(fill="both", expand=False, pady=(10, 0))

    # ------------------------------------------------------------------
    def _build_dialect_card(self, outer) -> None:
        """Dialektpakete, die die App selbst spricht."""
        umfaenge = sorted(p.count for p in dialect.DIALECTS)
        spanne = (f"{umfaenge[0]} bis {umfaenge[-1]}" if umfaenge[0] != umfaenge[-1]
                  else str(umfaenge[0]))
        card = Card(outer, self.theme, "Selbst erzeugen: Dialektpakete",
                    f"{len(dialect.DIALECTS)} Dialekte, {spanne} Ansagen - "
                    f"fertig herunterladen kann man die nirgends.")
        card.pack(fill="x")

        ttk.Label(
            card.content,
            text=("Dialektpakete gibt es für keinen Saugroboter zum Herunterladen - "
                  "weder für Dreame noch für Roborock, Xiaomi oder Valetudo. In den "
                  "Foren wurden sie oft gewünscht, gebaut hat sie niemand; vorhanden "
                  "ist einzig ein Schweizerdeutsch-Paket für den Roborock S5. Es gibt "
                  "also kein Fremdpaket zum Umbauen.\n\n"
                  "Diese App schreibt die Ansagen deshalb selbst im jeweiligen "
                  "Dialekt und lässt sie sprechen. Mit der Windows-Stimme läuft das "
                  "offline und kostenlos; für echten Dialekt in der Aussprache lässt "
                  "sich auf ElevenLabs umschalten."),
            style="Surface.TLabel", wraplength=820, justify="left").pack(anchor="w")

        # --- Dialektauswahl ---------------------------------------------
        picker = ttk.Frame(card.content, style="Card.TFrame")
        picker.pack(fill="x", pady=(14, 0))
        ttk.Label(picker, text="Dialekt", style="Surface.TLabel").pack(side="left")

        self.var_dialect = tk.StringVar()
        self.combo_dialect = ttk.Combobox(
            picker, textvariable=self.var_dialect, state="readonly", width=34)
        self.combo_dialect.pack(side="left", padx=(8, 0))
        self.combo_dialect.bind("<<ComboboxSelected>>",
                                lambda _e: self._on_dialect_changed())

        self.lbl_dialect_meta = ttk.Label(picker, text="", style="Muted.TLabel")
        self.lbl_dialect_meta.pack(side="left", padx=(14, 0))

        # --- Eigene Pakete verwalten ------------------------------------
        eigene = ttk.Frame(card.content, style="Card.TFrame")
        eigene.pack(fill="x", pady=(8, 0))
        ttk.Button(eigene, text="Eigenes Paket anlegen ...",
                   style="Small.TButton",
                   command=self._on_new_custom).pack(side="left")
        self.btn_rename = ttk.Button(eigene, text="Umbenennen",
                                     style="Small.TButton",
                                     command=self._on_rename_custom)
        self.btn_rename.pack(side="left", padx=(8, 0))
        self.btn_delete_custom = ttk.Button(eigene, text="Löschen",
                                            style="Small.TButton",
                                            command=self._on_delete_custom)
        self.btn_delete_custom.pack(side="left", padx=(8, 0))
        ttk.Button(eigene, text="Aufnahmen einlesen ...",
                   style="Small.TButton",
                   command=self._on_import_ready).pack(side="left", padx=(8, 0))

        ttk.Label(card.content,
                  text=("Unter 'Eigenes Paket anlegen' entsteht eine eigene "
                        "Textsammlung - etwa im Stil einer Filmfigur. Sie "
                        "verhält sich wie ein Dialekt: anhören, Texte ändern, "
                        "mit jeder Stimme erzeugen, nach aufgebrauchtem "
                        "Kontingent fortsetzen. 'Aufnahmen einlesen' nimmt "
                        "fertig gesprochene Ansagen entgegen: eine "
                        "ZIP-Datei von der Projektseite, ein fertiges "
                        ".tar.gz oder einen Ordner voller mp3- und "
                        "wav-Dateien."),
                  style="Muted.TLabel", wraplength=820,
                  justify="left").pack(anchor="w", pady=(6, 0))

        self.lbl_dialect_desc = ttk.Label(card.content, text="",
                                          style="Surface.TLabel",
                                          wraplength=800, justify="left")
        self.lbl_dialect_desc.pack(anchor="w", pady=(8, 0))

        self.lbl_samples = ttk.Label(card.content, text="", style="Muted.TLabel",
                                     justify="left")
        self.lbl_samples.pack(anchor="w", pady=(6, 0))

        # Zwischenstand: wie weit ein früherer Lauf gekommen ist.
        fortschritt = ttk.Frame(card.content, style="Card.TFrame")
        fortschritt.pack(fill="x", pady=(10, 0))
        self.lbl_fortschritt = ttk.Label(fortschritt, text="",
                                         style="Muted.TLabel",
                                         wraplength=700, justify="left")
        self.lbl_fortschritt.pack(side="left")
        self.btn_verwerfen = ttk.Button(
            fortschritt, text="Zwischenstand verwerfen", style="Small.TButton",
            command=self._on_discard_progress)

        self._build_engine_chooser(card.content)

        # --- Aktionen ----------------------------------------------------
        actions = ttk.Frame(card.content, style="Card.TFrame")
        actions.pack(fill="x", pady=(14, 0))

        self.btn_preview = ttk.Button(actions, text="Kostprobe anhören",
                                      command=self._on_preview_dialect)
        self.btn_preview.pack(side="left")
        self._dialect_buttons.append(self.btn_preview)

        self.btn_texts = ttk.Button(actions, text="Texte ansehen und ändern",
                                    command=self._on_show_texts)
        self.btn_texts.pack(side="left", padx=(8, 0))

        self.btn_generate = ttk.Button(actions, text="Paket erzeugen",
                                       style="Accent.TButton",
                                       command=self._on_generate_selected)
        self.btn_generate.pack(side="left", padx=(8, 0))
        self._dialect_buttons.append(self.btn_generate)

        # Absichtlich NICHT in _dialect_buttons: dieser Knopf muss genau
        # dann bedienbar sein, wenn alle anderen gesperrt sind.
        self.btn_abbrechen = ttk.Button(actions, text="Abbrechen",
                                        command=self._on_cancel_work,
                                        state="disabled")
        self.btn_abbrechen.pack(side="left", padx=(8, 0))

        # --- Textdateien --------------------------------------------------
        dateien = ttk.Frame(card.content, style="Card.TFrame")
        dateien.pack(fill="x", pady=(8, 0))

        ttk.Button(dateien, text="Texte als Dateien ausgeben",
                   style="Small.TButton",
                   command=self._on_export_texts).pack(side="left")
        ttk.Button(dateien, text="Texte aus Datei einlesen",
                   style="Small.TButton",
                   command=self._on_import_texts).pack(side="left", padx=(8, 0))
        ttk.Button(dateien, text="Ordner öffnen", style="Small.TButton",
                   command=self._on_open_text_folder).pack(side="left", padx=(8, 0))

        ttk.Label(card.content,
                  text=("Die Kostprobe spricht drei Sätze mit der gerade gewählten "
                        "Stimme und spielt sie ab - so hörst du vorher, ob dir das "
                        "Ergebnis gefällt. Bei ElevenLabs kostet sie rund 60 Zeichen "
                        "aus dem Monatskontingent.\n"
                        "Unter 'Texte ansehen und ändern' kannst du jede Ansage "
                        "umformulieren. Deine Fassung bleibt gespeichert; bereits "
                        "gesprochene Aufnahmen geänderter Ansagen werden verworfen "
                        "und beim nächsten Erzeugen neu aufgenommen.\n"
                        "Für größere Überarbeitungen liegt jeder Dialekt auch als "
                        "Textdatei im Datenordner: kopieren, von einer Sprach-KI "
                        "verbessern lassen, zurück in die Datei einfügen und wieder "
                        "einlesen."),
                  style="Muted.TLabel", wraplength=800,
                  justify="left").pack(anchor="w", pady=(6, 0))

        # Erst hier: die Auswahlliste füllt auch die Beschriftungen, die es
        # weiter oben noch gar nicht gibt.
        self._refill_dialect_picker()

        ttk.Label(
            card.content,
            text=("Die Stimme einer real existierenden Person nachzubilden - etwa "
                  "aus YouTube-Aufnahmen oder fremden Sprachpaketen - ist rechtlich "
                  "heikel (Persönlichkeitsrecht, bei Schauspielern kommen "
                  "Verwertungsrechte dazu). Dafür bietet diese App bewusst keine "
                  "Funktion an."),
            style="Muted.TLabel", wraplength=820, justify="left").pack(anchor="w",
                                                                       pady=(10, 0))

    # ------------------------------------------------------------------
    # Auswahlliste: mitgelieferte Dialekte und eigene Pakete
    # ------------------------------------------------------------------
    VORSATZ_DIALEKT = "Dialekt · "
    VORSATZ_EIGEN = "Eigenes · "

    def _all_packs(self) -> list:
        """Alle wählbaren Pakete: erst die Dialekte, dann die eigenen."""
        try:
            eigene = custom.list_packs()
        except OSError:
            eigene = []
        return list(dialect.DIALECTS) + eigene

    def _label_for(self, pack) -> str:
        vorsatz = (self.VORSATZ_EIGEN if self._is_custom(pack)
                   else self.VORSATZ_DIALEKT)
        return f"{vorsatz}{pack.name}"

    def _is_custom(self, pack) -> bool:
        return not any(d.key == pack.key for d in dialect.DIALECTS)

    def _refill_dialect_picker(self, auswahl: str = "") -> None:
        """Baut die Auswahlliste neu auf und hält die Auswahl fest."""
        self._packs = self._all_packs()
        beschriftungen = [self._label_for(p) for p in self._packs]
        self.combo_dialect.configure(values=beschriftungen)

        vorher = auswahl or self.var_dialect.get()
        if vorher in beschriftungen:
            self.combo_dialect.set(vorher)
        elif beschriftungen:
            self.combo_dialect.set(beschriftungen[0])

        eigene = sum(1 for p in self._packs if self._is_custom(p))
        for knopf in (getattr(self, "btn_rename", None),
                      getattr(self, "btn_delete_custom", None)):
            if knopf is not None:
                knopf.configure(state="normal" if eigene else "disabled")

        self._on_dialect_changed()

    def _selected_dialect(self):
        """Das gewählte Paket mit seinen mitgelieferten Texten."""
        wahl = self.var_dialect.get()
        for pack in getattr(self, "_packs", None) or self._all_packs():
            if self._label_for(pack) == wahl:
                return pack
        # Ältere Fassungen hatten den blanken Namen in der Liste.
        return next((p for p in self._all_packs() if p.name == wahl), None)

    def _effective_dialect(self, pack=None):
        """Der Dialekt so, wie er wirklich gesprochen wird - mit eigenen Texten."""
        pack = pack or self._selected_dialect()
        if pack is None:
            return None
        return dialect.with_overrides(
            pack, self.state.config.dialect_overrides(pack.key))

    def _on_dialect_changed(self) -> None:
        pack = self._selected_dialect()
        if pack is None:
            return
        aktuell = self._effective_dialect(pack)
        eigene = len(dialect.changed_ids(
            pack, self.state.config.dialect_overrides(pack.key)))

        meta = f"{aktuell.count} Ansagen  ·  Kennung {pack.lang_id}"
        if eigene:
            meta += f"  ·  {eigene} selbst geändert"
        self.lbl_dialect_meta.configure(text=meta)
        self.lbl_dialect_desc.configure(text=pack.description)
        samples = "\n".join(f"   {line}"
                            for line in dialect.preview_texts(aktuell, 6))
        self.lbl_samples.configure(text="Kostprobe:\n" + samples)
        self.refresh_progress()

    def _work_dir(self, pack=None) -> Path:
        """Ablageort der Aufnahmen für die aktuelle Stimme und Einstellung."""
        pack = pack or self._selected_dialect()
        if pack is None:
            return build_dir() / "_dialekt" / "unbekannt"

        engine = self.var_engine.get()
        if engine == dialect.ENGINE_ELEVENLABS:
            gewaehlt = self._selected_eleven_voice()
            stimme = gewaehlt.voice_id if gewaehlt else (
                self.state.config["elevenlabs_voice_id"] or "standard")
        else:
            stimme = self._selected_win_voice() or "standard"

        modell, klang, eigene = self._eleven_klang()
        tempo, hoehe = self._win_klang()
        fingerabdruck = hashlib.md5(
            f"{modell}|{eigene}|{sorted((klang or {}).items())}|{tempo}|{hoehe}"
            .encode("utf-8")).hexdigest()[:8]
        kennung = str(stimme).replace(" ", "_")[:40]
        return build_dir() / "_dialekt" / f"{pack.key}_{engine}_{kennung}_{fingerabdruck}"

    def refresh_progress(self) -> None:
        """Zeigt, wie weit ein früherer Lauf gekommen ist."""
        pack = self._effective_dialect()
        if pack is None:
            return

        try:
            ordner = self._work_dir()
            passend, uebernommen, veraltet = dialect.classify_recordings(
                pack, ordner)
        except Exception:
            self.lbl_fortschritt.configure(text="")
            self.btn_verwerfen.pack_forget()
            return

        fertig = len(passend) + len(uebernommen)
        if fertig == 0 and not veraltet:
            self.lbl_fortschritt.configure(
                text="Zwischenstand: noch nichts gesprochen.",
                style="Muted.TLabel")
            self.btn_verwerfen.pack_forget()
            return

        teile = [f"Zwischenstand: {fertig} von {pack.count} Ansagen gesprochen"]
        if uebernommen:
            teile.append(f"davon {len(uebernommen)} aus vorhandenen Dateien "
                         f"übernommen")
        if veraltet:
            teile.append(f"{len(veraltet)} gehören zu geändertem Text und "
                         f"werden erneuert")
        offen = pack.count - fertig
        if offen > 0:
            teile.append(f"{offen} offen - 'Paket erzeugen' macht dort weiter")
        else:
            teile.append("alles vorhanden, das Erzeugen kostet nichts mehr")

        self.lbl_fortschritt.configure(
            text="  ·  ".join(teile),
            style="Success.TLabel" if offen == 0 else "Muted.TLabel")
        self.btn_verwerfen.pack(side="right")

    def _on_discard_progress(self) -> None:
        """Wirft die zwischengespeicherten Aufnahmen weg."""
        pack = self._effective_dialect()
        if pack is None:
            return
        ordner = self._work_dir()
        fertig = dialect.spoken_count(ordner)
        if not fertig:
            return

        if not messagebox.askyesno(
                "Zwischenstand verwerfen",
                f"{fertig} bereits gesprochene Ansagen werden gelöscht.\n\n"
                f"Beim nächsten Erzeugen wird alles neu gesprochen - bei "
                f"ElevenLabs kostet das erneut Kontingent.\n\nWirklich löschen?",
                parent=self):
            return

        try:
            shutil.rmtree(ordner / "gesprochen", ignore_errors=True)
            shutil.rmtree(ordner / "umgewandelt", ignore_errors=True)
        except OSError:
            pass
        self.refresh_progress()
        self.log.append(f"Zwischenstand verworfen ({fertig} Aufnahmen).", "warn")

    # ------------------------------------------------------------------
    # Eigene Pakete anlegen, umbenennen, löschen
    # ------------------------------------------------------------------
    def _on_new_custom(self) -> None:
        """Legt eine eigene Textsammlung an - meist als Kopie eines Dialekts."""
        name = simpledialog.askstring(
            "Eigenes Sprachpaket",
            "Wie soll das Paket heißen?\n\n"
            "Zum Beispiel 'Bruce Willis', 'Pirat' oder 'Butler'. Der Name "
            "steht nur in dieser App - der Roboter bekommt daraus eine kurze "
            "Kennung.",
            parent=self)
        if not name or not name.strip():
            return

        vorlagen = [f"Kopie von {p.name}" for p in dialect.DIALECTS]
        vorlagen.append("Leer anfangen")

        wahl = self._ask_choice(
            "Womit anfangen?",
            "Ein Paket braucht für jede Ansage einen Text.\n\n"
            "Am einfachsten kopierst du einen vorhandenen Dialekt: dann "
            "stehen alle Ansagen schon da und du schreibst sie um. Neben "
            "jeder Zeile steht, was sie bedeuten muss.\n\n"
            "Leer anfangen lohnt nur, wenn du bloß einzelne Ansagen "
            "austauschen willst - der Rest bleibt dann auf der deutschen "
            "Originalstimme.",
            vorlagen, vorlagen[0])
        if wahl is None:
            return

        texte = {}
        if wahl != "Leer anfangen":
            quelle = next((p for p in dialect.DIALECTS
                           if f"Kopie von {p.name}" == wahl), None)
            if quelle is not None:
                # Bewusst die wirksamen Texte: eigene Änderungen am Dialekt
                # sollen in der Kopie erhalten bleiben.
                texte = dict(self._effective_dialect(quelle).texts)

        vergeben = [p.lang_id for p in self._all_packs()]
        neu = custom.create(name.strip(), texte, vergeben=vergeben)
        try:
            custom.save(neu)
        except OSError as exc:
            show_error(self, self.theme, "Nicht gespeichert",
                       "Das eigene Paket konnte nicht angelegt werden.",
                       f"Technische Details: {exc}")
            return

        self.log.append(f"Eigenes Paket '{neu.name}' angelegt "
                        f"({neu.count} Ansagen, Kennung {neu.lang_id}).", "ok")
        self._refill_dialect_picker(self._label_for(neu))
        show_info(
            self, self.theme, "Paket angelegt",
            f"'{neu.name}' steht jetzt in der Auswahl.",
            f"{neu.count} Ansagen als Vorlage, Kennung {neu.lang_id}.\n\n"
            f"Mit 'Texte ansehen und ändern' schreibst du sie um - oder du "
            f"gibst die Datei\n{custom.path_for(neu.key).name}\naus dem Ordner "
            f"'{custom.ORDNER}' einer Sprach-KI. Danach wie gewohnt auf "
            f"'Paket erzeugen'.")

    def _on_rename_custom(self) -> None:
        pack = self._selected_dialect()
        if pack is None or not self._is_custom(pack):
            show_warning(self, self.theme, "Kein eigenes Paket",
                         "Mitgelieferte Dialekte lassen sich nicht umbenennen.",
                         "Wähle oben ein Paket aus, das mit 'Eigenes' beginnt.")
            return
        neu = simpledialog.askstring("Umbenennen", "Neuer Name:",
                                     initialvalue=pack.name, parent=self)
        if not neu or not neu.strip():
            return
        custom.rename(pack, neu)
        try:
            custom.save(pack)
        except OSError as exc:
            show_error(self, self.theme, "Nicht gespeichert", str(exc))
            return
        self._refill_dialect_picker(self._label_for(pack))
        self.log.append(f"Umbenannt in '{pack.name}'.", "ok")

    def _on_delete_custom(self) -> None:
        pack = self._selected_dialect()
        if pack is None or not self._is_custom(pack):
            show_warning(self, self.theme, "Kein eigenes Paket",
                         "Mitgelieferte Dialekte lassen sich nicht löschen.",
                         "Wähle oben ein Paket aus, das mit 'Eigenes' beginnt.")
            return
        if not messagebox.askyesno(
                "Wirklich löschen?",
                f"'{pack.name}' mit {pack.count} Ansagen löschen?\n\n"
                f"Bereits gesprochene Aufnahmen und fertig gebaute Pakete "
                f"bleiben erhalten - nur die Textsammlung verschwindet.",
                parent=self):
            return
        custom.delete(pack.key)
        self.log.append(f"'{pack.name}' gelöscht.", "warn")
        self._refill_dialect_picker()

    def _on_import_ready(self) -> None:
        """Ein fertiges Paket oder einen Ordner voller Aufnahmen übernehmen."""
        if not self.state.has_base_pack:
            show_warning(
                self, self.theme, "Originalpaket fehlt",
                "Lade zuerst unter 'Einzelne Ansagen' das offizielle Sprachpaket deines "
                "Roboters herunter.",
                "Jedes eigene Paket entsteht als Kopie davon - sonst fehlen "
                "dem Roboter alle Ansagen, die du nicht selbst lieferst.")
            return

        art = self._ask_choice(
            "Was soll eingelesen werden?",
            "Die Aufnahmen von der Projektseite sind ZIP-Dateien wie "
            "'Bayerisch-Aufnahmen.zip'. Nimm dafür die erste Zeile und wähle "
            "das ZIP direkt aus - entpacken musst du nichts.\n\n"
            "Beides landet als fertiges Paket in deiner Sammlung und steht "
            "danach unter 'Fertige Stimmen' zur Auswahl.",
            [WAHL_ARCHIV, WAHL_ORDNER],
            WAHL_ARCHIV)
        if art is None:
            return

        bekannt = self.state.catalog.ids() if self.state.catalog else None
        start = self.state.config["last_audio_dir"] or str(
            Path.home() / "Downloads")

        if art == WAHL_ARCHIV:
            quelle = filedialog.askopenfilename(
                parent=self, title="ZIP oder Paketdatei wählen",
                initialdir=start if Path(start).is_dir() else str(Path.home()),
                filetypes=[("Aufnahmen und Pakete",
                            "*.zip *.tar.gz *.tgz *.tar"),
                           ("Alle Dateien", "*.*")])
            if not quelle:
                return
            try:
                gefunden = importer.import_archive(
                    Path(quelle), build_dir() / "_import",
                    known_ids=bekannt, log=lambda m: self._log(m))
            except Exception as exc:                   # noqa: BLE001
                self._on_import_error(exc)
                return
        else:
            quelle = filedialog.askdirectory(
                parent=self, title="Ordner mit den Aufnahmen wählen",
                initialdir=start if Path(start).is_dir() else str(Path.home()),
                mustexist=True)
            if not quelle:
                return
            try:
                gefunden = importer.scan_folder(
                    Path(quelle), known_ids=bekannt, log=lambda m: self._log(m))
            except Exception as exc:                   # noqa: BLE001
                self._on_import_error(exc)
                return

        # Beim naechsten Mal dort weitermachen, wo zuletzt etwas lag.
        merken = Path(quelle)
        self.state.config["last_audio_dir"] = str(
            merken if merken.is_dir() else merken.parent)

        zuordnung = gefunden.assigned
        if not zuordnung:
            show_warning(
                self, self.theme, "Nichts gefunden",
                f"In {Path(quelle).name} steckt keine zuzuordnende Aufnahme.",
                "Die Dateien müssen die Ansage-Nummer im Namen tragen, also "
                "7.ogg, 7.wav oder 7.mp3. Ein passend benannter Vorlagenordner "
                "lässt sich unter 'Einzelne Ansagen' anlegen.")
            return

        name = simpledialog.askstring(
            "Name für dieses Paket",
            f"{len(zuordnung)} Ansagen gefunden.\n\n"
            f"Unter welchem Namen soll das fertige Paket gespeichert werden?",
            initialvalue=library.safe_name(Path(quelle).stem or "eigenes_paket"),
            parent=self)
        if name is None:
            return

        # Gibt es den Namen schon, wird gefragt statt stillschweigend eine
        # zweite Fassung danebenzulegen - wer neuere Aufnahmen einliest,
        # will meist die alten ersetzen. Vorgabe bleibt trotzdem das
        # Danebenlegen: ein mit bezahltem Kontingent erzeugtes Paket darf
        # nicht aus Versehen verschwinden.
        sicher = library.safe_name(name)
        schon_da = library.existing_pack(build_dir(), sicher)
        if schon_da is None:
            ziel = build_dir() / f"{sicher}.tar.gz"
        else:
            alt = library.read_info(schon_da)
            wahl = self._ask_choice(
                "Dieses Paket gibt es schon",
                f"Vorhanden ist:\n{alt.label}\n\n"
                f"Ersetzen überschreibt es endgültig. Das neue Paket wird "
                f"zuerst vollständig gebaut - schlägt das fehl, bleibt das "
                f"vorhandene unangetastet.",
                [WAHL_DANEBEN, WAHL_ERSETZEN], WAHL_DANEBEN)
            if wahl is None:
                return
            if wahl == WAHL_ERSETZEN:
                ziel = schon_da
                self.log.append(f"Ersetze {schon_da.name}.", "warn")
            else:
                ziel = library.unique_path(build_dir(), sicher)

        kennung = simpledialog.askstring(
            "Kennung",
            "Unter welcher Kennung soll der Roboter das Paket führen?\n\n"
            "CUSTOM ist eine gute Wahl - damit bleibt die mitgelieferte "
            "deutsche Stimme unangetastet.",
            initialvalue="CUSTOM", parent=self)
        if kennung is None:
            return

        base = self.state.base_pack_path
        ffmpeg = self.state.ffmpeg
        mapping = self.state.voice_mapping()

        self.log.clear()
        self.log.append(f"Baue Paket aus {len(zuordnung)} Aufnahmen ...", "step")
        self._busy(True)
        self.badge.set("Wandle um und baue ...", "muted")

        def work_fn(_task):
            return packer.build_pack(
                base_pack=Path(base), assignments=zuordnung,
                out_name=ziel.name, ffmpeg=ffmpeg,
                work_dir=build_dir() / "_import_arbeit",
                mapping=mapping, log=lambda m: self._log(m))

        def ok(build) -> None:
            library.write_info(build.path, dialect=name.strip() or ziel.stem,
                               engine="Eigene Aufnahmen",
                               voice=Path(quelle).name,
                               lang_id=(kennung or "CUSTOM").strip().upper(),
                               replaced=len(build.replaced),
                               total=len(zuordnung))
            self.state.prebuilt = build
            self.state.prebuilt_name = name.strip() or ziel.stem
            self.state.last_build = build
            self.state.config["custom_lang_id"] = (kennung or "CUSTOM").strip().upper()
            self.state.save()
            self.state.notify("assignments_changed")
            self.badge.set(f"Fertig - {len(build.replaced)} Ansagen", "ok")
            self.log.append(build.summary(), "ok")
            for warnung in build.warnings:
                self.log.append(warnung, "warn")
            show_info(self, self.theme, "Paket ist fertig",
                      f"{len(build.replaced)} Ansagen übernommen.",
                      f"Gespeichert als:\n{build.path.name}\n\n"
                      f"Unter 'Fertige Stimmen' wählst du es zum Installieren aus.")

        def fail(exc: Exception) -> None:
            message, hint = error_text(exc)
            self.badge.set("Fehlgeschlagen", "error")
            self.log.append(message, "error")
            if hint:
                self.log.append(hint, "warn")
            show_error(self, self.theme, "Paket nicht gebaut", message, hint)

        run_async(self, work_fn, on_success=ok, on_error=fail,
                  on_finally=lambda: self._busy(False))

    def _on_import_error(self, exc: Exception) -> None:
        message, hint = error_text(exc)
        self.log.append(message, "error")
        show_error(self, self.theme, "Einlesen fehlgeschlagen", message, hint)

    def _ask_choice(self, titel: str, frage: str, optionen: list,
                    vorgabe: str = "") -> Optional[str]:
        """Kleiner Auswahldialog - tkinter bringt keinen mit."""
        fenster = tk.Toplevel(self)
        fenster.title(titel)
        fenster.configure(bg=self.theme.color("bg"))
        fenster.transient(self.winfo_toplevel())
        fenster.grab_set()

        card = Card(fenster, self.theme, titel)
        card.pack(fill="both", expand=True, padx=16, pady=16)
        ttk.Label(card.content, text=frage, style="Surface.TLabel",
                  wraplength=420, justify="left").pack(anchor="w")

        var = tk.StringVar(value=vorgabe or (optionen[0] if optionen else ""))
        # Breit genug fuer die laengste Wahl ("Daneben speichern - ...").
        breite = max(40, *(len(o) for o in optionen)) if optionen else 40
        combo = ttk.Combobox(card.content, textvariable=var, state="readonly",
                             values=optionen, width=min(breite + 2, 60))
        combo.pack(anchor="w", pady=(12, 0))

        ergebnis = {"wert": None}

        def uebernehmen() -> None:
            ergebnis["wert"] = var.get()
            fenster.destroy()

        knoepfe = ttk.Frame(card.content, style="Card.TFrame")
        knoepfe.pack(fill="x", pady=(16, 0))
        ttk.Button(knoepfe, text="Übernehmen", style="Accent.TButton",
                   command=uebernehmen).pack(side="left")
        ttk.Button(knoepfe, text="Abbrechen",
                   command=fenster.destroy).pack(side="left", padx=(8, 0))

        fenster.wait_window()
        return ergebnis["wert"]

    # ------------------------------------------------------------------
    # Dialekttexte als Datei
    # ------------------------------------------------------------------
    def _on_export_texts(self) -> None:
        """Schreibt alle sieben Dialekte als Textdatei in den Datenordner."""
        try:
            pfade = textfiles.write_all(self.state.config.dialect_overrides)
        except OSError as exc:
            show_error(self, self.theme, "Dateien nicht geschrieben",
                       "Die Textdateien konnten nicht angelegt werden.",
                       f"Technische Details: {exc}")
            return

        self.log.append(f"{len(pfade)} Dialekt-Textdateien geschrieben.", "ok")
        show_info(
            self, self.theme, "Textdateien angelegt",
            f"{len(pfade)} Dateien liegen jetzt in:\n{textfiles.folder()}",
            "Eine Datei komplett kopieren, von einer Sprach-KI überarbeiten "
            "lassen, das Ergebnis wieder einfügen und speichern. Danach hier "
            "auf 'Texte aus Datei einlesen' klicken.\n\n"
            "Achtung: vorhandene Dateien wurden mit dem aktuellen Stand "
            "überschrieben.")

    def _on_open_text_folder(self) -> None:
        try:
            open_with_default_player(textfiles.folder())
        except Exception as exc:                       # noqa: BLE001
            show_error(self, self.theme, "Ordner nicht geöffnet",
                       str(exc), f"Der Ordner liegt hier:\n{textfiles.folder()}")

    def _on_import_texts(self) -> None:
        """Liest eine überarbeitete Textdatei ein."""
        pack = self._selected_dialect()
        vorschlag = textfiles.file_for(pack.key) if pack else None

        pfad = filedialog.askopenfilename(
            parent=self,
            title="Überarbeitete Dialekttexte einlesen",
            initialdir=str(textfiles.folder()),
            initialfile=vorschlag.name if vorschlag else "",
            filetypes=[("Textdateien", "*.txt"), ("Alle Dateien", "*.*")])
        if not pfad:
            return

        pfad = Path(pfad)
        # Der Dialekt richtet sich nach dem Dateinamen, nicht nach der
        # Auswahl im Fenster - sonst landen kölsche Texte beim Bayerischen.
        ziel = next((p for p in self._all_packs() if p.key == pfad.stem), None)
        if ziel is None:
            show_warning(
                self, self.theme, "Paket nicht erkannt",
                f"Zu '{pfad.name}' gibt es kein passendes Paket.",
                "Die Datei muss so heißen wie das Paket, also zum Beispiel "
                "'wienerisch.txt'. Benenne sie um und versuche es erneut.")
            return

        try:
            ergebnis = textfiles.read_one(pfad, ziel)
        except (OSError, UnicodeError) as exc:
            show_error(self, self.theme, "Datei nicht lesbar",
                       f"{pfad.name} konnte nicht gelesen werden.",
                       f"Technische Details: {exc}")
            return

        if not ergebnis.gelesen:
            show_warning(
                self, self.theme, "Nichts gefunden",
                f"In {pfad.name} steht keine einzige verwertbare Zeile.",
                "Jede Zeile braucht die Form\n"
                "  Nummer | Bedeutung | Dialekttext\n\n"
                "Hat die KI das Format geändert, gib ihr die Datei noch einmal "
                "mit dem Hinweis, den Aufbau der Zeilen beizubehalten.")
            return

        hinweise = []
        if ergebnis.unbekannt:
            zeige = ", ".join(str(i) for i in ergebnis.unbekannt[:8])
            if len(ergebnis.unbekannt) > 8:
                zeige += " ..."
            hinweise.append(
                f"{len(ergebnis.unbekannt)} Nummern gibt es bei diesem Dialekt "
                f"nicht und wurden übergangen: {zeige}")
        if ergebnis.leer:
            hinweise.append(
                f"{ergebnis.leer} Zeilen hatten keinen Text - diese Ansagen "
                f"bleiben, wie sie waren.")

        if not messagebox.askyesno(
                "Texte übernehmen?",
                f"{pfad.name}\n\n{ergebnis.summary()}\n\n"
                + ("\n".join(hinweise) + "\n\n" if hinweise else "")
                + f"Sollen diese Texte für {ziel.name} übernommen werden?",
                parent=self):
            return

        alt = self.state.config.dialect_overrides(ziel.key)
        geaendert = dialect.changed_ids(ziel, ergebnis.overrides)
        # Nur das neu sprechen, was sich wirklich geändert hat.
        wirklich_neu = {i for i in geaendert
                        if alt.get(i, ziel.texts.get(i, "")) !=
                        ergebnis.overrides.get(i, ziel.texts.get(i, ""))}
        verworfen = dialect.forget_cached_audio(ziel, wirklich_neu)

        self.state.config.set_dialect_overrides(ziel.key, ergebnis.overrides)
        self.state.save()
        self._on_dialect_changed()

        self.log.append(
            f"{ziel.name}: {ergebnis.geaendert} Texte aus {pfad.name} "
            f"übernommen.", "ok")

        zusatz = ""
        if verworfen:
            zusatz = (f"\n\n{verworfen} bereits gesprochene Aufnahmen wurden "
                      f"verworfen, damit sie mit dem neuen Text neu entstehen. "
                      f"Alle übrigen bleiben liegen und kosten kein Kontingent.")
        show_info(self, self.theme, "Texte übernommen",
                  f"{ergebnis.geaendert} von {ziel.count} Ansagen weichen jetzt "
                  f"vom mitgelieferten Text ab.",
                  "Die Änderungen bleiben erhalten, auch nach einem Neustart."
                  + zusatz)

    def _on_show_texts(self) -> None:
        """Öffnet den Texteditor für den gewählten Dialekt."""
        pack = self._selected_dialect()
        if pack is None:
            return

        basis = pack                      # mitgelieferte Texte
        aktuell = self._effective_dialect(pack)   # mit eigenen Änderungen

        window = tk.Toplevel(self)
        window.title(f"{pack.name} - {pack.count} Ansagen bearbeiten")
        window.configure(bg=self.theme.color("bg"))
        window.geometry("900x700")
        window.transient(self.winfo_toplevel())

        card = Card(window, self.theme, f"{pack.name} anpassen",
                    "Ändere die Texte, wie du sie hören willst. Was du leer "
                    "lässt, bleibt auf der deutschen Originalstimme.")
        card.pack(fill="both", expand=True, padx=16, pady=16)

        suche_zeile = ttk.Frame(card.content, style="Card.TFrame")
        suche_zeile.pack(fill="x", pady=(0, 8))
        ttk.Label(suche_zeile, text="Suche", style="Surface.TLabel").pack(side="left")
        var_suche = tk.StringVar()
        eingabe = ttk.Entry(suche_zeile, textvariable=var_suche, width=30)
        eingabe.pack(side="left", padx=(8, 0))
        lbl_zahl = ttk.Label(suche_zeile, text="", style="Muted.TLabel")
        lbl_zahl.pack(side="left", padx=(14, 0))

        liste = ScrollableList(card.content, self.theme)
        liste.pack(fill="both", expand=True)

        felder: dict[int, tk.StringVar] = {}
        katalog = self.state.catalog

        def aufbauen() -> None:
            # Fast 600 Zeilen mit je vier Bausteinen brauchen gut zwei
            # Sekunden. Ohne Rückmeldung wirkt das wie ein Absturz.
            lbl_zahl.configure(text="Liste wird aufgebaut ...")
            window.configure(cursor="watch")
            window.update_idletasks()
            try:
                _aufbauen()
            finally:
                window.configure(cursor="")

        def _aufbauen() -> None:
            liste.clear()
            felder.clear()
            begriff = var_suche.get().strip().lower()
            gezeigt = 0

            for sound_id in sorted(basis.texts):
                text_jetzt = aktuell.texts.get(sound_id, "")
                eintrag = katalog.get(sound_id)
                bedeutung = eintrag.title if eintrag else ""

                if begriff and not (begriff in text_jetzt.lower()
                                    or begriff in bedeutung.lower()
                                    or begriff == str(sound_id)):
                    continue

                zeile = ttk.Frame(liste.inner, style="Card.TFrame")
                zeile.pack(fill="x", padx=4, pady=(0, 2))
                zeile.columnconfigure(1, weight=1)

                ttk.Label(zeile, text=str(sound_id), style="Mono.TLabel",
                          width=5, anchor="e").grid(row=0, column=0, rowspan=2,
                                                    sticky="ne", padx=(0, 8))
                var = tk.StringVar(value=text_jetzt)
                felder[sound_id] = var
                ttk.Entry(zeile, textvariable=var).grid(row=0, column=1, sticky="ew")

                # Sofort hören, wie der geänderte Satz klingt.
                ttk.Button(zeile, text="▶", width=3, style="Small.TButton",
                           command=lambda v=var: self._speak_text(v.get())
                           ).grid(row=0, column=2, sticky="e", padx=(6, 0))

                geaendert = text_jetzt != basis.texts.get(sound_id, "")
                hinweis = bedeutung + ("   ·  geändert" if geaendert else "")
                ttk.Label(zeile, text=hinweis, style="Muted.TLabel",
                          anchor="w").grid(row=1, column=1, sticky="ew",
                                           pady=(1, 4))
                gezeigt += 1

            liste.scroll_to_top()
            lbl_zahl.configure(text=f"{gezeigt} von {basis.count} Ansagen")

        eingabe.bind("<KeyRelease>", lambda _e: aufbauen())
        aufbauen()

        # ---- Knöpfe ------------------------------------------------------
        knoepfe = ttk.Frame(window, style="TFrame")
        knoepfe.pack(fill="x", padx=16, pady=(0, 16))

        def speichern() -> None:
            abweichungen = {}
            for sound_id, var in felder.items():
                wert = var.get().strip()
                if wert and wert != basis.texts.get(sound_id, ""):
                    abweichungen[sound_id] = wert

            # Änderungen ausserhalb der aktuellen Suchansicht behalten
            alt = self.state.config.dialect_overrides(pack.key)
            for sound_id, wert in alt.items():
                if sound_id not in felder:
                    abweichungen[sound_id] = wert

            geaendert = dialect.changed_ids(basis, abweichungen)
            verworfen = dialect.forget_cached_audio(basis, geaendert)

            self.state.config.set_dialect_overrides(pack.key, abweichungen)
            self.state.save()
            window.destroy()

            self._on_dialect_changed()
            zusatz = ""
            if verworfen:
                zusatz = (f"\n\n{verworfen} bereits gesprochene Aufnahmen wurden "
                          f"verworfen, damit sie neu mit deinem Text entstehen.")
            show_info(self, self.theme, "Texte gespeichert",
                      f"{len(geaendert)} von {basis.count} Ansagen weichen jetzt "
                      f"vom mitgelieferten Text ab.",
                      "Die Änderungen bleiben erhalten, auch nach einem Neustart."
                      + zusatz)

        def zuruecksetzen() -> None:
            if not messagebox.askyesno(
                    "Zurücksetzen",
                    f"Alle eigenen Änderungen an {pack.name} verwerfen und die "
                    f"mitgelieferten Texte wiederherstellen?", parent=window):
                return
            alt = self.state.config.dialect_overrides(pack.key)
            dialect.forget_cached_audio(basis, dialect.changed_ids(basis, alt))
            self.state.config.set_dialect_overrides(pack.key, {})
            self.state.save()
            window.destroy()
            self._on_dialect_changed()

        ttk.Button(knoepfe, text="Speichern", style="Accent.TButton",
                   command=speichern).pack(side="left")
        ttk.Button(knoepfe, text="Auf Standard zurücksetzen",
                   command=zuruecksetzen).pack(side="left", padx=(8, 0))
        ttk.Button(knoepfe, text="Abbrechen",
                   command=window.destroy).pack(side="right")

    def _speak_text(self, text: str) -> None:
        """Spricht einen einzelnen Satz mit der gerade gewählten Stimme."""
        text = (text or "").strip()
        if not text:
            show_warning(self, self.theme, "Kein Text",
                         "In dieser Zeile steht nichts zum Vorlesen.")
            return

        engine = self.var_engine.get()
        api_key = voice_id = win_voice = ""
        modell, klang, eigene = self._eleven_klang()
        tempo, hoehe = self._win_klang()

        if engine == dialect.ENGINE_ELEVENLABS:
            api_key = self.var_key.get().strip() or self.state.config.elevenlabs_key
            gewaehlt = self._selected_eleven_voice()
            if not api_key or gewaehlt is None:
                show_warning(
                    self, self.theme, "Erst verbinden",
                    "Für ElevenLabs brauchst du Schlüssel und Stimme.",
                    "Ohne beides kann der Satz nicht gesprochen werden. Mit der "
                    "Windows-Stimme geht es sofort.")
                return
            voice_id = gewaehlt.voice_id
        else:
            if not tts.german_voices():
                show_warning(self, self.theme, "Keine deutsche Stimme",
                             "Es ist keine deutsche Sprachausgabe installiert.")
                return
            win_voice = self._selected_win_voice()

        ordner = build_dir() / "_satzprobe"

        def work(_task):
            return dialect.speak_one(
                text, ordner, engine=engine, voice=win_voice,
                api_key=api_key, voice_id=voice_id, model=modell,
                voice_settings=klang, use_voice_settings=eigene,
                rate=tempo, pitch=hoehe)

        def ok(pfad) -> None:
            try:
                open_with_default_player(pfad)
            except OSError as exc:
                show_error(self, self.theme, "Wiedergabe nicht möglich",
                           f"Die Aufnahme liegt hier:\n{pfad}", str(exc))

        def fail(exc: Exception) -> None:
            message, hint = error_text(exc)
            show_error(self, self.theme, "Vorlesen fehlgeschlagen", message, hint)

        run_async(self, work, on_success=ok, on_error=fail)

    def _on_generate_selected(self) -> None:
        # Bewusst die wirksamen Texte: was der Nutzer geändert hat, wird
        # auch gesprochen.
        pack = self._effective_dialect()
        if pack is not None:
            self.generate_dialect(pack)

    # ------------------------------------------------------------------
    def _on_preview_dialect(self) -> None:
        """Spricht drei Sätze und spielt sie ab."""
        pack = self._effective_dialect()
        if pack is None:
            return

        engine = self.var_engine.get()
        api_key = ""
        voice_id = ""
        win_voice = ""

        if engine == dialect.ENGINE_ELEVENLABS:
            api_key = self.var_key.get().strip() or self.state.config.elevenlabs_key
            chosen = self._selected_eleven_voice()
            if not api_key or chosen is None:
                messagebox.showinfo(
                    "Erst verbinden",
                    "Trage deinen ElevenLabs-Schlüssel ein, klicke auf "
                    "'Verbinden und Stimmen laden' und wähle eine Stimme aus. "
                    "Danach kannst du sie hier anhören.", parent=self)
                return
            voice_id = chosen.voice_id
        else:
            if not tts.german_voices():
                messagebox.showwarning(
                    "Keine deutsche Stimme",
                    "Es ist keine deutsche Sprachausgabe installiert.",
                    parent=self)
                return
            win_voice = self._selected_win_voice()

        tempo_vor, hoehe_vor = self._win_klang()
        modell_vor, klang_vor, eigen_vor = self._eleven_klang()
        stempel = hashlib.md5(
            f"{win_voice}|{voice_id}|{modell_vor}|{eigen_vor}|"
            f"{sorted((klang_vor or {}).items())}|{tempo_vor}|{hoehe_vor}"
            .encode("utf-8")).hexdigest()[:8]
        work = build_dir() / "_kostprobe" / f"{pack.key}_{engine}_{stempel}"

        self._busy(True)
        self.badge.set("Spreche die Kostprobe ...", "muted")
        self.log.clear()
        for line in dialect.preview_texts(pack, 3):
            self.log.append(line, "info")

        modell, klang, eigene = self._eleven_klang()
        tempo, hoehe = self._win_klang()

        def work_fn(_task):
            return dialect.preview(
                pack, work, engine=engine, voice=win_voice,
                api_key=api_key, voice_id=voice_id,
                model=modell, voice_settings=klang,
                use_voice_settings=eigene,
                rate=tempo, pitch=hoehe, ffmpeg=self.state.ffmpeg,
                log=lambda m: self._log(m))

        def ok(files) -> None:
            self.badge.set(f"Kostprobe fertig - {len(files)} Sätze", "ok")
            self.log.append("Spiele ab ...", "ok")
            for path in files:
                try:
                    open_with_default_player(path)
                except OSError as exc:
                    self.log.append(f"Konnte {path.name} nicht abspielen: {exc}",
                                    "warn")
                    break

        def fail(exc: Exception) -> None:
            message, hint = error_text(exc)
            self.badge.set("Kostprobe fehlgeschlagen", "error")
            self.log.append(message, "error")
            if hint:
                self.log.append(hint, "warn")
            show_error(self, self.theme, "Kostprobe fehlgeschlagen",
                       message + (f"\n\n{hint}" if hint else ""))

        run_async(self, work_fn, on_success=ok, on_error=fail,
                  on_finally=lambda: self._busy(False))

    # ------------------------------------------------------------------
    def _build_engine_chooser(self, parent) -> None:
        """Auswahl, wer die Ansagen spricht."""
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.pack(fill="x", pady=(14, 0))

        ttk.Frame(frame, style="Separator.TFrame", height=1).pack(fill="x",
                                                                   pady=(0, 12))
        ttk.Label(frame, text="Wer spricht?", style="Heading.TLabel").pack(anchor="w")

        self.var_engine = tk.StringVar(value=self.state.config["tts_engine"])

        # --- Windows ---------------------------------------------------
        win_row = ttk.Frame(frame, style="Card.TFrame")
        win_row.pack(fill="x", pady=(8, 0))
        ttk.Radiobutton(win_row, text="Windows-Sprachausgabe",
                        variable=self.var_engine, value=dialect.ENGINE_WINDOWS,
                        command=self._on_engine_changed).pack(side="left")
        self.combo_winvoice = ttk.Combobox(win_row, state="readonly", width=30,
                                           values=[])
        self.combo_winvoice.pack(side="left", padx=(12, 0))

        self.lbl_voice = ttk.Label(
            frame,
            text=("   Offline, kostenlos, sofort einsatzbereit - aber hochdeutsche "
                  "Aussprache. Der Dialekt steckt nur in den Worten. Stefan ist "
                  "die einzige männliche deutsche Stimme; System.Speech kennt sie "
                  "nicht, die App holt sie über die Windows-Runtime."),
            style="Muted.TLabel", wraplength=800, justify="left")
        self.lbl_voice.pack(anchor="w", pady=(2, 0))

        # --- Regler für die Windows-Stimme --------------------------------
        self.win_regler = ttk.Frame(frame, style="Card.TFrame")
        ttk.Label(self.win_regler, text="   Tempo",
                  style="Surface.TLabel").pack(side="left")
        self.var_rate = tk.IntVar(value=int(self.state.config["tts_rate"]))
        ttk.Scale(self.win_regler, from_=-6, to=6, orient="horizontal",
                  variable=self.var_rate, length=150,
                  command=lambda _v: self._on_win_regler()).pack(side="left",
                                                                 padx=(8, 8))
        self.lbl_rate = ttk.Label(self.win_regler, text="", style="Muted.TLabel")
        self.lbl_rate.pack(side="left")

        ttk.Label(self.win_regler, text="   Tonhöhe",
                  style="Surface.TLabel").pack(side="left", padx=(16, 0))
        self.var_pitch = tk.IntVar(value=int(self.state.config["tts_pitch"]))
        ttk.Scale(self.win_regler, from_=-6, to=6, orient="horizontal",
                  variable=self.var_pitch, length=150,
                  command=lambda _v: self._on_win_regler()).pack(side="left",
                                                                 padx=(8, 8))
        self.lbl_pitch = ttk.Label(self.win_regler, text="", style="Muted.TLabel")
        self.lbl_pitch.pack(side="left")

        ttk.Button(self.win_regler, text="Zurücksetzen", style="Small.TButton",
                   command=self._on_win_reset).pack(side="left", padx=(16, 0))

        # --- ElevenLabs -------------------------------------------------
        el_row = ttk.Frame(frame, style="Card.TFrame")
        el_row.pack(fill="x", pady=(12, 0))
        ttk.Radiobutton(el_row, text="ElevenLabs - echter bayerischer Akzent",
                        variable=self.var_engine, value=dialect.ENGINE_ELEVENLABS,
                        command=self._on_engine_changed).pack(side="left")

        bedarf = min((elevenlabs.estimate_characters(p.texts)
                      for p in dialect.DIALECTS), default=0)
        self.lbl_eleven_info = ttk.Label(
            frame,
            text=("   Ein frei verfügbares Dialekt-Sprachmodell gibt es nicht - "
                  "geprüft: Piper hat nur Hochdeutsch, Thorsten-Voice nur Hessisch, "
                  "und der einzige bayerische Sprachkorpus gehört dem Bayerischen "
                  "Rundfunk. ElevenLabs bietet Dialekte dagegen ausdrücklich an, "
                  f"mit 10.000 Freizeichen im Monat. Ein Dialektpaket braucht ab "
                  f"{bedarf} Zeichen; volle Abdeckung eher das Doppelte. Geht das "
                  f"Kontingent aus, macht die App beim nächsten Mal dort weiter.\n"
                  "   Du brauchst ein eigenes (kostenloses) Konto. Die App legt "
                  "keins an. Übertragen werden nur die Ansagetexte."),
            style="Muted.TLabel", wraplength=800, justify="left")
        self.lbl_eleven_info.pack(anchor="w", pady=(2, 0))

        key_row = ttk.Frame(frame, style="Card.TFrame")
        key_row.pack(fill="x", pady=(8, 0))
        ttk.Label(key_row, text="   Zugangsschlüssel", style="Surface.TLabel").pack(
            side="left")
        self.var_key = tk.StringVar(value=self.state.config.elevenlabs_key)
        self.entry_key = ttk.Entry(key_row, textvariable=self.var_key, width=34,
                                   show="•")
        self.entry_key.pack(side="left", padx=(8, 8))
        self.btn_connect = ttk.Button(key_row, text="Verbinden und Stimmen laden",
                                      style="Small.TButton",
                                      command=self._on_connect_elevenlabs)
        self.btn_connect.pack(side="left")
        ttk.Button(key_row, text="Schlüssel holen", style="Link.TButton",
                   command=self._open_api_key_page).pack(side="left", padx=(8, 0))
        ttk.Button(key_row, text="Schlüssel vergessen", style="Link.TButton",
                   command=self._on_forget_key).pack(side="left", padx=(8, 0))

        self.lbl_key_ort = ttk.Label(frame, text="", style="Muted.TLabel",
                                     wraplength=800, justify="left")
        self.lbl_key_ort.pack(anchor="w", pady=(2, 0))

        voice_row = ttk.Frame(frame, style="Card.TFrame")
        voice_row.pack(fill="x", pady=(8, 0))
        ttk.Label(voice_row, text="   Stimme", style="Surface.TLabel").pack(side="left")
        self.combo_elvoice = ttk.Combobox(voice_row, state="readonly", width=44,
                                          values=[])
        self.combo_elvoice.pack(side="left", padx=(8, 8))
        self.combo_elvoice.bind(
            "<<ComboboxSelected>>", lambda _e: self._on_elvoice_changed())
        self.btn_search = ttk.Button(voice_row, text="Stimmen-Bibliothek durchsuchen",
                                     style="Small.TButton",
                                     command=self._on_search_bavarian)
        self.btn_search.pack(side="left")

        # Eigene Stimmen tauchen nicht immer in der Liste auf. Mit der ID
        # lässt sich jede Stimme direkt ansprechen.
        id_row = ttk.Frame(frame, style="Card.TFrame")
        id_row.pack(fill="x", pady=(8, 0))
        ttk.Label(id_row, text="   Eigene Stimmen-ID",
                  style="Surface.TLabel").pack(side="left")
        self.var_voice_id = tk.StringVar(
            value=self.state.config["elevenlabs_voice_id"])
        self.entry_voice_id = ttk.Entry(id_row, textvariable=self.var_voice_id,
                                        width=28)
        self.entry_voice_id.pack(side="left", padx=(8, 8))
        self.btn_add_id = ttk.Button(id_row, text="Übernehmen",
                                     style="Small.TButton",
                                     command=self._on_add_voice_id)
        self.btn_add_id.pack(side="left")
        ttk.Label(id_row,
                  text="(in ElevenLabs: drei Punkte an der Stimme > Copy Voice ID)",
                  style="Muted.TLabel").pack(side="left", padx=(10, 0))

        # --- Klang -------------------------------------------------------
        klang = ttk.Frame(frame, style="Card.TFrame")
        klang.pack(fill="x", pady=(8, 0))
        ttk.Label(klang, text="   Modell", style="Surface.TLabel").pack(side="left")
        self.combo_model = ttk.Combobox(klang, state="readonly", width=34,
                                        values=[])
        self.combo_model.pack(side="left", padx=(8, 16))
        self.combo_model.set("Standard (eleven_multilingual_v2)")

        self.var_own_settings = tk.BooleanVar(
            value=bool(self.state.config["elevenlabs_use_voice_settings"]))
        ttk.Checkbutton(klang, text="Klang der Stimme übernehmen",
                        variable=self.var_own_settings,
                        command=self._on_settings_mode).pack(side="left")

        self.regler = ttk.Frame(frame, style="Card.TFrame")
        ttk.Label(self.regler, text="   Lebendigkeit",
                  style="Surface.TLabel").pack(side="left")
        self.var_stability = tk.DoubleVar(
            value=float(self.state.config["elevenlabs_stability"]))
        ttk.Scale(self.regler, from_=0.0, to=1.0, orient="horizontal",
                  variable=self.var_stability, length=150,
                  command=lambda _v: self._on_regler()).pack(side="left", padx=(8, 8))
        self.lbl_stability = ttk.Label(self.regler, text="", style="Muted.TLabel")
        self.lbl_stability.pack(side="left")

        ttk.Label(self.regler, text="   Ausdruck",
                  style="Surface.TLabel").pack(side="left", padx=(16, 0))
        self.var_style = tk.DoubleVar(
            value=float(self.state.config["elevenlabs_style"]))
        ttk.Scale(self.regler, from_=0.0, to=1.0, orient="horizontal",
                  variable=self.var_style, length=150,
                  command=lambda _v: self._on_regler()).pack(side="left", padx=(8, 8))
        self.lbl_style = ttk.Label(self.regler, text="", style="Muted.TLabel")
        self.lbl_style.pack(side="left")

        ttk.Label(
            frame,
            text=("   'Klang der Stimme übernehmen' benutzt genau die "
                  "Einstellungen, die du in ElevenLabs an der Stimme "
                  "hinterlegt hast - so klingt sie wie dort in der Vorschau. "
                  "Ohne den Haken kannst du selbst regeln: weniger Stabilität "
                  "heisst mehr Schwung, mehr Stabilität heisst gleichförmiger."),
            style="Muted.TLabel", wraplength=800, justify="left").pack(
            anchor="w", pady=(4, 0))

        self.lbl_eleven = ttk.Label(frame, text="", style="Muted.TLabel",
                                    wraplength=800, justify="left")
        self.lbl_eleven.pack(anchor="w", pady=(6, 0))

        self._on_settings_mode()
        self._on_regler()
        self._on_win_regler()
        self._refresh_key_location()

        self._eleven_voices: list = []
        self._refresh_voice_info()
        self._on_engine_changed()

    def _on_win_regler(self) -> None:
        """Beschriftet die Regler der Windows-Stimme."""
        tempo = self.var_rate.get()
        hoehe = self.var_pitch.get()
        self.lbl_rate.configure(
            text=f"{tempo * 10:+d} %  ({'normal' if tempo == 0 else 'langsamer' if tempo < 0 else 'schneller'})")
        self.lbl_pitch.configure(
            text=f"{hoehe * 10:+d} %  ({'normal' if hoehe == 0 else 'tiefer' if hoehe < 0 else 'höher'})")
        self.state.config["tts_rate"] = int(tempo)
        self.state.config["tts_pitch"] = int(hoehe)

    def _on_win_reset(self) -> None:
        self.var_rate.set(0)
        self.var_pitch.set(0)
        self._on_win_regler()

    def _win_klang(self) -> tuple:
        return int(self.var_rate.get()), int(self.var_pitch.get())

    def _on_settings_mode(self) -> None:
        """Regler nur zeigen, wenn nicht die Stimmen-Einstellungen gelten."""
        eigene = self.var_own_settings.get()
        self.state.config["elevenlabs_use_voice_settings"] = eigene
        if eigene:
            self.regler.pack_forget()
        else:
            self.regler.pack(fill="x", pady=(6, 0))

    def _on_regler(self) -> None:
        stab = self.var_stability.get()
        art = ("sehr lebendig" if stab < 0.3 else
               "lebendig" if stab < 0.5 else
               "ausgewogen" if stab < 0.7 else "gleichförmig")
        self.lbl_stability.configure(text=f"{stab:.2f}  ({art})")
        self.lbl_style.configure(text=f"{self.var_style.get():.2f}")

    def _eleven_klang(self):
        """Was an ElevenLabs geschickt wird: (Modell, Einstellungen, Modus)."""
        modell = ""
        gewaehlt = self.combo_model.get()
        for eintrag in getattr(self, "_models", []):
            if eintrag["label"] == gewaehlt:
                modell = eintrag["id"]
                break

        if self.var_own_settings.get():
            return modell, None, True
        return modell, {"stability": round(self.var_stability.get(), 2),
                        "similarity_boost": 0.75,
                        "style": round(self.var_style.get(), 2),
                        "use_speaker_boost": True}, False

    def _on_engine_changed(self) -> None:
        engine = self.var_engine.get()
        self.state.config["tts_engine"] = engine
        self.state.save()

        eleven = engine == dialect.ENGINE_ELEVENLABS
        for widget in (self.entry_key, self.btn_connect, self.combo_elvoice,
                       self.btn_search, self.entry_voice_id, self.btn_add_id,
                       self.combo_model):
            widget.configure(state="normal" if eleven else "disabled")
        if eleven:
            self.combo_elvoice.configure(state="readonly")
            self.combo_model.configure(state="readonly")
        self.combo_winvoice.configure(state="disabled" if eleven else "readonly")
        self.refresh_progress()

        # Die Regler der Windows-Stimme nur zeigen, wenn sie auch spricht.
        if eleven:
            self.win_regler.pack_forget()
        else:
            self.win_regler.pack(fill="x", pady=(6, 0),
                                 before=self.lbl_voice)

    def _refresh_voice_info(self) -> None:
        self._win_voices = tts.german_voices()
        if self._win_voices:
            labels = [v.label for v in self._win_voices]
            self.combo_winvoice.configure(values=labels)
            stored = self.state.config["tts_voice"]
            chosen = next((v for v in self._win_voices if v.name == stored), None)
            self.combo_winvoice.set((chosen or self._win_voices[0]).label)
        else:
            self.combo_winvoice.configure(values=[])
            self.lbl_voice.configure(
                text=("   Es ist keine deutsche Sprachausgabe installiert. "
                      "Windows-Einstellungen > Zeit und Sprache > Sprache > "
                      "Deutsch > Optionen > Sprachausgabe hinzufügen, danach die "
                      "App neu starten."),
                style="Warning.TLabel")

    def _selected_win_voice(self) -> str:
        """Name der gewählten Windows-Stimme (leer = automatisch)."""
        label = self.combo_winvoice.get()
        voice = next((v for v in getattr(self, "_win_voices", [])
                      if v.label == label), None)
        return voice.name if voice else ""

        if self.state.config["elevenlabs_voice_name"]:
            self.combo_elvoice.configure(
                values=[self.state.config["elevenlabs_voice_name"]])
            self.combo_elvoice.set(self.state.config["elevenlabs_voice_name"])

    # ------------------------------------------------------------------
    def _refresh_key_location(self) -> None:
        """Zeigt, wo der Zugangsschlüssel abgelegt ist."""
        ort = self.state.config.elevenlabs_key_location
        if "Anmeldeinformationsspeicher" in ort:
            text = ("   Schlüssel liegt im Windows-Anmeldeinformationsspeicher - "
                    "einsehbar unter Systemsteuerung > "
                    "Anmeldeinformationsverwaltung > Windows-Anmeldeinformationen "
                    "> „DreameSprachpaket:ElevenLabs“. Die config.json enthält "
                    "ihn nicht.")
            stil = "Success.TLabel"
        elif "config.json" in ort:
            text = ("   Schlüssel liegt verschlüsselt in der config.json "
                    "(der Windows-Anmeldespeicher war nicht erreichbar).")
            stil = "Muted.TLabel"
        else:
            text = "   Schlüssel ist nicht gespeichert."
            stil = "Muted.TLabel"
        self.lbl_key_ort.configure(text=text, style=stil)

    def _on_forget_key(self) -> None:
        if not messagebox.askyesno(
                "Schlüssel vergessen",
                "Der gespeicherte ElevenLabs-Schlüssel wird entfernt - aus dem "
                "Windows-Anmeldespeicher und aus der config.json.\n\n"
                "Fortfahren?", parent=self):
            return
        self.state.config.forget_elevenlabs_key()
        self.state.save()
        self.var_key.set("")
        self._refresh_key_location()
        self.lbl_eleven.configure(text="   Schlüssel entfernt.",
                                  style="Muted.TLabel")

    def _open_api_key_page(self) -> None:
        messagebox.showinfo(
            "Zugangsschlüssel holen",
            "Es öffnet sich die Seite, auf der ElevenLabs den Schlüssel erzeugt.\n\n"
            "Dort auf 'Create API Key' klicken. Der Schlüssel wird nur ein "
            "einziges Mal vollständig angezeigt - sofort kopieren und hier "
            "einfügen.\n\n"
            "Falls die Seite nicht direkt aufgeht: unten links auf dein Profil, "
            "dann Settings > API Keys.\n\n"
            "Im Free-Plan ist das enthalten (10.000 Zeichen pro Monat).",
            parent=self)
        webbrowser.open(elevenlabs.API_KEY_URL)

    def _on_connect_elevenlabs(self) -> None:
        key = self.var_key.get().strip()
        if not key:
            show_warning(
                self, self.theme, "Zugangsschlüssel fehlt",
                "Lege dir ein kostenloses ElevenLabs-Konto an und kopiere den "
                "Zugangsschlüssel hier herein.",
                "Zu finden unter elevenlabs.io/app/settings/api-keys > "
                "Create API Key. Die App legt kein Konto für dich an.")
            return

        if not elevenlabs.looks_like_key(key):
            show_warning(
                self, self.theme, "Schlüssel sieht ungewöhnlich aus",
                "Der eingetragene Zugangsschlüssel beginnt nicht mit 'sk_'.",
                f"Eingetragen ist etwas mit {len(key)} Zeichen, das mit "
                f"'{key[:6]}…' anfängt. Falls das eine Stimmen-ID ist: die "
                f"gehört ins Feld darunter.\n\nDie Verbindung wird trotzdem "
                f"versucht - vielleicht hat ElevenLabs das Format geändert.")

        self.btn_connect.configure(state="disabled")
        self.lbl_eleven.configure(text="Verbinde ...", style="Muted.TLabel")

        def work(_task):
            quota = elevenlabs.check_key(key)
            voices = elevenlabs.list_voices(key)
            models = elevenlabs.list_models(key)
            return quota, voices, models

        def ok(result):
            quota, voices, models = result
            self.state.config.set_elevenlabs_key(key)
            self.state.save()
            self._set_eleven_voices(voices)
            self._set_models(models)
            self._refresh_key_location()

            needed = elevenlabs.estimate_characters(
                dialect.DIALECTS[0].texts) if dialect.DIALECTS else 0
            enough = quota.left >= needed
            self.lbl_eleven.configure(
                text=(f"   Verbunden. Kontingent: {quota.describe()}. "
                      f"Für das bayerische Paket werden rund {needed} Zeichen "
                      f"gebraucht - " +
                      ("das reicht." if enough else "das reicht derzeit nicht.")),
                style="Success.TLabel" if enough else "Warning.TLabel")

            eigene = [v for v in voices if v.is_own_creation]
            bavarian = [v for v in voices if v.is_bavarian]
            zusatz = f"\n   {len(voices)} Stimmen im Konto"
            if eigene:
                zusatz += f", davon {len(eigene)} selbst erzeugt (stehen oben)"
            elif not bavarian:
                zusatz += (". Keine davon ist als bayerisch ausgewiesen - die "
                           "Bibliotheksstimmen taugen dafür erfahrungsgemäss wenig. "
                           "Besser: in ElevenLabs mit Voice Design eine eigene "
                           "bauen und ihre ID unten eintragen.")
            self.lbl_eleven.configure(text=self.lbl_eleven.cget("text") + zusatz)

        def fail(exc):
            message, hint = error_text(exc)
            self.lbl_eleven.configure(text=f"   {message} {hint}".strip(),
                                      style="Danger.TLabel")

        run_async(self, work, on_success=ok, on_error=fail,
                  on_finally=lambda: self.btn_connect.configure(state="normal"))

    def _set_eleven_voices(self, voices, bevorzugt: str = "") -> None:
        """Füllt die Stimmenliste. Selbst erzeugte und bayerische zuerst."""
        self._eleven_voices = sorted(
            voices,
            key=lambda v: (not v.is_own_creation, not v.is_bavarian, v.name.lower()))
        self.combo_elvoice.configure(
            values=[v.label for v in self._eleven_voices])

        stored = bevorzugt or self.state.config["elevenlabs_voice_id"]
        chosen = next((v for v in self._eleven_voices if v.voice_id == stored), None)
        if chosen is None:
            chosen = next((v for v in self._eleven_voices if v.is_own_creation), None)
        if chosen is None:
            chosen = next((v for v in self._eleven_voices if v.is_bavarian), None)
        if chosen is None and self._eleven_voices:
            chosen = self._eleven_voices[0]
        if chosen is not None:
            self.combo_elvoice.set(chosen.label)
            self.var_voice_id.set(chosen.voice_id)

    def _set_models(self, models) -> None:
        """Füllt die Modellauswahl. Ein neueres Modell klingt oft lebendiger."""
        self._models = [{"id": m["id"], "label": f"{m['name']} ({m['id']})"}
                        for m in models]
        if not self._models:
            self._models = [{"id": elevenlabs.MODEL,
                             "label": f"Standard ({elevenlabs.MODEL})"}]

        self.combo_model.configure(values=[m["label"] for m in self._models])
        gespeichert = self.state.config["elevenlabs_model"] or elevenlabs.MODEL
        treffer = next((m for m in self._models if m["id"] == gespeichert), None)
        self.combo_model.set((treffer or self._models[0])["label"])

    def _selected_eleven_voice(self):
        label = self.combo_elvoice.get()
        return next((v for v in self._eleven_voices if v.label == label), None)

    def _on_elvoice_changed(self) -> None:
        """Hält das ID-Feld mit der Auswahl im Gleichklang."""
        voice = self._selected_eleven_voice()
        if voice is not None:
            self.var_voice_id.set(voice.voice_id)

    def _on_add_voice_id(self) -> None:
        """Übernimmt eine Stimme direkt über ihre ID."""
        key = self.var_key.get().strip() or self.state.config.elevenlabs_key
        voice_id = self.var_voice_id.get().strip()

        if not key:
            show_warning(self, self.theme, "Zugangsschlüssel fehlt",
                         "Trage zuerst deinen ElevenLabs-Schlüssel ein.")
            return
        if not voice_id:
            show_warning(
                self, self.theme, "Keine ID eingetragen",
                "Kopiere die ID deiner Stimme aus ElevenLabs hier herein.",
                "Du findest sie in der Stimmenübersicht: die drei Punkte an der "
                "Stimme anklicken und 'Copy Voice ID' wählen. Sie ist rund "
                "20 Zeichen lang.")
            return

        # Vertauschte Felder sind der haeufigste Stolperstein - lieber vorher
        # erkennen als eine unverstaendliche Serverantwort zeigen.
        if voice_id.startswith("sk_"):
            show_warning(
                self, self.theme, "Felder vertauscht?",
                "Im Feld für die Stimmen-ID steht ein Zugangsschlüssel.",
                "Schlüssel beginnen mit 'sk_', Stimmen-IDs nicht. Der "
                "Schlüssel gehört ins obere Feld, die Stimmen-ID hierher.")
            return
        if not elevenlabs.looks_like_key(key):
            show_warning(
                self, self.theme, "Schlüssel sieht ungewöhnlich aus",
                f"Der eingetragene Zugangsschlüssel beginnt nicht mit 'sk_'.",
                f"Eingetragen ist etwas mit {len(key)} Zeichen, das mit "
                f"'{key[:6]}…' anfängt. Ein ElevenLabs-Schlüssel sieht so aus: "
                f"sk_ gefolgt von rund 45 weiteren Zeichen.\n\n"
                f"Neuen Schlüssel holen: elevenlabs.io/app/settings/api-keys "
                f"> Create API Key. Er wird nur einmal vollständig angezeigt.")
            return

        self.btn_add_id.configure(state="disabled")
        self.lbl_eleven.configure(text="   Hole die Stimme ...", style="Muted.TLabel")

        def work(_task):
            voice = elevenlabs.get_voice(key, voice_id)
            alle = elevenlabs.list_voices(key)
            return voice, alle

        def ok(result):
            voice, alle = result
            # Die geholte Stimme nach vorne, Doppelte vermeiden.
            rest = [v for v in alle if v.voice_id != voice.voice_id]
            self._set_eleven_voices([voice] + rest, bevorzugt=voice.voice_id)

            self.state.config.set_elevenlabs_key(key)
            self.state.config["elevenlabs_voice_id"] = voice.voice_id
            self.state.config["elevenlabs_voice_name"] = voice.label
            self.state.save()

            self.lbl_eleven.configure(
                text=f"   '{voice.name}' ist ausgewählt. Hör sie dir mit "
                     f"'Kostprobe anhören' an.",
                style="Success.TLabel")

        def fail(exc):
            message, hint = error_text(exc)
            self.lbl_eleven.configure(text=f"   {message} {hint}".strip(),
                                      style="Danger.TLabel")
            show_error(self, self.theme, "Stimme nicht gefunden",
                       message + (f"\n\n{hint}" if hint else ""))

        run_async(self, work, on_success=ok, on_error=fail,
                  on_finally=lambda: self.btn_add_id.configure(state="normal"))

    # ------------------------------------------------------------------
    def _on_search_bavarian(self) -> None:
        key = self.var_key.get().strip() or self.state.config.elevenlabs_key
        if not key:
            messagebox.showinfo("Zugangsschlüssel fehlt",
                                "Trage zuerst deinen ElevenLabs-Schlüssel ein.",
                                parent=self)
            return

        self.btn_search.configure(state="disabled")
        self.lbl_eleven.configure(text="   Durchsuche die Stimmenbibliothek ...",
                                  style="Muted.TLabel")

        def work(_task):
            return elevenlabs.search_bavarian_voices(key)

        def ok(found):
            if not found:
                self.lbl_eleven.configure(
                    text=("   In der Bibliothek war gerade keine als bayerisch "
                          "ausgewiesene Stimme zu finden. Am besten baust du dir "
                          "in ElevenLabs selbst eine (Voice Design) und trägst "
                          "ihre ID unten ein."),
                    style="Warning.TLabel")
                webbrowser.open(elevenlabs.LIBRARY_URL)
                return
            self._show_voice_chooser(key, found)

        def fail(exc):
            message, hint = error_text(exc)
            self.lbl_eleven.configure(text=f"   {message} {hint}".strip(),
                                      style="Danger.TLabel")

        run_async(self, work, on_success=ok, on_error=fail,
                  on_finally=lambda: self.btn_search.configure(state="normal"))

    def _show_voice_chooser(self, key: str, found: list) -> None:
        """Lässt den Nutzer auswählen, welche Stimme übernommen wird."""
        window = tk.Toplevel(self)
        window.title("Stimme auswählen")
        window.configure(bg=self.theme.color("bg"))
        window.geometry("760x560")
        window.transient(self)
        window.grab_set()

        card = Card(window, self.theme, f"{len(found)} Stimmen gefunden",
                    "Wähle die Stimme, die in dein ElevenLabs-Konto übernommen "
                    "werden soll. Anhören kannst du sie danach mit 'Kostprobe'.")
        card.pack(fill="both", expand=True, padx=16, pady=16)

        liste = ScrollableList(card.content, self.theme)
        liste.pack(fill="both", expand=True)

        gewaehlt = tk.StringVar(value=found[0].voice_id)
        for voice in found:
            block = ttk.Frame(liste.inner, style="Card.TFrame")
            block.pack(fill="x", padx=4, pady=(0, 6))
            ttk.Radiobutton(block, text=voice.details, variable=gewaehlt,
                            value=voice.voice_id).pack(anchor="w")
            if voice.preview_url:
                ttk.Button(
                    block, text="bei ElevenLabs anhören", style="Link.TButton",
                    command=lambda u=voice.preview_url: webbrowser.open(u)
                ).pack(anchor="w", padx=(24, 0))
            ttk.Frame(block, style="Separator.TFrame", height=1).pack(
                fill="x", pady=(6, 0))

        buttons = ttk.Frame(window, style="TFrame")
        buttons.pack(fill="x", padx=16, pady=(0, 16))

        def uebernehmen() -> None:
            voice = next((v for v in found if v.voice_id == gewaehlt.get()), None)
            window.destroy()
            if voice is not None:
                self._add_voice(key, voice)

        ttk.Button(buttons, text="Ausgewählte Stimme übernehmen",
                   style="Accent.TButton", command=uebernehmen).pack(side="left")
        ttk.Button(buttons, text="Abbrechen",
                   command=window.destroy).pack(side="left", padx=(8, 0))
        ttk.Label(buttons,
                  text=("Keine passt? Bau dir in ElevenLabs mit Voice Design eine "
                        "eigene und trage ihre ID im Feld unten ein."),
                  style="MutedBg.TLabel", wraplength=380,
                  justify="left").pack(side="left", padx=(16, 0))

    def _add_voice(self, key: str, voice) -> None:
        def work(_task):
            elevenlabs.add_shared_voice(key, voice)
            return elevenlabs.list_voices(key)

        def ok(voices):
            self._set_eleven_voices(voices)
            self.lbl_eleven.configure(
                text=f"   '{voice.name}' ist jetzt in deinem Konto und ausgewählt.",
                style="Success.TLabel")

        def fail(exc):
            message, hint = error_text(exc)
            self.lbl_eleven.configure(text=f"   {message} {hint}".strip(),
                                      style="Danger.TLabel")

        run_async(self, work, on_success=ok, on_error=fail)

    # ------------------------------------------------------------------
    def generate_dialect(self, pack) -> None:
        """Spricht ein Dialektpaket und baut es auf das Originalpaket."""
        if not self.state.has_base_pack:
            messagebox.showwarning(
                "Originalpaket fehlt",
                "Lade zuerst unter 'Einzelne Ansagen' das offizielle Sprachpaket deines Roboters "
                "herunter - es ist die Grundlage jedes Pakets.",
                parent=self)
            return

        engine = self.var_engine.get()
        api_key = ""
        voice_id = ""
        win_voice = ""

        if engine == dialect.ENGINE_ELEVENLABS:
            api_key = self.var_key.get().strip() or self.state.config.elevenlabs_key
            chosen = self._selected_eleven_voice()
            if not api_key:
                messagebox.showwarning(
                    "Zugangsschlüssel fehlt",
                    "Trage deinen ElevenLabs-Schlüssel ein und klicke auf "
                    "'Verbinden und Stimmen laden'.", parent=self)
                return
            if chosen is None:
                messagebox.showwarning(
                    "Keine Stimme gewählt",
                    "Klicke auf 'Verbinden und Stimmen laden' und wähle danach "
                    "eine Stimme aus - am besten eine bayerische.", parent=self)
                return
            voice_id = chosen.voice_id
            # Bei selbst erzeugten Stimmen sagen die Merkmale nichts über den
            # Dialekt aus - da weiss der Nutzer besser Bescheid als die Labels.
            if (not chosen.is_bavarian and not chosen.is_own_creation
                    and not messagebox.askyesno(
                        "Keine bayerische Stimme",
                        f"'{chosen.name}' ist nicht als bayerisch ausgewiesen. Das "
                        f"Ergebnis klingt dann nicht nach Dialekt.\n\nTrotzdem "
                        f"fortfahren?", parent=self)):
                return
        else:
            if not tts.german_voices():
                messagebox.showwarning(
                    "Keine deutsche Stimme",
                    "Es ist keine deutsche Sprachausgabe installiert.\n\n"
                    "Windows-Einstellungen > Zeit und Sprache > Sprache > Deutsch > "
                    "Optionen > Sprachausgabe hinzufügen. Danach die App neu "
                    "starten.", parent=self)
                return
            win_voice = self._selected_win_voice()

        if not self.state.ffmpeg:
            messagebox.showwarning(
                "ffmpeg fehlt",
                "Zum Umwandeln der gesprochenen Ansagen wird ffmpeg gebraucht.\n\n"
                "Wechsle kurz unter 'Einzelne Ansagen' - dort richtet die App es ein.",
                parent=self)
            return

        # Der Ablageort enthält Stimme, Dienst und Klangeinstellung. Sonst
        # würde nach einem Wechsel das alte Audio wiederverwendet - und beim
        # Fortsetzen nach aufgebrauchtem Kontingent landeten zwei
        # verschiedene Klangbilder im selben Paket.
        # Muss vor der Rückfrage stehen: dort wird schon gezeigt, wie weit
        # ein früherer Lauf gekommen ist.
        tempo, hoehe = self._win_klang()
        work = self._work_dir(pack)

        schon_da = dialect.spoken_count(work)
        offen = dialect.remaining_texts(pack, work)

        if engine == dialect.ENGINE_ELEVENLABS:
            chars = elevenlabs.estimate_characters(offen)

            # Kontingent abfragen, damit vorher klar ist, wie weit es reicht.
            rest = None
            try:
                rest = elevenlabs.check_key(api_key).left
            except Exception:
                pass

            question = (f"Bereits gesprochen: {schon_da} von {pack.count} "
                        f"Ansagen.\nNoch offen: {len(offen)} "
                        f"({chars} Zeichen).\n\n")

            if rest is not None:
                question += f"Dein Kontingent: {rest} Zeichen frei.\n"
                if rest < chars:
                    passt = 0
                    verbraucht = 0
                    for _i, t in sorted(offen.items()):
                        if verbraucht + len(t) > rest:
                            break
                        verbraucht += len(t)
                        passt += 1
                    question += (
                        f"\nDAS REICHT NICHT FÜR ALLES: etwa {passt} der "
                        f"{len(offen)} offenen Ansagen sind machbar.\n\n"
                        f"Die App bricht deshalb nicht ab. Sie spricht so viel "
                        f"wie möglich, baut das Paket damit, und der Rest bleibt "
                        f"auf Hochdeutsch. Nächsten Monat einfach wieder auf "
                        f"'Paket erzeugen' klicken - dann macht sie genau hier "
                        f"weiter und spricht nur noch das Fehlende.\n")
                else:
                    question += "\nDas reicht für alles Offene.\n"

            question += ("\nÜbertragen werden nur die Ansagetexte, keine "
                         "persönlichen Daten.\n\nFortfahren?")
        else:
            question = (
                f"Die App spricht jetzt {len(offen)} Ansagen auf {pack.name} und "
                f"baut daraus ein Sprachpaket."
                + (f"\n\n{schon_da} sind schon gesprochen und werden "
                   f"übersprungen." if schon_da else "")
                + f"\n\nDas dauert ein paar Minuten und passiert vollständig auf "
                  f"diesem PC - es wird nichts hochgeladen.\n\nFortfahren?")

        if not messagebox.askyesno(f"{pack.name} erzeugen?", question, parent=self):
            return

        # ---- Name des Pakets -------------------------------------------
        # Wichtig: jede Stimme bekommt ihre eigene Datei. Sonst überschreibt
        # ein Testlauf mit einer Windows-Stimme das Paket, das vorher mit
        # bezahltem ElevenLabs-Kontingent entstanden ist.
        if engine == dialect.ENGINE_ELEVENLABS:
            stimmen_label = (self._selected_eleven_voice().name
                             if self._selected_eleven_voice() else "")
        else:
            stimmen_label = win_voice
        vorschlag = library.suggest_name(pack.name, engine, stimmen_label)

        gewuenscht = simpledialog.askstring(
            "Name für dieses Paket",
            "Unter welchem Namen soll das Paket gespeichert werden?\n\n"
            "Der Vorschlag enthält Dialekt und Stimme, damit mehrere "
            "Fassungen nebeneinander liegen können. Ein vorhandenes Paket "
            "wird nie überschrieben - notfalls hängt die App eine Zahl an.",
            initialvalue=vorschlag, parent=self)
        if gewuenscht is None:
            return
        dateiname = library.safe_name(gewuenscht) or vorschlag
        ziel_pfad = library.unique_path(build_dir(), dateiname)
        out_name = ziel_pfad.name

        # Auswahl merken
        self.state.config["tts_engine"] = engine
        self.state.config["tts_voice"] = win_voice
        if engine == dialect.ENGINE_ELEVENLABS:
            self.state.config.set_elevenlabs_key(api_key)
            self.state.config["elevenlabs_voice_id"] = voice_id
            chosen = self._selected_eleven_voice()
            self.state.config["elevenlabs_voice_name"] = chosen.label if chosen else ""
            modell_speichern, _, _ = self._eleven_klang()
            self.state.config["elevenlabs_model"] = modell_speichern
            self.state.config["elevenlabs_use_voice_settings"] = \
                self.var_own_settings.get()
            self.state.config["elevenlabs_stability"] = round(
                self.var_stability.get(), 2)
            self.state.config["elevenlabs_style"] = round(self.var_style.get(), 2)
        self.state.save()

        base = self.state.base_pack_path
        ffmpeg = self.state.ffmpeg

        self.log.clear()
        self.log.append(f"Erzeuge Dialektpaket: {pack.name}", "step")
        # Das Sprechen hört auf den Abbruch - hier darf der Knopf mitspielen.
        self._busy(True, abbrechbar=True)
        self.badge.set("Spreche die Ansagen ...", "muted")

        modell, klang, eigene = self._eleven_klang()

        def work_fn(task):
            return dialect.generate(
                dialect=pack, base_pack=base, work_dir=work, ffmpeg=ffmpeg,
                voice=win_voice, engine=engine, api_key=api_key, voice_id=voice_id,
                model=modell, voice_settings=klang, use_voice_settings=eigene,
                mapping=self.state.voice_mapping(),
                out_name=out_name,
                rate=tempo, pitch=hoehe,
                log=lambda m: self._log(m),
                progress=lambda d, t: to_main(
                    self, self.progress.configure,
                    {"value": (d / t * 100) if t else 0}),
                cancelled=lambda: task.cancelled,
            )

        def ok(build) -> None:
            self.state.last_build = build
            self.state.prebuilt = build
            self.state.prebuilt_name = pack.name
            self.state.config["custom_lang_id"] = pack.lang_id
            self.state.save()
            self.state.notify("assignments_changed")

            # Beschreibung daneben legen, damit unter 'Fertige Stimmen' erkennbar bleibt,
            # welche Stimme in welchem Paket steckt.
            library.write_info(
                build.path, dialect=pack.name, engine=(
                    "ElevenLabs" if engine == dialect.ENGINE_ELEVENLABS
                    else "Windows-Sprachausgabe"),
                voice=stimmen_label, lang_id=pack.lang_id,
                replaced=len(build.replaced), total=pack.count)

            vollstaendig = len(build.replaced) >= pack.count
            self.badge.set(f"Fertig - {len(build.replaced)} Ansagen auf "
                           f"{pack.name}", "ok" if vollstaendig else "warn")
            self.log.append(build.summary(), "ok")
            for warnung in build.warnings:
                self.log.append(warnung, "warn")

            hinweis = ""
            if not vollstaendig:
                hinweis = (f"\n\n{pack.count - len(build.replaced)} Ansagen fehlen "
                           f"noch - vermutlich war das ElevenLabs-Kontingent "
                           f"aufgebraucht. Das Gesprochene ist gespeichert: starte "
                           f"die Erzeugung im nächsten Monat einfach erneut, dann "
                           f"macht die App genau dort weiter.")

            messagebox.showinfo(
                f"{pack.name} ist fertig",
                f"{len(build.replaced)} Ansagen sprechen jetzt {pack.name}, der "
                f"Rest bleibt auf Hochdeutsch.{hinweis}\n\n"
                f"Gespeichert als:\n{build.path.name}\n\n"
                f"Frühere Pakete bleiben erhalten. Wechsle unter 'Fertige Stimmen' - dort "
                f"wählst du aus, welches installiert wird.",
                parent=self)

        def fail(exc: Exception) -> None:
            # Ein selbst ausgelöster Abbruch ist kein Fehler und darf sich
            # auch nicht so anfühlen.
            if getattr(self, "_task", None) is not None and self._task.cancelled:
                gesprochen = dialect.spoken_count(work)
                self.badge.set("Abgebrochen", "warn")
                self.log.append("Vorgang abgebrochen.", "warn")
                show_info(
                    self, self.theme, "Abgebrochen",
                    f"Es wurde kein Paket gebaut.",
                    f"{gesprochen} von {pack.count} Ansagen sind gesprochen "
                    f"und bleiben gespeichert."
                    + (" Das dafür verbrauchte ElevenLabs-Kontingent ist weg, "
                       "aber beim nächsten Anlauf macht die App genau hier "
                       "weiter und fordert nur noch das Fehlende an."
                       if engine == dialect.ENGINE_ELEVENLABS else
                       " Beim nächsten Anlauf macht die App genau hier weiter."))
                return

            message, hint = error_text(exc)
            self.badge.set("Fehlgeschlagen", "error")
            self.log.append(message, "error")
            if hint:
                self.log.append(hint, "warn")
            show_error(self, self.theme, "Fehler",
                       message + (f"\n\n{hint}" if hint else ""))

        self._task = run_async(self, work_fn, on_success=ok, on_error=fail,
                               on_finally=lambda: self._busy(False))

    # ------------------------------------------------------------------
    def _on_cancel_work(self) -> None:
        """Bricht einen laufenden Vorgang ab.

        Beim Sprechen über ElevenLabs zählt jede Ansage Kontingent. Wer
        sich verklickt hat, soll nicht zusehen müssen, wie sein Guthaben
        verbraucht wird. Bereits gesprochene Ansagen bleiben gespeichert -
        ihr Kontingent ist ohnehin weg, und beim nächsten Anlauf macht die
        App genau dort weiter.
        """
        task = getattr(self, "_task", None)
        if task is None or task.cancelled:
            return
        task.cancel()
        self.btn_abbrechen.configure(state="disabled")
        self.badge.set("Wird abgebrochen ...", "warn")
        self.log.append("Abbruch angefordert - die laufende Ansage wird noch "
                        "zu Ende gesprochen.", "warn")

    def _busy(self, active: bool, abbrechbar: bool = False) -> None:
        """Sperrt die Bedienung während der Arbeit.

        `abbrechbar` schaltet den Abbrechen-Knopf frei. Er bleibt gesperrt,
        wenn der laufende Vorgang gar nicht auf einen Abbruch hört - ein
        Knopf, der nichts tut, ist schlimmer als keiner.
        """
        state = "disabled" if active else "normal"
        for child in self.list_frame.winfo_children():
            if isinstance(child, PackCard):
                child.btn_use.configure(state=state)
        for button in self._dialect_buttons:
            button.configure(state=state)
        self.btn_abbrechen.configure(
            state="normal" if (active and abbrechbar) else "disabled")
        if not active:
            self._task = None
        if active:
            self.progress.pack(side="right")
            self.progress.configure(value=0)
        else:
            self.progress.pack_forget()

    def _log(self, message: str, kind: str = "info") -> None:
        to_main(self, self.log.append, message, kind)

    # ------------------------------------------------------------------
    def use_pack(self, pack: CommunityPack) -> None:
        if not self.state.has_base_pack:
            messagebox.showwarning(
                "Originalpaket fehlt",
                "Lade zuerst unter 'Einzelne Ansagen' das offizielle "
                "Sprachpaket deines Roboters herunter. Erst damit kann ein "
                "Fremdpaket sicher auf dein Modell angepasst werden.",
                parent=self)
            return

        if not messagebox.askyesno(
                f"'{pack.name}' verwenden?",
                f"Das Paket wird von folgender Quelle geladen:\n\n{pack.url}\n\n"
                f"Anschließend wird es auf das offizielle Paket deines Modells "
                f"gelegt. Danach kannst du es im Tab 'Upload & Installation' "
                f"installieren.\n\nFortfahren?",
                parent=self):
            return

        base = self.state.base_pack_path
        self.log.clear()
        self.log.append(f"Lade '{pack.name}' von {pack.project_url}", "step")
        self._busy(True)
        self.badge.set("Lade herunter ...", "muted")

        def report(done: int, total: int) -> None:
            percent = (done / total * 100) if total else 0
            to_main(self, self.progress.configure, {"value": percent})

        def work(_task):
            archive = community.download(pack, progress=report)
            self._log(f"Heruntergeladen: {archive.name}", "ok")
            self._log("Passe das Paket auf dein Modell an ...", "step")
            return packer.overlay_pack(
                base_pack=base,
                overlay_pack_path=archive,
                out_name=f"community_{pack.key}.tar.gz",
                mapping=self.state.voice_mapping(),
                log=lambda m: self._log(m),
                progress=lambda d, t: to_main(
                    self, self.progress.configure,
                    {"value": (d / t * 100) if t else 0}),
            )

        def ok(build: packer.BuildResult) -> None:
            self.state.last_build = build
            self.state.prebuilt = build
            self.state.prebuilt_name = pack.name
            self.state.notify("assignments_changed")

            covered = len(build.replaced)
            total = build.total_members or covered
            self.badge.set(f"Bereit - {covered} von {total} Ansagen ersetzt", "ok")
            self.log.append(build.summary(), "ok")
            for warning in build.warnings:
                self.log.append(warning, "warn")

            suggestion = pack.key.split("_")[0].upper()[:8] or "CUSTOM"
            self.state.config["custom_lang_id"] = installer.validate_lang_id(
                suggestion)[0]
            self.state.save()

            messagebox.showinfo(
                "Paket vorbereitet",
                f"'{pack.name}' wurde auf dein Modell angepasst.\n\n"
                f"{covered} von {total} Ansagen bekommen die neue Stimme, der Rest "
                f"bleibt auf Deutsch.\n\nWechsle jetzt in den Tab "
                f"'Upload & Installation' und klicke auf "
                f"'Sprachpaket auf Roboter installieren'.",
                parent=self)

        def fail(exc: Exception) -> None:
            message, hint = error_text(exc)
            self.badge.set("Fehlgeschlagen", "error")
            self.log.append(message, "error")
            if hint:
                self.log.append(hint, "warn")
            show_error(self, self.theme, "Fehler",
                       message + (f"\n\n{hint}" if hint else ""))

        run_async(self, work, on_success=ok, on_error=fail,
                  on_finally=lambda: self._busy(False))
