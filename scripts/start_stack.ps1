# SISEMB — arranca broker + dashboard en tu PC (PowerShell)
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Instalando websockets si falta..."
python -m pip install websockets -q

Write-Host "Broker: TCP 5051 | WS 5052"
Start-Process python -ArgumentList "broker/simpleBroker/simple_server.py" -WorkingDirectory $Root -WindowStyle Normal

Start-Sleep -Seconds 2
$DashboardPort = 8765
Write-Host "Dashboard: http://127.0.0.1:$DashboardPort"
Start-Process python -ArgumentList "-m","http.server",$DashboardPort -WorkingDirectory "$Root\frontend" -WindowStyle Normal

$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.InterfaceAlias -notmatch 'Loopback' -and $_.IPAddress -notmatch '^169\.'
} | Select-Object -First 1).IPAddress
Write-Host ""
Write-Host "Pon en firmware/config.py: BROKER_HOST = `"$ip`""
Write-Host "Abre: http://127.0.0.1:$DashboardPort/index.html"
