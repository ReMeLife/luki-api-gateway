# Simple development server startup script for LUKi API Gateway

# Check if virtual environment exists, create if not
if (!(Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
}

# Activate virtual environment
venv\Scripts\Activate.ps1

# Install dependencies if requirements.txt exists
if (Test-Path "requirements.txt") {
    Write-Host "Installing dependencies..."
    pip install -r requirements.txt
}

# Install the package in development mode
Write-Host "Installing package in development mode..."
pip install -e .

# Run the development server
Write-Host "Starting development server..."
python -m luki_api.main
