[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$vendorRoot = Join-Path $projectRoot 'vendor\recover_mp4'
$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("mp4repair-extractor-" + [guid]::NewGuid().ToString('N'))
$listingUrl = 'https://www.videohelp.com/download/recover_mp4_192.zip'
$expectedSha256 = 'BCCBC8A6F0D5EF7D72564DCE4F4AA059738BE985598502114BB389F60F284247'

$installedExecutable = Join-Path $vendorRoot 'recover_mp4.exe'
if (Test-Path -LiteralPath $installedExecutable) {
    Write-Host "Sony recovery engine is already installed: $installedExecutable"
    exit 0
}

try {
    New-Item -ItemType Directory -Path $stagingRoot | Out-Null
    Write-Host 'Requesting the recover_mp4 1.92 freeware download from VideoHelp...'
    $listingFile = Join-Path $stagingRoot 'listing.html'
    & curl.exe -L --fail --retry 4 --retry-delay 2 --user-agent 'Mozilla/5.0 MP4-Reference-Repair' --output $listingFile $listingUrl
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $listingFile)) {
        throw 'Could not retrieve the VideoHelp download page.'
    }
    $listingContent = Get-Content -LiteralPath $listingFile -Raw
    $match = [regex]::Match($listingContent, 'recover_mp4_192\.zip\?r=[A-Za-z0-9]+')
    if (-not $match.Success) {
        throw 'VideoHelp did not return a recover_mp4 download token.'
    }
    $downloadUrl = 'https://www.videohelp.com/download/' + $match.Value
    $archive = Join-Path $stagingRoot 'recover_mp4_192.zip'
    & curl.exe -L --fail --retry 4 --retry-delay 2 --user-agent 'Mozilla/5.0 MP4-Reference-Repair' --output $archive $downloadUrl
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $archive)) {
        throw 'Could not download the recover_mp4 archive.'
    }
    $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedSha256) {
        throw "Downloaded archive failed SHA-256 verification. Expected $expectedSha256 but received $actualHash."
    }

    $expanded = Join-Path $stagingRoot 'expanded'
    Expand-Archive -LiteralPath $archive -DestinationPath $expanded
    $executable = Join-Path $expanded 'recover_mp4.exe'
    if (-not (Test-Path -LiteralPath $executable)) {
        throw 'Downloaded archive did not contain recover_mp4.exe.'
    }
    New-Item -ItemType Directory -Path $vendorRoot -Force | Out-Null
    Get-ChildItem -LiteralPath $expanded -Force | Copy-Item -Destination $vendorRoot -Force
    Write-Host "Installed Sony recovery engine: $(Join-Path $vendorRoot 'recover_mp4.exe')"
    Write-Host 'Source: https://www.videohelp.com/software/recover-mp4-to-h264'
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
