"""Selbsttest der Kernlogik - ohne Oberfläche und ohne Roboter.

Prüft die Teile, bei denen ein Fehler teuer wäre: Paketbau, Prüfsummen,
Vollständigkeit des Archivs und die Auslieferung per HTTP.

Aufruf:   python selftest.py
"""

from __future__ import annotations

import hashlib
import io
import logging
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dreamevoice import audio, official, packer, server, installer  # noqa: E402
from dreamevoice.cloud import DreameCloud  # noqa: E402
from dreamevoice.errors import DreameError  # noqa: E402
from dreamevoice.sounds import SoundCatalog  # noqa: E402

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [ok]   {name}")
    else:
        FAILED += 1
        print(f"  [FEHL] {name}" + (f"  -> {detail}" if detail else ""))


def section(title: str) -> None:
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


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="dreamevoice_selftest_"))
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
        check("Abruf wird registriert", srv.was_downloaded)

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

    _orig_request = elevenlabs.requests.request
    elevenlabs.requests.request = _fake
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
        elevenlabs.requests.request = _orig_request

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

    elevenlabs.requests.request = _fake_klang
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
        elevenlabs.requests.request = _orig_request

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

        # ACHTUNG: Der Selbsttest hat hier einmal die *echten* Eintraege
        # benutzt - und damit bei jedem EXE-Bau den gespeicherten
        # ElevenLabs-Schluessel des Nutzers geloescht. Deshalb laeuft der
        # Test jetzt ausschliesslich auf eigenen Zielnamen, und am Ende
        # wird geprueft, dass die echten unangetastet geblieben sind.
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
    # nicht, der Parameter heisst on_finally. Beim Import eines fertigen
    # Pakets waere die App abgestuerzt.
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
        check("Kennung ist kurz und in Grossbuchstaben",
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
        _laut = logging.getLogger("dreamevoice.custom")
        _vorher = _laut.disabled
        _laut.disabled = True
        try:
            check("kaputte Dateien werden übersprungen",
                  custom.load(eigen_dir / "gibtsnicht.json") is None)
        finally:
            _laut.disabled = _vorher
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

    zip_dir = Path(tempfile.mkdtemp())
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
    check("der Ordner im Archiv stoert nicht",
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
    check("und verzweigt darueber, nicht ueber losen Text",
          "art == WAHL_ARCHIV" in quelle_imp)
    check("'ZIP' steht in der ersten Wahl", "ZIP" in _ts.WAHL_ARCHIV)

    # Tab 3 nimmt nur gebaute Pakete. Ein Aufnahmen-ZIP dort muss zu einem
    # Hinweis fuehren, nicht zu einer Formatmeldung.
    from dreamevoice.ui import tab_install as _ti  # noqa: E402
    quelle_pick = inspect.getsource(_ti.InstallTab._on_pick_pack)
    check("Tab 3 faengt ein versehentlich gewaehltes ZIP ab",
          '".zip"' in quelle_pick and "Tab 4" in quelle_pick)

    _shutil.rmtree(zip_dir, ignore_errors=True)

    # ---------------------------------------------------------------
    section("24. Ersetzen nur auf ausdrueckliche Wahl")

    from dreamevoice import library as _lib  # noqa: E402

    lib_dir = Path(tempfile.mkdtemp())
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
    check("und das Vorhandene bleibt unberuehrt",
          (lib_dir / "Hessisch.tar.gz").read_bytes() == b"alt")

    # Der Kern: die Vorgabe im Auswahldialog muss das Behalten sein.
    check("'Daneben speichern' steht an erster Stelle",
          _ts.WAHL_DANEBEN.startswith("Daneben"))
    quelle_imp2 = inspect.getsource(_ts.StoreTab._on_import_ready)
    pos_frage = quelle_imp2.find("WAHL_DANEBEN, WAHL_ERSETZEN")
    pos_vorgabe = quelle_imp2.find("WAHL_DANEBEN)")
    check("und ist die Vorgabe des Dialogs", 0 < pos_frage < pos_vorgabe,
          f"Liste bei {pos_frage}, Vorgabe bei {pos_vorgabe}")
    check("ersetzt wird nur bei ausdruecklicher Wahl",
          "wahl == WAHL_ERSETZEN" in quelle_imp2)

    # build_pack baut in eine .part-Datei und ersetzt erst zum Schluss -
    # sonst waere ein Fehlschlag mitten im Bauen der Verlust des alten.
    quelle_build = inspect.getsource(packer.build_pack)
    pos_part = quelle_build.find('with_suffix(".part")')
    pos_ersetzt = quelle_build.find("tmp_path.replace(out_path)")
    check("gebaut wird in eine .part-Datei", pos_part > 0)
    check("die erst ganz am Ende das Ziel ersetzt",
          0 < pos_part < pos_ersetzt,
          f".part bei {pos_part}, Ersetzen bei {pos_ersetzt}")

    _shutil.rmtree(lib_dir, ignore_errors=True)

    # ---------------------------------------------------------------
    print()
    print("=" * 52)
    print(f"  Bestanden: {PASSED}    Fehlgeschlagen: {FAILED}")
    print("=" * 52)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
