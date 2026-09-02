# Änderungen

Vollständige Liste der Änderungen je Fassung. Die kurze, für Nutzer
geschriebene Fassung steht in [RELEASE.md](RELEASE.md).

---

## v1.3.0 — seit v1.2.0

28 Quelldateien geändert, 3 neue Module, rund 5.000 Zeilen dazu.
Der Selbsttest wuchs von 287 auf 617 Prüfstellen im Code und von 31
auf 49 Abschnitte; ein Lauf führt daraus 901 Prüfungen aus.

### Neue Funktionen

- **Bayerisch (weiblich)** — 598 Ansagen, mit ElevenLabs gesprochen, in
  der Programmdatei enthalten. Die bisherigen Stimmen heißen jetzt
  ausdrücklich „(männlich)".
- **Selbst aktualisieren** — die App kann sich ohne Installation und
  ohne Administratorrechte durch eine neuere Fassung ersetzen. Sie lädt
  die Datei, prüft deren SHA-256-Summe, legt sich beiseite und startet
  neu. Neues Modul `dreamevoice/aktualisierung.py`.
- **Eigener Knopf „Aktualisierung"** oben rechts, neben „Hilfe" und
  „Über", mit dem Schalter „beim Start nachsehen" darin. Vorher lag
  beides auf der Seite „Verbindung" unter Konto und Roboterliste — dort
  sucht das niemand. Neues Fenster `dreamevoice/ui/fenster_update.py`.
- **MOVA und Trouver** sind bedienbar. Beide Anmeldeformulare haben eine
  Auswahl „App" (Dreamehome / MOVA Home / Trouver). Die drei Mandanten
  waren im Code fertig hinterlegt, aber `account_type` wurde nirgends
  gesetzt — die beiden Marken waren nur über einen Handeingriff in die
  `config.json` erreichbar.
- **Ausführliche Anleitungen aus der App heraus** — das Hilfe-Fenster
  verlinkt die sechs Seiten in `docs/`. Liegen sie vor, öffnen sie sich
  als Datei, sonst im Browser. Neues Modul `dreamevoice/anleitungen.py`.
- **Notausgang direkt erreichbar** — „Originalstimme zurück" auf der
  Startseite rollt jetzt bis zum Abschnitt „Originalstimme zurückholen".
- **Sprachsynthese viermal schneller.** ElevenLabs wurde bisher eine
  Ansage nach der anderen gefragt; die Leitung wartete dabei fast nur.
  Jetzt laufen mehrere Ansagen gleichzeitig, und die Anzahl regelt sich
  selbst — nach einer sauberen Welle eine mehr, bei einer Drosselung
  sofort halbieren. Gemessen an 60 Ansagen mit realistischer Antwortzeit:
  72,1 s statt 16,6 s, hochgerechnet auf ein volles Paket **11,9 → 2,7
  Minuten**. Die Verbindung bleibt außerdem offen, statt für jede Ansage
  neu aufgebaut zu werden.

### Behoben

- **Der Sprachpaket-Katalog wurde vollständig verworfen.** Die
  Erlaubnisliste der Bezugsadressen kannte `oss.iot.dreame.life` nicht —
  den Server, von dem Dreame tatsächlich ausliefert. Folge: kein
  einziges Originalpaket ließ sich laden, die App war unbenutzbar.
  Nachgemessen über neun Modelle, 237 Katalogeinträge.
- **„Anhören" scheiterte bei jeder Stimme.** `state.ffmpeg` wurde nur
  von der Seite „Einzelne Ansagen" gesetzt; seit die Seiten erst beim
  Öffnen entstehen, blieb der Wert leer. Der gemeinsame Zustand sucht
  ffmpeg jetzt selbst.
- **Nach dem Aufspielen ging der Gerätestand verloren.** Die Seite
  „Fertige Stimmen" meldete „Roboter gewechselt", obwohl nur das
  Sprachpaket neu war. Vier Seiten wurden dadurch gesperrt, der Nutzer
  landete wieder auf der Startseite, und die Auswahl im Notausgang war
  leer — der Rückweg zur Originalstimme also tot.
- **Der Katalog wurde nicht auf seine Form geprüft.** Eine unerwartete
  Antwort ergab rohes Englisch im Fehlerdialog
  (`'str' object has no attribute 'get'`). Schwerer: eine Kennung als
  Zahl passierte alle Schranken und wäre so an den Roboter gegangen.
- **Ein abgebrochener Download ließ die halbe Datei liegen** — bei einem
  übergroßen Paket 240 MB, und das bei jedem neuen Versuch erneut.
- **Fremdpakete hatten keinerlei Schranke** — weder Schema noch Server
  noch Obergrenze. Jetzt nur https von GitHub, höchstens 200 MB.
- **Zwei Fremdpakete ohne Prüfsumme.** Für eines wurde sie nachgerechnet
  und eingetragen; ohne sie galt eine einmal geladene Datei für immer
  als gültig.
- **Ein schlafender Roboter galt als „kennt keine Sprachpakete"** — der
  Nutzer suchte den Fehler beim falschen Gerät.
