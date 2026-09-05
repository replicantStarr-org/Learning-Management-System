$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location -LiteralPath $scriptDir

$skipReports = $false
$pythonArgs = @()
foreach ($argument in $args) {
    if ($argument -eq '--skip-report-download') {
        $skipReports = $true
    }
    else {
        $pythonArgs += $argument
    }
}

if (-not $skipReports) {
    try {
        & (Join-Path $repoRoot 'download_reports.ps1')
        if ($LASTEXITCODE -ne 0) {
            throw "Report downloader exited with status $LASTEXITCODE."
        }
    }
    catch {
        [Console]::Error.WriteLine('Unable to update reports/. The downloader uses the GitHub CLI (gh) and requires it to be installed and authenticated.')
        [Console]::Error.WriteLine('Run again with --skip-report-download to skip downloading (for non-DevOps reviews or manually supplied reports).')
        exit 1
    }
}

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

& $python agentic_loop.py @pythonArgs
exit $LASTEXITCODE
