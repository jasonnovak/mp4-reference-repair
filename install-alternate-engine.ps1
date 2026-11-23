[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$vendorRoot = Join-Path $projectRoot 'vendor\recover_mp4'
$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("mp4repair-extractor-" + [guid]::NewGuid().ToString('N'))
$downloadUrl = 'https://restore.media/blog/recover_MP4.zip'
$expectedSha256 = 'BCCBC8A6F0D5EF7D72564DCE4F4AA059738BE985598502114BB389F60F284247'

$installedExecutable = Join-Path $vendorRoot 'recover_mp4.exe'
if (Test-Path -LiteralPath $installedExecutable) {
    Write-Host "Sony recovery engine is already installed: $installedExecutable"
    exit 0
}

try {
    New-Item -ItemType Directory -Path $stagingRoot | Out-Null
    Write-Host 'Downloading recover_mp4 1.92 from Restore.Media...'
    $archive = Join-Path $stagingRoot 'recover_mp4_192.zip'
    & curl.exe --silent --show-error --location --fail --retry 2 --max-time 60 --output $archive $downloadUrl
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
    Write-Host "Source: $downloadUrl"
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
