"""Selbsttest der Kernlogik - ohne Oberfläche und ohne Roboter.

Prüft die Teile, bei denen ein Fehler teuer wäre: Paketbau, Prüfsummen,
Vollständigkeit des Archivs und die Auslieferung per HTTP.

Aufruf:   python selftest.py
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import shutil
import sys
import tarfile
import threading
import time
import traceback
import tempfile
import urllib.request
from urllib.parse import urlsplit as _urlsplit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dreamevoice import audio, official, packer, server, installer  # noqa: E402
from dreamevoice.cloud import DreameCloud  # noqa: E402
from dreamevoice.errors import DreameError, NetworkError, PackError  # noqa: E402
from dreamevoice.sounds import SoundCatalog  # noqa: E402

PASSED = 0
FAILED = 0
UEBERSPRUNGEN = 0
ABSCHNITTE = 0
LETZTER_ABSCHNITT = "(noch keiner)"
#: Die Titel aller gelaufenen Abschnitte. Die bloße Anzahl
#: genügt nicht: Ein doppelt gezählter Abschnitt würde einen
#: fehlenden ausgleichen und die Lücke verdecken.
GESEHEN: list = []

#: So viele Abschnitte muss ein vollständiger Lauf durchlaufen.
#:
#: Ohne diese Zahl kann die Suite stillschweigend schrumpfen: Fehlt
#: ffmpeg, der Windows-Tresor oder Tkinter, entfallen ganze Blöcke -
#: und am Ende steht trotzdem "Fehlgeschlagen: 0". Wer der Zahl
#: vertraut, hört auf, selbst hinzusehen.
ABSCHNITTE_ERWARTET = 49


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [ok]   {name}")
    else:
        FAILED += 1
        print(f"  [FEHL] {name}" + (f"  -> {detail}" if detail else ""))


def uebersprungen(name: str, grund: str) -> None:
    """Eine Prüfung, die hier nicht laufen kann - sichtbar, nicht grün.

    Früher wurde so etwas als bestanden gezählt: "Tkinter steht zur
    Verfügung" bekam einen Haken, gerade WEIL Tkinter fehlte. Ein
    übersprungener Test ist aber kein bestandener.
    """
    global UEBERSPRUNGEN
    UEBERSPRUNGEN += 1
    print(f"  [--]   {name}  -> übersprungen: {grund}")


#: Alle Arbeitsordner dieses Laufs. Sie wurden bisher nie gelöscht -
#: 66 Ordner mit rund 48 MB lagen nach den heutigen Läufen im
#: Temp-Verzeichnis. Der neue Außenrahmen machte es schlimmer: Er
#: fängt Abbrüche ab, der Lauf endet äußerlich normal, und der
#: Müll bleibt stumm liegen.
ARBEITSORDNER: list = []


def arbeitsordner(praefix: str = "dreamevoice_selftest_") -> Path:
    """Ein Arbeitsordner, der am Ende des Laufs verschwindet."""
    ordner = Path(tempfile.mkdtemp(prefix=praefix))
    ARBEITSORDNER.append(ordner)
    return ordner


def aufraeumen() -> int:
    """Löscht alle Arbeitsordner. Gibt zurück, was übrigblieb."""
    rest = 0
    for ordner in ARBEITSORDNER:
        shutil.rmtree(ordner, ignore_errors=True)
        if ordner.exists():
            rest += 1
    ARBEITSORDNER.clear()
    return rest


def section(title: str) -> None:
    global ABSCHNITTE, LETZTER_ABSCHNITT
    ABSCHNITTE += 1
    LETZTER_ABSCHNITT = title
    GESEHEN.append(title)
    print(f"\n{title}")
    print("-" * len(title))


def make_fake_base(path: Path, ids: list[int], ogg_bytes: bytes) -> None:
    """Baut ein Ersatz-Originalpaket mit derselben Struktur wie das echte."""
    with tarfile.open(path, "w:gz") as tf:
        for sound_id in ids:
            info = tarfile.TarInfo(f"{sound_id}.ogg")
            info.size = len(ogg_bytes)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(ogg_bytes))
        for meta, payload in (
            ("voice_mapping.json", b'{"18": {"856": ["dreame.vacuum.r2532h"]}}'),
            ("tts.json", b'{"tts_base_general": []}'),
            ("dmr_audio.json", b'{"0": [10, 0, 0, 100]}'),
            ("first_audio.json", b'{"first_audio_number": [323]}'),
            ("mini_broad.json", b'{"0": 1}'),
            ("time.txt", b"2026-01-28 13:20:01"),
        ):
            info = tarfile.TarInfo(meta)
            info.size = len(payload)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(payload))


@contextlib.contextmanager
def leise(*namen: str):
    """Schaltet Logger stumm.

    Manche Prüfungen lösen absichtlich einen Fehlerfall aus - dass die
    App ihn protokolliert, ist ja gerade richtig. Auf der Konsole sähe es
    aber nach einem kaputten Selbsttest aus, und Windows PowerShell macht
    aus jeder stderr-Zeile ohnehin einen Fehlerdatensatz.
    """
    logger = [logging.getLogger(n) for n in namen]
    vorher = [ll.disabled for ll in logger]
    for ll in logger:
        ll.disabled = True
    try:
        yield
    finally:
        for ll, alt in zip(logger, vorher):
            ll.disabled = alt


def minimal_vorbis_ogg() -> bytes:
    """Eine Ogg-Seite mit gültigem Vorbis-Kopf (mono, 16000 Hz).

    Reicht für die Formaterkennung; als Audio ist sie nicht abspielbar.
    """
    identification = (
        b"\x01vorbis"
        + (0).to_bytes(4, "little")      # Version
        + bytes([1])                     # Kanäle
        + (16000).to_bytes(4, "little")  # Abtastrate
        + b"\x00" * 16
    )
    page = bytearray(b"OggS")
    page += bytes([0, 2])                       # Version, Kopfseite
    page += (0).to_bytes(8, "little")           # Granule
    page += (1).to_bytes(4, "little")           # Serie
    page += (0).to_bytes(4, "little")           # Seitennummer
    page += (0).to_bytes(4, "little")           # Prüfsumme (hier egal)
    page += bytes([1, len(identification)])     # 1 Segment
    page += identification
    return bytes(page)


def _alle_pruefungen() -> None:
    work = arbeitsordner()
    print(f"Arbeitsordner: {work}")

    ogg = minimal_vorbis_ogg()

    # ---------------------------------------------------------------
    section("1. Audioformat erkennen")
    sample = work / "sample.ogg"
    sample.write_bytes(ogg)
    info = audio.probe_ogg(sample)
    check("Ogg-Kopf wird gelesen", info is not None)
    check("Codec erkannt: vorbis", info and info.codec == "vorbis",
          str(info and info.codec))
    check("Mono erkannt", info and info.channels == 1)
    check("16000 Hz erkannt", info and info.rate == 16000)
    check("Zielformat wird als passend erkannt", info and info.is_target_format)
    check("Keine Umwandlung nötig", not audio.needs_conversion(sample))

    wav = work / "sample.wav"
    wav.write_bytes(b"RIFF....WAVEfmt ")
    check("wav wird als umwandlungsbedürftig erkannt", audio.needs_conversion(wav))

    ffmpeg = audio.find_ffmpeg()
    print(f"  (Hinweis: ffmpeg {'gefunden: ' + str(ffmpeg) if ffmpeg else 'nicht gefunden'})")

    # ---------------------------------------------------------------
    section("2. Sound-Katalog")
    catalog = SoundCatalog.load()
    check("Katalog geladen", len(catalog) > 0, f"{len(catalog)} Einträge")
    # 616 = Vereinigung der beiden Varianten des X50 Ultra Complete:
    # r2532h hat 558 Ansagen, r2532v hat 613. Welche davon wirklich
    # gebraucht werden, entscheidet zur Laufzeit das Originalpaket
    # (SoundCatalog.restrict_to).
    check("616 Ansagen (X50 Ultra Complete, beide Varianten)",
          len(catalog) == 616, str(len(catalog)))
    check("Ansage 7 vorhanden", catalog.get(7) is not None)
    check("Ansage 7 hat deutsches Label",
          catalog.get(7) is not None and catalog.get(7).has_german_label,
          catalog.get(7).de if catalog.get(7) else "-")
    check("Gruppen vorhanden", len(catalog.groups()) >= 5, str(catalog.groups()))
    check("Filter 'nur wichtige' liefert Treffer",
          len(catalog.filtered(only_common=True)) > 20,
          str(len(catalog.filtered(only_common=True))))
    check("Suche nach 'Akku' findet etwas",
          len(catalog.filtered(search="Akku")) > 0)
    restricted = catalog.restrict_to([7, 12, 999])
    check("restrict_to ergänzt unbekannte IDs", len(restricted) == 3)
    check("restrict_to legt Platzhalter an", restricted.get(999) is not None)

    # ---------------------------------------------------------------
    section("3. Paketbau")
    base = work / "base.tar.gz"
    ids = [0, 7, 12, 40, 105]
    make_fake_base(base, ids, ogg)
    check("Originalpaket lesbar", official.list_sound_ids(base) == sorted(ids))
    meta = official.read_metadata(base)
    check("Steuerdateien erkannt", len(meta) == 6, str(sorted(meta)))

    custom = work / "custom.ogg"
    custom.write_bytes(ogg + b"UNTERSCHIED")

    import dreamevoice.paths as paths_mod
    original_build_dir = paths_mod.build_dir
    out_dir = work / "out"
    out_dir.mkdir()
    paths_mod.build_dir = lambda: out_dir
    packer.build_dir = lambda: out_dir

    try:
        result = packer.build_pack(
            base_pack=base,
            assignments={7: custom, 12: custom},
            out_name="test.tar.gz",
            work_dir=work / "prep",
        )
    except DreameError as exc:
        check("Paket gebaut", False, str(exc))
        return 1

    check("Paket gebaut", result.path.is_file())
    check("Zwei Ansagen ersetzt", result.replaced == [7, 12], str(result.replaced))
    check("MD5 ist 32-stellig", len(result.md5) == 32)

    recomputed = hashlib.md5(result.path.read_bytes()).hexdigest()
    check("MD5 stimmt mit der Datei überein", recomputed == result.md5)
    check("Größe stimmt", result.path.stat().st_size == result.size)

    with tarfile.open(result.path, "r:gz") as tf:
        names = sorted(m.name for m in tf.getmembers())
        content_7 = tf.extractfile("7.ogg").read()
        content_0 = tf.extractfile("0.ogg").read()
        mapping = tf.extractfile("voice_mapping.json").read()

    check("Alle 5 Ansagen + 6 Steuerdateien enthalten", len(names) == 11, str(names))
    check("Ersetzte Ansage enthält die neue Datei", content_7 == custom.read_bytes())
    check("Nicht ersetzte Ansage unverändert", content_0 == ogg)
    check("Steuerdatei voice_mapping.json erhalten",
          b"r2532h" in mapping)

    # Ansage, die es im Original nicht gibt
    result2 = packer.build_pack(
        base_pack=base, assignments={999: custom},
        out_name="test2.tar.gz", work_dir=work / "prep2")
    check("Unbekannte Ansage wird ergänzt", 999 in result2.replaced)
    check("Warnung dazu ausgegeben", len(result2.warnings) == 1,
          str(result2.warnings))

    # Fehlerfälle
    try:
        packer.build_pack(base_pack=base, assignments={}, work_dir=work / "prep3")
        check("Leere Zuweisung wird abgelehnt", False)
    except DreameError:
        check("Leere Zuweisung wird abgelehnt", True)

    try:
        packer.build_pack(base_pack=work / "gibtsnicht.tar.gz",
                          assignments={7: custom}, work_dir=work / "prep4")
        check("Fehlendes Originalpaket wird abgelehnt", False)
    except DreameError:
        check("Fehlendes Originalpaket wird abgelehnt", True)

    # ---------------------------------------------------------------
    section("4. Fremdpaket überlagern")
    overlay_src = work / "overlay.tar.gz"
    with tarfile.open(overlay_src, "w:gz") as tf:
        for sound_id in (7, 40, 777):
            payload = ogg + f"OVERLAY{sound_id}".encode()
            info = tarfile.TarInfo(f"{sound_id}.ogg")
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))

    merged = packer.overlay_pack(base, overlay_src, out_name="merged.tar.gz")
    check("Überlagerung erfolgreich", merged.path.is_file())
    check("Nur passende IDs übernommen", merged.replaced == [7, 40],
          str(merged.replaced))
    check("Hinweis auf nicht passende ID", len(merged.warnings) == 1,
          str(merged.warnings))
    with tarfile.open(merged.path, "r:gz") as tf:
        merged_names = sorted(m.name for m in tf.getmembers())
    check("Struktur des Originals erhalten", len(merged_names) == 11,
          str(merged_names))

    # zip statt tar.gz
    import zipfile
    overlay_zip = work / "overlay.zip"
    with zipfile.ZipFile(overlay_zip, "w") as zf:
        zf.writestr("projekt-main/voice_pack/12.ogg", ogg + b"ZIP")
        zf.writestr("projekt-main/README.md", "egal")
    merged_zip = packer.overlay_pack(base, overlay_zip, out_name="merged_zip.tar.gz")
    check("zip-Archiv wird verstanden", merged_zip.replaced == [12],
          str(merged_zip.replaced))

    paths_mod.build_dir = original_build_dir

    # ---------------------------------------------------------------
    section("5. Webserver")
    srv = server.PackServer(result.path, port=0, host_ip="127.0.0.1")
    url = srv.start()
    try:
        check("Server gestartet", url.startswith("http://127.0.0.1:"))
        with urllib.request.urlopen(url, timeout=10) as resp:
            served = resp.read()
            length = resp.headers.get("Content-Length")
        check("Datei wird unverändert ausgeliefert",
              hashlib.md5(served).hexdigest() == result.md5)
        check("Content-Length stimmt", int(length) == result.size)
        # Das Ereignis feuert erst, wenn der Server ALLE Bytes
        # geschrieben hat - das kann Sekundenbruchteile nach dem
        # Lesen des Clients sein. Genau dafür gibt es
        # wait_for_download; die App benutzt es ebenso.
        check("Abruf wird registriert", srv.wait_for_download(5.0))

        wrong = url.rsplit("/", 1)[0] + "/andere_datei.tar.gz"
        try:
            urllib.request.urlopen(wrong, timeout=10)
            check("Fremde Pfade werden abgewiesen", False)
        except urllib.error.HTTPError as exc:
            check("Fremde Pfade werden abgewiesen", exc.code == 404, str(exc.code))
    finally:
        srv.stop()

    check("Freier Port wird gefunden", server.free_port() > 0)
    check("Lokale IP wird ermittelt", len(server.local_ip_for_internet().split(".")) == 4)

    # ---------------------------------------------------------------
    section("6. Paketkennung prüfen")
    check("Leere Kennung wird zu CUSTOM",
          installer.validate_lang_id("")[0] == "CUSTOM")
    check("Kleinschreibung wird umgewandelt",
          installer.validate_lang_id("bayern")[0] == "BAYERN")
    check("Offizielle Kennung erzeugt Warnung",
          installer.validate_lang_id("DE")[1] != "")
    check("Eigene Kennung ohne Warnung",
          installer.validate_lang_id("CUSTOM")[1] == "")
    for bad in ("mit leerzeichen", "VIELZULANGEKENNUNG", "a-b"):
        try:
            installer.validate_lang_id(bad)
            check(f"Ungültige Kennung {bad!r} abgelehnt", False)
        except DreameError:
            check(f"Ungültige Kennung {bad!r} abgelehnt", True)

    # ---------------------------------------------------------------
    section("7. Cloud-Protokoll (ohne Netzwerk)")
    cloud = DreameCloud("dreame")
    check("Passwort-Hash ist 32-stelliges Hex",
          len(cloud.hash_password("test")) == 32)
    check("Passwort-Hash ist reproduzierbar",
          cloud.hash_password("test") == cloud.hash_password("test"))
    check("Salz wird verwendet",
          cloud.hash_password("test") != hashlib.md5(b"test").hexdigest())
    check("Basis-URL für eu korrekt",
          cloud._base_url("eu") == "https://eu.iot.dreame.tech:13267",
          cloud._base_url("eu"))

    from dreamevoice.cloud import Device
    device = Device({"did": "123", "model": "dreame.vacuum.r2532h",
                     "bindDomain": "eu1.iot.dreame.tech:1883", "mac": "AA:BB"})
    check("Roboter wird als Saugroboter erkannt", device.is_vacuum)
    check("Befehlspfad enthält die Region",
          cloud._command_path(device.bind_domain) == "dreame-iot-com-eu1/device/sendCommand",
          cloud._command_path(device.bind_domain))
    check("Befehlspfad ohne bindDomain fällt zurück",
          cloud._command_path("") == "dreame-iot-com/device/sendCommand")

    # ---------------------------------------------------------------
    section("8. Dialektpakete")
    from dreamevoice import dialect  # noqa: E402

    check("Dialekte vorhanden", len(dialect.DIALECTS) >= 5,
          str(len(dialect.DIALECTS)))

    # Gemeinsamer Kern: was jeder Dialekt mindestens abdecken muss.
    kern = set.intersection(*(set(p.texts) for p in dialect.DIALECTS))
    check("gemeinsamer Kern umfasst mindestens 239 Ansagen", len(kern) >= 239,
          str(len(kern)))
    check("Kern enthält die wichtigsten Ansagen",
          {7, 12, 13, 20, 40, 111, 421, 515}.issubset(kern))

    # Die Zeichenzahl steht in der Hilfe und in docs/Eigene-Stimmen.md -
    # danach entscheidet jemand, ob sein ElevenLabs-Kontingent reicht.
    # Vorher stand dort eine Spanne, die nicht mehr stimmte, und eine
    # Zeile über einen "gemeinsamen Kern von 239 Ansagen", den es seit
    # der Vervollständigung aller sieben Dialekte nicht mehr gibt.
    _zeichen = sorted(sum(len(t) for t in p.texts.values())
                      for p in dialect.DIALECTS)
    # Die Spanne im Text ist auf volle Hundert gerundet, deshalb 100
    # Spielraum nach unten: 22.693 darf als "22.700" dastehen.
    check("ein Dialektpaket liegt zwischen 22.700 und 25.000 Zeichen",
          22_600 <= _zeichen[0] and _zeichen[-1] <= 25_000,
          f"{_zeichen[0]}-{_zeichen[-1]}")
    _hilfe = (Path(__file__).resolve().parent / "dreamevoice" / "ui"
              / "app.py").read_text(encoding="utf-8-sig")
    check("die Hilfe nennt diese Spanne", "22.700\nbis 25.000" in _hilfe
          or "22.700\n  bis 25.000" in _hilfe or "22.700" in _hilfe)
    _es = (Path(__file__).resolve().parent / "docs" / "Eigene-Stimmen.md")
    if _es.is_file():
        _txt_es = _es.read_text(encoding="utf-8")
        check("die Anleitung nennt keinen 239-Ansagen-Kern mehr",
              "239 Ansagen" not in _txt_es)
        check("und dieselbe Spanne wie die Hilfe",
              "22.700–25.000" in _txt_es or "22.700-25.000" in _txt_es)

    kennungen = set()
    for pack in dialect.DIALECTS:
        check(f"{pack.name}: deckt den gemeinsamen Kern ab",
              kern.issubset(set(pack.texts)),
              f"{len(kern - set(pack.texts))} fehlen")
        check(f"{pack.name}: kein Text leer",
              all(t.strip() for t in pack.texts.values()))
        check(f"{pack.name}: nur Ansagen, die es im Modell gibt",
              set(pack.texts).issubset(set(catalog.ids())),
              str(sorted(set(pack.texts) - set(catalog.ids()))[:10]))
        cleaned, warning = installer.validate_lang_id(pack.lang_id)
        check(f"{pack.name}: Kennung {cleaned} kollidiert nicht mit Dreame",
              warning == "", warning)
        check(f"{pack.name}: Kennung eindeutig", cleaned not in kennungen)
        kennungen.add(cleaned)
        check(f"{pack.name}: drei Beispielsätze für die Hörprobe",
              len(dialect.sample_texts(pack, 3)) == 3)

    from dreamevoice import elevenlabs  # noqa: E402
    for pack in dialect.DIALECTS:
        chars = elevenlabs.estimate_characters(pack.texts)
        # Nur zur Information: volle Abdeckung sprengt das Freikontingent
        # eines Monats, deshalb kann die App teilweise erzeugen und später
        # fortsetzen.
        check(f"{pack.name}: {pack.count} Ansagen, {chars} Zeichen",
              chars > 0, str(chars))

    # ---------------------------------------------------------------
    section("9. ElevenLabs-Anbindung (mit nachgestellten Antworten)")
    import json as _json  # noqa: E402

    _calls = []

    class _Resp:
        def __init__(self, status, payload=None, content=b""):
            self.status_code = status
            self._payload = payload or {}
            self.text = _json.dumps(self._payload)
            self.content = content

        def json(self):
            return self._payload

    _tts_calls = {"n": 0, "limit": 4}

    def _fake(method, url, headers=None, timeout=None, **kwargs):
        _calls.append((url, kwargs.get("params")))
        if "text-to-speech" in url:
            _tts_calls["n"] += 1
            if _tts_calls["n"] > _tts_calls["limit"]:
                return _Resp(429, {"detail": "quota"})
            return _Resp(200, content=b"ID3" + b"\x00" * 2000)
        if "/v2/voices" in url:
            token = (kwargs.get("params") or {}).get("next_page_token")
            if token is None:
                return _Resp(200, {"voices": [
                    {"voice_id": "a", "name": "Premade", "category": "premade"},
                    {"voice_id": "b", "name": "Selbstbau", "category": "generated",
                     "labels": {"accent": "bavarian"}}],
                    "has_more": True, "next_page_token": "s2"})
            return _Resp(200, {"voices": [
                {"voice_id": "c", "name": "Dritte", "category": "premade"}],
                "has_more": False, "next_page_token": None})
        if url.endswith("/v1/voices/b"):
            return _Resp(200, {"voice_id": "b", "name": "Selbstbau",
                               "category": "generated",
                               "labels": {"accent": "bavarian"}})
        if url.endswith("/v1/voices/weg"):
            return _Resp(404, {"detail": "not found"})
        return _Resp(200, {"voices": []})

    _orig_request = elevenlabs._http
    elevenlabs._http = _fake
    try:
        voices = elevenlabs.list_voices("k")
        check("Stimmenliste blättert über alle Seiten", len(voices) == 3,
              str(len(voices)))
        check("Auflistung nutzt die v2-Schnittstelle",
              any("/v2/voices" in c[0] for c in _calls))
        check("page_size wird auf 100 gesetzt",
              _calls[0][1].get("page_size") == 100, str(_calls[0][1]))

        eigene = [v for v in voices if v.is_own_creation]
        check("selbst erzeugte Stimme wird erkannt", len(eigene) == 1,
              str([v.name for v in voices]))

        voice = elevenlabs.get_voice("k", "b")
        check("Stimme über ihre ID abrufbar", voice.voice_id == "b")
        check("bayerische Stimme wird erkannt", voice.is_bavarian)

        try:
            elevenlabs.get_voice("k", "weg")
            check("unbekannte Stimmen-ID wird abgefangen", False)
        except DreameError as exc:
            check("unbekannte Stimmen-ID wird abgefangen",
                  "Copy Voice ID" in exc.hint)

        # Teilerzeugung: Kontingent reicht nur für einen Teil
        texte = {i: f"Satz {i}." for i in range(1, 9)}
        ordner = work / "eleven"
        teil = elevenlabs.synthesize(texte, ordner, api_key="k", voice_id="v")
        check("Teilerzeugung liefert das Bisherige", len(teil) == 4,
              str(len(teil)))

        _tts_calls["n"] = 0
        _tts_calls["limit"] = 99
        voll = elevenlabs.synthesize(texte, ordner, api_key="k", voice_id="v")
        check("zweiter Anlauf vervollständigt", len(voll) == 8, str(len(voll)))
        check("bereits Gesprochenes kostet nichts mehr",
              _tts_calls["n"] == 4, f"{_tts_calls['n']} Anfragen")
    finally:
        elevenlabs._http = _orig_request

    # -- Klang: die Einstellungen der Stimme müssen gelten ----------------
    _gesendet = []
    _stimme = {"stability": 0.20, "similarity_boost": 0.80, "style": 0.65,
               "use_speaker_boost": True}

    def _fake_klang(method, url, headers=None, timeout=None, **kwargs):
        if url.endswith("/settings"):
            return _Resp(200, _stimme)
        if "text-to-speech" in url:
            _gesendet.append(kwargs.get("json"))
            return _Resp(200, content=b"ID3" + b"\x00" * 2000)
        if url.endswith("/v1/models"):
            return _Resp(200, [
                {"model_id": "eleven_multilingual_v2", "name": "Multilingual",
                 "can_do_text_to_speech": True},
                {"model_id": "scribe_v1", "name": "Scribe",
                 "can_do_text_to_speech": False}])
        return _Resp(200, {})

    elevenlabs._http = _fake_klang
    try:
        gelesen = elevenlabs.get_voice_settings("k", "v")
        check("Klangeinstellungen der Stimme werden gelesen",
              gelesen == _stimme, str(gelesen))
        check("niedrige Stabilität wird als lebendig beschrieben",
              "lebendig" in elevenlabs.describe_settings(gelesen))

        elevenlabs.synthesize({1: "Probe."}, work / "klang1", api_key="k",
                              voice_id="v")
        check("Stimme klingt wie eingestellt, nicht wie von der App überstülpt",
              _gesendet and _gesendet[-1].get("voice_settings") == _stimme,
              str(_gesendet[-1].get("voice_settings") if _gesendet else None))

        _gesendet.clear()
        eigene = {"stability": 0.15, "style": 0.7}
        elevenlabs.synthesize({1: "Probe."}, work / "klang2", api_key="k",
                              voice_id="v", voice_settings=eigene,
                              use_voice_settings=False)
        check("eigene Regler werden übernommen",
              _gesendet[-1].get("voice_settings") == eigene)

        _gesendet.clear()
        elevenlabs.synthesize({1: "Probe."}, work / "klang3", api_key="k",
                              voice_id="v", model="eleven_turbo_v2_5")
        check("gewähltes Modell wird benutzt",
              _gesendet[-1].get("model_id") == "eleven_turbo_v2_5")

        modelle = elevenlabs.list_models("k")
        check("nur Sprachausgabe-Modelle in der Auswahl",
              [m["id"] for m in modelle] == ["eleven_multilingual_v2"],
              str(modelle))
    finally:
        elevenlabs._http = _orig_request

    # ---------------------------------------------------------------
    section("10. Dateien stapelweise übernehmen")
    from dreamevoice import importer  # noqa: E402

    for name, erwartet in (("7.ogg", 7), ("007.wav", 7),
                           ("7 - Reinigung.mp3", 7), ("Ansage_12.ogg", 12),
                           ("ohne-nummer.wav", None)):
        check(f"Dateiname {name!r} ergibt Ansage {erwartet}",
              importer.sound_id_from_name(name) == erwartet,
              str(importer.sound_id_from_name(name)))

    quelle = work / "import"
    quelle.mkdir()
    for name in ("7.ogg", "012.wav", "9999.ogg", "keine_nummer.ogg", "text.txt"):
        (quelle / name).write_bytes(ogg)
    (quelle / "tief").mkdir()
    (quelle / "tief" / "40.ogg").write_bytes(ogg)

    erg = importer.scan_folder(quelle, catalog.ids())
    check("gültige Dateien werden zugeordnet", erg.count == 3,
          str(sorted(erg.assigned)))
    check("Unterordner wird durchsucht", 40 in erg.assigned)
    check("unbekannte Ansage-Nummer aussortiert", erg.unknown_ids == [9999],
          str(erg.unknown_ids))
    check("Dateien ohne Nummer übersprungen",
          any("keine_nummer" in s for s in erg.skipped))
    check("Nicht-Audio übersprungen", any("text.txt" in s for s in erg.skipped))

    archiv = work / "fremd.tar.gz"
    with tarfile.open(archiv, "w:gz") as tf:
        for sid in (7, 12):
            info = tarfile.TarInfo(f"irgendwo/tief/{sid}.ogg")
            info.size = len(ogg)
            tf.addfile(info, io.BytesIO(ogg))
    erg2 = importer.import_archive(archiv, work / "entpackt", catalog.ids())
    check("Archiv wird ausgepackt und zugeordnet", erg2.count == 2,
          str(sorted(erg2.assigned)))
    check("Pfade aus dem Archiv werden verworfen",
          all(p.parent.name == "fremd" for p in erg2.assigned.values()))

    vorlage = importer.create_template_folder(
        {7: sample, 12: sample}, catalog, work / "vorlage")
    check("Vorlagenordner enthält beide Ansagen",
          (vorlage / "7.ogg").is_file() and (vorlage / "12.ogg").is_file())
    check("Anleitung wird mitgeliefert", (vorlage / "_Anleitung.txt").is_file())
    check("Anleitung nennt die Bedeutung",
          "7.ogg" in (vorlage / "_Anleitung.txt").read_text(encoding="utf-8"))

    # ---------------------------------------------------------------
    section("11. Eigene Dialekttexte")
    from dreamevoice.config import Config  # noqa: E402

    bay = dialect.DIALECTS[0]
    cfg = Config()
    cfg.set_dialect_overrides(bay.key, {7: "Mei eigener Text."})
    gespeichert = cfg.dialect_overrides(bay.key)
    check("Änderung wird gespeichert", gespeichert == {7: "Mei eigener Text."},
          str(gespeichert))

    angepasst = dialect.with_overrides(bay, gespeichert)
    check("Text wird tatsächlich ersetzt",
          angepasst.texts[7] == "Mei eigener Text.")
    check("mitgelieferter Text bleibt unangetastet",
          bay.texts[7] != "Mei eigener Text.")
    check("übrige Ansagen unverändert", angepasst.texts[12] == bay.texts[12])
    check("Anzahl bleibt gleich", angepasst.count == bay.count)
    check("geänderte Nummer wird gemeldet",
          dialect.changed_ids(bay, gespeichert) == [7])
    check("leerer Text ändert nichts",
          dialect.with_overrides(bay, {12: "  "}).texts[12] == bay.texts[12])
    check("Änderung übersteht das Neuladen",
          Config(cfg.as_dict()).dialect_overrides(bay.key) == gespeichert)

    # ---------------------------------------------------------------
    section("12. Nummern-Umsetzung des Modells")

    # Ein Paket, das die Umsetzung nachbildet: 18 -> 856
    mapping_pack = work / "mit_mapping.tar.gz"
    with tarfile.open(mapping_pack, "w:gz") as tf:
        for sound_id in (7, 18, 856):
            info = tarfile.TarInfo(f"{sound_id}.ogg")
            info.size = len(ogg)
            tf.addfile(info, io.BytesIO(ogg))
        vm = _json.dumps({
            "18": {"856": ["dreame.vacuum.r2532h", "dreame.vacuum.r2489a"]},
            "112": {"858": ["dreame.vacuum.andere"]},
        }).encode("utf-8")
        info = tarfile.TarInfo("voice_mapping.json")
        info.size = len(vm)
        tf.addfile(info, io.BytesIO(vm))

    umsetzung = official.read_voice_mapping(mapping_pack, "dreame.vacuum.r2532h")
    check("Umsetzung für das eigene Modell gelesen", umsetzung == {18: 856},
          str(umsetzung))
    check("Umsetzung anderer Modelle wird ignoriert", 112 not in umsetzung)
    check("ohne Modell keine Umsetzung",
          official.read_voice_mapping(mapping_pack, "") == {})

    gespiegelt = packer.apply_mapping({18: sample}, umsetzung)
    check("ausgetauschte Ansage landet auch auf der Zielnummer",
          gespiegelt.get(856) == sample and gespiegelt.get(18) == sample,
          str(sorted(gespiegelt)))

    rueck = packer.apply_mapping({856: sample}, umsetzung)
    check("umgekehrt genauso", rueck.get(18) == sample)

    unberuehrt = packer.apply_mapping({7: sample}, umsetzung)
    check("nicht betroffene Ansagen bleiben unberührt",
          set(unberuehrt) == {7})

    ergebnis_map = packer.build_pack(
        base_pack=mapping_pack, assignments={18: custom},
        out_name="mapping.tar.gz", work_dir=work / "prep_map",
        mapping=umsetzung)
    with tarfile.open(ergebnis_map.path, "r:gz") as tf:
        inhalt_18 = tf.extractfile("18.ogg").read()
        inhalt_856 = tf.extractfile("856.ogg").read()
    check("gebautes Paket ersetzt beide Nummern",
          inhalt_18 == custom.read_bytes() and inhalt_856 == custom.read_bytes())

    # ---------------------------------------------------------------
    section("13. Stimme einstellen und Fortschritt")
    from dreamevoice import tts  # noqa: E402

    check("Tempostufe 0 ergibt +0 %", tts._ssml_prozent(0) == "+0%")
    check("Stufe -3 ergibt -30 %", tts._ssml_prozent(-3) == "-30%")
    check("Stufe 4 ergibt +40 %", tts._ssml_prozent(4) == "+40%")
    check("Extremwerte werden begrenzt",
          tts._ssml_prozent(99) == "+50%" and tts._ssml_prozent(-99) == "-50%")

    lauf = work / "lauf"
    (lauf / "gesprochen").mkdir(parents=True)
    for sound_id in (7, 12, 40):
        (lauf / "gesprochen" / f"{sound_id}.wav").write_bytes(b"x" * 2000)
    (lauf / "gesprochen" / "leer.wav").write_bytes(b"x" * 10)

    check("gesprochene Ansagen werden gezählt", dialect.spoken_count(lauf) == 3,
          str(dialect.spoken_count(lauf)))
    offen = dialect.remaining_texts(bay, lauf)
    check("offene Ansagen richtig berechnet",
          len(offen) == bay.count - 3 and 7 not in offen and 12 not in offen,
          str(len(offen)))
    check("ohne Zwischenspeicher ist alles offen",
          len(dialect.remaining_texts(bay, work / "gibtsnicht")) == bay.count)

    # Zusammenfügen der Hörprobe - nur wenn ffmpeg vorhanden ist
    ffmpeg_da = audio.find_ffmpeg()
    if ffmpeg_da:
        einzel = []
        for nummer in range(3):
            ziel = work / f"ton{nummer}.wav"
            proc = audio._run([str(ffmpeg_da), "-hide_banner", "-loglevel",
                               "error", "-y", "-f", "lavfi", "-t", "1",
                               "-i", f"sine=frequency={300 + nummer * 100}:r=16000",
                               "-ac", "1", str(ziel)])
            if proc.returncode == 0:
                einzel.append(ziel)
        if len(einzel) == 3:
            zusammen = audio.concat_with_pauses(einzel, work / "zusammen.wav",
                                                ffmpeg_da, pause=0.5)
            import wave as _wave
            with _wave.open(str(zusammen)) as w:
                laenge = w.getnframes() / w.getframerate()
            check(f"drei Töne plus Pausen ergeben eine Datei ({laenge:.1f}s)",
                  zusammen != einzel[0] and 3.8 < laenge < 4.2, f"{laenge:.2f}s")
    else:
        print("  (übersprungen: ffmpeg nicht vorhanden)")

    # ---------------------------------------------------------------
    section("14. Zwischenspeicher: was bleibt, was wird erneuert")

    def _lege_an(ordner, ids):
        (ordner / "gesprochen").mkdir(parents=True, exist_ok=True)
        for sid in ids:
            (ordner / "gesprochen" / f"{sid}.wav").write_bytes(b"x" * 3000)

    proben = [7, 12, 13, 20]

    # Aus einer Sicherung kopiert - kein Herkunftsvermerk vorhanden
    sicherung = work / "cache_sicherung"
    _lege_an(sicherung, proben)
    passend, uebernommen, veraltet = dialect.classify_recordings(bay, sicherung)
    check("kopierte Aufnahmen werden übernommen, nicht verworfen",
          len(uebernommen) == 4 and not veraltet,
          f"passend={len(passend)} übernommen={len(uebernommen)} alt={veraltet}")
    check("sie gelten als erledigt",
          all(i not in dialect.remaining_texts(bay, sicherung) for i in proben))

    # Von Hand überschriebene Datei bei unverändertem Text
    hand = work / "cache_hand"
    _lege_an(hand, proben)
    dialect.write_manifest(hand, {i: bay.texts[i] for i in proben})
    (hand / "gesprochen" / "7.wav").write_bytes(b"eigene aufnahme" * 200)
    passend, uebernommen, veraltet = dialect.classify_recordings(bay, hand)
    check("von Hand ersetzte Aufnahme bleibt erhalten",
          7 in passend and not veraltet, str(veraltet))
    check("ihr Inhalt wird nicht angefasst",
          (hand / "gesprochen" / "7.wav").read_bytes().startswith(b"eigene"))

    # Text geändert -> nur diese eine erneuern
    anders = dialect.with_overrides(bay, {12: "Ein völlig anderer Satz."})
    passend, uebernommen, veraltet = dialect.classify_recordings(anders, hand)
    check("nur die geänderte Ansage gilt als veraltet", veraltet == [12],
          str(veraltet))
    check("die übrigen bleiben stehen", len(passend) == 3, str(sorted(passend)))

    # Gelöschter Ordner
    check("nach dem Löschen ist alles offen",
          len(dialect.remaining_texts(bay, work / "gibtsnichtmehr")) == bay.count)

    # Müll wird ignoriert
    schmutz = work / "cache_schmutz"
    _lege_an(schmutz, [7])
    (schmutz / "gesprochen" / "12.wav").write_bytes(b"x" * 10)
    (schmutz / "gesprochen" / "notiz.txt").write_text("egal", encoding="utf-8")
    (schmutz / "gesprochen" / "99999.wav").write_bytes(b"x" * 3000)
    check("leere, fremde und unbekannte Dateien zählen nicht",
          dialect.spoken_count(schmutz, bay) == 1,
          str(dialect.spoken_count(schmutz, bay)))

    # ---------------------------------------------------------------
    section("15. Windows-Anmeldeinformationsspeicher")
    from dreamevoice import credentials  # noqa: E402
    from dreamevoice.config import Config as _Config  # noqa: E402

    if credentials.available():
        ziel = "DreameSprachpaket:Selbsttest"
        credentials.delete(ziel)
        check("Speichern klappt", credentials.save(ziel, "sk_probe_äöü"))
        check("Auslesen ergibt denselben Wert",
              credentials.load(ziel) == "sk_probe_äöü", str(credentials.load(ziel)))
        credentials.delete(ziel)
        check("Löschen entfernt den Eintrag", credentials.load(ziel) is None)

        # ACHTUNG: Der Selbsttest hat hier einmal die *echten* Einträge
        # benutzt - und damit bei jedem EXE-Bau den gespeicherten
        # ElevenLabs-Schlüssel des Nutzers gelöscht. Deshalb läuft der
        # Test jetzt ausschließlich auf eigenen Zielnamen, und am Ende
        # wird geprüft, dass die echten unangetastet geblieben sind.
        echt_dreame = credentials.exists(credentials.TARGET_DREAME)
        echt_eleven = credentials.exists(credentials.TARGET_ELEVENLABS)

        alt_dreame = credentials.TARGET_DREAME
        alt_eleven = credentials.TARGET_ELEVENLABS
        credentials.TARGET_DREAME = "DreameSprachpaket:Selbsttest-Dreamehome"
        credentials.TARGET_ELEVENLABS = "DreameSprachpaket:Selbsttest-ElevenLabs"
        try:
            credentials.delete(credentials.TARGET_ELEVENLABS)
            cfg2 = _Config()
            cfg2.set_elevenlabs_key("sk_selbsttest_1234567890")
            check("Schlüssel landet im Anmeldespeicher",
                  credentials.load(credentials.TARGET_ELEVENLABS)
                  == "sk_selbsttest_1234567890")
            check("und nicht in der config.json",
                  cfg2.as_dict().get("elevenlabs_key_enc") == "",
                  repr(cfg2.as_dict().get("elevenlabs_key_enc")))
            check("eine neue Sitzung findet ihn wieder",
                  _Config().elevenlabs_key == "sk_selbsttest_1234567890")
            cfg2.forget_elevenlabs_key()
            check("Vergessen räumt überall auf",
                  _Config().elevenlabs_key == ""
                  and credentials.load(credentials.TARGET_ELEVENLABS) is None)
        finally:
            credentials.delete(credentials.TARGET_ELEVENLABS)
            credentials.delete(credentials.TARGET_DREAME)
            credentials.TARGET_DREAME = alt_dreame
            credentials.TARGET_ELEVENLABS = alt_eleven

        check("der echte Dreamehome-Eintrag ist unangetastet",
              credentials.exists(credentials.TARGET_DREAME) == echt_dreame,
              f"vorher {echt_dreame}, nachher "
              f"{credentials.exists(credentials.TARGET_DREAME)}")
        check("der echte ElevenLabs-Schlüssel ist unangetastet",
              credentials.exists(credentials.TARGET_ELEVENLABS) == echt_eleven,
              f"vorher {echt_eleven}, nachher "
              f"{credentials.exists(credentials.TARGET_ELEVENLABS)}")
    else:
        print("  (übersprungen: nur unter Windows verfügbar)")

    # ---------------------------------------------------------------
    section("16. Mitgeliefertes ffmpeg")
    from dreamevoice import embedded  # noqa: E402

    check("Anhang-Signatur ist 16 Byte", len(embedded.MAGIC) == 16)
    check("Trailer ist 24 Byte", embedded.TRAILER_SIZE == 24)
    check("ohne EXE wird kein Anhang gemeldet", embedded.payload_size() == 0)

    # ---------------------------------------------------------------
    section("17. Lautstärke wie bei den Originalansagen")
    from dreamevoice import loudness  # noqa: E402

    check("ohne Messwerte gilt der allgemeine Zielwert",
          loudness.target_for({}, 7) == audio.TARGET_LUFS)
    check("mit Messwert gilt der Wert der Originalansage",
          loudness.target_for({7: -14.2, 8: -17.0}, 7) == -14.2)
    check("fehlt die Nummer, wird der Median genommen",
          loudness.target_for({1: -20.0, 2: -16.0, 3: -13.0}, 99) == -16.0)
    check("Ausreißer nach oben werden begrenzt",
          loudness.target_for({7: -3.0}, 7) == -12.0)
    check("Ausreißer nach unten werden begrenzt",
          loudness.target_for({7: -40.0}, 7) == -24.0)

    laut_dir = work / "laut"
    laut_dir.mkdir(parents=True, exist_ok=True)
    if ffmpeg_da:
        # Zwei gleich laute Töne, einer davon künstlich abgesenkt.
        quelle = laut_dir / "ton.wav"
        audio._run([str(ffmpeg_da), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-t", "3", "-i", "sine=frequency=440:r=16000",
                    "-af", "volume=-14dB", "-ac", "1", str(quelle)])
        gemessen = audio.measure_loudness(quelle, ffmpeg_da)
        check("Lautheit lässt sich messen",
              bool(gemessen) and -40 < gemessen["input_i"] < 0,
              f"{gemessen['input_i']:.1f} LUFS" if gemessen else "keine Messung")

        for ziel in (-16.0, -13.0):
            ergebnis = laut_dir / f"ziel{abs(int(ziel))}.ogg"
            audio.convert_to_pack_format(quelle, ergebnis, ffmpeg_da,
                                         target_lufs=ziel)
            nach = audio.measure_loudness(ergebnis, ffmpeg_da)
            abweichung = abs(nach["input_i"] - ziel) if nach else 99
            check(f"Ergebnis trifft {ziel:.0f} LUFS auf 0.5 genau",
                  abweichung <= 0.5,
                  f"{nach['input_i']:.2f} LUFS" if nach else "keine Messung")
            check(f"Spitzenpegel bleibt unter {audio.TARGET_PEAK} dBTP",
                  bool(nach) and nach["input_tp"] <= audio.TARGET_PEAK + 0.3,
                  f"{nach['input_tp']:.2f} dBTP" if nach else "-")

        # Ohne Angleichung darf nichts verändert werden.
        roh = laut_dir / "roh.ogg"
        audio.convert_to_pack_format(quelle, roh, ffmpeg_da, normalize=False)
        ohne = audio.measure_loudness(roh, ffmpeg_da)
        check("ohne Angleichung bleibt die Lautheit wie sie war",
              bool(ohne) and abs(ohne["input_i"] - gemessen["input_i"]) < 0.6,
              f"{ohne['input_i']:.2f} statt {gemessen['input_i']:.2f}"
              if ohne and gemessen else "-")

        # Zwischenspeicher der Messwerte
        fake = work / "laut_basis.tar.gz"
        make_fake_base(fake, [1, 2, 3], minimal_vorbis_ogg())
        check("ohne gespeicherte Tabelle wird nichts gefunden",
              loudness.load_cached(fake) is None)
        loudness._save(fake, {1: -16.0, 2: -14.5})
        wieder = loudness.load_cached(fake)
        check("gespeicherte Tabelle wird wiedergefunden",
              wieder == {1: -16.0, 2: -14.5}, str(wieder))
        fake.write_bytes(fake.read_bytes() + b"geaendert")
        check("nach Änderung am Paket wird neu gemessen",
              loudness.load_cached(fake) is None)
    else:
        print("  (übersprungen: ffmpeg nicht vorhanden)")

    # ---------------------------------------------------------------
    section("18. Namen, die es gar nicht gibt")
    import namecheck  # noqa: E402

    # Der Anlass: `show_info` war in tab_store.py benutzt, aber nicht
    # importiert. Auffallen konnte das erst beim Speichern geänderter
    # Dialekttexte - ein Zweig, den ein Selbsttest nie anfasst.
    probe = work / "namensprobe.py"
    probe.write_text(
        "from math import sqrt\n"
        "def f(x):\n"
        "    return sqrt(x) + gibtsnicht(x)\n", encoding="utf-8")
    funde = namecheck.pruefe_datei(probe)
    check("fehlender Name wird gefunden",
          [n for _, n in funde] == ["gibtsnicht"], str(funde))

    probe.write_text(
        "from math import sqrt\n"
        "def f(x):\n"
        "    hilfe = 2\n"
        "    return sqrt(x) * hilfe\n", encoding="utf-8")
    check("sauberer Code meldet nichts", namecheck.pruefe_datei(probe) == [],
          str(namecheck.pruefe_datei(probe)))

    projekt = Path(__file__).resolve().parent
    treffer = namecheck.pruefe_ordner(projekt / "dreamevoice")
    check("die App selbst benutzt nur bekannte Namen", not treffer,
          "; ".join(f"{p.name}: {[n for _, n in f]}"
                    for p, f in list(treffer.items())[:3]))

    # Anlass: dialect.generate(out_name=...) - den Parameter gab es nicht.
    # Der Name ist gültig, deshalb schlug die Prüfung oben nicht an; der
    # Fehler kam erst beim Erzeugen eines Pakets ans Licht.
    probe.write_text(
        "def machwas(a, b=1):\n"
        "    return a + b\n", encoding="utf-8")
    (work / "aufrufer.py").write_text(
        "import namensprobe\n"
        "namensprobe.machwas(1, b=2)\n"
        "namensprobe.machwas(1, c=3)\n", encoding="utf-8")
    schluessel = namecheck.pruefe_aufrufe(work)
    gefunden = [n for f in schluessel.values() for _, n in f]
    check("unbekanntes Schlüsselwort wird gefunden",
          any("'c'" in n for n in gefunden), str(gefunden))
    check("bekanntes Schlüsselwort meldet nichts",
          not any("'b'" in n for n in gefunden), str(gefunden))
    (work / "aufrufer.py").unlink(missing_ok=True)

    # Auch direkt importierte Funktionen: run_async(on_done=...) gab es
    # nicht, der Parameter heißt on_finally. Beim Import eines fertigen
    # Pakets wäre die App abgestürzt.
    (work / "aufrufer.py").write_text(
        "from namensprobe import machwas\n"
        "machwas(1, c=3)\n", encoding="utf-8")
    direkt = [n for f in namecheck.pruefe_aufrufe(work).values() for _, n in f]
    check("auch direkt importierte Funktionen werden geprüft",
          any("machwas()" in n and "'c'" in n for n in direkt), str(direkt))
    (work / "aufrufer.py").unlink(missing_ok=True)

    check("die App ruft nur mit bekannten Schlüsselwörtern auf",
          not namecheck.pruefe_aufrufe(projekt / "dreamevoice"),
          "; ".join(f"{p.name}: {[n for _, n in f]}" for p, f in
                    list(namecheck.pruefe_aufrufe(projekt / "dreamevoice")
                         .items())[:3]))

    import inspect  # noqa: E402
    unterschrift = inspect.signature(dialect.generate).parameters
    for erwartet in ("out_name", "mapping", "engine", "api_key", "voice_id",
                     "voice_settings", "rate", "pitch", "cancelled"):
        check(f"dialect.generate nimmt '{erwartet}' entgegen",
              erwartet in unterschrift)

    # ---------------------------------------------------------------
    section("19. Dialekttexte als Datei aus- und einlesen")
    from dreamevoice import textfiles  # noqa: E402
    import dreamevoice.paths as _paths  # noqa: E402

    # Die Dateien landen im Datenordner - für den Test in einen eigenen.
    text_dir = work / "textdateien"
    text_dir.mkdir(parents=True, exist_ok=True)
    _alt_data_dir = textfiles.data_dir
    textfiles.data_dir = lambda: text_dir
    try:
        pfade = textfiles.write_all()
        check(f"{len(dialect.DIALECTS)} Dateien geschrieben",
              len(pfade) == len(dialect.DIALECTS), str(len(pfade)))
        check("jede Datei ist nach ihrem Dialekt benannt",
              all(p.stem == d.key for p, d in zip(pfade, dialect.DIALECTS)))

        bay = dialect.get("bayerisch")
        datei = textfiles.file_for("bayerisch")

        zurueck = textfiles.read_one(datei, bay)
        check("unverändert eingelesen ergibt keine Abweichung",
              zurueck.geaendert == 0, str(zurueck.overrides))
        check("dabei werden alle Ansagen gelesen",
              zurueck.gelesen == bay.count,
              f"{zurueck.gelesen} statt {bay.count}")

        # So etwa sieht es aus, wenn eine KI das Format nachlässig
        # wiedergibt: Vorspann, andere Abstände, eine erfundene Nummer,
        # eine Zeile ohne Text.
        datei.write_text(
            "Hier die überarbeitete Fassung:\n"
            "\n"
            "7 | Reinigung gestartet | Auf gehds, i fang o.\n"
            "  12|Reinigung fertig|Fertig samma.\n"
            "99999 | Gibt es nicht | Blabla\n"
            "  13 | Fährt zum Laden |\n"
            "Das war alles.\n", encoding="utf-8")
        wild = textfiles.read_one(datei, bay)
        check("umformatierte Antwort wird trotzdem gelesen",
              set(wild.overrides) == {7, 12}, str(wild.overrides))
        check("erfundene Nummern werden gemeldet, nicht übernommen",
              wild.unbekannt == [99999], str(wild.unbekannt))
        check("Zeilen ohne Text ändern nichts", wild.leer == 1, str(wild.leer))

        datei.write_text("7 | Bedeutung | Sag A | B | C\n", encoding="utf-8")
        strich = textfiles.read_one(datei, bay)
        check("senkrechter Strich im Text bleibt erhalten",
              strich.overrides == {7: "Sag A | B | C"}, str(strich.overrides))

        eigen = textfiles.write_one(bay, {7: "Mei ganz eigener Text."})
        check("eigene Texte stehen in der Datei",
              "Mei ganz eigener Text." in eigen.read_text(encoding="utf-8"))
        check("und kommen unverändert zurück",
              textfiles.read_one(eigen, bay).overrides
              == {7: "Mei ganz eigener Text."})

        datei.unlink()
        check("ensure_files legt nur Fehlendes an",
              len(textfiles.ensure_files()) == 1)
        check("und lässt beim zweiten Mal alles liegen",
              textfiles.ensure_files() == [])
    finally:
        textfiles.data_dir = _alt_data_dir

    # ---------------------------------------------------------------
    section("20. Gebaute Pakete überschreiben sich nicht")
    from dreamevoice import library  # noqa: E402

    check("Dialekt und Dienst stehen im Namen",
          library.suggest_name("Bayerisch", "elevenlabs", "Bairischer Bua")
          == "dialekt_Bayerisch_ElevenLabs_Bairischer_Bua",
          library.suggest_name("Bayerisch", "elevenlabs", "Bairischer Bua"))
    check("Windows-Stimme ergibt einen anderen Namen",
          library.suggest_name("Bayerisch", "windows", "Microsoft Stefan")
          != library.suggest_name("Bayerisch", "elevenlabs", "Bairischer Bua"))
    check("Klammerzusätze fliegen raus",
          "de" not in library.suggest_name("Wienerisch", "elevenlabs",
                                           "Wiener (de · selbst erzeugt)"),
          library.suggest_name("Wienerisch", "elevenlabs",
                               "Wiener (de · selbst erzeugt)"))
    check("Umlaute werden ersetzt",
          library.safe_name("Schwäbisch Süß") == "Schwaebisch_Suess",
          library.safe_name("Schwäbisch Süß"))
    check("verbotene Zeichen verschwinden",
          "/" not in library.safe_name('a/b:c*d?"e'),
          library.safe_name('a/b:c*d?"e'))
    check("leerer Name ergibt trotzdem etwas",
          library.safe_name("///") == "sprachpaket", library.safe_name("///"))

    lib_dir = work / "paketsammlung"
    lib_dir.mkdir(parents=True, exist_ok=True)
    erste = library.unique_path(lib_dir, "dialekt_Bayerisch_ElevenLabs")
    erste.write_bytes(b"x" * 100)
    zweite = library.unique_path(lib_dir, "dialekt_Bayerisch_ElevenLabs")
    check("ein zweiter Bau bekommt einen eigenen Namen",
          zweite != erste and zweite.name.endswith("_2.tar.gz"), zweite.name)
    check("das erste Paket ist unangetastet",
          erste.exists() and erste.stat().st_size == 100)

    library.write_info(erste, dialect="Bayerisch", engine="ElevenLabs",
                       voice="Bairischer Bua", lang_id="BAYERN",
                       replaced=598, total=593)
    info = library.read_info(erste)
    check("Beschreibung wird wiedergefunden",
          info.dialect == "Bayerisch" and info.voice == "Bairischer Bua",
          f"{info.dialect}/{info.voice}")
    check("die Beschriftung nennt Dialekt und Stimme",
          "Bayerisch" in info.label and "Bairischer Bua" in info.label,
          info.label)
    check("ohne Beschreibung gibt es trotzdem eine Beschriftung",
          library.read_info(zweite).label != "")

    zweite.write_bytes(b"y" * 50)
    liste = library.list_packs(lib_dir)
    check("beide Pakete stehen in der Sammlung", len(liste) == 2,
          str([i.path.name for i in liste]))

    # ---------------------------------------------------------------
    section("21. Eigene Sprachpakete")
    from dreamevoice import custom  # noqa: E402

    eigen_dir = work / "eigene"
    eigen_dir.mkdir(parents=True, exist_ok=True)
    _alt_data = custom.data_dir
    custom.data_dir = lambda: eigen_dir
    try:
        check("Schlüssel ohne Sonderzeichen",
              custom.make_key("Bruce Willis!") == "bruce_willis",
              custom.make_key("Bruce Willis!"))
        check("Umlaute im Schlüssel werden ersetzt",
              custom.make_key("Käpt'n Blaubär") == "kaeptn_blaubaer",
              custom.make_key("Käpt'n Blaubär"))
        check("Kennung ist kurz und in Großbuchstaben",
              custom.make_lang_id("Bruce Willis") == "BRUCEWIL",
              custom.make_lang_id("Bruce Willis"))
        check("Kennung kollidiert nicht mit einer offiziellen Sprache",
              custom.make_lang_id("Deutsch") not in ("DE",),
              custom.make_lang_id("Deutsch"))
        check("belegte Kennungen werden gemieden",
              custom.make_lang_id("Pirat", ["PIRAT"]) != "PIRAT",
              custom.make_lang_id("Pirat", ["PIRAT"]))

        bay = dialect.get("bayerisch")
        neu = custom.create("Bruce Willis", dict(bay.texts))
        check("die Kopie hat alle Ansagen", neu.count == bay.count,
              f"{neu.count} statt {bay.count}")
        check("und ist ein ganz normales Paket",
              isinstance(neu, dialect.DialectPack))

        custom.save(neu)
        check("gespeichert wird als Datei", custom.exists(neu.key))
        wieder = custom.load(custom.path_for(neu.key))
        check("und kommt unverändert zurück",
              wieder is not None and wieder.texts == neu.texts
              and wieder.name == "Bruce Willis")
        check("die Kennung überlebt", wieder.lang_id == neu.lang_id)

        zweit = custom.create("Bruce Willis", {})
        check("gleicher Name ergibt einen eigenen Schlüssel",
              zweit.key != neu.key, f"{zweit.key} / {neu.key}")

        check("die Sammlung listet das Paket",
              [p.name for p in custom.list_packs()] == ["Bruce Willis"],
              str([p.name for p in custom.list_packs()]))

        custom.rename(wieder, "Bruce W.")
        custom.save(wieder)
        check("Umbenennen behält den Schlüssel",
              custom.load(custom.path_for(neu.key)).name == "Bruce W.")

        # Der Schlüssel muss bleiben, sonst gehen die gesprochenen
        # Aufnahmen beim Umbenennen verloren.
        check("und damit auch den Ablageort der Aufnahmen",
              custom.load(custom.path_for(neu.key)).key == neu.key)

        check("Löschen entfernt die Datei",
              custom.delete(neu.key) and not custom.exists(neu.key))
        # custom.load meldet die fehlende Datei per Logging nach stderr -
        # hier ist genau das der Prüfpunkt, also darf die Meldung nicht in
        # der Ausgabe landen. Sonst hält das Bauskript sie für einen Fehler.
        with leise("dreamevoice.custom"):
            check("kaputte Dateien werden übersprungen",
                  custom.load(eigen_dir / "gibtsnicht.json") is None)
    finally:
        custom.data_dir = _alt_data

    # ---------------------------------------------------------------
    section("22. Abbrechen während des Sprechens")
    from dreamevoice.ui.state import Task  # noqa: E402

    auftrag = Task()
    check("ein frischer Auftrag ist nicht abgebrochen", not auftrag.cancelled)
    auftrag.cancel()
    check("nach cancel() ist er es", auftrag.cancelled)

    # Der Kern: synthesize muss vor jeder Ansage nachsehen und das
    # bereits Gesprochene zurückgeben - sonst wäre das Kontingent weg,
    # ohne dass etwas ankommt.
    from dreamevoice import elevenlabs as _el  # noqa: E402
    quelle = inspect.getsource(_el.synthesize)
    check("synthesize prüft in der Schleife auf Abbruch",
          "if cancelled():" in quelle)
    check("und bricht ab, statt eine Ausnahme zu werfen",
          "break" in quelle.split("if cancelled():")[1][:80],
          quelle.split("if cancelled():")[1][:60].strip())

    # Reihenfolge in dialect.generate: erst den Vermerk schreiben, dann
    # den Abbruch prüfen. Andersherum wäre bezahltes Kontingent verloren.
    quelle_gen = inspect.getsource(dialect.generate)
    pos_manifest = quelle_gen.find("write_manifest")
    pos_abbruch = quelle_gen.find("Vom Benutzer abgebrochen")
    check("Gesprochenes wird vermerkt, bevor der Abbruch greift",
          0 < pos_manifest < pos_abbruch,
          f"Vermerk bei {pos_manifest}, Abbruch bei {pos_abbruch}")

    unterschrift = inspect.signature(_el.synthesize).parameters
    check("synthesize nimmt 'cancelled' entgegen", "cancelled" in unterschrift)

    # ---------------------------------------------------------------
    section("23. Aufnahmen-ZIP ohne Entpacken einlesen")

    # Die Anleitung sagt: ZIP herunterladen, direkt auswählen, fertig. Die
    # Archive von der Projektseite haben oben einen Ordner drin und liegen
    # neben zwei Textdateien - beides muss der Import wegstecken.
    import shutil as _shutil  # noqa: E402
    import zipfile as _zip  # noqa: E402

    zip_dir = arbeitsordner()
    archiv = zip_dir / "Test-Aufnahmen.zip"
    ton = minimal_vorbis_ogg()
    with _zip.ZipFile(archiv, "w") as zf:
        for nummer in (1, 7, 42):
            zf.writestr(f"Test-Aufnahmen/{nummer}.ogg", ton)
        zf.writestr("Test-Aufnahmen/LIESMICH.txt", "Hinweise")
        zf.writestr("Test-Aufnahmen/LIZENZ-AUDIO.txt", "Bedingungen")

    ergebnis = importer.import_archive(archiv, zip_dir / "arbeit")
    check("das ZIP wird ohne Entpacken gelesen", len(ergebnis.assigned) == 3,
          f"{len(ergebnis.assigned)} statt 3")
    check("der Ordner im Archiv stört nicht",
          sorted(ergebnis.assigned) == [1, 7, 42], str(sorted(ergebnis.assigned)))
    check("LIESMICH und LIZENZ landen nicht als Ansage",
          all(p.suffix == ".ogg" for p in ergebnis.assigned.values()))

    # Und derselbe Inhalt als entpackter Ordner - auch eine Ebene tiefer,
    # weil Windows beim Entpacken gern einen zweiten Ordner erzeugt.
    entpackt = zip_dir / "entpackt"
    with _zip.ZipFile(archiv) as zf:
        zf.extractall(entpackt)
    check("derselbe Inhalt als Ordner ergibt dasselbe",
          sorted(importer.scan_folder(entpackt).assigned) == [1, 7, 42])

    # Die Wahlmöglichkeiten dürfen nicht auseinanderlaufen: der Text im
    # Auswahldialog entscheidet über den Zweig im Code.
    from dreamevoice.ui import tab_store as _ts  # noqa: E402
    quelle_imp = inspect.getsource(_ts.StoreTab._on_import_ready)
    check("der Auswahldialog nennt genau die beiden Konstanten",
          "WAHL_ARCHIV" in quelle_imp and "WAHL_ORDNER" in quelle_imp)
    check("und verzweigt darüber, nicht über losen Text",
          "art == WAHL_ARCHIV" in quelle_imp)
    check("'ZIP' steht in der ersten Wahl", "ZIP" in _ts.WAHL_ARCHIV)

    # Tab 3 nimmt nur gebaute Pakete. Ein Aufnahmen-ZIP dort muss zu einem
    # Hinweis führen, nicht zu einer Formatmeldung.
    from dreamevoice.ui import tab_install as _ti  # noqa: E402
    quelle_pick = inspect.getsource(_ti.InstallTab._on_pick_pack)
    check("die ausführliche Seite fängt ein ZIP ab und verweist weiter",
          '".zip"' in quelle_pick
          and "Fertige Stimmen" in quelle_pick
          and "Eigene Stimmen" in quelle_pick)

    _shutil.rmtree(zip_dir, ignore_errors=True)

    # ---------------------------------------------------------------
    section("24. Ersetzen nur auf ausdrückliche Wahl")

    from dreamevoice import library as _lib  # noqa: E402

    lib_dir = arbeitsordner()
    check("ohne vorhandene Datei meldet existing_pack nichts",
          _lib.existing_pack(lib_dir, "Hessisch") is None)

    (lib_dir / "Hessisch.tar.gz").write_bytes(b"alt")
    gefunden = _lib.existing_pack(lib_dir, "Hessisch")
    check("ein vorhandenes Paket wird gemeldet", gefunden is not None)
    check("und zwar genau dieses", gefunden and gefunden.name == "Hessisch.tar.gz")

    # Das Danebenlegen darf die vorhandene Datei nicht anfassen.
    daneben = _lib.unique_path(lib_dir, "Hessisch")
    check("der Ausweichpfad ist ein anderer", daneben != gefunden,
          f"{daneben.name} vs {gefunden.name if gefunden else '-'}")
    check("und das Vorhandene bleibt unberührt",
          (lib_dir / "Hessisch.tar.gz").read_bytes() == b"alt")

    # Der Kern: die Vorgabe im Auswahldialog muss das Behalten sein.
    check("'Daneben speichern' steht an erster Stelle",
          _ts.WAHL_DANEBEN.startswith("Daneben"))
    quelle_imp2 = inspect.getsource(_ts.StoreTab._on_import_ready)
    pos_frage = quelle_imp2.find("WAHL_DANEBEN, WAHL_ERSETZEN")
    pos_vorgabe = quelle_imp2.find("WAHL_DANEBEN)")
    check("und ist die Vorgabe des Dialogs", 0 < pos_frage < pos_vorgabe,
          f"Liste bei {pos_frage}, Vorgabe bei {pos_vorgabe}")
    check("ersetzt wird nur bei ausdrücklicher Wahl",
          "wahl == WAHL_ERSETZEN" in quelle_imp2)

    # build_pack baut in eine .part-Datei und ersetzt erst zum Schluss -
    # sonst wäre ein Fehlschlag mitten im Bauen der Verlust des alten.
    quelle_build = inspect.getsource(packer.build_pack)
    pos_part = quelle_build.find('with_suffix(".part")')
    pos_ersetzt = quelle_build.find("tmp_path.replace(out_path)")
    check("gebaut wird in eine .part-Datei", pos_part > 0)
    check("die erst ganz am Ende das Ziel ersetzt",
          0 < pos_part < pos_ersetzt,
          f".part bei {pos_part}, Ersetzen bei {pos_ersetzt}")

    _shutil.rmtree(lib_dir, ignore_errors=True)

    # ---------------------------------------------------------------
    section("25. Zwei Anhänge in einer EXE")

    # ffmpeg und die mitgelieferten Dialekte hängen beide hinten an der
    # EXE. Der zweite darf den ersten nicht unauffindbar machen - genau
    # das wäre passiert, solange nur der letzte Abspann gelesen wurde.
    import lzma as _lzma          # noqa: E402
    import tarfile as _tar        # noqa: E402
    from dreamevoice import embedded as _emb  # noqa: E402

    anh_dir = arbeitsordner()
    exe_test = anh_dir / "Test.exe"

    ffmpeg_roh = b"MZ" + b"\xc3" * 1_500_000
    ffmpeg_pak = _lzma.compress(ffmpeg_roh, preset=1)

    zips = {"Bayerisch-Aufnahmen.zip": b"PK\x03\x04" + b"b" * 1_200_000}
    puffer = io.BytesIO()
    with _tar.open(fileobj=puffer, mode="w") as tf_:
        for name_, roh_ in zips.items():
            info_ = _tar.TarInfo(name=name_)
            info_.size = len(roh_)
            tf_.addfile(info_, io.BytesIO(roh_))
    dial_tar = puffer.getvalue()

    with exe_test.open("wb") as fh_:
        fh_.write(b"PROGRAMM" * 1000)
        fh_.write(ffmpeg_pak)
        fh_.write(len(ffmpeg_pak).to_bytes(8, "little"))
        fh_.write(_emb.MAGIC)
        fh_.write(dial_tar)
        fh_.write(len(dial_tar).to_bytes(8, "little"))
        fh_.write(_emb.MAGIC_DIALEKTE)

    _echt_frozen, _echt_exe, _echt_daten = (_emb.is_frozen, sys.executable,
                                            _emb.data_dir)
    _emb.is_frozen = lambda: True
    sys.executable = str(exe_test)
    _emb.data_dir = lambda: anh_dir / "Daten"
    try:
        check("beide Anhänge werden gefunden", len(_emb._bloecke()) == 2,
              str(len(_emb._bloecke())))
        check("ffmpeg bleibt auffindbar, obwohl etwas dahinter liegt",
              _emb.has_ffmpeg())
        check("und zwar in voller Länge",
              _emb.payload_size() == len(ffmpeg_pak))
        entpackt_ = _emb.extract_ffmpeg()
        check("ffmpeg kommt bitgenau wieder heraus",
              entpackt_ is not None and entpackt_.read_bytes() == ffmpeg_roh)

        check("die Dialekte werden gefunden", _emb.has_dialekte())
        check("die Liste nennt das Archiv",
              _emb.list_dialekte() == sorted(zips), str(_emb.list_dialekte()))
        dpfad = _emb.extract_dialekt("Bayerisch-Aufnahmen.zip")
        check("und es kommt bitgenau wieder heraus",
              dpfad is not None
              and dpfad.read_bytes() == zips["Bayerisch-Aufnahmen.zip"])
        with leise("dreamevoice.embedded"):
            check("ein unbekannter Name liefert nichts",
                  _emb.extract_dialekt("Gibtsnicht.zip") is None)

        leer_ = anh_dir / "Leer.exe"
        leer_.write_bytes(b"PROGRAMM" * 1000)
        sys.executable = str(leer_)
        check("ohne Anhang meldet sich weder ffmpeg ...", not _emb.has_ffmpeg())
        check("... noch ein Dialekt", not _emb.has_dialekte())
    finally:
        _emb.is_frozen, sys.executable, _emb.data_dir = (_echt_frozen,
                                                         _echt_exe,
                                                         _echt_daten)
    _shutil.rmtree(anh_dir, ignore_errors=True)

    # ---------------------------------------------------------------
    section("26. Vorhören aus jeder Paketart")

    from dreamevoice import vorhoeren as _vh  # noqa: E402

    vh_dir = arbeitsordner()
    ton_ = minimal_vorbis_ogg()
    drin = [7, 14, 40, 55, 99]

    # Dieselben Ansagen als Ordner, als ZIP und als gebautes tar.gz - alle
    # drei Wege müssen zum selben Ergebnis führen.
    als_ordner = vh_dir / "ordner"
    als_ordner.mkdir()
    for n_ in drin:
        (als_ordner / f"{n_}.ogg").write_bytes(ton_)
    (als_ordner / "LIESMICH.txt").write_text("kein Ton", encoding="utf-8")

    als_zip = vh_dir / "aufnahmen.zip"
    with _zip.ZipFile(als_zip, "w") as zf_:
        for n_ in drin:
            zf_.writestr(f"Irgendein-Ordner/{n_}.ogg", ton_)
        zf_.writestr("Irgendein-Ordner/LIESMICH.txt", "kein Ton")

    als_tar = vh_dir / "paket.tar.gz"
    make_fake_base(als_tar, drin, ton_)

    for name_, quelle_ in (("Ordner", als_ordner), ("ZIP", als_zip),
                           ("tar.gz", als_tar)):
        ids_ = _vh.verfuegbare_ids(quelle_)
        check(f"{name_}: alle Ansagen gefunden", sorted(ids_) == drin, str(ids_))
        gewaehlt = _vh.auswahl(quelle_)
        check(f"{name_}: die Beispiele werden bevorzugt",
              gewaehlt == _vh.BEISPIELE, str(gewaehlt))
        entnommen = _vh.entnehmen(quelle_, vh_dir / f"raus_{name_}")
        check(f"{name_}: entnommen wird genau die Auswahl",
              sorted(entnommen) == _vh.BEISPIELE, str(sorted(entnommen)))
        check(f"{name_}: der Beipackzettel ist keine Ansage",
              all(p.suffix.lower() != ".txt" for p in entnommen.values()))

    # Ein Paket ohne die Wunschnummern muss trotzdem etwas anbieten.
    sonder = vh_dir / "sonder"
    sonder.mkdir()
    for n_ in (300, 301, 302, 303, 304, 305):
        (sonder / f"{n_}.ogg").write_bytes(ton_)
    ersatz = _vh.auswahl(sonder)
    check("ohne die Wunschnummern werden andere genommen",
          len(ersatz) == _vh.HOECHSTENS and 300 in ersatz, str(ersatz))

    with leise("dreamevoice.vorhoeren"):
        check("ein leerer Ordner liefert nichts",
              _vh.auswahl(vh_dir / "gibtsnicht") == [])
        check("und probe_vorbereiten dann auch nichts",
              _vh.probe_vorbereiten(vh_dir / "gibtsnicht", None) == {})

    # Ohne ffmpeg lässt sich nichts in WAV wandeln - das muss sauber
    # gemeldet werden statt zu krachen.
    check("ohne ffmpeg gibt es keine Probe",
          _vh.probe_vorbereiten(als_zip, None) == {})
    check("eine WAV-Datei braucht kein ffmpeg",
          _vh.nach_wav(vh_dir / "x.wav", vh_dir / "y.wav", None)
          == vh_dir / "x.wav")

    _shutil.rmtree(vh_dir, ignore_errors=True)

    # ---------------------------------------------------------------
    section("26b. Gemerkte Lautheitswerte")

    # Der Schlüssel muss am Inhalt hängen, nicht am Pfad oder der
    # Änderungszeit: Beim Bauen wird das Aufnahmen-Archiv jedes Mal neu
    # entpackt, wodurch jede Datei eine frische Zeit bekommt. Hängt der
    # Schlüssel daran, greift der Puffer nie - genau das war der Fall.
    laut_dir = arbeitsordner()
    a = laut_dir / "7.ogg"
    a.write_bytes(minimal_vorbis_ogg())
    schluessel_a = audio._lautheit_schluessel(a)
    check("eine Datei bekommt einen Schlüssel", bool(schluessel_a))

    # Dieselbe Datei noch einmal entpackt: anderer Name, andere Zeit,
    # gleicher Inhalt - der Schlüssel muss derselbe sein.
    b = laut_dir / "kopie" / "7.ogg"
    b.parent.mkdir()
    b.write_bytes(a.read_bytes())
    check("gleicher Inhalt ergibt denselben Schlüssel",
          audio._lautheit_schluessel(b) == schluessel_a)

    c = laut_dir / "8.ogg"
    c.write_bytes(minimal_vorbis_ogg() + bytes([0]))
    check("anderer Inhalt ergibt einen anderen Schlüssel",
          audio._lautheit_schluessel(c) != schluessel_a)
    check("eine fehlende Datei hat keinen Schlüssel",
          audio._lautheit_schluessel(laut_dir / "gibtsnicht.ogg") is None)

    quelle_mess = inspect.getsource(audio.measure_loudness)
    check("measure_loudness fragt den Puffer",
          "_LAUTHEIT.get(" in quelle_mess)
    check("und lässt sich abschalten", "use_cache" in quelle_mess)
    check("gesichert wird gebündelt, nicht nach jeder Messung",
          "_LAUTHEIT_BUENDEL" in inspect.getsource(audio._lautheit_sichern))

    _shutil.rmtree(laut_dir, ignore_errors=True)

    # ---------------------------------------------------------------
    section("26c. Die Hilfe behauptet nichts Veraltetes")

    # Der Hilfetext stand nach dem Einbetten noch monatelang auf "einfach
    # ffmpeg.exe neben die App legen" - was in der EXE schlicht falsch
    # ist. Solche Sätze veralten still, deshalb hier festgenagelt.
    from dreamevoice.ui import app as _app     # noqa: E402

    hilfe = _app.HELP_TEXT
    check("die Hilfe sagt, dass ffmpeg mitgeliefert wird",
          "in der Programmdatei" in hilfe or "in der App enthalten" in hilfe)
    check("und fordert nicht mehr zum Danebenlegen auf",
          "ffmpeg.exe neben die App legen" not in hilfe)
    check("der Sonderfall Quellcode wird trotzdem erwähnt",
          "Quellcode" in hilfe)

    # Und die Oberfläche muss den eingebetteten Weg auch wirklich gehen,
    # bevor sie zum Herunterladen rät.
    from dreamevoice.ui.tab_builder import BuilderTab   # noqa: E402

    quelle_check = inspect.getsource(BuilderTab._check_ffmpeg)
    pos_eingebettet = quelle_check.find("embedded.has_ffmpeg()")
    pos_download = quelle_check.find("btn_ffmpeg.pack(side=")
    check("erst das eingebettete ffmpeg, dann der Download",
          0 < pos_eingebettet < pos_download,
          f"eingebettet bei {pos_eingebettet}, Download bei {pos_download}")

    # ---------------------------------------------------------------
    section("27. Das Hauptfenster baut sich auf")

    # Falsche Stilnamen, fehlende Widgets, Tippfehler in pack() - all das
    # findet kein Namenscheck, sondern erst der Aufbau. Das Fenster wird
    # deshalb wirklich erzeugt, aber nie sichtbar gemacht.
    try:
        import tkinter as _tk       # noqa: E402
        _wurzel = _tk.Tk()
        _wurzel.destroy()
        _tk_da = True
    except Exception:               # pragma: no cover - Rechner ohne Anzeige
        _tk_da = False
        uebersprungen("Das Hauptfenster baut sich auf",
                      "Tkinter oder Anzeige fehlt auf diesem Rechner")

    if _tk_da:
        from dreamevoice.ui.app import MainWindow      # noqa: E402
        from dreamevoice.ui.page_start import ZUSTAND_ANMELDEN  # noqa: E402

        _fenster = None
        try:
            _fenster = MainWindow()
            _fenster.withdraw()
            _fenster.update_idletasks()
            check("das Hauptfenster entsteht", _fenster is not None)

            _shell = _fenster.shell
            check("alle Einträge der Seitenleiste sind da",
                  _shell.keys() == ["start", "stimme", "eigene",
                                    "ansagen", "aufspielen", "verbindung"],
                  str(_shell.keys()))
            check("Start ist die erste Seite", _shell.current == "start")
            check("ohne Anmeldung steht das Anmeldeformular",
                  _fenster.page_start._zustand == ZUSTAND_ANMELDEN,
                  _fenster.page_start._zustand)
            check("was ohne Anmeldung sinnlos ist, ist gesperrt",
                  all(not _shell._eintraege[k].enabled
                      for k in ("stimme", "eigene", "ansagen", "aufspielen")))
            check("Verbindung bleibt erreichbar",
                  _shell._eintraege["verbindung"].enabled)
            check("und trägt einen Warnpunkt",
                  _shell._eintraege["verbindung"].dot == "warn")

            for _key in _shell.keys():
                _shell._eintraege[_key].enabled = True
                _shell.show(_key)
                _fenster.update_idletasks()
                check(f"Seite '{_key}' lässt sich anzeigen",
                      _shell.current == _key)

            _platziert = [k for k in _shell.keys()
                          if _shell._eintraege[k].seite.grid_info()]
            check("es ist immer genau eine Seite platziert",
                  _platziert == [_shell.current], str(_platziert))

            check("die vier bisherigen Ansichten sind eingezogen",
                  all(getattr(_fenster, n, None) is not None for n in
                      ("tab_connect", "tab_builder", "tab_install", "tab_store")))

            # Die neue Seite muss die mitgelieferten Dialekte auch finden -
            # eine leere Auswahl wäre der peinlichste aller Fehler.
            _stimmen = _fenster.page_voice._auswahl
            from dreamevoice import dialektpakete as _dpk  # noqa: E402
            _erwartet = len(_dpk.verfuegbar())
            if _erwartet == 0:
                uebersprungen("die Stimmenseite findet die Dialekte",
                              "hier liegen keine Aufnahmen (weder in der "
                              "EXE noch im Projektordner)")
            else:
                check("die Stimmenseite findet die Dialekte",
                      len(_stimmen) >= _erwartet,
                      f"{len(_stimmen)} von {_erwartet} gefunden")
            check("und jede lässt sich auflösen",
                  all(_fenster.page_voice._quelle_holen(a) is not None
                      for a in _stimmen))
        finally:
            if _fenster is not None:
                try:
                    _fenster.destroy()
                except Exception:
                    pass

    # ---------------------------------------------------------------
    section("28. Geheimnisse landen nie in der config.json")

    # Zustand der ECHTEN Einträge festhalten. Am Ende wird verglichen,
    # nicht auf Vorhandensein geprüft: Wer frisch installiert hat - oder
    # gerade "Persönliche Daten entfernen" benutzt hat - hat zu Recht
    # keine, und dafür darf der Selbsttest nicht rot werden. Was er
    # verhindern muss, ist die VERAENDERUNG.
    def _fingerabdruck(ziel):
        """Erkennungsmerkmal eines Tresoreintrags, ohne ihn preiszugeben.

        Auf Vorhandensein zu prüfen genügt nicht: Würde der
        Selbsttest den echten Schlüssel UEBERSCHREIBEN statt ihn zu
        löschen, bliebe exists() wahr und die Prüfung grün - der
        bezahlte Schlüssel wäre trotzdem weg. Verglichen wird
        deshalb ein Hashwert, nie der Wert selbst.
        """
        try:
            wert = credentials.load(ziel)
        except Exception:                        # noqa: BLE001
            return "(nicht lesbar)"
        if not wert:
            return "(keiner)"
        return hashlib.sha256(wert.encode("utf-8")).hexdigest()[:12]

    _echt_vorher = (_fingerabdruck(credentials.TARGET_DREAME),
                    _fingerabdruck(credentials.TARGET_ELEVENLABS))

    # Passwort und ElevenLabs-Schlüssel gehören in den Windows-Tresor
    # und sonst nirgendwohin. Früher hat ein Fehler in genau diesem
    # Selbsttest den echten Schlüssel gelöscht - Grund genug, den
    # Umgang damit besonders festzunageln.
    from dreamevoice import config as _cfgmod       # noqa: E402

    geheim_dir = arbeitsordner()
    _alt_datei = _cfgmod.config_file
    _cfgmod.config_file = lambda: geheim_dir / "config.json"

    # Und der Tresor bekommt Testnamen, damit die echten Einträge
    # unangetastet bleiben.
    _alt_ziele = (credentials.TARGET_DREAME, credentials.TARGET_ELEVENLABS)
    credentials.TARGET_DREAME = "DreameSprachpaket:Selbsttest-Dreame28"
    credentials.TARGET_ELEVENLABS = "DreameSprachpaket:Selbsttest-Eleven28"
    try:
        PROBE_PW = "Geheim!Test#28_pw"
        PROBE_KEY = "sk_selbsttest_28_" + "x" * 30

        c = _cfgmod.Config.load()
        c["email"] = "test@example.invalid"
        c.set_password(PROBE_PW, remember=True)
        c.set_elevenlabs_key(PROBE_KEY)
        c.save()

        roh = (geheim_dir / "config.json").read_text(encoding="utf-8")
        check("das Passwort steht nicht in der Datei", PROBE_PW not in roh)
        check("der Schlüssel steht nicht in der Datei", PROBE_KEY not in roh)
        import base64 as _b64
        check("auch nicht base64-kodiert",
              _b64.b64encode(PROBE_PW.encode()).decode() not in roh
              and _b64.b64encode(PROBE_KEY.encode()).decode() not in roh)

        # Steht der Tresor bereit, müssen die Ausweichfelder leer sein.
        if credentials.available():
            check("password_enc bleibt leer, wenn der Tresor da ist",
                  not c["password_enc"], repr(c["password_enc"])[:40])
            check("elevenlabs_key_enc bleibt leer",
                  not c["elevenlabs_key_enc"])
            check("das Passwort kommt aus dem Tresor zurück",
                  c.password == PROBE_PW)
            check("der Schlüssel auch", c.elevenlabs_key == PROBE_KEY)
            check("und die App sagt auch, wo es liegt",
                  "Anmelde" in c.password_location, c.password_location)

        # Vergessen muss wirklich vergessen.
        c.forget_elevenlabs_key()
        c.set_password("", remember=False)
        c.save()
        roh2 = (geheim_dir / "config.json").read_text(encoding="utf-8")
        check("nach dem Vergessen ist nichts mehr da",
              PROBE_PW not in roh2 and PROBE_KEY not in roh2)
        check("und der Tresoreintrag ist weg",
              not credentials.exists(credentials.TARGET_ELEVENLABS))
    finally:
        credentials.delete(credentials.TARGET_DREAME)
        credentials.delete(credentials.TARGET_ELEVENLABS)
        credentials.TARGET_DREAME, credentials.TARGET_ELEVENLABS = _alt_ziele
        _cfgmod.config_file = _alt_datei
        _shutil.rmtree(geheim_dir, ignore_errors=True)

    # ---------------------------------------------------------------
    section("28b. Weitergeben, ohne Spuren zu hinterlassen")

    # Passwort und Schlüssel wandern ohnehin nicht mit, die liegen im
    # Tresor. Die config.json enthält aber E-Mail, Robotername, dessen
    # MAC und die IP des PCs - beim Weitergeben samt Datenordner ginge
    # das alles mit.
    weiter_dir = arbeitsordner()
    _alt_cfgdatei = _cfgmod.config_file
    _alt_logdatei = _cfgmod.log_file
    _cfgmod.config_file = lambda: weiter_dir / "config.json"
    _cfgmod.log_file = lambda: weiter_dir / "verlauf.log"
    _alt_ziele2 = (credentials.TARGET_DREAME, credentials.TARGET_ELEVENLABS)
    credentials.TARGET_DREAME = "DreameSprachpaket:Selbsttest-Dreame28b"
    credentials.TARGET_ELEVENLABS = "DreameSprachpaket:Selbsttest-Eleven28b"
    try:
        (weiter_dir / "verlauf.log").write_text(
            "2026-01-01 Auftrag http://192.168.10.196:5555/x" + chr(10),
            encoding="utf-8")

        w = _cfgmod.Config.load()
        w["email"] = "wer@example.invalid"
        w["device_id"] = "955461008"
        w["device_name"] = "X50 Ultra Complete"
        w["device_mac"] = "70:C9:32:A7:23:6C"
        w["host_ip"] = "192.168.10.196"
        w["elevenlabs_voice_id"] = "L8v90KZAhUv5vBKb5enK"
        w["elevenlabs_voice_name"] = "Irgendeine Stimme"
        w["last_pack_name"] = "Bayerisch"          # darf bleiben
        w.set_password("Geheim28b!", remember=True)
        w.set_elevenlabs_key("sk_28b_" + "y" * 40)
        w.save()

        geleert = w.forget_personal()
        w.save()
        inhalt = (weiter_dir / "config.json").read_text(encoding="utf-8")

        for feld, spur in (("email", "wer@example.invalid"),
                           ("device_id", "955461008"),
                           ("device_name", "X50 Ultra Complete"),
                           ("device_mac", "70:C9:32:A7:23:6C"),
                           ("host_ip", "192.168.10.196"),
                           ("elevenlabs_voice_id", "L8v90KZAhUv5vBKb5enK")):
            check(f"{feld} ist weg", spur not in inhalt)

        check("das Protokoll ist geleert",
              not (weiter_dir / "verlauf.log").read_text(encoding="utf-8").strip())
        check("die Tresoreinträge sind gelöscht",
              not credentials.exists(credentials.TARGET_DREAME)
              and not credentials.exists(credentials.TARGET_ELEVENLABS))
        check("es wird gemeldet, was entfernt wurde", len(geleert) >= 8,
              f"{len(geleert)} Angaben")

        # Was zur Arbeit gehört, muss bleiben.
        check("der zuletzt benutzte Paketname bleibt",
              w["last_pack_name"] == "Bayerisch")
        check("die Kennung bleibt", bool(w["custom_lang_id"]))
    finally:
        credentials.delete(credentials.TARGET_DREAME)
        credentials.delete(credentials.TARGET_ELEVENLABS)
        credentials.TARGET_DREAME, credentials.TARGET_ELEVENLABS = _alt_ziele2
        _cfgmod.config_file = _alt_cfgdatei
        _cfgmod.log_file = _alt_logdatei
        _shutil.rmtree(weiter_dir, ignore_errors=True)

    # Die echten Einträge müssen den Test unverändert überstanden
    # haben - genau hier ist früher der bezahlte Schlüssel
    # verlorengegangen.
    _echt_nachher = (_fingerabdruck(credentials.TARGET_DREAME),
                     _fingerabdruck(credentials.TARGET_ELEVENLABS))
    check("der echte Dreamehome-Eintrag ist unverändert",
          _echt_nachher[0] == _echt_vorher[0],
          f"vorher {_echt_vorher[0]}, nachher {_echt_nachher[0]}")
    check("der echte ElevenLabs-Eintrag ist unverändert",
          _echt_nachher[1] == _echt_vorher[1],
          f"vorher {_echt_vorher[1]}, nachher {_echt_nachher[1]}")
    if all(v == "(keiner)" for v in _echt_vorher):
        print("         (zurzeit ist keiner hinterlegt - dann ist genau das"
              " das richtige Ergebnis)")

    # ---------------------------------------------------------------
    section("29. Lautstärke nach dem Sprachwechsel")

    # Der Roboter spricht nach einem Paketwechsel leiser, bis er neu
    # startet - obwohl die gespeicherte Lautstärke unverändert bleibt.
    # Er wendet seine eigene Einstellung also nicht wieder an. Ein
    # Schreibzugriff auf 7/1 stößt das an und erspart den Neustart.
    from dreamevoice import installer as _inst
    from dreamevoice.cloud import DreameCloud as _DC

    class _Roboter:
        """Merkt sich jeden Schreibzugriff, damit man die Folge prüfen kann."""

        def __init__(self, stand=100, nimmt_an=True):
            self.stand, self.nimmt_an, self.spur = stand, nimmt_an, []

        def voice_volume(self, _d):
            return self.stand

        def set_voice_volume(self, _d, wert):
            self.spur.append(wert)
            if self.nimmt_an:
                self.stand = wert
            return self.stand == wert

    r = _Roboter(stand=100)
    check("die gemerkte Lautstärke wird zurückgeschrieben",
          _inst.refresh_volume(r, None, 100) and r.spur == [100],
          f"geschrieben: {r.spur}")

    # Falls der Praxistest zeigt, dass derselbe Wert nicht genügt,
    # wird über einen anderen Wert gegangen - danach muss aber wieder
    # genau der Ausgangswert stehen.
    _alt_umweg = _inst.LAUTSTAERKE_UMWEG
    try:
        _inst.LAUTSTAERKE_UMWEG = True
        r = _Roboter(stand=100)
        _inst.refresh_volume(r, None, 100)
        check("der Umweg erzeugt einen echten Wertwechsel",
              len(r.spur) == 2 and r.spur[0] != 100, f"{r.spur}")
        check("und landet trotzdem auf dem Ausgangswert", r.stand == 100)
        r = _Roboter(stand=99)
        _inst.refresh_volume(r, None, 99)
        check("auch wenn der Ausgangswert der Umwegwert selbst ist",
              r.spur[0] != 99 and r.stand == 99, f"{r.spur}")
    finally:
        _inst.LAUTSTAERKE_UMWEG = _alt_umweg

    # Ein Fehlschlag darf die Installation nicht kippen - das Paket ist
    # zu diesem Zeitpunkt schon drauf.
    class _Offline:
        def set_voice_volume(self, _d, _w):
            raise RuntimeError("offline")

    check("ein unerreichbarer Roboter wirft keine Ausnahme",
          _inst.refresh_volume(_Offline(), None, 100) is False)
    check("ohne gelesenen Wert wird nichts geschrieben",
          _inst.refresh_volume(_Roboter(), None, None) is False)

    class _Weigert:
        def voice_volume(self, _d):
            return 50

        def set_voice_volume(self, _d, _w):
            return False

    # Die Neustart-Empfehlung steht bewusst NICHT hier, sondern einmal
    # zentral in NEUSTART_HINWEIS - sie gilt bei Erfolg genauso.
    _hinweise = []
    check("wird der Wert nicht übernommen, wird das gemeldet",
          _inst.refresh_volume(_Weigert(), None, 100, _hinweise.append) is False
          and any("nicht bestätigen" in z for z in _hinweise), f"{_hinweise}")

    # Unplausible Werte gar nicht erst zurückschreiben: Bei einem Gerät,
    # das an 7/1 etwas anderes führt, wäre das ein Schreibzugriff ins
    # Blaue.
    _leer = object.__new__(_DC)
    for _roh, _erwartet in ((100, 100), (0, 0), (55.0, 55), (None, None),
                            ("laut", None), (True, None), (101, None),
                            (-1, None)):
        _leer.get_property = lambda _d, _s, _p, _v=_roh: _v
        check(f"Lautstärke {_roh!r} wird als {_erwartet!r} gelesen",
              _leer.voice_volume(None) == _erwartet)

    # Der Testton (7/aiid 2) - erst nach erfolgreichem Schreiben, nie davor.
    class _MitTon(_Roboter):
        def __init__(self, nimmt_an=True):
            super().__init__(100, nimmt_an)
            self.toene = 0

        def play_voice_test(self, _d):
            self.toene += 1
            return True

    _alt_ton = _inst.LAUTSTAERKE_TESTTON
    try:
        _inst.LAUTSTAERKE_TESTTON = True
        r = _MitTon()
        _inst.refresh_volume(r, None, 100)
        check("nach dem Schreiben wird der Testton ausgelöst", r.toene == 1)
        r = _MitTon(nimmt_an=False)
        _inst.refresh_volume(r, None, 42)
        check("ohne übernommenen Wert kein Testton", r.toene == 0)
        _inst.LAUTSTAERKE_TESTTON = False
        r = _MitTon()
        _inst.refresh_volume(r, None, 100)
        check("abgeschaltet bleibt es still", r.toene == 0)
    finally:
        _inst.LAUTSTAERKE_TESTTON = _alt_ton

    # Aktionen sind gefährlicher als Eigenschaften - auf denselben
    # Dienstnummern liegen Reinigung starten und zur Station fahren.
    # Es darf deshalb genau eine geben, und zwar den Testton.
    _cq = (Path(__file__).resolve().parent / "dreamevoice"
           / "cloud.py").read_text(encoding="utf-8")
    check("die App löst genau eine Aktion aus",
          _cq.count("self.call_action(") == 1)
    check("und zwar den Testton des Sprachdienstes",
          "call_action(device, SIID_VOICE, AIID_VOICE_PLAY_SOUND)" in _cq)

    # Die Reihenfolge zählt: erst lesen, dann wechseln, dann schreiben.
    _quelle = (Path(__file__).resolve().parent / "dreamevoice"
               / "installer.py").read_text(encoding="utf-8")
    _lesen = _quelle.find("cloud.voice_volume(device)")
    _wechsel = _quelle.find("cloud.install_voice_pack(")
    _schreiben = _quelle.find("refresh_volume(cloud, device")
    check("die Lautstärke wird vor dem Wechsel gelesen",
          0 < _lesen < _wechsel)
    check("und erst nach dem Wechsel zurückgeschrieben",
          _wechsel < _schreiben)

    # ---------------------------------------------------------------
    section("30. Sammelabfrage und die Speichersonde")

    # Hundert Werte einzeln zu holen heißt hundert Anfragen durch die
    # Cloud. Gebündelt ist es eine - aber nur, wenn die Antwort sauber
    # auseinandergenommen wird.
    _c = object.__new__(_DC)

    class _Geraet:
        did = "X"

    _antwort = [
        {"did": "X", "siid": 7, "piid": 1, "code": 0, "value": 100},
        {"did": "X", "siid": 7, "piid": 2, "code": 0, "value": "BAYERN"},
        {"did": "X", "siid": 7, "piid": 8, "code": -4004},        # gibt es nicht
        {"did": "X", "siid": 7, "piid": 9, "code": 0},            # ohne Wert
        "kaputt",                                                  # gar kein Eintrag
        {"did": "X", "siid": "7", "piid": "10", "code": 0, "value": "de"},
    ]
    _c.send = lambda _d, _m, _p, **_k: _antwort
    _gelesen = _c.get_properties(_Geraet(), [(7, i) for i in range(1, 11)])
    check("die Sammelabfrage liefert die beantworteten Stellen",
          _gelesen == {(7, 1): 100, (7, 2): "BAYERN", (7, 10): "de"},
          f"{_gelesen}")
    check("nicht vorhandene Stellen fehlen im Ergebnis", (7, 8) not in _gelesen)
    check("Stellen ohne Wert fehlen ebenfalls", (7, 9) not in _gelesen)
    _c.send = lambda _d, _m, _p, **_k: None
    check("eine unbrauchbare Antwort ergibt nichts",
          _c.get_properties(_Geraet(), [(7, 1)]) == {})

    # Die Sonde tastet den Roboter ab. Sie darf ihn dabei unter keinen
    # Umständen anfassen - auf denselben Dienstnummern liegt die
    # Reinigung.
    # Der Ordner "Werkzeuge" liegt nicht im Git. Ein frischer Klon hätte
    # hier einen FileNotFoundError geworfen - mitten im Lauf, ohne
    # Bilanz, und alle folgenden Prüfungen wären ersatzlos entfallen.
    _sonde_pfad = (Path(__file__).resolve().parent / "Werkzeuge"
                   / "Speicher-suchen.py")
    if not _sonde_pfad.is_file():
        uebersprungen("die Sonde fasst den Roboter nicht an",
                      "Werkzeuge/Speicher-suchen.py ist hier nicht vorhanden")
    else:
        _sonde = _sonde_pfad.read_text(encoding="utf-8")
        for _verboten in ("set_property", "set_properties", "call_action",
                          "install_voice_pack", "play_voice_test"):
            check(f"die Sonde ruft kein {_verboten} auf", _verboten not in _sonde)

    # ---------------------------------------------------------------
    section("31. Feste Kennung - und der Beweis, dass wirklich etwas geschah")

    # Weil jetzt immer unter CUSTOM installiert wird, meldet der Roboter
    # diese Kennung schon vor dem Auftrag als aktiv. "Kennung ist aktiv"
    # taugt dann nicht mehr als Erfolgsbeweis - sonst meldet die App
    # Erfolg, bevor der Roboter überhaupt etwas getan hat.
    import inspect as _inspect

    check("install_pack nimmt keine Kennung mehr entgegen",
          "lang_id" not in _inspect.signature(_inst.install_pack).parameters)

    # Der Roboter liefert den Zustand als JSON mit maskierten
    # Anführungszeichen - so, wie es die Abfrage am Gerät gezeigt hat.
    _echt = '{\\"id\\":\\"CUSTOM\\",\\"state\\":\\"success\\",\\"progress\\":100}'
    check("die maskierte Zustandsmeldung wird gelesen",
          (_inst._status_lesen(_echt) or {}).get("id") == "CUSTOM")
    check("gewöhnliches JSON auch",
          (_inst._status_lesen('{"state":"downloading"}') or {}).get("state")
          == "downloading")
    for _muell in (None, "", "  ", "kein json", 42, "[1,2]"):
        check(f"{_muell!r} ergibt keinen Zustand",
              _inst._status_lesen(_muell) is None)

    class _Uhr:
        """Ersetzt die Uhr im Installer - sleep lässt die Zeit springen.

        Früher liefen diese Prüfungen gegen die echte Uhr mit einer
        Frist von 0,4 Sekunden. Unter Last kippte das gelegentlich um.
        Jetzt ist der Ablauf deterministisch.
        """

        def __init__(self):
            self.jetzt = 1000.0

        def time(self):
            return self.jetzt

        def sleep(self, sekunden):
            self.jetzt += sekunden

    class _Falscher:
        """Ein Roboter, dessen Antworten der Test vorgibt."""

        def __init__(self, paket="CUSTOM", verlauf=None, stumm=0,
                     stumm_am_anfang=False, halb=False):
            self.paket = paket
            self.verlauf = list(verlauf or [])
            #: So viele der nächsten Abfragen bleiben ohne Antwort.
            self.stumm = stumm
            self.stumm_am_anfang = stumm_am_anfang
            #: Nur eine der beiden Stellen antwortet.
            self.halb = halb
            self.abfragen = 0
            self.aufgespielt = []
            self.lautstaerke = 100

        def supports_voice_service(self, _d):
            return True

        def voice_volume(self, _d):
            return self.lautstaerke

        def set_voice_volume(self, _d, w):
            self.lautstaerke = w
            return True

        def _status(self):
            # Der erste Wert gilt als Zustand vor dem Auftrag; danach
            # wird die Liste abgearbeitet, der letzte bleibt stehen.
            if len(self.verlauf) > 1:
                return self.verlauf.pop(0)
            return self.verlauf[0] if self.verlauf else None

        def voice_state(self, _d):
            self.abfragen += 1
            if self.stumm_am_anfang and self.abfragen == 1:
                return {}
            if self.stumm > 0:
                self.stumm -= 1
                return {}
            if self.halb:
                # Nur die Kennung antwortet, der Zustand nicht.
                return {"paket": self.paket}
            return {"paket": self.paket, "zustand": self._status()}

        def install_voice_pack(self, _d, lang_id, url, md5, size):
            self.aufgespielt.append((lang_id, url, md5, size))
            return True

    class _Bau:
        path = Path("Bayerisch_fertig.tar.gz")
        size = 7_000_000
        size_mb = 7.0
        md5 = "0" * 32

    def _spielen(roboter, zeit=60.0):
        """Ruft install_pack ohne Webserver und mit gestellter Uhr auf."""
        _alt = _inst.time
        try:
            _inst.time = _Uhr()
            return _inst.install_pack(
                cloud=roboter, device=object(), build=_Bau(),
                public_url="http://192.0.2.1/paket.tar.gz",
                install_timeout=zeit)
        finally:
            _inst.time = _alt

    def _zurueckholen(roboter, pack, zeit=60.0):
        _alt = _inst.time
        try:
            _inst.time = _Uhr()
            return _inst.restore_official(cloud=roboter, device=object(),
                                          pack=pack, timeout=zeit)
        finally:
            _inst.time = _alt

    _fertig = '{"id":"CUSTOM","state":"success","progress":100}'
    _laeuft = '{"id":"CUSTOM","state":"downloading","progress":40}'
    _kaputt = '{"id":"CUSTOM","state":"fail"}'

    # a) Nichts rührt sich, die Kennung stand schon vorher: Die alte
    #    Erfolgsmeldung darf nicht als Beweis durchgehen - auch nicht
    #    nach beliebig langem Warten. Der Roboter lässt seine letzte
    #    Meldung stehen; bloße Zeit macht daraus keine neue.
    _r = _Falscher(paket="CUSTOM", verlauf=[_fertig])
    _e = _spielen(_r, zeit=600)
    check("unveränderte Erfolgsmeldung gilt nie als Beweis",
          not _e.success, _e.message)
    check("auch langes Warten ändert daran nichts",
          _r.abfragen > 100, f"{_r.abfragen} Abfragen")
    check("der Auftrag ging trotzdem unter CUSTOM raus",
          bool(_r.aufgespielt) and _r.aufgespielt[0][0] == "CUSTOM")

    # b) Der Zustand bewegt sich - das ist der einzige Beweis.
    _r = _Falscher(paket="CUSTOM", verlauf=[_fertig, _laeuft, _fertig])
    _e = _spielen(_r)
    check("eine beobachtete Zustandsänderung genügt", _e.success, _e.message)

    # c) Ein einzelner Aussetzer der Cloud ist KEINE Veränderung.
    #    Vorher galt "keine Antwort" als anderer Wert - ein Wackler
    #    reichte, um die alte Erfolgsmeldung zu glauben.
    _r = _Falscher(paket="CUSTOM", verlauf=[_fertig], stumm=3)
    _e = _spielen(_r, zeit=120)
    check("ein Abfragefehler zählt nicht als Bewegung",
          not _e.success, _e.message)

    # d) Auch der Vorzustand kann fehlschlagen. Dann darf erst recht
    #    nicht sofort Erfolg gemeldet werden.
    _r = _Falscher(paket="CUSTOM", verlauf=[_fertig], stumm_am_anfang=True)
    _e = _spielen(_r, zeit=120)
    check("ohne gelesenen Vorzustand kein Sofort-Erfolg",
          not _e.success, _e.message)

    # e) Der Roboter sagt selbst, dass es schiefging - nach Bewegung.
    _r = _Falscher(paket="CUSTOM", verlauf=[_fertig, _laeuft, _kaputt])
    _e = _spielen(_r)
    check("ein gemeldeter Fehlschlag wird als solcher gemeldet",
          not _e.success and "fehlgeschlagen" in _e.message.lower(), _e.message)

    # f) Ein stehengebliebener Fehlschlag vom letzten Versuch darf den
    #    neuen nicht sofort abwürgen - sonst sitzt ein Laie in einer
    #    Sackgasse, aus der er nicht mehr herausfindet.
    _r = _Falscher(paket="CUSTOM", verlauf=[_kaputt])
    _e = _spielen(_r, zeit=30)
    check("ein alter Fehlschlag würgt den neuen Versuch nicht ab",
          "fehlgeschlagen" not in _e.message.lower(), _e.message)

    # g) Und der Fehlschlag eines FREMDEN Pakets erst recht nicht.
    _r = _Falscher(paket="CUSTOM",
                   verlauf=[_fertig, '{"id":"DE","state":"fail"}', _fertig])
    _e = _spielen(_r, zeit=30)
    check("der Fehlschlag eines anderen Pakets zählt nicht",
          "fehlgeschlagen" not in _e.message.lower(), _e.message)

    # h) Der alte Weg muss weiter gehen: Stand vorher etwas anderes,
    #    reicht das Umschalten der Kennung.
    class _Umschalter(_Falscher):
        def __init__(self, von="DE", nach="CUSTOM"):
            super().__init__(paket=von)
            self.nach = nach

        def voice_state(self, _d):
            self.abfragen += 1
            if self.abfragen > 1:
                self.paket = self.nach
            return {"paket": self.paket, "zustand": None}

    _e = _spielen(_Umschalter())
    check("das Umschalten von DE auf CUSTOM zählt weiter", _e.success,
          _e.message)

    # i) Und die Lautstärke wurde dabei zurückgeschrieben.
    _r = _Falscher(paket="CUSTOM", verlauf=[_fertig, _laeuft, _fertig])
    _r.lautstaerke = 63
    _spielen(_r)
    check("die Lautstärke steht hinterher wieder auf ihrem Wert",
          _r.lautstaerke == 63, f"{_r.lautstaerke}")

    # j) Ohne bestätigten Erfolg wird die Lautstärke nicht angefasst.
    _r = _Falscher(paket="CUSTOM", verlauf=[_fertig])
    _r.lautstaerke = 55
    _e = _spielen(_r, zeit=30)
    check("ohne Bestätigung bleibt die Lautstärke unberührt",
          not _e.success and _r.lautstaerke == 55, f"{_r.lautstaerke}")

    # k) Aus dem Forum: Der Roboter blieb auch nach dem Zurückholen der
    #    Originalstimme leise. Dieser Weg braucht dieselbe Behandlung.
    class _Pack:
        id = "DE"
        label = "Deutsch"
        url = "https://example.invalid/de.tar.gz"
        md5 = "0" * 32
        size = 5_000_000

    _r = _Umschalter(von="CUSTOM", nach="DE")
    _r.lautstaerke = 77
    _e = _zurueckholen(_r, _Pack())
    check("das Zurückholen wird bestätigt", _e.success, _e.message)
    check("und die Lautstärke wird auch dabei zurückgeschrieben",
          _r.lautstaerke == 77, f"{_r.lautstaerke}")
    check("mit dem Hinweis auf den Neustart, falls es doch leise bleibt",
          "Neustart" in (_e.hint or ""), _e.hint)

    # l) "DE" wiederherstellen, während "DE" schon aktiv ist. Die
    #    Meldung "Das Originalpaket ist wieder aktiv" ist dann wahr -
    #    sie sagt etwas über den Zustand aus, nicht über den
    #    Vorgang, und genau diesen Zustand wollte der Nutzer. Wer aber
    #    wiederherstellt, WEIL etwas kaputt ist, darf nicht in
    #    Sicherheit gewiegt werden: Dass keine Neuinstallation zu
    #    beobachten war, muss dabeistehen.
    _r = _Falscher(paket="DE", verlauf=['{"id":"DE","state":"success"}'])
    _e = _zurueckholen(_r, _Pack(), zeit=600)
    check("bereits aktives Originalpaket gilt als erreicht",
          _e.success, _e.message)
    check("aber der fehlende Nachweis steht im Hinweis",
          "war schon vorher die aktive" in (_e.hint or ""), _e.hint)
    check("mit einem Weg, es trotzdem zu erzwingen",
          "Sprachton" in (_e.hint or ""))

    # m) Beim EIGENEN Paket wäre derselbe Schluss falsch: Dass CUSTOM
    #    aktiv ist, heißt nicht, dass das neue Paket darunterliegt.
    #    Ohne belegten Download darf es deshalb keinen Erfolg geben.
    _r = _Falscher(paket="CUSTOM", verlauf=[_fertig])
    _e = _spielen(_r, zeit=600)
    check("beim eigenen Paket zählt der Endzustand allein nicht",
          not _e.success, _e.message)

    # n) Der Fall, an dem die erste Korrektur noch scheiterte: Der Roboter
    #    beantwortet nur EINE der beiden Stellen. Früher kam die andere
    #    als None zurück, und None sah aus wie ein geänderter Wert -
    #    damit war die Scheinbewegung wieder da, die der ganze Beobachter
    #    verhindern soll. Alle drei Fälle sind nachgestellt.
    class _Halb(_Falscher):
        """Beantwortet bei bestimmten Abfragen nur eine der Stellen."""

        def __init__(self, fehlt, bei, paket="CUSTOM", verlauf=None):
            super().__init__(paket=paket, verlauf=verlauf)
            self.fehlt = fehlt          # "paket" oder "zustand"
            self.bei = set(bei)         # bei diesen Abfragenummern

        def voice_state(self, _d):
            self.abfragen += 1
            antwort = {"paket": self.paket, "zustand": self._status()}
            if self.abfragen in self.bei:
                antwort.pop(self.fehlt)
            return antwort

    # Fall A: Die Kennung fehlt schon beim Vorzustand. Früher wurde
    #         schon_aktiv damit fälschlich False - und der allererste
    #         Blick meldete sofort Erfolg.
    _r = _Halb("paket", bei=[1], paket="CUSTOM", verlauf=[_fertig])
    _e = _spielen(_r, zeit=120)
    check("fehlende Kennung im Vorzustand ergibt keinen Sofort-Erfolg",
          not _e.success, _e.message)

    # Fall B: Der Zustand fällt bei einem einzelnen Blick aus. Früher
    #         galt das als Bewegung, und der nächste Blick glaubte die
    #         stehengebliebene Erfolgsmeldung.
    _r = _Halb("zustand", bei=[3], paket="CUSTOM", verlauf=[_fertig])
    _e = _spielen(_r, zeit=120)
    check("ein halber Ausfall ist keine Bewegung", not _e.success, _e.message)

    # Fall C: Stehengebliebener Fehlschlag plus halber Blick. Früher
    #         würgte das den laufenden Versuch ab.
    _r = _Halb("zustand", bei=[3], paket="CUSTOM", verlauf=[_kaputt])
    _e = _spielen(_r, zeit=120)
    check("ein halber Ausfall belebt keinen alten Fehlschlag",
          "fehlgeschlagen" not in _e.message.lower(), _e.message)

    # o) Und der Gegenbeweis, dass die Sperre nicht zu weit geht: Mit
    #    belegtem Download UND Erfolgsmeldung für die eigene Kennung
    #    darf es gelingen, auch ohne erwischtes Zwischenfenster. Sonst
    #    stünde beim Nutzer "Nicht aufgespielt", obwohl alles geklappt
    #    hat - der Roboter hat die Datei nachweislich geholt.
    class _MitDownload(_Falscher):
        pass

    _alt_los = _inst._Beobachter.los
    _r = _MitDownload(paket="CUSTOM", verlauf=[_fertig])
    _alt = _inst.time
    try:
        _inst.time = _Uhr()
        _e = _inst.install_pack(
            cloud=_r, device=object(), build=_Bau(),
            public_url="http://192.0.2.1/paket.tar.gz", install_timeout=600)
    finally:
        _inst.time = _alt
    check("ohne Download-Beleg bleibt es bei der Zurückhaltung",
          not _e.success, _e.message)

    # Dasselbe mit Beleg - direkt am Beobachter, weil der Webserver im
    # Test nicht läuft.
    _r = _Falscher(paket="CUSTOM", verlauf=[_fertig])
    _alt = _inst.time
    try:
        _uhr = _Uhr()
        _inst.time = _uhr
        _b = _inst._Beobachter(_r, object(), "CUSTOM")
        _b.los()
        _b.beleg_download()
        _erste = _b.nachsehen()
        _uhr.sleep(_inst._Beobachter.NACH_DOWNLOAD + 1)
        _spaeter = _b.nachsehen()
    finally:
        _inst.time = _alt
    check("gleich nach dem Download zählt die alte Meldung noch nicht",
          _erste == _inst._Beobachter.WARTEN, _erste)
    # Bewusst nicht FERTIG: Der Zustand ist wortgleich mit dem von
    # vorher, eine Änderung war also nicht zu beobachten. Der
    # Download belegt, dass der Roboter unsere Datei geholt hat -
    # mehr als "wahrscheinlich" gibt das nicht her, und genau das
    # bekommt der Nutzer auch zu lesen.
    check("nach der Wartezeit reicht es für WAHRSCHEINLICH",
          _spaeter == _inst._Beobachter.WAHRSCHEINLICH, _spaeter)

    # Und die Meldung darf dann nicht so klingen wie eine bestätigte.
    _r = _Falscher(paket="CUSTOM", verlauf=[_fertig])
    _alt = _inst.time
    try:
        _inst.time = _Uhr()
        _b = _inst._Beobachter(_r, object(), "CUSTOM")
        _b.los()
        _b.beleg_download()
    finally:
        _inst.time = _alt

    # Der Widerspruch, der die App einmal lügen ließ: Der Roboter
    # meldet eine andere Kennung als aktiv, der Zustand trägt noch
    # den Erfolg des Ziels. Der Gegenbeweis liegt im selben Datensatz.
    class _Widerspruch(_Falscher):
        def voice_state(self, _d):
            self.abfragen += 1
            return {"paket": "FR",
                    "zustand": '{"id":"DE","state":"success"}'}

    _r = _Widerspruch()
    _e = _zurueckholen(_r, _Pack(), zeit=120)
    check("eine Erfolgsmeldung gegen die aktive Kennung zählt nicht",
          not _e.success, _e.message)

    # Der Fehlschlag darf davon nicht betroffen sein: Nach einem
    # misslungenen Wechsel steht die ALTE Kennung noch - ein Abgleich
    # mit dem Ziel wäre dort falsch.
    _r = _Falscher(paket="DE", verlauf=[_fertig, _laeuft, _kaputt])
    _e = _spielen(_r, zeit=120)
    check("ein Fehlschlag wird trotz alter Kennung gemeldet",
          "fehlgeschlagen" in _e.message.lower(), _e.message)

    # Firmware ohne id-Feld: Erfolg und Fehlschlag müssen gleich
    # behandelt werden. Sonst ist so ein Gerät blind für Fehler
    # und blindgläubig beim Erfolg.
    _r = _Falscher(paket="CUSTOM",
                   verlauf=['{"state":"idle"}', '{"state":"fail"}'])
    _e = _spielen(_r, zeit=120)
    check("ein Fehlschlag ohne Kennung wird trotzdem gemeldet",
          "fehlgeschlagen" in _e.message.lower(), _e.message)

    # Ein einzelnes null bei der Kennung ist keine Bewegung.
    class _Aussetzer(_Falscher):
        def voice_state(self, _d):
            self.abfragen += 1
            paket = None if self.abfragen == 3 else "CUSTOM"
            return {"paket": paket, "zustand": _fertig}

    _e = _spielen(_Aussetzer(), zeit=120)
    check("ein null-Wert bei der Kennung ist keine Bewegung",
          not _e.success, _e.message)


    # Die App darf nicht versprechen, was sie nicht halten kann. Ein
    # Nutzer konnte die Lautstärke nach dem Wechsel auch über die
    # Dreamehome-App nicht mehr erhöhen - unser Schreibzugriff ist
    # schwächer als das. Er bestätigt den gespeicherten Wert, mehr
    # nicht.
    _zeilen = []
    _r = _Falscher(paket="CUSTOM")
    _inst.refresh_volume(_r, None, 100, _zeilen.append)
    _gesagt = " ".join(_zeilen).lower()
    check("die Erfolgsmeldung verspricht keinen ersparten Neustart",
          "kein neustart" not in _gesagt, f"{_zeilen}")
    check("sie behauptet nur, was geprüft wurde", "bestätigt" in _gesagt,
          f"{_zeilen}")

    # Und der Hinweis sagt dem Laien, was er tun kann.
    for _wort in ("Firmware", "Neustart", "aus und wieder ein"):
        check(f"der Hinweis nennt '{_wort}'", _wort in _inst.NEUSTART_HINWEIS)
    check("er schiebt es nicht auf die Aufnahmen",
          "nicht an den Aufnahmen" in _inst.NEUSTART_HINWEIS)
    check("er steht im Fertig-Fenster, nicht nur im Protokoll",
          "installer.NEUSTART_HINWEIS" in
          (Path(__file__).resolve().parent / "dreamevoice" / "ui"
           / "page_voice.py").read_text(encoding="utf-8"))

    # Solange nicht am Gerät geprüft, bleibt der Testton aus.
    check("der Testton ist ab Werk aus", _inst.LAUTSTAERKE_TESTTON is False)
    check("der Umweg über einen anderen Wert auch",
          _inst.LAUTSTAERKE_UMWEG is False)

    # Beide Wege hängen am selben Baustein - sonst driften sie wieder
    # auseinander, genau wie beim ersten Anlauf.
    _iq = (Path(__file__).resolve().parent / "dreamevoice"
           / "installer.py").read_text(encoding="utf-8")
    check("beide Wege benutzen denselben Beobachter",
          _iq.count("_Beobachter(cloud, device") == 2)
    check("beide frischen die Lautstärke auf",
          _iq.count("refresh_volume(cloud, device") == 2)

    # Kein Eingabefeld für die Kennung mehr - weder auf der Seite noch
    # im alten Reiter.
    for _datei in ("page_voice.py", "tab_install.py"):
        _q = (Path(__file__).resolve().parent / "dreamevoice" / "ui"
              / _datei).read_text(encoding="utf-8")
        check(f"{_datei} hat kein Kennungsfeld mehr", "var_lang" not in _q)

    # ---------------------------------------------------------------
    section("32. Sicherheit: fremde Archive und Programmaufrufe")

    import zipfile as _zip
    import tarfile as _tar
    from dreamevoice import importer as _imp, embedded as _emb, tts as _tts

    _sicher = arbeitsordner()
    try:
        # a) Ein Archiv darf nicht aus dem Zielordner ausbrechen können.
        _slip = _sicher / "slip.zip"
        with _zip.ZipFile(_slip, "w") as _zf:
            _zf.writestr("../../../entkommen.ogg", b"OggS")
            _zf.writestr("C:/Windows/Temp/absolut.ogg", b"OggS")
            _zf.writestr("7.ogg", b"OggS")
        _raus = _sicher / "a"
        _imp.extract_archive(_slip, _raus)
        _namen = sorted(p.name for p in _raus.iterdir())
        check("Pfadangaben im Archiv werden verworfen",
              _namen == ["7.ogg", "absolut.ogg", "entkommen.ogg"], f"{_namen}")
        check("nichts landet außerhalb des Zielordners",
              not (_sicher / "entkommen.ogg").exists()
              and all(p.parent == _raus for p in _raus.iterdir()))

        # b) Eine Archivbombe darf den Speicher nicht füllen.
        _bombe = _sicher / "bombe.zip"
        with _zip.ZipFile(_bombe, "w", _zip.ZIP_DEFLATED) as _zf:
            _zf.writestr("999.ogg", b"\0" * (int(_imp.MAX_EINTRAG_BYTES) + 4096))
            _zf.writestr("8.ogg", b"OggS")
        _raus = _sicher / "b"
        with leise("dreamevoice.importer"):
            _imp.extract_archive(_bombe, _raus)
        check("die übergroße Datei wird übersprungen",
              sorted(p.name for p in _raus.iterdir()) == ["8.ogg"])
        check("das Archiv selbst ist winzig - genau darum geht es",
              _bombe.stat().st_size < 1024 * 1024,
              f"{_bombe.stat().st_size // 1024} kB")

        # c) Ein Verweis im tar zeigt woandershin - er darf nicht mit.
        _link = _sicher / "link.tar"
        with _tar.open(_link, "w") as _tf:
            _i = _tar.TarInfo("9.ogg")
            _i.type = _tar.SYMTYPE
            _i.linkname = r"C:\Windows\System32\config\SAM"
            _tf.addfile(_i)
            _d = b"OggS"
            _e = _tar.TarInfo("10.ogg")
            _e.size = len(_d)
            _tf.addfile(_e, io.BytesIO(_d))
        _raus = _sicher / "c"
        _imp.extract_archive(_link, _raus)
        _namen = sorted(p.name for p in _raus.iterdir())
        check("Verweise im tar werden nicht übernommen", _namen == ["10.ogg"],
              f"{_namen}")

        # d) Ein beschädigtes Archiv muss eine verständliche Meldung
        #    ergeben. Der tar-Zweig übersetzte seine Fehler seit jeher,
        #    der zip-Zweig ließ einen rohen BadZipFile durch - bis in
        #    den Fehlerdialog eines Laien.
        _crc = _sicher / "crc.zip"
        _nutz = b"OggS" + bytes(500)
        with _zip.ZipFile(_crc, "w", _zip.ZIP_STORED) as _zf:
            _zf.writestr("7.ogg", _nutz)
        _roh = bytearray(_crc.read_bytes())
        _roh[_roh.find(_nutz) + 10] ^= 0xFF      # CRC stimmt nun nicht mehr
        _crc.write_bytes(bytes(_roh))
        try:
            with leise("dreamevoice.importer"):
                _imp.extract_archive(_crc, _sicher / "d")
            check("ein beschädigtes ZIP wird abgefangen", False,
                  "keine Ausnahme")
        except PackError as _exc:
            check("ein beschädigtes ZIP wird abgefangen", True)
            # Der Hinweis muss sagen, was los ist UND was zu tun ist.
            # "Technische Details: Bad CRC-32" allein ist beides nicht.
            _h = (getattr(_exc, "hint", "") or "").lower()
            check("und in Worte gefasst, die ein Laie versteht",
                  ("beschädigt" in _h or "unvollständig" in _h)
                  and "herunter" in _h, _h[:120])
        except Exception as _exc:                # noqa: BLE001
            check("ein beschädigtes ZIP wird abgefangen", False,
                  f"{type(_exc).__name__} statt PackError")
    finally:
        _shutil.rmtree(_sicher, ignore_errors=True)

    # d) Auch der Weg aus der EXE heraus nimmt keinen Pfad entgegen.
    with leise("dreamevoice.embedded"):
        for _boese in ("../autostart.exe", r"..\autostart.exe",
                       "unter/ordner.zip", ""):
            check(f"Dialektname {_boese!r} wird abgewiesen",
                  _emb.extract_dialekt(_boese) is None)

    # e) Programme werden mit vollem Pfad gestartet. Ohne Pfad sucht
    #    Windows zuerst im Ordner der Anwendung - bei einer
    #    heruntergeladenen EXE ist das der Download-Ordner.
    _ps = _tts._powershell_exe()
    check("powershell wird mit vollem Pfad aufgerufen",
          _ps.lower().endswith("powershell.exe") and Path(_ps).is_absolute(),
          _ps)
    _tq = (Path(__file__).resolve().parent / "dreamevoice"
           / "tts.py").read_text(encoding="utf-8")
    check("der bloße Name steht nicht mehr im Aufruf",
          '["powershell", "-NoProfile"' not in _tq)

    # f) Kein Weg, auf dem Text zu Befehl werden könnte.
    check("Anführungszeichen werden für PowerShell verdoppelt",
          _tts._ps_quote("a'; rm -rf /; '") == "'a''; rm -rf /; '''")
    check("die Ansagetexte gehen über eine Datei, nicht ins Skript",
          "$job.text" in _tq and "SecurityElement]::Escape" in _tq)

    _quellen = {p.name: p.read_text(encoding="utf-8")
                for p in (Path(__file__).resolve().parent
                          / "dreamevoice").rglob("*.py")}
    for _verboten in ("eval(", "exec(", "shell=True", "os.system(",
                      "pickle", "extractall"):
        _treffer = [n for n, q in _quellen.items() if _verboten in q]
        check(f"nirgends {_verboten}", not _treffer, f"{_treffer}")

    # g) Verschlüsselte Verbindungen werden nirgends abgeschaltet.
    #    Früher stand hier check(..., True) - buchstäblich eine
    #    Prüfung, die nicht fehlschlagen konnte.
    _ohne_tls = [_n for _n, _q in _quellen.items()
                 if "verify=False" in _q.replace(" ", "")]
    check("die Zertifikatsprüfung wird nirgends abgeschaltet",
          not _ohne_tls, f"{_ohne_tls}")

    # ---------------------------------------------------------------
    section("33. Männlich und weiblich auseinanderhalten")

    from dreamevoice import dialektpakete as _dp

    # Sobald es zwei bayerische Stimmen gibt, unterscheiden sie sich nur
    # noch im Geschlecht. Steht das nicht im angezeigten Namen, sind die
    # beiden Einträge in der Liste nicht auseinanderzuhalten - und die
    # Auswahl greift über den Namen zu.
    _namen = [e.anzeigename for e in _dp.KATALOG]
    check("jeder Eintrag trägt sein Geschlecht im Namen",
          all("(" in n and (n.endswith("(männlich)") or n.endswith("(weiblich)"))
              for n in _namen), f"{_namen}")
    check("keine zwei Einträge heißen gleich",
          len(set(_namen)) == len(_namen), f"{_namen}")
    check("es gibt genau eine weibliche Stimme",
          sum(1 for e in _dp.KATALOG if e.geschlecht == "weiblich") == 1)
    check("und die ist bayerisch",
          next(e.name for e in _dp.KATALOG if e.geschlecht == "weiblich")
          == "Bayerisch")

    # Ein Eintrag ohne Aufnahmen darf nicht in der Liste auftauchen -
    # sonst wählt man etwas, das die App nicht liefern kann.
    #
    # Früher wurden hier die Einträge mit quelle() == FEHLT gegen
    # verfuegbar() geschnitten. Beide Mengen kommen aus derselben
    # Funktion; die Schnittmenge ist per Definition leer, ganz gleich
    # wie quelle() aussieht. Jetzt wird ein Eintrag gebaut, zu dem es
    # garantiert keine Datei gibt.
    _erfunden = _dp.FertigerDialekt(
        key="gibtsnicht", name="Marsianisch",
        datei="Gibt-Es-Nicht-Aufnahmen.zip", ansagen=1,
        stimme="niemand", beschreibung="nur zum Testen")
    check("ein Eintrag ohne Aufnahmen gilt als fehlend",
          _dp.quelle(_erfunden) == _dp.QUELLE_FEHLT,
          _dp.quelle(_erfunden))

    _alt_katalog = _dp.KATALOG
    try:
        _dp.KATALOG = _alt_katalog + [_erfunden]
        check("und taucht deshalb nicht in der Auswahl auf",
              _erfunden.key not in [e.key for e in _dp.verfuegbar()])
        check("die übrigen bleiben davon unberührt",
              len(_dp.verfuegbar()) == len([e for e in _alt_katalog
                                            if _dp.quelle(e)
                                            != _dp.QUELLE_FEHLT]))
    finally:
        _dp.KATALOG = _alt_katalog

    # Die Kennung steuert nichts mehr - sie darf nicht wieder
    # unbemerkt an die Installation geraten.
    _pv = (Path(__file__).resolve().parent / "dreamevoice" / "ui"
           / "page_voice.py").read_text(encoding="utf-8")
    check("die Stimmenliste führt keine Kennung mehr mit",
          "self.kennung" not in _pv)

    # ---------------------------------------------------------------
    section("34. Was den Roboter wirklich anfasst")

    # Diese drei Funktionen sind der gesamte Kontakt zum Gerät - und sie
    # waren bisher von keinem Test berührt, weil jede Attrappe genau sie
    # ersetzt hat. Ein Tippfehler im Schlüsselnamen oder eine Größe als
    # Zeichenkette statt als Zahl wäre nie aufgefallen; der Roboter
    # bekäme Müll auf der Nummer, auf der er Sprachpakete annimmt.
    from dreamevoice import cloud as _cl

    class _Gemerkt:
        did = "did-123"

    _echt = object.__new__(_cl.DreameCloud)
    _gesendet = []
    _echt.send = lambda _d, methode, params, **_k: _gesendet.append(
        (methode, params)) or [{"code": 0}]

    _echt.install_voice_pack(_Gemerkt(), "CUSTOM",
                             "http://192.168.1.5:8000/paket.tar.gz",
                             "d41d8cd98f00b204e9800998ecf8427e", 7_654_321)
    _methode, _params = _gesendet[-1]
    check("der Auftrag geht als set_properties raus", _methode == "set_properties")
    _eintrag = _params[0]
    check("an den Sprachdienst, Stelle 4",
          (_eintrag["siid"], _eintrag["piid"]) == (7, 4),
          f"{_eintrag['siid']}/{_eintrag['piid']}")

    _nutzlast = json.loads(_eintrag["value"])
    check("die Nutzlast hat genau die vier erwarteten Felder",
          sorted(_nutzlast) == ["id", "md5", "size", "url"], f"{sorted(_nutzlast)}")
    check("die Kennung steht drin", _nutzlast["id"] == "CUSTOM")
    check("die Adresse steht drin",
          _nutzlast["url"] == "http://192.168.1.5:8000/paket.tar.gz")
    check("die Prüfsumme steht drin",
          _nutzlast["md5"] == "d41d8cd98f00b204e9800998ecf8427e")
    # Als Zeichenkette würde der Roboter die Größe verwerfen.
    check("die Größe ist eine Zahl, keine Zeichenkette",
          isinstance(_nutzlast["size"], int) and _nutzlast["size"] == 7_654_321,
          f"{type(_nutzlast['size']).__name__}")
    check("die Nutzlast enthält keine überflüssigen Leerzeichen",
          " " not in _eintrag["value"], _eintrag["value"])

    # Auch eine Größe, die als Zeichenkette hereinkommt, muss als Zahl
    # hinausgehen - der Aufrufer liest sie mitunter aus einer Datei.
    _gesendet.clear()
    _echt.install_voice_pack(_Gemerkt(), "CUSTOM", "http://x/y", "0" * 32, "42")
    check("eine als Text übergebene Größe wird zur Zahl",
          json.loads(_gesendet[-1][1][0]["value"])["size"] == 42)

    # Die Sicherheitsschranke: Ohne sie schriebe die App auf Geräte, bei
    # denen auf siid 7 etwas ganz anderes liegt - Mähroboter, alte
    # Mi-Home-Modelle. Ihre Logik lief bisher nie.
    for _roh, _erwartet in (("DE", True), ("CUSTOM", True), ("BAYERN", True),
                            ("", False), ("   ", False), (None, False),
                            (42, False), (True, False), ("x" * 17, False),
                            ("x" * 16, True), ([], False), ({}, False)):
        _echt.get_property = lambda _d, _s, _p, _v=_roh: _v
        check(f"Sprachdienst bei {_roh!r}: {'ja' if _erwartet else 'nein'}",
              _echt.supports_voice_service(_Gemerkt()) is _erwartet)

    # Antwortet das Gerät gar nicht, wird nichts gesendet.
    def _wirft(_d, *_a, **_k):
        raise NetworkError("offline")

    # Ein schlafender Roboter darf NICHT als "kennt keine Sprachpakete"
    # durchgehen. Früher gab die Schranke dafür False zurück, und der
    # Nutzer bekam die Auskunft, sein Gerät könne das gar nicht - er
    # suchte dann an der völlig falschen Stelle.
    # Die Attrappe aus der Tabelle oben muss weg - sonst fängt sie den
    # Aufruf ab, bevor er überhaupt bis get_properties kommt.
    _echt.__dict__.pop("get_property", None)
    _echt.get_properties = _wirft
    with leise("dreamevoice.cloud"):
        try:
            _echt.supports_voice_service(_Gemerkt())
            check("keine Antwort wird nicht als fehlender Dienst gewertet",
                  False, "es kam False statt einer Ausnahme")
        except NetworkError:
            check("keine Antwort wird nicht als fehlender Dienst gewertet", True)

    # voice_state trägt seit heute die gesamte Erfolgserkennung. Lieferte
    # es bei einem Netzaussetzer True statt False, meldete die App eine
    # Installation als gelungen, die nie stattgefunden hat.
    _echt.get_properties = lambda _d, _specs: {(7, 2): "CUSTOM",
                                               (7, 3): '{"state":"success"}'}
    check("voice_state liefert Kennung und Zustand",
          _echt.voice_state(_Gemerkt())
          == {"paket": "CUSTOM", "zustand": '{"state":"success"}'})

    _echt.get_properties = lambda _d, _specs: {}
    check("eine leere Antwort gilt als nicht gelesen",
          _echt.voice_state(_Gemerkt()) == {})

    def _wirft2(_d, _specs):
        raise NetworkError("offline")

    _echt.get_properties = _wirft2
    with leise("dreamevoice.cloud"):
        check("ein Netzfehler gilt als nicht gelesen",
              _echt.voice_state(_Gemerkt()) == {})

    # Der Teilfall, an dem sich alles entscheidet: Der Roboter
    # beantwortet nur EINE der beiden Stellen. Früher kam die andere
    # als None zurück - und None sah für die Erfolgserkennung aus
    # wie ein geänderter Wert. Ein halber Aussetzer genügte damit
    # als "Beweis", dass am Roboter etwas passiert sei.
    _echt.get_properties = lambda _d, _specs: {(7, 2): "CUSTOM"}
    _halb = _echt.voice_state(_Gemerkt())
    check("eine halbe Antwort liefert nur den gelesenen Wert",
          _halb == {"paket": "CUSTOM"}, f"{_halb}")
    check("die unbeantwortete Stelle fehlt, statt None zu sein",
          "zustand" not in _halb)



    # ---------------------------------------------------------------
    section("35. Was die App behauptet, muss sie belegen können")

    # Jeder Fall hier stammt aus einer Gegenprüfung und war einmal ein
    # echter Fehler. Die App hat dabei nie abgestürzt - sie hat gelogen,
    # und das ist schlimmer, weil es niemandem auffällt.
    from dreamevoice import installer as _i2

    def _blicke(folge, ziel="CUSTOM", runden=4, takt=_i2.TAKT,
                download=False):
        """Ruft den Beobachter mit vorgegebenen Antworten auf.

        Die Uhr läuft dabei mit: Einige Regeln hängen an der Zeit
        seit dem Auftrag, nicht nur an der Zahl der Blicke.
        """
        class _R:
            def __init__(self):
                self.n = 0

            def voice_state(self, _d):
                self.n += 1
                return dict(folge[min(self.n - 1, len(folge) - 1)])

        _alt = _i2.time
        try:
            _uhr = _Uhr()
            _i2.time = _uhr
            b = _i2._Beobachter(_R(), object(), ziel)
            b.los()
            if download:
                b.beleg_download()
            erg = []
            for _ in range(runden):
                erg.append(b.nachsehen())
                _uhr.sleep(takt)
            return erg
        finally:
            _i2.time = _alt

    _E = '{"id":"CUSTOM","state":"success","progress":100}'

    # a) Ein hochzählendes Nebenfeld ist keine Veränderung. Vorher
    #    genügte ein anderer Prozentwert, um eine stehengebliebene
    #    Erfolgsmeldung in ein "installiert und aktiv" zu verwandeln.
    _r = _blicke([
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"success","progress":10}'},
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"success","progress":20}'},
    ])
    check("ein hochzählendes Nebenfeld beweist nichts",
          set(_r) == {_i2._Beobachter.WARTEN}, f"{_r}")

    # b) Leerzeichen um die Kennung dürfen nicht zum Stillstand führen.
    _r = _blicke([
        {"paket": " CUSTOM ", "zustand": '{"id":"CUSTOM","state":"downloading"}'},
        {"paket": " CUSTOM ", "zustand": _E},
    ])
    check("' CUSTOM ' wird als CUSTOM erkannt",
          _i2._Beobachter.FERTIG in _r, f"{_r}")

    # c) Der Widerspruch: aktive Kennung passt nicht zur Erfolgsmeldung.
    #    Früher meldete die App hier Erfolg - der Gegenbeweis lag im
    #    selben Datensatz.
    #    Er darf aber nicht sofort zuschlagen: Die beiden Stellen am
    #    Roboter werden getrennt geführt, und die Kennung zieht der
    #    Zustandsmeldung um Sekunden hinterher. Wer nach zwei Blicken
    #    abbricht, würgt eine laufende Installation ab.
    _kurz = _blicke([{"paket": "FR", "zustand": '{"id":"DE","state":"success"}'}],
                    ziel="DE", runden=4)
    check("ein frischer Widerspruch schlägt nicht sofort zu",
          _i2._Beobachter.WIDERSPRUCH not in _kurz, f"{_kurz}")
    _r = _blicke([{"paket": "FR", "zustand": '{"id":"DE","state":"success"}'}],
                 ziel="DE", runden=25, takt=5.0)
    check("ein anhaltender Widerspruch wird gemeldet",
          _i2._Beobachter.WIDERSPRUCH in _r, f"{_r}")
    check("und niemals als Erfolg",
          _i2._Beobachter.FERTIG not in _r
          and _i2._Beobachter.WAHRSCHEINLICH not in _r, f"{_r}")

    # d) Ein einzelner Fehlschlag-Ausreißer darf den Vorgang nicht
    #    abwürgen - er schließt den Webserver, ein Wiederholungsversuch
    #    des Roboters ginge danach ins Leere.
    _r = _blicke([
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"downloading"}'},
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"fail"}'},
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"downloading"}'},
        {"paket": "CUSTOM", "zustand": _E},
    ])
    check("ein einzelner Fehlschlag würgt nicht ab",
          _i2._Beobachter.FEHLER not in _r, f"{_r}")

    # e) Ein anhaltender schon.
    _r = _blicke([
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"downloading"}'},
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"fail"}'},
    ])
    check("ein anhaltender Fehlschlag wird gemeldet",
          _i2._Beobachter.FEHLER in _r, f"{_r}")

    # f) Nie das Wort "None" in einer Meldung an den Nutzer.
    _alt = _i2.time
    try:
        _i2.time = _Uhr()
        _b = _i2._Beobachter(_Falscher(paket="CUSTOM"), object(), "CUSTOM")
        _b.aktiv = None
    finally:
        _i2.time = _alt
    check("eine unlesbare Kennung heißt nicht 'None'",
          _b.aktiv_text == "unbekannt", _b.aktiv_text)

    # g) Der Unterschied zwischen belegt und wahrscheinlich muss bis in
    #    die Oberfläche durchschlagen. Der ehrlichste Text im Installer
    #    nützt nichts, wenn das Fenster daneben "läuft jetzt" sagt.
    for _datei in ("page_voice.py", "tab_install.py"):
        _q = (Path(__file__).resolve().parent / "dreamevoice" / "ui"
              / _datei).read_text(encoding="utf-8")
        check(f"{_datei} unterscheidet belegt und wahrscheinlich",
              "bestaetigt" in _q, "Feld wird nicht ausgewertet")
        check(f"{_datei} zeigt den Hinweis auch bei Erfolg",
              _q.count("hint") >= 2, "hint nur im Fehlerfall")

    # h) Ein abgebrochener Download darf nicht als Firewall-Problem
    #    diagnostiziert werden - der Roboter hat den PC ja erreicht.
    _iq = (Path(__file__).resolve().parent / "dreamevoice"
           / "installer.py").read_text(encoding="utf-8")
    check("ein Abbruch mitten im Laden wird eigens erklärt",
          "begonnen zu laden und dann" in _iq)
    check("und nicht mit Firewall und Gast-WLAN begründet",
          "an Firewall oder" in _iq)

    # i) Hörproben räumen ihre Arbeitsordner wieder weg. Vorher blieb
    #    jede für immer liegen - beim Entwickeln waren es 146 Ordner.
    from dreamevoice import vorhoeren as _vh
    _vorher = len(list(Path(tempfile.gettempdir()).glob("dreamevoice_probe_*")))
    _leer = _vh.probe_vorbereiten(arbeitsordner() / "gibtsnicht.tar.gz", None,
                                  log=lambda _m: None)
    _nachher = len(list(Path(tempfile.gettempdir()).glob("dreamevoice_probe_*")))
    check("eine Hörprobe ohne Ergebnis lässt nichts liegen",
          _leer == {} and _nachher == _vorher, f"{_vorher} -> {_nachher}")
    check("und beim Beenden wird aufgeräumt",
          callable(getattr(_vh, "_aufraeumen", None)))


    # j) Unlesbares ist keine Auskunft. Der Vergleich fiel früher auf die
    #    Rohzeile zurück - eine einzelne HTML-Fehlerseite an dieser
    #    Stelle galt damit als Veränderung und machte aus einer
    #    stehengebliebenen Erfolgsmeldung ein "installiert und aktiv".
    _r = _blicke([
        {"paket": "CUSTOM", "zustand": _E},
        {"paket": "CUSTOM", "zustand": "<html>502 Bad Gateway</html>"},
        {"paket": "CUSTOM", "zustand": _E},
    ], runden=6)
    check("eine Fehlerseite als Zustand beweist nichts",
          set(_r) == {_i2._Beobachter.WARTEN}, f"{_r}")

    # k) Ein Roboter, der die Zustandsstelle gar nicht beantwortet, wurde
    #    nie fertig - obwohl er das Paket nachweislich geholt hatte. Der
    #    Download-Beleg lag hinter einem vorzeitigen Ausstieg.
    _r = _blicke([{"paket": "CUSTOM"}], runden=12, download=True)
    check("ohne lesbaren Zustand trägt der Download den Beweis",
          _i2._Beobachter.WAHRSCHEINLICH in _r, f"{_r}")

    # l) Fällt das Zustandsfeld nach einem Fehlschlag aus, darf der alte
    #    Messwert nicht ein zweites Mal als Bestätigung zählen.
    _r = _blicke([
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"downloading"}'},
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"fail"}'},
        {"paket": "CUSTOM"},
    ], runden=6)
    check("ein ausgefallenes Feld bestätigt keinen Fehlschlag",
          _i2._Beobachter.FEHLER not in _r, f"{_r}")

    # m) Eine dazwischenliegende Fremdmeldung unterbricht die Reihe.
    _r = _blicke([
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"downloading"}'},
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"fail"}'},
        {"paket": "CUSTOM", "zustand": '{"id":"DE","state":"fail"}'},
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"fail"}'},
        {"paket": "CUSTOM", "zustand": '{"id":"CUSTOM","state":"downloading"}'},
    ], runden=4)
    check("'zweimal hintereinander' heißt hintereinander",
          _i2._Beobachter.FEHLER not in _r, f"{_r}")

    # n) Nur die Schreibweise der Kennung ändert sich - das ist keine
    #    Veränderung am Roboter, sondern Groß- und Kleinschreibung.
    _r = _blicke([{"paket": "custom", "zustand": _E},
                  {"paket": "CUSTOM", "zustand": _E}], runden=4)
    check("eine andere Schreibweise ist keine Bewegung",
          set(_r) == {_i2._Beobachter.WARTEN}, f"{_r}")

    # o) Springt die Kennung um, während der Roboter Fehlschlag meldet,
    #    ist das kein Erfolg.
    _r = _blicke([{"paket": "DE", "zustand": '{"state":"downloading"}'},
                  {"paket": "CUSTOM", "zustand": '{"state":"fail"}'}], runden=3)
    check("ein Kennungswechsel bei gemeldetem Fehlschlag zählt nicht",
          _i2._Beobachter.FERTIG not in _r, f"{_r}")

    # p) Der Notausgang muss ebenfalls unterscheiden. Er ist der Weg, den
    #    jemand geht, WEIL etwas kaputt ist - ein grünes "wieder aktiv"
    #    ohne Nachweis wäre hier am schädlichsten.
    class _Nichts(_Falscher):
        def voice_state(self, _d):
            self.abfragen += 1
            return {"paket": "DE", "zustand": '{"id":"DE","state":"success"}'}

    _e = _zurueckholen(_Nichts(), _Pack(), zeit=600)
    check("ein unbelegtes Zurückholen gilt nicht als bestätigt",
          _e.success and not _e.bestaetigt,
          f"success={_e.success} bestätigt={_e.bestaetigt}")
    check("und behauptet keinen Download von hier",
          _e.downloaded is False)
    _ti = (Path(__file__).resolve().parent / "dreamevoice" / "ui"
           / "tab_install.py").read_text(encoding="utf-8")
    check("auch der Notausgang wertet bestätigt aus",
          "outcome.success and outcome.bestaetigt" in _ti)

    # q) Ein Paketname mit Leerzeichen muss sich abholen lassen. Ohne
    #    Dekodierung des Pfades schlug der Download fehl - und wurde dann
    #    auch noch als Firewall-Problem erklärt.
    from dreamevoice.server import PackServer as _PS
    import urllib.parse as _up
    _sv_dir = arbeitsordner()
    _sv_datei = _sv_dir / "Sprachpaket Bayerisch Frau.tar.gz"
    _sv_datei.write_bytes(b"x" * 40_000)
    _sv = _PS(_sv_datei, host_ip="127.0.0.1")
    _url = _sv.start()
    try:
        _kodiert = _url.rsplit("/", 1)[0] + "/" + _up.quote(_sv_datei.name)
        with urllib.request.urlopen(_kodiert, timeout=10) as _r:
            _laenge = len(_r.read())
        check("ein Name mit Leerzeichen lässt sich abholen",
              _laenge == 40_000, f"{_laenge} Bytes")
        check("und zählt als vollständiger Download",
              _sv.wait_for_download(5.0))
    finally:
        _sv.stop()

    # r) Gleichnamige Dateien aus Unterordnern überschreiben sich - dann
    #    darf die Meldung sie nicht mehrfach zählen.
    _dop = arbeitsordner() / "doppelt.zip"
    with _zip.ZipFile(_dop, "w") as _zf:
        for _k in range(3):
            _zf.writestr(f"o{_k}/7.ogg", b"OggS" + bytes(100 + _k))
        _zf.writestr("8.ogg", b"OggS" + bytes(50))
    _ziel = arbeitsordner() / "raus"
    _meld = []
    _imp.extract_archive(_dop, _ziel, log=_meld.append)
    _da = sorted(p.name for p in _ziel.iterdir())
    check("gleichnamige Dateien werden einmal gezählt",
          _da == ["7.ogg", "8.ogg"] and "2 Dateien" in _meld[0],
          f"{_da} / {_meld}")

    # ---------------------------------------------------------------
    section("36. Sich selbst ersetzen, ohne sich zu zerstören")

    from dreamevoice import aktualisierung as _akt

    # a) Versionen zahlenweise vergleichen. Als Text stünde 1.10.0 vor
    #    1.9.0, weil "1" kleiner ist als "9" - dann bekäme niemand mehr
    #    ein Update angeboten.
    for _neu, _alt, _erwartet in (
            ("1.3.0", "1.2.0", True), ("v1.3.0", "1.2.0", True),
            ("1.10.0", "1.9.0", True), ("1.2.0", "1.2.0", False),
            ("1.1.9", "1.2.0", False), ("1.2", "1.2.0", False),
            ("1.2.1", "1.2", True), ("", "1.2.0", False),
            ("Unsinn", "1.2.0", False)):
        check(f"{_neu!r} neuer als {_alt!r}: {_erwartet}",
              _akt.ist_neuer(_neu, _alt) is _erwartet)

    check("die Projektadresse wird zerlegt",
          _akt._repo_pfad("https://github.com/wer/was/") == "wer/was")
    check("eine unbrauchbare Adresse ergibt nichts",
          _akt._repo_pfad("kein-github") == "")

    # b) Ohne Prüfsumme wird nichts getauscht. Eine Programmdatei
    #    ungeprüft über die eigene zu schreiben, wäre genau der Weg,
    #    den man einem Angreifer nicht offenlassen darf.
    _ohne = _akt.Neuerung(version="9.9.9", url="https://x/y", groesse=1,
                          sha256="", seite="https://x")
    check("eine Fassung ohne Prüfsumme gilt als nicht prüfbar",
          not _ohne.pruefbar)
    try:
        _akt.herunterladen(_ohne, ziel=arbeitsordner() / "egal.exe")
        check("ohne Prüfsumme wird nicht geladen", False, "kein Fehler")
    except NetworkError as _exc:
        check("ohne Prüfsumme wird nicht geladen", True)

    # c) Der Tausch: Umbenennen darf man eine laufende Datei, überschreiben
    #    nicht. Geprueft wird an Attrappen, nicht an der echten EXE.
    _ord = arbeitsordner()
    _exe = _ord / "DreameSprachpaket.exe"
    _exe.write_bytes(b"alte Fassung")
    _neu_datei = _ord / "DreameSprachpaket.neu.exe"
    _neu_datei.write_bytes(b"neue Fassung")
    _beiseite = _akt.austauschen(_neu_datei, exe=_exe)
    check("nach dem Tausch steht die neue Fassung am Platz",
          _exe.read_bytes() == b"neue Fassung")
    check("die alte liegt beiseite, nicht im Müll",
          _beiseite.read_bytes() == b"alte Fassung")
    check("und die Zwischendatei ist weg", not _neu_datei.exists())

    # d) Aufräumen kann erst beim nächsten Start passieren - vorher lief
    #    die Datei ja noch.
    check("die Vorgängerfassung wird später weggeräumt",
          _akt.altlasten_entfernen(exe=_exe) == 1 and not _beiseite.exists())

    # e) Schlägt der zweite Schritt fehl, muss der erste zurückgenommen
    #    werden. Es darf keinen Zustand ohne startfähige Programmdatei
    #    geben - das wäre der schlimmste denkbare Ausgang.
    _exe.write_bytes(b"alte Fassung")
    _fehlt = _ord / "gibtsnicht.neu.exe"
    try:
        _akt.austauschen(_fehlt, exe=_exe)
        check("ein fehlender Ersatz bricht ab", False, "kein Fehler")
    except NetworkError:
        check("ein fehlender Ersatz bricht ab", True)
    check("und die alte Fassung steht unverändert am Platz",
          _exe.is_file() and _exe.read_bytes() == b"alte Fassung")

    class _Sperrig(type(_ord)):
        pass

    # Der Fehlschlag beim zweiten Umbenennen, künstlich ausgelöst.
    _exe.write_bytes(b"alte Fassung")
    _ersatz = _ord / "DreameSprachpaket.neu.exe"
    _ersatz.write_bytes(b"neue Fassung")
    _echt_rename = Path.rename

    def _stolpert(selbst, ziel):
        if selbst.name.endswith(".neu.exe"):
            raise OSError("kuenstlich")
        return _echt_rename(selbst, ziel)

    try:
        Path.rename = _stolpert
        try:
            _akt.austauschen(_ersatz, exe=_exe)
            check("ein Fehler beim Tausch wird zurückgenommen", False,
                  "kein Fehler")
        except OSError:
            check("ein Fehler beim Tausch wird zurückgenommen", True)
    finally:
        Path.rename = _echt_rename
    check("danach ist die alte Fassung wieder da",
          _exe.is_file() and _exe.read_bytes() == b"alte Fassung")

    # f) Ein Ordner ohne Schreibrecht wird erkannt, bevor irgendetwas
    #    geladen wird.
    check("ein beschreibbarer Ordner wird erkannt",
          _akt.ordner_beschreibbar(_exe))

    # g) Die Prüfsumme kommt aus dem Release, nicht aus der Datei selbst.
    _rel = {"body": "Prüfsumme: " + "a" * 64, "assets": []}
    check("die Summe aus dem digest-Feld hat Vorrang",
          _akt._pruefsumme_finden(_rel, {"digest": "sha256:" + "b" * 64})
          == "b" * 64)
    check("sonst wird der Begleittext genommen",
          _akt._pruefsumme_finden(_rel, {}) == "a" * 64)
    check("ohne beides bleibt sie leer",
          _akt._pruefsumme_finden({"body": "", "assets": []}, {}) == "")

    # h) Der Schalter ist ab Werk aus. Die Abfrage geht an GitHub und
    #    verrät, dass hier jemand diese App benutzt - das gehört
    #    gefragt, nicht angenommen.
    check("die Suche beim Start ist ab Werk ausgeschaltet",
          _cfgmod.DEFAULTS["update_pruefen"] is False)
    for _feld in ("update_pruefen", "update_zuletzt", "update_uebersprungen"):
        check(f"{_feld} ist vorgesehen", _feld in _cfgmod.DEFAULTS)

    # Erreichbar muss das Ganze auch sein. Bis Version 1.3.0 lag es auf
    # der Seite "Verbindung", unter Konto und Roboterliste - dort sucht
    # niemand nach einer Aktualisierung, und der Schalter "beim Start
    # nachsehen" war damit ebenso versteckt.
    _uiord = Path(__file__).resolve().parent / "dreamevoice" / "ui"
    _appq = (_uiord / "app.py").read_text(encoding="utf-8-sig")
    check("die Kopfleiste hat einen Knopf 'Aktualisierung'",
          'text="Aktualisierung"' in _appq and "_show_update" in _appq)

    _fensterdatei = _uiord / "fenster_update.py"
    check("es gibt ein eigenes Aktualisierungsfenster", _fensterdatei.is_file())
    if _fensterdatei.is_file():
        _fq = _fensterdatei.read_text(encoding="utf-8-sig")
        check("der Schalter steht mit im Fenster",
              'config["update_pruefen"]' in _fq and "Checkbutton" in _fq)
        for _teil in ("pruefen()", "herunterladen", "austauschen",
                      "neu_starten"):
            check(f"das Fenster kann '{_teil}'", _teil in _fq)

    # Und die Kette darf es nur EINMAL geben - zwei Fassungen derselben
    # Download-und-Austausch-Logik laufen sonst auseinander.
    _connq = (_uiord / "tab_connect.py").read_text(encoding="utf-8-sig")
    for _teil in ("aktualisierung.herunterladen", "aktualisierung.austauschen"):
        check(f"'{_teil}' steht nicht mehr doppelt in tab_connect",
              _teil not in _connq)


    # ---------------------------------------------------------------
    section("37. Seiten entstehen erst, wenn man sie braucht")

    # Vier der sechs Seiten sieht ein Benutzer nie an. Sie beim Start
    # mitzubauen kostete über eine Sekunde und einen blockierenden
    # PowerShell-Aufruf für die Windows-Stimmen.
    if not _tk_da:
        uebersprungen("Seiten entstehen erst bei Bedarf",
                      "Tkinter oder Anzeige fehlt auf diesem Rechner")
    else:
        _f = None
        try:
            _f = MainWindow()
            _f.withdraw()
            _f.update_idletasks()
            _roh = _f.shell._eintraege
            _sofort = [k for k, e in _roh.items() if e.seite is not None]
            _spaeter = [k for k, e in _roh.items() if e.seite is None]
            check("nur die beiden Hauptseiten entstehen sofort",
                  sorted(_sofort) == ["start", "stimme"], f"{sorted(_sofort)}")
            check("die vier unter 'Erweitert' warten",
                  sorted(_spaeter) == ["ansagen", "aufspielen", "eigene",
                                       "verbindung"], f"{sorted(_spaeter)}")

            # Der Zugriff über die Eigenschaft baut sie - so bleibt jeder
            # bisherige Aufruf gültig.
            check("der Zugriff baut die Seite", _f.tab_store is not None)
            check("und sie ist danach gemerkt",
                  _roh["eigene"].seite is _f.tab_store)

            # Jede Seite muss sich auch wirklich zeigen lassen.
            for _key in ("eigene", "ansagen", "aufspielen", "verbindung",
                         "stimme", "start"):
                _f.shell.show(_key)
                _f.update_idletasks()
                check(f"Seite '{_key}' lässt sich öffnen",
                      _f.shell.current == _key
                      and _roh[_key].seite is not None)

            # Die Windows-Stimmen werden erst beim Öffnen aufgezählt.
            check("die Stimmenliste entsteht erst beim Öffnen",
                  getattr(_f.tab_store, "_stimmen_geladen", None) is True)
        finally:
            if _f is not None:
                _f.destroy()


    # ---------------------------------------------------------------
    section("38. Die Doku behauptet nichts Veraltetes")

    # Die Doku ist still veraltet, während die App sich änderte: 13
    # falsche Stellen in der README, 7 im Release-Text, vier
    # Beipackzettel mit Anleitungen für Reiter, die es nicht mehr gibt.
    # Nichts davon fällt auf, bis es jemand liest und dem Falschen folgt.
    _wurzel = Path(__file__).resolve().parent
    _texte = {}
    for _p in [_wurzel / "README.md", _wurzel / "RELEASE.md"] \
            + sorted((_wurzel / "docs").glob("*.md")):
        if _p.is_file():
            _texte[_p.name] = _p.read_text(encoding="utf-8")
    check("die Doku ist vorhanden", len(_texte) >= 7, f"{sorted(_texte)}")

    # a0) Aus der App heraus muss man sie auch finden. Die README wurde
    #     von 850 auf 232 Zeilen gekürzt und alles Ausführliche nach
    #     docs/ ausgelagert - wer nur die EXE hat, sah davon nichts.
    from dreamevoice import anleitungen as _anl

    _heim = _anl.ordner()
    check("die App findet den Ordner mit den Anleitungen", _heim is not None,
          f"{_heim}")
    _gelistet = {a.datei for a in _anl.ANLEITUNGEN}
    _vorhanden = {p.name for p in (_wurzel / "docs").glob("*.md")}
    check("jede verlinkte Anleitung gibt es wirklich",
          not (_gelistet - _vorhanden), f"fehlt: {sorted(_gelistet - _vorhanden)}")
    # Andersherum ebenso: Eine neue Anleitung, die niemand verlinkt,
    # ist so unsichtbar wie gar keine.
    check("und jede Anleitung ist auch verlinkt",
          not (_vorhanden - _gelistet),
          f"nicht verlinkt: {sorted(_vorhanden - _gelistet)}")
    for _a in _anl.ANLEITUNGEN:
        check(f"'{_a.datei}' ist erreichbar",
              _anl.verfuegbar(_a.datei) == "oertlich",
              _anl.verfuegbar(_a.datei))
        check(f"'{_a.datei}' hat eine Netzadresse im Projekt",
              _anl.netz_adresse(_a.datei).startswith("https://github.com/"))

    # Über diesen Weg darf nichts außerhalb von docs/ geöffnet
    # werden - auch wenn der Aufrufer aus der eigenen Liste kommt.
    for _boese in ("../main.py", r"..\main.py", "docs/Technik.md",
                   "/etc/passwd", ""):
        check(f"{_boese!r} wird nicht als Anleitung geöffnet",
              _anl.pfad(_boese) is None)

    # Und die EXE muss sie mitnehmen, sonst greift nur der Umweg
    # über den Browser.
    _spec = (_wurzel / "DreameSprachpaket.spec")
    if _spec.is_file():
        _sp = _spec.read_text(encoding="utf-8")
        check("die EXE nimmt die Anleitungen mit", '("docs", "docs")' in _sp)

    # Das Hilfe-Fenster muss sie auch wirklich anzeigen.
    _ui = (_wurzel / "dreamevoice" / "ui" / "app.py").read_text(
        encoding="utf-8-sig")
    check("das Hilfe-Fenster verlinkt die Anleitungen",
          "_bau_anleitungen" in _ui and "anleitungen.ANLEITUNGEN" in _ui)

    # a) Die Reiter gibt es seit der Seitenleiste nicht mehr.
    import re as _re
    _reiter = _re.compile(r"\bTab [1-4]\b")
    for _name, _text in _texte.items():
        _t = _reiter.findall(_text)
        check(f"{_name} spricht nicht mehr von Reitern", not _t, f"{_t}")

    # b) Eine Kennung lässt sich nicht mehr wählen - eine Anleitung
    #    dazu wäre nicht ausführbar.
    for _name, _text in _texte.items():
        check(f"{_name} rat nicht zur Kennung DE",
              "Kennung `DE`" not in _text and "Kennung 'DE'" not in _text)

    # c) Die Zahl der Stimmen muss zum Katalog passen.
    _stimmen = len(_dp.KATALOG)
    check("die README nennt die Stimmen nicht als 'vier Dialekte'",
          "vier Dialekte" not in _texte.get("README.md", ""))
    check(f"der Katalog führt {_stimmen} Stimmen", _stimmen == 5, f"{_stimmen}")

    # d) Der Release-Text muss zur Version passen. Sonst steht auf der
    #    Projektseite eine andere Zahl als im Programmfenster.
    _rel = _texte.get("RELEASE.md", "")
    from dreamevoice import __version__ as _ver
    check("der Release-Text nennt die aktuelle Version",
          f"v{_ver}" in _rel or f"## v{_ver}" in _rel, _ver)

    # d2) Und die EXE muss dieselbe Zahl tragen. Beim Bau von 1.3.0
    #     stand in version_info.txt noch 1.2.0 - Windows hätte die
    #     neue Datei als alte Fassung ausgewiesen, und ein
    #     Virenscanner wertet eine falsche Versionsangabe als
    #     zusätzliches Verdachtsmoment.
    _vi = _wurzel / "version_info.txt"
    if not _vi.is_file():
        uebersprungen("die EXE trägt dieselbe Version", "version_info.txt fehlt")
    else:
        _vt = _vi.read_text(encoding="utf-8")
        _teile = tuple(int(x) for x in _ver.split("."))
        _erwartet = _teile + (0,) * (4 - len(_teile))
        _zahl = ", ".join(str(x) for x in _erwartet)
        _punkt = ".".join(str(x) for x in _erwartet)
        check("die EXE trägt dieselbe Version wie das Programm",
              f"filevers=({_zahl})" in _vt and f"prodvers=({_zahl})" in _vt,
              f"erwartet ({_zahl})")
        check("auch als Text in den Dateieigenschaften",
              _vt.count(f"'{_punkt}'") >= 2, f"erwartet '{_punkt}'")

    # e) Verweise auf ausgelagerte Dateien müssen existieren.
    _fehlend = []
    for _ziel in _re.findall(r"\]\((docs/[A-Za-z\-]+\.md)\)",
                             _texte.get("README.md", "")):
        if not (_wurzel / _ziel).is_file():
            _fehlend.append(_ziel)
    check("alle Verweise der README zeigen auf vorhandene Dateien",
          not _fehlend, f"{_fehlend}")

    # e2) Dasselbe für alle übrigen Texte, und für jede Art von Ziel.
    #     In `docs/Entwicklung.md` stand ein Verweis auf
    #     `dreamevoice/__init__.py` - relativ zu docs/ gelesen also auf
    #     `docs/dreamevoice/__init__.py`. Auf GitHub war das ein 404,
    #     und niemandem fiel es auf, weil der Text daneben stimmte.
    #
    #     Verweise, die aus dem Projekt HINAUS zeigen, bleiben außen vor:
    #     `../../releases/latest` ist GitHubs Kurzschrift für die
    #     Release-Seite und hat auf der Festplatte kein Gegenstück.
    _tot = []
    for _p in ([_wurzel / "README.md", _wurzel / "RELEASE.md",
                _wurzel / "CHANGELOG.md", _wurzel / "VEROEFFENTLICHEN.md"]
               + sorted((_wurzel / "docs").glob("*.md"))):
        if not _p.is_file():
            continue
        for _z in _re.findall(r"\[[^\]]*\]\(([^)]+)\)",
                              _p.read_text(encoding="utf-8")):
            if _z.startswith(("http://", "https://", "#", "mailto:")):
                continue
            _ziel = (_p.parent / _z.split("#")[0]).resolve()
            try:
                _ziel.relative_to(_wurzel)
            except ValueError:
                continue          # zeigt aus dem Projekt heraus
            if not _ziel.exists():
                _tot.append(f"{_p.name}: {_z}")
    check("kein Verweis in der Doku zeigt ins Leere", not _tot, f"{_tot}")

    # f) Die Startseite muss kurz bleiben. Der Forumsnutzer stieg genau
    #    daran aus: "Denke dein Text ist etwas viel zum Durchlesen."
    _woerter = len(_texte.get("README.md", "").split())
    check("die README bleibt unter 2000 Wörtern",
          _woerter < 2000, f"{_woerter} Wörter, rund {_woerter // 200} Minuten")

    # g) Die Beipackzettel in den Archiven zählen mit. Sie wandern zu
    #    Leuten, die die App gar nicht haben.
    #
    #    Geprüft wird JEDES Archiv, nicht nur "*-Aufnahmen.zip". Genau
    #    daran ist es vorbeigegangen: In "Bayerisch-zum-Anhoeren.zip"
    #    stand die Anleitung noch über "Tab 1" bis "Tab 4", während die
    #    fünf Aufnahmen-Archive längst nachgezogen waren. Der Filter im
    #    Dateinamen hat den Fehler zugedeckt.
    #
    #    Ebenso die entpackten Ordner daneben: Wer sie weitergibt, gibt
    #    genau diesen Text weiter.
    _pakete = _wurzel / "Fertige Pakete"
    _archive = sorted(_pakete.glob("*.zip"))
    _lose = sorted(_p for _p in _pakete.rglob("*.txt"))
    if not _archive and not _lose:
        uebersprungen("die Beipackzettel sind aktuell",
                      "in diesem Klon liegen keine fertigen Pakete")
    else:
        # Eine Anleitung, die das Aufspielen erklärt, muss die heutigen
        # Seitennamen nennen. Reine Erklärtexte (der Hörvergleich) nicht.
        def _pruefe_zettel(woher: str, dateien: dict) -> None:
            _lm = dateien.get("LIESMICH.txt", "")
            if _lm and "SO SPIELST DU SIE AUF DEINEN ROBOTER" in _lm:
                check(f"{woher}: die Anleitung ist aktuell",
                      not _reiter.search(_lm) and "Fertige Stimmen" in _lm,
                      f"{_reiter.findall(_lm)}")
            for _n, _t in dateien.items():
                check(f"{woher}: {_n} spricht nicht von Reitern",
                      not _reiter.search(_t), f"{_reiter.findall(_t)}")
            # Ein kyrillisches a sieht aus wie ein lateinisches, macht das
            # Wort aber unsuchbar - und in einer Lizenzdatei sieht es nach
            # maschinell erzeugtem Text aus.
            #
            # Als Codepunkt gemeldet, nicht als Zeichen: Die Konsole hier
            # kann kein Kyrillisch, und ein Absturz der Meldung hätte den
            # ganzen Abschnitt verschluckt - der Fund wäre so gerade in
            # dem Moment untergegangen, in dem es einen gab.
            _fremd = sorted({ord(_c) for _t in dateien.values() for _c in _t
                             if 0x400 <= ord(_c) <= 0x4FF})
            check(f"{woher}: keine kyrillischen Buchstaben im Text",
                  not _fremd, ", ".join(f"U+{_o:04X}" for _o in _fremd))

        for _a in _archive:
            with _zip.ZipFile(_a) as _zf:
                _dateien = {Path(n).name:
                            _zf.read(n).decode("utf-8-sig", "replace")
                            for n in _zf.namelist() if n.endswith(".txt")}
            _pruefe_zettel(_a.name, _dateien)
            if _a.name.endswith("-Aufnahmen.zip"):
                check(f"{_a.name}: eine Anleitung liegt bei",
                      "LIESMICH.txt" in _dateien)

        _daneben = {}
        for _p in _lose:
            _daneben.setdefault(_p.parent, {})[_p.name] = _p.read_text(
                encoding="utf-8-sig", errors="replace")
        for _ordner, _dateien in sorted(_daneben.items()):
            _pruefe_zettel(_ordner.name, _dateien)


    # ---------------------------------------------------------------
    section("39. Roboterwechsel und Notstand beim Austausch")

    from dreamevoice.ui.state import AppState as _AppState

    # a) Beim Roboterwechsel muss alles weg, was zum alten Modell gehört.
    #    Das stand in "Einzelne Ansagen" - seit die Seiten erst beim
    #    Öffnen entstehen, lief es bei den meisten Benutzern NIE. Folge:
    #    Nach einem Gerätewechsel behielt die App das Originalpaket des
    #    vorigen Modells und hätte dessen Paket verschickt.
    _st = _AppState()
    _st.base_pack_path = Path("irgendwo/altes_modell.tar.gz")
    _st.official_packs = ["DE", "EN"]
    _st.notify("device_changed")
    check("ein Roboterwechsel verwirft das alte Originalpaket",
          _st.base_pack_path is None, f"{_st.base_pack_path}")
    check("und die Sprachliste des alten Modells",
          _st.official_packs == [], f"{_st.official_packs}")
    check("das passiert ohne jede gebaute Seite", True)

    _sq = (Path(__file__).resolve().parent / "dreamevoice" / "ui"
           / "state.py").read_text(encoding="utf-8")
    check("das Verwerfen sitzt in AppState, nicht in einer Seite",
          "_geraetestand_verwerfen" in _sq)

    # b) Der Notstand: Der Tausch scheitert UND die Rücknahme auch.
    #    Früher behauptete der Docstring, das könne nicht vorkommen -
    #    und die Fehlermeldung sagte "es wurde nichts ausgetauscht",
    #    während die Programmdatei tatsächlich verschwunden war.
    _ord = arbeitsordner()
    _exe = _ord / "DreameSprachpaket.exe"
    _exe.write_bytes(b"alte Fassung")
    _ersatz = _ord / "DreameSprachpaket.neu.exe"
    _ersatz.write_bytes(b"neue Fassung")

    _echt_rename = Path.rename
    _zaehler = {"n": 0}

    def _erst_gut_dann_kaputt(selbst, ziel):
        """Der erste Schritt gelingt, danach geht alles schief.

        Genau so entsteht der Notstand: Die Programmdatei ist schon
        beiseitegelegt, die neue kommt nicht an ihren Platz, und die
        Rücknahme scheitert ebenfalls. Scheitert dagegen schon der
        erste Schritt, ist nichts verschoben - das ist ein
        gewöhnlicher Fehler, kein Notstand.
        """
        _zaehler["n"] += 1
        if _zaehler["n"] == 1:
            return _echt_rename(selbst, ziel)
        raise OSError("kuenstlich")

    try:
        Path.rename = _erst_gut_dann_kaputt
        try:
            _akt.austauschen(_ersatz, exe=_exe)
            check("ein Notstand wird als solcher gemeldet", False, "kein Fehler")
        except _akt.TauschNotstand as _exc:
            check("ein Notstand wird als solcher gemeldet", True)
            _text = f"{getattr(_exc, 'message', '')} {getattr(_exc, 'hint', '')}"
            check("die Meldung sagt, dass keine Datei am Platz liegt",
                  "KEINE startfähige" in _text, _text[:80])
            check("und wie man sie zurückbekommt",
                  ".alt.exe" in _text and "um." in _text)
        except OSError:
            check("ein Notstand wird als solcher gemeldet", False,
                  "roher OSError statt TauschNotstand")
    finally:
        Path.rename = _echt_rename

    # c) Eine gesperrte Vorgängerdatei darf keine Aktualisierung
    #    dauerhaft blockieren, ohne zu sagen warum.
    _exe.write_bytes(b"alte Fassung")
    _alt_datei = _ord / "DreameSprachpaket.alt.exe"
    _alt_datei.write_bytes(b"noch aelter")
    _echt_unlink = Path.unlink

    def _gesperrt(selbst, missing_ok=False):
        if selbst.name.endswith(".alt.exe"):
            raise OSError(32, "in Benutzung")
        return _echt_unlink(selbst, missing_ok=missing_ok)

    try:
        Path.unlink = _gesperrt
        try:
            _akt.austauschen(_ersatz if _ersatz.is_file() else _exe, exe=_exe)
            check("eine gesperrte Vorgängerdatei wird erklärt", False,
                  "kein Fehler")
        except NetworkError as _exc:
            check("eine gesperrte Vorgängerdatei wird erklärt",
                  "beiseiteräumen" in getattr(_exc, "message", ""),
                  getattr(_exc, "message", ""))
    finally:
        Path.unlink = _echt_unlink
    check("und die Programmdatei bleibt dabei unangetastet",
          _exe.is_file() and _exe.read_bytes() == b"alte Fassung")

    # d) Aufgeräumt wird nur das Eigene. Die App liegt oft im
    #    Download-Ordner, wo alles Mögliche danebenliegt.
    _fremd = _ord / "MeinBackup.alt.exe"
    _fremd.write_bytes(b"gehoert jemand anderem")
    _eigen = _ord / "DreameSprachpaket.alt.exe"
    _eigen.write_bytes(b"unsere alte")
    _akt.altlasten_entfernen(exe=_exe)
    check("die eigene Vorgängerfassung wird geräumt", not _eigen.exists())
    check("fremde Dateien bleiben unangetastet", _fremd.is_file())

    # e) Die Prüfsumme aus dem Begleittext muss zur Programmdatei
    #    gehören. Sonst gewinnt die erste beste Zeichenfolge - etwa die
    #    eines anderen Anhangs - und jede Aktualisierung scheitert.
    _rel = {"assets": [], "body": (
        "Dialektpakete.zip: " + "b" * 64 + "\n"
        "DreameSprachpaket.exe: " + "a" * 64 + "\n")}
    check("die Summe der Programmdatei wird genommen",
          _akt._pruefsumme_finden(_rel, {}) == "a" * 64)
    _mehrdeutig = {"assets": [], "body": "x " + "b" * 64 + "\ny " + "c" * 64}
    check("mehrere namenlose Summen gelten als unklar",
          _akt._pruefsumme_finden(_mehrdeutig, {}) == "")
    _einzeln = {"assets": [], "body": "Prüfsumme: " + "d" * 64}
    check("eine einzelne namenlose Summe gilt",
          _akt._pruefsumme_finden(_einzeln, {}) == "d" * 64)


    # ---------------------------------------------------------------
    section("40. Was in der App steht, muss auch stimmen")

    # Der Doku-Test prüft die .md-Dateien. Die Texte IN der App - Hilfe,
    # Über-Fenster, Beschriftungen - waren nie dabei. Genau dort standen
    # dann eine Anleitung für ein entferntes Eingabefeld, eine
    # Überschrift mit "Tab 4" und zwei widersprechende Zahlen zum
    # ElevenLabs-Kontingent. Ein Beta-Tester fand alle drei in zehn
    # Minuten; kein Codeprüfer hatte sie bemerkt.
    _ui = Path(__file__).resolve().parent / "dreamevoice" / "ui"
    _quellen_ui = {p.name: p.read_text(encoding="utf-8-sig")
                   for p in sorted(_ui.glob("*.py"))}
    check("die Oberfläche ist lesbar", len(_quellen_ui) >= 8,
          f"{len(_quellen_ui)} Dateien")

    import ast as _ast
    import re as _re2
    # Nicht nur "Tab 1" bis "Tab 4": Die Seitenleiste hat die Reiter
    # abgelöst, aber drei Meldungen schickten den Nutzer weiter zu
    # "Tab 'Upload & Installation'" und "Tab 'Sprachpaket erstellen'" -
    # Namen, die es nicht mehr gibt. Das alte Muster fing genau die
    # nicht, weil dort keine Ziffer steht. Bei einer der drei war es
    # die Abschlussmeldung nach dem Herunterladen, also genau der
    # Moment, in dem der Nutzer weitergehen soll.
    _reiter2 = _re2.compile(r"\bTAB [1-4]\b|\bTab [1-4]\b"
                            r"|\bTabs? ['\"]|\bReiter ['\"]")

    def _sichtbare_texte(quelle: str) -> list:
        """Alle Zeichenketten, die beim Nutzer ankommen können.

        Kommentare und Docstrings gehören nicht dazu - dort steht die
        Begründung, warum es die Reiter nicht mehr gibt, und die soll
        stehenbleiben. Ein erster Anlauf verglich schlicht alle Zeilen
        und schlug genau daran an.
        """
        baum = _ast.parse(quelle)
        docstrings = set()
        for knoten in _ast.walk(baum):
            if isinstance(knoten, (_ast.Module, _ast.ClassDef,
                                   _ast.FunctionDef, _ast.AsyncFunctionDef)):
                erst = (knoten.body or [None])[0]
                if (isinstance(erst, _ast.Expr)
                        and isinstance(erst.value, _ast.Constant)
                        and isinstance(erst.value.value, str)):
                    docstrings.add(id(erst.value))
        return [k.value for k in _ast.walk(baum)
                if isinstance(k, _ast.Constant)
                and isinstance(k.value, str)
                and id(k) not in docstrings]

    _sichtbar_je_datei = {n: _sichtbare_texte(q)
                          for n, q in _quellen_ui.items()}
    for _name, _texte in _sichtbar_je_datei.items():
        _t = [x for x in _texte if _reiter2.search(x)]
        check(f"{_name} zeigt dem Nutzer keine Reiter", not _t, f"{_t[:1]}")

    # Die abgeschafften Seitennamen dürfen nirgends mehr auftauchen -
    # weder mit noch ohne das Wort "Tab" davor.
    _alt_ui = "\n".join("\n".join(t) for t in _sichtbar_je_datei.values())
    for _weg in ("Upload & Installation", "Sprachpaket erstellen"):
        check(f"der abgeschaffte Name '{_weg}' steht nirgends mehr",
              _weg not in _alt_ui)

    # Eine Anleitung zu einer Kennung, die niemand mehr eingeben kann.
    for _name, _texte in _sichtbar_je_datei.items():
        _t = [x for x in _texte if "Kennung" in x and "DE" in x
              and "installier" in x.lower()]
        check(f"{_name} rat nicht zur Kennung DE", not _t, f"{_t[:1]}")

    # Zahlen zum ElevenLabs-Kontingent dürfen sich nicht widersprechen.
    # Gemessen sind es 22693 Zeichen für ein volles Dialektpaket.
    _alles_ui = "\n".join("\n".join(t)
                          for t in _sichtbar_je_datei.values())
    check("keine falsche Kontingentangabe von 7.500",
          "7.500" not in _alles_ui and "braucht rund 7500" not in _alles_ui)
    check("die gemessene Zahl steht drin",
          "22.7" in _alles_ui or "22693" in _alles_ui or "22.693" in _alles_ui)

    # Jedes Navigationsziel muss es geben. Der Knopf "Originalstimme
    # zurück" zeigte auf eine Seite namens "original" - die gab es nie,
    # und ein Klick tat schlicht nichts. Ausgerechnet der Knopf, den
    # jemand drückt, wenn ihm die neue Stimme auf die Nerven geht.
    _ziele = set()
    for _text in _quellen_ui.values():
        _ziele.update(_re2.findall(r'gehe_zu\("([a-z_]+)"\)', _text))
    check("es gibt Navigationsziele zu prüfen", bool(_ziele), f"{_ziele}")

    _start_q = _quellen_ui.get("page_start.py", "")
    _stelle = _start_q.find('text="Originalstimme zurück"')
    check("der Knopf 'Originalstimme zurück' steht in der Startseite",
          _stelle >= 0)
    check("er ruft _zum_notausgang statt nur die Seite zu wechseln",
          "_zum_notausgang" in _start_q[_stelle:_stelle + 400],
          _start_q[_stelle:_stelle + 200])

    if not _tk_da:
        uebersprungen("jedes Navigationsziel existiert",
                      "Tkinter oder Anzeige fehlt auf diesem Rechner")
    else:
        _f2 = None
        try:
            _f2 = MainWindow()
            _f2.withdraw()
            _f2.update_idletasks()
            _bekannt = set(_f2.shell._eintraege)
            _fehlend = sorted(_ziele - _bekannt)
            check("jedes Navigationsziel existiert wirklich",
                  not _fehlend, f"unbekannt: {_fehlend}")

            # Und die Knöpfe müssen auch tatsächlich irgendwo landen.
            for _ziel in sorted(_ziele):
                _f2.shell.show(_ziel)
                _f2.update_idletasks()
                check(f"der Weg nach '{_ziel}' führt hin",
                      _f2.shell.current == _ziel, _f2.shell.current)

            # Ankommen genügt nicht. "Originalstimme zurück" landete
            # oben auf einer langen Seite - und der auffälligste Knopf
            # dort heißt "Sprachpaket auf Roboter installieren". Wer
            # seine Stimme loswerden will, darf da nicht landen.
            _start = _f2.shell.seite("start")
            _auf = _f2.tab_install
            check("die Startseite kennt den Weg zum Notausgang",
                  callable(getattr(_start, "_zum_notausgang", None)))
            check("die Aufspielseite kann zum Notausgang rollen",
                  callable(getattr(_auf, "zeige_notausgang", None)))
            check("und weiß, wo ihr Notausgang steht",
                  getattr(_auf, "karte_notausgang", None) is not None)
            _start._zum_notausgang()
            _f2.update()
            check("der Notausgangsknopf wechselt auf die richtige Seite",
                  _f2.shell.current == "aufspielen", _f2.shell.current)
        finally:
            if _f2 is not None:
                _f2.destroy()

    # Das Bild in der README muss die App zeigen, nicht das Symbol. Ein
    # Interessent entscheidet daran, ob er 90 MB herunterlädt.
    _bild = Path(__file__).resolve().parent / "app-vorschau.png"
    if not _bild.is_file():
        uebersprungen("die Vorschau zeigt die App", "app-vorschau.png fehlt")
    else:
        try:
            from PIL import Image as _Image
            with _Image.open(_bild) as _im:
                _breit, _hoch = _im.size
            check("die Vorschau ist ein Fensterbild, kein Symbol",
                  _breit >= 800 and _hoch >= 500, f"{_breit}x{_hoch}")
        except ImportError:                              # pragma: no cover
            uebersprungen("die Vorschau zeigt die App", "Pillow fehlt")

    # ==================================================================
    section("41. Kaputte Archive müssen verständlich scheitern")
    # ==================================================================
    # Ein Beta-Tester brach den Download eines Zips ab und bekam fünf
    # Zeilen englischer tar-Fehler über eine Datei, die unverkennbar
    # ein Zip ist - samt der Auskunft, erwartet werde ein zip-Archiv.
    # Ein kennwortgeschütztes Zip galt als "beschädigt". Beides
    # schickt den Nutzer an die falsche Stelle.
    import zipfile
    from dreamevoice.importer import archiv_art as _art
    from dreamevoice.importer import extract_archive

    _ordner = arbeitsordner("archive")
    _ton = _ordner / "7.ogg"
    _ton.write_bytes(b"OggS" + b"\x00" * 400)

    _ganz = _ordner / "ganz.zip"
    with zipfile.ZipFile(_ganz, "w", zipfile.ZIP_DEFLATED) as _zf:
        for _n in (7, 8, 9):
            _zf.writestr(f"{_n}.ogg", _ton.read_bytes())
    _roh = _ganz.read_bytes()

    check("ein Zip wird am Dateianfang erkannt", _art(_ganz) == "zip")
    _halb = _ordner / "halb.zip"
    _halb.write_bytes(_roh[: len(_roh) // 2])
    check("auch ohne Inhaltsverzeichnis am Ende", _art(_halb) == "zip",
          _art(_halb))

    _leer = _ordner / "leer.zip"
    _leer.write_bytes(b"")
    check("eine leere Datei wird als leer erkannt", _art(_leer) == "leer")

    _html = _ordner / "fehlerseite.tar.gz"
    _html.write_bytes(b"<!DOCTYPE html><html>404 Not Found</html>")
    check("eine Fehlerseite ist kein Archiv", _art(_html) == "unbekannt")

    _rar = _ordner / "paket.rar"
    _rar.write_bytes(b"Rar!\x1a\x07\x00" + b"\x00" * 64)
    check("ein RAR wird als RAR erkannt", _art(_rar) == "rar")

    def _meldung(pfad):
        """Was der Nutzer zu sehen bekäme - oder None, wenn es klappt."""
        _ziel = _ordner / "raus"
        shutil.rmtree(_ziel, ignore_errors=True)
        try:
            extract_archive(pfad, _ziel)
            return None
        except PackError as exc:
            return f"{exc.message}\n{exc.hint}"

    _m = _meldung(_halb)
    check("das halbe Zip heißt 'unvollständig', nicht 'kein Archiv'",
          _m is not None and "unvollständig" in _m and "Zip" in _m, str(_m)[:120])
    check("und niemand wird nach einem tar.gz gefragt",
          _m is not None and "tar.gz" not in _m, str(_m)[:160])

    # Englische Originalfehler dürfen die Meldung nicht tragen. Als
    # angehängter technischer Grund sind sie in Ordnung - als
    # Hauptaussage nicht.
    for _wort in ("not a gzip file", "Bad magic number", "File is not",
                  "unexpected end of data"):
        check(f"kein englischer tar-Fehler in der Meldung ({_wort[:14]})",
              _m is not None and _wort not in _m)

    _kennwort = _ordner / "kennwort.zip"
    _daten = bytearray(_roh)
    for _magie, _abstand in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        _i = 0
        while True:
            _i = _daten.find(_magie, _i)
            if _i < 0:
                break
            _daten[_i + _abstand] |= 0x01
            _i += 4
    _kennwort.write_bytes(bytes(_daten))
    _m = _meldung(_kennwort)
    check("ein kennwortgeschütztes Zip wird als solches benannt",
          _m is not None and "Kennwort" in _m, str(_m)[:120])
    check("und nicht als beschädigt ausgegeben",
          _m is not None and "beschädigt" not in _m, str(_m)[:160])

    _m = _meldung(_leer)
    check("eine leere Datei heißt leer", _m is not None and "leer" in _m.lower(),
          str(_m)[:120])

    _m = _meldung(_ton)
    check("eine einzelne Tondatei wird erklärt, nicht abgewiesen",
          _m is not None and "kein Archiv" in _m and "Ordner" in _m,
          str(_m)[:160])

    _m = _meldung(_rar)
    check("ein RAR bekommt einen Rat statt eines Fehlercodes",
          _m is not None and "RAR" in _m and "ZIP" in _m, str(_m)[:160])

    _tgz = _ordner / "ganz.tar.gz"
    with tarfile.open(_tgz, "w:gz") as _tf:
        _tf.add(_ton, arcname="7.ogg")
    _roh2 = _tgz.read_bytes()
    _halbtgz = _ordner / "halb.tar.gz"
    _halbtgz.write_bytes(_roh2[: len(_roh2) - 40])
    _m = _meldung(_halbtgz)
    check("ein abgeschnittenes tar.gz heißt unvollständig",
          _m is not None and "unvollständig" in _m, str(_m)[:120])

    # Und das Wichtigste: heile Archive müssen weiterhin durchgehen.
    check("das heile Zip wird trotzdem entpackt", _meldung(_ganz) is None)
    check("das heile tar.gz auch", _meldung(_tgz) is None)


    # ==================================================================
    section("42. Der Katalog, wie er wirklich aussieht")
    # ==================================================================
    # Die Erlaubnisliste in official.py kannte den echten
    # Auslieferungsserver nicht: oss.iot.dreame.life fehlte, nur
    # dreame.tech stand drin. Die App verwarf damit jeden einzelnen
    # Katalogeintrag - komplett unbrauchbar, und zwar erst am Gerät
    # bemerkt. Grün blieb die Suite, weil ihre Prüfdaten dieselbe
    # falsche Annahme trugen wie der Code.
    #
    # Die Werte unten sind deshalb GEMESSEN, nicht erfunden: am
    # 30.08.2026 über neun Modelle von Dreame, MOVA und Trouver.
    # 143 Einträge kamen von oss.iot.dreame.life, 38 von
    # oss.iot.dreame.tech, alle über https.
    _ECHT = {
        "id": "DE",
        "size": 11094134,
        "md5sum": "0ede9316f4dbb2f4d1e5a0e0e59d3a71",
        "download": ("https://oss.iot.dreame.life/dreame-product/"
                     "resources/0ede9316.tar.gz"),
        "listen": "https://oss.iot.dreame.life/dreame-product/probe.mp3",
        "name": {"default": "Deutsch", "de": "Deutsch"},
    }

    _e = official.VoicePackInfo(_ECHT)
    check("ein echter Katalogeintrag wird angenommen", _e.brauchbar,
          _e.einwand)
    check("und trägt keinen Einwand", _e.einwand == "", _e.einwand)

    # Genau das war der zweite Fehler: Die eingeschobene Eigenschaft
    # hatte die letzten Zeilen von __init__ hinter ein return gedrängt.
    # name und preview_url wurden nie gesetzt, label warf eine
    # AttributeError - aufgefallen wäre es erst, wenn ein Eintrag
    # durchkommt, und es kam ja keiner durch.
    check("der Anzeigename wird gesetzt", _e.name == "Deutsch", _e.name)
    check("die Beschriftung lässt sich bilden", _e.label == "Deutsch (DE)",
          _e.label)
    check("die Hörprobe wird übernommen", bool(_e.preview_url),
          _e.preview_url)

    for _wirt in ("oss.iot.dreame.life", "oss.iot.dreame.tech"):
        check(f"der gemessene Server {_wirt} ist erlaubt",
              official.adresse_erlaubt(f"https://{_wirt}/x/y.tar.gz"))

    # Die Schranken müssen weiter greifen - sonst hätten wir den
    # Fehler nur gegen ein neues Loch getauscht.
    _angriffe = (
        ("http statt https", dict(_ECHT, download=_ECHT["download"]
                                  .replace("https://", "http://"))),
        ("Adresse im Heimnetz", dict(_ECHT, download="http://192.168.1.5/x")),
        ("file-Pfad", dict(_ECHT, download="file:///C:/Windows/x")),
        ("fremde Domain", dict(_ECHT, download="https://boese.example.com/x")),
        ("angehängte Domain",
         dict(_ECHT, download="https://oss.iot.dreame.life.boese.com/x")),
        ("Pfadausbruch in der Kennung", dict(_ECHT, id="../../autostart")),
        ("ohne Größenangabe", dict(_ECHT, size=0)),
        ("unplausible Größe", dict(_ECHT, size=300 * 1024 * 1024)),
    )
    for _name, _roh in _angriffe:
        _v = official.VoicePackInfo(_roh)
        check(f"abgewehrt: {_name}", not _v.brauchbar)
        # Der Grund muss dastehen. "Sieht ungewöhnlich aus" hat beim
        # echten Fehler eine halbe Stunde gekostet.
        check(f"und begründet: {_name}", bool(_v.einwand))

    # --- und nun einmal die Wirklichkeit selbst -----------------------
    # Genau EINE Anfrage. Der Server von Dreame ist eine Auskunft, kein
    # Testziel. Ohne Netz wird übersprungen - der Bau soll nicht an
    # einer fehlenden Verbindung scheitern.
    try:
        _live = official.fetch_catalog("dreame.vacuum.r2532v", timeout=8)
    except Exception as _exc:                            # noqa: BLE001
        uebersprungen("der echte Katalog wird angenommen",
                      f"nicht erreichbar ({type(_exc).__name__})")
    else:
        check("der echte Katalog liefert brauchbare Einträge",
              len(_live) >= 10, f"{len(_live)}")
        _de = [p for p in _live if p.id == "DE"]
        check("und enthält ein deutsches Paket", bool(_de))
        if _de:
            _p = _de[0]
            check("das deutsche Paket hat eine Prüfsumme",
                  len(_p.md5) == 32, _p.md5)
            check("eine plausible Größe",
                  1_000_000 < _p.size <= official.MAX_PAKET_BYTES,
                  f"{_p.size}")
            check("und einen Namen für die Anzeige",
                  bool(_p.name) and _p.name != _p.id, _p.name)
        # Wenn Dreame die Auslieferung umstellt, muss das hier
        # auffallen - und nicht beim Nutzer.
        _fremd = sorted({_u.hostname for _u in
                         (_urlsplit(p.url) for p in _live)}
                        - {"oss.iot.dreame.life", "oss.iot.dreame.tech"})
        check("Dreame liefert weiterhin von den bekannten Servern",
              not _fremd, f"neu aufgetaucht: {_fremd}")


    # --- und die FORM der Antwort, nicht nur ihr Inhalt --------------
    # Geprueft wurde bisher, ob die Adresse von einem bekannten Server
    # kommt und die Größe stimmt. Dass `data` ein Wörterbuch,
    # `voices` eine Liste, `size` eine Zahl und `name` ein Objekt ist,
    # wurde einfach unterstellt. Fünf präparierte Antworten ergaben
    # rohe englische Ausnahmen im Fehlerdialog - und eine Kennung als
    # ZAHL kam durch alle Schranken, weil `str(42)` auf das Muster
    # passt, gespeichert aber die Zahl blieb.
    class _Antwort:
        status_code = 200

        def __init__(self, inhalt):
            self._inhalt = inhalt

        def json(self):
            return self._inhalt

    def _mit_antwort(inhalt):
        """Ruft fetch_catalog mit einer selbst gebauten Antwort auf.

        Örtlich, ohne den Server von Dreame anzufassen: Der ist eine
        Auskunftsquelle, kein Testziel.
        """
        import requests as _rq
        _alt = official.requests
        official.requests = type("R", (), {
            "get": staticmethod(lambda *a, **k: _Antwort(inhalt)),
            "exceptions": _rq.exceptions})
        try:
            return official.fetch_catalog("dreame.vacuum.r2532v"), None
        except DreameError as exc:
            return None, exc
        finally:
            official.requests = _alt

    _gut = "https://oss.iot.dreame.life/dreame-product/x.tar.gz"

    def _eintrag(**aender):
        roh = {"id": "DE", "size": 11094134, "md5sum": "0e" * 16,
               "download": _gut, "name": {"default": "Deutsch"}}
        roh.update(aender)
        return {"data": {"voices": [roh]}}

    _kaputt = [
        ("data ist eine Liste", {"code": 0, "data": ["x"]}),
        ("data fehlt ganz", {"code": 0}),
        ("die Antwort selbst ist eine Liste", ["a", "b"]),
        ("voices ist ein Wörterbuch", {"data": {"voices": {"a": 1}}}),
        ("voices enthält Text", {"data": {"voices": ["kaputt"]}}),
        ("size ist Text", _eintrag(size="gross")),
        ("md5sum ist eine Zahl", _eintrag(md5sum=1234)),
        ("md5sum ist zu kurz", _eintrag(md5sum="ab")),
        ("download ist eine Liste", _eintrag(download=[_gut])),
        ("id ist eine Zahl", _eintrag(id=42)),
    ]
    with leise("dreamevoice.official"):
        for _was, _inhalt in _kaputt:
            _pakete, _fehler = _mit_antwort(_inhalt)
            check(f"verdaute Antwort: {_was}",
                  _fehler is not None and not _pakete,
                  f"{len(_pakete or [])} angenommen")
            # Die Meldung muss deutsch und verständlich sein - nicht
            # "'str' object has no attribute 'get'".
            if _fehler is not None:
                _txt = f"{_fehler.message} {_fehler.hint}"
                check(f"und auf Deutsch erklärt: {_was}",
                      "object has no attribute" not in _txt
                      and "invalid literal" not in _txt
                      and "unhashable" not in _txt, _txt[:90])

        # Ein Eintrag mit Text statt Objekt im Namen ist noch brauchbar -
        # da muss die App nicht kleinlich sein.
        _pakete, _fehler = _mit_antwort(_eintrag(name="Deutsch"))
        check("ein Name als Text wird trotzdem angenommen",
              _fehler is None and _pakete and _pakete[0].name == "Deutsch",
              f"{_fehler}")
        _pakete, _fehler = _mit_antwort(_eintrag())
        check("und die heile Antwort geht durch",
              _fehler is None and len(_pakete or []) == 1, f"{_fehler}")

    # --- Ein Abbruch darf nichts liegen lassen -----------------------
    # Der Abbruch wegen Überlänge ist ein NetworkError und damit
    # keine RequestException - er lief an der Aufräumzeile vorbei.
    # Bei einem 300-MB-Strom blieben 240 MB im Zwischenspeicher liegen,
    # und zwar bei jedem neuen Versuch erneut.
    class _Strom:
        status_code = 200
        headers: dict = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_content(self, chunk_size=0):
            for _ in range(300):
                yield b"x" * (1024 * 1024)

    import requests as _rq3
    _alt3 = official.requests
    official.requests = type("R", (), {
        "get": staticmethod(lambda *a, **k: _Strom()),
        "exceptions": _rq3.exceptions})
    try:
        _p3 = official.VoicePackInfo(
            {"id": "ZZ", "size": 11094134, "md5sum": "0e" * 16,
             "download": "https://oss.iot.dreame.life/x.tar.gz"})
        with leise("dreamevoice.official"):
            try:
                official.download_pack(_p3, "selbsttestmodell")
                check("ein übergroßes Paket wird abgebrochen", False,
                      "keine Ausnahme")
            except DreameError:
                check("ein übergroßes Paket wird abgebrochen", True)
        from dreamevoice.paths import cache_dir as _cache
        _reste = list(_cache().glob("selbsttestmodell*"))
        check("und lässt keine halbe Datei zurück", not _reste,
              f"{[(r.name, r.stat().st_size) for r in _reste]}")
        for _r in _reste:
            _r.unlink(missing_ok=True)
    finally:
        official.requests = _alt3

    # --- Fremdpakete hatten überhaupt keine Schranke ----------------
    # community.download() prüft weder Schema noch Host und hatte
    # keine Obergrenze. Ein Eintrag zeigt auf ein unversioniertes
    # Zweigarchiv, dessen Inhalt der Projektinhaber jederzeit
    # austauschen kann - und dessen Größe der Server nicht nennt.
    from dreamevoice import community as _com

    for _p in _com.PACKS:
        check(f"Fremdpaket '{_p.key}' kommt von GitHub",
              _com.adresse_erlaubt(_p.url), _p.url)
    for _boese in ("http://github.com/x", "https://boese.example.com/x",
                   "file:///C:/Windows/x", "https://github.com.boese.de/x",
                   "//github.com/x", ""):
        check(f"abgewehrt als Fremdquelle: {_boese[:34]!r}",
              not _com.adresse_erlaubt(_boese))
    check("Fremdpakete haben eine Obergrenze",
          getattr(_com, "MAX_PAKET_BYTES", 0) > 0)

    # Ohne Prüfsumme gilt eine einmal geladene Datei für immer als
    # gültig und wird nie erneuert. Nur der eine Eintrag, dessen
    # Quelle sich naturgemäß ändert, darf ohne auskommen.
    _ohne = [p.key for p in _com.PACKS if not p.expected_md5]
    check("höchstens das Zweigarchiv hat keine Prüfsumme",
          _ohne in ([], ["glados_x40_kokoro"]), f"{_ohne}")

    # --- Die Prüfsumme im Release-Text ------------------------------
    # Sie stand monatelang als "BITTE-NACH-DEM-BAUEN-EINTRAGEN" drin.
    # Eine falsche oder fehlende Summe ist schlimmer als gar keine:
    # Wer sie nachrechnet und eine Abweichung findet, hält die Datei
    # für manipuliert und lädt sie nicht.
    _rel2 = (Path(__file__).resolve().parent / "RELEASE.md")
    if not _rel2.is_file():
        uebersprungen("die Prüfsumme im Release-Text stimmt",
                      "RELEASE.md fehlt")
    else:
        _txt2 = _rel2.read_text(encoding="utf-8")
        check("im Release-Text steht kein Platzhalter mehr",
              "BITTE-NACH-DEM-BAUEN" not in _txt2)
        _summen = _re.findall(r"\b[0-9a-f]{64}\b", _txt2)
        check("und eine richtige SHA-256-Summe", bool(_summen),
              "keine 64 Hexzeichen gefunden")
        _exe2 = Path(__file__).resolve().parent / "dist" / "DreameSprachpaket.exe"
        if not _exe2.is_file():
            uebersprungen("die Summe gehört zur gebauten EXE",
                          "dist/DreameSprachpaket.exe fehlt")
        elif _summen:
            _ist = hashlib.sha256(_exe2.read_bytes()).hexdigest()
            if _ist in _summen:
                check("die Summe gehört zur gebauten EXE", True)
            else:
                # KEIN Fehlschlag: build_exe.ps1 lässt den Selbsttest
                # VOR dem Bauen laufen. Wäre das hier rot, blockierte
                # es jeden weiteren Bau - die Summe kann ja erst danach
                # stimmen. Sichtbar bleibt es trotzdem, und vor dem
                # Veröffentlichen gehört es nachgetragen.
                uebersprungen(
                    "die Summe gehört zur gebauten EXE",
                    f"EXE ist {_ist[:16]}..., im Text steht "
                    f"{_summen[0][:16]}... - nach dem letzten Bau nachtragen")

    # --- Die Packliste fürs Release ---------------------------------
    # `VEROEFFENTLICHEN.md` ist die Liste, die ein Mensch abarbeitet.
    # Steht dort eine Datei, die es nicht gibt, fehlt sie hinterher im
    # Release - genau so ging "Bayerisch-Weiblich" in v1.2.0 verloren,
    # und der Knopf "neuere Fassung holen" lief für diese Stimme in
    # einen 404. Die Größenangaben laufen mit: Sie sagen dem Menschen,
    # ob er die richtige Datei erwischt hat.
    _vm = Path(__file__).resolve().parent / "VEROEFFENTLICHEN.md"
    if not _vm.is_file():
        uebersprungen("die Packliste fürs Release stimmt",
                      "VEROEFFENTLICHEN.md fehlt")
    else:
        _pakete2 = Path(__file__).resolve().parent / "Fertige Pakete"
        _zeilen = _re.findall(
            r"^\|\s*`([A-Za-z0-9_.\-]+\.(?:zip|exe))`\s*\|\s*~?([\d,]+)\s*MB",
            _vm.read_text(encoding="utf-8"), _re.M)
        check("die Packliste nennt die EXE und fünf Archive",
              len(_zeilen) == 6, f"{[n for n, _ in _zeilen]}")
        for _name2, _mb in _zeilen:
            _quelle = (Path(__file__).resolve().parent / "dist" / _name2
                       if _name2.endswith(".exe") else _pakete2 / _name2)
            if not _quelle.is_file():
                # Die EXE fehlt in einem frischen Klon; die Archive nicht.
                if _name2.endswith(".exe"):
                    uebersprungen(f"{_name2} liegt bereit", "noch nicht gebaut")
                else:
                    check(f"{_name2} liegt bereit", False, f"{_quelle} fehlt")
                continue
            _ist_mb = _quelle.stat().st_size / (1024 * 1024)
            _soll = float(_mb.replace(",", "."))
            check(f"{_name2} liegt bereit und ist rund {_mb} MB groß",
                  abs(_ist_mb - _soll) <= 0.5, f"{_ist_mb:.1f} MB")

    # --- "rund 90 MB" stand da, als es 97 waren ---------------------
    # Die Zahl steht an drei Stellen, und alle drei sind das Erste, was
    # jemand liest: der Download-Knopf in der README, die Bauanleitung
    # und die Packliste. Sie wächst mit jeder neuen Stimme mit, ohne
    # dass jemand daran denkt.
    _exe3 = Path(__file__).resolve().parent / "dist" / "DreameSprachpaket.exe"
    if not _exe3.is_file():
        uebersprungen("die Doku nennt die richtige Größe der EXE",
                      "dist/DreameSprachpaket.exe fehlt")
    else:
        _echt_mb = _exe3.stat().st_size / (1024 * 1024)
        _daneben = []
        for _name3 in ("README.md", "VEROEFFENTLICHEN.md",
                       "docs/Entwicklung.md"):
            _p3 = Path(__file__).resolve().parent / _name3
            if not _p3.is_file():
                continue
            for _m3 in _re.finditer(r"(?:rund|~)\s*(\d{2,3})\s*MB",
                                    _p3.read_text(encoding="utf-8")):
                if abs(int(_m3.group(1)) - _echt_mb) > 3:
                    _daneben.append(f"{_name3}: {_m3.group(0)}")
        check("die Doku nennt die richtige Größe der EXE", not _daneben,
              f"EXE ist {_echt_mb:.0f} MB, im Text steht {_daneben}")

    # ==================================================================
    section("43. Was der Umbau auf faule Seiten hinterlassen hat")
    # ==================================================================
    from dreamevoice.ui.state import AppState as _AppState

    # a) ffmpeg muss der gemeinsame Zustand selbst finden.
    #    Früher setzte allein BuilderTab diesen Wert. Seit die Seite
    #    erst beim Öffnen entsteht, blieb er None - und "Anhören"
    #    scheiterte auf dem Hauptweg bei jeder einzelnen Stimme.
    _st = _AppState()
    _ff_da = audio.find_ffmpeg()
    if _ff_da is None:
        uebersprungen("ffmpeg findet sich ohne gebaute Seite",
                      "auf diesem Rechner ist kein ffmpeg installiert")
    else:
        check("ffmpeg findet sich ohne dass eine Seite gebaut wurde",
              _st.ffmpeg is not None, f"{_st.ffmpeg}")
        check("und zwar dasselbe, das audio.find_ffmpeg liefert",
              _st.ffmpeg == _ff_da, f"{_st.ffmpeg} != {_ff_da}")
    # Ein gesetzter Wert bleibt stehen, ein zurückgesetzter wird neu
    # gesucht - sonst fiele die Suche nach dem Auspacken nicht mehr an.
    _st.ffmpeg = Path("irgendwo/ffmpeg.exe")
    check("ein gesetzter Pfad wird nicht überschrieben",
          _st.ffmpeg == Path("irgendwo/ffmpeg.exe"), f"{_st.ffmpeg}")

    # b) "anderer Roboter" und "andere Stimme" sind zweierlei.
    _st2 = _AppState()
    _st2.base_pack_path = Path("original.tar.gz")
    _st2.official_packs = ["DE", "EN"]
    _st2.notify("pack_installed")
    check("nach dem Aufspielen bleibt das Originalpaket erhalten",
          _st2.base_pack_path is not None)
    check("und die Sprachliste für den Notausgang auch",
          len(_st2.official_packs) == 2, f"{_st2.official_packs}")

    _st2.notify("device_changed")
    check("beim echten Roboterwechsel wird beides verworfen",
          _st2.base_pack_path is None and not _st2.official_packs)

    # c) Und niemand darf das verwerfende Ereignis aus einem anderen
    #    Anlass melden. Genau daran ist es gescheitert: gemeint war
    #    "frisch anzeigen", ausgelöst wurde "alles wegwerfen".
    _erlaubt = {"page_start.py", "tab_connect.py"}
    _falsch = []
    for _p in sorted((Path(__file__).resolve().parent / "dreamevoice"
                      / "ui").glob("*.py")):
        if 'notify("device_changed")' in _p.read_text(encoding="utf-8-sig") \
                and _p.name not in _erlaubt:
            _falsch.append(_p.name)
    check("nur ein echter Gerätewechsel meldet 'device_changed'",
          not _falsch, f"auch: {_falsch}")

    # d) Der gemeinsame Zustand darf überhaupt nichts von einer Seite
    #    geschenkt bekommen, das er nicht selbst herstellen kann.
    _frisch = _AppState()
    for _feld in ("catalog", "config"):
        check(f"AppState bringt '{_feld}' selbst mit",
              getattr(_frisch, _feld, None) is not None)


    # ==================================================================
    section("44. Drei Marken, nicht nur eine")
    # ==================================================================
    # cloud.py hatte alle drei Mandanten fertig - eigene Adresse, eigene
    # Mandanten-ID, eigener User-Agent. Nur: config["account_type"] wurde
    # an zwei Stellen GELESEN und nirgends geschrieben. In der ganzen
    # Oberfläche gab es kein Feld dafür. Die README wirbt mit "Dreame,
    # MOVA und Trouver", docs/Modelle.md zählt 97 MOVA- und 17
    # Trouver-Modelle: zwei beworbene Gerätefamilien, erreichbar nur
    # über einen Handeingriff in die config.json.
    from dreamevoice import cloud as _cl

    check("es gibt drei Marken", sorted(_cl.MARKEN) ==
          ["dreame", "mova", "trouver"], f"{_cl.MARKEN}")
    for _m in _cl.MARKEN:
        check(f"'{_m}' hat eine Beschriftung", bool(_cl.MARKEN_LABELS.get(_m)))
        check(f"'{_m}' hat eine eigene Adresse",
              _m in _cl.API_HOST_SUFFIX and _m in _cl.TENANT_ID)
        _c = _cl.DreameCloud(_m)
        check(f"'{_m}' behält seinen Mandanten",
              _c.account_type == _m and _c.tenant_id == _cl.TENANT_ID[_m])

    # Trouver betreibt Korea und China nicht - per DNS nachgemessen an
    # allen 18 Kombinationen. Wer sie trotzdem anbietet, schickt den
    # Nutzer in einen DNS-Fehler statt in eine Auskunft.
    check("Trouver bietet Korea und China nicht an",
          "kr" not in _cl.regionen_fuer("trouver")
          and "cn" not in _cl.regionen_fuer("trouver"),
          f"{_cl.regionen_fuer('trouver')}")
    check("Dreame und MOVA bieten alle Regionen",
          _cl.regionen_fuer("dreame") == _cl.REGIONS
          and _cl.regionen_fuer("mova") == _cl.REGIONS)
    for _m in _cl.MARKEN:
        check(f"jede Region von '{_m}' hat eine Beschriftung",
              all(r in _cl.REGION_LABELS for r in _cl.regionen_fuer(_m)))
    check("eine unbekannte Marke bekommt trotzdem eine Liste",
          _cl.regionen_fuer("gibtsnicht") == _cl.REGIONS)

    # Und die Oberfläche muss den Wert auch SETZEN können. Genau das
    # fehlte: gelesen an zwei Stellen, geschrieben an keiner.
    _ui = Path(__file__).resolve().parent / "dreamevoice" / "ui"
    _schreiber = [p.name for p in sorted(_ui.glob("*.py"))
                  if 'config["account_type"] =' in p.read_text(encoding="utf-8-sig")]
    check("die Oberfläche kann die Marke überhaupt setzen",
          bool(_schreiber), "kein einziges Feld schreibt account_type")
    # Beide Anmeldeformulare, nicht nur eines - sonst kann derselbe
    # Nutzer je nach Seite etwas anderes einstellen.
    for _datei in ("page_start.py", "tab_connect.py"):
        check(f"{_datei} bietet die Markenauswahl an", _datei in _schreiber,
              f"{_schreiber}")
        _q = (_ui / _datei).read_text(encoding="utf-8-sig")
        check(f"{_datei} meldet sich mit der gewählten Marke an",
              "DreameCloud(marke)" in _q)

    # Kein Anmeldetext darf nur eine der drei Apps nennen.
    for _datei in ("page_start.py", "tab_connect.py"):
        _q = (_ui / _datei).read_text(encoding="utf-8-sig")
        for _falsch in ("Bei Dreamehome anmelden",
                        "wie in der Dreamehome-App."):
            check(f"{_datei} nennt nicht nur Dreamehome ({_falsch[:22]})",
                  _falsch not in _q)


    # ==================================================================
    section("45. Was man sehen können muss")
    # ==================================================================
    # Zwei Meldungen des Nutzers, dieselbe Ursache: Im dunklen Design
    # war die Knopffläche DUNKLER als ihre Karte (1,06:1), und der
    # Rand des leeren Auswahlkästchens lag bei 1,26:1. Beides war da,
    # nur nicht zu sehen. Dunkle Oberflächen funktionieren umgekehrt
    # zu hellen: Was näher am Betrachter liegt, ist heller.
    from dreamevoice.ui import theme as _th

    def _leuchtdichte(rgb):
        """Relative Helligkeit nach WCAG."""
        def _k(wert):
            wert /= 255
            return wert / 12.92 if wert <= 0.04045 else ((wert + 0.055) / 1.055) ** 2.4
        return 0.2126 * _k(rgb[0]) + 0.7152 * _k(rgb[1]) + 0.0722 * _k(rgb[2])

    def _rgb(hexwert):
        return tuple(int(hexwert[i:i + 2], 16) for i in (1, 3, 5))

    def _kontrast(a, b):
        _l1, _l2 = sorted((_leuchtdichte(a), _leuchtdichte(b)), reverse=True)
        return (_l1 + 0.05) / (_l2 + 0.05)

    #: Was die Norm für den Umriss eines Bedienelements verlangt.
    _NORM = 3.0

    for _name, _pal in (("hell", _th.LIGHT), ("dunkel", _th.DARK)):
        for _feld in ("button", "button_hover", "button_border"):
            check(f"{_name}: '{_feld}' ist gesetzt", _feld in _pal, f"{_feld}")
        if "button_border" not in _pal:
            continue
        _rand = _rgb(_pal["button_border"])
        for _grund, _wo in ((_rgb(_pal["surface"]), "Karte"),
                            (_rgb(_pal["bg"]), "Seite")):
            _k = _kontrast(_rand, _grund)
            check(f"{_name}: Knopfrand auf der {_wo} erfüllt die Norm",
                  _k >= _NORM, f"{_k:.2f}:1, nötig {_NORM}:1")
        # Die Beschriftung muss auf der Knopffläche lesbar sein - dafür
        # gilt die schärfere Textnorm von 4,5:1.
        _kt = _kontrast(_rgb(_pal["text"]), _rgb(_pal["button"]))
        check(f"{_name}: Knopfbeschriftung ist lesbar", _kt >= 4.5,
              f"{_kt:.2f}:1")

    # Im Dunkeln muss der Knopf HELLER sein als seine Karte. Genau
    # andersherum war es der Fehler.
    check("im dunklen Design liegt der Knopf über seiner Karte",
          _leuchtdichte(_rgb(_th.DARK["button"]))
          > _leuchtdichte(_rgb(_th.DARK["surface"])),
          "der Knopf ist dunkler als die Karte")

    # Und dasselbe für das Kästchen der Auswahlfelder. Sein Rand
    # steckt im Bild, nicht in der Palette - er fällt bei einer
    # Farbänderung also nicht von selbst mit auf.
    try:
        from PIL import Image as _Img
        _pillow = True
    except ImportError:                                  # pragma: no cover
        _pillow = False
    if not _pillow:
        uebersprungen("der Rand des Auswahlkästchens erfüllt die Norm",
                      "Pillow fehlt")
    else:
        import base64 as _b64
        for _vorsatz, _pal in (("LICHT", _th.LIGHT), ("DUNKEL", _th.DARK)):
            _daten = _th.HAKEN_PNG.get(f"{_vorsatz}_AUS")
            if not _daten:
                check(f"{_vorsatz}: es gibt ein leeres Kästchen", False)
                continue
            with _Img.open(io.BytesIO(_b64.b64decode(_daten))) as _im:
                _bild = _im.convert("RGBA")
                _breit, _hoch = _bild.size
                # Kräftigster Randpunkt an der Oberkante: Die Ecken
                # sind rund und durch das Herunterrechnen weich.
                _kandidaten = [_bild.getpixel((_x, _y))[:3]
                               for _x in range(_breit // 3, 2 * _breit // 3)
                               for _y in (1, 2, 3)]
            _grund = _rgb(_pal["surface"])
            _best = max(_kandidaten, key=lambda _p: _kontrast(_p, _grund))
            _k = _kontrast(_best, _grund)
            check(f"{_vorsatz}: der Rand des Kästchens erfüllt die Norm",
                  _k >= _NORM, f"{_k:.2f}:1, nötig {_NORM}:1")

    # Angehakt muss sich vom Leeren auch aus dem Augenwinkel
    # unterscheiden - deshalb gefüllt statt nur umrandet.
    if _pillow:
        def _mittelwert(daten):
            """Durchschnittsfarbe der Kästchenfläche.

            Ein einzelner Bildpunkt in der Mitte taugt dafür nicht:
            Beim angehakten Kästchen liegt dort der Haken, und der ist
            absichtlich dunkel - gemessen kam so 1,11:1 heraus, obwohl
            die Flächen sich deutlich unterscheiden.
            """
            with _Img.open(io.BytesIO(_b64.b64decode(daten))) as _im:
                _b = _im.convert("RGB")
                _w, _h = _b.size
                _punkte = [_b.getpixel((_x, _y))
                           for _x in range(_w // 4, 3 * _w // 4)
                           for _y in range(_h // 4, 3 * _h // 4)]
            return tuple(sum(_p[_i] for _p in _punkte) // len(_punkte)
                         for _i in range(3))

        for _vorsatz in ("LICHT", "DUNKEL"):
            _leer = _mittelwert(_th.HAKEN_PNG[f"{_vorsatz}_AUS"])
            _voll = _mittelwert(_th.HAKEN_PNG[f"{_vorsatz}_AN"])
            _k = _kontrast(_leer, _voll)
            check(f"{_vorsatz}: angehakt sieht anders aus als leer",
                  _k >= 2.0, f"{_k:.2f}:1 zwischen {_leer} und {_voll}")

    # --- Die Roboterliste darf sich nicht selbst aufrufen -------------
    # Ich hatte ConnectTab auf "device_changed" hören lassen, damit
    # eine Anmeldung auf der Startseite hier ankommt. Das ergab eine
    # Endlosschleife: liste_auffrischen -> tree.selection_set ->
    # <<TreeviewSelect>> -> _on_select_device -> notify("device_changed")
    # -> zurück. Die gebaute App blieb beim Öffnen der Seite stehen,
    # "Keine Rückmeldung". Kein Test hat das bemerkt, weil er die Seite
    # nie mit Geräten im Zustand geöffnet hat.
    if not _tk_da:
        uebersprungen("die Roboterliste läuft nicht im Kreis",
                      "Tkinter oder Anzeige fehlt auf diesem Rechner")
    else:
        from dreamevoice.cloud import Device as _Dev
        from dreamevoice.ui.tab_connect import ConnectTab as _CT
        from dreamevoice.ui.theme import Theme as _Th
        from dreamevoice.ui.state import AppState as _AppSt
        import tkinter as _tk3

        # Der Test darf die Konfiguration des Nutzers NICHT anfassen.
        # Genau das ist passiert: Tk stellt <<TreeviewSelect>> in die
        # Warteschlange, beim nächsten update() lief es nach - da war
        # der Riegel schon wieder offen -, und _on_select_device
        # schrieb das erfundene Gerät "1" in die echte config.json.
        from dreamevoice import config as _cfgmod3
        _echte_datei = _cfgmod3.config_file
        _testordner = arbeitsordner("konfig")
        _cfgmod3.config_file = lambda: _testordner / "config.json"

        _w = None
        try:
            _w = _tk3.Tk()
            _w.withdraw()
            _st3 = _AppSt()
            _st3.devices = [
                _Dev({"did": "1", "name": "Erster", "model": "dreame.vacuum.r2532v"}),
                _Dev({"did": "2", "name": "Zweiter", "model": "dreame.vacuum.r2532h"}),
            ]
            _tab = _CT(_w, _Th(_w, dark=False), _st3)

            # Mitzählen, wie oft die Auswahl verarbeitet wird. Ohne
            # Riegel liefe das bis zum Rekursionsanschlag.
            _zaehler = {"n": 0}
            _echt_select = _tab._on_select_device

            def _gezaehlt(_e=None):
                _zaehler["n"] += 1
                if _zaehler["n"] > 50:
                    raise RecursionError("liste_auffrischen ruft sich selbst")
                return _echt_select(_e)

            _tab._on_select_device = _gezaehlt
            _tab.tree.bind("<<TreeviewSelect>>", _gezaehlt)

            _tab.beim_zeigen()
            _w.update()
            check("die Roboterliste läuft nicht im Kreis", True)
            check("und zeigt beide Roboter",
                  len(_tab.tree.get_children()) == 2,
                  f"{len(_tab.tree.get_children())}")
            # Der Aufbau selbst darf die Auswahl NICHT verarbeiten -
            # sie kommt ja von uns, nicht vom Benutzer.
            check("der Aufbau löst keine Gerätewahl aus",
                  _zaehler["n"] <= 2, f"{_zaehler['n']} Aufrufe")

            # Und niemand darf wieder auf device_changed hören.
            _q3 = (Path(__file__).resolve().parent / "dreamevoice" / "ui"
                   / "tab_connect.py").read_text(encoding="utf-8-sig")
            check("tab_connect hört nicht auf 'device_changed'",
                  'subscribe("device_changed"' not in _q3)
        except RecursionError as _exc:
            check("die Roboterliste läuft nicht im Kreis", False, str(_exc))
        finally:
            _cfgmod3.config_file = _echte_datei
            if _w is not None:
                _w.destroy()

        # Und die Gegenprobe: Der Test darf nichts hinterlassen haben.
        _echt_jetzt = _echte_datei()
        if _echt_jetzt.is_file():
            try:
                _inhalt = json.loads(_echt_jetzt.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                _inhalt = {}
            check("der Test hat die echte Konfiguration nicht angefasst",
                  _inhalt.get("device_id") not in ("1", "2"),
                  f"device_id steht auf {_inhalt.get('device_id')!r}")

    # --- Das Symbol der App ------------------------------------------
    # Es ging bisher nur an PyInstaller - das ist das Symbol der DATEI
    # im Explorer. Das Fenster und die Taskleiste zeigten Tks
    # eingebaute Feder. Und als das Symbol dann da war, war es
    # unscharf: Es fehlten 20, 40 und 96 - genau die Größen, die die
    # Taskleiste bei 125 %, 150 % und 200 % Skalierung abruft. Fehlt
    # eine, rechnet Windows sie sich selbst zurecht.
    _ico = Path(__file__).resolve().parent / "app.ico"
    if not _ico.is_file():
        uebersprungen("das Symbol der App ist scharf", "app.ico fehlt")
    elif not _pillow:
        uebersprungen("das Symbol der App ist scharf", "Pillow fehlt")
    else:
        with _Img.open(_ico) as _i:
            _hat = {g[0] for g in _i.info.get("sizes", [])}
        _noetig = {16, 20, 24, 32, 40, 48, 64, 96, 128, 256}
        _fehlt2 = sorted(_noetig - _hat)
        check("das Symbol bringt alle Größen mit, die Windows abruft",
              not _fehlt2, f"es fehlen {_fehlt2}")
        check("und reicht bis 256 Pixel", 256 in _hat, f"{sorted(_hat)}")

    # Es muss auch zur Laufzeit gefunden werden, sonst bleibt es bei
    # der Feder - in der EXE liegt es nur da, wenn die spec es mitnimmt.
    from dreamevoice.paths import icon_file as _iconf
    check("die App findet ihr Symbol", _iconf() is not None)
    _spec2 = Path(__file__).resolve().parent / "DreameSprachpaket.spec"
    if _spec2.is_file():
        check("die EXE nimmt das Symbol als Datei mit",
              '("app.ico", ".")' in _spec2.read_text(encoding="utf-8"))
    _appq2 = (Path(__file__).resolve().parent / "dreamevoice" / "ui"
              / "app.py").read_text(encoding="utf-8-sig")
    # Kein geplanter Auftrag darf ein zerstörtes Fenster überleben.
    # Tk löscht beim Zerstören den Befehl, der Zeitauftrag bleibt aber
    # stehen und meldet dann "invalid command name ..." - im
    # Bauprotokoll standen davon zuletzt sechs Stück. Eine Prüfung IM
    # Rückruf hilft nicht; er muss abbestellt werden, und dafür gibt
    # es state.spaeter().
    _uidateien = sorted((_uiord).glob("*.py"))
    _roh_after = []
    for _p in _uidateien:
        # state.py definiert den Helfer und beschreibt after() im
        # Text - dort ist ein Treffer kein Fund.
        if _p.name == "state.py":
            continue
        _q = _p.read_text(encoding="utf-8-sig")
        for _nr, _zeile in enumerate(_q.splitlines(), 1):
            if _re.search(r"\.after\(\s*\d", _zeile) and "spaeter" not in _zeile:
                _roh_after.append(f"{_p.name}:{_nr}")
    check("kein ungesicherter Zeitauftrag in der Oberfläche",
          not _roh_after, f"{_roh_after[:3]}")
    _stateq = (_uiord / "state.py").read_text(encoding="utf-8")
    check("es gibt einen Helfer, der Aufträge abbestellt",
          "def spaeter(" in _stateq and "after_cancel" in _stateq)

    check("das Fenster setzt sein Symbol", "iconbitmap" in _appq2)
    check("und meldet sich der Taskleiste als eigene App",
          "AppUserModelID" in _appq2)

    # Und es muss wirklich ankommen. Zwei Fehler hintereinander haben
    # verhindert, dass überhaupt etwas gesetzt wurde, und beide waren
    # von außen nicht zu sehen - das Fenster zeigte einfach weiter
    # das alte Bild:
    #   1. winfo_id() liefert bei Tk das INNERE Fenster ("TkChild").
    #      Der Taskleisteneintrag hängt am äußeren ("TkTopLevel").
    #   2. Das Setzen lief über after(0, ...) und damit, bevor das
    #      äußere Fenster überhaupt existierte.
    # Deshalb wird hier nicht der Quelltext geprüft, sondern das
    # Ergebnis: Windows selbst wird gefragt, ob ein Symbol dranhängt.
    if sys.platform != "win32":
        uebersprungen("das Symbol hängt wirklich am Fenster",
                      "nur unter Windows prüfbar")
    elif not _tk_da:
        uebersprungen("das Symbol hängt wirklich am Fenster",
                      "Tkinter oder Anzeige fehlt auf diesem Rechner")
    else:
        import ctypes as _ct
        from ctypes import wintypes as _wt
        _u32 = _ct.windll.user32
        _u32.SendMessageW.restype = _ct.c_void_p
        _f3 = None
        try:
            _f3 = MainWindow()
            _f3.withdraw()
            _innen = _wt.HWND(_f3.winfo_id())
            _aussen = _u32.GetParent(_innen)
            _ziel = _wt.HWND(_aussen) if _aussen else _innen
            check("das äußere Fenster ist ein anderes als winfo_id()",
                  bool(_aussen), "GetParent lieferte nichts")
            _gross = _u32.SendMessageW(_ziel, 0x007F, 1, 0)   # WM_GETICON
            _klein = _u32.SendMessageW(_ziel, 0x007F, 0, 0)
            check("ein großes Symbol hängt am Fenster", bool(_gross))
            check("ein kleines Symbol hängt am Fenster", bool(_klein))
        finally:
            if _f3 is not None:
                _f3.destroy()

    # --- Keine Namen von Hinweisgebern -------------------------------
    # Verbesserungen kamen aus Foren und von Testern. Ihre Namen
    # gehören nicht in ein Projekt, das Spenden annimmt - wer einen
    # Fehler meldet, hat damit keiner Nennung zugestimmt. Anonym
    # formuliert ("Aus dem Forum kam der Bericht ...") bleibt der
    # Grund erhalten, ohne jemanden zu benennen.
    _wurzel3 = Path(__file__).resolve().parent
    _dateien3 = ([_p for _p in _wurzel3.rglob("*.py")
                  if not any(_t in _p.parts
                             for _t in ("build", "dist", "__pycache__",
                                        ".git", "Werkzeuge"))]
                 + list(_wurzel3.glob("*.md")) + list((_wurzel3 / "docs").glob("*.md")))
    _nennung = _re.compile(
        # Der Großbuchstabe hinter "von"/"an" ist das Erkennungszeichen
        # eines Namens - deshalb darf NUR der Verbteil beide
        # Schreibweisen zulassen. Ein pauschales IGNORECASE würde
        # "gemeldet von mehreren Nutzern" mitfangen.
        r"(?i:gemeldet|entdeckt|gefunden|berichtet|beigetragen)"
        r"\s+von\s+[A-ZÄÖÜ]"
        r"|(?i:vielen\s+dank|danke|dank)\s+an\s+[A-ZÄÖÜ]"
        r"|(?i:hinweis|fund|bericht|meldung|idee|vorschlag)"
        r"\s+von\s+[A-ZÄÖÜ]")
    _treffer3 = []
    for _p in sorted(set(_dateien3)):
        for _m in _nennung.finditer(_p.read_text(encoding="utf-8-sig",
                                                 errors="replace")):
            _treffer3.append(f"{_p.name}: {_m.group(0)}")
    check("kein Hinweisgeber wird namentlich genannt", not _treffer3,
          f"{_treffer3[:3]}")

    # --- Umlaute stehen als Umlaute da -------------------------------
    # Im Hilfefenster stand "Dafuer wird ffmpeg gebraucht". Für den
    # Leser sieht so etwas nach einem kaputten Zeichensatz aus - und es
    # blieb lange unbemerkt, weil es sich beim Schreiben einschleicht.
    #
    # Geprüft werden nur Zeichenketten mit einem Leerzeichen darin, also
    # gesprochene Sätze. Reine Schlüssel und Dateinamen sind davon
    # ausgenommen: "update_pruefen" ist ein Name, kein Satz, und
    # "Problemloesung.md" heißt wirklich so.
    import tokenize as _tk

    _falsch = _re.compile(
        r"(?<![\w])(?:dafuer|Dafuer|fuer|Fuer|ueber|Ueber|laeuft|laesst"
        r"|laedt|moeglich|Moeglich|koenn|muess|groess|Groess|Pruefsumme"
        r"|zurueck|Zurueck|waehl|Waehl|gewaehlt|oeffn|Oeffn|bestaetig"
        r"|unberuehrt|vollstaendig|verfuegbar|uebernomm|uebersprungen"
        r"|spaeter|naechst|Geraet|geraet|haeufig|ausfuehrlich|Schluessel"
        r"|Lautstaerke|anhoer|Anhoer|gehoert|erklaer|Erklaer|pruef|Pruef)"
        r"[a-zäöüß]*")
    _fs_mitte = getattr(_tk, "FSTRING_MIDDLE", -1)
    _namen4: set = set()
    _stellen4 = []
    for _p in sorted(_wurzel3.rglob("*.py")):
        if any(_t in _p.parts for _t in ("build", "dist", "__pycache__",
                                         ".git")):
            continue
        with open(_p, "rb") as _fh:
            for _tok in _tk.tokenize(_fh.readline):
                if _tok.type == _tk.NAME:
                    _namen4.add(_tok.string)
                    continue
                if _tok.type not in (_tk.STRING, _fs_mitte):
                    continue
                _text = _tok.string
                # b"..." verträgt keine Umlaute - dort ist die
                # Ersatzschreibweise die einzig mögliche.
                if _tok.type == _tk.STRING and "b" in _text[:3].lower().split(
                        "'")[0].split('"')[0]:
                    continue
                if " " not in _text.strip("'\"") or "_" in _text:
                    continue
                _stellen4.append((_p.name, _tok.start[0], _text))

    _roh = []
    for _name4, _zeile4, _text in _stellen4:
        for _m in _falsch.finditer(_text):
            # Ein Wort, das im Quellcode als Bezeichner vorkommt, ist ein
            # Verweis auf Code - `spaeter` heißt nun einmal so.
            if _m.group(0) in _namen4:
                continue
            _roh.append(f"{_name4}:{_zeile4}: {_m.group(0)}")
    for _p in sorted(set(list(_wurzel3.glob("*.md"))
                         + list((_wurzel3 / "docs").glob("*.md")))):
        for _z, _zeile in enumerate(
                _p.read_text(encoding="utf-8-sig").splitlines(), 1):
            # Backticks umschließen Code und Dateinamen.
            _ohne = _re.sub(r"`[^`]*`|\S+\.(?:md|py|txt|zip|exe|ps1)", "",
                            _zeile)
            for _m in _falsch.finditer(_ohne):
                _roh.append(f"{_p.name}:{_z}: {_m.group(0)}")
    check("Umlaute stehen in allen angezeigten Texten als Umlaute da",
          not _roh, f"{_roh[:4]}")


    # ==================================================================
    section("46. Mehrere Ansagen gleichzeitig sprechen lassen")
    # ==================================================================
    # Früher lief eine Anfrage nach der anderen: bei 593 Ansagen rund
    # zwölf Minuten, in denen die Leitung fast nur wartet. Jetzt in
    # Wellen, deren Breite sich selbst regelt.
    #
    # Der teuerste denkbare Fehler wäre hier, eine Ansage zweimal
    # sprechen zu lassen - das kostet echtes Geld. Deshalb prüft der
    # Abschnitt vor allem das.
    from dreamevoice import elevenlabs as _el

    _TON = b"ID3" + b"\x00" * 4000

    class _Antwort:
        def __init__(self, status=200, inhalt=_TON, koerper=None):
            self.status_code = status
            self.content = inhalt
            self.text = "" if koerper is None else str(koerper)
            self._koerper = koerper

        def json(self):
            if self._koerper is None:
                raise ValueError("kein JSON")
            return self._koerper

    class _Dienst:
        """Nachgebauter Dienst - zählt mit, wer gleichzeitig anfragt."""

        def __init__(self, grenze=4, dauer=0.0, drosseln_sekunden=0.0,
                     leer_ab=0):
            self.grenze = grenze
            self.dauer = dauer
            self.drosseln_sekunden = drosseln_sekunden
            self.leer_ab = leer_ab
            self.aktiv = 0
            self.hoechstens = 0
            self.anfragen = 0
            self.geliefert: dict = {}
            self.start = time.perf_counter()
            self._riegel = threading.Lock()

        def __call__(self, method, url, headers=None, timeout=None, **kw):
            if "text-to-speech" not in url:
                return _Antwort(200, b"", {"voice_settings": {}})
            text = (kw.get("json") or {}).get("text", "")
            with self._riegel:
                self.anfragen += 1
                nummer = self.anfragen
                self.aktiv += 1
                self.hoechstens = max(self.hoechstens, self.aktiv)
                zuviel = self.aktiv > self.grenze
                spaet = (time.perf_counter() - self.start) < self.drosseln_sekunden
            try:
                if self.dauer:
                    time.sleep(self.dauer)
                if self.leer_ab and nummer > self.leer_ab:
                    return _Antwort(429, b"", {"detail": {
                        "status": "quota_exceeded",
                        "message": "character limit exceeded"}})
                if zuviel or spaet:
                    return _Antwort(429, b"", {"detail": {
                        "status": "too_many_concurrent_requests",
                        "message": "zu viele gleichzeitige Anfragen"}})
                with self._riegel:
                    self.geliefert[text] = self.geliefert.get(text, 0) + 1
                return _Antwort(200, _TON)
            finally:
                with self._riegel:
                    self.aktiv -= 1

    def _mit_dienst(dienst, texte, ordner=None, **kw):
        _alt = _el._http
        _el._http = dienst
        try:
            ziel = ordner or arbeitsordner("wellen")
            return _el.synthesize(texte, ziel, api_key="sk_" + "x" * 30,
                                  voice_id="v1", use_voice_settings=False,
                                  **kw), None
        except DreameError as exc:
            return {}, exc
        finally:
            _el._http = _alt

    _texte = {i: f"Ansage Nummer {i}" for i in range(1, 25)}

    # a) Normalfall: alles kommt durch, die Grenze wird geachtet.
    _d = _Dienst(grenze=4)
    _erg, _fehler = _mit_dienst(_d, _texte)
    check("alle Ansagen werden gesprochen", len(_erg) == len(_texte),
          f"{len(_erg)} von {len(_texte)}, Fehler {_fehler}")
    check("nichts wird doppelt angefordert",
          all(n == 1 for n in _d.geliefert.values()),
          f"{[t for t, n in _d.geliefert.items() if n > 1][:2]}")
    check("die Wellenbreite bleibt in der Grenze",
          _d.hoechstens <= _el.MAX_GLEICHZEITIG, f"{_d.hoechstens}")

    # b) Ein Dienst, der nur eine Anfrage gleichzeitig erlaubt.
    _d = _Dienst(grenze=1)
    _erg, _fehler = _mit_dienst(_d, _texte)
    check("auch ein strenger Dienst wird bedient",
          len(_erg) == len(_texte), f"{len(_erg)}, Fehler {_fehler}")
    check("und auch dabei nichts doppelt",
          all(n == 1 for n in _d.geliefert.values()))

    # c) Kurze Überlastung: die App muss sich erholen, nicht aufgeben.
    #    Genau hier lag ein Denkfehler - jede gedrosselte Ansage bekam
    #    einen Fehlversuch angerechnet, obwohl der Dienst ALLES bremste.
    #    Ergebnis war null gesprochene Ansagen.
    _d = _Dienst(grenze=6, drosseln_sekunden=1.5)
    _erg, _fehler = _mit_dienst(_d, _texte)
    check("nach kurzer Überlastung wird weitergemacht",
          len(_erg) == len(_texte), f"{len(_erg)}, Fehler {_fehler}")

    # d) Kontingent mitten im Lauf leer: behalten, was fertig ist.
    _d = _Dienst(grenze=8, leer_ab=8)
    with leise("dreamevoice.elevenlabs"):
        _erg, _fehler = _mit_dienst(_d, _texte)
    check("bei leerem Kontingent bleibt das Bisherige erhalten",
          0 < len(_erg) < len(_texte) and _fehler is None,
          f"{len(_erg)}, Fehler {_fehler}")

    # e) Ein halb fertiges Paket kostet nur den Rest.
    _ordner = arbeitsordner("halbfertig")
    for _i in range(1, 13):
        (_ordner / f"{_i}.mp3").write_bytes(_TON)
    _d = _Dienst(grenze=8)
    _erg, _fehler = _mit_dienst(_d, _texte, ordner=_ordner)
    check("ein halb fertiges Paket wird fortgesetzt",
          len(_erg) == len(_texte), f"{len(_erg)}")
    check("und nur der Rest wird bezahlt", _d.anfragen == 12,
          f"{_d.anfragen} Anfragen statt 12")

    # f) Abbruch durch den Nutzer wirkt zwischen den Wellen.
    _halt = {"n": 0}

    def _abbrechen():
        _halt["n"] += 1
        return _halt["n"] > 3

    _d = _Dienst(grenze=8)
    _erg, _fehler = _mit_dienst(_d, _texte, cancelled=_abbrechen)
    check("ein Abbruch hält sauber an",
          0 <= len(_erg) < len(_texte) and _fehler is None,
          f"{len(_erg)}, Fehler {_fehler}")

    # g) Und die beiden Bedeutungen von 429 müssen getrennt bleiben.
    #    Sequenziell hieß 429 fast immer "Kontingent leer", parallel
    #    fast immer "zu viele gleichzeitige Anfragen". Beides in einen
    #    Topf zu werfen, bräche den Lauf beim ersten Bremsen ab.
    class _NurStatus:
        status_code = 429

        def __init__(self, status):
            self._status = status
            self.text = status

        def json(self):
            return {"detail": {"status": self._status, "message": self._status}}

    for _status, _erwartet in (("quota_exceeded", False),
                               ("character_limit_exceeded", False),
                               ("too_many_concurrent_requests", True),
                               ("system_busy", True)):
        _alt = _el._http
        _el._http = lambda *a, _s=_status, **k: _NurStatus(_s)
        try:
            _el._request("GET", "user", "sk_" + "x" * 30)
            _ist = None
        except _el.Ueberlastet:
            _ist = True
        except NetworkError:
            _ist = False
        finally:
            _el._http = _alt
        check(f"429 mit '{_status}' gilt als "
              f"{'Drosselung' if _erwartet else 'leeres Kontingent'}",
              _ist is _erwartet, f"{_ist}")


def main() -> int:
    """Alle Prüfungen laufen lassen und Bilanz ziehen.

    Der Rahmen fängt jeden unerwarteten Fehler ab. Ohne ihn beendete
    ein Tippfehler in einem späten Abschnitt den Lauf mit einem
    Stacktrace - ohne Zahl, ohne Bilanz und ohne Hinweis darauf, dass
    zweihundert Prüfungen gar nicht mehr gelaufen sind.
    """
    try:
        _alle_pruefungen()
    except Exception as exc:                         # noqa: BLE001
        print()
        traceback.print_exc()
        check(f"Abschnitt '{LETZTER_ABSCHNITT}' läuft bis zum Ende", False,
              f"{type(exc).__name__}: {exc}")

    _rest = aufraeumen()
    check("die Arbeitsordner sind aufgeräumt", _rest == 0,
          f"{_rest} liegen noch im Temp-Verzeichnis")

    # Eine stillschweigend geschrumpfte Suite ist gefährlicher als eine
    # rote: Sie meldet Erfolg für Prüfungen, die gar nicht liefen.
    check("alle Abschnitte sind gelaufen",
          ABSCHNITTE == ABSCHNITTE_ERWARTET,
          f"{ABSCHNITTE} von {ABSCHNITTE_ERWARTET}")
    _doppelt = sorted({t for t in GESEHEN if GESEHEN.count(t) > 1})
    check("und keiner doppelt", not _doppelt, f"{_doppelt}")

    print()
    print("=" * 52)
    print(f"  Bestanden: {PASSED}    Fehlgeschlagen: {FAILED}"
          + (f"    Übersprungen: {UEBERSPRUNGEN}" if UEBERSPRUNGEN else ""))
    print(f"  Abschnitte: {ABSCHNITTE} von {ABSCHNITTE_ERWARTET}")
    print("=" * 52)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
