## v1.4.0 — Servitor und eine Liste für alle Stimmen

Gib deinem Dreame, MOVA oder Trouver eine eigene Stimme — **ohne Rooting**,
ohne Valetudo, mit einer einzigen portablen EXE.

```
    "So, packma's. I fang zum Saugn o."                  Bayerisch
    "Ei gude, dann geht's los. Isch fang aa zu sauge."   Hessisch
    "Na servas, dann fang ma au. I saug jetzt."          Wienerisch
    "Na denn los. Ick fang an zu sauje."                 Berlinerisch
```

### Neu: Servitor, ein Community-Pack von Carnimo

Die erste Stimme, die nicht aus diesem Projekt stammt: **Carnimo** hat ein
komplettes Sprachpaket geschrieben, mit ElevenLabs vertont und auf seinem
X50 Ultra Complete im Alltag getestet. Eine **männliche, mechanische Stimme**
wie aus einer düsteren Maschinenkathedrale — die Station heißt Schrein, das
WLAN Funkkommunion, das Wasser heiliges Reinigungsfluid.

**590 Ansagen**, fest in der App enthalten. In der Liste steht direkt
daneben *Community-Pack von Carnimo* — wer die Stimme gemacht hat, soll man
sehen, ohne suchen zu müssen. Danke, Carnimo!

Sein Paket brachte 620 Tondateien mit; 30 davon waren Dreames eigene
Aufnahmen (Startton, Signaltöne). Die sind nicht im Archiv — die App nimmt
sie beim Aufspielen aus dem Originalpaket deines Roboters, passend zu
deinem Modell.

### Eine Liste für alle Stimmen

Unter *Fertige Stimmen* standen bisher die eingebauten Stimmen klein in
einer Klappliste — und die freien Stimmen aus dem Netz groß auf einer ganz
anderen Seite. Jetzt steht alles gleich groß in **einer Liste**:

* **In der App enthalten** — die sechs eingebauten Stimmen
* **Eigene** — was du selbst gebaut hast
* **Freie Stimmen aus dem Netz** — GLaDOS, R2-D2 und die anderen

### Auch freie Stimmen vorher anhören

GLaDOS & Co. musste man bisher erst herunterladen und bauen, bevor man
überhaupt etwas hören konnte. Jetzt genügt **Anhören** — die App lädt die
Stimme dafür kurz herunter, und der Knopf sagt vorher, wie viel. Gefällt
sie, erledigt **Aufspielen** den Rest in einem Zug. Ein Schritt und eine
ganze Seite weniger.

### Eine Seite weniger, nichts verloren

*Einzelne Ansagen* gibt es nicht mehr als eigene Seite. Was dort ging, geht
jetzt unter **Eigene Stimmen**: ein Knopf öffnet die Liste aller Ansagen,
jede kann eine eigene Audiodatei bekommen — und **derselbe Knopf baut daraus
das Paket**. Vorher standen dieselben Schaltflächen auf zwei Seiten, und
gebaut wurde auf einer dritten.

### Fremde Pakete werden vorher geprüft

Wer ein Sprachpaket aus dem Netz einliest, bekommt es jetzt zuerst
angesehen: Steckt Programmcode zwischen den Ansagen? Bricht ein Eintrag
beim Auspacken aus seinem Ordner aus? Versteckt sich ein Archiv im Archiv?
Auffälliges wird gemeldet, Gefährliches gar nicht erst eingelesen.

Das ist kein Virenscanner und ersetzt keinen. Es schließt die Lücke, die
ein Virenscanner hier hat: **Dein Roboter läuft unter Linux.** Ein
Linux-Programm zwischen den Ansagen ist für Windows eine unauffällige
Datei — für den Roboter wäre es ausführbarer Code.

### Alles unter CUSTOM, auch Eigenes

Der Roboter legt je Kennung einen eigenen Ordner an, und löschen kann man
die über die Cloud nicht. Seit 1.3.0 geht deshalb alles unter `CUSTOM` raus
— jetzt zeigt die App auch bei selbst erstellten Paketen keine andere
Kennung mehr an. Ein Ordner, der sich selbst überschreibt.

