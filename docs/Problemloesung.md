<!-- Ausgelagert aus der README, damit die Startseite kurz bleibt.
     Inhalt unverändert. -->

# Wenn etwas nicht klappt

## Das Paket steht nicht in der Dreamehome-App

Normal, kein Fehler. Die App zeigt unter *Sprachton* nur Sprachen aus Dreames
eigenem Katalog — die Kennung `CUSTOM`
steht dort nicht drin.

Meldet die Dreamehome-App beim Öffnen, Roboter und App hätten **verschiedene
Spracheinstellungen**, ist das genau das Zeichen dafür, dass dein Paket läuft:
Der Roboter meldet eine Kennung, die die App nicht kennt.

* **Wähle in der Dreamehome-App keine Sprache aus**, solange dein Paket laufen
  soll — damit lädt der Roboter das offizielle Paket nach und überschreibt
  deines.
* **In der Liste auftauchen kann es nicht.** Die Kennung ist fest `CUSTOM`,
  und Dreames Katalog kennt sie nicht. Das ist Absicht: Der Roboter legt je
  Kennung einen eigenen Ordner an, den man über die Cloud nicht mehr löschen
  kann — eine einzige Kennung überschreibt sich selbst.
* **Zurück zur Originalstimme** geht es jederzeit: auf der Seite *Start* mit
  **Originalstimme zurück**, oder unter *Bauen und Aufspielen* mit
  *Originalstimme wiederherstellen*. Beides ist derselbe Vorgang — der
  Roboter lädt sie direkt bei Dreame.

Ob dein Paket läuft, verrät auf der Seite *Start* der Knopf **Am Roboter
abfragen**; unter *Bauen und Aufspielen* heißt derselbe Knopf *Sprachpaket am
Roboter abfragen*. Die Antwort kommt direkt vom Gerät, nicht aus der App.

---


## Wenn der Roboter das Paket nicht abholt

Der häufigste Stolperstein. Der Roboter muss den PC im Netzwerk erreichen:

* Die **Windows-Firewall** muss eingehende Verbindungen erlauben. Beim ersten
  Start fragt Windows nach — dort *Privates Netzwerk* anhaken.
* PC und Roboter müssen im **selben Netz** hängen. Ein getrenntes IoT- oder
  Gast-WLAN verhindert die Verbindung.
* Ein aktives **VPN** auf dem PC leitet die Antwort ins Leere.
* Der Roboter darf nicht im **Tiefschlaf** sein.

Alternative: das gebaute Paket (in `Daten/Meine Pakete/`) auf einen eigenen
Webspace laden und die öffentliche Adresse im Feld *Eigene URL* eintragen.

---


---

[Zurück zur Übersicht](../README.md)
