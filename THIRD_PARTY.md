# Third-party components

Reference reconstruction is performed by [anthwlock/untrunc](https://github.com/anthwlock/untrunc), which is licensed under GPL-2.0-or-later. `install-engine.ps1` downloads its current Windows release directly from the project's official GitHub release page into `vendor/untrunc`. That downloaded engine and its FFmpeg runtime libraries remain separate programs and are not covered by this project's MIT license.

FFmpeg and FFprobe are invoked as separate system tools. Their licensing depends on the build installed on the user's system; see [ffmpeg.org/legal.html](https://ffmpeg.org/legal.html).

Sony XAVC elementary-stream extraction can optionally use `recover_mp4` 1.92 by Dmitry Vasilyev. It is separately distributed freeware. `install-alternate-engine.ps1` downloads the unmodified archive from the publisher and verifies its SHA-256 checksum before installation. See the [publisher's download instructions](https://restore.media/blog/how-to-fix-corrupted-mp4-files#method-2).
