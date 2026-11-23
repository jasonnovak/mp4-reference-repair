[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$vendorRoot = Join-Path $projectRoot 'vendor\untrunc'
$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("mp4repair-untrunc-" + [guid]::NewGuid().ToString('N'))

try {
    Write-Host 'Finding the latest anthwlock/untrunc Windows release...'
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/anthwlock/untrunc/releases/latest' -Headers @{ 'User-Agent' = 'MP4-Reference-Repair' }
    $assetName = if ([Environment]::Is64BitOperatingSystem) { 'untrunc_x64.zip' } else { 'untrunc_x32.zip' }
    $asset = $release.assets | Where-Object { $_.name -eq $assetName } | Select-Object -First 1
    if (-not $asset) {
        throw "The latest release does not contain $assetName. Download untrunc manually and pass --engine PATH."
    }

    New-Item -ItemType Directory -Path $stagingRoot | Out-Null
    $archive = Join-Path $stagingRoot $asset.name
    Write-Host ("Downloading {0} ({1:N0} bytes)..." -f $asset.name, $asset.size)
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $archive -Headers @{ 'User-Agent' = 'MP4-Reference-Repair' }
    $expanded = Join-Path $stagingRoot 'expanded'
    Expand-Archive -LiteralPath $archive -DestinationPath $expanded
    $executable = Get-ChildItem -LiteralPath $expanded -Filter 'untrunc.exe' -File -Recurse | Select-Object -First 1
    if (-not $executable) {
        throw 'Downloaded archive did not contain untrunc.exe.'
    }

    New-Item -ItemType Directory -Path $vendorRoot -Force | Out-Null
    # Copy the executable together with any sibling runtime DLLs shipped by the release.
    Get-ChildItem -LiteralPath $executable.DirectoryName -Force |
        Copy-Item -Destination $vendorRoot -Recurse -Force
    $installed = Join-Path $vendorRoot 'untrunc.exe'
    if (-not (Test-Path -LiteralPath $installed)) {
        Copy-Item -LiteralPath $executable.FullName -Destination $installed -Force
    }
    Write-Host "Installed reference engine: $installed"
    Write-Host "Release: $($release.html_url)"
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
