param(
    [Parameter(Mandatory = $true)]
    [string]$ProbePath,

    [string]$OutputDir = "experiments/recorded_traces",
    [string]$Condition = "healthy_idle",

    [ValidateSet("COMPLIANT", "BREACH")]
    [string]$GroundTruth = "COMPLIANT",

    [int]$Count = 5,
    [int]$Iterations = 12,
    [int]$Warmup = 3,
    [long]$Elements = 4194304,
    [int]$Inner = 128,
    [int]$Device = 0,
    [string]$RuntimeProfileId = "CUDA-RECORDED-v0.1",
    [string]$BenchmarkProfileId = "CUDA-MICROBENCH-v0.1"
)

$ErrorActionPreference = "Stop"

if ($Count -lt 1) {
    throw "Count must be >= 1"
}
if (-not (Test-Path -LiteralPath $ProbePath)) {
    throw "CUDA probe not found: $ProbePath"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$entries = @()

for ($i = 1; $i -le $Count; $i++) {
    $stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $suffix = "{0:D2}" -f $i
    $captureId = "$Condition-$stamp-$suffix"
    $contractId = "$Condition-contract-$stamp-$suffix"
    $sessionId = "$Condition-session-$stamp-$suffix"
    $fileName = "$captureId.json"
    $outputPath = Join-Path $OutputDir $fileName

    Write-Host "[$i/$Count] Capturing $Condition -> $outputPath"

    & $ProbePath `
        --device $Device `
        --warmup $Warmup `
        --iterations $Iterations `
        --elements $Elements `
        --inner $Inner `
        --capture-id $captureId `
        --contract-id $contractId `
        --session-id $sessionId `
        --runtime-profile-id $RuntimeProfileId `
        --benchmark-profile-id $BenchmarkProfileId `
        --output $outputPath

    if ($LASTEXITCODE -ne 0) {
        throw "CUDA probe failed for capture $captureId with exit code $LASTEXITCODE"
    }

    $entries += [ordered]@{
        trial_id = $captureId
        condition = $Condition
        ground_truth = $GroundTruth
        trace_paths = @($fileName)
        notes = @(
            "Ground truth is experiment metadata only and must not be copied into verifier evidence."
        )
    }

    Start-Sleep -Milliseconds 250
}

$fragmentPath = Join-Path $OutputDir "$Condition-trials.fragment.json"
$fragment = [ordered]@{
    schema_version = "recorded-campaign-fragment/0.1"
    generated_at_unix_ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    condition = $Condition
    ground_truth = $GroundTruth
    trials = $entries
    notes = @(
        "This file is campaign metadata, not verifier input.",
        "Review the condition label and ground truth before merging these trials into a campaign manifest."
    )
}

$fragment | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $fragmentPath
Write-Host "Campaign fragment: $fragmentPath"
Write-Host "Captured $Count trace(s)."
