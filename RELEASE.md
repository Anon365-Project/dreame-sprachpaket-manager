## v1.1.1 — Hessisch dazu

Gib deinem Dreame, MOVA oder Trouver eine eigene Stimme — **ohne Rooting**,
ohne Valetudo, mit einer einzigen portablen EXE.

```
    "Ei gude, dann geht's los. Isch fang aa zu sauge."   Hessisch
    "So, packma's. I fang zum Saugn o."                  Bayerisch
    "Na servas, dann fang ma au. I saug jetzt."          Wienerisch
```

### Neu in dieser Fassung

* **Hessisch überarbeitet** — auf Wunsch aus der Community. Die 593 Ansagen
  sind jetzt durchgehend Frankfurterisch/Rhein-Main geschrieben, mit der
  hessischen Lenisierung (*basst, bidde, Bladd, Debbisch, schdell, schbäder*)
  statt halb hochdeutscher Schreibweise.
* **Hessisch-Aufnahmen.zip** ist neu dabei.

### Kleinere Korrekturen

Beim Überarbeiten sind ein paar Fehler in den hessischen Texten aufgefallen,
die vorher falsch ausgesprochen wurden:

* `Spaeder` (7 Ansagen) — eine Ersatzschreibung ohne Umlaut, die die
  Sprachausgabe als „Spa-e-der" vorgelesen hat. Jetzt `schbäder`.
* `risch` (2 Ansagen) — ein abgeschnittenes Wort, richtig ist `rischtisch`.
* Uneinheitliches `nochema` / `nochemol` und `Reinigung` / `Reinischung`
  vereinheitlicht.
* Die Küche hieß mal `Küch`, mal `Kisch` — im Hessischen immer `Kisch`.

Wer schon v1.1.0 nutzt: Die EXE austauschen lohnt nur, wenn du Hessisch
willst — die Dialekttexte stecken im Programm. Alles andere ist unverändert.

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

### Die fertigen Aufnahmen

Für **Bayerisch, Wienerisch, Berlinerisch und Hessisch** liegen je 593 fertig
gesprochene Ansagen bereit — mit ElevenLabs erzeugt, also echter Dialekt auch
in der Aussprache.

So spielst du sie auf: ZIP entpacken → Tab 4 → *Fertiges Paket einlesen* →
*Ordner mit mp3- oder wav-Dateien* → den entpackten Ordner wählen.

**Warum Aufnahmen und keine fertigen Pakete?** Ein fertiges Sprachpaket
enthält immer die Steuerdateien genau eines Modells. Die Aufnahmen dagegen
passen auf jedes Modell — die App baut daraus das Paket, das zu deinem
Roboter gehört, und nimmt die Steuerdateien aus dessen Originalpaket.

Für die übrigen drei Dialekte — Schwäbisch, Sächsisch, Kölsch — erzeugst du
dir die Aufnahmen in Tab 4 selbst.

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

Privates Freizeitprojekt. **Ohne Gewährleistung, ohne Haftung.** Nicht von
Dreame, MOVA, Trouver oder Xiaomi unterstützt oder geprüft. Die Nutzung
erfolgt auf eigene Verantwortung.

Quellcode und Dialekttexte: **MIT-Lizenz**. Die Audiodateien in den
`*-Aufnahmen.zip` stehen unter eigenen Bedingungen (privat nutzen und
unverändert weitergeben: ja; als Trainingsmaterial oder eigenständiges
Produkt: nein) — siehe `LICENSE-AUDIO.md` im Projekt und die
`LIZENZ-AUDIO.txt` in jedem Archiv.

### Trinkgeld

Die App ist kostenlos und bleibt es. Wer mag: ☕
**https://paypal.me/anon365project** — freiwillig, ohne Gegenleistung.
