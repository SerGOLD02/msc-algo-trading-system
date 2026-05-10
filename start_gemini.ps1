# 1. Controlla se Docker è avviato, altrimenti lo lancia
$dockerCheck = docker info 2>$null
if (!$dockerCheck) {
    Write-Host "🚀 Avvio di Docker Desktop in corso..." -ForegroundColor Cyan
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    
    # Aspetta finché Docker non è pronto (max 60 secondi)
    $retryCount = 0
    while (!(docker info 2>$null) -and $retryCount -lt 12) {
        Write-Host "⏳ In attesa che la balena si svegli..."
        Start-Sleep -Seconds 5
        $retryCount++
    }
}

# 2. Attiva l'ambiente virtuale
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "🐍 Attivazione Environment (.venv)..." -ForegroundColor Green
    .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "⚠️ Errore: Cartella .venv non trovata!" -ForegroundColor Red
}

# 3. Lancia Gemini CLI con Sandbox attiva e modello Pro
Write-Host "🤖 Avvio Gemini CLI con Sandbox..." -ForegroundColor Gold
gemini -s --model gemini-3.1-pro-preview