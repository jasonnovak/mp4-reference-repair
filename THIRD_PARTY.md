# Third-party components

The Windows app contains [CPython](https://docs.python.org/3/license.html) and [Tcl/Tk](https://www.tcl-lang.org/software/tcltk/license.html). Their notices are in `licenses/` in the ZIP. The Windows executables were packaged with [PyInstaller](https://pyinstaller.org/en/stable/license.html).

The app invokes FFmpeg, FFprobe, and untrunc as separate programs in `vendor/media/`.

- [FFmpeg](https://ffmpeg.org/) and FFprobe use the LGPL build of FFmpeg 8.1.3 with shared libraries and external libraries disabled. The LGPL license text is in `licenses/FFmpeg-LGPL-2.1.txt`. FFmpeg's source and build instructions are in `Media-Tools-Corresponding-Source.zip` on the release page. [FFmpeg licensing](https://ffmpeg.org/legal.html)
- [anthwlock/untrunc](https://github.com/anthwlock/untrunc) is licensed under GPL-2.0-or-later and is built from revision `87a5d9202ae48495b9aa6b5880649dbdf32c82d0` against the bundled FFmpeg libraries. The license is in `licenses/Untrunc-GPL-2.0.txt`. Its exact source and build instructions are in the same source ZIP.

Find the corresponding source archive under the assets for [release v1.3.0](https://github.com/jasonnovak/mp4-reference-repair/releases/tag/v1.3.0). The Windows application source is available under this project's MIT license.

The optional Sony XAVC engine `recover_mp4` 1.92 by Dmitry Vasilyev is separately distributed freeware. The app retrieves it on the first `sony-xavc` repair, verifies the publisher archive against a pinned SHA-256 checksum, and saves the executable in the user's local app data. [Publisher download instructions](https://restore.media/blog/how-to-fix-corrupted-mp4-files#method-2)
