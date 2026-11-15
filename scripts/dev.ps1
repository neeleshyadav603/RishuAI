# Developer start script (Windows). Installs the core in editable mode and
# opens the text chat. The Flutter app is added to this script in Phase 2.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\core")
python -m pip install -e ".[web,dev]"
python -m rishu_core
