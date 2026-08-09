# Vorlage für die Release-Beschreibung

Diese Datei gehört nicht zum Programm. Sie ist eine Vorlage: den Text ab der
nächsten Überschrift kopieren und beim Anlegen eines Releases auf GitHub in
das Beschreibungsfeld einfügen.

Anzuhängende Datei: **`dist/DreameSprachpaket.exe`** — sonst nichts.

---

## v1.1.0 — Eigene Stimmen für deinen Saugroboter

Gib deinem Dreame, MOVA oder Trouver eine eigene Stimme — **ohne Rooting**,
ohne Valetudo, mit einer einzigen portablen EXE.

```
    "So, packma's. I fang zum Saugn o."          Bayerisch
    "Na servas, dann fang ma au. I saug jetzt."  Wienerisch
    "Alaaf, dann jeht et los."                   Kölsch
```

### Zum Loslegen

`DreameSprachpaket.exe` herunterladen und doppelklicken. Keine Installation,
ffmpeg ist eingebaut.

Windows meldet beim ersten Start „Computer geschützt" — die Datei ist nicht
signiert. Über *Weitere Informationen → Trotzdem ausführen* startet sie. Wer
das nicht mag, baut sie sich aus dem Quellcode selbst.

### Was drin ist

* **Sieben Dialekte** mit je 593 Ansagen: Bayerisch, Hessisch, Schwäbisch,
  Sächsisch, Berlinerisch, Wienerisch, Kölsch
* **Eigene Sprachpakete** anlegen — eigene Texte, eigene Stimme, etwa im Stil
  einer Filmfigur
* **Eigene Aufnahmen** einlesen, als `.tar.gz` oder als Ordner mit mp3/wav
* **402 Modelle** geprüft (Dreame, MOVA, Trouver)
* **Lautstärke** wird auf das Niveau der Originalansagen gebracht
* **Originalstimme wiederherstellen** mit einem Klick

### Warum hier keine fertigen Sprachpakete liegen

Die Dialekte stecken als **Texte** in der App — gesprochen wird auf deinem
Rechner. Das hat zwei Gründe: Ein fertiges Paket würde immer nur zu einem
Modell passen, und Sprachausgaben haben eigene Nutzungsbedingungen, die sich
mit der MIT-Lizenz dieses Projekts nicht vertragen. Also wird hier gar kein
fremdes Audio verteilt.

Der Weg dahin dauert wenige Minuten: Tab 4, Dialekt wählen, *Kostprobe
anhören*, *Paket erzeugen*.

### Stimmen

Die **Windows-Sprachausgabe** läuft offline und kostenlos, spricht aber
hochdeutsch — der Dialekt steckt dann nur in der Wortwahl. Für echten Dialekt
in der Aussprache lässt sich auf **ElevenLabs** umschalten (eigener
kostenloser Zugang nötig, 10.000 Zeichen im Monat). Geht das Kontingent
mitten in der Erzeugung aus, bricht die App nicht ab: Das Gesprochene bleibt
gespeichert, und beim nächsten Versuch macht sie genau dort weiter.

### Sicherheit

Es wird keine Firmware angefasst. Dein Paket entsteht als **Kopie** des
offiziellen Pakets, sodass keine Ansage verlorengeht; der Roboter prüft es
selbst gegen MD5 und Größe. Vor dem Senden fragt die App, ob dein Gerät den
Sprachpaket-Dienst überhaupt kennt — wenn nicht, wird gar nichts geschrieben.

### Rechtliches

Privates Freizeitprojekt unter MIT-Lizenz. **Ohne Gewährleistung, ohne
Haftung.** Nicht von Dreame, MOVA, Trouver oder Xiaomi unterstützt oder
geprüft. Die Nutzung erfolgt auf eigene Verantwortung.

### Trinkgeld

Die App ist kostenlos und bleibt es. Wer mag: ☕
**https://paypal.me/anon365project** — freiwillig, ohne Gegenleistung.
