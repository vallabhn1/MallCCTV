# init_project.ps1 - Create project structure and placeholder files
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Split-Path -Parent $scriptDir

Write-Host "[INFO] Initializing project in $projectRoot" -ForegroundColor Cyan

# Directories to create
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
    Write-Host "[INFO] Created: $d"
  } else {
    Write-Host "[INFO] Exists: $d"
  }
}

# .env
$envFile = Join-Path $projectRoot '.env'
if (-not (Test-Path $envFile)) {
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
"@ | Out-File -FilePath $envFile -Encoding utf8
  Write-Host "[INFO] .env created"
} else {
  Write-Host "[INFO] .env already exists; skipping."
}

# requirements.txt (if missing, created by install_env earlier; this is a safe check)
$reqFile = Join-Path $projectRoot 'requirements.txt'
if (-not (Test-Path $reqFile)) {
  @"
ultralytics==8.2.82
opencv-python==4.10.0.84
numpy==1.26.4
pandas==2.2.2
"@ | Out-File -FilePath $reqFile -Encoding utf8
  Write-Host "[INFO] requirements.txt created (minimal)"
} else {
  Write-Host "[INFO] requirements.txt exists; skipping."
}

# init_db.sql
$initDb = Join-Path $projectRoot 'init_db.sql'
if (-not (Test-Path $initDb)) {
  @"
-- init_db.sql (placeholder)
CREATE TABLE IF NOT EXISTS detections (id SERIAL PRIMARY KEY, camera_id TEXT, class_name TEXT, confidence REAL, bbox TEXT, track_id INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS alerts (id SERIAL PRIMARY KEY, alert_type TEXT, severity TEXT, camera_id TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, metadata JSONB, acknowledged INTEGER DEFAULT 0);
"@ | Out-File -FilePath $initDb -Encoding utf8
  Write-Host "[INFO] init_db.sql created"
} else {
  Write-Host "[INFO] init_db.sql exists; skipping."
}

# docker-compose.yml
$compose = Join-Path $projectRoot 'docker-compose.yml'
if (-not (Test-Path $compose)) {
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
      - '5432:5432'
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init_db.sql:/docker-entrypoint-initdb.d/init.sql
  redis:
    image: redis:7-alpine
    ports:
      - '6379:6379'
    volumes:
      - redis_data:/data
volumes:
  postgres_data:
  redis_data:
"@ | Out-File -FilePath $compose -Encoding utf8
  Write-Host "[INFO] docker-compose.yml created"
} else {
  Write-Host "[INFO] docker-compose.yml exists; skipping."
}

Write-Host "[OK] Project initialization complete." -ForegroundColor Green
