"""Eine Stimme wählen, anhören und aufspielen - an einem Ort.

Das war bisher auf zwei Reiter verteilt: In Tab 4 suchte man den Dialekt
aus, in Tab 3 spielte man ihn auf. Dass beides zusammengehört, stand
nirgends - und weil beide Reiter einen fast gleich benannten Knopf für
"fertiges Paket" hatten, landete man leicht im falschen.

Hier ist es eine Handlung: Liste, Probe, Knopf. Was zur Auswahl steht,
kommt aus drei Quellen und ist als solche gekennzeichnet:

* **mitgeliefert** - die vier Dialekte aus der EXE (dialektpakete.py)
* **gebaut** - was in dieser App schon entstanden ist (library.py)
* **selbst erzeugen** - Verweis auf die Seite für eigene Stimmen

Aufgespielt wird über dieselben Bausteine wie bisher: `packer.build_pack`
baut das Paket auf das eigene Modell, `installer.install_pack` schickt es
weg. Der Roboter lädt es dabei vom PC über das lokale Netz.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Tuple

from .. import dialektpakete, importer, installer, library, packer, vorhoeren
from ..paths import build_dir
from .state import AppState, Task, error_text, run_async, to_main
from .theme import Theme
from .widgets import (Card, LogView, ScrollablePage, StatusBadge, show_error,
                      show_info, show_warning)

_LOG = logging.getLogger(__name__)

QUELLE_MITGELIEFERT = "Dialekt"
QUELLE_GEBAUT = "Eigenes"


class Auswahl:
    """Ein Eintrag in der Stimmenliste."""

    def __init__(self, key: str, name: str, art: str, beschreibung: str,
                 kennung: str = "CUSTOM",
                 dialekt=None, paket: Optional[Path] = None) -> None:
        self.key = key
        self.name = name
        self.art = art
        self.beschreibung = beschreibung
        # Jede Stimme bringt ihre eigene Kennung mit. Frueher stand hier
        # immer der zuletzt benutzte Wert aus der Konfiguration - wer
        # einmal Hessisch aufgespielt hatte, bekam "HESSEN" auch bei
        # Bayerisch angeboten.
        self.kennung = kennung
        self.dialekt = dialekt          # FertigerDialekt oder None
        self.paket = paket              # fertiges .tar.gz oder None

    @property
    def label(self) -> str:
        return f"{self.art} · {self.name}"


class VoicePage(ttk.Frame):
    """Stimme aussuchen, anhören, auf den Roboter bringen."""

    def __init__(self, master, theme: Theme, state: AppState,
                 gehe_zu=None) -> None:
        super().__init__(master, style="TFrame")
        self.theme = theme
        self.state = state
        self.gehe_zu = gehe_zu or (lambda _key: None)

        self._auswahl: List[Auswahl] = []
        self._task: Optional[Task] = None
        #: Laeuft gerade eine Probe? Dann ist der Anhoeren-Knopf der
        #: Stopp-Knopf.
        self._probe_laeuft: Optional[Task] = None
        #: Je Stimme die schon umgewandelten Ansagen - ein zweiter Klick
        #: spart Auspacken und ffmpeg.
        self._probe_puffer: Dict[str, Dict[int, Path]] = {}

        self.var_stimme = tk.StringVar()
        self.var_lang = tk.StringVar(value=state.config["custom_lang_id"] or "CUSTOM")

        self._build()
        self.refresh()

        self.state.subscribe("base_pack_changed", self.refresh)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        page = ScrollablePage(self, self.theme)
        page.pack(fill="both", expand=True)
        outer = page.body()

        ttk.Label(outer, text="Fertige Stimmen", style="Title.TLabel"
                  ).pack(anchor="w")
        ttk.Label(
            outer,
            text=("Aussuchen, anhören, aufspielen. Die vier Dialekte sind in der "
                  "App enthalten - es wird nichts heruntergeladen."),
            style="MutedBg.TLabel", wraplength=760, justify="left"
        ).pack(anchor="w", pady=(3, 16))

        # -- Auswahl ---------------------------------------------------
        card = Card(outer, self.theme, "Welche Stimme?")
        card.pack(fill="x")

        reihe = ttk.Frame(card.content, style="Card.TFrame")
        reihe.pack(fill="x")
        self.combo = ttk.Combobox(reihe, textvariable=self.var_stimme,
                                  state="readonly", width=52)
        self.combo.pack(side="left")
        self.combo.bind("<<ComboboxSelected>>", self._on_pick)

        self.btn_probe = ttk.Button(reihe, text="▶ Anhören",
                                    command=self._on_probe)
        self.btn_probe.pack(side="left", padx=(10, 0))

        self.lbl_beschreibung = ttk.Label(card.content, text="",
                                          style="Muted.TLabel",
                                          wraplength=700, justify="left")
        self.lbl_beschreibung.pack(anchor="w", pady=(10, 0))

        self.lbl_probe = ttk.Label(card.content, text="", style="Surface.TLabel",
                                   wraplength=700, justify="left")
        self.lbl_probe.pack(anchor="w", pady=(6, 0))

        # -- Aufspielen ------------------------------------------------
        card2 = Card(outer, self.theme, "Auf den Roboter bringen")
        card2.pack(fill="x", pady=(14, 0))

        kennung = ttk.Frame(card2.content, style="Card.TFrame")
        kennung.pack(fill="x")
        ttk.Label(kennung, text="Kennung", style="Surface.TLabel",
                  width=11, anchor="w").pack(side="left")
        ttk.Entry(kennung, textvariable=self.var_lang, width=12).pack(side="left")
        ttk.Label(kennung,
                  text=("Jede Stimme bringt ihre eigene mit. Solange es keine "
                        "offizielle Sprachkennung ist, bleibt die deutsche "
                        "Originalstimme unangetastet."),
                  style="Muted.TLabel", wraplength=440, justify="left"
                  ).pack(side="left", padx=(10, 0))

        knoepfe = ttk.Frame(card2.content, style="Card.TFrame")
        knoepfe.pack(fill="x", pady=(14, 0))
        self.btn_los = ttk.Button(knoepfe, text="Aufspielen",
                                  style="Accent.TButton", command=self._on_install)
        self.btn_los.pack(side="left")
        self.btn_abbruch = ttk.Button(knoepfe, text="Abbrechen", state="disabled",
                                      command=self._on_cancel)
        self.btn_abbruch.pack(side="left", padx=(8, 0))
        self.badge = StatusBadge(knoepfe, self.theme, "Bereit")
        self.badge.pack(side="left", padx=(12, 0))

        self.progress = ttk.Progressbar(card2.content, mode="determinate",
                                        maximum=100)
        self.progress.pack(fill="x", pady=(12, 6))

        self.log = LogView(card2.content, self.theme, height=10)
        self.log.pack(fill="both", expand=True)

        hinweis = ttk.Frame(outer, style="TFrame")
        hinweis.pack(fill="x", pady=(14, 0))
        ttk.Label(
            hinweis,
            text=("Du willst eine eigene Stimme, einen anderen Dialekt oder "
                  "eigene Aufnahmen?"),
            style="MutedBg.TLabel").pack(side="left")
        ttk.Button(hinweis, text="Eigene Stimme bauen", style="Small.TButton",
                   command=lambda: self.gehe_zu("eigene")
                   ).pack(side="left", padx=(10, 0))

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Liest zusammen, was gerade zur Auswahl steht."""
        vorher = self.var_stimme.get()
        self._auswahl = self._sammeln()
        beschriftungen = [a.label for a in self._auswahl]
        self.combo.configure(values=beschriftungen)

        if vorher in beschriftungen:
            self.var_stimme.set(vorher)
        elif beschriftungen:
            self.var_stimme.set(beschriftungen[0])
        else:
            self.var_stimme.set("")
        self._on_pick()

    def _sammeln(self) -> List[Auswahl]:
        eintraege: List[Auswahl] = []

        for d in dialektpakete.KATALOG:
            quelle = dialektpakete.quelle(d)
            if quelle == dialektpakete.QUELLE_FEHLT:
                continue
            woher = {
                dialektpakete.QUELLE_MITGELIEFERT: "in der App enthalten",
                dialektpakete.QUELLE_GELADEN: "heruntergeladene Fassung",
                dialektpakete.QUELLE_PROJEKTORDNER: "aus dem Projektordner",
            }.get(quelle, "")
            eintraege.append(Auswahl(
                key=f"dialekt:{d.key}", name=d.name, art=QUELLE_MITGELIEFERT,
                beschreibung=f"{d.beschreibung}  ({d.ansagen} Ansagen, "
                             f"{d.stimme}, {woher})",
                kennung=d.kennung, dialekt=d))

        for info in library.list_packs(build_dir()):
            # Selbst gebaute Pakete tragen ihre Kennung in der
            # Beschreibungsdatei. Fehlt sie - etwa bei einem von Hand
            # hineinkopierten Paket -, bleibt es bei CUSTOM.
            eintraege.append(Auswahl(
                key=f"paket:{info.path.name}",
                name=info.dialect or info.path.stem,
                art=QUELLE_GEBAUT,
                beschreibung=info.label,
                kennung=(info.lang_id or "CUSTOM").strip().upper(),
                paket=info.path))

        return eintraege

    def _gewaehlt(self) -> Optional[Auswahl]:
        label = self.var_stimme.get()
        return next((a for a in self._auswahl if a.label == label), None)

    def _on_pick(self, _event=None) -> None:
        wahl = self._gewaehlt()
        self.lbl_probe.configure(text="")
        if wahl is None:
            self.lbl_beschreibung.configure(
                text="Es steht noch keine fertige Stimme bereit.")
            return
        self.lbl_beschreibung.configure(text=wahl.beschreibung)
        self.var_lang.set(wahl.kennung)

    # -- Anhören --------------------------------------------------------
    def _quelle_holen(self, wahl: Auswahl) -> Optional[Path]:
        """Der Pfad zu den Aufnahmen bzw. zum fertigen Paket."""
        if wahl.paket is not None:
            return wahl.paket
        if wahl.dialekt is not None:
            return dialektpakete.beschaffen(wahl.dialekt,
                                            log=lambda m: self._log(m))
        return None

    def _on_probe(self) -> None:
        # Läuft gerade eine Probe, ist derselbe Knopf der Stopp-Knopf.
        # Zwölf Sekunden zuhören zu müssen, weil man sich verklickt hat,
        # wäre die unfreundlichste Art, eine Vorschau anzubieten.
        if self._probe_laeuft is not None:
            self._probe_laeuft.cancel()
            return

        wahl = self._gewaehlt()
        if wahl is None:
            return

        ffmpeg = self.state.ffmpeg
        katalog = self.state.catalog
        # Einmal umgewandelte Ansagen werden gemerkt: Beim zweiten Klick
        # auf dieselbe Stimme entfällt Auspacken und ffmpeg.
        gemerkt = self._probe_puffer.get(wahl.key)
        self.lbl_probe.configure(
            text="Spiele ab ..." if gemerkt else "Bereite die Probe vor ...")
        self.btn_probe.configure(text="■ Stopp")
        aufgabe = Task()
        self._probe_laeuft = aufgabe

        def work(task: Task):
            proben = gemerkt
            if proben is None:
                quelle = self._quelle_holen(wahl)
                if quelle is None:
                    return None
                proben = vorhoeren.probe_vorbereiten(quelle, ffmpeg,
                                                     log=lambda m: self._log(m))
                if not proben:
                    return {}
            if task.cancelled:
                return proben

            nummern = sorted(proben)
            reihenfolge = [proben[n] for n in nummern]

            def melde(index: int) -> None:
                to_main(self, self.lbl_probe.configure,
                        {"text": f"▶ {index + 1}/{len(nummern)}  "
                                 f"{vorhoeren.beschriftung(nummern[index], katalog)}"})

            vorhoeren.abspielen(reihenfolge,
                                cancelled=lambda: task.cancelled,
                                melden=melde)
            return proben

        def ok(proben) -> None:
            if proben is None:
                self.lbl_probe.configure(text="")
                show_warning(
                    self, self.theme, "Aufnahmen nicht gefunden",
                    f"Die Aufnahmen für {wahl.name} ließen sich nicht öffnen.")
                return
            if not proben:
                self.lbl_probe.configure(text="")
                show_warning(
                    self, self.theme, "Keine Probe möglich",
                    "Aus dieser Stimme ließ sich keine Ansage entnehmen.",
                    "Zum Anhören wird ffmpeg gebraucht. Es steckt in der EXE "
                    "und wird beim ersten Bedarf ausgepackt.")
                return
            self._probe_puffer[wahl.key] = proben
            if aufgabe.cancelled:
                self.lbl_probe.configure(text="Probe abgebrochen.")
            else:
                self.lbl_probe.configure(
                    text=f"{len(proben)} Ansagen angehört. "
                         f"Klingt gut? Dann unten aufspielen.")

        def fail(exc: Exception) -> None:
            self.lbl_probe.configure(text="")
            nachricht, hinweis = error_text(exc)
            show_error(self, self.theme, "Probe fehlgeschlagen", nachricht, hinweis)

        def fertig() -> None:
            self._probe_laeuft = None
            self.btn_probe.configure(text="▶ Anhören")

        run_async(self, work, on_success=ok, on_error=fail, on_finally=fertig,
                  task=aufgabe)

    # -- Aufspielen -----------------------------------------------------
    def _log(self, nachricht: str, art: str = "info") -> None:
        to_main(self, self.log.append, nachricht, art)

    def _step(self, nachricht: str, anteil: float) -> None:
        def anwenden() -> None:
            self.progress.configure(value=max(0.0, min(1.0, anteil)) * 100)
            self.badge.set(nachricht, "muted")
        to_main(self, anwenden)

    def _busy(self, aktiv: bool) -> None:
        self.btn_los.configure(state="disabled" if aktiv else "normal")
        self.btn_probe.configure(state="disabled" if aktiv else "normal")
        self.btn_abbruch.configure(state="normal" if aktiv else "disabled")

    def _on_cancel(self) -> None:
        if self._task:
            self._task.cancel()
            self.log.append("Abbruch angefordert ...", "warn")

    def _on_install(self) -> None:
        wahl = self._gewaehlt()
        if wahl is None:
            show_warning(self, self.theme, "Keine Stimme gewählt",
                         "Wähle oben aus, wie dein Roboter klingen soll.")
            return
        if not self.state.connected:
            show_warning(self, self.theme, "Nicht verbunden",
                         "Melde dich auf der Startseite an und wähle deinen "
                         "Roboter.")
            return
        if not self.state.has_base_pack:
            show_warning(self, self.theme, "Originalpaket fehlt",
                         "Das offizielle Sprachpaket deines Roboters wird auf "
                         "der Startseite einmalig geholt.")
            return

        kennung = self.var_lang.get().strip().upper() or "CUSTOM"
        try:
            kennung, warnung = installer.validate_lang_id(kennung)
        except Exception as exc:                       # noqa: BLE001
            nachricht, hinweis = error_text(exc)
            show_error(self, self.theme, "Kennung ungültig", nachricht, hinweis)
            return
        if warnung and not messagebox.askyesno(
                "Offizielle Kennung", warnung + "\n\nTrotzdem fortfahren?",
                parent=self):
            return

        if not messagebox.askyesno(
                "Aufspielen?",
                f"'{wahl.name}' auf {self.state.device.name or self.state.model} "
                f"aufspielen?\n\nKennung: {kennung}\n\n"
                f"Der Rückweg zur Originalstimme bleibt jederzeit offen.",
                parent=self):
            return

        cloud, geraet = self.state.cloud, self.state.device
        basis = self.state.base_pack_path
        ffmpeg = self.state.ffmpeg
        mapping = self.state.voice_mapping()
        bekannt = self.state.catalog.ids() if self.state.catalog else None
        port = int(self.state.config["serve_port"] or 0)
        host = self.state.config["host_ip"] or ""

        self.log.clear()
        self.progress.configure(value=0)
        self._busy(True)
        self.badge.set("Bereite vor ...", "muted")

        def work(task: Task):
            if wahl.paket is not None:
                self._log(f"Verwende das fertige Paket {wahl.paket.name}.", "info")
                build = packer.load_existing(wahl.paket)
            else:
                self._log(f"Hole die Aufnahmen für {wahl.name} ...", "step")
                quelle = self._quelle_holen(wahl)
                if quelle is None:
                    raise RuntimeError(
                        f"Die Aufnahmen für {wahl.name} sind nicht auffindbar.")
                gefunden = importer.import_archive(
                    quelle, build_dir() / "_stimme",
                    known_ids=bekannt, log=lambda m: self._log(m))
                if not gefunden.assigned:
                    raise RuntimeError(
                        f"In {Path(quelle).name} war keine zuzuordnende Ansage.")
                if task.cancelled:
                    raise RuntimeError("Vom Benutzer abgebrochen.")

                ziel = library.unique_path(
                    build_dir(), library.safe_name(f"{wahl.name}_fertig"))
                self._log(f"Baue das Paket für dein Modell "
                          f"({len(gefunden.assigned)} Ansagen) ...", "step")
                build = packer.build_pack(
                    base_pack=Path(basis), assignments=gefunden.assigned,
                    out_name=ziel.name, ffmpeg=ffmpeg,
                    work_dir=build_dir() / "_stimme_arbeit",
                    mapping=mapping, log=lambda m: self._log(m))
                library.write_info(build.path, dialect=wahl.name,
                                   engine="Mitgeliefert",
                                   voice=wahl.dialekt.stimme if wahl.dialekt else "",
                                   lang_id=kennung,
                                   replaced=len(build.replaced),
                                   total=len(gefunden.assigned))

            if task.cancelled:
                raise RuntimeError("Vom Benutzer abgebrochen.")

            self.state.last_build = build
            self._log("", "info")
            self._log("Übertrage auf den Roboter", "step")
            return installer.install_pack(
                cloud=cloud, device=geraet, build=build, lang_id=kennung,
                port=port, host_ip=host,
                log=lambda m: self._log(m), step=self._step,
                cancelled=lambda: task.cancelled)

        def ok(ergebnis: installer.InstallOutcome) -> None:
            if ergebnis.success:
                self.progress.configure(value=100)
                self.badge.set("Erfolgreich aufgespielt", "ok")
                self.log.append(ergebnis.message, "ok")
                self.state.config["custom_lang_id"] = kennung
                self.state.config["last_pack_name"] = wahl.name
                self.state.prebuilt_name = wahl.name
                self.state.save()
                self.state.notify("device_changed")
                show_info(
                    self, self.theme, "Fertig",
                    f"{wahl.name} läuft jetzt auf deinem Roboter.",
                    "Probier es aus: Lass ihn eine Reinigung starten - er "
                    "sollte anders klingen.\n\nIn der Dreamehome-App taucht "
                    "das Paket nicht auf; das ist normal und kein Fehler.")
            else:
                self.badge.set("Nicht aufgespielt", "error")
                self.log.append(ergebnis.message, "error")

        def fail(exc: Exception) -> None:
            nachricht, hinweis = error_text(exc)
            self.badge.set("Fehlgeschlagen", "error")
            self.log.append(nachricht, "error")
            if hinweis:
                self.log.append(hinweis, "warn")
            show_error(self, self.theme, "Nicht aufgespielt", nachricht, hinweis)

        self._task = run_async(self, work, on_success=ok, on_error=fail,
                               on_finally=lambda: self._busy(False))
