param(
    [string]$BuildDir = "build-cuda",
    [string]$OutputDir = "experiments/recorded_traces",
    [int]$HealthyCount = 5,
    [int]$Iterations = 12,
    [string]$CalibrationId = "rtx3050-local-healthy-v0.1",
    [switch]$InstallPythonPackage
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Require-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Required command '$Name' was not found on PATH."
    }
    return $command
}

if ($HealthyCount -lt 3) {
    throw "HealthyCount must be >= 3 so calibration is not based on a single lucky capture."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildPath = Join-Path $repoRoot $BuildDir
$outputPath = Join-Path $repoRoot $OutputDir
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null

Write-Host "== North Standard Mode R preflight =="
Require-Command "nvidia-smi" | Out-Null
Require-Command "nvcc" | Out-Null
Require-Command "cmake" | Out-Null
Require-Command "python" | Out-Null

$nvidiaInfo = (& nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "nvidia-smi failed: $nvidiaInfo"
}
$nvccInfo = (& nvcc --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "nvcc failed: $nvccInfo"
}
$cmakeInfo = (& cmake --version 2>&1 | Select-Object -First 1 | Out-String).Trim()
$pythonInfo = (& python --version 2>&1 | Out-String).Trim()

Write-Host "GPU: $nvidiaInfo"
Write-Host $cmakeInfo
Write-Host $pythonInfo

& python -c "import north_standard" 2>$null
if ($LASTEXITCODE -ne 0) {
    if ($InstallPythonPackage) {
        Write-Host "Installing the local Python package into the active Python environment..."
        Push-Location $repoRoot
        try {
            & python -m pip install -e .
            if ($LASTEXITCODE -ne 0) {
                throw "python -m pip install -e . failed"
            }
        }
        finally {
            Pop-Location
        }
    }
    else {
        throw "Python cannot import north_standard. Activate your project environment and run 'python -m pip install -e .', or rerun this script with -InstallPythonPackage."
    }
}

Write-Host "== Building CUDA probe for RTX 3050 / compute capability 8.6 =="
& cmake -S $repoRoot -B $buildPath `
    -DNORTH_STANDARD_BUILD_CUDA_PROBE=ON `
    -DBUILD_TESTING=OFF `
    -DCMAKE_CUDA_ARCHITECTURES=86
if ($LASTEXITCODE -ne 0) {
    throw "CMake CUDA configure failed"
}

& cmake --build $buildPath --config Release --target north-standard-cuda-probe --parallel 2
if ($LASTEXITCODE -ne 0) {
    throw "CUDA probe build failed"
}

$candidates = @(
    (Join-Path $buildPath "cuda/Release/north-standard-cuda-probe.exe"),
    (Join-Path $buildPath "cuda/north-standard-cuda-probe.exe")
)
$probePath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($null -eq $probePath) {
    $found = Get-ChildItem -Path $buildPath -Recurse -File -Filter "north-standard-cuda-probe.exe" | Select-Object -First 1
    if ($null -eq $found) {
        throw "Build completed but north-standard-cuda-probe.exe was not found under $buildPath"
    }
    $probePath = $found.FullName
}

Write-Host "Probe: $probePath"
Write-Host "== Capturing healthy-idle baseline =="
& (Join-Path $PSScriptRoot "capture_recorded.ps1") `
    -ProbePath $probePath `
    -OutputDir $outputPath `
    -Condition "healthy_idle" `
    -GroundTruth "COMPLIANT" `
    -Count $HealthyCount `
    -Iterations $Iterations

$fragmentPath = Join-Path $outputPath "healthy_idle-trials.fragment.json"
if (-not (Test-Path -LiteralPath $fragmentPath)) {
    throw "Expected campaign fragment was not created: $fragmentPath"
}
$fragment = Get-Content -Raw -LiteralPath $fragmentPath | ConvertFrom-Json
$tracePaths = @()
foreach ($trial in $fragment.trials) {
    foreach ($relativeTrace in $trial.trace_paths) {
        $tracePaths += (Join-Path $outputPath $relativeTrace)
    }
}
if ($tracePaths.Count -ne $HealthyCount) {
    throw "Expected $HealthyCount trace paths in the fragment but found $($tracePaths.Count)"
}

Write-Host "== Building challenge-bound calibration =="
$calibrationPath = Join-Path $outputPath "rtx3050-calibration.json"
$calibrationArgs = @("experiments/calibrate_recorded.py") + $tracePaths + @(
    "--calibration-id", $CalibrationId,
    "--output", $calibrationPath
)
Push-Location $repoRoot
try {
    & python @calibrationArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Recorded calibration failed"
    }
}
finally {
    Pop-Location
}

Write-Host "== Describing healthy-baseline variance =="
$qualityPath = Join-Path $outputPath "rtx3050-baseline-quality.json"
$qualityArgs = @("experiments/analyze_recorded_baseline.py") + $tracePaths + @(
    "--calibration", $calibrationPath,
    "--output", $qualityPath
)
Push-Location $repoRoot
try {
    & python @qualityArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Recorded baseline-quality analysis failed"
    }
}
finally {
    Pop-Location
}

$reportPath = Join-Path $outputPath "mode-r-bootstrap-report.json"
$report = [ordered]@{
    schema_version = "mode-r-bootstrap-report/0.1"
    status = "RECORDED_LOCAL_BASELINE_NOT_PUBLICATION_READY"
    created_at_unix_ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    target = "RTX_3050_LOCAL_ACCESSIBLE_HARDWARE"
    cuda_architecture = 86
    nvidia_smi = $nvidiaInfo
    nvcc = $nvccInfo
    cmake = $cmakeInfo
    python = $pythonInfo
    probe_path = $probePath
    trace_paths = $tracePaths
    calibration_path = $calibrationPath
    baseline_quality_path = $qualityPath
    limitations = @(
        "This report records a local baseline workflow, not H100/H200/B200 evidence.",
        "The collector is LOCAL_SOFTWARE_ONLY and is not hardware-rooted attestation.",
        "Healthy baseline capture alone is not a publication-ready evaluation.",
        "The baseline-quality report is descriptive and does not impose a stability pass/fail threshold."
    )
}
$report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $reportPath

Write-Host ""
Write-Host "Mode R healthy baseline complete."
Write-Host "Calibration: $calibrationPath"
Write-Host "Baseline quality: $qualityPath"
Write-Host "Bootstrap report: $reportPath"
Write-Host "Next: inspect baseline variance before capturing labelled evaluation conditions."
