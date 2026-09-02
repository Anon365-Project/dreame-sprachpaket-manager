# Prüft, ob dieser Rechner ein aussagekräftiger Testfall für die
# SmartScreen-Sperre ist. IN DER VM ausführen, nicht auf dem Wirt.
#
#     powershell -ExecutionPolicy Bypass -File VM-Pruefung.ps1
#
# Optional mit Pfad zur heruntergeladenen EXE:
#     powershell -ExecutionPolicy Bypass -File VM-Pruefung.ps1 C:\Users\...\DreameSprachpaket.exe

param([string]$Datei = "", [switch]$Starten)

function Zeile($was, $wert, $hinweis = "") {
    $text = "{0,-34} {1}" -f $was, $wert
    if ($hinweis) { $text += "   $hinweis" }
    Write-Host $text
}

Write-Host ""
Write-Host "=== Windows ===" -ForegroundColor Cyan
$os = Get-CimInstance Win32_OperatingSystem
Zeile "Ausgabe" $os.Caption
Zeile "Version" "$($os.Version)  (Build $($os.BuildNumber))"

Write-Host ""
Write-Host "=== Smart App Control ===" -ForegroundColor Cyan
# Das ist der Riegel, der KEIN 'Trotzdem ausführen' anbietet.
$ci = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy" -ErrorAction SilentlyContinue
$sac = $ci.VerifiedAndReputablePolicyState
switch ($sac) {
    0 { Zeile "Zustand" "AUS" "unsignierte Programme erlaubt" }
    1 { Zeile "Zustand" "EIN" "<-- blockt unsigniert, ohne Ausweg!" }
    2 { Zeile "Zustand" "Bewertungsmodus" "kann jederzeit anspringen" }
    default { Zeile "Zustand" "nicht vorhanden" "ältere Windows-Fassung" }
}

Write-Host ""
Write-Host "=== SmartScreen ===" -ForegroundColor Cyan
$ex = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer" -ErrorAction SilentlyContinue
Zeile "Explorer-Einstellung" $(if ($ex.SmartScreenEnabled) { $ex.SmartScreenEnabled } else { "Vorgabe (Warn)" })

$ah = Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppHost" -ErrorAction SilentlyContinue
if ($null -ne $ah.EnableWebContentEvaluation) {
    Zeile "Prüfung von Apps/Dateien" $(if ($ah.EnableWebContentEvaluation -eq 1) { "EIN" } else { "AUS" })
}
if ($null -ne $ah.PreventOverride) {
    Zeile "Übergehen verboten" $(if ($ah.PreventOverride -eq 1) { "JA <-- kein 'Trotzdem ausführen'" } else { "nein" })
}

Write-Host ""
Write-Host "=== Defender ===" -ForegroundColor Cyan
try {
    $mp = Get-MpComputerStatus -ErrorAction Stop
    Zeile "Echtzeitschutz" $(if ($mp.RealTimeProtectionEnabled) { "EIN" } else { "AUS" })
    Zeile "Signaturen vom" $mp.AntivirusSignatureLastUpdated
} catch {
    Zeile "Defender" "nicht abfragbar"
}

Write-Host ""
Write-Host "=== Internet ===" -ForegroundColor Cyan
# Ohne Netz kann SmartScreen den Ruf gar nicht abfragen - dann verhält
# sich der Rechner anders als der eines echten Empfängers.
$netz = Test-NetConnection -ComputerName "www.microsoft.com" -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
Zeile "Erreichbar" $(if ($netz) { "ja" } else { "NEIN <-- Test unbrauchbar" })

Write-Host ""
Write-Host "=== Die Datei ===" -ForegroundColor Cyan

# Erst zeigen, was überhaupt da ist. Früher suchte diese Stelle genau
# einen Dateinamen und schluckte jeden Fehler - nach einem zweiten
# Download heißt die Datei aber "DreameSprachpaket (1).exe", und dann
# meldete die Prüfung fälschlich "keine Herkunftsmarkierung".
$ordner = "$env:USERPROFILE\Downloads"
$alle = @(Get-ChildItem $ordner -Filter "DreameSprachpaket*.exe" -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending)
if ($alle.Count -gt 1) {
    Write-Host "  Mehrere Fassungen in Downloads:"
    $alle | ForEach-Object {
        "    {0,-34} {1,8:N1} MB   {2}" -f $_.Name, ($_.Length/1MB), $_.LastWriteTime
    } | Write-Host
    Write-Host "    -> geprüft wird die neueste"
    Write-Host ""
}
if (-not $Datei -and $alle.Count -gt 0) { $Datei = $alle[0].FullName }

