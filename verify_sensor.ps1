# Verification Script for Sensor (PowerShell)

# 0. Load .env if present
if (Test-Path ".env") {
    Write-Host "Loading .env file..."
    Get-Content .env | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
        $key, $value = $_.Split('=', 2)
        [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), [System.EnvironmentVariableTarget]::Process)
    }
}

# 1. Check Docker & MinIO (Skip if external)
if (-not $Env:USE_EXTERNAL_MINIO) {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        docker-compose up -d minio
        
        # Default local env vars
        $Env:MINIO_ENDPOINT = "localhost:9000"
        $Env:MINIO_ACCESS_KEY = "minioadmin"
        $Env:MINIO_SECRET_KEY = "minioadmin"
    } else {
        Write-Host "Skipping Docker start (assuming external or already running)..."
    }
} else {
    Write-Host "Running in External MinIO Mode..."
    if (-not $Env:MINIO_ENDPOINT) {
        Write-Error "Error: MINIO_ENDPOINT must be set when USE_EXTERNAL_MINIO is true."
        exit 1
    }
}

# 2. Setup Environment with uv
Write-Host "Setting up Python environment with uv..."

# Check for uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not installed. Please install it first (see WARP.md)."
    exit 1
}

# Create venv if missing
if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv..."
    uv venv
}

# Install dependencies
Write-Host "Installing dependencies..."
uv pip install -e .

# 3. Run Upload Script
Write-Host "Running upload script..."
# Use the python from .venv
$VENV_PYTHON = if ($IsWindows) { ".venv\Scripts\python.exe" } else { ".venv/bin/python" }
& $VENV_PYTHON verify_sensor_upload.py

# 4. Hint to run Dagster
Write-Host "`nTo run the Dagster UI:"
if ($IsWindows) {
    Write-Host ".venv\Scripts\dagster dev -m src.pipelines.definitions"
} else {
    Write-Host "source .venv/bin/activate; dagster dev -m src.pipelines.definitions"
}
