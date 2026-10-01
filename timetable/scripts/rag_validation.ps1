# .\rag_demo.ps1                 check the timetable RAG integration through the backend
# .\rag_demo.ps1 -Question "..."  ask a different grounded question
# If scripts are blocked, run: powershell -ExecutionPolicy Bypass -File rag_demo.ps1
param(
    [string]$BackendUrl = "http://localhost:5005",
    [string]$Question = "When is priya.patel's Cybersecurity lab?",
    [string]$UnanswerableQuestion = "What is priya.patel's grade in Cybersecurity?"
)

$ErrorActionPreference = "Stop"
$RagUrl = "$($BackendUrl.TrimEnd('/'))/rag"
$Insufficient = "Insufficient evidence."
$script:Passed = 0
$script:Failed = 0

function Invoke-Rag {
    param([string]$Method, [string]$Path, [hashtable]$Body = $null, [int]$TimeoutSec = 180)

    Write-Host ""
    Write-Host ">>> $Method $RagUrl$Path" -ForegroundColor Cyan
    $request = @{ Uri = "$RagUrl$Path"; Method = $Method; UseBasicParsing = $true; TimeoutSec = $TimeoutSec }
    if ($Body) {
        $json = $Body | ConvertTo-Json -Compress
        Write-Host "    $($json -replace '\\[u]0027', "'")"
        $request.Body = [Text.Encoding]::UTF8.GetBytes($json)
        $request.ContentType = "application/json; charset=utf-8"
    }

    $started = Get-Date
    try {
        $response = Invoke-WebRequest @request
        $status = [int]$response.StatusCode
        $content = $response.Content
    } catch {
        if (-not $_.Exception.Response) {
            Write-Host "<<< no response: $($_.Exception.Message)" -ForegroundColor Red
            return @{ Status = 0; Body = $null }
        }
        $status = [int]$_.Exception.Response.StatusCode
        $reader = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())
        $content = $reader.ReadToEnd()
    }
    $seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    Write-Host "<<< HTTP $status in $seconds s"
    return @{ Status = $status; Body = ($content | ConvertFrom-Json) }
}

function Test-Check {
    param([string]$Name, [bool]$Condition, [string]$Detail = "")

    if ($Condition) {
        Write-Host "PASS $Name" -ForegroundColor Green
        $script:Passed++
    } else {
        Write-Host "FAIL $Name $Detail" -ForegroundColor Red
        $script:Failed++
    }
}

function Show-Answer {
    param($Body)

    Write-Host ""
    Write-Host "Answer:     $($Body.answer)" -ForegroundColor Yellow
    Write-Host "Confidence: $($Body.confidence_category)"
    Write-Host "Records:    $($Body.retrieval_summary.retrieved_count) of $($Body.retrieval_summary.k) used"
    Write-Host "Citations:"
    if (-not $Body.citations) {
        Write-Host "  (none)"
    }
    foreach ($citation in $Body.citations) {
        Write-Host "  - $($citation.title)  [$($citation.chunk_id)]"
    }
}

Write-Host "Timetable RAG demo: frontend -> backend $RagUrl -> shared RAG server" -ForegroundColor White

Write-Host ""
Write-Host "== 1. RAG is enabled in the timetable backend ==" -ForegroundColor White
$result = Invoke-Rag GET "/status"
Test-Check "/rag/status reports enabled" ($result.Status -eq 200 -and $result.Body.enabled -eq $true) "(set RAG_ENABLED=true in docker-compose.yml)"

Write-Host ""
Write-Host "== 2. The backend can reach the shared RAG server ==" -ForegroundColor White
$result = Invoke-Rag GET "/health"
Test-Check "/rag/health relays the RAG server's health" ($result.Status -eq 200 -and $result.Body.status -eq "ok") "(start it with rag-server\run.ps1)"

Write-Host ""
Write-Host "== 3. Index the timetable entries ==" -ForegroundColor White
$result = Invoke-Rag POST "/ingest" @{}
$service = $result.Body.services | Select-Object -First 1
Test-Check "/rag/ingest indexed timetable chunks" ($result.Status -eq 200 -and $service.chunk_count -gt 0) "(are the timetable containers running?)"
if ($service) {
    Write-Host "Indexed $($service.chunk_count) timetable chunks ($($service.removed_count) stale removed)."
}

Write-Host ""
Write-Host "== 4. Grounded answer with citations and a confidence category ==" -ForegroundColor White
$result = Invoke-Rag POST "/answer" @{ query = $Question }
if ($result.Body) {
    Show-Answer $result.Body
    Write-Host ""
    Write-Host "Full JSON returned by the backend:"
    Write-Host (($result.Body | ConvertTo-Json -Depth 6) -replace '\\[u]0027', "'")
}
Test-Check "answer is grounded in timetable entries" ($result.Status -eq 200 -and $result.Body.answer -and $result.Body.answer -ne $Insufficient)
Test-Check "answer has source citations" (@($result.Body.citations).Count -gt 0)
Test-Check "answer has a confidence category" ($result.Body.confidence_category -in @("High", "Medium", "Low"))
Test-Check "every citation is a timetable entry" (@($result.Body.citations | Where-Object { $_.service -ne "timetable" }).Count -eq 0)

Write-Host ""
Write-Host "== 5. Insufficient-context response ==" -ForegroundColor White
$result = Invoke-Rag POST "/answer" @{ query = $UnanswerableQuestion }
if ($result.Body) {
    Show-Answer $result.Body
}
Test-Check "unanswerable question returns '$Insufficient'" ($result.Status -eq 200 -and $result.Body.answer -eq $Insufficient)

Write-Host ""
$color = if ($script:Failed) { "Red" } else { "Green" }
Write-Host "Summary: $($script:Passed) passed, $($script:Failed) failed" -ForegroundColor $color
exit [int]($script:Failed -gt 0)
