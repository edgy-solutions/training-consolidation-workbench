# Verification Script for Module 1

# 1. Check Docker
Write-Host "Checking Docker..."
docker --version
if ($LASTEXITCODE -ne 0) { 
    Write-Error "Docker is not found. Please install Docker Desktop."
    exit 1
}

# 2. Start MinIO
Write-Host "Starting MinIO..."
docker-compose up -d minio
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to start MinIO."
    exit 1
}

# 3. Install Python Dependencies
Write-Host "Installing Python dependencies..."
# Try to find python executable: 'python' or 'py'
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PYTHON_CMD = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PYTHON_CMD = "py"
} else {
    Write-Error "Python not found in PATH. Please install Python."
    exit 1
}

& $PYTHON_CMD -m pip install -e .
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install dependencies."
    exit 1
}

# 4. Create Test Data
Write-Host "Creating test data in data/raw..."
if (-not (Test-Path "data/raw")) {
    New-Item -ItemType Directory -Path "data/raw" | Out-Null
}
Set-Content -Path "data/raw/test_doc.txt" -Value "Hello, this is a test document for the training consolidation workbench."

# 5. Run Dagster Materialization
Write-Host "Running Dagster asset 'raw_documents'..."
# Set default env vars for local dev if not set
$Env:MINIO_ENDPOINT = "localhost:9000"
$Env:MINIO_ACCESS_KEY = "minioadmin"
$Env:MINIO_SECRET_KEY = "minioadmin"

& $PYTHON_CMD -m dagster asset materialize -m src.pipelines.definitions --select raw_documents

if ($LASTEXITCODE -eq 0) {
    Write-Host "Success! Assets materialized."
    Write-Host "You can view the MinIO console at http://localhost:9001 to verify the 'images', 'text', and 'manifests' buckets."
} else {
    Write-Error "Dagster run failed."
    exit 1
}
