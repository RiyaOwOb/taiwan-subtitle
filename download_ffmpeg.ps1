$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root 'runtime\ffmpeg'
$temp = Join-Path $env:TEMP 'TaiwanSubtitle-ffmpeg.zip'
$url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
Write-Host "Downloading FFmpeg essentials from $url"
Invoke-WebRequest -Uri $url -OutFile $temp -UseBasicParsing
$extract = Join-Path $env:TEMP 'TaiwanSubtitle-ffmpeg-extract'
Remove-Item -Recurse -Force $extract -ErrorAction SilentlyContinue
Expand-Archive -Path $temp -DestinationPath $extract -Force
$exe = Get-ChildItem -Path $extract -Filter ffmpeg.exe -Recurse | Select-Object -First 1
if (-not $exe) { throw 'ffmpeg.exe was not found in the downloaded archive.' }
Copy-Item $exe.FullName (Join-Path $runtime 'ffmpeg.exe') -Force
Remove-Item $temp -Force -ErrorAction SilentlyContinue
Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
& (Join-Path $runtime 'ffmpeg.exe') -version | Select-Object -First 1
Write-Host 'FFmpeg ready.'
