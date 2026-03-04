# Forge Demo Runner (Windows)
# Usage: .\scripts\run_demo.ps1 [-Pack saas_support] [-Port 8000]

param(
    [string]$Pack = "saas_support",
    [int]$Port = 8000,
    [string]$OutputDir = ".\demo_output"
)

Write-Host "🔨 Forge Demo Runner" -ForegroundColor Cyan
Write-Host "   Pack: $Pack"
Write-Host "   Port: $Port"
Write-Host ""

# Generate agency from pack
Write-Host "📦 Generating agency from '$Pack' pack..." -ForegroundColor Yellow
forge create --pack $Pack --output $OutputDir --overwrite

# Find generated directory
$AgencyDir = Get-ChildItem -Path $OutputDir -Directory | Select-Object -First 1

if (-not $AgencyDir) {
    Write-Host "❌ No agency generated" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Agency generated at $($AgencyDir.FullName)" -ForegroundColor Green

# Copy runtime
Write-Host "📦 Packaging runtime..." -ForegroundColor Yellow
$RuntimeSrc = Join-Path $PSScriptRoot "..\forge\runtime"
$RuntimeDst = Join-Path $AgencyDir.FullName "forge\runtime"
if (Test-Path $RuntimeSrc) {
    New-Item -ItemType Directory -Force -Path (Join-Path $AgencyDir.FullName "forge") | Out-Null
    Copy-Item -Recurse -Force $RuntimeSrc $RuntimeDst
}

# Start server
Write-Host ""
Write-Host "🚀 Starting agency API server on port $Port..." -ForegroundColor Green
Write-Host "   API: http://localhost:$Port/docs"
Write-Host "   Health: http://localhost:$Port/health"
Write-Host ""
Set-Location $AgencyDir.FullName
python -m uvicorn api_server:app --host 0.0.0.0 --port $Port
