"""Der eigentliche Installationsablauf.

Reihenfolge:

1. Webserver starten, der genau das gebaute Paket ausliefert.
2. Über die Dreame-Cloud den Auftrag an den Roboter schicken
   (MIoT-Eigenschaft 7/4) - mit URL, MD5 und Größe.
3. Warten, bis der Roboter die Datei tatsächlich abholt.
4. Den Installationszustand abfragen, bis er fertig meldet.
5. Webserver in jedem Fall wieder schließen.

Der Roboter prüft das Archiv selbst gegen MD5 und Größe. Stimmt etwas
nicht, verwirft er es und behält die bisherige Stimme - genau das macht
den Vorgang unkritisch.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .cloud import DreameCloud, Device
from .errors import InstallError, LoginError, NetworkError
from .official import VoicePackInfo
from .packer import BuildResult
from .server import PackServer, reachability_hint

_LOG = logging.getLogger(__name__)

LogFn = Callable[[str], None]
StepFn = Callable[[str, float], None]   # (Beschreibung, Fortschritt 0..1)

# Kennungen, die Dreame selbst vergibt. Wer eine davon überschreibt,
# verliert die Möglichkeit, per Knopfdruck dorthin zurückzukehren.
OFFICIAL_LANG_IDS = {
    "ZH", "EN", "DE", "RU", "FR", "KO", "ES", "IT", "JA", "PL",
    "TR", "SV", "DA", "NB", "PT", "THA", "VI", "UK", "HE",
}
DEFAULT_CUSTOM_LANG_ID = "CUSTOM"

#: Abstand zwischen zwei Blicken auf den Roboter, in Sekunden.
#:
#: Der Zustand durchläuft beim Wechsel kurz "downloading" und kehrt
#: danach auf "success" zurück. Genau diese Bewegung ist der Beweis,
#: dass gerade etwas passiert ist - wer zu selten hinsieht, verpasst
#: sie und wartet anschließend ergebnislos die volle Frist ab.
TAKT = 3.0


def _status_lesen(roh: Any) -> Optional[dict]:
    """Macht aus der Zustandsmeldung des Roboters ein Wörterbuch.

    Der Roboter liefert dort JSON - allerdings mit maskierten
    Anführungszeichen, also `{\\"id\\":\\"CUSTOM\\", ...}`. Das ist kein
    gültiges JSON, deshalb der zweite Versuch.
    """
    if isinstance(roh, dict):
        return roh
    if not isinstance(roh, str) or not roh.strip():
        return None
    for text in (roh, roh.replace('\\"', '"')):
        try:
            wert = json.loads(text)
        except (ValueError, TypeError):
            continue
        if isinstance(wert, dict):
            return wert
    return None


def validate_lang_id(lang_id: str) -> tuple[str, str]:
    """Prüft die Paketkennung. Rückgabe: (bereinigt, Warnung oder "").

    Zurzeit ruft das niemand mehr auf: `install_pack` setzt die Kennung
    fest auf CUSTOM, damit sich auf dem Roboter keine unlöschbaren
    Ordner ansammeln. Die Funktion bleibt samt Tests stehen, weil sie
    die Regeln festhält, die gelten *würden* - wer die Kennung je wieder
    freigibt, braucht genau diese Prüfung wieder. Wer sie entfernt,
    entfernt auch `OFFICIAL_LANG_IDS`.
    """
    cleaned = (lang_id or "").strip().upper()
    if not cleaned:
        return DEFAULT_CUSTOM_LANG_ID, ""
    if not cleaned.isalnum() or len(cleaned) > 8:
        raise InstallError(
            f"Die Paketkennung '{lang_id}' ist ungültig.",
            "Erlaubt sind bis zu 8 Buchstaben oder Ziffern, z. B. CUSTOM oder BAYERN.",
        )
    if cleaned in OFFICIAL_LANG_IDS:
        return cleaned, (
            f"'{cleaned}' ist eine offizielle Dreame-Kennung. Dein Paket "
            f"überschreibt damit die mitgelieferte Sprache. Zum Zurückwechseln "
            f"musst du das Originalpaket erneut installieren - das kann diese "
            f"App, aber eine eigene Kennung wie CUSTOM ist bequemer."
        )
    return cleaned, ""


@dataclass
class InstallOutcome:
    success: bool
    message: str
    downloaded: bool = False
    final_status: Optional[str] = None
    hint: str = ""
    #: Ob der Erfolg belegt ist oder nur wahrscheinlich.
    #:
    #: Der Unterschied darf nicht in der Oberfläche verlorengehen:
    #: Ein Download belegt die Übertragung, nicht die Installation.
    #: Verwirft der Roboter das Paket wegen der Prüfsumme und lässt
    #: seine alte Erfolgsmeldung stehen, sieht das von außen genauso
    #: aus wie ein geglückter Wechsel.
    bestaetigt: bool = True


def _noop_log(_: str) -> None:
    pass


def _noop_step(_msg: str, _p: float) -> None:
    pass


#: Ob beim Auffrischen ein Umweg über einen anderen Wert nötig ist.
#:
#: Bleibt aus. Ein Nutzer hat nach dem Paketwechsel über die
#: Dreamehome-App einen echten Wertwechsel geschrieben - er wollte
#: lauter stellen - und es blieb leise. Der Umweg wäre genau das, was
#: dort schon versagt hat, und er hinterlässt bei einem Abbruch
#: zwischen den beiden Schreibzugriffen dauerhaft den falschen Wert.
LAUTSTAERKE_UMWEG = False

#: Ob nach dem Schreiben der Testton ausgelöst wird (7/aiid 2).
#:
#: Die Referenz-Integration für Dreame-Sauger ruft die Aktion nach
#: jedem Schreiben der Lautstärke auf. Warum, steht dort nicht - am
#: naheliegendsten ist eine Rückmeldung für den Nutzer, damit er hört,
#: was er eingestellt hat. Dass die Firmware den Wert *dadurch* erst
#: übernimmt, wäre ein Rückschluss, für den es keinen Beleg gibt.
#:
#: Als Hörprobe wäre die Aktion sinnvoll. Sie bleibt trotzdem aus,
#: solange nicht am Gerät geprüft ist, dass sie beim r2532v wirklich
#: nur einen Ton abspielt.
LAUTSTAERKE_TESTTON = False


def refresh_volume(cloud: DreameCloud, device: Device, wert: Optional[int],
                   log: LogFn = _noop_log) -> bool:
    """Schreibt die gemerkte Lautstärke zurück, damit sie wieder greift.

    Schlägt fehl, ohne zu stören: Das Sprachpaket ist an dieser Stelle
    bereits installiert, und eine nicht wiederhergestellte Lautstärke ist
    ein Schönheitsfehler - kein Grund, den Vorgang als gescheitert zu
    melden.
    """
    if wert is None:
        return False
    try:
        if LAUTSTAERKE_UMWEG:
            # Erst absichtlich daneben, damit ein echter Wertwechsel
            # entsteht, dann zurück auf den gemerkten Wert.
            cloud.set_voice_volume(device, 99 if wert != 99 else 98)
        ok = cloud.set_voice_volume(device, wert)
        if ok and LAUTSTAERKE_TESTTON:
            cloud.play_voice_test(device)
    except Exception as exc:  # pragma: no cover - reine Absicherung
        _LOG.warning("Lautstärke konnte nicht aufgefrischt werden: %s", exc)
        return False
    if ok:
        # Bewusst ohne Versprechen: Der Roboter hat den Wert im Speicher
        # übernommen - ob er ihn auch auf die Ausgabe anwendet, weiß die
        # App nicht. Ein früherer Text hier lautete "kein Neustart
        # nötig" und redete dem Nutzer damit genau das aus, was als
        # einziges nachweislich hilft.
        log(f"Lautstärke bestätigt: {wert}.")
    else:
        log("Hinweis: Die Lautstärke ließ sich nicht bestätigen.")
    return ok


class _Beobachter:
    """Verfolgt, ob der Roboter seit dem Auftrag wirklich etwas getan hat.

    Nötig, weil die Zielkennung schon vor dem Auftrag dieselbe sein kann:
    Eigene Pakete gehen immer unter CUSTOM raus, und wer die Originalstimme
    wiederherstellt, während sie ohnehin läuft, hat denselben Fall. "Die
    Kennung ist aktiv" beweist dann gar nichts - die Meldung stand schon
    vorher da.

    Die Regeln, jede aus einem echten Fehlschlag entstanden:

    1. Als Beweis zählt eine *Veränderung* gegenüber dem Zustand vor dem
       Auftrag. Bloßes Abwarten zählt nicht - der Roboter lässt seine
       letzte Meldung stehen, notfalls tagelang.
    2. Verglichen wird die Bedeutung, nicht die Rohzeile. Ein Nebenfeld
       wie `progress`, das die Firmware von selbst hochzählt, hat sonst
       genau den "Beweis" fabriziert, den Regel 1 verlangt.
    3. Eine Stelle, die nicht, mit `null` oder leer antwortet, ist keine
       Information - und damit auch keine Veränderung.
    4. Widerspricht die aktive Kennung der Erfolgsmeldung, gilt der
       Erfolg nicht. Das wird nach ein paar Runden als eigenes Ergebnis
       gemeldet, statt bis zum Zeitablauf stillzustehen.
    5. Ein Fehlschlag muss zweimal hintereinander zu sehen sein. Er
       beendet den Vorgang und reißt den Webserver ab; ein einzelner
       Ausreißer darf das nicht auslösen.
    """

    FERTIG = "fertig"
    WAHRSCHEINLICH = "wahrscheinlich"
    FEHLER = "fehler"
    WIDERSPRUCH = "widerspruch"
    WARTEN = "warten"

    #: Wartezeit, bevor eine unveränderte Erfolgsmeldung als
    #: WAHRSCHEINLICH durchgeht. Sie beweist nichts - sie gibt der
    #: Installation nur Zeit, überhaupt anzulaufen.
    NACH_DOWNLOAD = 20.0

    #: So oft muss dieselbe Auffälligkeit zu sehen sein, bevor sie zählt.
    BESTAETIGUNGEN = 2

    #: Wie lange ein Widerspruch zwischen Zustand und aktiver Kennung
    #: anhalten muss, bevor er zählt.
    #:
    #: Die beiden Stellen werden am Roboter getrennt geführt: Der Zustand
    #: springt auf "erfolgreich", die aktive Kennung zieht Sekunden später
    #: nach. Wer hier nach zwei Blicken abbricht, würgt eine laufende
    #: Installation ab - und schließt dabei den Webserver, über den der
    #: Roboter womöglich noch nachladen wollte.
    WIDERSPRUCH_FRIST = 60.0

    def __init__(self, cloud: DreameCloud, device: Device, ziel_id: str) -> None:
        self.cloud = cloud
        self.device = device
        self.ziel = (ziel_id or "").strip().upper()
        self.letzter_zustand = None
        self.bewegung = False
        self.start = time.time()
        self.download_beleg = False
        self._fehler_gesehen = 0
        self._widerspruch_gesehen = 0

        vorher = cloud.voice_state(device) or {}
        self.vorher_paket = self._wert(vorher, "paket")
        self.vorher_zustand = self._wert(vorher, "zustand")
        self.vorher_kern = self._kern(_status_lesen(self.vorher_zustand))
        self.paket_bekannt = self.vorher_paket is not None
        self.zustand_bekannt = self.vorher_kern is not None
        self.aktiv = self.vorher_paket
        # Ohne gelesene Kennung wird pessimistisch angenommen, sie stehe
        # bereits auf dem Ziel. Sonst risse ein einziger Abfragefehler
        # genau das Loch auf, das diese Klasse stopfen soll.
        self.schon_aktiv = (not self.paket_bekannt
                            or self._passt(self.vorher_paket))

    # -- Lesen und Vergleichen --------------------------------------------

    @staticmethod
    def _wert(gelesen: dict, schluessel: str):
        """Der brauchbare Wert einer Stelle - sonst None.

        Fehlender Schlüssel, `null` und leerer Text sind dasselbe: keine
        Auskunft. Text wird dabei gleich von Leerzeichen befreit, sonst
        wäre " CUSTOM " etwas anderes als "CUSTOM".
        """
        wert = gelesen.get(schluessel)
        if wert is None:
            return None
        if isinstance(wert, str):
            wert = wert.strip()
            return wert or None
        return wert

    def _passt(self, kennung) -> bool:
        return str(kennung or "").strip().upper() == self.ziel

    @staticmethod
    def _kern(zustand):
        """Die Bedeutung einer Zustandsmeldung: (Zustand, Kennung).

        Nur darauf kommt es an. Früher wurde die ganze Rohzeile
        verglichen - dann genügte ein hochzählendes
        `progress`-Feld, um eine Veränderung vorzutäuschen. Und
        für unlesbaren Text gab es einen Rückfall auf ebendiese
        Rohzeile, womit eine einzelne Fehlerseite denselben
        Scheinbeweis lieferte. Unlesbares kommt hier gar nicht
        mehr an: Der Aufrufer behandelt es als "keine Auskunft".
        """
        if not zustand:
            return None
        return (str(zustand.get("state", "")).strip().lower(),
                str(zustand.get("id", "") or "").strip().upper())

    def los(self) -> None:
        """Setzt die Uhr auf jetzt - Beginn der eigentlichen Beobachtung."""
        self.start = time.time()

    def beleg_download(self) -> None:
        """Der Roboter hat die Datei vollständig vom eigenen Server geholt."""
        self.download_beleg = True

    def beleg_endzustand(self) -> None:
        """Schon der Endzustand allein trägt hier die Aussage.

        Nur beim Zurückholen eines offiziellen Pakets: Dort lautet die
        Meldung "Das Originalpaket ist wieder aktiv" - eine Aussage über
        den Zustand. War es schon vorher aktiv, ist sie trotzdem wahr.

        Beim eigenen Paket wäre derselbe Schluss falsch: Dass CUSTOM
        aktiv ist, heißt nicht, dass das NEUE Paket darunterliegt.
        """
        self.download_beleg = True

    # -- Der Blick auf den Roboter ----------------------------------------

    def nachsehen(self, log: LogFn = _noop_log) -> str:
        gelesen = self.cloud.voice_state(self.device) or {}
        if not gelesen:
            return self.WARTEN

        paket = self._wert(gelesen, "paket")
        zustand_roh = self._wert(gelesen, "zustand")
        # Unlesbares ist keine Auskunft. Früher fiel der Vergleich auf
        # die Rohzeile zurück - eine einzelne HTML-Fehlerseite an dieser
        # Stelle galt damit als Veränderung und machte aus einer
        # stehengebliebenen Erfolgsmeldung ein "installiert und aktiv".
        zustand = _status_lesen(zustand_roh) if zustand_roh is not None else None

        if zustand is not None:
            if zustand_roh != self.letzter_zustand:
                log(f"Zustand: {zustand_roh}")
            self.letzter_zustand = zustand_roh
            kern = self._kern(zustand)
            if not self.zustand_bekannt:
                self.vorher_kern = kern
                self.zustand_bekannt = True
            elif kern != self.vorher_kern:
                self.bewegung = True
        elif zustand_roh is not None:
            _LOG.debug("Zustand nicht lesbar: %r", zustand_roh)

        if paket is not None:
            self.aktiv = paket
            if not self.paket_bekannt:
                self.vorher_paket = paket
                self.paket_bekannt = True
                self.schon_aktiv = self._passt(paket)
            elif str(paket).strip().upper() != str(self.vorher_paket).strip().upper():
                # Verglichen wird normalisiert: "custom" statt "CUSTOM"
                # ist keine Veränderung am Roboter, sondern Schreibweise.
                self.bewegung = True

        gemeldet = (str(zustand.get("state", "")).strip().lower()
                    if zustand is not None else "")
        gescheitert = gemeldet in ("fail", "failed", "error")

        # Der klarste Fall: Die Kennung ist umgesprungen. Nicht aber,
        # wenn der Roboter im selben Atemzug einen Fehlschlag meldet.
        if (paket is not None and self._passt(paket) and not self.schon_aktiv
                and not gescheitert):
            return self.FERTIG

        # Ohne lesbaren Zustand bleibt nur der Download als Beleg. Diese
        # Abzweigung stand früher hinter einem vorzeitigen Ausstieg -
        # ein Roboter, der die Zustandsstelle nicht beantwortet, wurde
        # dadurch nie fertig, obwohl er das Paket nachweislich hatte.
        if zustand is None:
            return self._wahrscheinlich_wenn_reif()

        genannte_id = str(zustand.get("id", "") or "").strip().upper()
        if genannte_id and genannte_id != self.ziel:
            # Eine Meldung über ein fremdes Paket geht uns nichts an -
            # weder ihr Erfolg noch ihr Fehlschlag. Die Zähler laufen
            # dabei nicht weiter: "zweimal hintereinander" heißt
            # hintereinander.
            self._fehler_gesehen = 0
            self._widerspruch_gesehen = 0
            return self.WARTEN

        if gescheitert:
            self._widerspruch_gesehen = 0
            if not self.bewegung:
                self._fehler_gesehen = 0
                return self.WARTEN
            self._fehler_gesehen += 1
            return (self.FEHLER if self._fehler_gesehen >= self.BESTAETIGUNGEN
                    else self.WARTEN)
        self._fehler_gesehen = 0

        if not gemeldet.startswith("succe"):
            self._widerspruch_gesehen = 0
            return self.WARTEN

        # Eine Erfolgsmeldung, der die aktive Kennung widerspricht, ist
        # keine. Sie darf aber nicht sofort zuschlagen: Die beiden
        # Stellen am Roboter werden getrennt geführt, und die Kennung
        # zieht der Zustandsmeldung um Sekunden hinterher. Wer hier nach
        # zwei Blicken abbricht, würgt eine laufende Installation ab -
        # und schließt dabei den Webserver, über den der Roboter noch
        # nachladen wollte.
        if self.aktiv is not None and not self._passt(self.aktiv):
            self._widerspruch_gesehen += 1
            reif = (time.time() - self.start) >= self.WIDERSPRUCH_FRIST
            return (self.WIDERSPRUCH
                    if (reif
                        and self._widerspruch_gesehen >= self.BESTAETIGUNGEN)
                    else self.WARTEN)
        self._widerspruch_gesehen = 0

        if self.bewegung:
            return self.FERTIG
        return self._wahrscheinlich_wenn_reif()

    def _wahrscheinlich_wenn_reif(self) -> str:
        """Der Download als letzter Beleg - aber erst nach der Wartezeit.

        Nichts hat sich gerührt. Der Roboter hat unsere Datei aber
        nachweislich geholt; mehr als "wahrscheinlich" ist daraus nicht
        zu machen, und genau das bekommt der Nutzer auch zu lesen.
        """
        if (self.download_beleg
                and (time.time() - self.start) >= self.NACH_DOWNLOAD):
            return self.WAHRSCHEINLICH
        return self.WARTEN

    @property
    def aktiv_text(self) -> str:
        """Die aktive Kennung für Meldungen - nie das Wort "None"."""
        return str(self.aktiv) if self.aktiv is not None else "unbekannt"


#: Was nach jedem Sprachwechsel im Protokoll und im Fertig-Fenster steht.
#:
#: Zwei unabhängige Berichte, dass der Roboter nach einem Paketwechsel
#: leiser bleibt - in einem Fall ließ er sich auch über die
#: Dreamehome-App nicht mehr lauter stellen, und zwar ebenso nach dem
#: Zurückholen der Originalstimme. Erst ein Neustart half.
#:
#: Damit liegt die Ursache in der Firmware, unterhalb dessen, was über
#: die Cloud erreichbar ist: Der gespeicherte Wert und die gehörte
#: Lautstärke laufen auseinander. Die App kann das nicht beheben. Was
#: sie kann, ist den Nutzer richtig informieren - deshalb steht der
#: Hinweis sichtbar im Fertig-Fenster und nicht nur im Protokoll.
NEUSTART_HINWEIS = (
    "Falls der Roboter danach leiser klingt als gewohnt: Das liegt an "
    "seiner Firmware, nicht an den Aufnahmen - sie haben denselben Pegel "
    "wie die Originalansagen. Nach einem Sprachwechsel wendet er seine "
    "Lautstärke mitunter erst nach einem Neustart wieder an. Schalte ihn "
    "dazu am Gerät einmal aus und wieder ein; danach ist es behoben."
)


def install_pack(cloud: DreameCloud,
                 device: Device,
                 build: BuildResult,
                 port: int = 0,
                 host_ip: str = "",
                 public_url: str = "",
                 log: LogFn = _noop_log,
                 step: StepFn = _noop_step,
                 download_timeout: float = 120.0,
                 install_timeout: float = 420.0,
                 cancelled: Optional[Callable[[], bool]] = None) -> InstallOutcome:
    """Installiert ein gebautes Paket auf dem Roboter.

    Die Kennung ist fest `CUSTOM` und lässt sich nicht ändern. Der
    Roboter legt jedes Paket in einem Ordner pro Kennung ab; löschen
    kann man dort über die Cloud nichts. Vier Kennungen wären vier
    Ordner, die für immer bleiben - eine einzige überschreibt sich
    selbst und belegt dauerhaft nur einen Platz.
    """

    cancelled = cancelled or (lambda: False)
    lang_id = DEFAULT_CUSTOM_LANG_ID

    log(f"Paket:  {build.path.name}")
    log(f"Größe: {build.size} Bytes ({build.size_mb:.1f} MB)")
    log(f"MD5:    {build.md5}")
    log(f"Kennung: {lang_id}")

    server: Optional[PackServer] = None
    try:
        # ---- 1. Auslieferung vorbereiten -------------------------------
        if public_url:
            url = public_url.strip()
            log(f"Verwende eigene URL: {url}")
            step("Eigene URL wird verwendet", 0.15)
        else:
            step("Webserver wird gestartet", 0.05)
            server = PackServer(build.path, port=port, host_ip=host_ip, log=log)
            url = server.start()
            step("Webserver läuft", 0.15)

        # ---- 2. Auftrag senden ------------------------------------------
        step("Roboter wird geprüft", 0.20)
        log("Frage beim Roboter nach, ob er Sprachpakete auf dem üblichen "
            "Weg entgegennimmt ...")
        try:
            kennt_sprachpakete = cloud.supports_voice_service(device)
        except (NetworkError, LoginError) as exc:
            # Der Roboter hat gar nicht geantwortet. Das ist etwas anderes
            # als "kennt keine Sprachpakete" - meist schläft er nur.
            # Früher stand hier dieselbe Meldung, und der Nutzer suchte
            # den Fehler bei seinem Gerät.
            return InstallOutcome(
                False,
                "Der Roboter hat auf die Nachfrage nicht geantwortet.",
                hint=("Es wurde nichts gesendet. Am häufigsten liegt es "
                      "daran, dass er gerade schläft: Wecke ihn in der "
                      "Dreamehome-App auf - ein Tipp auf 'Roboter finden' "
                      "genügt - und versuche es erneut.\n\n"
                      f"Technische Details: {exc}"))

        if not kennt_sprachpakete:
            return InstallOutcome(
                False,
                "Dieser Roboter meldet keinen Sprachpaket-Dienst.",
                hint=("Die App hat vorsichtshalber nichts gesendet. Der "
                      "Installationsauftrag geht bei Dreame- und "
                      "MOVA-Saugrobotern immer an dieselbe Stelle "
                      "(MIoT siid 7, piid 4); dein Gerät antwortet dort "
                      "aber nicht. Das spricht dafür, dass es Sprachpakete "
                      "gar nicht kennt - etwa bei Mährobotern oder sehr "
                      "alten Modellen aus der Mi-Home-App.\n\n"
                      "Prüfe, ob du in der Dreamehome-App unter "
                      "'Sprachton' überhaupt Sprachen auswählen kannst. "
                      "Geht das dort nicht, kann es diese App auch nicht."),
            )
        log("Der Roboter kennt den Sprachpaket-Dienst.")

        # Jetzt merken, nicht später: Nach dem Wechsel wollen wir genau
        # den Wert wiederherstellen, den der Benutzer eingestellt hatte.
        lautstaerke = cloud.voice_volume(device)
        if lautstaerke is not None:
            log(f"Eingestellte Lautstärke: {lautstaerke}")

        beobachter = _Beobachter(cloud, device, lang_id)
        if beobachter.schon_aktiv:
            log(f"Unter '{lang_id}' liegt bereits ein Paket - es wird "
                f"überschrieben.")

        step("Auftrag wird an den Roboter geschickt", 0.25)
        log("Sende Installationsauftrag über die Dreame-Cloud ...")
        try:
            cloud.install_voice_pack(device, lang_id, url, build.md5, build.size)
        except NetworkError as exc:
            return InstallOutcome(
                False,
                "Der Roboter hat den Auftrag nicht angenommen.",
                hint=str(exc),
            )
        log("Auftrag angenommen.")

        # ---- 3. Auf den Download warten ---------------------------------
        if server is not None:
            step("Roboter lädt das Paket herunter", 0.4)
            log(f"Warte bis zu {int(download_timeout)} Sekunden auf den Download ...")

            deadline = time.time() + download_timeout
            while time.time() < deadline and not server.was_downloaded:
                if cancelled():
                    return InstallOutcome(False, "Vom Benutzer abgebrochen.")
                server.wait_for_download(1.0)

            if not server.was_downloaded:
                # Hat der Roboter überhaupt angeklopft? Dann liegt es
                # nicht an Firewall oder getrennten Netzen - er hat uns
                # ja erreicht. Die alte Meldung schickte den Nutzer in
                # genau diesem Fall auf eine stundenlange Suche an der
                # falschen Stelle.
                # Auch eine abgelehnte Anfrage belegt die
                # Erreichbarkeit - sie kam ja an. Früher zählten nur
                # GET und HEAD, womit gerade der häufigste Auslöser
                # (falscher Pfad) wieder als Firewall galt.
                angeklopft = bool(server.hits)
                if angeklopft:
                    return InstallOutcome(
                        False,
                        "Der Roboter hat begonnen zu laden und dann "
                        "abgebrochen.",
                        hint=("Er hat diesen PC erreicht - an Firewall oder "
                              "getrennten Netzen liegt es also nicht. Die "
                              "Verbindung ist mittendrin abgerissen. Häufigste "
                              "Gründe: schwaches WLAN an der Stelle, an der "
                              "der Roboter gerade steht, oder er ist in den "
                              "Standby gegangen. Stell ihn näher an den "
                              "Router, weck ihn in der Dreamehome-App auf "
                              "und versuche es erneut."),
                    )
                return InstallOutcome(
                    False,
                    "Der Roboter hat das Sprachpaket nicht abgeholt.",
                    hint=reachability_hint(server.port),
                )
            log("Download durch den Roboter bestätigt.")
            # Der stärkste Beleg, den wir haben - und der einzige, der
            # nicht vom Roboter selbst kommt: Er hat die Datei gerade
            # von diesem PC geholt. Damit zählt seine Erfolgsmeldung
            # auch dann, wenn kein Blick ins kurze Zwischenfenster
            # gefallen ist. Ohne diesen Beleg meldete die App
            # "Nicht aufgespielt", obwohl alles geklappt hatte.
            beobachter.beleg_download()
            step("Paket übertragen", 0.6)
        else:
            step("Warte auf den Roboter", 0.4)
            time.sleep(5)

        # ---- 4. Installation beobachten ---------------------------------
        step("Roboter installiert das Paket", 0.7)
        log("Warte auf die Rückmeldung des Roboters ...")

        beobachter.los()
        deadline = time.time() + install_timeout

        while time.time() < deadline:
            if cancelled():
                return InstallOutcome(False, "Vom Benutzer abgebrochen.",
                                      downloaded=True)
            time.sleep(TAKT)

            ergebnis = beobachter.nachsehen(log)

            if ergebnis == _Beobachter.FEHLER:
                return InstallOutcome(
                    False,
                    "Der Roboter meldet, dass die Installation fehlgeschlagen ist.",
                    downloaded=True,
                    final_status=str(beobachter.letzter_zustand),
                    hint=("Meist stimmt die Datei nicht mit MD5 oder Größe "
                          "überein, oder der Roboter kam nicht bis zum Ende "
                          "an sie heran. Die bisherige Stimme bleibt dabei "
                          "unangetastet - du kannst es einfach erneut "
                          "versuchen."),
                )

            if ergebnis == _Beobachter.WIDERSPRUCH:
                return InstallOutcome(
                    False,
                    f"Der Roboter meldet '{beobachter.aktiv_text}' als "
                    f"aktive Sprache, nicht '{lang_id}'.",
                    downloaded=beobachter.download_beleg,
                    final_status=(str(beobachter.letzter_zustand)
                                  if beobachter.letzter_zustand is not None
                                  else None),
                    hint=("Der Zustand am Gerät meldet zwar Erfolg, die "
                          "aktive Sprache passt aber nicht dazu. Am "
                          "wahrscheinlichsten ist, dass in der "
                          "Dreamehome-App zwischenzeitlich eine Sprache "
                          "unter 'Sprachton' ausgewählt wurde - damit "
                          "lädt der Roboter das offizielle Paket nach "
                          "und überschreibt das eigene. Versuche es "
                          "erneut und lass die Sprachauswahl in der "
                          "Handy-App dabei unberührt."),
                )

            if ergebnis in (_Beobachter.FERTIG, _Beobachter.WAHRSCHEINLICH):
                sicher = ergebnis == _Beobachter.FERTIG
                log(f"Der Roboter meldet '{beobachter.aktiv_text}' als aktives "
                    f"Sprachpaket.")
                refresh_volume(cloud, device, lautstaerke, log)
                if sicher:
                    meldung = (f"Das Sprachpaket '{lang_id}' ist "
                               f"installiert und aktiv.")
                    hinweis = NEUSTART_HINWEIS
                else:
                    # Der Roboter hat die Datei nachweislich geholt und
                    # meldet Erfolg - aber seine Zustandsmeldung ist
                    # wortgleich mit der von vorher. Damit ist der
                    # Wechsel nicht belegt, nur wahrscheinlich. Das
                    # gehört dem Nutzer gesagt, statt es zu glätten.
                    meldung = (f"Das Sprachpaket '{lang_id}' wurde "
                               f"übertragen.")
                    hinweis = (
                        "Der Roboter hat das Paket nachweislich abgeholt "
                        "und meldet 'erfolgreich' - eine Zustandsänderung "
                        "war dabei aber nicht zu beobachten, weil dort schon "
                        "vorher dieselbe Meldung stand. Hör einmal hin: Wenn "
                        "der Roboter in der neuen Stimme spricht, hat alles "
                        "geklappt.\n\n") + NEUSTART_HINWEIS
                log(hinweis)
                step("Fertig", 1.0)
                return InstallOutcome(
                    True, meldung,
                    downloaded=True,
                    bestaetigt=sicher,
                    final_status=(str(beobachter.letzter_zustand)
                                  if beobachter.letzter_zustand is not None else None),
                    hint=hinweis,
                )

            progress = 0.7 + min(0.25, (time.time() - beobachter.start)
                                 / install_timeout * 0.25)
            step("Roboter installiert das Paket", progress)

        # Zeit abgelaufen, aber der Download hat geklappt.
        return InstallOutcome(
            False,
            "Der Roboter hat die Installation nicht innerhalb der Wartezeit bestätigt.",
            downloaded=True,
            final_status=(str(beobachter.letzter_zustand)
                          if beobachter.letzter_zustand is not None else None),
            # Bei einer eigenen URL liefert nicht dieser PC aus - dann
            # ist über den Download nichts bekannt, und die Meldung
            # darf ihn auch nicht behaupten.
            hint=(("Das Paket wurde nachweislich vollständig abgeholt. "
                   if beobachter.download_beleg else
                   "Ob der Roboter das Paket abgeholt hat, lässt sich bei "
                   "einer eigenen URL von hier aus nicht sehen. ")
                  + "Sehr wahrscheinlich läuft die Installation noch oder ist "
                    "bereits fertig. Der Roboter sagt bei Erfolg 'Sprache "
                    "erfolgreich gewechselt'. Prüfe die Stimme am Gerät; falls "
                    "sie unverändert ist, starte den Vorgang einfach erneut."),
        )

    except InstallError:
        raise
    except Exception as exc:  # pragma: no cover - unerwartete Fälle
        _LOG.exception("Installation fehlgeschlagen")
        return InstallOutcome(False, "Unerwarteter Fehler bei der Installation.",
                              hint=str(exc))
    finally:
        if server is not None:
            server.stop()


def restore_official(cloud: DreameCloud,
                     device: Device,
                     pack: VoicePackInfo,
                     log: LogFn = _noop_log,
                     step: StepFn = _noop_step,
                     timeout: float = 420.0) -> InstallOutcome:
    """Stellt ein offizielles Sprachpaket wieder her.

    Hier wird bewusst Dreames eigene Download-URL benutzt - der Roboter
    lädt also direkt beim Hersteller, ganz ohne PC im Spiel. Das ist
    derselbe Vorgang, den die Dreamehome-App beim Sprachwechsel auslöst.
    """
    log(f"Stelle das offizielle Paket '{pack.label}' wieder her.")
    log(f"Quelle: {pack.url}")
    log(f"Größe: {pack.size} Bytes, MD5: {pack.md5}")

    # Wie beim eigenen Paket: erst die Lautstärke merken, dann den
    # Zustand vor dem Auftrag festhalten. Aus dem Forum kam der Bericht,
    # dass der Roboter auch *nach* dem Zurückholen der Originalstimme
    # leise blieb - dieser Weg braucht also dieselbe Behandlung.
    lautstaerke = cloud.voice_volume(device)
    if lautstaerke is not None:
        log(f"Eingestellte Lautstärke: {lautstaerke}")
    beobachter = _Beobachter(cloud, device, pack.id)
    if beobachter.schon_aktiv:
        log(f"'{pack.id}' ist bereits die aktive Kennung - das Paket wird "
            f"neu geladen.")

    step("Auftrag wird geschickt", 0.2)
    try:
        cloud.install_voice_pack(device, pack.id, pack.url, pack.md5, pack.size)
    except NetworkError as exc:
        return InstallOutcome(False, "Der Roboter hat den Auftrag nicht angenommen.",
                              hint=str(exc))

    log("Auftrag angenommen. Der Roboter lädt jetzt direkt bei Dreame.")
    step("Roboter lädt bei Dreame", 0.5)

    beobachter.los()
    beobachter.beleg_endzustand()
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(TAKT)
        ergebnis = beobachter.nachsehen(log)

        if ergebnis == _Beobachter.FEHLER:
            return InstallOutcome(
                False,
                "Der Roboter meldet, dass das Zurückholen fehlgeschlagen ist.",
                final_status=str(beobachter.letzter_zustand),
                hint=("Die bisherige Stimme bleibt dabei unangetastet. "
                      "Versuche es erneut, oder stelle die Sprache in der "
                      "Dreamehome-App unter Einstellungen > Sprachpaket um."))

        if ergebnis == _Beobachter.WIDERSPRUCH:
            return InstallOutcome(
                False,
                f"Der Roboter meldet '{beobachter.aktiv_text}' als aktive "
                f"Sprache, nicht '{pack.id}'.",
                hint=("Die Zustandsmeldung am Gerät passt nicht zur aktiven "
                      "Sprache. Stelle die Sprache in der Dreamehome-App "
                      "unter 'Sprachton' um - das ist derselbe Vorgang, und "
                      "dort siehst du unmittelbar, was der Roboter tut."))

        if ergebnis in (_Beobachter.FERTIG, _Beobachter.WAHRSCHEINLICH):
            refresh_volume(cloud, device, lautstaerke, log)
            hinweis = NEUSTART_HINWEIS
            if not beobachter.bewegung:
                # Der Roboter führte diese Sprache schon vorher, und es
                # war keine Veränderung zu beobachten. Die Meldung
                # stimmt trotzdem - sie sagt etwas über den Zustand aus,
                # nicht über den Vorgang. Wer aber wiederherstellt,
                # WEIL etwas kaputt ist, darf davon nicht in Sicherheit
                # gewiegt werden.
                hinweis = (
                    f"Hinweis: '{pack.id}' war schon vorher die aktive "
                    f"Sprache, und der Roboter hat keine Neuinstallation "
                    f"gemeldet. Falls du das Paket erneuern wolltest, weil "
                    f"etwas nicht stimmt: Stelle in der Dreamehome-App unter "
                    f"'Sprachton' auf eine andere Sprache und wieder zurück - "
                    f"dann lädt der Roboter es garantiert neu.\n\n"
                ) + NEUSTART_HINWEIS
                log(hinweis)
            else:
                log(NEUSTART_HINWEIS)
            step("Fertig", 1.0)
            return InstallOutcome(
                True, f"Das Originalpaket '{pack.id}' ist wieder aktiv.",
                # Hier lädt der Roboter direkt bei Dreame - von hier
                # aus wurde nichts übertragen, das dürfen wir auch
                # nicht behaupten.
                downloaded=False,
                bestaetigt=(ergebnis == _Beobachter.FERTIG),
                hint=hinweis)

    return InstallOutcome(
        False,
        "Keine Bestätigung innerhalb der Wartezeit.",
        hint=("Der Auftrag wurde angenommen. Prüfe die Stimme am Roboter - "
              "oft ist die Installation trotzdem durchgelaufen. Alternativ "
              "lässt sich die Sprache jederzeit in der Dreamehome-App unter "
              "Einstellungen > Sprachpaket umstellen."),
    )
