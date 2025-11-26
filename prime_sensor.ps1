$ErrorActionPreference = "Stop"

# --- Configuration ---
$bucketName = "training-content"
$sourceDir = "source_docs"

# MinIO Config (defaults, override with env vars)
$minioEndpoint = if ($env:MINIO_ENDPOINT) { $env:MINIO_ENDPOINT } else { "localhost:9000" }
$minioAccessKey = if ($env:MINIO_ACCESS_KEY) { $env:MINIO_ACCESS_KEY } else { "minioadmin" }
$minioSecretKey = if ($env:MINIO_SECRET_KEY) { $env:MINIO_SECRET_KEY } else { "minioadmin" }
$secure = if ($env:MINIO_SECURE -eq "true") { $true } else { $false }

# Check dependencies
if (Get-Command "uv" -ErrorAction SilentlyContinue) {
    # Ensure minio library is available in the venv
    # We'll run a python script using 'uv run' or just assume 'py' has it if not using uv directly for script exec
} else {
    # Fallback check
}

$pyFile = "prime_sensor.py"

Write-Host "Priming Sensor with documents from '$sourceDir'..."

if (Get-Command "uv" -ErrorAction SilentlyContinue) {
    # Assuming 'minio' is installed in the project environment
    uv run python $pyFile
} else {
    python $pyFile
}