- **Ein falsches Passwort wurde in allen sechs Regionen probiert**, mit
  entsprechendem Risiko fürs Konto. Bricht jetzt sofort ab.
- **Trouver bot Korea und China an** — beide Adressen existieren nicht
  (per DNS geprüft). Sie werden für diese Marke nicht mehr angezeigt.
- **Die zuletzt gewählte ElevenLabs-Stimme wurde nie zurückgesetzt** —
  drei Zeilen standen hinter einem `return` und liefen nie.
- **„Für das bayerische Paket…"** stand auch dann da, wenn man einen
  anderen Dialekt erzeugte. Jetzt wird das gewählte Paket genannt, samt
  eigener Textänderungen in der Zeichenzahl.
- **Drei Meldungen verwiesen auf Reiter**, die es seit der Seitenleiste
  nicht mehr gibt — eine davon direkt nach einem Download.
- **Die Dialekt-Textdateien behaupteten, nur für den X50 zu gelten.**
  Die Ansage-Nummern sind bei allen Modellen dieselben.
- **`version_info.txt` stand auf 1.2.0**, während das Programm 1.3.0
  war — Windows hätte die neue Datei als alte Fassung ausgewiesen.
- **HTTP 429 galt als „Kontingent aufgebraucht".** Der Code hat zwei
  völlig verschiedene Lagen in einen Topf geworfen: leeres Kontingent
  (aufhören) und Drosselung wegen zu vieler gleichzeitiger Anfragen
  (kurz warten, weitermachen). Sequenziell fiel das kaum auf, bei
  paralleler Arbeit hätte die erste Drosselung den ganzen Lauf
  abgebrochen — mit der falschen Auskunft, das Kontingent sei leer.
- **Das Fenstersymbol** ging an das innere Tk-Fenster statt an das
  äußere, an dem der Taskleisteneintrag hängt, und wurde zu früh
  gesetzt. Beides unsichtbar von außen: Die App zeigte weiter Tks Feder.
- **Endlosschleife auf der Seite „Verbindung".** Das Füllen der
  Roboterliste löste die Auswahl aus, die Auswahl meldete einen
  Gerätewechsel, und der füllte die Liste erneut. Die App blieb beim
  Öffnen der Seite stehen.

### Bedienung und Aussehen

- **Knöpfe im dunklen Design waren kaum zu erkennen**: Die Fläche war
  *dunkler* als ihre Karte (Kontrast 1,06:1). Sie liegen jetzt darüber,
  mit sichtbarem Rand — 3,97:1 statt 2,32:1.
- **Das Kästchen der Auswahlfelder** hatte im Dunkeln einen Rand mit
  1,26:1. Alle sechs Zustandsbilder neu gezeichnet: 3,59:1 im Dunkeln,
  3,37:1 im Hellen. Angehakt ist jetzt gefüllt statt nur umrandet.
- **Knopf „Vollbild" entfernt** — er tat nichts anderes als das Viereck
  in der Windows-Titelleiste. F11 bleibt.
- **Zehnmal schnellerer Start**: 2458 ms → 238 ms, weil die vier
  selten benutzten Seiten erst beim Öffnen entstehen.
- **Verständliche Meldungen für kaputte Archive** — halb geladenes ZIP,
  Archiv mit Kennwort, leere Datei, einzelne Tondatei, RAR, Fehlerseite
  des Servers. Vorher gab es dafür fünf Zeilen englischer tar-Fehler.
- Abgeschnittene Beschriftungen auf „Einzelne Ansagen" korrigiert.
- Das Hilfe-Fenster schob Knopf und Anleitungen aus dem Bild; es wird
  jetzt von unten nach oben aufgebaut.
- **Umlaute stehen überall als Umlaute da.** In der Hilfe stand
  `Dafuer wird ffmpeg gebraucht`, und so ging es quer durch die App:
  rund 1.200 Stellen in angezeigten Texten, Kommentaren, den sechs
  Anleitungen, den Versionsangaben der Programmdatei, den Bauskripten
  und den beiden Textdateien in den fertigen Archiven. Ebenso das
  scharfe s — „gross" und „groß" standen nebeneinander. Unangetastet
  bleiben Bezeichner im Quellcode, Schlüssel wie `update_pruefen` und
  Dateinamen wie `Problemloesung.md`: die werden verglichen und
  geöffnet, nicht gelesen.
- **Die Übersicht der Seiten unter „Erweitert"** stand in der Hilfe als
  Tabelle aus Leerzeichen. Die Schrift dort ist aber keine
  Schreibmaschinenschrift, also stand jede Erklärung woanders. Jetzt
  eine Aufzählung wie im übrigen Text.
- **Das Bild in der README zeigte eine App, die es nicht mehr gibt** —
  einen Knopf „Vollbild", der entfernt wurde, keinen Knopf
  „Aktualisierung", den es jetzt gibt, und in der Fußzeile den vollen
  Pfad **samt Windows-Benutzernamen**. Neu aufgenommen: heutige
  Oberfläche, keine persönlichen Angaben im Bild.
