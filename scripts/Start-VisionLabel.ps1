param([string]$DataRoot = "$env:LOCALAPPDATA\DataTracking")
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Installation is incomplete: Python environment is missing.'
}
& $pythonPath -I -m visionlabel.launcher --root $DataRoot
exit $LASTEXITCODE
