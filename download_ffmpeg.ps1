param([string]$Root = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root).Path
$runtime = Join-Path $Root 'runtime\ffmpeg'
$temp = Join-Path $env:TEMP 'TaiwanSubtitle-ffmpeg.zip'
$extract = Join-Path $env:TEMP 'TaiwanSubtitle-ffmpeg-extract'
$url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
Write-Host "Project root: $Root"
Write-Host "Downloading FFmpeg essentials from $url"
Invoke-WebRequest -Uri $url -OutFile $temp -UseBasicParsing
Remove-Item -Recurse -Force $extract -ErrorAction SilentlyContinue
Expand-Archive -Path $temp -DestinationPath $extract -Force
$exe = Get-ChildItem -Path $extract -Filter ffmpeg.exe -File -Recurse | Select-Object -First 1
if (-not $exe) { throw 'ffmpeg.exe was not found in the downloaded archive.' }
$target = Join-Path $runtime 'ffmpeg.exe'
Copy-Item -LiteralPath $exe.FullName -Destination $target -Force
if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "FFmpeg copy failed: $target" }
Remove-Item $temp -Force -ErrorAction SilentlyContinue
Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
& $target -version | Select-Object -First 1
Write-Host "FFmpeg ready at: $target"
