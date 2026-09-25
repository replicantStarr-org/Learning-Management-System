# Sets up the RAG server on the host, since it does not run in a container:
# a Python virtual environment with its dependencies, and the Ollama model.
# Safe to re-run. Override the interpreter with $env:PYTHON = "C:\path\to\python.exe".
# Works in Windows PowerShell 5.1 and PowerShell 7. If scripts are blocked, run:
#   powershell -ExecutionPolicy Bypass -File init.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Venv = ".venv_rag"
# $IsWindows only exists in PowerShell 6+, where it is false on Linux and macOS.
if ($IsWindows -eq $false) {
    $VenvPython = Join-Path $Venv "bin/python"
} else {
    $VenvPython = Join-Path $Venv "Scripts\python.exe"
}

# Native commands do not throw on failure, so every call is checked by hand.
function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments, [string]$Failure)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Error $Failure
    }
}

# Prefer the py launcher: on Windows "python" is often the Microsoft Store stub.
if ($env:PYTHON) {
    $Python = $env:PYTHON; $PythonArgs = @()
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"; $PythonArgs = @("-3")
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $Python = "python3"; $PythonArgs = @()
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"; $PythonArgs = @()
} else {
    Write-Error "Python not found; install Python 3.11 or newer from python.org"
}

# config.py reads TOML with tomllib, which arrived in 3.11.
& $Python @PythonArgs -c "import sys; sys.exit(sys.version_info < (3, 11))"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python 3.11 or newer is required ('$Python' is older, or is the Microsoft Store stub)"
}

# Checking for the interpreter rather than the directory also repairs a venv
# left half-created by an interrupted run.
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating $Venv"
    if (Test-Path $Venv) {
        Remove-Item -Recurse -Force $Venv
    }
    Invoke-Checked $Python ($PythonArgs + @("-m", "venv", $Venv)) "Could not create $Venv"
}

Write-Host "Installing dependencies (chromadb can take a few minutes)"
Invoke-Checked $VenvPython @("-m", "pip", "install", "-q", "--upgrade", "pip") "Could not upgrade pip"
Invoke-Checked $VenvPython @("-m", "pip", "install", "-q", "-r", "requirements.txt") "Could not install requirements.txt"

$Model = & $VenvPython -c "from pipeline.common import settings; print(settings()['ollama']['model'])"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Could not read the Ollama model from config.toml"
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Warning "ollama not found; install it and run 'ollama pull $Model' before using /answer"
} else {
    # A missing model is reported on stderr, which Windows PowerShell 5.1
    # turns into a terminating error under "Stop" once it is redirected.
    $ErrorActionPreference = "Continue"
    & ollama show $Model *> $null
    $ModelPresent = $LASTEXITCODE -eq 0
    $ErrorActionPreference = "Stop"

    if ($ModelPresent) {
        Write-Host "Ollama model $Model already present"
    } else {
        Write-Host "Pulling Ollama model $Model"
        & ollama pull $Model
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not pull $Model; is Ollama running?"
        }
    }
}

Write-Host ""
Write-Host "Setup complete. Start the server with:"
Write-Host "  $VenvPython http_server.py"
