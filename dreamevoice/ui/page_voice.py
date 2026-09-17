"""Eine Stimme wählen, anhören und aufspielen - an einem Ort.

Das war bisher auf zwei Reiter verteilt: In Tab 4 suchte man den Dialekt
aus, in Tab 3 spielte man ihn auf. Dass beides zusammengehört, stand
nirgends - und weil beide Reiter einen fast gleich benannten Knopf für
"fertiges Paket" hatten, landete man leicht im falschen.

Seit 1.4.0 stehen hier ALLE fertigen Stimmen, gleich groß und nach
Herkunft geordnet:

* **In der App enthalten** - die Aufnahmen aus der EXE (dialektpakete.py),
  darunter Community-Packs mit dem Namen ihres Urhebers
* **Eigene** - was unter "Eigene Stimmen" gebaut wurde (library.py)
* **Freie Stimmen aus dem Netz** - geprüfte Bastelprojekte von GitHub
  (community.py)

Vorher standen die freien Stimmen als große Karten auf einer anderen
Seite, ließen sich nicht anhören, und nach dem Herunterladen hieß es
"wechsle jetzt zu Bauen und Aufspielen". Jetzt ist es für jede Stimme
dasselbe: auswählen, anhören, aufspielen. Eine freie Stimme wird beim
ersten Anhören geladen und dann für das Aufspielen wiederverwendet.

Aufgespielt wird über dieselben Bausteine wie bisher: `packer` baut das
Paket auf das eigene Modell, `installer.install_pack` schickt es weg -
immer unter der Kennung CUSTOM. Pakete, die dabei nur als Zwischenschritt
entstehen, landen in einem eigenen Unterordner und tauchen nicht unter
"Eigene" auf (siehe library.ist_zwischenstand).
"""

from __future__ import annotations

import logging
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

from .. import (community, dialektpakete, embedded, importer, installer,
                library, packer, vorhoeren)
from ..errors import PackError
from ..paths import build_dir
from .state import AppState, Task, error_text, run_async, to_main
from .theme import Theme
from .widgets import (Card, LogView, ScrollablePage, StatusBadge, show_error,
                      show_info, show_warning)

_LOG = logging.getLogger(__name__)

GRUPPE_ENTHALTEN = "In der App enthalten"
GRUPPE_EIGEN = "Eigene"
GRUPPE_FREI = "Freie Stimmen aus dem Netz"
GRUPPEN = (GRUPPE_ENTHALTEN, GRUPPE_EIGEN, GRUPPE_FREI)

#: Kennzeichen der Zeilen, die keine Stimme sind.
_KOPF = "kopf:"
_LEER = "leer:"


@dataclass
class Auswahl:
    """Eine Stimme in der Liste - gleich, woher sie kommt."""

    key: str
    name: str
    gruppe: str
    #: Rechte Spalte der Liste: Herkunft und Umfang auf einen Blick.
    details: str
    beschreibung: str
    dialekt: Optional[dialektpakete.FertigerDialekt] = None
    paket: Optional[Path] = None
    frei: Optional[community.CommunityPack] = None
    #: Etwas, das man vor dem Aufspielen wissen sollte (R2-D2 spricht nicht).
    hinweis: str = ""

    # Eine Kennung führt der Eintrag nicht mit: Aufgespielt wird
    # grundsätzlich unter CUSTOM, damit sich die Pakete auf dem Roboter
    # nicht ansammeln. Siehe installer.install_pack.

    @property
    def label(self) -> str:
        return self.name

    @property
    def muss_laden(self) -> bool:
        """Wird beim Anhören oder Aufspielen erst etwas geladen?"""
        return self.frei is not None and not community.ist_geladen(self.frei)


def _groesse(pack: community.CommunityPack) -> str:
    if not pack.size_mb:
        return ""
    return f"{pack.size_mb:.1f} MB".replace(".", ",")


