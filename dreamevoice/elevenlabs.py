"""Sprachsynthese über ElevenLabs - der Weg zu echtem bayerischem Akzent.

Warum überhaupt ein Onlinedienst?
--------------------------------
Ein frei verfügbares Sprachmodell mit bayerischem Dialekt gibt es nicht.
Nachgeprüft: die Piper-Stimmen von Rhasspy haben nur Hochdeutsch, das
Thorsten-Voice-Projekt hat zwar Dialektmodelle, aber nur Hessisch. Der
einzige offene bayerische Sprachkorpus (Betthupferl) gehört dem
Bayerischen Rundfunk und ist nicht frei nutzbar. Und Windows bringt
ausschließlich Hochdeutsch mit.

ElevenLabs bietet dagegen ausdrücklich deutschen Sprachausgabe mit
bayerischem Akzent an, und zwar mit einem kostenlosen Monatskontingent
von 10.000 Zeichen. Das komplette bayerische Paket dieser App braucht
rund 4.400 Zeichen - es passt also zweimal in ein Freikontingent.

Wichtig: Die App legt kein Konto an und verwendet keinen fremden
Zugangsschlüssel. Der Nutzer trägt seinen eigenen Schlüssel ein; dieser
wird - wie das Dreame-Passwort - mit der Windows-DPAPI verschlüsselt
abgelegt. Übertragen werden ausschließlich die Ansagetexte.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from .errors import AudioError, NetworkError

_LOG = logging.getLogger(__name__)


class Ueberlastet(NetworkError):
    """ElevenLabs bremst gerade - erneut versuchen, nicht aufgeben.

    Eigener Typ, weil das Gegenteil von "Kontingent aufgebraucht"
    gemeint ist: Dort hilft nur Warten bis zum nächsten Monat, hier
    genügen ein paar Sekunden.
    """


#: Wie viele Ansagen die App höchstens gleichzeitig anfordert.
#:
#: ElevenLabs begrenzt das je nach Tarif - die Grenze steht nirgends
#: abrufbar, deshalb wird sie ertastet: Nach einer sauberen Welle eine
#: mehr, bei einer Drosselung sofort halbieren. Anfangs bewusst
#: vorsichtig, damit auch ein Freikonto nicht gleich anläuft.
MAX_GLEICHZEITIG = 8
START_GLEICHZEITIG = 3

#: So oft wird eine EINZELNE gedrosselte Ansage erneut versucht, wenn
#: der Dienst nachweislich läuft - also in derselben Welle eine andere
#: Ansage durchgekommen ist.
MAX_VERSUCHE = 4

#: So viele Wellen darf der Dienst am Stück ALLES drosseln, bevor die
#: App aufgibt. Großzügiger als MAX_VERSUCHE, weil hier keinem
#: einzelnen Auftrag etwas vorzuwerfen ist - der Dienst ist kurz
#: überlastet und fängt sich meist wieder. Ohne diese Trennung
#: verbrauchten die ersten Ansagen ihre Versuche während einer
#: allgemeinen Drosselung, und der Lauf brach mit null Ergebnissen ab.
MAX_WELLEN_GEDROSSELT = 10

API = "https://api.elevenlabs.io/v1"
SIGNUP_URL = "https://elevenlabs.io/text-to-speech/german-bavarian-accent"
LIBRARY_URL = "https://elevenlabs.io/app/voice-library"
# Direkt zur Seite, auf der der Zugangsschlüssel erzeugt wird. Über die
# Oberfläche: Profil unten links > Settings > API Keys > Create API Key.
API_KEY_URL = "https://elevenlabs.io/app/settings/api-keys"

# Mehrsprachiges Modell - liefert bei deutschem Text eine gute Aussprache.
# Über list_models() lässt sich ein anderes wählen: eine Stimme, die mit
# einem neueren Modell entworfen wurde, klingt damit oft lebendiger.
MODEL = "eleven_multilingual_v2"
OUTPUT_FORMAT = "mp3_44100_128"

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int], None]


@dataclass
class ElevenVoice:
    voice_id: str
    name: str
    labels: Dict[str, str]
    description: str = ""
    public_owner_id: str = ""
    category: str = ""
    preview_url: str = ""

    @property
    def is_own_creation(self) -> bool:
        """Selbst erzeugte oder geklonte Stimme (nicht von ElevenLabs vorgegeben)."""
        return self.category in ("generated", "cloned", "professional")

    @property
    def accent(self) -> str:
        return (self.labels or {}).get("accent", "")

    @property
    def language(self) -> str:
        return (self.labels or {}).get("language", "")

    @property
    def is_bavarian(self) -> bool:
        haystack = " ".join([
            self.name, self.accent, self.description,
            " ".join((self.labels or {}).values()),
        ]).lower()
        return any(word in haystack for word in
                   ("bavarian", "bayerisch", "bairisch", "bayrisch", "münchen",
                    "munich", "austrian", "österreich"))

    @property
    def label(self) -> str:
        teile = [x for x in (self.language, self.accent) if x]
        if self.category == "generated":
            teile.append("selbst erzeugt")
        elif self.category == "cloned":
            teile.append("geklont")
        extra = " · ".join(teile)
        return f"{self.name} ({extra})" if extra else self.name

    @property
    def details(self) -> str:
        """Mehrzeilige Beschreibung für die Auswahl."""
        zeilen = [self.name]
        merkmale = [v for k, v in (self.labels or {}).items() if v]
        if merkmale:
            zeilen.append("   " + " · ".join(merkmale))
        if self.description:
            kurz = self.description.strip().replace("\n", " ")
            zeilen.append("   " + (kurz[:150] + "…" if len(kurz) > 150 else kurz))
        return "\n".join(zeilen)


@dataclass
class Quota:
    used: int
    limit: int

    @property
    def left(self) -> int:
        return max(0, self.limit - self.used)

    def describe(self) -> str:
        return f"{self.left} von {self.limit} Zeichen übrig"


#: Je Thread eine offene Verbindung.
#:
#: Bisher baute jede einzelne Ansage eine neue TLS-Verbindung auf -
#: gemessen 48 ms, über 593 Ansagen rund 30 Sekunden reines Warten.
#: Eine Sitzung je Thread statt einer gemeinsamen, weil `requests`
#: Thread-Sicherheit für eine geteilte Sitzung nicht zusichert.
_oertlich = threading.local()


def _sitzung():
    """Die offene Verbindung dieses Threads.

    Der Schlüssel enthält absichtlich die Kennnummer des
    `requests`-Moduls: Die Testsuite tauscht `elevenlabs.requests` gegen
    eine Attrappe aus. Eine einmal gemerkte Sitzung des echten Moduls
    hätte den Austausch danach umgangen - die nachgestellten Antworten
    wären wirkungslos geblieben, und die Tests hätten sich gegen den
    echten Dienst gewandt.
    """
    schluessel = id(requests)
    gemerkt = getattr(_oertlich, "sitzung", None)
    if gemerkt is not None and gemerkt[0] == schluessel:
        return gemerkt[1]
    sitzung = requests.Session()
    _oertlich.sitzung = (schluessel, sitzung)
    return sitzung


def _http(method: str, url: str, **kwargs):
    """Der eine Ort, an dem diese Datei wirklich ins Netz geht.

    Absichtlich eine eigene, benannte Funktion: Die Testsuite ersetzt
    genau sie, um Antworten nachzustellen. Früher wurde dafür
    `requests.request` ausgetauscht - seit die App eine offene
    Verbindung benutzt, ginge das daran vorbei. Die Tests hätten sich
    dann unbemerkt gegen den echten Dienst gewandt, statt gegen die
    nachgestellten Antworten.
    """
    return _sitzung().request(method, url, **kwargs)


def _headers(api_key: str) -> Dict[str, str]:
    return {"xi-api-key": api_key, "Accept": "application/json"}


def looks_like_key(value: str) -> bool:
    """Grobe Formprüfung: ElevenLabs-Schlüssel beginnen mit 'sk_'."""
    value = (value or "").strip()
    return value.startswith("sk_") and len(value) > 20


def _request(method: str, path: str, api_key: str, api_version: str = "v1",
             raise_on_auth: bool = True, **kwargs):
    """Ein API-Aufruf.

    `raise_on_auth=False` gibt die Antwort auch bei 401 zurück. Das ist
    wichtig, weil ElevenLabs 401 nicht nur bei einem falschen Schlüssel
    schickt, sondern auch, wenn der Schlüssel stimmt, aber auf die
    angefragte Stimme kein Zugriff besteht. Beides in einen Topf zu werfen
    führt zu der irreführenden Meldung "Schlüssel ungültig", obwohl er
    einwandfrei ist.
    """
    base = API if api_version == "v1" else API.replace("/v1", f"/{api_version}")
    url = f"{base}/{path.lstrip('/')}"
    try:
        resp = _http(method, url, headers=_headers(api_key),
                     timeout=kwargs.pop("timeout", 30), **kwargs)
    except requests.exceptions.RequestException as exc:
        raise NetworkError("ElevenLabs ist nicht erreichbar.",
                           f"Aufruf: {method} {url}\nTechnische Details: {exc}") from exc

    if resp.status_code == 401 and raise_on_auth:
        raise NetworkError(
            "Der Zugangsschlüssel wurde nicht akzeptiert.",
            f"Aufruf: {method} {url}\n"
            f"Antwort: {(resp.text or '')[:200]}\n\n"
            f"Prüfe den Schlüssel unter elevenlabs.io/app/settings/api-keys. "
            f"Er beginnt mit 'sk_'. Achte darauf, dass beim Kopieren nichts "
            f"abgeschnitten wurde und kein Leerzeichen mitgekommen ist.")
    if resp.status_code == 429:
        # 429 hat bei ElevenLabs ZWEI Bedeutungen, und sie führen zu
        # entgegengesetztem Verhalten: "Kontingent leer" heißt aufhören,
        # "zu viele gleichzeitige Anfragen" heißt kurz warten und erneut
        # versuchen. Früher galt beides als leeres Kontingent - was
        # sequenziell meist stimmte, parallel aber fast nie.
        meldung = (_server_message(resp) or "").lower()
        if any(w in meldung for w in ("quota", "character_limit", "credit",
                                      "exceeded", "aufgebraucht")):
            raise NetworkError(
                "Das Kontingent bei ElevenLabs ist aufgebraucht.",
                "Das Freikontingent füllt sich jeden Monat wieder auf. Bis "
                "dahin kannst du das Paket mit der Windows-Stimme erzeugen.")
        raise Ueberlastet(
            "ElevenLabs nimmt gerade keine weitere Anfrage an.",
            "Der Dienst begrenzt, wie viele Ansagen gleichzeitig gesprochen "
            "werden dürfen. Die App drosselt sich selbst und versucht es "
            "erneut - das ist kein Fehler.\n\n"
            f"Antwort des Dienstes: {_server_message(resp) or '(ohne Angabe)'}")
    return resp


def check_key(api_key: str) -> Quota:
    """Prüft den Schlüssel und liefert das verbleibende Kontingent."""
    if not (api_key or "").strip():
        raise NetworkError("Es wurde kein Zugangsschlüssel eingetragen.")

    resp = _request("GET", "user/subscription", api_key)
    if resp.status_code != 200:
        raise NetworkError(f"ElevenLabs antwortete mit HTTP {resp.status_code}.",
                           (resp.text or "")[:200])
    data = resp.json()
    return Quota(used=int(data.get("character_count", 0)),
                 limit=int(data.get("character_limit", 0)))


def _parse_voice(raw: Dict[str, Any]) -> ElevenVoice:
    return ElevenVoice(
        voice_id=raw.get("voice_id", ""),
        name=raw.get("name", "") or "(ohne Namen)",
        labels=raw.get("labels") or {},
        description=raw.get("description") or "",
        category=raw.get("category", "") or "",
        preview_url=raw.get("preview_url", "") or "",
    )


def list_voices(api_key: str) -> List[ElevenVoice]:
    """Alle Stimmen im Konto des Nutzers - über alle Seiten hinweg.

    Wichtig: die Auflistung läuft über **v2**. Die ältere v1-Liste lässt
    selbst erzeugte Stimmen (Voice Design, Kategorie "generated") außen
    vor - genau die, die man sich mühsam selbst gebaut hat. Außerdem gibt
    v2 nur 10 Stimmen zurück, wenn man `page_size` nicht setzt, deshalb
    wird hier geblättert.
    """
    voices: List[ElevenVoice] = []
    token = None
    seiten = 0

    while seiten < 20:
        params: Dict[str, Any] = {"page_size": 100}
        if token:
            params["next_page_token"] = token

        resp = _request("GET", "voices", api_key, params=params, api_version="v2")
        if resp.status_code != 200:
            break

        data = resp.json()
        for raw in data.get("voices", []):
            voices.append(_parse_voice(raw))

        seiten += 1
        token = data.get("next_page_token")
        if not data.get("has_more") or not token:
            return voices

    if voices:
        return voices

    # Rückfallebene, falls v2 nicht erreichbar ist.
    resp = _request("GET", "voices", api_key)
    if resp.status_code != 200:
        raise NetworkError(f"Die Stimmenliste kam nicht an (HTTP {resp.status_code}).")
    return [_parse_voice(raw) for raw in resp.json().get("voices", [])]


def _server_message(resp) -> str:
    """Zieht die Klartextmeldung aus einer ElevenLabs-Fehlerantwort."""
    try:
        detail = resp.json().get("detail")
    except Exception:
        return (resp.text or "").strip()[:300]

    if isinstance(detail, dict):
        teile = [str(detail.get(k)) for k in ("status", "message") if detail.get(k)]
        return " - ".join(teile) or str(detail)[:300]
    if isinstance(detail, str):
        return detail[:300]
    return (resp.text or "").strip()[:300]


def _is_key_problem(resp) -> bool:
    """Erkennt, ob die Antwort auf einen untauglichen Schlüssel hinweist.

    ElevenLabs meldet das je nach Endpunkt mit 401 *oder* 400, deshalb wird
    zusätzlich der Meldungstext ausgewertet.
    """
    if resp.status_code == 401:
        return True
    text = (_server_message(resp) or "").lower()
    return any(w in text for w in ("api_key", "api key", "unauthorized",
                                   "invalid_api", "authentication"))


def _eigene_stimmen(api_key: str) -> Optional[int]:
    """Wie viele selbst angelegte Stimmen hat das Konto zu diesem Schlüssel?

    `None`, wenn es sich nicht feststellen lässt. Die mitgelieferten
    Stimmen ("premade") zählen nicht mit - die hat jedes Konto.
    """
    try:
        resp = _request("GET", "voices", api_key, raise_on_auth=False, timeout=15)
        if resp.status_code != 200:
            return None
        return sum(1 for v in resp.json().get("voices", [])
                   if (v.get("category") or "") != "premade")
    except Exception:                                  # noqa: BLE001
        return None


def _konto_hinweis(api_key: str) -> str:
    """Der häufigste Grund für eine nicht gefundene Stimme, in Worten.

    Wer mehrere ElevenLabs-Konten hat - etwa ein Gratiskonto zum
    Ausprobieren und eines mit den echten Stimmen - trägt hier leicht
    den Schlüssel des einen und die Stimmen-ID des anderen ein. Von
    außen sieht das aus wie "ID ungültig", ist aber keine.
    """
    anzahl = _eigene_stimmen(api_key)
    if anzahl is None:
        return ""
    if anzahl == 0:
        return ("Wichtig: In dem Konto, zu dem dieser Zugangsschlüssel "
                "gehört, gibt es überhaupt keine eigenen Stimmen - nur die "
                "mitgelieferten. Die gesuchte Stimme wurde also sehr "
                "wahrscheinlich in einem anderen ElevenLabs-Konto "
                "angelegt. Trag oben den Schlüssel des Kontos ein, in dem "
                "die Stimme steht.\n\n")
    return (f"Zur Einordnung: In dem Konto zu diesem Schlüssel liegen "
            f"{anzahl} eigene Stimmen - die gesuchte ist nicht darunter.\n\n")


def get_voice(api_key: str, voice_id: str) -> ElevenVoice:
    """Holt eine einzelne Stimme über ihre ID.

    Der Weg, um eine selbst erzeugte Stimme zu benutzen, die in keiner
    Liste auftaucht: ID aus ElevenLabs kopieren und hier eintragen.
    """
    voice_id = (voice_id or "").strip()
    if not voice_id:
        raise NetworkError(
            "Es wurde keine Stimmen-ID eingetragen.",
            "Die ID steht in ElevenLabs bei der Stimme unter den drei Punkten "
            "('Copy Voice ID') und ist rund 20 Zeichen lang.")

    if voice_id.startswith("sk_"):
        raise NetworkError(
            "Im Feld für die Stimmen-ID steht ein Zugangsschlüssel.",
            "Schlüssel beginnen mit 'sk_', Stimmen-IDs nicht. Die beiden "
            "Felder sind vermutlich vertauscht: der Schlüssel gehört nach "
            "oben, die Stimmen-ID hierher.")

    resp = _request("GET", f"voices/{voice_id}", api_key, raise_on_auth=False)

    if resp.status_code == 200:
        return _parse_voice(resp.json())

    meldung = _server_message(resp)

    if _is_key_problem(resp):
        raise NetworkError(
            "ElevenLabs hat den Zugangsschlüssel abgelehnt.",
            f"Antwort des Servers (HTTP {resp.status_code}):\n{meldung}\n\n"
            f"Ein gültiger Schlüssel beginnt mit 'sk_'. Häufigste Ursachen:\n"
            f"· beim Kopieren wurde nur ein Teil erwischt\n"
            f"· der Schlüssel wurde in ElevenLabs zurückgezogen oder neu erzeugt\n"
            f"· Schlüssel und Stimmen-ID sind in den Feldern vertauscht\n\n"
            f"Neuen Schlüssel holen: elevenlabs.io/app/settings/api-keys")

    if resp.status_code in (400, 404, 422):
        raise NetworkError(
            f"Zu der ID '{voice_id}' konnte keine Stimme geladen werden.",
            f"Antwort des Servers (HTTP {resp.status_code}):\n{meldung}\n\n"
            + _konto_hinweis(api_key) +
            f"Prüfe die ID in deinem ElevenLabs-Konto: bei der Stimme auf die "
            f"drei Punkte klicken und 'Copy Voice ID' wählen. Stimmen aus der "
            f"öffentlichen Bibliothek musst du erst deinem Konto hinzufügen, "
            f"bevor du sie über die ID ansprechen kannst.")

    raise NetworkError(
        f"Die Stimme konnte nicht geladen werden (HTTP {resp.status_code}).",
        f"Antwort des Servers:\n{meldung}")


def search_bavarian_voices(api_key: str, limit: int = 30) -> List[ElevenVoice]:
    """Durchsucht die öffentliche Stimmenbibliothek nach bayerischem Akzent."""
    found: Dict[str, ElevenVoice] = {}

    for term in ("bavarian", "bayerisch", "bairisch"):
        resp = _request("GET", "shared-voices", api_key,
                        params={"page_size": limit, "search": term,
                                "language": "de"})
        if resp.status_code != 200:
            continue
        for raw in resp.json().get("voices", []):
            voice = ElevenVoice(
                voice_id=raw.get("voice_id", ""),
                name=raw.get("name", ""),
                labels={k: v for k, v in {
                    "accent": raw.get("accent", ""),
                    "language": raw.get("language", ""),
                    "gender": raw.get("gender", ""),
                    "age": raw.get("age", ""),
                }.items() if v},
                description=raw.get("description") or "",
                public_owner_id=raw.get("public_owner_id", ""),
            )
            if voice.voice_id:
                found[voice.voice_id] = voice

    return list(found.values())


def get_voice_settings(api_key: str, voice_id: str) -> Optional[Dict[str, Any]]:
    """Holt die Einstellungen, die bei der Stimme hinterlegt sind.

    Entscheidend für den Klang: `stability` steuert die Ausdruckskraft.
    Niedrige Werte lassen die Stimme lebendig schwanken, hohe machen sie
    gleichförmig bis monoton. Wer seine Stimme in ElevenLabs eingestellt
    hat, soll genau diese Einstellung hören - nicht eine, die diese App
    ihm überstülpt.
    """
    resp = _request("GET", f"voices/{voice_id}/settings", api_key,
                    raise_on_auth=False)
    if resp.status_code != 200:
        _LOG.info("Stimmeneinstellungen nicht abrufbar (HTTP %s)", resp.status_code)
        return None
    try:
        daten = resp.json()
    except ValueError:
        return None

    erlaubt = ("stability", "similarity_boost", "style", "use_speaker_boost",
               "speed")
    ergebnis = {k: v for k, v in daten.items() if k in erlaubt and v is not None}
    return ergebnis or None


def describe_settings(settings: Optional[Dict[str, Any]]) -> str:
    """Kurzbeschreibung der Einstellungen für die Anzeige."""
    if not settings:
        return "Standardwerte von ElevenLabs"
    teile = []
    if "stability" in settings:
        wert = float(settings["stability"])
        art = "lebendig" if wert < 0.4 else ("ausgewogen" if wert < 0.7
                                             else "gleichförmig")
        teile.append(f"Stabilität {wert:.2f} ({art})")
    if settings.get("style"):
        teile.append(f"Stil {float(settings['style']):.2f}")
    if "speed" in settings:
        teile.append(f"Tempo {float(settings['speed']):.2f}")
    return ", ".join(teile) or "eigene Einstellungen"


def list_models(api_key: str) -> List[Dict[str, Any]]:
    """Die Sprachmodelle, die dem Konto zur Verfügung stehen."""
    resp = _request("GET", "models", api_key, raise_on_auth=False)
    if resp.status_code != 200:
        return []
    try:
        roh = resp.json()
    except ValueError:
        return []

    modelle = []
    for eintrag in roh if isinstance(roh, list) else []:
        if not eintrag.get("can_do_text_to_speech", True):
            continue
        modelle.append({
            "id": eintrag.get("model_id", ""),
            "name": eintrag.get("name", "") or eintrag.get("model_id", ""),
            "description": eintrag.get("description", "") or "",
        })
    return [m for m in modelle if m["id"]]


def add_shared_voice(api_key: str, voice: ElevenVoice,
                     name: str = "") -> Optional[str]:
    """Übernimmt eine Stimme aus der Bibliothek ins eigene Konto."""
    if not voice.public_owner_id:
        return voice.voice_id

    resp = _request(
        "POST", f"voices/add/{voice.public_owner_id}/{voice.voice_id}", api_key,
        json={"new_name": name or voice.name})
    if resp.status_code not in (200, 201):
        raise NetworkError(
            "Die Stimme konnte nicht ins Konto übernommen werden.",
            (resp.text or "")[:200])
    return resp.json().get("voice_id", voice.voice_id)


def synthesize(texts: Dict[int, str],
               out_dir: Path,
               api_key: str,
               voice_id: str,
               log: Optional[LogFn] = None,
               progress: Optional[ProgressFn] = None,
               cancelled: Optional[Callable[[], bool]] = None,
               allow_partial: bool = True,
               model: str = "",
               voice_settings: Optional[Dict[str, Any]] = None,
               use_voice_settings: bool = True,
               parallel: int = START_GLEICHZEITIG) -> Dict[int, Path]:
    """Spricht alle Texte und legt je eine mp3-Datei ab.

    Bereits gesprochene Ansagen werden nicht erneut angefordert - das
    spart Kontingent und erlaubt es, ein großes Paket in mehreren
    Anläufen fertigzustellen.

    Zum Klang: Ohne eigene Angabe werden die Einstellungen benutzt, die
    an der Stimme hinterlegt sind. Frühere Fassungen dieser App haben
    stattdessen feste Werte geschickt - dadurch klang eine sorgfältig
    eingestellte Stimme deutlich flacher als in der Vorschau bei
    ElevenLabs.
    """
    cancelled = cancelled or (lambda: False)

    if not voice_id:
        raise AudioError("Es wurde keine Stimme ausgewählt.")
    if not texts:
        raise AudioError("Es wurden keine Texte übergeben.")

    out_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[int, Path] = {}
    items = sorted(texts.items())

    # Klangeinstellungen bestimmen
    einstellungen = voice_settings
    if einstellungen is None and use_voice_settings:
        einstellungen = get_voice_settings(api_key, voice_id)
        if log:
            log(f"Klang der Stimme: {describe_settings(einstellungen)}")

    rumpf: Dict[str, Any] = {"model_id": model or MODEL}
    if einstellungen:
        rumpf["voice_settings"] = einstellungen

    # --- Was überhaupt noch gesprochen werden muss -------------------
    # Schon vorhandene Aufnahmen sparen Kontingent und machen ein großes
    # Paket über mehrere Anläufe hinweg fertigstellbar.
    offen: List[tuple] = []
    for sound_id, text in items:
        if not (text or "").strip():
            continue
        ziel = out_dir / f"{sound_id}.mp3"
        if ziel.is_file() and ziel.stat().st_size > 1024:
            result[sound_id] = ziel
            continue
        offen.append((sound_id, text, ziel))

    gesamt = len(result) + len(offen)
    if progress and result:
        progress(len(result), gesamt)
    if log and result:
        log(f"{len(result)} Ansagen liegen schon vor und werden "
            f"wiederverwendet.")

    def _sprich(auftrag):
        """Eine einzelne Ansage anfordern. Läuft in einem eigenen Thread.

        Gibt (sound_id, ziel, fehler) zurück - geworfen wird hier
        nichts, damit eine einzelne Ansage nie die ganze Welle reißt.
        """
        sound_id, text, ziel = auftrag
        try:
            resp = _request(
                "POST", f"text-to-speech/{voice_id}", api_key,
                params={"output_format": OUTPUT_FORMAT},
                json={"text": text, **rumpf},
                timeout=60)
        except BaseException as exc:                     # noqa: BLE001
            return sound_id, None, exc
        if resp.status_code != 200:
            return sound_id, None, NetworkError(
                f"Ansage {sound_id} konnte nicht gesprochen werden "
                f"(HTTP {resp.status_code}).", (resp.text or "")[:300])
        try:
            ziel.write_bytes(resp.content)
        except OSError as exc:
            return sound_id, None, exc
        return sound_id, ziel, None

    breite = max(1, min(int(parallel or START_GLEICHZEITIG), MAX_GLEICHZEITIG))
    versuche: Dict[int, int] = {}
    #: Wie viele Wellen am Stück komplett gedrosselt wurden.
    welle_gedrosselt = 0
    abgebrochen = False

    while offen and not abgebrochen:
        if cancelled():
            break
        welle, offen = offen[:breite], offen[breite:]

        if len(welle) == 1:
            ergebnisse = [_sprich(welle[0])]
        else:
            with ThreadPoolExecutor(max_workers=len(welle)) as pool:
                ergebnisse = list(pool.map(_sprich, welle))

        gedrosselt: List[tuple] = []
        # Kam in dieser Welle überhaupt etwas durch? Davon hängt ab,
        # ob eine Drosselung dem einzelnen Auftrag anzulasten ist oder
        # dem Dienst.
        etwas_durch = any(f is None for _, _, f in ergebnisse)
        if etwas_durch:
            welle_gedrosselt = 0

        for (sound_id, text, ziel), (_, fertig, fehler) in zip(welle, ergebnisse):
            if fehler is None:
                result[sound_id] = fertig
                continue

            if isinstance(fehler, Ueberlastet):
                # Eine Drosselung kostet kein Kontingent - erneut
                # versuchen ist also frei. Angerechnet wird sie dem
                # Auftrag nur, wenn der Dienst nachweislich läuft.
                if etwas_durch:
                    versuche[sound_id] = versuche.get(sound_id, 0) + 1
                if versuche.get(sound_id, 0) <= MAX_VERSUCHE:
                    gedrosselt.append((sound_id, text, ziel))
                    continue
                fehler = NetworkError(
                    "ElevenLabs hat mehrfach gebremst.",
                    f"Ansage {sound_id} ließ sich auch nach "
                    f"{MAX_VERSUCHE} Versuchen nicht sprechen. Versuche "
                    f"es später noch einmal - das Bisherige bleibt "
                    f"gespeichert.")

            if isinstance(fehler, NetworkError) and "Kontingent" in fehler.message:
                if allow_partial and result:
                    if log:
                        log(f"Kontingent aufgebraucht nach {len(result)} von "
                            f"{gesamt} Ansagen.")
                        log("Das Bisherige bleibt gespeichert. Beim nächsten "
                            "Versuch macht die App genau hier weiter.")
                    return result
                raise fehler

            if allow_partial and result:
                if log:
                    log(f"Abbruch bei Ansage {sound_id}: {fehler}")
                    log(f"{len(result)} Ansagen sind fertig und bleiben "
                        f"erhalten.")
                return result
            raise fehler

        if gedrosselt:
            # Der Dienst bremst: Breite halbieren und kurz Luft lassen.
            # Die gedrosselten Ansagen kommen ganz nach vorn, damit sie
            # nicht bis zum Schluss liegenbleiben.
            vorher = breite
            breite = max(1, breite // 2)
            offen = gedrosselt + offen

            if not etwas_durch:
                welle_gedrosselt += 1
                if welle_gedrosselt > MAX_WELLEN_GEDROSSELT:
                    fehler = NetworkError(
                        "ElevenLabs bremst dauerhaft.",
                        f"Auch nach {MAX_WELLEN_GEDROSSELT} Versuchen mit "
                        f"immer weniger gleichzeitigen Anfragen kam keine "
                        f"einzige Ansage durch. Versuche es später noch "
                        f"einmal - das Bisherige bleibt gespeichert.")
                    if allow_partial and result:
                        if log:
                            log(str(fehler.message))
                        return result
                    raise fehler

            if log and breite != vorher:
                log(f"ElevenLabs bremst - es laufen jetzt {breite} "
                    f"Ansagen gleichzeitig.")
            # Schrittweise länger warten, aber nie ewig.
            time.sleep(min(0.5 * (2 ** min(welle_gedrosselt, 4)), 8.0))
        elif breite < MAX_GLEICHZEITIG:
            # Saubere Welle: vorsichtig eine mehr.
            breite += 1

        if progress:
            progress(len(result), gesamt)
        if log and len(result) % 20 < len(welle) and len(result) >= 20:
            log(f"  {len(result)} von {gesamt} Ansagen gesprochen ...")

    if not result:
        raise AudioError("Es wurde keine einzige Ansage erzeugt.")
    if log:
        log(f"{len(result)} Ansagen von ElevenLabs erhalten.")
    return result


def estimate_characters(texts: Dict[int, str]) -> int:
    return sum(len(t) for t in texts.values())
