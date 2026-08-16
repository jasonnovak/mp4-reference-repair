# MP4 Reference Repair

Current version: **1.2.0**. This version adds a separate Sony XAVC elementary-stream recovery engine; version 1.1's untrunc deep scan remains available.

Repair a truncated `.mp4`, `.mov`, `.m4v`, `.3gp`, or `.m4a` recording with a healthy clip from the same camera or recording app. It never modifies either input.

The tool combines two lossless recovery methods:

- **FFmpeg remux** when the damaged file still has readable track metadata.
- **Reference reconstruction** with `untrunc` when an interrupted recording lost its final `moov` movie index.
- **Sony XAVC stream extraction** with the optional `recover_mp4` freeware engine when `untrunc` misclassifies `avc1`/`twos`/`rtmd` payloads.

No video is uploaded. Processing is local.

## Quick start on Windows

The portable Windows ZIP includes both recovery engines. If you copied that package, skip directly to step 2. When using a source-only copy, install the engines once:

1. Install the reference engine once:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install-engine.ps1
   ```

   For Sony XAVC recordings, also install the alternate extractor:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install-alternate-engine.ps1
   ```

2. Double-click **Start MP4 Repair Tool.cmd**.
3. Choose a healthy reference, the damaged recording, and a new output filename.
4. Leave **Method** on `auto` and click **Repair video**.

FFmpeg and FFprobe must be available on `PATH`. The installer downloads the current Windows build of [anthwlock/untrunc](https://github.com/anthwlock/untrunc), an actively maintained GPL-licensed repair engine; it is not part of this project.

## Command line

From this folder:

```powershell
python repair_mp4.py check "broken.mp4" --reference "good.mp4"
python repair_mp4.py repair "good.mp4" "broken.mp4"
python repair_mp4.py repair "good.mp4" "broken.mp4" -o "recovered.mp4"
```

Options:

- `--strategy auto` uses remux when possible, then reference reconstruction as needed.
- `--strategy reference` forces reference reconstruction.
- `--strategy deep-scan` forces reconstruction with `untrunc -s`, scanning past unknown or corrupt byte sequences. It is slower but can recover recordings where an ordinary pass stops after only a few megabytes.
- `--strategy sony-xavc` uses a separate Sony-aware algorithm to extract H.264 and PCM, then remuxes them at the reference frame rate. This is the preferred fallback when an untrunc log reports zero keyframes or substantial unmatched bytes.
- `--strategy remux` only tries FFmpeg; useful when the `moov` atom survived.
- `--engine C:\path\to\untrunc.exe` selects a manually installed engine.
- `--overwrite` replaces an existing output, but never either input.

You can also install the Python command locally with `python -m pip install -e .` and then use `mp4repair`.

## Choosing a good reference

Use a playable clip created by the same device/app and, ideally, the same resolution, frame rate, codec, audio setting, and orientation. It can be short. A reference from a different device or recording mode often cannot reconstruct the sample tables correctly.

## What can and cannot be recovered

A cut-off MP4 often contains intact encoded frames in its `mdat` atom but lacks the `moov` index normally written when recording stops. Reference reconstruction can rebuild that index. Bytes that were never written, overwritten, encrypted, or physically unreadable cannot be recovered. The final partial frame may be dropped, and severely damaged recordings may only be partly recoverable.

Keep the original damaged file until you have watched and scrubbed through the repaired output.
