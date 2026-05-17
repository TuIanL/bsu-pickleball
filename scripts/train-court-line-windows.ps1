<#
.SYNOPSIS
Prepare and run Windows NVIDIA training for the court-line segmentation model.

.DESCRIPTION
This helper creates or reuses backend/.venv, optionally installs the PyTorch
command copied from the official selector, installs backend requirements,
checks CUDA visibility, validates the COCO dataset, prepares YOLO-format data,
and optionally starts Ultralytics segmentation training.
#>

[CmdletBinding()]
param(
    [string]$DatasetRoot,
    [string]$ConvertedOutput,
    [string]$Model = "yolo11n-seg.pt",
    [int]$ImgSize = 960,
    [int]$Epochs = 100,
    [string]$Batch = "-1",
    [string]$Device = "cuda:0",
    [string]$Project,
    [string]$Name = "court-line-seg",
    [string]$TorchInstallCommand = "",
    [switch]$PrepareOnly,
    [switch]$SkipInstall,
    [switch]$AllowCpu
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message"
}

function Resolve-RepoPath {
    param(
        [string]$Value,
        [string]$DefaultRelative
    )

    $raw = if ([string]::IsNullOrWhiteSpace($Value)) { $DefaultRelative } else { $Value }
    if ([System.IO.Path]::IsPathRooted($raw)) {
        return [System.IO.Path]::GetFullPath($raw)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $raw))
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $RepoRoot
    )

    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-InVirtualEnvCommand {
    param([string]$Command)

    $oldPath = $env:PATH
    $oldVirtualEnv = $env:VIRTUAL_ENV
    $scriptsPath = Join-Path $VenvDir "Scripts"
    $env:VIRTUAL_ENV = $VenvDir
    $env:PATH = "$scriptsPath;$oldPath"
    try {
        Invoke-Expression $Command
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $Command"
        }
    }
    finally {
        $env:PATH = $oldPath
        $env:VIRTUAL_ENV = $oldVirtualEnv
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir ".."))
$BackendDir = Join-Path $RepoRoot "backend"
$VenvDir = Join-Path $BackendDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$DatasetRootPath = Resolve-RepoPath $DatasetRoot "datasets\court-line-coco"
$ConvertedOutputPath = Resolve-RepoPath $ConvertedOutput "datasets\court-line-yolo"
$ProjectPath = Resolve-RepoPath $Project "runs\court-line"

Write-Step "Court-line training setup"
Write-Host "Repository:       $RepoRoot"
Write-Host "Backend:          $BackendDir"
Write-Host "Dataset root:     $DatasetRootPath"
Write-Host "Converted output: $ConvertedOutputPath"
Write-Host "Training project: $ProjectPath"
Write-Host "Device:           $Device"

if (-not (Test-Path $BackendDir)) {
    throw "Backend directory not found: $BackendDir"
}

if (-not (Test-Path $DatasetRootPath)) {
    throw "Dataset root not found: $DatasetRootPath"
}

if (-not (Test-Path $PythonExe)) {
    Write-Step "Creating backend virtual environment"
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        Invoke-Checked $py.Source @("-3.11", "-m", "venv", $VenvDir)
    }
    else {
        $python = Get-Command python -ErrorAction Stop
        Invoke-Checked $python.Source @("-m", "venv", $VenvDir)
    }
}
else {
    Write-Step "Using existing backend virtual environment"
}

Write-Step "Python environment"
Invoke-Checked $PythonExe @("--version")

if (-not $SkipInstall) {
    Write-Step "Upgrading pip"
    Invoke-Checked $PythonExe @("-m", "pip", "install", "-U", "pip")

    if (-not [string]::IsNullOrWhiteSpace($TorchInstallCommand)) {
        Write-Step "Installing PyTorch command supplied by user"
        Invoke-Checked $PythonExe @("-m", "pip", "install", "-U", "pip")
        Invoke-InVirtualEnvCommand $TorchInstallCommand
    }
    else {
        Write-Host "No -TorchInstallCommand supplied. Reusing any existing torch installation."
        Write-Host "For first setup, copy the current Windows/Pip/CUDA command from https://pytorch.org/get-started/locally/."
    }

    Write-Step "Installing backend requirements"
    Invoke-Checked $PythonExe @("-m", "pip", "install", "-r", (Join-Path $BackendDir "requirements.txt"))
}
else {
    Write-Step "Skipping dependency installation"
}

Write-Step "Dependency report"
$dependencyCode = @"
import importlib.util
for name in ("torch", "ultralytics", "cv2", "numpy"):
    print(f"{name}: {'installed' if importlib.util.find_spec(name) else 'missing'}")
try:
    import torch
    print(f"torch_version: {torch.__version__}")
    print(f"cuda_available: {torch.cuda.is_available()}")
    print(f"cuda_version: {torch.version.cuda}")
    if torch.cuda.is_available():
        print(f"cuda_device: {torch.cuda.get_device_name(0)}")
except Exception as exc:
    print(f"torch_error: {type(exc).__name__}: {exc}")
"@
Invoke-Checked $PythonExe @("-c", $dependencyCode)

$isCudaDevice = $Device -match "^(cuda|[0-9])"
if ($isCudaDevice -and -not $AllowCpu) {
    Write-Step "Verifying CUDA before training"
    $cudaCheck = @"
import sys
import torch
if not torch.cuda.is_available():
    print("CUDA is not available to PyTorch.")
    print("Install an NVIDIA driver and a CUDA-enabled PyTorch wheel before training.")
    sys.exit(1)
print("CUDA OK:", torch.cuda.get_device_name(0))
"@
    Invoke-Checked $PythonExe @("-c", $cudaCheck)
}
elseif ($AllowCpu) {
    Write-Host "AllowCpu is set; CUDA availability will not block this run."
}

Write-Step "Validating COCO dataset"
Invoke-Checked $PythonExe @(
    (Join-Path $BackendDir "scripts\validate_coco_segmentation.py"),
    "--dataset-root", $DatasetRootPath
) $BackendDir

Write-Step "Preparing YOLO segmentation dataset"
$trainArgs = @(
    (Join-Path $BackendDir "scripts\train_court_line_segmentation.py"),
    "--dataset-root", $DatasetRootPath,
    "--converted-output", $ConvertedOutputPath,
    "--model", $Model,
    "--imgsz", [string]$ImgSize,
    "--epochs", [string]$Epochs,
    "--batch", $Batch,
    "--device", $Device,
    "--project", $ProjectPath,
    "--name", $Name
)

if ($PrepareOnly) {
    $trainArgs += "--prepare-only"
}

Invoke-Checked $PythonExe $trainArgs $BackendDir

if ($PrepareOnly) {
    Write-Step "Prepare-only run complete"
    Write-Host "Regenerated YOLO data at: $ConvertedOutputPath"
}
else {
    Write-Step "Training run complete"
    Write-Host "Review Ultralytics outputs under: $ProjectPath"
    Write-Host "Copy the selected checkpoint to models\court-line\best.pt for runtime use."
}
