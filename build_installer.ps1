$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildScript = Join-Path $repoRoot 'build_windows.ps1'
$issPath = Join-Path $repoRoot 'installer\UniversalStockDAM.iss'
$isccCandidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)

$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Could not find ISCC.exe (Inno Setup command-line compiler). Install Inno Setup 6 or update `$isccCandidates in this script."
}

Write-Host "== Step 1/2: Building app bundle (models excluded) =="
& $buildScript -ExcludeModels
if ($LASTEXITCODE -ne 0) {
    throw "build_windows.ps1 -ExcludeModels failed with exit code $LASTEXITCODE"
}

Write-Host "== Step 2/2: Compiling installer with Inno Setup =="
& $iscc $issPath
if ($LASTEXITCODE -ne 0) {
    throw "ISCC.exe failed with exit code $LASTEXITCODE"
}

Write-Host "Installer build complete. Output is in: $repoRoot\dist\installer"
