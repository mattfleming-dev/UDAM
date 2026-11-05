param(
    # Excludes *.gguf model files from the bundled resources folder. Use this
    # for installer builds where end users supply their own model weights
    # (see build_installer.ps1). Regular dev builds should omit this switch.
    [switch]$ExcludeModels
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distDir = Join-Path $repoRoot 'dist/windows'
$buildDir = Join-Path $repoRoot 'build/windows'
$venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found at $venvPython. Create it first with: python -m venv .venv"
}

& $venvPython -m pip install --upgrade pip pyinstaller

$pyinstallerArgs = @(
    '--noconfirm',
    '--windowed',
    '--clean',
    '--name', 'UniversalStockDAM',
    '--distpath', $distDir,
    '--workpath', $buildDir,
    '--paths', $repoRoot,
    '--hidden-import', 'PySide6',
    '--hidden-import', 'PySide6.QtCore',
    '--hidden-import', 'PySide6.QtGui',
    '--hidden-import', 'PySide6.QtWidgets'
)

if (Test-Path (Join-Path $repoRoot 'settings.yaml')) {
    $pyinstallerArgs += @('--add-data=' + ((Join-Path $repoRoot 'settings.yaml') + ';.'))
}

if (Test-Path (Join-Path $repoRoot 'README.md')) {
    $pyinstallerArgs += @('--add-data=' + ((Join-Path $repoRoot 'README.md') + ';.'))
}

if (Test-Path (Join-Path $repoRoot 'resources')) {
    $resourcesSourceDir = Join-Path $repoRoot 'resources'

    if ($ExcludeModels) {
        # Stage a filtered copy of resources/ without .gguf model weights so
        # the installer build doesn't bundle multi-GB model files.
        $stagedResourcesDir = Join-Path $buildDir 'resources-staged'
        if (Test-Path $stagedResourcesDir) {
            Remove-Item -Recurse -Force $stagedResourcesDir
        }
        New-Item -ItemType Directory -Path $stagedResourcesDir -Force | Out-Null

        robocopy $resourcesSourceDir $stagedResourcesDir /E /XF *.gguf /NFL /NDL /NJH /NJS /NC /NS | Out-Null
        if ($LASTEXITCODE -ge 8) {
            throw "robocopy failed while staging resources without models (exit code $LASTEXITCODE)"
        }

        $resourcesSourceDir = $stagedResourcesDir
        Write-Host "Excluding *.gguf model files from bundled resources (installer build)."
    }

    $pyinstallerArgs += @('--add-data=' + ($resourcesSourceDir + ';resources'))
}

$pyinstallerArgs += (Join-Path $repoRoot 'main.py')

& $venvPython -m PyInstaller @pyinstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$mcpPyinstallerArgs = @(
    '--noconfirm',
    '--clean',
    '--onefile',
    '--console',
    '--name', 'UniversalStockDAM-MCP',
    '--distpath', (Join-Path $distDir 'UniversalStockDAM'),
    '--workpath', (Join-Path $buildDir 'mcp-server'),
    '--paths', $repoRoot
)

& $venvPython -m PyInstaller @mcpPyinstallerArgs (Join-Path $repoRoot 'mcp_server.py')
if ($LASTEXITCODE -ne 0) {
    throw "MCP server build failed with exit code $LASTEXITCODE"
}

Write-Host "Build complete. Executables are in: $distDir/UniversalStockDAM"
