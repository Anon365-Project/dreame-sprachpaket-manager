# Dreame Sprachpaket-Manager

**Gib deinem Saugroboter eine eigene Stimme — auf Bayerisch, Kölsch oder
Wienerisch. Ohne Rooting, ohne Bastelei, mit einer einzigen EXE.**

Windows-App für Saugroboter von **Dreame, MOVA und Trouver**. Sie meldet sich
an der Dreame-Cloud an, lädt das offizielle Sprachpaket deines Modells,
tauscht darin die Ansagen aus, die du haben willst, und schickt das Ergebnis
an den Roboter.

Mit dabei: **sieben fertige Dialektpakete** mit je 593 Ansagen — Bayerisch,
Hessisch, Schwäbisch, Sächsisch, Berlinerisch, Wienerisch und Kölsch. Oder du
legst dir eine eigene Textsammlung an, im Stil einer Filmfigur zum Beispiel,
und lässt sie sprechen.

```
    "So, packma's. I fang zum Saugn o."          Bayerisch
    "Na servas, dann fang ma au. I saug jetzt."  Wienerisch
    "Alaaf, dann jeht et los."                   Kölsch
```

**Warum das anders ist als bisherige Lösungen:** Für eigene Sprachpakete
musste man den Roboter bisher rooten und Valetudo aufspielen. Diese App
braucht das nicht — sie geht denselben Weg wie die Dreamehome-App selbst und
nutzt nur die Sprachpaket-Funktion, die der Hersteller ohnehin vorsieht. Ein
Klick stellt die Originalstimme wieder her.

* ✅ **Getestet mit 402 Modellen** von Dreame, MOVA und Trouver
* ✅ **Kein Rooting**, keine Firmware wird angefasst
* ✅ **Portable EXE**, keine Installation, ffmpeg ist eingebaut
* ✅ **Offline nutzbar** mit der Windows-Sprachausgabe — echter Dialekt in der
  Aussprache geht optional über ElevenLabs
* ✅ **Rückweg jederzeit**: Originalstimme direkt von Dreame wiederherstellen

