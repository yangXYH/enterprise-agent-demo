$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$env:APP_ENV = "test"
trap {
    $message = $_ | Out-String
    $message | Set-Content (Join-Path $PSScriptRoot 'startup-error.log')
    (New-Object -ComObject WScript.Shell).Popup(('Startup failed. See ' + $PSScriptRoot + '\startup-error.log'), 0, 'Enterprise Agent', 16) | Out-Null
    exit 1
}
$Frontend = Join-Path $Root "frontend"
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Node = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
if ($nodeCommand) { $Node = $nodeCommand.Source }

if (-not (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)) {
    Start-Process `
        -FilePath $Python `
        -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--timeout-graceful-shutdown", "5") `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Root "backend-dev.out.log") `
        -RedirectStandardError (Join-Path $Root "backend-dev.err.log")
}

if (-not (Get-NetTCPConnection -State Listen -LocalPort 5717 -ErrorAction SilentlyContinue)) {
    Start-Process `
        -FilePath $Node `
        -ArgumentList @(('"' + (Join-Path $Frontend 'node_modules\vite\bin\vite.js') + '"'), '--host', '127.0.0.1', '--port', '5717', '--strictPort') `
        -WorkingDirectory $Frontend `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Frontend "vite-dev.log") `
        -RedirectStandardError (Join-Path $Frontend "vite-dev.err.log")
}

$deadline = (Get-Date).AddSeconds(90)
$backendOk = $false
$frontendOk = $false

while ((Get-Date) -lt $deadline -and -not ($backendOk -and $frontendOk)) {
    if (-not $backendOk) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/openapi.json" -UseBasicParsing -TimeoutSec 3
            $backendOk = $response.StatusCode -eq 200
        }
        catch {
        }
    }

    if (-not $frontendOk) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:5717/" -UseBasicParsing -TimeoutSec 3
            $frontendOk = $response.StatusCode -eq 200
        }
        catch {
        }
    }

    if (-not ($backendOk -and $frontendOk)) {
        Start-Sleep -Seconds 2
    }
}

if ($backendOk -and $frontendOk) {
    Start-Process "http://127.0.0.1:5717"
}
else {
    $message = 'Startup timed out. Check backend-dev.err.log and frontend\vite-dev.err.log in ' + $Root
    $message | Set-Content (Join-Path $Root 'startup-error.log')
    (New-Object -ComObject WScript.Shell).Popup($message, 0, 'Enterprise Agent', 16) | Out-Null
}
