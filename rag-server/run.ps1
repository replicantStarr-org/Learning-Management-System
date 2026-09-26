# .\run.ps1 [start]   start the RAG server in this terminal (Ctrl+C stops it)
# .\run.ps1 stop      stop a RAG server started from this folder
# If scripts are blocked, run: powershell -ExecutionPolicy Bypass -File run.ps1 [start|stop]
param(
    [ValidateSet("start", "stop")]
    [string]$Command = "start"
)

$ErrorActionPreference = "Stop"
$PidFile = "rag-server.pid"
$StopTimeoutSeconds = 30

# Push/Pop rather than Set-Location, which would leave the caller's shell in rag-server/.
Push-Location $PSScriptRoot
try {
    # $IsWindows only exists in PowerShell 6+, where it is false on Linux and macOS.
    $OnWindows = $IsWindows -ne $false
    if ($OnWindows) {
        $VenvPython = Join-Path ".venv_rag" "Scripts\python.exe"
    } else {
        $VenvPython = Join-Path ".venv_rag" "bin/python"
    }

    # The server's process if it is running. A pid file left by a crash, or a
    # pid since reused by an unrelated process, does not count.
    function Get-RunningServer {
        if (-not (Test-Path $PidFile)) {
            return $null
        }
        $process = Get-Process -Id ([int](Get-Content $PidFile)) -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -like "python*") {
            return $process
        }
        return $null
    }

    if ($Command -eq "start") {
        if (-not (Test-Path $VenvPython)) {
            Write-Error "$VenvPython not found; run .\init.ps1 first"
        }
        $running = Get-RunningServer
        if ($running) {
            Write-Error "RAG server is already running (pid $($running.Id)); stop it with .\run.ps1 stop"
        }
        & $VenvPython -m server.http_server
        exit $LASTEXITCODE
    }

    $server = Get-RunningServer
    if (-not $server) {
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        Write-Host "RAG server is not running"
        exit 0
    }

    Write-Host "Stopping RAG server (pid $($server.Id))"
    if ($OnWindows) {
        # Windows has no SIGTERM for console programs, so this ends it at once
        # and requests in progress (such as an ingest) are cut off.
        Stop-Process -Id $server.Id -Force
    } else {
        # Same as Ctrl+C: requests in progress are finished first.
        & kill -TERM $server.Id
    }

    $server | Wait-Process -Timeout $StopTimeoutSeconds -ErrorAction SilentlyContinue
    if (-not $server.HasExited) {
        Write-Warning "Still running after $StopTimeoutSeconds s; forcing it to stop"
        Stop-Process -Id $server.Id -Force
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    Write-Host "RAG server stopped"
} finally {
    Pop-Location
}
