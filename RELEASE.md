## v1.3.0 — Eine Frauenstimme, und mehr Ehrlichkeit

Gib deinem Dreame, MOVA oder Trouver eine eigene Stimme — **ohne Rooting**,
ohne Valetudo, mit einer einzigen portablen EXE.

```
    "So, packma's. I fang zum Saugn o."                  Bayerisch
    "Ei gude, dann geht's los. Isch fang aa zu sauge."   Hessisch
    "Na servas, dann fang ma au. I saug jetzt."          Wienerisch
    "Na denn los. Ick fang an zu sauje."                 Berlinerisch
```

### Bayerisch, jetzt auch weiblich

Auf Wunsch aus dem Forum. **598 Ansagen**, dieselbe Sorgfalt wie bei den
anderen: echter Dialekt in der Aussprache, jede Ansage auf den Pegel der
Originalansage gebracht, die sie ersetzt.

Damit stehen fünf Stimmen zur Auswahl, und sie heißen jetzt auch so:
`Bayerisch (männlich)`, `Bayerisch (weiblich)`, `Hessisch (männlich)`,
`Wienerisch (männlich)`, `Berlinerisch (männlich)`. Das Geschlecht stand
vorher klein hinten in der Klammer und ging unter.

### Zehnmal schneller beim Start

Gemessen, nicht geschätzt: Die App baute beim Start **über tausend
Bedienelemente** — auch für die vier Seiten unter *Erweitert*, die die
meisten nie öffnen. Mittendrin lief ein blockierender PowerShell-Aufruf, um
die Windows-Stimmen aufzuzählen.

```
Fenster aufbauen    2458 ms  →  238 ms
```

Die Seiten entstehen jetzt beim ersten Öffnen. Wer nur eine andere Stimme
will, zahlt für den Rest nichts mehr.

### Sie überschreiben sich, statt sich anzusammeln

Ein Forumsnutzer hat genau richtig gefragt: *„Wird immer wieder die Datei
überschrieben oder jedes Mal zusätzlich eine angelegt?"* Es wurde
angesammelt — und das war ein Fehler.

Der Roboter legt je Kennung einen eigenen Ordner an, und **löschen kann man
den über die Cloud nicht**. In 1.2.0 brachte jede Stimme ihre eigene Kennung
mit (`BAYERN`, `HESSEN`, …), also blieb bei jedem Dialekt ein Ordner zurück.
Ab jetzt geht alles unter `CUSTOM` raus, fest und nicht mehr einstellbar:
ein Ordner, der sich selbst überschreibt, egal wie oft du wechselst.

Wer schon mehrere Dialekte aufgespielt hat, trägt die alten Ordner weiter mit
sich — rund 8 MB je Stimme. Wegbekommen wir sie nicht, aber es kommt nichts
mehr dazu.

### Sich selbst aktualisieren

Neu oben rechts, neben *Hilfe* und *Über*: Die App kann nachsehen, ob es
eine neuere Fassung gibt — beim Start oder auf Knopfdruck.

Wie das ohne Installation geht: Windows lässt eine laufende Programmdatei
nicht überschreiben, **wohl aber umbenennen**. Die App lädt die neue Fassung
daneben, vergleicht die Prüfsumme, legt sich selbst beiseite und rückt die
neue an ihren Platz. Schlägt etwas fehl, wird der Schritt zurückgenommen —
es gibt zu keinem Zeitpunkt einen Zustand ohne startfähige Datei. Ohne
Prüfsumme wird gar nicht erst geladen.

Ein Nebeneffekt, der einiges wert ist: Eine Datei, die *die App selbst* holt,
bekommt **kein „Mark of the Web"** — das setzt nur der Browser. Die
SmartScreen-Warnung beim Start entfällt damit.

**Ab Werk ausgeschaltet.** Die Abfrage geht an GitHub und verrät dadurch,
dass hier jemand diese App benutzt. Das gehört gefragt, nicht angenommen.

### Wenn die App etwas nicht weiß, sagt sie es

Der größte Teil dieser Fassung steckt in etwas, das man nicht sieht: Die App
hat an mehreren Stellen Erfolg gemeldet, ohne ihn belegen zu können.

* Sie meldete *„Das Originalpaket ist wieder aktiv"*, während der Roboter im
  **selben Datensatz** eine andere Sprache als aktiv meldete.
* Ein einzelner Netzaussetzer während der Installation galt als Beweis, dass
  der Roboter etwas getan hat — er hatte nichts getan.
* Ein hochzählender Fortschrittswert in der Zustandsmeldung genügte ebenso.
* Eine stehengebliebene Fehlermeldung vom letzten Versuch würgte jeden neuen
  sofort ab. Für einen Laien eine Sackgasse ohne Ausweg.

