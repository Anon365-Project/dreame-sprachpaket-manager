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

# --- Abhaengigkeiten ---
Write-Host "Installiere Abhaengigkeiten ..."
# Ein einziges Fremdpaket. python-miio wird nicht gebraucht - siehe README.
python -m pip install --quiet --disable-pip-version-check "requests>=2.28"
if (-not $?) { Write-Host "FEHLER beim Installieren von requests." -ForegroundColor Red; exit 1 }

python -m pip show pyinstaller *> $null
if (-not $?) {
    Write-Host "Installiere PyInstaller ..."
    python -m pip install --quiet --disable-pip-version-check pyinstaller
    if (-not $?) { Write-Host "FEHLER beim Installieren von PyInstaller." -ForegroundColor Red; exit 1 }
}

# --- Selbsttest, damit keine kaputte EXE entsteht ---
Write-Host ""
Write-Host "Fuehre Selbsttest aus ..."
python selftest.py | Select-Object -Last 4
if (-not $?) {
    Write-Host "FEHLER: Der Selbsttest ist fehlgeschlagen. Es wird nichts gebaut." -ForegroundColor Red
    exit 1
}

# --- Bauen ---
Write-Host ""

# Eine noch laufende App haelt Dateien im dist-Ordner fest.
$laufend = Get-Process DreameSprachpaket -ErrorAction SilentlyContinue
if ($laufend) {
    Write-Host "Die App laeuft noch - sie wird jetzt beendet." -ForegroundColor Yellow
    $laufend | Stop-Process -Force
    Start-Sleep -Seconds 2
}

Write-Host "Baue EXE (dauert ein bis zwei Minuten) ..."
foreach ($ordner in @("build", "dist")) {
    if (Test-Path $ordner) {
        try {
            Remove-Item -Recurse -Force $ordner -ErrorAction Stop
        } catch {
            Write-Host "FEHLER: '$ordner' laesst sich nicht loeschen." -ForegroundColor Red
            Write-Host "Schliesse die App und alle Explorer-Fenster darin, dann erneut versuchen."
            exit 1
        }
    }
}

python -m PyInstaller DreameSprachpaket.spec --noconfirm --clean
if (-not $?) { Write-Host "FEHLER: PyInstaller ist fehlgeschlagen." -ForegroundColor Red; exit 1 }

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
    python embed_ffmpeg.py $ffmpeg $exe
    if (-not $?) { Write-Host "WARNUNG: ffmpeg konnte nicht eingebettet werden." -ForegroundColor Yellow }
} else {
    Write-Host "Hinweis: keine ffmpeg.exe im Projektordner gefunden." -ForegroundColor Yellow
    Write-Host "Die EXE wird ohne eingebautes ffmpeg gebaut - sie kann es dann auf"
    Write-Host "Wunsch zur Laufzeit nachladen. Fuer eine EXE mit eingebautem ffmpeg:"
    Write-Host "ffmpeg.exe in diesen Ordner legen und erneut bauen."
    Write-Host "Bezugsquelle: https://github.com/BtbN/FFmpeg-Builds/releases"
}

$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "Fertig!" -ForegroundColor Green
Write-Host "  Datei:   $exe"
Write-Host "  Groesse: $sizeMb MB"
Write-Host ""
Write-Host "Die EXE laeuft ohne Installation. Zum Weitergeben genuegt diese eine Datei."
