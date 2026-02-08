# install_env.ps1 - Create conda env and install pip packages (non-PyTorch)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$envName = "hive-dynamics"
$pyVersion = "3.11"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Split-Path -Parent $scriptDir   # install folder is inside project root

Write-Host "[INFO] install_env.ps1 running. Project root: $projectRoot" -ForegroundColor Cyan

function Conda-Exists {
    try { conda --version > $null 2>&1; return $true } catch { return $false }
}

if (-not (Conda-Exists)) {
    Write-Host "[ERROR] Conda not found on PATH. Install Anaconda/Miniconda and re-run." -ForegroundColor Red
    exit 2
}

# Create env only if missing
$envsJson = conda env list --json | Out-String
if ($envsJson -match '"name":\s*"' + [regex]::Escape($envName) + '"') {
    Write-Host "[INFO] Conda environment '$envName' already exists." -ForegroundColor Yellow
} else {
    Write-Host "[INFO] Creating conda environment '$envName' (python $pyVersion)" -ForegroundColor Cyan
    conda create -n $envName python=$pyVersion -y
}

# ALWAYS overwrite requirements.txt with correct versions
$reqFile = Join-Path $projectRoot 'requirements.txt'

Write-Host "[INFO] Writing updated requirements.txt with OpenAI integration..." -ForegroundColor Cyan

@"
# Computer Vision
ultralytics==8.2.82
opencv-python==4.10.0.84
supervision==0.24.0

# Tracking & Processing
numpy==1.26.4
scipy==1.13.0
pandas==2.2.2

# Agent Framework
langgraph==0.2.34
langchain==0.3.0
langchain-core==0.3.1
langchain-openai==0.2.0
openai==1.53.0

# Database
psycopg[binary,pool]==3.2.1
sqlalchemy==2.0.35
asyncpg==0.29.0
sqlalchemy-utils==0.41.2

# Analytics
matplotlib==3.9.2
seaborn==0.13.2
plotly==5.24.0

# API & Web
fastapi==0.115.0
uvicorn==0.31.0
streamlit==1.39.0
pydantic==2.7.4

# Cache & Queue
redis==5.1.1
celery[redis]==5.4.0

# Monitoring & Logging
python-dotenv==1.0.1
pyyaml==6.0.2
python-json-logger==2.0.7
APScheduler==3.10.4

# Testing
pytest==7.4.4
pytest-asyncio==0.23.3
"@ | Out-File -FilePath $reqFile -Encoding utf8

Write-Host "[INFO] requirements.txt generated successfully." -ForegroundColor Green

# Install requirements
Write-Host "[INFO] Installing pip packages into env '$envName'..." -ForegroundColor Cyan

try {
    conda run -n $envName pip install --upgrade pip
    conda run -n $envName pip install -r $reqFile
    Write-Host "[INFO] Pip dependencies installed successfully." -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Failed installing pip packages: $_" -ForegroundColor Red
    exit 3
}