Jetzt zählt als Beweis nur eine **beobachtete Veränderung** am Roboter. Reicht
das nicht, sagt die App *„übertragen"* statt *„installiert und aktiv"* — mit
gelber Plakette und dem Hinweis, einmal hinzuhören. Das ist weniger schön und
mehr wert.

Ebenso raus: die Zeile *„Lautstärke gesetzt — kein Neustart nötig"*. Sie
versprach etwas, das die App nicht halten kann, und redete genau das aus, was
als einziges hilft.

### Dialekte erzeugen geht jetzt viermal schneller

Wer sich eine eigene Stimme mit ElevenLabs sprechen lässt, wartete
bisher zehn bis zwanzig Minuten. Der Grund war banal: Die App fragte
eine Ansage nach der anderen und wartete dazwischen.

```
593 Ansagen erzeugen    11,9 min  →  2,7 min
```

Jetzt laufen mehrere gleichzeitig, und die Anzahl regelt sich selbst.
Bremst ElevenLabs, geht die App sofort zurück und versucht es erneut —
eine abgewiesene Anfrage kostet kein Kontingent. Was schon gesprochen
ist, bleibt wie bisher liegen: Ein großes Paket lässt sich weiterhin
über mehrere Anläufe fertigstellen.

### MOVA und Trouver lassen sich endlich anmelden

Die App wirbt seit jeher mit drei Marken, und im Code lagen alle drei
Mandanten fertig bereit — nur ließ sich nirgends einstellen, welche es sein
soll. Jedes Konto ging an den Dreame-Mandanten, MOVA- und Trouver-Anmeldungen
scheiterten ohne erkennbaren Grund. Beide Anmeldeformulare haben jetzt eine
Auswahl **App**.

### Besser zu sehen

Im dunklen Design war die Fläche eines Knopfes *dunkler* als die Karte, auf
der er lag — Kontrast 1,06:1. Man erkannte Knöpfe nur am Text. Der Rand der
Auswahlkästchen lag bei 1,26:1. Beides neu gezeichnet, jetzt über den 3:1,
die die Norm für Bedienelemente verlangt.

### Kleinere Korrekturen

* Ein Paketname mit **Leerzeichen oder Umlaut** ließ den Download scheitern —
  und wurde dann auch noch als Firewall-Problem erklärt.
* Ein **abgebrochener Download** wird nicht mehr mit Firewall und Gast-WLAN
  begründet, wenn der Roboter den PC nachweislich erreicht hat.
* Beim **Einlesen fremder Archive** gab es keine Größengrenze — ein 300 kB
  großes Archiv mit 300 MB Inhalt hätte den Arbeitsspeicher gefüllt.
* Ein **beschädigtes Archiv** kommt jetzt als verständliche Meldung an,
  nicht als englischer Programmabbruch.
* Jedes **Vorhören** ließ einen Ordner im Temp-Verzeichnis zurück. Für immer.
* Der Knopf *Gebautes Paket wählen* war **abgeschnitten**.
* Die Hilfe riet noch zu einer Kennung, die sich gar nicht mehr eingeben
  lässt — eine Anleitung, der niemand folgen konnte.
* In der Hilfe stand **`Dafuer wird ffmpeg gebraucht`**. So ging es quer
  durch die App, die Anleitungen und die beiliegenden Textdateien. Umlaute
  stehen jetzt überall als Umlaute da.
* Die Übersicht der Seiten unter *Erweitert* war in der Hilfe **verschoben**
  — sie stand als Tabelle aus Leerzeichen in einer Schrift, in der nicht
  jeder Buchstabe gleich breit ist.

### Zum Loslegen

`DreameSprachpaket.exe` herunterladen und doppelklicken. Keine Installation.
ffmpeg und alle fünf Stimmen sind enthalten; man braucht sonst nichts.

Windows meldet beim ersten Start „Computer geschützt" — die Datei ist nicht
signiert. Über *Weitere Informationen → Trotzdem ausführen* startet sie. Wer
das nicht mag, baut sie sich aus dem Quellcode selbst.

### Was drin ist

* **Fünf fertige Stimmen**: Bayerisch männlich und weiblich, Hessisch,
  Wienerisch, Berlinerisch — sofort einsatzbereit, nichts nachzuladen
* **Sieben Dialekte** als Text, auch Schwäbisch, Sächsisch und Kölsch — in
  der App selbst vertonbar
* **Eigene Sprachpakete** anlegen: eigene Texte, eigene Stimme
* **Eigene Aufnahmen** einlesen, als ZIP, `.tar.gz` oder Ordner
* **402 Modelle** geprüft (Dreame, MOVA, Trouver)
* **Lautstärke** wird auf das Niveau der Originalansagen gebracht
* **Originalstimme wiederherstellen** mit einem Klick

