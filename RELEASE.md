# Vorlage für die Release-Beschreibung

Diese Datei gehört nicht zum Programm. Sie ist eine Vorlage: Text kopieren
und beim Anlegen eines Releases auf GitHub in das Beschreibungsfeld einfügen.

---

## v1.1.0 — Eigene Stimmen für deinen Saugroboter

Gib deinem Dreame, MOVA oder Trouver eine eigene Stimme — **ohne Rooting**,
ohne Valetudo, mit einer einzigen portablen EXE.

### Zum Loslegen

`DreameSprachpaket.exe` herunterladen und doppelklicken. Keine Installation,
ffmpeg ist eingebaut.

Windows meldet beim ersten Start „Computer geschützt" — die Datei ist nicht
signiert. Über *Weitere Informationen → Trotzdem ausführen* startet sie.

### Was drin ist

* **Sieben Dialektpakete** mit je 593 Ansagen: Bayerisch, Hessisch,
  Schwäbisch, Sächsisch, Berlinerisch, Wienerisch, Kölsch
* **Eigene Sprachpakete** anlegen — eigene Texte, eigene Stimme
* **Eigene Aufnahmen** einlesen, als `.tar.gz` oder als Ordner mit mp3/wav
* **402 Modelle** geprüft (Dreame, MOVA, Trouver)
* **Lautstärke** wird auf das Niveau der Originalansagen gebracht
* **Originalstimme wiederherstellen** mit einem Klick

### Stimmen

Die **Windows-Sprachausgabe** läuft offline und kostenlos, spricht aber
hochdeutsch — der Dialekt steckt dann nur in der Wortwahl. Für echten Dialekt
in der Aussprache lässt sich auf **ElevenLabs** umschalten (eigener
kostenloser Zugang nötig, 10.000 Zeichen im Monat).

### Sicherheit

Es wird keine Firmware angefasst. Dein Paket entsteht als **Kopie** des
offiziellen Pakets, sodass keine Ansage verlorengeht; der Roboter prüft es
selbst gegen MD5 und Größe. Vor dem Senden fragt die App, ob dein Gerät den
Sprachpaket-Dienst überhaupt kennt — wenn nicht, wird gar nichts geschrieben.

### Dateien in diesem Release

| Datei | Inhalt |
|---|---|
| `DreameSprachpaket.exe` | die Anwendung (51 MB, portabel) |
| `dialekt_bayerisch_x50.tar.gz` u. a. | fertige Dialektpakete für den X50 Ultra Complete |
| `Hoerproben.zip` | drei Sätze je Dialekt |

Die Dialektpakete passen zum **X50 Ultra Complete**. Für andere Modelle
erzeugt die App sie selbst — der Zuschnitt auf dein Gerät passiert dabei
automatisch.

### Rechtliches

Privates Freizeitprojekt unter MIT-Lizenz. **Ohne Gewährleistung, ohne
Haftung.** Nicht von Dreame, MOVA, Trouver oder Xiaomi unterstützt oder
geprüft. Die Nutzung erfolgt auf eigene Verantwortung.

### Trinkgeld

Die App ist kostenlos und bleibt es. Wer mag: ☕
**https://paypal.me/anon365project** — freiwillig, ohne Gegenleistung.
