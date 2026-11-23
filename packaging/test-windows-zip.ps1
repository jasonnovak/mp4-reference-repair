[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Zip,
    [Parameter(Mandatory)] [string] $Fixtures
)

$ErrorActionPreference = 'Stop'
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('MP4 Repair ZIP test ' + [guid]::NewGuid())
Expand-Archive -LiteralPath $Zip -DestinationPath $testRoot
$app = Join-Path $testRoot 'MP4 Reference Repair'
$cli = Join-Path $app 'mp4repair.exe'
$ffmpeg = Join-Path $app 'vendor/media/ffmpeg.exe'
$ffprobe = Join-Path $app 'vendor/media/ffprobe.exe'

function Remove-MovieIndex ([string] $Reference, [string] $Damaged) {
    Copy-Item -LiteralPath $Reference -Destination $Damaged
    $file = [System.IO.File]::Open($Damaged, 'Open', 'ReadWrite', 'None')
    try {
        $header = [byte[]]::new(8)
        while ($file.Position + 8 -le $file.Length) {
            $offset = $file.Position
            if ($file.Read($header, 0, 8) -ne 8) { break }
            if ([Text.Encoding]::ASCII.GetString($header, 4, 4) -eq 'moov') {
                $file.SetLength($offset)
                return
            }
            [Array]::Reverse($header, 0, 4)
            $size = [BitConverter]::ToUInt32($header, 0)
            if ($size -lt 8) { break }
            $file.Position = $offset + $size
        }
        throw "No trailing movie index found in $Reference"
    } finally { $file.Dispose() }
}

function Test-RepairedMedia ([string] $File, [int] $Rate, [int] $Channels) {
    # Null output only checks decoding. CFR normalization gives the sink monotonic timestamps.
    & $ffmpeg -v error -xerror -i $File -map 0:v:0 -map 0:a:0 -r $Rate -f null NUL
    if ($LASTEXITCODE) { throw "Decoding failed for $File" }
    $info = & $ffprobe -v error -of json -show_entries stream=codec_name,r_frame_rate,channels:format=duration $File | ConvertFrom-Json
    if ($LASTEXITCODE -or [double]$info.format.duration -lt 1.9 -or [double]$info.format.duration -gt 2.2) {
        throw "Unexpected duration for $File"
    }
    if ($info.streams[0].codec_name -ne 'h264' -or $info.streams[0].r_frame_rate -ne "$Rate/1" -or
        $info.streams[1].codec_name -ne 'aac' -or $info.streams[1].channels -ne $Channels) {
        throw "Unexpected video or audio streams in $File"
    }
}

$originalPath = $env:Path
$originalLocalAppData = $env:LOCALAPPDATA
$originalHttpsProxy = $env:https_proxy
$originalNoProxy = $env:no_proxy
try {
    $env:Path = Join-Path $env:SystemRoot 'System32'
    $env:LOCALAPPDATA = Join-Path $testRoot 'LocalAppData'
    $engine = Join-Path $env:LOCALAPPDATA 'MP4 Reference Repair/recover_mp4/1.92/recover_mp4.exe'
    if (Get-Command python,ffmpeg,ffprobe,untrunc,recover_mp4 -ErrorAction SilentlyContinue) {
        throw 'The smoke test can see a system Python or repair tool'
    }
    if (Get-ChildItem -LiteralPath $app -Filter 'recover_mp4*.exe' -File -Recurse) {
        throw 'The proprietary Sony engine must be downloaded on demand'
    }
    & $cli --version
    if ($LASTEXITCODE) { throw 'Bundled command-line launcher failed' }

    $gui = Start-Process -FilePath (Join-Path $app 'MP4 Reference Repair.exe') -WorkingDirectory $testRoot -WindowStyle Hidden -PassThru
    try {
        if (-not $gui.WaitForInputIdle(15000) -or $gui.WaitForExit(1000)) { throw 'Desktop launcher did not start' }
    } finally {
        if (-not $gui.HasExited) { Stop-Process -Id $gui.Id }
        $gui.Dispose()
    }

    $normal = Join-Path $Fixtures 'standard.mp4'
    $broken = Join-Path $testRoot 'standard cut off.mp4'
    $fixed = Join-Path $testRoot 'standard repaired.mp4'
    Remove-MovieIndex $normal $broken
    & $cli repair $normal $broken -o $fixed --strategy reference
    if ($LASTEXITCODE) { throw 'Bundled untrunc repair failed' }
    Test-RepairedMedia $fixed 30 1

    $remuxed = Join-Path $testRoot 'standard remuxed.mp4'
    & $cli repair $normal $fixed -o $remuxed --strategy remux
    if ($LASTEXITCODE) { throw 'Bundled FFmpeg remux failed' }
    Test-RepairedMedia $remuxed 30 1

    $sony = Join-Path $Fixtures 'sony.mov'
    $sonyBroken = Join-Path $testRoot 'sony cut off.mov'
    $sonyFixed = Join-Path $testRoot 'sony repaired.mp4'
    Remove-MovieIndex $sony $sonyBroken
    & $cli repair $sony $sonyBroken -o $sonyFixed --strategy sony-xavc
    if ($LASTEXITCODE -or -not (Test-Path -LiteralPath $engine -PathType Leaf)) { throw 'First-use Sony engine setup or repair failed' }
    Test-RepairedMedia $sonyFixed 50 2

    $env:https_proxy = 'http://127.0.0.1:1'
    $env:no_proxy = ''
    $sonyOffline = Join-Path $testRoot 'sony cached engine.mp4'
    & $cli repair $sony $sonyBroken -o $sonyOffline --strategy sony-xavc
    if ($LASTEXITCODE) { throw 'Cached Sony repair failed with the download route blocked' }
    Test-RepairedMedia $sonyOffline 50 2
} finally {
    $env:Path = $originalPath
    $env:LOCALAPPDATA = $originalLocalAppData
    $env:https_proxy = $originalHttpsProxy
    $env:no_proxy = $originalNoProxy
    $validated = (Get-Item -LiteralPath $testRoot).FullName
    if ($validated -eq $testRoot) { Remove-Item -LiteralPath $validated -Recurse -Force }
}