- **Zwei Beipackzettel waren stehengeblieben.** Die fünf
  Aufnahmen-Archive waren längst nachgezogen, `Bayerisch-zum-Anhoeren.zip`
  erklärte den Weg aber weiter über „Tab 1" bis „Tab 4". Der Filter der
  Prüfung sah nur `*-Aufnahmen.zip` und hat den Fehler damit zugedeckt;
  sie prüft jetzt jedes Archiv und jeden Ordner daneben.
- **Ein kyrillisches „а" in der Lizenzdatei** zweier Archive
  („unverаendert"). Es sieht aus wie ein lateinisches a, macht das Wort
  aber unsuchbar. Die Prüfung dagegen gab es schon — sie lief nur nicht
  über diese Archive.
- **„rund 90 MB"** stand in der README und in der Bauanleitung, während
  die Datei auf 97 MB gewachsen war. Die Bauanleitung sagt jetzt auch,
  woraus sie besteht: 13 MB Programm, 39 MB ffmpeg, 45 MB Stimmen.
- **Ein Verweis in `docs/Entwicklung.md`** zeigte auf
  `docs/dreamevoice/__init__.py` — auf GitHub ein 404.
- **Die Kontingenttabelle** nannte einen „gemeinsamen Kern von 239
  Ansagen", den es seit der Vervollständigung aller sieben Dialekte
  nicht mehr gibt, und eine Zeichenspanne, die nicht mehr stimmte.
  Nachgemessen: 22.693 bis 24.971 Zeichen je Paket.
- **Der Weg zurück zur Originalstimme** stand in der Problemlösung nur
  unter „Bauen und Aufspielen". Auf der Startseite reicht seit dieser
  Fassung ein Klick.

### Sicherheit

- Bezugsadressen: nur https und nur von bekannten Servern — geprüft für
  Originalpakete, Fremdpakete und die Aktualisierung.
- Kennungen aus dem Katalog dürfen keine Pfadanteile enthalten.
- Obergrenzen beim Einlesen fremder Archive (Eintrag, Gesamtgröße,
  Anzahl). Ein Archiv mit gefälschten Größenangaben belegte vorher
  600 MB Arbeitsspeicher statt der erlaubten 50.
- Die MD5-Prüfsumme wird auch dann verlangt, wenn der Katalog keine
  nennt — vorher übersprang eine leere Angabe die Kontrolle ganz.
- Die Prüfsumme wird unmittelbar vor dem Austausch der Programmdatei
  erneut geprüft.
- `get_property` prüft Rückgabecode und Adresse; die Schranke davor war
  umgehbar.
- Zugangsdaten liegen im Windows-Anmeldeinformationsspeicher, nicht in
  einer Datei, und wandern beim Kopieren der App nicht mit.

### Doku und Tests

- README von 849 auf 231 Zeilen gekürzt; alles Ausführliche in sechs
  Seiten unter `docs/`.
- Selbsttest: 287 → 617 Prüfstellen, 31 → 49 Abschnitte. Neu darunter
  eine Abfrage des echten Dreame-Katalogs, die anschlägt, wenn sich die
  Auslieferung ändert — ohne Netz wird sie übersprungen, und vierzehn
  Prüfungen der Sprachsynthese gegen einen nachgebauten Dienst
  (Drosselung, leeres Kontingent, Abbruch, halb fertiges Paket) — ohne
  einen einzigen Aufruf bei ElevenLabs.
- Neue Prüfungen für Farbkontraste, tote Navigationsziele, unerreichbare
  Codestellen und die Prüfsumme im Release-Text.
- Der Selbsttest meldet jetzt, wenn Abschnitte stillschweigend
  ausfallen — vorher konnte er schrumpfen und trotzdem „0 Fehler"
  melden.
- Neue Prüfung gegen Ersatzschreibweisen: Sie durchsucht jeden Satz im
  Quellcode und in den Anleitungen nach „ue", „ae" und „oe". Verweise
  auf Bezeichner und `b"..."`-Zeichenketten sind ausgenommen — dort ist
  die Ersatzschreibweise richtig.
- Vier neue Prüfungen gegen still veraltende Angaben: kein Verweis in
  der Doku zeigt ins Leere, die Packliste in `VEROEFFENTLICHEN.md`
  nennt nur Dateien, die es gibt (und mit der richtigen Größe), die
  Größenangabe der EXE stimmt mit der gebauten Datei überein, und die
  Zeichenspanne für ein Dialektpaket stimmt mit den Texten überein.

### Bewusst nicht eingebaut

- **Knopf „Roboter jetzt sprechen lassen".** Die Cloud-Aktion dafür
  (`siid 7 / aiid 2`) liegt bereit, wurde am X50 Ultra Complete aber
  nachgemessen: Der Roboter nimmt sie an, meldet Erfolg — und **zu hören
  ist nichts**. Ein Knopf, der nützlich aussieht und nichts tut, ist
  schlimmer als keiner. Wer die Frage für ein anderes Modell klären
  will, nimmt `Werkzeuge/Testton-pruefen.py`.

---

## v1.2.0 und früher

Siehe die Versionsgeschichte im Projekt.
