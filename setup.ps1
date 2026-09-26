# Run from the project root: 
#   powershell -ExecutionPolicy Bypass -File setup.ps1
# or, if your execution policy already allows local scripts:
#   .\setup.ps1

Write-Host "Creating virtual environment (.venv)..."
python -m venv .venv

Write-Host "Activating virtual environment..."
. .\.venv\Scripts\Activate.ps1

Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

Write-Host "Installing dependencies (requirements-dev.txt)..."
pip install -r requirements-dev.txt

Write-Host ""
Write-Host "Done. The venv is active in this shell."
Write-Host "Next time, activate it with:  .\.venv\Scripts\Activate.ps1"
Write-Host "Run the app with:             python -m cli.main `"Explain VLAN`""
Write-Host "Run the tests with:           pytest -v"
