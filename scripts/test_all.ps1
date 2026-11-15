# Run every check that works without Flutter: lint + core tests.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m ruff check core
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m pytest core -q
exit $LASTEXITCODE
