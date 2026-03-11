Hive Dynamics - Windows setup summary
====================================

What's been created:
 - Project folders (src/, config/, data/, models/, logs/, tests/)
 - .env (placeholders) at: C:\Users\Vallabhj\hive-dynamics\.env
 - requirements.txt at: C:\Users\Vallabhj\hive-dynamics\requirements.txt
 - init_db.sql placeholder at: C:\Users\Vallabhj\hive-dynamics\init_db.sql
 - docker-compose.yml at: C:\Users\Vallabhj\hive-dynamics\docker-compose.yml

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

