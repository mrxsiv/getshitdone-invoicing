# Build GET SHIT DONE: PyInstaller exe + bundled Chromium + Inno Setup installer.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$py   = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

Write-Host "==> PyInstaller" -ForegroundColor Cyan
& $py -m PyInstaller "packaging\gsd.spec" --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "==> Bundling Chromium browser" -ForegroundColor Cyan
$browsers = "dist\GETSHITDONE\browsers"
New-Item -ItemType Directory -Force -Path $browsers | Out-Null
Get-ChildItem "$env:LOCALAPPDATA\ms-playwright" -Directory |
  Where-Object { $_.Name -like "chromium*" } |
  ForEach-Object { Copy-Item $_.FullName "$browsers\$($_.Name)" -Recurse -Force }
Copy-Item "$env:LOCALAPPDATA\ms-playwright\.links" "$browsers\.links" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "==> Inno Setup installer" -ForegroundColor Cyan
& $iscc "packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

Write-Host "==> Done. Installer is in packaging\Output\" -ForegroundColor Green
Get-ChildItem "packaging\Output\*.exe" | Select-Object Name, @{n="MB";e={[math]::Round($_.Length/1MB,1)}}