> **Privates Freizeitprojekt, MIT-Lizenz, ohne jede Gewährleistung oder
> Haftung.** Nicht von Dreame unterstützt oder geprüft. Siehe
> [Haftungsausschluss](#haftungsausschluss).
>
> Wenn dir die App gefällt: [☕ Trinkgeld](#ein-trinkgeld) — freiwillig,
> ohne Gegenleistung.

---

## Herunterladen

Es genügt **eine einzige Datei** von den
**[Releases](../../releases/latest)**:

| Datei | Was ist das |
|---|---|
| `DreameSprachpaket.exe` | die App — herunterladen, doppelklicken, fertig |

Die vier fertig gesprochenen Dialekte **sind darin enthalten**: Bayerisch,
Hessisch, Wienerisch und Berlinerisch mit je 593 Ansagen. Ebenso ffmpeg. Man
braucht sonst nichts.

Daneben liegen die Aufnahmen auch einzeln als `*-Aufnahmen.zip`. Die braucht
man nur, wenn man eine neuere Fassung möchte als die in der eigenen EXE, oder
sie an jemanden weitergeben will.

Windows meldet beim ersten Start vermutlich „Computer geschützt" — die EXE ist
nicht signiert (das kostet Geld). Über *Weitere Informationen → Trotzdem
ausführen* startet sie. Wer das nicht mag, baut sie sich aus dem Quellcode
selbst; wie das geht, steht unter [Entwicklung](#entwicklung).

### Warum Aufnahmen und keine fertigen Pakete

Ein fertiges Sprachpaket enthält immer die **Steuerdateien genau eines
Modells** — `dmr_audio.json`, `voice_mapping.json` und weitere, die sich von
Roboter zu Roboter unterscheiden. Ein Paket für den X50 auf einem L10s zu
installieren, würde also fremde Steuerdaten aufspielen.

Die Aufnahmen dagegen passen auf **jedes** Modell. Die App baut daraus das
Paket, das zu deinem Roboter gehört, und nimmt die Steuerdateien aus dessen
Originalpaket. Nachgemessen mit den 593 bayerischen Aufnahmen:

| Zielmodell | Ansagen im Gerät | davon zugeordnet |
|---|---|---|
| `dreame.vacuum.r2532v` | 613 | 593 |
| `dreame.vacuum.r2532h` | 558 | 539 |
| `dreame.vacuum.r2253a` | 401 | 398 |
| `mova.vacuum.r5977e` | 617 | 566 |
| `dreame.vacuum.r63018` | 503 | 490 |

Zu tun ist dafür nichts: **Die vier Dialekte stecken in der Programmdatei**
und werden beim ersten Bedarf einmalig in den Datenordner ausgepackt. Unter
*Fertige Stimmen* aussuchen, anhören, aufspielen — die App wandelt um,
gleicht die Lautstärke an die Originalansagen an und baut das Paket für dein
Modell.

Wer die Aufnahmen trotzdem einzeln haben will — etwa um eine neuere Fassung
zu holen oder sie weiterzugeben — findet sie als Download bei den
[Releases](https://github.com/Anon365-Project/dreame-sprachpaket-manager/releases)
und liest sie über *Eigene Stimmen* → *Aufnahmen einlesen* ein. Eine so
geladene Fassung hat dann Vorrang vor der mitgelieferten.

Die Aufnahmen entstanden mit **ElevenLabs** und sprechen echten Dialekt — auch
in der Aussprache, nicht nur in der Wortwahl. Sie stehen unter eigenen
Bedingungen, siehe [LICENSE-AUDIO.md](LICENSE-AUDIO.md).

Wer lieber selbst erzeugt: *Eigene Stimmen*, Dialekt wählen, *Kostprobe anhören*, *Paket
erzeugen*. Mit der Windows-Sprachausgabe offline und kostenlos — dann steckt
der Dialekt allerdings nur in der Wortwahl.

---

## Schnellstart

1. `python main.py` — oder die fertige `DreameSprachpaket.exe` doppelklicken.
2. **Start:** mit den Dreamehome-Zugangsdaten anmelden. Das Originalpaket
   deines Roboters holt die App danach von selbst — einmalig.
3. **Fertige Stimmen:** Dialekt aussuchen, *Anhören*, *Aufspielen*.

Das ist der ganze Weg. Die vier Dialekte stecken in der Programmdatei, es
wird nichts heruntergeladen.

### Die Seitenleiste

| | |
|---|---|
| **Start** | Anmeldung, Originalpaket, und was der Roboter gerade spricht |
| **Fertige Stimmen** | aussuchen, anhören, aufspielen |
| *Eigene Stimmen* | eigene Texte, weitere Dialekte, Sprachsynthese |
| *Einzelne Ansagen* | Ansage für Ansage eine eigene Datei zuweisen |
| *Bauen und Aufspielen* | der ausführliche Weg mit allen Schaltern |
| *Verbindung* | Konto oder Region wechseln |

Die kursiven Punkte stehen unter **Erweitert** und werden nur gebraucht,
wenn man mehr will als einen der mitgelieferten Dialekte. Graue Einträge
sind nicht kaputt — sie brauchen nur erst die Anmeldung; ein Klick darauf
verrät, was fehlt.

---

## Welche Roboter funktionieren?

**Kurz: alle, für die Dreame selbst Sprachpakete anbietet.** Die App ist an
keiner Stelle auf ein Modell festgelegt — sie fragt für dein Gerät den
offiziellen Katalog ab, lädt dessen Originalpaket und baut das eigene Paket
als Kopie davon.

Nachgeprüft, nicht vermutet: Für alle **714 Modellkennungen**, die im
Originalpaket des X50 vorkommen, wurde der offizielle Katalog abgefragt.

| | Anzahl |
|---|---|
| Modelle mit Sprachpaket-Katalog bei Dreame | **402** |
| davon mit deutschem Paket | **402** (alle) |
| Modelle ohne Katalog (ältere Mi-Home-Geräte) | 312 |

Nach Marke: **288 × `dreame`**, **97 × `mova`**, **17 × `trouver`**.

### Warum das auch für fremde Modelle sicher ist

**Die Ansage-Nummern sind bei allen Modellen dieselben.** Das war die
entscheidende Frage — ein Dialektpaket wäre wertlos oder verwirrend, wenn
Nummer 7 bei einem anderen Roboter etwas anderes bedeutet. Beleg: die Datei
`tts.json` in jedem Paket enthält je Nummer den deutschen Textbaustein. Im
Stichprobenvergleich mit sieben fremden Modellen stimmten diese Texte
**vollständig** überein:

| Modell | Ansagen im Paket | gleiche Textbausteine |
|---|---|---|
| `dreame.vacuum.r2532h` | 558 | 309 / 309 |
| `dreame.vacuum.r501wj` | 588 | 300 / 300 |
| `dreame.vacuum.r63018` | 503 | 309 / 309 |
| `dreame.vacuum.r9535e` | 585 | 271 / 271 |
| `mova.vacuum.r5769t` | 573 | 300 / 300 |
| `mova.vacuum.r5977e` | 617 | 300 / 300 |
| `mova.vacuum.r6710a` | 508 | 300 / 300 |
| `dreame.vacuum.r2253a` | 401 | 236 / 237 |

Dreame nutzt also eine gemeinsame Nummerierung; Abweichungen einzelner
Modelle stehen in `voice_mapping.json` und werden von der App ausgelesen.

Die App passt sich dabei selbst an:

* Der Ansagenkatalog wird auf die Nummern eingeschränkt, die im Paket deines
  Modells wirklich vorkommen (`SoundCatalog.restrict_to`).
* Bei den Dialektpaketen werden Ansagen, die es bei deinem Modell nicht gibt,
  übersprungen — das spart Zeit und bei ElevenLabs bares Kontingent.
* Steuerdateien werden unverändert übernommen, egal wie viele es sind
  (gefunden: zwischen 0 und 6 je nach Modell).

### Eingebaute Bremse

Vor dem Senden fragt die App den Roboter, ob er den Sprachpaket-Dienst
überhaupt kennt (MIoT-Eigenschaft `siid 7 / piid 2`). Antwortet er dort
nicht, wird **gar nichts geschrieben** und die App sagt, warum. So landet
kein Schreibzugriff auf einer unbekannten Eigenschaft — relevant etwa bei
Mährobotern oder sehr alten Geräten aus der Mi-Home-App.

**Faustregel:** Kannst du in der Dreamehome-App unter *Sprachton* eine
Sprache auswählen, funktioniert diese App. Geht das dort nicht, geht es hier
auch nicht.

---

## Warum das den Roboter nicht beschädigt

Das ist die wichtigste Frage, deshalb zuerst.

**Es wird keine Firmware angefasst.** Ein Sprachpaket zu wechseln ist eine
normale, vom Hersteller vorgesehene Funktion. Die Dreamehome-App macht beim
Sprachwechsel exakt denselben Aufruf (MIoT-Eigenschaft `siid 7 / piid 4`).

**Dein Paket ist eine Kopie des Originals.** Die App baut kein Paket aus dem
Nichts. Sie lädt das offizielle Paket deines Modells und tauscht darin nur die
Dateien aus, die du selbst zugewiesen hast. Ein X50-Paket enthält 558 Ansagen
(Variante `r2532h`) bzw. 613 (Variante `r2532v`) und sechs Steuerdateien:

```
0.ogg 1.ogg 2.ogg … 915.ogg      558 bzw. 613 Ansagen
voice_mapping.json               Nummern-Umsetzung zwischen Modellvarianten
tts.json                         Textbausteine des Sprachassistenten
dmr_audio.json                   Abspielparameter je Ansage
first_audio.json                 Ansagen mit Sonderbehandlung
mini_broad.json                  Kurzansage ja/nein
time.txt                         Erstellungszeitpunkt
```

Alle Steuerdateien und alle nicht zugewiesenen Ansagen bleiben Byte für Byte
erhalten. Der Roboter wird also an keiner Stelle stumm. *(Der beiliegende
Selbsttest prüft genau das.)*

**Nummern-Umsetzung.** `voice_mapping.json` hält fest, dass manche Modelle für
eine Ansage eine andere Nummer abspielen — beim X50 Ultra Complete etwa 856
statt 18 („Lädt"), ebenso 863/17, 864/19, 858/112 und 859/140. Wer nur `18.ogg`
austauscht, hört weiterhin das Original. Die App liest diese Umsetzung aus dem
Originalpaket und legt die Aufnahme auf **beide** Nummern.

**Der Roboter prüft selbst.** Mit der URL bekommt er Größe und MD5-Prüfsumme.
Passt etwas nicht, verwirft er das Paket und behält seine bisherige Stimme.

**Es gibt einen Rückweg.** Der Knopf *Originalstimme wiederherstellen* lässt
den Roboter das offizielle Paket direkt bei Dreame laden — dieser PC ist dabei
gar nicht beteiligt. Zusätzlich lässt sich die Sprache jederzeit in der
Dreamehome-App umstellen.

**Eigene Kennung.** Standardmäßig landet dein Paket unter `CUSTOM` und
überschreibt damit nicht die mitgelieferte deutsche Stimme.

---

## Warum kein 32-stelliges Token und kein python-miio

Ältere Dreame-Modelle liefen über Xiaomi Mi Home. Dort gab es je Gerät eine
lokale IP und ein 32-stelliges miio-Token, mit dem man den Roboter direkt im
LAN ansprechen konnte.

Modelle, die in der **Dreamehome**-App registriert sind — dazu gehört der X50
Ultra — machen das nicht mehr. Sie bieten im Heimnetz keinen miio-Dienst an,
und die Cloud gibt weder `localip` noch ein lokales Token heraus. Nachprüfbar
in der Referenz-Implementierung
[Tasshack/dreame-vacuum](https://github.com/Tasshack/dreame-vacuum): dort wird
für Dreamehome-Konten gar keine lokale Verbindung mehr aufgebaut
(`protocol.py`, `if ip and token and account_type == "mi"`).

Diese App geht deshalb denselben Weg wie die Handy-App: Befehle laufen über die
Dreame-Cloud. Nur der Download des Pakets läuft direkt vom PC zum Roboter.
`python-miio` wird dafür nicht gebraucht — `requests` genügt.

---

## Aufbau

```
main.py                      Startpunkt
selftest.py                  Selbsttest der Kernlogik (257 Prüfungen)
namecheck.py                 Sucht unbekannte Namen und Schlüsselwörter
build_exe.ps1                Baut die portable EXE
DreameSprachpaket.spec       PyInstaller-Bauplan

embed_ffmpeg.py              Hängt ffmpeg komprimiert an die fertige EXE

dreamevoice/
  cloud.py                   Dreamehome-Cloud: Anmeldung, Geräte, MIoT-Befehle
  official.py                Offizieller Dreame-Katalog, Download, Prüfsummen
  packer.py                  Paketbau auf Basis des Originals
  audio.py                   Formatprüfung und Umwandlung (OGG Vorbis 16 kHz)
  loudness.py                Lautheit der Originalansagen als Vorlage
  ffmpeg_setup.py            Nutzergesteuerte ffmpeg-Einrichtung
  embedded.py                Liest das an die EXE angehängte ffmpeg
  server.py                  Kurzlebiger Webserver für die Auslieferung
  installer.py               Ablauf: bauen, ausliefern, Auftrag, Überwachung
  community.py               Geprüfte Community-Pakete
  importer.py                Ordner und Archive stapelweise übernehmen
  dialect.py                 Dialektpakete: sprechen, umwandeln, bauen
  textfiles.py               Dialekttexte als Datei aus- und einlesen
  library.py                 Sammlung der gebauten Pakete (Namen, Beschreibung)
  custom.py                  Selbst angelegte Sprachpakete
  dialects/                  Die Texte je Dialekt (7 Module, je 593 Ansagen)
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
    theme.py                 Erscheinungsbild (hell/dunkel, ohne Fremdpakete)
    widgets.py               Bausteine
    state.py                 Gemeinsamer Zustand, Hintergrundarbeit
    tab_connect.py           *Start*
    tab_builder.py           *Einzelne Ansagen*
    tab_install.py           *Fertige Stimmen*
    tab_store.py             *Eigene Stimmen*
```

---

## Audiodateien

Der Roboter versteht ausschließlich **OGG Vorbis, mono, 16000 Hz**. Das wurde
durch Auslesen der offiziellen Pakete bestätigt.

* Fertige `.ogg` in diesem Format funktionieren sofort.
* `mp3`, `wav`, `m4a`, `flac` werden beim Bauen automatisch umgewandelt —
  dafür wird **ffmpeg** gebraucht.

**In der EXE ist ffmpeg bereits enthalten.** Es wird beim ersten Bedarf
einmalig in den Datenordner ausgepackt, danach ist nichts weiter zu tun.

Technisch steckt ffmpeg LZMA-komprimiert (139 MB → 39 MB) hinter dem Ende der
EXE, nicht im PyInstaller-Bündel. Grund: im Onefile-Modus entpackt PyInstaller
bei *jedem* Start alles ins Temp-Verzeichnis — die App würde dann jedes Mal
mehrere Sekunden brauchen, für ein Werkzeug, das viele nie benötigen. So bleibt
es eine einzige portable Datei und der Start unverändert schnell (gemessen:
3,2 s).

Beim Start aus dem Quellcode gibt es diesen Anhang nicht. Dann entweder
`ffmpeg.exe` neben die App legen oder unter *Einzelne Ansagen* auf *ffmpeg automatisch
einrichten* klicken — die App zeigt vorher Quelladresse und Größe an, lädt nur
nach Bestätigung und entnimmt dem Archiv gezielt nur `ffmpeg.exe` und
`ffprobe.exe`.

Halte die Ansagen kurz — die Originale sind meist zwei bis sechs Sekunden lang.

### Lautstärke: genauso laut wie das Original

Eine neue Ansage zwischen lauter deutschen Originalen fällt sofort auf, wenn
sie leiser ist. Deshalb misst die App **jede Originalansage** einmal aus und
gibt der Aufnahme, die sie ersetzt, exakt dieselbe Lautheit.

Gemessen wurde nach, warum das nötig ist: die Originalansagen des X50 liegen
im Median bei −15,9 LUFS und sind randvoll ausgesteuert (Spitzen im Median
+0,2 dBTP). Eine einfache Angleichung „im Vorbeilaufen" (einstufiges
`loudnorm`) verfehlt bei so kurzen Aufnahmen ihr Ziel regelmäßig — im Test
lagen die neuen Ansagen im Median 0,9 dB und im schlechtesten Fall 4,2 dB
darunter. Die App misst stattdessen erst, rechnet die nötige Verstärkung aus,
fängt die Spitzen mit einem Limiter ab und korrigiert nach.

Am fertigen Paket nachgemessen (40 Stichproben gegen die jeweilige
Originalansage): Median 0,00 LU Abweichung, schlechtester Fall 0,82 LU,
**alle 40 innerhalb 1 LU**.

Die Messwerte des Originalpakets liegen als `*.lautstaerke.json` daneben und
werden nur neu erhoben, wenn sich das Paket ändert.

### Viele Dateien auf einmal übernehmen

Hunderte Ansagen einzeln zuzuweisen macht keine Freude. *Einzelne Ansagen* bietet deshalb:

* **Ganzen Ordner importieren** — durchsucht einen Ordner samt Unterordnern und
  ordnet alles zu.
* **Aus Archiv importieren** — dasselbe direkt aus einem `.tar.gz` oder `.zip`.
* **Vorlagenordner anlegen** — legt jede Originalansage bereits richtig benannt
  in einen Ordner, dazu eine `_Anleitung.txt`. Anhören, unter demselben Namen
  neu einsprechen, Ordner importieren — fertig.

Die Zuordnung läuft über die **Zahl im Dateinamen**: `7.ogg`, `007.wav`,
`Ansage_7.ogg` und `7 - Reinigung gestartet.mp3` landen alle bei Ansage 7.
Dateien ohne Zahl werden übersprungen, damit nichts an der falschen Stelle
landet. Vor dem Übernehmen zeigt die App, was neu zugewiesen und was
überschrieben wird.

Auch beim einzelnen *Durchsuchen…* schlägt der Dateidialog den erwarteten
Namen vor — so passt beides zusammen.

---

## Das Paket steht nicht in der Dreamehome-App

Normal, kein Fehler. Die App zeigt unter *Sprachton* nur Sprachen aus Dreames
eigenem Katalog — eine selbst vergebene Kennung wie `CUSTOM` oder `BAYERN`
steht dort nicht drin.

Meldet die Dreamehome-App beim Öffnen, Roboter und App hätten **verschiedene
Spracheinstellungen**, ist das genau das Zeichen dafür, dass dein Paket läuft:
Der Roboter meldet eine Kennung, die die App nicht kennt.

* **Wähle in der Dreamehome-App keine Sprache aus**, solange dein Paket laufen
  soll — damit lädt der Roboter das offizielle Paket nach und überschreibt
  deines.
* Wer es doch in der Liste haben will, installiert unter der Kennung `DE`.
  Dann erscheint es als „Deutsch" und ist auswählbar; dafür ersetzt es die
  mitgelieferte deutsche Stimme. Zurück geht es über *Originalstimme
  wiederherstellen*.

Ob dein Paket läuft, beantwortet unter *Fertige Stimmen* der Knopf **Sprachpaket am Roboter
abfragen** — die Antwort kommt direkt vom Gerät, nicht aus der App.

---

## Wenn der Roboter das Paket nicht abholt

Der häufigste Stolperstein. Der Roboter muss den PC im Netzwerk erreichen:

* Die **Windows-Firewall** muss eingehende Verbindungen erlauben. Beim ersten
  Start fragt Windows nach — dort *Privates Netzwerk* anhaken.
* PC und Roboter müssen im **selben Netz** hängen. Ein getrenntes IoT- oder
  Gast-WLAN verhindert die Verbindung.
* Ein aktives **VPN** auf dem PC leitet die Antwort ins Leere.
* Der Roboter darf nicht im **Tiefschlaf** sein.

Alternative: das gebaute Paket (in `Daten/Meine Pakete/`) auf einen eigenen
Webspace laden und die öffentliche Adresse im Feld *Eigene URL* eintragen.

---

## Fertige Stimmen

Einen echten Store gibt es nicht. Was existiert, sind einige Bastelprojekte auf
GitHub — geprüft und aufgenommen wurden:

| Paket | Quelle | Lizenz |
|---|---|---|
| GLaDOS | [Makers-Im-Zigerschlitz](https://github.com/Makers-Im-Zigerschlitz/voicepacks_dreame) | keine angegeben |
| R2-D2 | dieselbe | keine angegeben |
| Memes | dieselbe | keine angegeben |
| Original Englisch | dieselbe | keine angegeben |
| GLaDOS (15.ai) | [Findus23](https://github.com/Findus23/voice_pack_dreame) | keine angegeben |
| GLaDOS X40, 514 Ansagen | [sproft](https://github.com/sproft/dreame-x40-glados-voice-pack) | siehe Projekt |
| Ukrainisch | [oleksandr-belei](https://github.com/oleksandr-belei/dreame-vacuum-uk-voice-packs) | MIT |

Jeder Download wird gegen die veröffentlichte MD5-Prüfsumme geprüft und
anschließend auf das Originalpaket deines Modells gelegt — was das Fremdpaket
nicht abdeckt, bleibt auf der deutschen Originalstimme.

### Mehrere Fassungen desselben Dialekts

**Ein neues Paket überschreibt nie ein altes.** Das ist wichtiger, als es
klingt: Wer ein bayerisches Paket mit seiner bezahlten ElevenLabs-Stimme
gebaut hat und danach dasselbe Dialektpaket zum Ausprobieren mit einer
Windows-Stimme erzeugt, hätte sonst das erste verloren — Kontingent
verbraucht, Ergebnis weg.

Deshalb fragt die App vor dem Erzeugen nach einem Namen und schlägt einen vor,
der Dialekt **und** Stimme nennt:

```
dialekt_Bayerisch_ElevenLabs_Bairischer_Bua.tar.gz
dialekt_Bayerisch_Windows_Microsoft_Stefan.tar.gz
```

Existiert der Name schon, hängt die App eine Zahl an. Daneben legt sie eine
kleine `.info.json` mit Dialekt, Dienst, Stimme, Datum und Anzahl der Ansagen.

In ***Fertige Stimmen*** stehen alle gespeicherten Pakete in einer Auswahlliste, beschriftet
mit genau diesen Angaben — dort entscheidest du beim Installieren, welche
Fassung auf den Roboter geht.

Auch die gesprochenen Aufnahmen liegen je Stimme getrennt (der Arbeitsordner
enthält Dienst, Stimme und Klangeinstellung im Namen). Ein Wechsel der Stimme
wirft also nichts weg, was schon Kontingent gekostet hat.

---

## Eigene Sprachpakete

Die Auswahl unter *Eigene Stimmen* ist zweigeteilt:

```
Dialekt · Bayerisch        ← die sieben mitgelieferten
Dialekt · Hessisch
...
Eigenes · Bruce Willis     ← selbst angelegt
Eigenes · Pirat
```

**Eigenes Paket anlegen** fragt nach einem Namen und danach, womit du
anfangen willst. Am praktischsten ist die **Kopie eines vorhandenen
Dialekts**: dann stehen alle 593 Ansagen als Vorlage da und du schreibst sie
um, statt bei Null anzufangen. Neben jeder Zeile steht, was sie bedeuten
muss. Wer nur ein paar Ansagen austauschen will, fängt leer an — der Rest
bleibt dann auf der deutschen Originalstimme.

Ein eigenes Paket verhält sich danach **genau wie ein Dialekt**: Kostprobe
anhören, Texte ändern, als Textdatei exportieren und von einer Sprach-KI
überarbeiten lassen, mit jeder Stimme erzeugen, nach aufgebrauchtem
ElevenLabs-Kontingent fortsetzen. Auch *Umbenennen* und *Löschen* gibt es;
beim Umbenennen bleibt der interne Schlüssel erhalten, damit die bereits
gesprochenen Aufnahmen nicht verlorengehen.

Gespeichert wird je Paket eine JSON-Datei in `Daten/Eigene Pakete`. Die lässt
sich weitergeben — wer sie in seinen Datenordner legt, hat dasselbe Paket.

Die Kennung für den Roboter entsteht aus dem Namen (`Bruce Willis` →
`BRUCEWIL`) und wird gegen die offiziellen Sprachkennungen geprüft, damit ein
eigenes Paket nie eine mitgelieferte Sprache überschreibt.

### Aufnahmen einlesen

Derselbe Knopf nimmt fertig gesprochenes Material entgegen:

* **eine ZIP-Datei**, etwa `Bayerisch-Aufnahmen.zip` von der Projektseite —
  direkt auswählen, ohne sie vorher zu entpacken
* **ein fertiges Sprachpaket** als `.tar.gz` oder `.tar`
* **einen Ordner voller mp3-, wav- oder ogg-Dateien**

Die Dateien müssen die Ansage-Nummer im Namen tragen (`7.wav`, `7.mp3`,
`7.ogg`). Ordner im Archiv und Beipackzettel wie `LIESMICH.txt` stören
nicht — es werden nur Audiodateien mit Nummer übernommen. Einen passend
benannten Vorlagenordner legt *Einzelne Ansagen* an — Originale
anhören, unter demselben Namen neu einsprechen, Ordner einlesen.

Alles wird ins Roboterformat umgewandelt, auf die Lautstärke der
Originalansagen gebracht und als Kopie des Originalpakets gebaut. Das
Ergebnis landet in derselben Sammlung wie alle anderen Pakete und steht in
*Fertige Stimmen* zur Auswahl.

---

## Dialektpakete

Fertige Dialektpakete gibt es für **keinen** Saugroboter zum Herunterladen —
weder für Dreame noch für Roborock, Xiaomi oder Valetudo. Nachgeprüft: in den
Foren wurden sie oft gewünscht, gebaut hat sie niemand. Vorhanden ist einzig
ein Schweizerdeutsch-Paket für den Roborock S5. Es gibt also kein Fremdpaket
zum Umbauen.

Die App erzeugt sie deshalb selbst. Sieben Dialekte, von Hand geschrieben
(nicht übersetzt — wörtliche Übertragungen klingen in keinem Dialekt
natürlich). Die 117 schematischen Ansagen (Akkustand 0–100 %,
Raumbestätigungen) entstehen aus Satzmustern statt aus Tipparbeit.

**Alle sieben Dialekte sind vollständig**: je 593 Texte. Mit der
Nummern-Umsetzung des Modells sind das 598 der 613 Ansagen des r2532v
(bzw. alle sprachlichen Ansagen des r2532h). Was bewusst im Original
bleibt, sind ausschließlich Klänge ohne Sprache — Startton, Piepser,
Tierlaute.

Der Wortlaut von 90 Ansagen steht in keiner Textdatei des Pakets. Er wurde
aus den deutschen Originalaufnahmen transkribiert (Windows-Spracherkennung)
und danach von Hand geglättet: sinngemäß richtig, im Wortlaut sinnvoll
gekürzt. Wer es genauer will, hört sich die Originalansage unter *Einzelne Ansagen* an und
ändert den Text im Editor.

| Dialekt | Kennung | Kostprobe (Ansage 7) |
|---|---|---|
| Bayerisch | `BAYERN` | „So, jetzt legn ma los. I fang zum Saugn o." |
| Hessisch | `HESSEN` | „Ei gude, dann geht's los. Isch fang aa zu sauge." |
| Schwäbisch | `SCHWABE` | „So, jetzt gohts los. I fang a zom Sauga." |
| Sächsisch | `SACHSE` | „Nu, dann gehds los. Isch fange an zu saugen." |
| Berlinerisch | `BERLIN` | „Na denn los. Ick fang an zu sauje." |
| Wienerisch | `WIEN` | „Na servas, dann fang ma an. I saug jetzt." |
| Kölsch | `KOELN` | „Alaaf, dann jeht et los. Ich fange aan ze sauge." |

Selbst erzeugte Pakete landen im Ordner `Daten/Meine Pakete`. Für Bayerisch,
Wienerisch, Berlinerisch und Hessisch gibt es fertig gesprochene Aufnahmen
zum Herunterladen — siehe [Warum Aufnahmen und keine fertigen
Pakete](#warum-aufnahmen-und-keine-fertigen-pakete).

### Vorher anhören und Texte anpassen

**Kostprobe anhören** spricht drei Sätze mit der gerade gewählten Stimme und
spielt sie ab — so lässt sich vor dem Erzeugen entscheiden, ob einem Dialekt
und Stimme gefallen.

**Texte ansehen und ändern** öffnet alle 593 Ansagen als Liste: Nummer,
editierbarer Dialekttext, darunter die Bedeutung auf Hochdeutsch. Jede Zeile
lässt sich umformulieren, eine Suche filtert die Liste.

Die eigenen Fassungen liegen in der `config.json` und überleben Neustarts.
Gespeichert wird nur, was vom mitgelieferten Text *abweicht* — eine neue
Programmfassung bringt also verbesserte Standardtexte für alles mit, was du
nicht selbst angefasst hast. *Auf Standard zurücksetzen* verwirft die eigenen
Änderungen.

Wichtig: Ändert sich ein Text, wird die bereits gesprochene Aufnahme dieser
Ansage verworfen, damit sie beim nächsten Erzeugen wirklich neu entsteht. Alle
übrigen Aufnahmen bleiben liegen und kosten kein Kontingent.

### Alle Texte als Datei — für die Überarbeitung durch eine Sprach-KI

593 Ansagen einzeln im Fenster durchzugehen ist Arbeit für einen Abend. Deshalb
liegt jeder Dialekt zusätzlich als Textdatei in `Daten/Dialekttexte`. Sie
entstehen beim ersten Start von selbst; *Texte als Dateien ausgeben* schreibt
sie mit dem aktuellen Stand neu.

```
Daten/Dialekttexte/
  bayerisch.txt  hessisch.txt  schwaebisch.txt  saechsisch.txt
  berlinerisch.txt  wienerisch.txt  koelsch.txt
```

Der Ablauf: Datei kopieren → einer Sprach-KI zum Überarbeiten geben → Antwort
zurück in die Datei einfügen → in der App auf *Texte aus Datei einlesen*. Ein
passender Auftragstext steht oben in jeder Datei.

Aufbau je Zeile — die mittlere Spalte sagt der KI, was die Ansage bedeutet:

```
   7 | Reinigung gestartet | So, jetzt legn ma los. I fang zum Saugn o.
  40 | Roboter steckt fest | Zefix, i häng fest. Kannst mi bittschön befrein?
```

Das Einlesen ist absichtlich nachsichtig, weil KI-Antworten selten exakt das
Format halten:

* Gezählt wird die Nummer und alles hinter dem **zweiten** senkrechten Strich.
  Die mittlere Spalte darf sich ändern, ein `|` im Dialekttext stört nicht.
* Zeilen mit `#`, Leerzeilen und alles, was nicht mit einer Zahl beginnt
  („Hier ist die überarbeitete Fassung:"), werden überlesen.
* Fehlende Zeilen bleiben unverändert — man kann also auch nur einen Ausschnitt
  überarbeiten lassen.
* Erfundene Nummern werden gemeldet, nicht übernommen.

Vor dem Übernehmen zeigt die App, wie viele Texte sich ändern. Verworfen werden
nur die Aufnahmen der tatsächlich geänderten Ansagen.

### Wer spricht — und wie echt klingt der Dialekt?

**Windows-Sprachausgabe** (Voreinstellung): offline, kostenlos, sofort
einsatzbereit. Der Dialekt steckt dabei aber nur in Wortwahl und lautgetreuer
Schreibweise; die Aussprache bleibt hochdeutsch. Windows bringt keine
Dialektstimmen mit.

Zur Auswahl stehen alle installierten deutschen Stimmen, **männliche zuerst**.
Wichtig: `System.Speech` kennt unter Deutsch nur die weibliche *Hedda*. Die
männliche *Stefan* und *Katja* sind sogenannte OneCore-Stimmen — die App holt
sie über die Windows-Runtime, ganz ohne Administratorrechte.

**ElevenLabs**: liefert echten Dialekt auch in der Aussprache. Nachgeprüft,
warum es dafür einen Onlinedienst braucht — ein frei verfügbares bayerisches
Sprachmodell existiert nicht: [Piper](https://github.com/rhasspy/piper) hat nur
Hochdeutsch, [Thorsten-Voice](https://huggingface.co/Thorsten-Voice) hat
Dialektmodelle, aber nur Hessisch, und der einzige bayerische Sprachkorpus
(Betthupferl) gehört dem Bayerischen Rundfunk und ist nicht frei nutzbar.

ElevenLabs bietet [deutschen Bavarian-Accent-Sprachausgabe](https://elevenlabs.io/text-to-speech/german-bavarian-accent)
ausdrücklich an, mit 10.000 Freizeichen im Monat. Du brauchst ein eigenes
(kostenloses) Konto; die App legt keins an und verwendet keinen fremden
Schlüssel. Der Schlüssel wird wie das Dreame-Passwort mit der Windows-DPAPI
verschlüsselt abgelegt, übertragen werden nur die Ansagetexte.

**Zugangsschlüssel:** [elevenlabs.io/app/settings/api-keys](https://elevenlabs.io/app/settings/api-keys)
— oder unten links aufs Profil, dann *Settings → API Keys → Create API Key*.
Der Schlüssel wird nur einmal vollständig angezeigt.

**Eigene Stimme benutzen:** Die als „bayerisch" ausgewiesenen Stimmen aus der
ElevenLabs-Bibliothek klingen erfahrungsgemäß wenig bayerisch. Besser: in
ElevenLabs mit *Voice Design* eine eigene bauen, dort die Stimmen-ID kopieren
(drei Punkte an der Stimme → *Copy Voice ID*) und im Feld **Eigene Stimmen-ID**
eintragen. Die App holt sie dann direkt — sie muss in keiner Liste stehen.

### Wie viel Kontingent braucht das?

| | Zeichen | Freikontingent (10.000/Monat) |
|---|---|---|
| Der gemeinsame Kern (239 Ansagen) | 7.200–7.900 | reicht |
| Ein vollständiges Dialektpaket (593 Ansagen) | 22.900–25.000 | reicht nicht — drei Monate oder Starter-Tarif |

**Abbrechen jederzeit.** Neben *Paket erzeugen* sitzt ein Abbrechen-Knopf.
Wer sich verklickt hat, muss nicht zusehen, wie sein Guthaben verbraucht wird:
die laufende Ansage wird noch zu Ende gesprochen, dann ist Schluss. Alles
bereits Gesprochene bleibt gespeichert - beim nächsten Anlauf macht die App
genau dort weiter. Der Knopf ist bewusst nur aktiv, wenn der laufende Vorgang
wirklich auf einen Abbruch hört.

Wird das Kontingent mitten in der Erzeugung leer, bricht die App **nicht** ab:
Das bereits Gesprochene bleibt gespeichert, das Paket wird mit dem fertigen
Teil gebaut, der Rest bleibt auf der deutschen Originalstimme. Beim nächsten
Versuch macht die App genau dort weiter und fordert nur noch das Fehlende an.
So lässt sich ein großes Paket über zwei Monate hinweg fertigstellen, ohne
einen Cent zu zahlen.

### Was die App bewusst nicht tut

Die Stimme einer real existierenden Person nachbilden — etwa aus
YouTube-Aufnahmen oder fremden Sprachpaketen. Das berührt das
Persönlichkeitsrecht, bei Schauspielern kommen Verwertungsrechte dazu. Wer eine
echte, eigene Dialektstimme will: die Ansagen selbst einsprechen und unter *Einzelne Ansagen*
zuweisen — die Textlisten sind dafür eine fertige Vorlage.

---

## Datenschutz

* E-Mail und Passwort gehen ausschließlich an die Dreame-Server.
* Das Passwort wird nur gespeichert, wenn du es ausdrücklich möchtest, und
  dann mit der Windows-DPAPI verschlüsselt (gebunden an dein Windows-Konto).
* Alle Dateien liegen im Ordner `Daten` neben der App. Zum Entfernen genügt
  es, diesen Ordner zu löschen.
* Die App sendet keinerlei Nutzungsdaten.

---

## Entwicklung

Ein einziges Fremdpaket wird gebraucht — `requests`. Insbesondere **nicht**
`python-miio`: Roboter, die in der Dreamehome-App registriert sind, bieten im
Heimnetz keinen miio-Dienst mehr an (siehe oben).

```bash
pip install requests
python selftest.py        # 257 Prüfungen, alle offline
python namecheck.py       # Namen, die es gar nicht gibt
python main.py
```

EXE bauen:

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

Ergebnis: `dist/DreameSprachpaket.exe`, rund 51 MB, ohne Installation lauffähig.
Liegt eine `ffmpeg.exe` im Projektordner, wird sie automatisch mit eingepackt;
ohne sie entsteht eine 12-MB-EXE, die ffmpeg bei Bedarf nachlädt.

---

## Lizenz

**Quellcode: MIT-Lizenz** — siehe [LICENSE](LICENSE). Du darfst die App
benutzen, verändern, weitergeben und auch in eigene Projekte übernehmen,
kommerziell wie privat. Einzige Bedingung: der Copyright-Hinweis und der
Lizenztext bleiben erhalten. Das gilt auch für die **Dialekttexte** — die sind
Teil des Quellcodes.

**Audiodateien: eigene Bedingungen** — siehe
[LICENSE-AUDIO.md](LICENSE-AUDIO.md). Die Aufnahmen in den Releases wurden mit
ElevenLabs erzeugt; eine so weitgehende Lizenz wie MIT lässt sich dafür nicht
erteilen. Privat nutzen und unverändert weitergeben: ja. Als Trainingsmaterial
für Sprachmodelle oder als eigenständiges Produkt verkaufen: nein.

---

## Haftungsausschluss

**Das hier ist ein privates Freizeitprojekt. Es gibt keine Garantie, keine
Zusicherung und keine Haftung — für gar nichts.**

* Die Software wird „wie besehen" bereitgestellt (`AS IS`), ohne Gewähr für
  Funktion, Eignung oder Fehlerfreiheit. Das ist keine Floskel, sondern der
  ausdrückliche Inhalt der MIT-Lizenz, unter der du sie bekommst.
* **Die Nutzung erfolgt auf eigene Verantwortung und auf eigenes Risiko.**
  Für Schäden an Roboter, Basisstation, Daten oder sonstigem Eigentum wird
  keine Haftung übernommen — soweit gesetzlich zulässig.
* Dieses Projekt steht in **keiner Verbindung zu Dreame, MOVA, Trouver oder
  Xiaomi**. Es ist von diesen Herstellern weder unterstützt noch geprüft noch
  genehmigt. Alle Marken- und Produktnamen gehören ihren jeweiligen Inhabern.
* Ein eigenes Sprachpaket ist **kein bestimmungsgemäßer Gebrauch** im Sinne
  des Herstellers. Ob dadurch Gewährleistungs- oder Garantieansprüche berührt
  werden, entscheidet allein der Hersteller. Kläre das im Zweifel vorher.
* Die App nutzt ausschließlich die vom Hersteller vorgesehene
  Sprachpaket-Funktion, fasst keine Firmware an und lässt sich jederzeit
  rückgängig machen (*Originalstimme wiederherstellen*). Das senkt das Risiko
  erheblich — eine Garantie ist es trotzdem nicht.

Wer damit nicht einverstanden ist, benutzt die App bitte nicht.

---

## Ein Trinkgeld?

In dieser App stecken viele Stunden Feierabend und Wochenende: das Protokoll
der Dreame-Cloud auseinandernehmen, herausfinden warum ausgetauschte Ansagen
stumm bleiben (es war die Nummern-Umsetzung), nachmessen warum eigene
Aufnahmen leiser klingen als die Originalen, und 593 Ansagen in sieben
Dialekten schreiben. Nichts davon musste sein — es hat einfach Spaß gemacht.

**Die App ist und bleibt kostenlos.** Sie liegt hier mit allem Quellcode, du
darfst sie benutzen, verändern und weitergeben.

Wenn sie dir etwas wert ist und du dich über deinen Roboter im Dialekt
gefreut hast, freue ich mich über ein Trinkgeld:

### ☕ [paypal.me/anon365project](https://paypal.me/anon365project)

Derselbe Link steht in der App unter *Über*.

Und damit das klar ist: Ein Trinkgeld ist eine **Schenkung**, keine Bezahlung
für ein Produkt. Es gibt dafür keine Gegenleistung, keinen Support-Anspruch
und keine bevorzugte Behandlung. Wer nichts gibt, bekommt genau dieselbe
Software — und ist genauso willkommen. Am Haftungsausschluss unten ändert ein
Trinkgeld nichts.

Genauso hilfreich und völlig kostenlos: einen Fehler melden, eine Verbesserung
für die Dialekttexte schicken, oder die App jemandem zeigen, der einen Dreame
hat.

---

## Eigene Adressen eintragen

Projektseite und Trinkgeld-Link stehen an **einer** Stelle im Code, in
[`dreamevoice/__init__.py`](dreamevoice/__init__.py):

```python
PROJEKT_URL = "https://github.com/Anon365-Project/dreame-sprachpaket-manager"
SPENDEN_URL = "https://paypal.me/anon365project"
```

Solange ein Eintrag leer ist, blendet die App den zugehörigen Knopf im
*Über*-Fenster einfach aus — es entstehen keine toten Links.
