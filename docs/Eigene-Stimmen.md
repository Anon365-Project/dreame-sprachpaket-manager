<!-- Ausgelagert aus der README, damit die Startseite kurz bleibt.
     Inhalt unverändert. -->

# Eigene Stimmen und Dialekte

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

| Dialekt | Kostprobe (Ansage 7) |
|---|---|
| Bayerisch | „So, jetzt legn ma los. I fang zum Saugn o." |
| Hessisch | „Ei gude, dann geht's los. Isch fang aa zu sauge." |
| Schwäbisch | „So, jetzt gohts los. I fang a zom Sauga." |
| Sächsisch | „Nu, dann gehds los. Isch fange an zu saugen." |
| Berlinerisch | „Na denn los. Ick fang an zu sauje." |
| Wienerisch | „Na servas, dann fang ma an. I saug jetzt." |
| Kölsch | „Alaaf, dann jeht et los. Ich fange aan ze sauge." |

Eine eigene Kennung je Dialekt gab es früher — sie ist entfallen.
Aufgespielt wird alles unter `CUSTOM`, weil der Roboter je Kennung einen
eigenen Ordner anlegt und man den über die Cloud nicht mehr löschen kann.

Selbst erzeugte Pakete landen im Ordner `Daten/Meine Pakete`. Für Bayerisch
(männlich und weiblich), Hessisch, Wienerisch und Berlinerisch sind fertig
gesprochene Aufnahmen bereits in der App enthalten — dafür muss man nichts
selbst erzeugen.

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
| Eine einzelne Ansage | 5–129, im Mittel 40 | reicht für hunderte |
| Ein vollständiges Dialektpaket (593 Ansagen) | 22.700–25.000 | reicht nicht — drei Monate oder Starter-Tarif |

Die Spanne kommt vom Dialekt: Bayerisch braucht 22.693 Zeichen, Hessisch
24.971. Nachgemessen an den mitgelieferten Texten.

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


---

[Zurück zur Übersicht](../README.md)
