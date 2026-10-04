param(
    [string]$DataRoot = "$env:LOCALAPPDATA\DataTracking",
    [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$PythonExecutable = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonExecutable)) {
    throw 'The existing .venv was not found. Follow README.md to set up Python 3.12.10.'
}
& $PythonExecutable -m visionlabel.launcher --root $DataRoot --port $Port
exit $LASTEXITCODE
