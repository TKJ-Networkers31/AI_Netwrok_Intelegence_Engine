#!/usr/bin/env bash
# Run from the project root:
#   ./setup.sh
set -euo pipefail

echo "Creating virtual environment (.venv)..."
python3 -m venv .venv

echo "Activating virtual environment..."
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing dependencies (requirements-dev.txt)..."
pip install -r requirements-dev.txt

echo
echo "Done. The venv is active in this shell."
echo "Next time, activate it with:  source .venv/bin/activate"
echo "Run the app with:             python -m cli.main \"Explain VLAN\""
echo "Run the tests with:           pytest -v"
