$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& "$PSScriptRoot\build_windows.bat"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