### Deine Zugangsdaten

Passwort und ElevenLabs-Schlüssel liegen ausschließlich im
**Windows-Anmeldeinformationsspeicher** — nie im Klartext auf der Platte, nie
in der `config.json`, nie in der EXE. Der Selbsttest prüft das bei jedem Lauf
und vergleicht dabei einen Hashwert, nicht nur, *ob* ein Eintrag existiert.

Im Datenordner steht kein Geheimnis, aber Persönliches: E-Mail, Name und MAC
deines Roboters, die IP deines PCs. Wer die App weitergibt, findet unter
*Verbindung* den Knopf **Persönliche Daten entfernen**.

### Sicherheit

Es wird keine Firmware angefasst. Dein Paket entsteht als **Kopie** des
offiziellen Pakets, sodass keine Ansage verlorengeht; der Roboter prüft es
selbst gegen MD5 und Größe. Vor dem Senden fragt die App, ob dein Gerät den
Sprachpaket-Dienst überhaupt kennt — wenn nicht, wird gar nichts geschrieben.

Geprüft für diese Fassung: **901 Selbsttests** in 49 Abschnitten, darunter
nachgestellte Angriffe mit Archivbomben, Pfadausbrüchen, untergeschobenen
Programmen und manipulierten Katalogantworten. Eine der Prüfungen fragt den
echten Dreame-Katalog ab und schlägt an, wenn sich dort etwas ändert.

### Rechtliches

Privates Freizeitprojekt. **Ohne Gewährleistung, ohne Haftung.** Nicht von
Dreame, MOVA, Trouver oder Xiaomi unterstützt oder geprüft. Die Nutzung
erfolgt auf eigene Verantwortung.

Quellcode und Dialekttexte: **MIT-Lizenz**. Die Audiodateien stehen unter
eigenen Bedingungen (privat nutzen und unverändert weitergeben: ja; als
Trainingsmaterial oder eigenständiges Produkt: nein) — siehe
`LICENSE-AUDIO.md`.

### Trinkgeld

Die App ist kostenlos und bleibt es. Wer mag: ☕
**https://paypal.me/anon365project** — freiwillig, ohne Gegenleistung.

---

## Warum warnt Windows vor der Datei?

Beim ersten Start meldet Windows **„Der Computer wurde durch Windows
geschützt"**. Das ist erwartet und kein Zeichen dafür, dass etwas nicht
stimmt.

**Der Grund:** Die Datei ist nicht mit einem Zertifikat signiert. Ein solches
kostet je nach Anbieter 200 bis 600 Euro im Jahr — für ein kostenloses
Freizeitprojekt ohne Einnahmen ist das nicht drin. Ohne Signatur baut
Microsofts SmartScreen erst dann Vertrauen auf, wenn eine Datei oft genug
heruntergeladen wurde.

**So startest du sie trotzdem:**

1. Doppelklick auf `DreameSprachpaket.exe`
2. Im blauen Fenster auf **Weitere Informationen** klicken
   (der Link ist leicht zu übersehen — er steht klein unter dem Text)
3. Auf **Trotzdem ausführen**

Das ist einmalig nötig; danach startet sie normal. Ab dieser Fassung stellt
sich die Frage beim nächsten Mal nicht mehr: Aktualisierungen holt die App
selbst, und dabei entsteht kein „Mark of the Web".

**Wenn „Trotzdem ausführen" fehlt** oder Windows die Datei ohne Rückfrage
blockiert, ist meist **Smart App Control** aktiv (Windows 11, neuere
Installationen). Das erkennst du unter *Windows-Sicherheit → App- und
Browsersteuerung → Smart App Control*. Es lässt unsignierte Programme
grundsätzlich nicht zu und kennt keine Ausnahme für einzelne Dateien.

**Du willst dich nicht darauf verlassen?** Verständlich. Der gesamte
Quellcode liegt offen; wer mag, baut sich die EXE in zwei Minuten selbst
(siehe `docs/Entwicklung.md`) oder startet die App direkt mit `python main.py`.
Dann fragt Windows gar nicht erst.

Zur Kontrolle die SHA-256-Prüfsumme dieser EXE:

```
bb9d99bef7bb5e22e8fe2bebe5dad4b95fbd64b0e0eb7b97b0b7252adc802007
```

Größe: 101.700.582 Byte (97,0 MB), Dateiversion 1.3.0.0.

Nachrechnen unter Windows:
`certutil -hashfile DreameSprachpaket.exe SHA256`
