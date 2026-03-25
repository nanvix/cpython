# e2e-mxc-pptx-test.ps1 — End-to-end PPTX test through MXC (wxc-exec.exe)
#
# Runs the PPTX generator script inside NanVix via the MXC sandbox,
# extracts the base64-encoded PPTX from stdout, decodes and validates it.
#
# Usage:
#   powershell -File nanvix-port\e2e-mxc-pptx-test.ps1

param(
    [string]$WxcExec = "A:\Repos\MXC\src\target\debug\wxc-exec.exe",
    [string]$NanvixBinDir = "A:\Repos\NanVix\bin",
    [string]$RamfsPath = "",
    [string]$OutputPath = "A:\Repos\NanVix\bin\nanvix-hello-mxc.pptx"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

# ── Resolve paths ──
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$testScript = Join-Path $scriptDir "e2e-pptx-test.py"
$nanvixd = Join-Path $NanvixBinDir "nanvixd.exe"

if (-not $RamfsPath) {
    $RamfsPath = Join-Path $NanvixBinDir "cpython-ramfs.img"
}

# ── Validate prerequisites ──
foreach ($f in @($WxcExec, $nanvixd, $RamfsPath, $testScript)) {
    if (-not (Test-Path $f)) {
        Write-Error "Required file not found: $f"
        exit 1
    }
}

Write-Host "=== MXC PPTX End-to-End Test ==="
Write-Host "  wxc-exec: $WxcExec"
Write-Host "  nanvixd:  $nanvixd"
Write-Host "  ramfs:    $RamfsPath"
Write-Host "  script:   $testScript"
Write-Host "  output:   $OutputPath"
Write-Host ""

# ── Read the Python script and escape for JSON ──
$pyScript = Get-Content $testScript -Raw
# Escape for JSON string: backslashes, quotes, newlines, tabs
$jsonScript = $pyScript -replace '\\', '\\' -replace '"', '\"' -replace "`r`n", '\n' -replace "`n", '\n' -replace "`t", '\t'

# ── Build MXC JSON config (use ConvertTo-Json -Compress for proper escaping) ──
$config = @{
    script = $pyScript
    containment = "nanvix"
    timeout = 60000
    nanvix = @{
        nanvixdPath = $nanvixd
        binDir = $NanvixBinDir
        ramfsPath = $RamfsPath
    }
} | ConvertTo-Json -Depth 3 -Compress

$configPath = Join-Path $env:TEMP "mxc-pptx-test.json"
# Write without BOM, no CRLF issues
[IO.File]::WriteAllText($configPath, $config, (New-Object Text.UTF8Encoding $false))
Write-Host "  Config: $configPath"
Write-Host ""

# ── Run via MXC ──
Write-Host "Running PPTX generation via MXC..."
$output = & $WxcExec --debug $configPath 2>$null

if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
    Write-Host "WARNING: wxc-exec exited with code $LASTEXITCODE"
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
    Write-Error "No PPTX data received from MXC"
    Write-Host ""
    Write-Host "MXC output ($($lines.Count) lines):"
    $lines | Select-Object -First 30 | ForEach-Object { Write-Host "  $_" }
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

$required = @("[Content_Types].xml", "ppt/presentation.xml", "ppt/media/image1.png")
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
Write-Host "  [INFO] $slideCount slide(s), $($entries.Count) total entries"

if (-not $allPresent) {
    Write-Error "PPTX validation failed"
    exit 1
}

# ── Cleanup ──
Remove-Item $configPath -Force -ErrorAction SilentlyContinue

# ── Success ──
Write-Host ""
Write-Host "=========================================="
Write-Host "  SUCCESS: MXC PPTX E2E test passed!"
Write-Host "  Output: $OutputPath"
Write-Host "=========================================="
Write-Host ""
Write-Host "To view: Start-Process '$OutputPath'"
