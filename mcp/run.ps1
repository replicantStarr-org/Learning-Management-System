$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

$venv = '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
$stamp = Join-Path $venv '.requirements-installed'
if (-not (Test-Path $venv)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3 -m venv $venv
    }
    else {
        python -m venv $venv
    }
}

$stale = -not (Test-Path $stamp) -or (Get-Item requirements.txt).LastWriteTime -gt (Get-Item $stamp).LastWriteTime
if ($stale) {
    & $python -m pip install --quiet --upgrade pip
    & $python -m pip install --quiet -r requirements.txt
    New-Item -ItemType File -Path $stamp -Force | Out-Null
}

& $python server.py $args
exit $LASTEXITCODE
