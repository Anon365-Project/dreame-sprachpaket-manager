<!-- Ausgelagert aus der README, damit die Startseite kurz bleibt.
     Inhalt unverändert. -->

# Technische Hintergründe

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


---

[Zurück zur Übersicht](../README.md)
