<#
Setup script for Hive Dynamics (Windows, Conda)
This script:
 - Ensures Conda is installed (will download and run installer if missing)
 - Creates project folders
 - Writes a .env file with placeholders
 - Writes requirements.txt (from the guide)
 - Creates a simple init_db.sql placeholder
 - Creates a helper docker-compose.yml if one doesn't exist
 - Creates a README_RUN.txt with next steps
 - Creates the conda environment and installs Python dependencies using conda run
USAGE (from an elevated PowerShell prompt):
    powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- Helpers ---
function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }

# --- Variables ---
$projectRoot = (Get-Location).Path
$envFile = Join-Path $projectRoot '.env'
$requirementsFile = Join-Path $projectRoot 'requirements.txt'
$initDbFile = Join-Path $projectRoot 'init_db.sql'
$dockerComposeFile = Join-Path $projectRoot 'docker-compose.yml'
$readmeFile = Join-Path $projectRoot 'README_RUN.txt'

# --- 1) Create folder structure ---
Write-Info "Creating project directories..."
$dirs = @(
  'src\agents','src\cv_pipeline','src\database','src\api','src\utils',
  'config\agents','config\database','config\deployment',
  'data\videos','data\annotations','data\cache',
  'models\yolo','models\reid','models\checkpoints',
  'logs\daily','logs\agent','logs\system',
  'tests'
)
foreach ($d in $dirs) {
  $full = Join-Path $projectRoot $d
  if (-not (Test-Path $full)) {
    New-Item -ItemType Directory -Force -Path $full | Out-Null
    Write-Info "  Created: $d"
  } else {
    Write-Info "  Exists: $d"
  }
}

# --- 2) Create .env (if not present) ---
if (-not (Test-Path $envFile)) {
  Write-Info "Writing .env with placeholders..."
  @"
# API Keys
OPENAI_API_KEY=REPLACE_WITH_YOUR_OPENAI_KEY

# PostgreSQL Configuration
POSTGRES_DB=hive_dynamics
POSTGRES_USER=hive_user
POSTGRES_PASSWORD=hive1234
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# Application Settings
LOG_LEVEL=INFO
VIDEO_FPS=1  # Process 1 frame per second from video
MAX_CAMERAS=20
DETECTION_CONFIDENCE_THRESHOLD=0.5

# Agent Configuration
PEAK_HOUR_THRESHOLD=100
LOW_HOUR_THRESHOLD=20
OVERCROWDING_THRESHOLD=50
FORECAST_ENABLED=true
"@ | Out-File -FilePath $envFile -Encoding utf8
  Write-Info ".env created at $envFile"
} else {
  Write-Warn ".env already exists; skipping creation."
}

# --- 3) Write requirements.txt (if not present) ---
if (-not (Test-Path $requirementsFile)) {
  Write-Info "Writing requirements.txt..."
  @"
# Computer Vision
ultralytics==8.3.0
opencv-python==4.10.0
supervision==0.24.0

# Tracking & Processing
numpy==1.26.4
scipy==1.13.0
pandas==2.2.2

# Agent Framework
langgraph==0.2.34
langchain==0.3.0
langchain-anthropic==0.2.0
langchain-core==0.3.1

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
pydantic==2.7.1

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
"@ | Out-File -FilePath $requirementsFile -Encoding utf8
  Write-Info "requirements.txt created at $requirementsFile"
} else {
  Write-Warn "requirements.txt already exists; skipping creation."
}

# --- 4) Create init_db.sql placeholder ---
if (-not (Test-Path $initDbFile)) {
  Write-Info "Creating init_db.sql placeholder..."
  @"
-- init_db.sql
-- Place your DB schema initialization SQL here.
-- Example: create tables for detections, alerts, analytics, zones

CREATE TABLE IF NOT EXISTS detections (
  id SERIAL PRIMARY KEY,
  camera_id TEXT,
  class_name TEXT,
  confidence REAL,
  bbox TEXT,
  track_id INTEGER,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
  id SERIAL PRIMARY KEY,
  alert_type TEXT,
  severity TEXT,
  camera_id TEXT,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  metadata JSONB,
  acknowledged INTEGER DEFAULT 0
);
"@ | Out-File -FilePath $initDbFile -Encoding utf8
  Write-Info "init_db.sql created at $initDbFile"
} else {
  Write-Warn "init_db.sql already exists; skipping creation."
}

