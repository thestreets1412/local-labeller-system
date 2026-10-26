param(
    [string]$Environment = '',
    [string]$Python = '',
    [switch]$SkipNative
)
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $PSScriptRoot 'install_phase10.py'
$installArguments = @($installer)
if ($Environment) { $installArguments += @('--environment', $Environment) }
if ($SkipNative) { $installArguments += '--skip-native' }
if ($Python) {
    & $Python @installArguments
} elseif (Test-Path -LiteralPath (Join-Path $repository '.venv\Scripts\python.exe')) {
    & (Join-Path $repository '.venv\Scripts\python.exe') @installArguments
} else {
    & py -3.12 @installArguments
}
if ($LASTEXITCODE -ne 0) { throw 'Phase 10 installation failed. See the error above.' }