if ($Datei -and (Test-Path $Datei)) {
    $fi = Get-Item $Datei
    Zeile "Pfad" $fi.FullName
    Zeile "Geändert" $fi.LastWriteTime
    Zeile "Größe" ("{0:N1} MB" -f ($fi.Length / 1MB))

    # Ohne NTFS gibt es gar keine Zusatzdatenströme - dann kann auch
    # kein Herkunftsvermerk existieren.
    $lw = (Split-Path $fi.FullName -Qualifier)
    $fs = (Get-Volume -DriveLetter $lw.TrimEnd(":") -ErrorAction SilentlyContinue).FileSystemType
    Zeile "Dateisystem" $(if ($fs) { $fs } else { "unbekannt" }) `
          $(if ($fs -and $fs -ne "NTFS") { "<-- ohne NTFS kein Herkunftsvermerk möglich" } else { "" })

    $hash = (Get-FileHash $Datei -Algorithm SHA256).Hash.ToLower()
    $soll = "a7458cd1d1fc292804d248c08a03850d54fe13f330d7727d1be5255ae77152a8"
    Zeile "SHA-256" $hash
    Zeile "stimmt überein" $(if ($hash -eq $soll) { "ja" } else { "NEIN - andere Fassung!" })

    # Alle Datenströme zeigen, nicht nur den gesuchten.
    Write-Host ""
    Write-Host "  Datenströme:"
    $streams = @(Get-Item -Path $fi.FullName -Stream * -ErrorAction SilentlyContinue)
    if ($streams) {
        $streams | ForEach-Object { "    {0,-22} {1,8} Bytes" -f $_.Stream, $_.Length } | Write-Host
    } else {
        Write-Host "    (keine lesbar)"
    }

    $zone = $streams | Where-Object { $_.Stream -eq "Zone.Identifier" }
    Write-Host ""
    if ($zone) {
        Zeile "Herkunftsmarkierung" "VORHANDEN" "gut - der Test ist aussagekräftig"
        Get-Content -Path $fi.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue |
            ForEach-Object { Write-Host "                                   $_" }
    } else {
        Zeile "Herkunftsmarkierung" "FEHLT"
        Write-Host ""
        Write-Host "  Mögliche Gründe:" -ForegroundColor Yellow
        Write-Host "   - die Datei wurde kopiert statt heruntergeladen" -ForegroundColor Yellow
        Write-Host "   - sie wurde über Eigenschaften entsperrt" -ForegroundColor Yellow
        Write-Host "   - Defender hat sie aus der Quarantäne wiederhergestellt" -ForegroundColor Yellow
        Write-Host "     (dabei geht der Vermerk verloren)" -ForegroundColor Yellow
        Write-Host "   - eine ältere Kopie liegt daneben (siehe Liste oben)" -ForegroundColor Yellow
    }
} else {
    Zeile "Datei" "nicht gefunden" "in $ordner gesucht"
    Write-Host "  Falls Defender sie gelöscht hat: Windows-Sicherheit ->" -ForegroundColor Yellow
    Write-Host "  Schutzverlauf zeigt es an." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Startversuch ===" -ForegroundColor Cyan
# Absichtlich NICHT der Ersatz für den Doppelklick: Die
# SmartScreen-Abfrage löst die Windows-Oberfläche aus, nicht das
# Starten eines Prozesses. Über Start-Process läuft die Datei also
# durch, obwohl der Doppelklick warnen würde.
#
# Dafür trennt dieser Versuch die beiden Fälle sauber: Smart App
# Control blockt auf Kernebene und lässt auch hier nichts durch.
if (-not $Starten) {
    Write-Host "  übersprungen - mit -Starten anfordern"
} elseif (-not ($Datei -and (Test-Path $Datei))) {
    Write-Host "  keine Datei zum Starten"
} else {
    try {
        $p = Start-Process -FilePath $Datei -PassThru -ErrorAction Stop
        Start-Sleep -Seconds 8
        $p.Refresh()
        if ($p.HasExited) {
            Zeile "Ergebnis" "sofort beendet" "Exitcode $($p.ExitCode)"
        } else {
            Zeile "Ergebnis" "läuft" "PID $($p.Id)"
            Zeile "Fenstertitel" $(if ($p.MainWindowTitle) { $p.MainWindowTitle } else { "(noch keiner)" })
            Write-Host "  -> Der Start als solcher ist nicht gesperrt."
            Write-Host "     Eine Warnung beim Doppelklick wäre dann normales"
            Write-Host "     SmartScreen, kein Smart App Control."
            # PyInstaller startet einen Kindprozess - der Elternteil
            # allein zu beenden ließe ihn zurück.
            Get-Process DreameSprachpaket -ErrorAction SilentlyContinue |
                Stop-Process -Force -ErrorAction SilentlyContinue
            Write-Host "     (wieder beendet)"
        }
    } catch {
        Zeile "Ergebnis" "BLOCKIERT" $_.Exception.Message
        Write-Host "  -> Der Start scheitert schon ohne Oberfläche." -ForegroundColor Yellow
        Write-Host "     Das spricht für Smart App Control oder eine" -ForegroundColor Yellow
        Write-Host "     Anwendungssteuerung, nicht für SmartScreen." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== Fazit ===" -ForegroundColor Cyan
if ($sac -eq 1) {
    Write-Host "  Smart App Control ist AN. Hier wird JEDE unsignierte Datei"
    Write-Host "  blockiert, ohne Ausweg. Das erklärt 'Entsperren hilft nicht'."
} elseif ($sac -eq 2) {
    Write-Host "  Smart App Control ist im Bewertungsmodus - es kann jederzeit"
    Write-Host "  scharf schalten. Für einen verlässlichen Test abschalten."
} else {
    Write-Host "  Smart App Control ist aus. Eine Warnung wäre dann normales"
    Write-Host "  SmartScreen - mit 'Weitere Informationen' -> 'Trotzdem ausführen'."
}
Write-Host ""
