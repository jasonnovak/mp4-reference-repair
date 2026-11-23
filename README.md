# MP4 Reference Repair

Current version **1.3.0** ships as a portable Windows x64 ZIP with Python, FFmpeg, FFprobe, and untrunc included.

Repair a truncated `.mp4`, `.mov`, `.m4v`, `.3gp`, or `.m4a` recording with a healthy clip from the same camera or recording app. It never modifies either input.

The tool offers three recovery methods:

- **FFmpeg remux** when the damaged file still has readable track metadata.
- **Reference reconstruction** with `untrunc` when an interrupted recording lost its final `moov` movie index.
- **Sony XAVC stream extraction** with the optional `recover_mp4` freeware engine when `untrunc` misclassifies `avc1`/`twos`/`rtmd` payloads.

No video is uploaded. Processing is local.

## Quick start on Windows

1. Download `MP4-Reference-Repair-1.3.0-Windows-x64.zip` from [GitHub Releases](https://github.com/jasonnovak/mp4-reference-repair/releases/latest) and extract the entire ZIP.
2. Open **MP4 Reference Repair.exe** in the extracted folder.
3. Choose a healthy reference, the damaged recording, and an output filename.
4. Select `sony-xavc` for Sony XAVC footage or leave **Method** on `auto` for other recordings. Click **Repair video**.

The first `sony-xavc` repair downloads the checksum-verified `recover_mp4` 1.92 archive directly from its publisher. The app caches the engine in `%LOCALAPPDATA%\MP4 Reference Repair` and reuses it offline. An existing `RECOVER_MP4_PATH` or `--extractor` still works. Videos are processed locally.

## Command line

From the extracted Windows folder:

```powershell
.\mp4repair.exe check "broken.mp4" --reference "good.mp4"
.\mp4repair.exe repair "good.mp4" "broken.mp4" -o "recovered.mp4"
```

Options:

- `--strategy auto` uses remux when possible, then reference reconstruction as needed.
- `--strategy reference` forces reference reconstruction.
- `--strategy deep-scan` forces reconstruction with `untrunc -s`, scanning past unknown or corrupt byte sequences. It is slower but can recover recordings where an ordinary pass stops after only a few megabytes.
- `--strategy sony-xavc` uses a separate Sony-aware algorithm to extract H.264 and PCM, then remuxes them at the reference frame rate. This is the preferred fallback when an untrunc log reports zero keyframes or substantial unmatched bytes.
- `--strategy remux` only tries FFmpeg; useful when the `moov` atom survived.
- `--engine C:\path\to\untrunc.exe` selects a manually installed engine.
- `--overwrite` replaces an existing output, but never either input.

### Running from source

Install [Python 3.10 or newer](https://www.python.org/downloads/windows/) with Tkinter and put [FFmpeg and FFprobe](https://ffmpeg.org/download.html#build-windows) on `PATH`. On Windows, run `powershell -ExecutionPolicy Bypass -File .\install-engine.ps1` to set up untrunc. Use `python repair_mp4.py` in place of `.\mp4repair.exe`, or run **Start MP4 Repair Tool.cmd** to open the desktop app.

The [Windows release workflow](.github/workflows/windows-release.yml) builds the bundled media tools and exercises the extracted ZIP on Windows. For licenses and build sources see [Third-party components](THIRD_PARTY.md).

## Choosing a good reference

Use a playable clip created by the same device/app and, ideally, the same resolution, frame rate, codec, audio setting, and orientation. It can be short. A reference from a different device or recording mode often cannot reconstruct the sample tables correctly.

## What can and cannot be recovered

A cut-off MP4 often contains intact encoded frames in its `mdat` atom but lacks the `moov` index normally written when recording stops. Reference reconstruction can rebuild that index. Bytes that were never written, overwritten, encrypted, or physically unreadable cannot be recovered. The final partial frame may be dropped, and severely damaged recordings may only be partly recoverable.

Keep the original damaged file until you have watched and scrubbed through the repaired output.
