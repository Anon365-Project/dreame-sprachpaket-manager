# Baut die portable EXE.
#
# Aufruf (Rechtsklick > "Mit PowerShell ausfuehren" geht auch):
#     powershell -ExecutionPolicy Bypass -File build_exe.ps1
#
# Ergebnis: dist\DreameSprachpaket.exe - eine einzelne Datei, die sich ohne
# Installation auf jeden Windows-PC kopieren laesst.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== Dreame Sprachpaket-Manager: EXE bauen ==" -ForegroundColor Cyan
Write-Host ""

# --- Python vorhanden? ---
try {
    $pyVersion = (python --version) 2>&1
    Write-Host "Python:      $pyVersion"
} catch {
    Write-Host "FEHLER: Python wurde nicht gefunden." -ForegroundColor Red
    Write-Host "Installiere Python 3.9 oder neuer von https://www.python.org/downloads/"
    Write-Host "und setze beim Setup den Haken bei 'Add Python to PATH'."
    exit 1
}

# Windows PowerShell macht aus jeder stderr-Zeile eines aufgerufenen
# Programms einen Fehlerdatensatz. Zusammen mit dem "Stop" oben bricht das
# den Bau ab, obwohl das Programm sauber mit 0 zurueckkommt - eine einzige
# Warnzeile von pip oder PyInstaller genuegt. Deshalb laufen alle Aufrufe
# fremder Programme durch diese Klammer, und ob es geklappt hat, sagt
# allein der Rueckgabewert in $LASTEXITCODE.
function Invoke-Native {
    param([Parameter(Mandatory = $true)][scriptblock]$Befehl)
    $alt = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Befehl } finally { $ErrorActionPreference = $alt }
}

# --- Abhaengigkeiten ---
Write-Host "Installiere Abhaengigkeiten ..."
# Ein einziges Fremdpaket. python-miio wird nicht gebraucht - siehe README.
Invoke-Native { python -m pip install --quiet --disable-pip-version-check "requests>=2.28" }
if ($LASTEXITCODE -ne 0) { Write-Host "FEHLER beim Installieren von requests." -ForegroundColor Red; exit 1 }

Invoke-Native { python -m pip show pyinstaller *> $null }
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installiere PyInstaller ..."
    Invoke-Native { python -m pip install --quiet --disable-pip-version-check pyinstaller }
    if ($LASTEXITCODE -ne 0) { Write-Host "FEHLER beim Installieren von PyInstaller." -ForegroundColor Red; exit 1 }
}

# --- Selbsttest, damit keine kaputte EXE entsteht ---
Write-Host ""
Write-Host "Fuehre Selbsttest aus ..."
Invoke-Native { python selftest.py } | Select-Object -Last 4
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Der Selbsttest ist fehlgeschlagen. Es wird nichts gebaut." -ForegroundColor Red
    exit 1
}

# --- Bauen ---
Write-Host ""

# Eine laufende App wird NICHT einfach abgeschossen. Sie koennte gerade
# Ansagen sprechen - bei ElevenLabs kostet jede davon Kontingent.
$laufend = Get-Process DreameSprachpaket -ErrorAction SilentlyContinue
if ($laufend) {
    Write-Host "FEHLER: Die App laeuft noch." -ForegroundColor Red
    Write-Host ""
    Write-Host "Sie wird absichtlich nicht beendet: laeuft gerade eine Erzeugung"
    Write-Host "ueber ElevenLabs, waere das dafuer verbrauchte Kontingent verloren."
    Write-Host "Bitte die App selbst schliessen und danach erneut bauen."
    exit 1
}

Write-Host "Baue EXE (dauert ein bis zwei Minuten) ..."

# build/ enthaelt nur Zwischenergebnisse und darf komplett weg.
if (Test-Path "build") {
    try {
        Remove-Item -Recurse -Force "build" -ErrorAction Stop
    } catch {
        Write-Host "FEHLER: 'build' laesst sich nicht loeschen." -ForegroundColor Red
        Write-Host "Schliesse alle Explorer-Fenster darin, dann erneut versuchen."
        exit 1
    }
}

# dist/ dagegen NICHT loeschen! Die portable EXE legt ihren Datenordner
# neben sich ab, also unter dist\Daten - dort stehen Zugangsdaten, fertige
# Pakete und die bereits gesprochenen Ansagen. Entfernt wird nur die alte
# EXE selbst; PyInstaller schreibt die neue an dieselbe Stelle.
$altExe = Join-Path $PSScriptRoot "dist\DreameSprachpaket.exe"
if (Test-Path $altExe) {
    try {
        Remove-Item -Force $altExe -ErrorAction Stop
    } catch {
        Write-Host "FEHLER: Die alte EXE laesst sich nicht ersetzen." -ForegroundColor Red
        Write-Host "Laeuft sie noch? Bitte schliessen und erneut versuchen."
        exit 1
    }
}