### Keine Doppel mehr unter „Eigene“

Beim Aufspielen einer fertigen Stimme legte die App bisher jedes Mal ein
weiteres Paket unter *Meine Pakete* ab (`Bayerisch_fertig.tar.gz`,
`Bayerisch_fertig_2.tar.gz` …), und die tauchten dann als „eigene Stimme“
auf. Diese Zwischenschritte liegen jetzt in einem eigenen Unterordner und
überschreiben sich. Die alten werden ausgeblendet, aber **nicht gelöscht** —
wer sie loswerden will, löscht sie selbst.

### Aktualisieren klappt jetzt auch mehrmals hintereinander

Nach einer Aktualisierung startete die neue Fassung nicht ganz eigenständig:
Sie lief mit Teilen der alten weiter, und ein unsichtbarer Rest der alten
Fassung blieb bis zur Abmeldung hängen. Beim ersten Mal fiel das nicht auf,
eine zweite Aktualisierung wäre aber daran gescheitert. Das ist behoben;
wer aus 1.3.0 kommt, bei dem räumt 1.4.0 das beim ersten Start selbst auf.

Getestet mit echten Programmdateien von 1.3.0 und 1.2.0 gegen vorgespielte
Releases bis Version 10.0: Jede Fassung ab 1.3.0 findet die jeweils neueste
und spielt sie ein. **1.2.0 kennt noch keine Aktualisierung** — wer die
hat, lädt 1.4.0 einmal von Hand herunter.

### Freie Stimmen klingen jetzt so laut wie die Originalansagen

GLaDOS und die anderen Stimmen aus dem Netz kamen bisher unverändert auf
den Roboter und waren im Schnitt gut ein Dezibel leiser als die deutschen
Ansagen. Jetzt bekommt jede übernommene Ansage die Lautheit der Ansage,
die sie ersetzt — dieselbe Angleichung, die eigene Pakete schon hatten.

### Kleinere Korrekturen

* In den Beipackzetteln aller Stimmen-Archive stand **`OHNE GEWAEHR`** —
  jetzt mit Umlaut.
* Fehlte das Originalpaket, schickte die Meldung zu einer Seite, auf der es
  gar nicht mehr geholt wird.

### Zum Loslegen

`DreameSprachpaket.exe` herunterladen und doppelklicken. Keine Installation.
ffmpeg und alle sechs Stimmen sind enthalten; man braucht sonst nichts.

Windows meldet beim ersten Start „Computer geschützt" — die Datei ist nicht
signiert. Über *Weitere Informationen → Trotzdem ausführen* startet sie. Wer
das nicht mag, baut sie sich aus dem Quellcode selbst.

### Was drin ist

* **Sechs fertige Stimmen**: Bayerisch männlich und weiblich, Hessisch,
  Wienerisch, Berlinerisch und Servitor — sofort einsatzbereit,
  nichts nachzuladen
* **Freie Stimmen aus dem Netz** wie GLaDOS, vor dem Aufspielen anhörbar
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

Geprüft für diese Fassung: **1048 Selbsttests** in 54 Abschnitten, darunter
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

Servitor ist ein Beitrag von Carnimo und steht unter seinen
Bedingungen: ein inoffizielles, nicht kommerzielles Fan-Sprachpaket, privat
nutzbar und unverändert kostenlos weiterzugeben. Details in
`LIZENZ-AUDIO.txt` im Archiv `Servitor-Aufnahmen.zip`.

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

Das ist einmalig nötig; danach startet sie normal. Seit 1.3.0 stellt
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
7466ffc580464033890a0cddd9344d27ca91e1033a25034becf05400c35fcd85
```

Größe: 111.194.102 Byte (106,0 MB), Dateiversion 1.4.0.0.

Nachrechnen unter Windows:
`certutil -hashfile DreameSprachpaket.exe SHA256`
