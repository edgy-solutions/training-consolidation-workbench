$ErrorActionPreference = "Stop"

Write-Host "Starting Data Purge..."
# Pipe 'yes' to auto-confirm if running non-interactively, or user can run python script directly
# For this script, we will ask for confirmation in PowerShell to be safe

$confirm = Read-Host "This will DELETE ALL DATA in Neo4j and Weaviate. Are you sure? (yes/no)"
if ($confirm -eq "yes") {
    # Pass 'yes' to the python script
    "yes" | py purge_data.py
} else {
    Write-Host "Cancelled."
}
