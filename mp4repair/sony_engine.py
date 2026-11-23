from __future__ import annotations

import hashlib
import io
import os
import struct
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable


_URL = "https://restore.media/blog/recover_MP4.zip"
_ARCHIVE_SHA256 = "bccbc8a6f0d5ef7d72564dce4f4aa059738be985598502114bb389f60f284247"
_MAX_ARCHIVE_BYTES = 1024 * 1024


class SonyEngineError(RuntimeError):
    """The optional Sony recovery engine could not be installed."""


def cached_extractor() -> Path | None:
    if os.name != "nt":
        return None
    local_data = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return local_data / "MP4 Reference Repair" / "recover_mp4" / "1.92" / "recover_mp4.exe"


def download_extractor(log: Callable[[str], None]) -> Path:
    target = cached_extractor()
    if target is None:
        raise SonyEngineError("Automatic Sony engine setup is available on Windows. Use --extractor PATH to supply an engine.")
    if target.is_file():
        return target

    log("Downloading the Sony XAVC recovery engine (recover_mp4 1.92) from Restore.Media...")
    try:
        request = urllib.request.Request(_URL, headers={"User-Agent": "MP4-Reference-Repair"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read(_MAX_ARCHIVE_BYTES + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise SonyEngineError(f"Sony engine download failed. Check your internet connection and try again. ({exc})") from exc
    if len(payload) > _MAX_ARCHIVE_BYTES or hashlib.sha256(payload).hexdigest() != _ARCHIVE_SHA256:
        raise SonyEngineError("The Sony engine download did not match the verified recover_mp4 1.92 archive.")

    member = "recover_mp4_x86.exe" if struct.calcsize("P") == 4 else "recover_mp4.exe"
    pending = None
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            executable = archive.read(member)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".part", delete=False) as staging:
            pending = Path(staging.name)
            staging.write(executable)
        try:
            pending.replace(target)
        except PermissionError:
            # Another app instance may have installed and started the same engine.
            if not target.is_file():
                raise
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise SonyEngineError(f"Could not install the Sony recovery engine in {target.parent}: {exc}") from exc
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)

    log(f"Sony recovery engine installed at {target}")
    return target
