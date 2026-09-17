# Veröffentlichen — Schritt für Schritt

Diese Liste ist für den Menschen, der das Release anlegt. Sie steht
hier, damit beim übernächsten Mal niemand raten muss, was dazugehört.

---

## 1. Vorher prüfen

```bash
python selftest.py
```

Erwartet: **0 fehlgeschlagen** und **alle Abschnitte gelaufen**. Eine
übersprungene Prüfung ist in Ordnung, wenn der Grund dabeisteht — die
Prüfsumme der EXE etwa stimmt erst nach dem Bauen.

```bash
python namecheck.py
```

Erwartet: keine unbekannten Namen.

## 2. Bauen

```bash
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

Das Skript führt den Selbsttest selbst noch einmal aus und baut nur,
wenn er durchläuft. Es weigert sich außerdem, solange die App noch
läuft — dann bitte schließen, nicht abschießen: Eine laufende
ElevenLabs-Erzeugung würde sonst bezahltes Kontingent verlieren.

Ergebnis: `dist\DreameSprachpaket.exe`, rund 106 MB.

## 3. Prüfsumme eintragen

```bash
certutil -hashfile dist\DreameSprachpaket.exe SHA256
```

Den Wert in `RELEASE.md` eintragen, zusammen mit der Dateigröße. Der
Selbsttest vergleicht danach beides und meldet eine Abweichung.

## 4. Kurz selbst ausprobieren

Die gebaute EXE starten und einmal durchgehen:

* Anmelden, Roboter erscheint in der Liste
* **Fertige Stimmen** → *Anhören* spielt vier Ansagen ab, auch bei
  einer freien Stimme wie GLaDOS (die wird dafür kurz geladen)
* Servitor zeigt „Community-Pack von Carnimo“
* **Aktualisierung** oben rechts öffnet sich
* **Hilfe** → *Ausführlich nachlesen* öffnet eine Anleitung

Danach die App wieder schließen.

## 5. Release anlegen

Tag: `v` + Version aus `dreamevoice/__init__.py`, also z. B. `v1.4.0`.

Als Beschreibung den Inhalt von `RELEASE.md` einfügen. Die
vollständige Liste der Änderungen steht in `CHANGELOG.md`.

### Diese Dateien gehören ins Release

| Datei | Größe | woher |
|---|---|---|
| `DreameSprachpaket.exe` | ~106 MB | `dist\` |
| `Bayerisch-Aufnahmen.zip` | 9,0 MB | `Fertige Pakete\` |
| `Bayerisch-Weiblich-Aufnahmen.zip` | 9,0 MB | `Fertige Pakete\` |
| `Hessisch-Aufnahmen.zip` | 9,1 MB | `Fertige Pakete\` |
| `Wienerisch-Aufnahmen.zip` | 9,1 MB | `Fertige Pakete\` |
| `Berlinerisch-Aufnahmen.zip` | 8,4 MB | `Fertige Pakete\` |
| `Servitor-Aufnahmen.zip` | 10,6 MB | `Fertige Pakete\` |

**Bayerisch-Weiblich fehlte im Release v1.2.0.** Die Stimme steckt zwar
in der EXE, aber der Knopf „neuere Fassung holen" lief für sie in einen
404. Diesmal bitte mitgeben.

### Was NICHT ins Release gehört

* `dialekt_*_x50.tar.gz` — alte, fertig gebaute Pakete vom 09.08.2026.
  Sie enthalten die Steuerdateien des X50 und passen deshalb wirklich
  nur auf dieses Modell. Ausgeliefert werden bewusst **Aufnahmen**, aus
  denen die App das Paket für das jeweilige Modell selbst baut.
* Der Ordner `Daten` und `dist\Daten` — dort stehen persönliche Angaben.

### Damit alte Fassungen das Release finden

Jede Fassung ab 1.3.0 fragt GitHub nach dem **neuesten** Release und
vergleicht die Versionsnummer zahlenweise. Das klappt für 1.4.0 genauso
wie für 3.0 oder 10.0 — solange diese Regeln eingehalten werden. Sie
sind in jeder ausgelieferten Fassung fest eingebaut:

* Die Programmdatei heißt immer genau **`DreameSprachpaket.exe`** und
  liegt direkt am Release (nicht in einem ZIP).
* Tag im Format **`vX.Y.Z`** (z. B. `v3.0.0`).
* Das Release ist **kein Entwurf und keine Vorabversion** — die
  übergeht GitHub bei „neuestes Release“.
* Das Repository bleibt `Anon365-Project/dreame-sprachpaket-manager`
  (eine Umbenennung leitet GitHub weiter, ein Löschen nicht).
* Die EXE bleibt **unter 400 MB**.
* Die Prüfsumme steht im Release-Text (GitHub legt sie zusätzlich selbst
  an). Ohne Prüfsumme tauscht keine Fassung die Datei aus.

Version **1.2.0 und älter** haben keine Aktualisierung — wer die hat, muss
einmal von Hand herunterladen.

Nach einer Aktualisierung **aus 1.3.0 heraus** startet die neue Fassung
sich einmal von selbst frisch (1.3.0 hat beim Neustart die alte Umgebung
mitgegeben). Verwendet eine künftige Fassung eine andere Python-Version,
kann dieser erste Neustart scheitern; dann genügt es, die EXE von Hand zu
starten. Ab 1.4.0 tritt das nicht mehr auf.

## 6. Nach dem Veröffentlichen

Einmal in der App auf **Aktualisierung → Jetzt nach Aktualisierung
suchen** klicken. Findet sie das neue Release und nennt die richtige
Version, funktioniert der Weg auch für alle anderen.
