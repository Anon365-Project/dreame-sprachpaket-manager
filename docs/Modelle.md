<!-- Ausgelagert aus der README, damit die Startseite kurz bleibt.
     Inhalt unverändert. -->

# Welche Roboter funktionieren?

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


---

[Zurück zur Übersicht](../README.md)
