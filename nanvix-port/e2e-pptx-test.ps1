# e2e-pptx-test.ps1 — End-to-end test: create PPTX inside NanVix, extract to host
#
# This script:
#   1. Pipes a Python script to nanvixd.exe that creates a PPTX
#   2. Captures the base64-encoded PPTX from stdout
#   3. Decodes and saves the .pptx file
#   4. Validates the output is a valid PPTX (ZIP with Open XML structure)
#
# Usage:
#   powershell -File nanvix-port\e2e-pptx-test.ps1
#   powershell -File nanvix-port\e2e-pptx-test.ps1 -RamfsPath "path\to\custom-ramfs.img"

param(
    [string]$NanvixBinDir = "A:\Repos\NanVix\bin",
    [string]$RamfsPath = "",
    [string]$OutputPath = "A:\Repos\NanVix\bin\nanvix-hello.pptx"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

# ── Resolve paths ──
$nanvixd = Join-Path $NanvixBinDir "nanvixd.exe"
$pythonElf = Join-Path $NanvixBinDir "python.elf"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$testScript = Join-Path $scriptDir "e2e-pptx-test.py"

if (-not $RamfsPath) {
    # Try pptx-enhanced ramfs first, fall back to standard
    $pptxRamfs = Join-Path $NanvixBinDir "cpython-pptx-ramfs.img"
    $stdRamfs = Join-Path $NanvixBinDir "cpython-ramfs.img"
    if (Test-Path $pptxRamfs) {
        $RamfsPath = $pptxRamfs
    } elseif (Test-Path $stdRamfs) {
        $RamfsPath = $stdRamfs
    } else {
        Write-Error "No ramfs image found in $NanvixBinDir"
        exit 1
    }
}

# ── Validate prerequisites ──
foreach ($f in @($nanvixd, $pythonElf, $RamfsPath, $testScript)) {
    if (-not (Test-Path $f)) {
        Write-Error "Required file not found: $f"
        exit 1
    }
}

Write-Host "=== NanVix PPTX End-to-End Test ==="
Write-Host "  nanvixd:  $nanvixd"
Write-Host "  python:   $pythonElf"
Write-Host "  ramfs:    $RamfsPath"
Write-Host "  script:   $testScript"
Write-Host "  output:   $OutputPath"
Write-Host ""

# ── Run Python inside NanVix ──
Write-Host "Running PPTX generation inside NanVix..."
$script = Get-Content $testScript -Raw

$output = $script | & $nanvixd -bin-dir $NanvixBinDir -ramfs $RamfsPath `
    -- $pythonElf "-S -B -c exec(__import__('sys').stdin.read());PYTHONHOME=/sysroot" 2>$null

if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
    Write-Error "nanvixd exited with code $LASTEXITCODE"
    Write-Host "Raw output:"
    Write-Host $output
    exit 1
}

# ── Extract base64 between delimiters ──
$lines = $output -split "`n"
$capturing = $false
$b64Lines = @()

foreach ($line in $lines) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "---PPTX_BASE64_START---") {
        $capturing = $true
        continue
    }
    if ($trimmed -eq "---PPTX_BASE64_END---") {
        $capturing = $false
        continue
    }
    if ($capturing -and $trimmed.Length -gt 0) {
        $b64Lines += $trimmed
    }
}

$b64 = $b64Lines -join ""

if ($b64.Length -eq 0) {
    Write-Error "No PPTX data received from NanVix"
    Write-Host ""
    Write-Host "Raw output ($($lines.Count) lines):"
    $lines | Select-Object -First 50 | ForEach-Object { Write-Host "  $_" }
    exit 1
}

Write-Host "  Received $($b64.Length) chars of base64 data"

# ── Decode and save ──
$bytes = [Convert]::FromBase64String($b64)
[IO.File]::WriteAllBytes($OutputPath, $bytes)
Write-Host "  Saved $($bytes.Length) bytes to $OutputPath"

# ── Validate PPTX structure ──
Write-Host ""
Write-Host "Validating PPTX structure..."

try {
    $zip = [IO.Compression.ZipFile]::OpenRead($OutputPath)
    $entries = $zip.Entries | Select-Object -ExpandProperty FullName
    $zip.Dispose()
} catch {
    Write-Error "Output is not a valid ZIP file: $_"
    exit 1
}

$required = @("[Content_Types].xml", "ppt/presentation.xml")
$allPresent = $true
foreach ($req in $required) {
    if ($entries -contains $req) {
        Write-Host "  [PASS] Contains $req"
    } else {
        Write-Host "  [FAIL] Missing $req"
        $allPresent = $false
    }
}

$slideCount = ($entries | Where-Object { $_ -match "ppt/slides/slide\d+\.xml" }).Count
Write-Host "  [INFO] $slideCount slide(s) found"
Write-Host "  [INFO] $($entries.Count) total entries in PPTX"

if (-not $allPresent) {
    Write-Error "PPTX validation failed — missing required entries"
    exit 1
}

# ── Success ──
Write-Host ""
Write-Host "=========================================="
Write-Host "  SUCCESS: PPTX E2E test passed!"
Write-Host "  Output: $OutputPath"
Write-Host "=========================================="
Write-Host ""
Write-Host "To view: Start-Process '$OutputPath'"