class VoicePage(ttk.Frame):
    """Stimme aussuchen, anhören, auf den Roboter bringen."""

    def __init__(self, master, theme: Theme, state: AppState,
                 gehe_zu=None) -> None:
        super().__init__(master, style="TFrame")
        self.theme = theme
        self.state = state
        self.gehe_zu = gehe_zu or (lambda _key: None)

        self._auswahl: List[Auswahl] = []
        self._nach_key: Dict[str, Auswahl] = {}
        self._gewaehlt_key: str = ""
        #: Richtung der letzten Bewegung in der Liste - damit das
        #: Überspringen einer Überschrift in die richtige Richtung geht.
        self._letzter_index = 0
        self._task: Optional[Task] = None
        #: Läuft gerade eine Probe? Dann ist der Anhören-Knopf der
        #: Stopp-Knopf.
        self._probe_laeuft: Optional[Task] = None
        #: Je Stimme die schon umgewandelten Ansagen - ein zweiter Klick
        #: spart Auspacken und ffmpeg.
        self._probe_puffer: Dict[str, Dict[int, Path]] = {}

        self._build()
        self.refresh()

        # Neu gebaute eigene Stimmen erscheinen trotzdem sofort: Die
        # Seitenleiste ruft refresh() bei jedem Anzeigen auf.
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
            text=("Aussuchen, anhören, aufspielen - für jede Stimme gleich. "
                  "Jede landet an derselben Stelle im Roboter und ersetzt "
                  "die vorige."),
            style="MutedBg.TLabel", wraplength=760, justify="left"
        ).pack(anchor="w", pady=(3, 16))

        # -- Auswahl ---------------------------------------------------
        card = Card(outer, self.theme, "Welche Stimme?")
        card.pack(fill="x")

        liste = ttk.Frame(card.content, style="Card.TFrame")
        liste.pack(fill="x")
        self.tree = ttk.Treeview(liste, columns=("details",), show="tree",
                                 selectmode="browse", height=12)
        self.tree.column("#0", width=300, minwidth=220, stretch=True)
        self.tree.column("details", width=360, minwidth=200, stretch=True)
        self.tree.tag_configure("kopf", font=self.theme.font_bold,
                                foreground=self.theme.color("muted"))
        self.tree.tag_configure("leer", foreground=self.theme.color("muted"),
                                font=self.theme.font_small)
        self.tree.tag_configure("community",
                                foreground=self.theme.color("accent"))
        rollen = ttk.Scrollbar(liste, orient="vertical",
                               command=self.tree.yview)
        self.tree.configure(yscrollcommand=rollen.set)
        self.tree.pack(side="left", fill="x", expand=True)
        rollen.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_pick)
        # Ein Doppelklick heißt fast immer "das will ich hören".
        self.tree.bind("<Double-1>", lambda _e: self._on_probe())
        self.tree.bind("<Return>", lambda _e: self._on_probe())

        # -- Was ist das für eine Stimme? -------------------------------
        info = ttk.Frame(card.content, style="Card.TFrame")
        info.pack(fill="x", pady=(14, 0))
        self.lbl_name = ttk.Label(info, text="", style="Heading.TLabel")
        self.lbl_name.pack(anchor="w")
        self.lbl_herkunft = ttk.Label(info, text="", style="Muted.TLabel",
                                      wraplength=700, justify="left")
        self.lbl_herkunft.pack(anchor="w", pady=(2, 0))
        self.lbl_beschreibung = ttk.Label(info, text="", style="Surface.TLabel",
                                          wraplength=700, justify="left")
        self.lbl_beschreibung.pack(anchor="w", pady=(6, 0))
        self.lbl_hinweis = ttk.Label(info, text="", style="Warning.TLabel",
                                     wraplength=700, justify="left")
        self.lbl_hinweis.pack(anchor="w", pady=(4, 0))

        reihe = ttk.Frame(card.content, style="Card.TFrame")
        reihe.pack(fill="x", pady=(12, 0))
        self.btn_probe = ttk.Button(reihe, text="▶ Anhören",
                                    command=self._on_probe)
        self.btn_probe.pack(side="left")
        self.btn_projekt = ttk.Button(reihe, text="Projektseite",
                                      style="Small.TButton",
                                      command=self._on_projektseite)
        self.lbl_probe = ttk.Label(reihe, text="", style="Surface.TLabel",
                                   wraplength=520, justify="left")
        self.lbl_probe.pack(side="left", padx=(12, 0))

        # -- Aufspielen ------------------------------------------------
        card2 = Card(outer, self.theme, "Auf den Roboter bringen")
        card2.pack(fill="x", pady=(14, 0))

        knoepfe = ttk.Frame(card2.content, style="Card.TFrame")
        knoepfe.pack(fill="x")
        self.btn_los = ttk.Button(knoepfe, text="Aufspielen",
                                  style="Accent.TButton", command=self._on_install)
        self.btn_los.pack(side="left")
        self.btn_abbruch = ttk.Button(knoepfe, text="Abbrechen", state="disabled",
                                      command=self._on_cancel)
        self.btn_abbruch.pack(side="left", padx=(8, 0))
        self.badge = StatusBadge(knoepfe, self.theme, "Bereit")
        self.badge.pack(side="left", padx=(12, 0))

        ttk.Label(
            card2.content,
            text=(f"Kennung {installer.DEFAULT_CUSTOM_LANG_ID} - für jede "
                  f"Stimme dieselbe, mit Absicht: Der Roboter legt je Kennung "
                  f"einen Ordner an, den man über die Cloud nicht löschen "
                  f"kann. So überschreibt jede Stimme die vorige, statt sich "
                  f"anzusammeln. Die deutsche Originalstimme bleibt davon "
                  f"unberührt."),
            style="Muted.TLabel", wraplength=720, justify="left"
        ).pack(anchor="w", pady=(10, 0))

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
        vorher = self._gewaehlt_key
        self._auswahl = self._sammeln()
        self._nach_key = {a.key: a for a in self._auswahl}

        self.tree.delete(*self.tree.get_children())
        for gruppe in GRUPPEN:
            eintraege = [a for a in self._auswahl if a.gruppe == gruppe]
            self.tree.insert("", "end", iid=_KOPF + gruppe,
                             text=gruppe.upper(), values=("",),
                             tags=("kopf",))
            if not eintraege:
                self.tree.insert("", "end", iid=_LEER + gruppe,
                                 text="    noch keine",
                                 values=(self._leer_text(gruppe),),
                                 tags=("leer",))
                continue
            for a in eintraege:
                marken = ("community",) if (a.dialekt is not None
                                            and a.dialekt.ist_community) else ()
                self.tree.insert("", "end", iid=a.key,
                                 text="    " + a.name,
                                 values=(a.details,), tags=marken)

        zeilen = len(self.tree.get_children())
        self.tree.configure(height=max(6, min(zeilen, 18)))

        ziel = vorher if vorher in self._nach_key else (
            self._auswahl[0].key if self._auswahl else "")
        if ziel:
            self.tree.selection_set(ziel)
            self.tree.see(ziel)
        self._zeige(self._nach_key.get(ziel))

    @staticmethod
    def _leer_text(gruppe: str) -> str:
        if gruppe == GRUPPE_EIGEN:
            return "entstehen unter „Eigene Stimmen“"
        return ""

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
            if d.ist_community:
                details = f"{d.herkunft}  ·  {d.ansagen} Ansagen"
            else:
                details = f"Deutsch  ·  {d.ansagen} Ansagen"
            beschreibung = d.beschreibung
            if d.ist_community:
                beschreibung += (f"\n\nEin Community-Pack: Text und Stimme "
                                 f"stammen von {d.urheber}, nicht aus diesem "
                                 f"Projekt.")
            beschreibung += f"\n\n{d.ansagen} Ansagen, {d.stimme}, {woher}."
            eintraege.append(Auswahl(
                key=f"dialekt:{d.key}", name=d.anzeigename,
                gruppe=GRUPPE_ENTHALTEN, details=details,
                beschreibung=beschreibung,
                dialekt=d))

        for info in library.list_packs(build_dir()):
            teile = []
            if info.voice:
                teile.append(info.voice)
            elif info.engine:
                teile.append(info.engine)
            if info.replaced:
                teile.append(f"{info.replaced} Ansagen")
            if info.created:
                teile.append(info.created[:10])
            eintraege.append(Auswahl(
                key=f"paket:{info.path.name}",
                name=info.dialect or info.path.stem,
                gruppe=GRUPPE_EIGEN,
                details="  ·  ".join(teile) or f"{info.size_mb:.1f} MB",
                beschreibung=(f"Selbst gebaut, liegt als {info.path.name} "
                              f"unter „Meine Pakete“."),
                paket=info.path))

        for pack in community.PACKS:
            teile = [pack.language, f"ca. {pack.approx_sounds} Ansagen"]
            if pack.size_mb:
                teile.append(_groesse(pack))
            eintraege.append(Auswahl(
                key=f"frei:{pack.key}", name=pack.name,
                gruppe=GRUPPE_FREI, details="  ·  ".join(teile),
                beschreibung=(
                    f"{pack.description}\n\nEin Bastelprojekt von "
                    f"{pack.author} auf GitHub (Lizenz: {pack.license}). "
                    f"Es bringt etwa {pack.approx_sounds} Ansagen mit - "
                    f"alles andere bleibt auf der deutschen Originalstimme "
                    f"deines Roboters."),
                frei=pack, hinweis=pack.notes))

        return eintraege

    def _gewaehlt(self) -> Optional[Auswahl]:
        return self._nach_key.get(self._gewaehlt_key)

    def _on_pick(self, _event=None) -> None:
        auswahl = self.tree.selection()
        if not auswahl:
            return
        iid = auswahl[0]
        if iid.startswith((_KOPF, _LEER)):
            # Überschriften und Platzhalter sind keine Stimmen - weiter
            # zur nächsten echten Zeile, in Bewegungsrichtung.
            zeilen = list(self.tree.get_children())
            jetzt = zeilen.index(iid)
            schritt = -1 if jetzt < self._letzter_index else 1
            i = jetzt
            while 0 <= i < len(zeilen) and zeilen[i] not in self._nach_key:
                i += schritt
            if not 0 <= i < len(zeilen):
                i = jetzt
                while 0 <= i < len(zeilen) and zeilen[i] not in self._nach_key:
                    i -= schritt
            if 0 <= i < len(zeilen) and zeilen[i] in self._nach_key:
                self.tree.selection_set(zeilen[i])
                self.tree.see(zeilen[i])
            elif self._gewaehlt_key:
                self.tree.selection_set(self._gewaehlt_key)
            return
        self._letzter_index = list(self.tree.get_children()).index(iid)
        if iid != self._gewaehlt_key:
            self.lbl_probe.configure(text="")
        self._zeige(self._nach_key.get(iid))

    def _zeige(self, wahl: Optional[Auswahl]) -> None:
        self._gewaehlt_key = wahl.key if wahl else ""
        if wahl is None:
            self.lbl_name.configure(text="Keine Stimme gewählt")
            self.lbl_herkunft.configure(text="")
            self.lbl_beschreibung.configure(
                text="Es steht noch keine fertige Stimme bereit.")
            self.lbl_hinweis.configure(text="")
            self.btn_projekt.pack_forget()
            return
        self.lbl_name.configure(text=wahl.name)
        self.lbl_herkunft.configure(text=wahl.details)
        self.lbl_beschreibung.configure(text=wahl.beschreibung)
        self.lbl_hinweis.configure(text=wahl.hinweis)
        if wahl.frei is not None:
            self.btn_projekt.pack(side="left", padx=(8, 0),
                                  before=self.lbl_probe)
        else:
            self.btn_projekt.pack_forget()
        self._probe_beschriften()

    def _probe_beschriften(self) -> None:
        if self._probe_laeuft is not None:
            return
        wahl = self._gewaehlt()
        text = "▶ Anhören"
        if wahl is not None and wahl.muss_laden:
            groesse = _groesse(wahl.frei)
            text = (f"▶ Anhören (lädt {groesse})" if groesse
                    else "▶ Anhören (wird geladen)")
        self.btn_probe.configure(text=text)

    def _on_projektseite(self) -> None:
        wahl = self._gewaehlt()
        if wahl is not None and wahl.frei is not None:
            webbrowser.open(wahl.frei.project_url)

    # -- Anhören --------------------------------------------------------
    def _quelle_holen(self, wahl: Auswahl, laden: bool = False,
                      task: Optional[Task] = None) -> Optional[Path]:
        """Der Pfad zu den Aufnahmen bzw. zum fertigen Paket.

        Eine freie Stimme wird nur mit `laden=True` aus dem Netz geholt -
        vorher liefert sie nur, was schon hier liegt.
        """
        if wahl.paket is not None:
            return wahl.paket
        if wahl.dialekt is not None:
            return dialektpakete.beschaffen(wahl.dialekt,
                                            log=lambda m: self._log(m))
        if wahl.frei is not None:
            if not laden:
                return (wahl.frei.local_path()
                        if community.ist_geladen(wahl.frei) else None)

            def melde(fertig: int, gesamt: int) -> None:
                if not gesamt:
                    return
                anteil = fertig / gesamt
                to_main(self, self.lbl_probe.configure,
                        {"text": f"Lade {wahl.name} ... {anteil:.0%}"})
                to_main(self, self.progress.configure, {"value": anteil * 100})

            return community.download(
                wahl.frei, progress=melde,
                cancelled=(lambda: task.cancelled) if task else None)
        return None

    def _on_probe(self) -> None:
        # Läuft gerade eine Probe, ist derselbe Knopf der Stopp-Knopf.
        # Zwölf Sekunden zuhören zu müssen, weil man sich verklickt hat,
        # wäre die unfreundlichste Art, eine Vorschau anzubieten.
        if self._probe_laeuft is not None:
            self._probe_laeuft.cancel()
            return
        if self._task is not None:
            return

        wahl = self._gewaehlt()
        if wahl is None:
            return

        ffmpeg = self.state.ffmpeg
        katalog = self.state.catalog
        # Einmal umgewandelte Ansagen werden gemerkt: Beim zweiten Klick
        # auf dieselbe Stimme entfällt Auspacken und ffmpeg.
        gemerkt = self._probe_puffer.get(wahl.key)
        if gemerkt:
            vorab = "Spiele ab ..."
        elif wahl.muss_laden:
            vorab = f"Lade {wahl.name} ..."
        else:
            vorab = "Bereite die Probe vor ..."
        self.lbl_probe.configure(text=vorab)
        self.btn_probe.configure(text="■ Stopp")
        aufgabe = Task()
        self._probe_laeuft = aufgabe

        def work(task: Task):
            nonlocal ffmpeg
            proben = gemerkt
            if proben is None:
                # Das Versprechen aus dem Hinweistext einlösen: ffmpeg
                # steckt in der EXE und wird beim ersten Bedarf
                # ausgepackt. Bisher geschah das nur auf der Seite
                # "Einzelne Ansagen" - wer die nie aufschlug, bekam
                # hier die Auskunft, ffmpeg fehle.
                if ffmpeg is None and embedded.has_ffmpeg():
                    to_main(self, self.lbl_probe.configure,
                            {"text": "ffmpeg wird einmalig ausgepackt ..."})
                    try:
                        ffmpeg = embedded.extract_ffmpeg()
                        self.state.ffmpeg = ffmpeg
                    except OSError as exc:
                        _LOG.warning("ffmpeg ließ sich nicht auspacken: %s",
                                     exc)
                try:
                    quelle = self._quelle_holen(wahl, laden=True, task=task)
                except community.Abgebrochen:
                    return {}
                if quelle is None:
                    return None
                if task.cancelled:
                    return {}
                to_main(self, self.lbl_probe.configure,
                        {"text": "Bereite die Probe vor ..."})
                if not vorhoeren.verfuegbare_ids(quelle):
                    # Kein Ton im Paket ist etwas anderes als ein
                    # fehlendes ffmpeg - und verdient eine andere Antwort.
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
            self.progress.configure(value=0)
            if proben is None:
                self.lbl_probe.configure(text="")
                show_warning(
                    self, self.theme, "Nichts zum Anhören",
                    f"In den Aufnahmen für {wahl.name} steckt keine Ansage, "
                    f"die sich vorspielen ließe.",
                    "Die Datei fehlt, ist beschädigt oder enthält keine "
                    "Tondateien mit Ansage-Nummer im Namen.")
                return
            if not proben:
                if aufgabe.cancelled:
                    self.lbl_probe.configure(text="Abgebrochen.")
                    return
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
            self.progress.configure(value=0)
            self.lbl_probe.configure(text="")
            nachricht, hinweis = error_text(exc)
            show_error(self, self.theme, "Probe fehlgeschlagen", nachricht, hinweis)

        def fertig() -> None:
            self._probe_laeuft = None
            self._probe_beschriften()

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
        self.tree.state(["disabled"] if aktiv else ["!disabled"])

    def _on_cancel(self) -> None:
        if self._task:
            self._task.cancel()
            self.log.append("Abbruch angefordert ...", "warn")

    def _frage_text(self, wahl: Auswahl, kennung: str) -> str:
        ziel = self.state.device.name or self.state.model
        teile = [f"'{wahl.name}' auf {ziel} aufspielen?"]
        if wahl.frei is not None:
            teile.append(
                f"Die Stimme bringt etwa {wahl.frei.approx_sounds} Ansagen "
                f"mit. Alle übrigen bleiben auf der deutschen "
                f"Originalstimme.")
            if wahl.muss_laden:
                groesse = _groesse(wahl.frei)
                teile.append(
                    "Sie wird dafür zuerst von GitHub geladen"
                    + (f" ({groesse})" if groesse else "")
                    + " und gegen ihre Prüfsumme geprüft.")
        if wahl.hinweis:
            teile.append(wahl.hinweis)
        teile.append(f"Kennung: {kennung} - eine schon dort liegende eigene "
                     f"Stimme wird dabei überschrieben.")
        teile.append("Der Rückweg zur Originalstimme bleibt jederzeit offen.")
        return "\n\n".join(teile)

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
        if self._probe_laeuft is not None:
            self._probe_laeuft.cancel()

        kennung = installer.DEFAULT_CUSTOM_LANG_ID

        if not messagebox.askyesno("Aufspielen?",
                                   self._frage_text(wahl, kennung),
                                   parent=self):
            return

        cloud, geraet = self.state.cloud, self.state.device
        basis = self.state.base_pack_path
        ffmpeg = self.state.ffmpeg
        mapping = self.state.voice_mapping()
        bekannt = self.state.catalog.ids() if self.state.catalog else None
        port = int(self.state.config["serve_port"] or 0)
        host = self.state.config["host_ip"] or ""
        zwischen = library.zwischenstand_ordner(build_dir())

        self.log.clear()
        self.progress.configure(value=0)
        self._busy(True)
        self.badge.set("Bereite vor ...", "muted")

        def work(task: Task):
            if wahl.paket is not None:
                self._log(f"Verwende das fertige Paket {wahl.paket.name}.", "info")
                build = packer.load_existing(wahl.paket)

            elif wahl.frei is not None:
                self._log(f"Hole {wahl.name} ...", "step")
                try:
                    archiv = self._quelle_holen(wahl, laden=True, task=task)
                except community.Abgebrochen:
                    raise RuntimeError("Vom Benutzer abgebrochen.") from None
                if task.cancelled:
                    raise RuntimeError("Vom Benutzer abgebrochen.")
                self._log("Lege die Stimme auf das Paket deines Modells ...",
                          "step")
                try:
                    build = packer.overlay_pack(
                        base_pack=Path(basis), overlay_pack_path=archiv,
                        out_name=f"frei_{wahl.frei.key}.tar.gz",
                        out_dir=zwischen,
                        mapping=mapping, log=lambda m: self._log(m),
                        progress=lambda d, t: to_main(
                            self, self.progress.configure,
                            {"value": (d / t * 100) if t else 0}))
                except PackError:
                    # Ein Paket ohne feste Prüfsumme (das X40-Projekt-
                    # archiv) würde sonst für immer als "geladen" gelten,
                    # auch wenn es unbrauchbar ist. Weg damit - der
                    # nächste Versuch lädt neu.
                    if not wahl.frei.expected_md5:
                        community.verwerfen(wahl.frei)
                    raise
                for warnung in build.warnings:
                    self._log(warnung, "warn")

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

                # Ein fester Name je Stimme: Das Paket ist nur ein
                # Zwischenschritt und wird beim nächsten Mal ersetzt,
                # statt sich neben die eigenen Stimmen zu legen.
                self._log(f"Baue das Paket für dein Modell "
                          f"({len(gefunden.assigned)} Ansagen) ...", "step")
                build = packer.build_pack(
                    base_pack=Path(basis), assignments=gefunden.assigned,
                    out_name=f"{wahl.dialekt.key}.tar.gz", out_dir=zwischen,
                    ffmpeg=ffmpeg,
                    work_dir=build_dir() / "_stimme_arbeit",
                    mapping=mapping, log=lambda m: self._log(m))

            if task.cancelled:
                raise RuntimeError("Vom Benutzer abgebrochen.")

            self.state.last_build = build
            self._log("", "info")
            self._log("Übertrage auf den Roboter", "step")
            return installer.install_pack(
                cloud=cloud, device=geraet, build=build,
                port=port, host_ip=host,
                log=lambda m: self._log(m), step=self._step,
                cancelled=lambda: task.cancelled)

        def ok(ergebnis: installer.InstallOutcome) -> None:
            if ergebnis.success:
                self.progress.configure(value=100)
                # Belegt oder nur wahrscheinlich - der Unterschied darf
                # hier nicht verlorengehen. Ein Download belegt die
                # Übertragung, nicht die Installation.
                if ergebnis.bestaetigt:
                    self.badge.set("Erfolgreich aufgespielt", "ok")
                else:
                    self.badge.set("Übertragen, nicht bestätigt", "warn")
                self.log.append(ergebnis.message,
                                "ok" if ergebnis.bestaetigt else "warn")
                self.state.config["custom_lang_id"] = kennung
                self.state.config["last_pack_name"] = wahl.name
                self.state.prebuilt_name = wahl.name
                self.state.save()
                # NICHT "device_changed": Der Roboter ist derselbe, nur
                # seine Stimme ist neu. Das andere Ereignis verwirft
                # Originalpaket und Sprachliste - vier Seiten würden
                # grau, und der Nutzer landete direkt nach der
                # Erfolgsmeldung wieder auf der Startseite.
                self.state.notify("pack_installed")
                show_info(
                    self, self.theme,
                    "Fertig" if ergebnis.bestaetigt else "Übertragen",
                    (f"{wahl.name} läuft jetzt auf deinem Roboter."
                     if ergebnis.bestaetigt else
                     f"{wahl.name} wurde auf den Roboter übertragen."),
                    "Probier es aus: Lass ihn eine Reinigung starten - er "
                    "sollte anders klingen.\n\nIn der Dreamehome-App taucht "
                    "das Paket nicht auf; das ist normal und kein Fehler.\n\n"
                    # Der Hinweis aus dem Ergebnis sagt bei einem nur
                    # wahrscheinlichen Erfolg, woran es liegt. Er stand
                    # bisher nur im Protokoll - im Fenster las der Nutzer
                    # trotzdem die Tatsachenbehauptung.
                    + (ergebnis.hint or installer.NEUSTART_HINWEIS))
            else:
                self.badge.set("Nicht aufgespielt", "error")
                self.log.append(ergebnis.message, "error")
                if ergebnis.hint:
                    self.log.append(ergebnis.hint, "warn")

        def fail(exc: Exception) -> None:
            nachricht, hinweis = error_text(exc)
            self.badge.set("Fehlgeschlagen", "error")
            self.log.append(nachricht, "error")
            if hinweis:
                self.log.append(hinweis, "warn")
            show_error(self, self.theme, "Nicht aufgespielt", nachricht, hinweis)

        def zum_schluss() -> None:
            self._task = None
            self._busy(False)
            # Eine eben geladene freie Stimme muss nicht mehr "lädt"
            # auf dem Knopf stehen haben.
            self._probe_beschriften()

        self._task = run_async(self, work, on_success=ok, on_error=fail,
                               on_finally=zum_schluss)
