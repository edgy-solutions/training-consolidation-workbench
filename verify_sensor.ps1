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
    # Check if uv is in the user path but not refreshed in this session?
    # Fallback to checking if user can run it
    Write-Warning "uv command not found in PATH. Attempting to proceed assuming it might be an alias or missing path entry, but this may fail."
    # Optionally try to find it in common locations or just fail later.
    # For now, we'll error out if we truly can't find it, but let's try one more common location or just exit.
    Write-Error "uv is not installed or not in PATH. Please install it first (see WARP.md) and ensure it is in your PATH."
    exit 1
}

# Create venv if missing
if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv..."
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv venv
    } else {
        python -m venv .venv
    }
}

# Install dependencies
Write-Host "Installing dependencies..."
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv pip install -e .
} else {
    # Fallback to pip if uv missing (but encouraged)
    # Check if running on Windows using .NET method
    $IsWin = [System.Environment]::OSVersion.Platform -eq "Win32NT"
    $PIP_CMD = if ($IsWin) { ".venv\Scripts\pip.exe" } else { ".venv/bin/pip" }
    & $PIP_CMD install -e .
}

# 3. Run Upload Script
Write-Host "Running upload script (test suite)..."
# Use the python from .venv
# Check if running on Windows using .NET method since $IsWindows is unreliable in some PS versions
$IsWin = [System.Environment]::OSVersion.Platform -eq "Win32NT"

if ($IsWin) {
    $VENV_PYTHON = ".venv\Scripts\python.exe"
} else {
    $VENV_PYTHON = ".venv/bin/python"
}
& $VENV_PYTHON upload_test_suite.py

# 4. Hint to run Dagster
Write-Host "`nTo run the Dagster UI:"
$IsWin = [System.Environment]::OSVersion.Platform -eq "Win32NT"
if ($IsWin) {
    Write-Host ".venv\Scripts\dagster dev -m src.pipelines.definitions"
} else {
    Write-Host "source .venv/bin/activate; dagster dev -m src.pipelines.definitions"
}
