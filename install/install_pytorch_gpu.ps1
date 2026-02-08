# install_pytorch_gpu.ps1 - Install CUDA-enabled PyTorch (cu121) for RTX 30-series
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$envName = "hive-dynamics"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Split-Path -Parent $scriptDir

Write-Host "[INFO] Installing PyTorch (CUDA 12.1) into conda env '$envName'..." -ForegroundColor Cyan

function Conda-Exists { try { conda --version > $null 2>&1; return $true } catch { return $false } }
if (-not (Conda-Exists)) { Write-Host "[ERROR] conda not found"; exit 2 }

# Ensure env exists
$envsJson = conda env list --json | Out-String
if (-not ($envsJson -match '"name":\s*"' + [regex]::Escape($envName) + '"')) {
    Write-Host "[ERROR] Conda environment '$envName' does not exist. Run install_env.ps1 first." -ForegroundColor Red
    exit 3
}

# PyTorch packages and extra index
$torchPkgs = @(
  "torch==2.5.1+cu121",
  "torchvision==0.20.1+cu121",
  "torchaudio==2.5.1+cu121"
)
$extraIndex = "https://download.pytorch.org/whl/cu121"

# Install each with pip inside the env
foreach ($pkg in $torchPkgs) {
    Write-Host "[INFO] Installing $pkg ..." -ForegroundColor Cyan
    try {
        conda run -n $envName pip install $pkg --extra-index-url $extraIndex
    } catch {
        Write-Host "[ERROR] Failed to install $pkg : $_" -ForegroundColor Red
        Write-Host "[INFO] You can retry manually after activating the env." -ForegroundColor Yellow
        Write-Host "  conda activate $envName"
        Write-Host "  pip install $pkg --extra-index-url $extraIndex"
        exit 4
    }
}

Write-Host "[INFO] PyTorch packages installed. Verifying inside environment..." -ForegroundColor Cyan
# Verify CUDA availability inside env
$checkCmd = "import torch; print('torch', torch.__version__); print('cuda', torch.version.cuda); print('cuda_available', torch.cuda.is_available())"
try {
    conda run -n $envName python -c $checkCmd
} catch {
    Write-Host "[WARN] Verification command failed: $_" -ForegroundColor Yellow
    Write-Host "Activate the environment and run the verification manually." -ForegroundColor Yellow
    exit 0
}
