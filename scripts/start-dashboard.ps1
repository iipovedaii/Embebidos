# SISEMB — servidor local del dashboard (cliente MQTT → broker.emqx.io)
$frontend = Join-Path $PSScriptRoot ".." "frontend" | Resolve-Path
Set-Location $frontend
Write-Host "Dashboard: http://localhost:8000" -ForegroundColor Cyan
Write-Host "Ctrl+C para detener." -ForegroundColor DarkGray
python -m http.server 8000
