# Run the ATLAS frontend from a local C:\ shadow.
# Required because Windows refuses to spawn .exe binaries (esbuild) from
# UNC-mapped network drives, which is how the H:\ home drive is mounted on
# corp Windows machines.
#
# Usage:  .\setup-frontend.ps1
#
# Behaviour:
#   1. Mirrors frontend/ -> C:\atlas-frontend\ (excluding node_modules / dist).
#   2. Runs `npm install` inside the shadow.
#   3. Starts `npm run dev` proxying /api -> http://localhost:8000 (the
#      backend running normally on H:).
#
# Live editing: edit files on H:\ as usual, then re-run this script (or
# attach a watcher).  The source folders are mirrored each run.

param(
    [string]$Mode = "dev",   # dev | build | install | clean
    [string]$ShadowDir = "$env:LOCALAPPDATA\atlas-frontend",
    [string]$EsbuildBin = "C:\Users\$env:USERNAME\ds\tools\esbuild\esbuild.exe"
)

$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot 'frontend'

if ($PSScriptRoot -like 'H:*' -or $PSScriptRoot -like '\\*') {
    Write-Host ""
    Write-Host "  IMPORTANT: do NOT run 'npm install' inside $src directly." -ForegroundColor Yellow
    Write-Host "  Corp AppLocker blocks esbuild.exe on network drives. This script" -ForegroundColor Yellow
    Write-Host "  mirrors the source to $ShadowDir and installs/runs from there." -ForegroundColor Yellow
    Write-Host ""
}

if (!(Test-Path $src)) {
    Write-Error "Cannot find frontend dir at $src"
    exit 1
}

if ($Mode -eq 'clean') {
    Write-Host "Cleaning $ShadowDir ..."
    if (Test-Path $ShadowDir) {
        $empty = New-Item -ItemType Directory -Path "$env:TEMP\atlas_empty_$(Get-Random)" -Force
        try { robocopy $empty.FullName $ShadowDir /MIR /NFL /NDL /NJH /NJS /NP | Out-Null } catch {}
        Remove-Item $ShadowDir -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item $empty -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Done."
    exit 0
}

Write-Host "Mirroring $src -> $ShadowDir"
robocopy "$src" "$ShadowDir" /MIR `
    /XD node_modules dist .vite `
    /XF package-lock.json `
    /NFL /NDL /NJH /NJS /NP /NS | Out-Null

Push-Location $ShadowDir
try {
    if ($Mode -eq 'install' -or !(Test-Path 'node_modules\vite')) {
        Write-Host "Running npm install (one-time, can be slow)..."
        npm install --ignore-scripts
        # Manually (re-)create vite shim if missing
        $bin = 'node_modules\.bin'
        if (!(Test-Path "$bin\vite.cmd")) {
            New-Item -ItemType Directory -Path $bin -Force | Out-Null
            $shim = @'
@ECHO off
SETLOCAL
SET "dp0=%~dp0"
"%dp0%\..\..\node_modules\vite\bin\vite.js" %*
'@
            $shim = '@ECHO off' + "`r`n" + 'node "%~dp0..\vite\bin\vite.js" %*'
            Set-Content -Path "$bin\vite.cmd" -Value $shim -Encoding ASCII
        }
    }

    switch ($Mode) {
        'install' { Write-Host "Done." }
        'build'   {
            if (Test-Path $EsbuildBin) { $env:ESBUILD_BINARY_PATH = $EsbuildBin }
            npm run build
        }
        'dev'     {
            if (Test-Path $EsbuildBin) { $env:ESBUILD_BINARY_PATH = $EsbuildBin }
            Write-Host "Frontend:  http://localhost:5173"
            Write-Host "Backend:   http://localhost:8000  (start it separately on H:)"
            npm run dev
        }
    }
}
finally {
    Pop-Location
}
