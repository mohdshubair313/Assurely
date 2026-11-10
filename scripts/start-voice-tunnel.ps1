param(
    [string]$CloudflaredPath = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskDirectory = Join-Path $taskRoot '.local\voice-tunnel'
if (-not (Test-Path -LiteralPath $CloudflaredPath)) { throw 'cloudflared is not installed at the selected path.' }
$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 5
if ($health.status -ne 'healthy' -or $health.environment -ne 'development') { throw 'A healthy development API is required.' }
$ready = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/ready' -TimeoutSec 8
if ($ready.status -ne 'ready') { throw 'Local dependencies and recovery must be ready first.' }
foreach ($taskPath in @('/docs', '/openapi.json', '/v1/voice/entitlement')) {
    try { $null = Invoke-WebRequest -UseBasicParsing -Uri ('http://127.0.0.1:8000' + $taskPath) -TimeoutSec 5; throw 'Unsafe development API exposure.' }
    catch { if ($null -eq $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 404) { throw } }
}
New-Item -ItemType Directory -Path $taskDirectory -Force | Out-Null
$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$taskErrorLog = Join-Path $taskDirectory ($taskStamp + '.stderr.log')
$taskOutputLog = Join-Path $taskDirectory ($taskStamp + '.stdout.log')
$taskProcess = Start-Process -FilePath $CloudflaredPath -ArgumentList @('tunnel', '--url', 'http://localhost:8000', '--no-autoupdate') -WindowStyle Hidden -PassThru -RedirectStandardError $taskErrorLog -RedirectStandardOutput $taskOutputLog
for ($taskAttempt = 0; $taskAttempt -lt 30; $taskAttempt++) {
    Start-Sleep -Milliseconds 500
    $taskText = [string](Get-Content -LiteralPath $taskErrorLog -Raw -ErrorAction SilentlyContinue) + [string](Get-Content -LiteralPath $taskOutputLog -Raw -ErrorAction SilentlyContinue)
    $taskMatch = [regex]::Match($taskText, 'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($taskMatch.Success) {
        $taskResult = @{ url = $taskMatch.Value; process_id = $taskProcess.Id; public_verified = $false; log_file = $taskErrorLog }
        $taskResult | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskDirectory 'current.json')
        $taskResult | ConvertTo-Json
        exit 0
    }
    if ($taskProcess.HasExited) { throw 'Quick Tunnel exited; inspect its private local log.' }
}
throw 'Quick Tunnel URL was not received within the bounded wait. Inspect its local log.'
