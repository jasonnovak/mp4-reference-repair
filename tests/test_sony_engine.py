import hashlib
import io
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mp4repair.sony_engine import SonyEngineError, download_extractor


class SonyEngineTests(unittest.TestCase):
    def test_verified_download_is_cached_and_reused_offline(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("recover_mp4.exe", b"x64 engine")
            output.writestr("recover_mp4_x86.exe", b"x86 engine")
        payload = archive.getvalue()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "cache" / "recover_mp4.exe"
            with (
                patch("mp4repair.sony_engine.cached_extractor", return_value=target),
                patch("mp4repair.sony_engine._ARCHIVE_SHA256", hashlib.sha256(payload).hexdigest()),
                patch("mp4repair.sony_engine.urllib.request.urlopen", return_value=io.BytesIO(payload)) as download,
            ):
                self.assertEqual(download_extractor(lambda _: None), target)
                self.assertEqual(download_extractor(lambda _: None), target)
                download.assert_called_once()
            self.assertEqual(target.read_bytes(), b"x64 engine" if struct.calcsize("P") == 8 else b"x86 engine")

    def test_unverified_archive_cannot_create_an_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "cache" / "recover_mp4.exe"
            with (
                patch("mp4repair.sony_engine.cached_extractor", return_value=target),
                patch("mp4repair.sony_engine.urllib.request.urlopen", return_value=io.BytesIO(b"unexpected response")),
                self.assertRaisesRegex(SonyEngineError, "did not match"),
            ):
                download_extractor(lambda _: None)
            self.assertFalse(target.exists())
