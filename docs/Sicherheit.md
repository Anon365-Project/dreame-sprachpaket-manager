<!-- Ausgelagert aus der README, damit die Startseite kurz bleibt.
     Inhalt unverändert. -->

# Warum das den Roboter nicht beschädigt

## Warum das den Roboter nicht beschädigt

Das ist die wichtigste Frage, deshalb zuerst.

**Es wird keine Firmware angefasst.** Ein Sprachpaket zu wechseln ist eine
normale, vom Hersteller vorgesehene Funktion. Die Dreamehome-App macht beim
Sprachwechsel exakt denselben Aufruf (MIoT-Eigenschaft `siid 7 / piid 4`).

**Dein Paket ist eine Kopie des Originals.** Die App baut kein Paket aus dem
Nichts. Sie lädt das offizielle Paket deines Modells und tauscht darin nur die
Dateien aus, die du selbst zugewiesen hast. Ein X50-Paket enthält 558 Ansagen
(Variante `r2532h`) bzw. 613 (Variante `r2532v`) und sechs Steuerdateien:

```
0.ogg 1.ogg 2.ogg … 915.ogg      558 bzw. 613 Ansagen
voice_mapping.json               Nummern-Umsetzung zwischen Modellvarianten
tts.json                         Textbausteine des Sprachassistenten
dmr_audio.json                   Abspielparameter je Ansage
first_audio.json                 Ansagen mit Sonderbehandlung
mini_broad.json                  Kurzansage ja/nein
time.txt                         Erstellungszeitpunkt
```

Alle Steuerdateien und alle nicht zugewiesenen Ansagen bleiben Byte für Byte
erhalten. Der Roboter wird also an keiner Stelle stumm. *(Der beiliegende
Selbsttest prüft genau das.)*

**Nummern-Umsetzung.** `voice_mapping.json` hält fest, dass manche Modelle für
eine Ansage eine andere Nummer abspielen — beim X50 Ultra Complete etwa 856
statt 18 („Lädt"), ebenso 863/17, 864/19, 858/112 und 859/140. Wer nur `18.ogg`
austauscht, hört weiterhin das Original. Die App liest diese Umsetzung aus dem
Originalpaket und legt die Aufnahme auf **beide** Nummern.

**Der Roboter prüft selbst.** Mit der URL bekommt er Größe und MD5-Prüfsumme.
Passt etwas nicht, verwirft er das Paket und behält seine bisherige Stimme.

**Es gibt einen Rückweg.** Der Knopf *Originalstimme wiederherstellen* lässt
den Roboter das offizielle Paket direkt bei Dreame laden — dieser PC ist dabei
gar nicht beteiligt. Zusätzlich lässt sich die Sprache jederzeit in der
Dreamehome-App umstellen.

**Feste Kennung.** Dein Paket landet immer unter `CUSTOM` und
überschreibt damit nicht die mitgelieferte deutsche Stimme.

---


---

[Zurück zur Übersicht](../README.md)