# --- 5) Create a minimal docker-compose.yml if none exists ---
if (-not (Test-Path $dockerComposeFile)) {
  Write-Info "Creating a minimal docker-compose.yml (for Docker Desktop)..."
  @"
version: '3.9'

services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-hive_dynamics}
      POSTGRES_USER: ${POSTGRES_USER:-hive_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-secure}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init_db.sql:/docker-entrypoint-initdb.d/init.sql

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
"@ | Out-File -FilePath $dockerComposeFile -Encoding utf8
  Write-Info "docker-compose.yml created at $dockerComposeFile"
} else {
  Write-Warn "docker-compose.yml already exists; skipping creation."
}

# --- 6) README_RUN with next steps ---
@"
Hive Dynamics - Windows setup summary
====================================

What's been created:
 - Project folders (src/, config/, data/, models/, logs/, tests/)
 - .env (placeholders) at: $envFile
 - requirements.txt at: $requirementsFile
 - init_db.sql placeholder at: $initDbFile
 - docker-compose.yml at: $dockerComposeFile

Next steps (recommended):
 1) Install Anaconda (if not installed):
    - Download: https://www.anaconda.com/products/distribution
    - Or let the script attempt to download if conda is missing.

 2) Create conda environment and install dependencies (script will attempt this automatically below):
    conda create -n hive-dynamics python=3.11 -y
    conda run -n hive-dynamics pip install -r requirements.txt

 3) Install Docker Desktop (Windows) and enable WSL2 integration if you plan to use GPU or Linux containers.
    - https://www.docker.com/products/docker-desktop

 4) Start services:
    docker compose up -d

 5) Initialize database (the compose mounts init_db.sql to the DB container)
    - The postgres container will execute init_db.sql at first start

 6) Test the CV pipeline (once dependencies & models are in place):
    python src\cv_pipeline\detector.py

Notes:
 - This script assumes an elevated PowerShell session for some operations.
 - For GPU-enabled YOLO on Windows, ensure NVIDIA drivers and CUDA toolkit are installed.
"@ | Out-File -FilePath $readmeFile -Encoding utf8
Write-Info "README_RUN.txt written to $readmeFile"

# --- 7) Ensure Conda is available, otherwise download Anaconda installer ---
function Conda-Exists {
  try {
    $null = & conda --version 2>$null
    return $true
  } catch {
    return $false
  }
}

if (-not (Conda-Exists)) {
  Write-Warn "Conda not found on PATH. Attempting to download Anaconda installer (interactive)."
  $installer = Join-Path $env:TEMP "Anaconda3-2025.01-Windows-x86_64.exe"
  Write-Info "Downloading Anaconda installer to $installer ... (this may take several minutes)"
  try {
    Invoke-WebRequest -Uri "https://repo.anaconda.com/archive/Anaconda3-2025.01-Windows-x86_64.exe" -OutFile $installer -UseBasicParsing
    Write-Info "Starting Anaconda installer (interactive). Please follow the GUI to complete installation."
    Start-Process -FilePath $installer -Wait
    Write-Info "After installation, please re-open this PowerShell session and re-run the script if needed."
  } catch {
    Write-Err "Failed to download or launch Anaconda installer: $_"
    Write-Err "Please install Anaconda manually from https://www.anaconda.com/products/distribution then re-run this script."
    exit 1
  }
} else {
  Write-Info "Conda found on PATH."
}

# --- 8) Create conda env and install dependencies ---
Write-Info "Creating conda environment 'hive-dynamics' (python 3.11) ..."
try {
  & conda create -n hive-dynamics python=3.11 -y
  Write-Info "Installing pip packages into conda env via 'conda run' ... (this may take several minutes)"
  & conda run -n hive-dynamics pip install --upgrade pip
  & conda run -n hive-dynamics pip install -r $requirementsFile
  Write-Info "Python dependencies installed into conda env 'hive-dynamics'."
} catch {
  Write-Err "Failed to create conda env or install packages: $_"
  Write-Err "You can run these commands manually in an Anaconda Prompt:"
  Write-Host "  conda create -n hive-dynamics python=3.11 -y"
  Write-Host "  conda activate hive-dynamics"
  Write-Host "  pip install -r requirements.txt"
  exit 1
}

# --- 9) Final message ---
Write-Host "`n=== SETUP COMPLETE ===`n" -ForegroundColor Green
Write-Info "If you plan to run the full stack:"
Write-Host "  1) Ensure Docker Desktop is installed and running."
Write-Host "  2) Start services: docker compose up -d"
Write-Host "  3) Initialize DB (done automatically on first postgres startup using init_db.sql)"
Write-Host "  4) Activate conda env: conda activate hive-dynamics"
Write-Host "  5) Run tests / agents as needed. Example: python src\cv_pipeline\detector.py"

# End of script
