$ErrorActionPreference = 'Stop'

# Download the latest artifacts for every workflow whose GitHub Actions name
# contains "CI". The script is intentionally rooted at its own directory.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Error "GitHub CLI (gh) is not installed."
    exit 1
}

& gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "GitHub CLI is not authenticated. Run 'gh auth login'."
    exit 1
}

$reportsDir = Join-Path $scriptDir 'reports'
$lastDownloadFile = Join-Path $reportsDir 'LAST_DOWNLOAD_TIME'
New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null

# Capture this before querying GitHub. It is written only after all downloads,
# so a run that starts while this script is working is picked up next time.
$downloadStartedAt = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")

function Invoke-Gh {
    param([string[]]$Arguments)

    $output = & gh @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        $details = ($output -join [Environment]::NewLine)
        throw "gh command failed: gh $($Arguments -join ' ')`n$details"
    }
    return ($output -join [Environment]::NewLine)
}

$lastDownloadAt = $null
if (Test-Path -LiteralPath $lastDownloadFile -PathType Leaf) {
    $lastDownloadAt = (Get-Content -LiteralPath $lastDownloadFile -Raw).Trim()
    if ($lastDownloadAt) {
        try {
            $lastDownloadTime = [DateTimeOffset]::Parse($lastDownloadAt)
        }
        catch {
            Write-Error "reports/LAST_DOWNLOAD_TIME is not a valid timestamp: $lastDownloadAt"
            exit 1
        }
    }
}

$latestRunAt = (Invoke-Gh @('run', 'list', '--limit', '1', '--json', 'updatedAt', '--jq', '.[0].updatedAt // empty')).Trim()
if (-not $latestRunAt) {
    Write-Error 'No GitHub Actions runs were found.'
    exit 1
}

try {
    $latestRunTime = [DateTimeOffset]::Parse($latestRunAt)
}
catch {
    Write-Error "GitHub returned an invalid latest-run timestamp: $latestRunAt"
    exit 1
}

if ($lastDownloadAt -and $lastDownloadTime -gt $latestRunTime) {
    Write-Output 'Reports are up to date.'
    exit 0
}

$workflowJson = Invoke-Gh @('workflow', 'list', '--all', '--json', 'name,path')
$workflows = @($workflowJson | ConvertFrom-Json | Where-Object { $_.name -clike '*CI*' })

foreach ($workflow in $workflows) {
    $workflowFile = [IO.Path]::GetFileName($workflow.path)
    $workflowId = [IO.Path]::GetFileNameWithoutExtension($workflowFile)
    if (-not $workflowId) {
        throw "Could not determine a safe reports folder for $($workflow.path)."
    }

    $runJson = Invoke-Gh @('run', 'list', '--workflow', $workflow.path, '--limit', '1', '--json', 'databaseId,createdAt')
    $runs = @($runJson | ConvertFrom-Json)
    if ($runs.Count -eq 0) {
        throw "No run found for workflow '$($workflow.name)'."
    }
    $run = $runs[0]
    if (-not $run.databaseId) {
        throw "Invalid run returned for '$($workflow.name)'."
    }

    $targetDir = Join-Path $reportsDir $workflowId
    $tempDir = Join-Path $reportsDir ".${workflowId}.tmp.$PID"
    if (Test-Path -LiteralPath $tempDir) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

    try {
        Write-Output "Downloading artifacts for $($workflow.name) (run $($run.databaseId))..."
        try {
            $downloadOutput = Invoke-Gh @('run', 'download', [string]$run.databaseId, '--dir', $tempDir)
            if ($downloadOutput) {
                Write-Output $downloadOutput
            }
        }
        catch {
            if ($_.Exception.Message -match '(?i)no\s+.*artifacts?|artifacts?\s+(not\s+found|found\s+for)|HTTP.*404') {
                Write-Warning "No artifacts found for $($workflow.name) (run $($run.databaseId)); continuing."
                # Treat a run without artifacts as an empty replacement, so stale
                # files from an older run are not retained.
                Remove-Item -LiteralPath $tempDir -Recurse -Force
                New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            }
            else {
                throw
            }
        }

        # Replace the complete workflow directory, rather than merging into
        # stale contents. This leaves one top-level folder per workflow.
        if (Test-Path -LiteralPath $targetDir) {
            Remove-Item -LiteralPath $targetDir -Recurse -Force
        }
        Move-Item -LiteralPath $tempDir -Destination $targetDir
    }
    catch {
        if (Test-Path -LiteralPath $tempDir) {
            Remove-Item -LiteralPath $tempDir -Recurse -Force
        }
        throw
    }
}

$lastDownloadTemp = Join-Path $reportsDir ".LAST_DOWNLOAD_TIME.tmp.$PID"
[IO.File]::WriteAllText($lastDownloadTemp, "$downloadStartedAt`n", [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $lastDownloadTemp -Destination $lastDownloadFile -Force

Write-Output 'Reports downloaded successfully.'
# Do not leak a handled gh failure (for a run with no artifacts) through
# $LASTEXITCODE to the launcher.
exit 0
