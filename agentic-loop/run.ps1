<#
    Runs the loop in its own virtual environment. Every argument is passed
    through to agentic_loop.py, so:

        .\run.ps1 --offline --iterations 5

    This is the Windows half of run.sh and the two are deliberately alike.
#>

$ErrorActionPreference = "Stop"

# The venv and services.yml are found relative to this script, so it does not
# matter which directory it is called from.
Set-Location -LiteralPath $PSScriptRoot

$venv = ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$stamp = Join-Path $venv ".requirements-installed"

if (-not (Test-Path $venv)) {
    # The py launcher ships with the python.org installer and picks a real
    # interpreter; bare "python" can be the Store stub that installs nothing.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3 -m venv $venv
    }
    else {
        python -m venv $venv
    }
}

# Installing only when requirements.txt is newer than the last install keeps a
# warm run off the network entirely.
$stale = -not (Test-Path $stamp) -or
    (Get-Item requirements.txt).LastWriteTime -gt (Get-Item $stamp).LastWriteTime

if ($stale) {
    & $python -m pip install --quiet --upgrade pip
    & $python -m pip install --quiet -r requirements.txt
    New-Item -ItemType File -Path $stamp -Force | Out-Null
}

& $python agentic_loop.py @args

# Passed straight back out, so --fail-on-critical still fails a build.
exit $LASTEXITCODE
