## v1.2.0 — Aufgeräumt

Gib deinem Dreame, MOVA oder Trouver eine eigene Stimme — **ohne Rooting**,
ohne Valetudo, mit einer einzigen portablen EXE.

```
    "So, packma's. I fang zum Saugn o."                  Bayerisch
    "Ei gude, dann geht's los. Isch fang aa zu sauge."   Hessisch
    "Na servas, dann fang ma au. I saug jetzt."          Wienerisch
    "Na denn los. Ick fang an zu sauje."                 Berlinerisch
```

### Der Weg ist jetzt kurz

Bisher führte „ich will einen bayerisch sprechenden Roboter" über vier
Reiter und einen Umweg durch den Explorer — und die Reihenfolge stand
nirgends. Jetzt sind es zwei Seiten:

1. **Start** — anmelden. Das Originalpaket deines Roboters holt die App
   danach von selbst.
2. **Fertige Stimmen** — Dialekt aussuchen, *Anhören*, *Aufspielen*.

Aus den Reitern ist eine **Seitenleiste** geworden, die nach Häufigkeit
ordnet statt nach Ablauf. Was selten gebraucht wird, steht unter
*Erweitert* — vollständig erhalten, aber aus dem Weg. Einträge, die ohne
Anmeldung sinnlos wären, sind grau und sagen beim Anklicken, woran es
liegt.

### Die Dialekte sind in der EXE

**Kein Download, kein Entpacken, kein Suchen im Explorer.** Bayerisch,
Hessisch, Wienerisch und Berlinerisch mit je 593 gesprochenen Ansagen
stecken in der Programmdatei und werden beim ersten Bedarf ausgepackt.
Die App hängt damit nicht mehr davon ab, dass ein Release im Netz steht.

Die Aufnahmen liegen weiterhin einzeln als `*-Aufnahmen.zip` bereit —
für alle, die eine neuere Fassung wollen oder sie weitergeben.

### Vorher anhören

Vier typische Ansagen — Reinigung startet, Akku schwach, festgefahren,
Rückkehr zur Station — auf Knopfdruck, bevor irgendetwas auf den Roboter
geht. Gefällt es nicht, ist nichts passiert. Der Knopf wird während des
Abspielens zum Stopp; wer sich verklickt hat, muss nicht zwölf Sekunden
zuhören.

### Deutlich schneller

Zwei Bremsen gefunden und gelöst:

* Die Stimmenliste las bei jedem Öffnen über **140 MB** aus der EXE, um
  festzustellen, welche Dialekte dabei sind. Jetzt einmal gelesen und
  gemerkt: **100 ms → 5 ms**.
* Beim Bauen wurde für jede der 593 Ansagen die Lautheit gemessen — knapp
  600 ffmpeg-Aufrufe. Die Werte werden jetzt gemerkt: **59 s beim ersten
  Bau, 5 s bei jedem weiteren**.

### Kleinere Korrekturen

* Im Anmeldeformular standen E-Mail und Passwort nebeneinander statt
  untereinander.
* Die Kennung zeigte immer den zuletzt benutzten Wert. Jetzt bringt jede
  Stimme ihre eigene mit: `BAYERN`, `HESSEN`, `WIEN`, `BERLIN` — so
  verrät die Abfrage am Gerät, welcher Dialekt gerade läuft.
* Ein vorhandenes Paket lässt sich beim Einlesen **ersetzen** statt eine
  zweite Fassung danebenzulegen. Gefragt wird trotzdem, und die Vorgabe
  bleibt das Danebenlegen.
* Neue Farben, runde Ecken, ein echtes Häkchen statt eines schwarzen
  Kreuzes in den Auswahlkästchen.
* Die Hilfe behauptete noch, man müsse ffmpeg selbst danebenlegen — es
  ist längst eingebaut.
* Neu unter *Verbindung*: **Persönliche Daten entfernen** — für alle,
  die die App weitergeben.

### Zum Loslegen

`DreameSprachpaket.exe` herunterladen und doppelklicken. Keine
Installation. ffmpeg und die vier Dialekte sind enthalten; man braucht
sonst nichts.

Windows meldet beim ersten Start „Computer geschützt" — die Datei ist
nicht signiert. Über *Weitere Informationen → Trotzdem ausführen* startet
sie. Wer das nicht mag, baut sie sich aus dem Quellcode selbst.

### Was drin ist

* **Sieben Dialekte** mit je 593 Ansagen: Bayerisch, Hessisch, Schwäbisch,
  Sächsisch, Berlinerisch, Wienerisch, Kölsch — vier davon fertig
  gesprochen mit dabei
* **Eigene Sprachpakete** anlegen — eigene Texte, eigene Stimme
* **Eigene Aufnahmen** einlesen, als ZIP, `.tar.gz` oder Ordner
* **402 Modelle** geprüft (Dreame, MOVA, Trouver)
* **Lautstärke** wird auf das Niveau der Originalansagen gebracht
* **Originalstimme wiederherstellen** mit einem Klick

### Deine Zugangsdaten

Passwort und ElevenLabs-Schlüssel liegen ausschließlich im
**Windows-Anmeldeinformationsspeicher** — nie im Klartext auf der Platte,
nie in der `config.json`, nie in der EXE. Nachgeprüft für diese Fassung:
Arbeitsverzeichnis, EXE, Zwischenstände und die gesamte Git-Historie
wurden nach dem Passwort und dem Schlüssel durchsucht, in sechs
Kodierungen — kein einziger Treffer. Der Selbsttest hält das jetzt fest.

Im Datenordner steht zwar kein Geheimnis, aber Persönliches: E-Mail,
Name und MAC deines Roboters, die IP deines PCs. Wer die App weitergibt,
findet unter *Verbindung* deshalb den Knopf **Persönliche Daten
entfernen** — er räumt genau das weg und lässt die gebauten Pakete und
Dialekttexte stehen.

### Sicherheit

Es wird keine Firmware angefasst. Dein Paket entsteht als **Kopie** des
offiziellen Pakets, sodass keine Ansage verlorengeht; der Roboter prüft
es selbst gegen MD5 und Größe. Vor dem Senden fragt die App, ob dein
Gerät den Sprachpaket-Dienst überhaupt kennt — wenn nicht, wird gar
nichts geschrieben.

Geprüft für diese Fassung: **355 Selbsttests** und ein Praxistest gegen
die echte Cloud und einen echten Roboter.

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
