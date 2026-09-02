<!-- Ausgelagert aus der README, damit die Startseite kurz bleibt.
     Inhalt unverändert. -->

# Entwicklung

## Aufbau

```
main.py                      Startpunkt
selftest.py                  Selbsttest der Kernlogik
namecheck.py                 Sucht unbekannte Namen und Schlüsselwörter
build_exe.ps1                Baut die portable EXE
DreameSprachpaket.spec       PyInstaller-Bauplan

embed_ffmpeg.py              Hängt ffmpeg komprimiert an die fertige EXE
embed_dialekte.py            Hängt die fertigen Stimmen an die EXE

dreamevoice/
  cloud.py                   Dreamehome-Cloud: Anmeldung, Geräte, MIoT-Befehle
  official.py                Offizieller Dreame-Katalog, Download, Prüfsummen
  packer.py                  Paketbau auf Basis des Originals
  audio.py                   Formatprüfung und Umwandlung (OGG Vorbis 16 kHz)
  loudness.py                Lautheit der Originalansagen als Vorlage
  ffmpeg_setup.py            Nutzergesteuerte ffmpeg-Einrichtung
  embedded.py                Liest die an die EXE angehängten Daten
  dialektpakete.py           Die mitgelieferten Dialekte bereitstellen
  vorhoeren.py               Ansagen entnehmen und abspielen
  server.py                  Kurzlebiger Webserver für die Auslieferung
  installer.py               Ablauf: bauen, ausliefern, Auftrag, Überwachung
  community.py               Geprüfte Community-Pakete
  importer.py                Ordner und Archive stapelweise übernehmen
  dialect.py                 Dialektpakete: sprechen, umwandeln, bauen
  textfiles.py               Dialekttexte als Datei aus- und einlesen
  library.py                 Sammlung der gebauten Pakete (Namen, Beschreibung)
  custom.py                  Selbst angelegte Sprachpakete
  dialects/                  Die Texte je Dialekt (7 Module)
  tts.py                     Windows-Sprachausgabe (offline)
  elevenlabs.py              ElevenLabs-Sprachausgabe (echter Dialekt)
  sounds.py                  Katalog der Ansage-Nummern
  config.py                  config.json, Geheimnisse per Windows-DPAPI
  paths.py                   Ablageorte (portabel)
  errors.py                  Fehler mit deutschsprachigem Klartext
  credentials.py             Geheimnisse im Windows-Anmeldespeicher
  data/sound_catalog.json    616 Ansagen des X50 Ultra Complete
  ui/
    app.py                   Hauptfenster
    shell.py                 Seitenleiste, Seitenwechsel, Sperren
    theme.py                 Erscheinungsbild (hell/dunkel, ohne Fremdpakete)
    widgets.py               Bausteine
    state.py                 Gemeinsamer Zustand, Hintergrundarbeit
    page_start.py            *Start* - Anmeldung, Originalpaket, Zustand
    page_voice.py            *Fertige Stimmen* - wählen, anhören, aufspielen
    tab_store.py             *Eigene Stimmen*
    tab_builder.py           *Einzelne Ansagen*
    tab_install.py           *Bauen und Aufspielen*
    tab_connect.py           *Verbindung*
```

---


## Entwicklung

Ein einziges Fremdpaket wird gebraucht — `requests`. Insbesondere **nicht**
`python-miio`: Roboter, die in der Dreamehome-App registriert sind, bieten im
Heimnetz keinen miio-Dienst mehr an (siehe oben).

```bash
pip install requests
python selftest.py        # alle Prüfungen, ohne Netz und ohne Roboter
python namecheck.py       # Namen, die es gar nicht gibt
python main.py
```

EXE bauen:

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

Ergebnis: `dist/DreameSprachpaket.exe`, rund 97 MB, ohne Installation
lauffähig. Der Großteil davon sind die eingebauten Stimmen und ffmpeg —
gemessen am Bau von 1.3.0:

| Teil | Größe |
|---|---|
| Programm samt Python und Tk | 13 MB |
| ffmpeg, LZMA-komprimiert angehängt | 39 MB |
| fünf fertige Stimmen, angehängt | 45 MB |

Liegt eine `ffmpeg.exe` im Projektordner, wird sie automatisch mit
eingepackt; ohne sie bleiben die 39 MB weg, und die App lädt ffmpeg bei
Bedarf nach.

---


## Eigene Adressen eintragen

Projektseite und Trinkgeld-Link stehen an **einer** Stelle im Code, in
[`dreamevoice/__init__.py`](../dreamevoice/__init__.py):

```python
PROJEKT_URL = "https://github.com/Anon365-Project/dreame-sprachpaket-manager"
SPENDEN_URL = "https://paypal.me/anon365project"
```

Solange ein Eintrag leer ist, blendet die App den zugehörigen Knopf im
*Über*-Fenster einfach aus — es entstehen keine toten Links.


---

[Zurück zur Übersicht](../README.md)