$datenOrdner = Join-Path $PSScriptRoot "dist\Daten"
if (Test-Path $datenOrdner) {
    $anzahl = (Get-ChildItem $datenOrdner -Recurse -File -ErrorAction SilentlyContinue).Count
    Write-Host "  (dist\Daten bleibt erhalten: $anzahl Dateien)" -ForegroundColor DarkGray
}

Invoke-Native { python -m PyInstaller DreameSprachpaket.spec --noconfirm --clean }
if ($LASTEXITCODE -ne 0) { Write-Host "FEHLER: PyInstaller ist fehlgeschlagen." -ForegroundColor Red; exit 1 }

$exe = Join-Path $PSScriptRoot "dist\DreameSprachpaket.exe"
if (-not (Test-Path $exe)) {
    Write-Host "FEHLER: Die EXE wurde nicht erzeugt." -ForegroundColor Red
    exit 1
}

# --- ffmpeg mit einpacken -------------------------------------------------
# Wird hinten an die EXE angehaengt statt ueber PyInstaller gebuendelt, damit
# der Start schnell bleibt. Details siehe dreamevoice/embedded.py.
Write-Host ""
$ffmpeg = $null
foreach ($p in @("ffmpeg.exe", "ffmpeg\ffmpeg.exe", "ffmpeg\bin\ffmpeg.exe")) {
    $full = Join-Path $PSScriptRoot $p
    if (Test-Path $full) { $ffmpeg = $full; break }
}

if ($ffmpeg) {
    Write-Host "Packe ffmpeg mit in die EXE ..."
    Invoke-Native { python embed_ffmpeg.py $ffmpeg $exe }
    if ($LASTEXITCODE -ne 0) { Write-Host "WARNUNG: ffmpeg konnte nicht eingebettet werden." -ForegroundColor Yellow }
} else {
    Write-Host "Hinweis: keine ffmpeg.exe im Projektordner gefunden." -ForegroundColor Yellow
    Write-Host "Die EXE wird ohne eingebautes ffmpeg gebaut - sie kann es dann auf"
    Write-Host "Wunsch zur Laufzeit nachladen. Fuer eine EXE mit eingebautem ffmpeg:"
    Write-Host "ffmpeg.exe in diesen Ordner legen und erneut bauen."
    Write-Host "Bezugsquelle: https://github.com/BtbN/FFmpeg-Builds/releases"
}

# --- Fertige Dialekte mit einpacken --------------------------------------
# Sie sollen ohne Internet und ohne Umweg ueber die Projektseite bereit
# stehen. Unkomprimiert angehaengt (Ogg in ZIP ist schon gepackt) und
# hinter ffmpeg - embedded.py liest die Kette vom Dateiende rueckwaerts.
Write-Host ""
$dialekte = Join-Path $PSScriptRoot "Fertige Pakete"
if (Test-Path $dialekte) {
    $anzahlZips = @(Get-ChildItem $dialekte -Filter "*-Aufnahmen.zip" -ErrorAction SilentlyContinue).Count
    if ($anzahlZips -gt 0) {
        Write-Host "Packe $anzahlZips fertige Dialekte mit in die EXE ..."
        Invoke-Native { python embed_dialekte.py }
        if ($LASTEXITCODE -ne 0) { Write-Host "WARNUNG: Dialekte konnten nicht eingebettet werden." -ForegroundColor Yellow }
    } else {
        Write-Host "Hinweis: keine *-Aufnahmen.zip in 'Fertige Pakete'." -ForegroundColor Yellow
        Write-Host "Die EXE wird ohne mitgelieferte Dialekte gebaut."
    }
} else {
    Write-Host "Hinweis: Ordner 'Fertige Pakete' fehlt." -ForegroundColor Yellow
    Write-Host "Die EXE wird ohne mitgelieferte Dialekte gebaut - die Texte"
    Write-Host "der sieben Dialekte stecken trotzdem im Programm."
}

$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "Fertig!" -ForegroundColor Green
Write-Host "  Datei:   $exe"
Write-Host "  Groesse: $sizeMb MB"
Write-Host ""
Write-Host "Die EXE laeuft ohne Installation. Zum Weitergeben genuegt diese eine Datei."
