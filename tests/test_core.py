import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mp4repair.core import (
    Atom,
    MediaReport,
    _is_xavc,
    _reference_repair,
    _recover_mp4_template,
    _reported_premature_end,
    _video_frame_rate,
    compatibility,
    default_output,
    scan_atoms,
)


def atom(name: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, name) + payload


class AtomTests(unittest.TestCase):
    def test_scans_normal_atoms(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "clip.mp4"
            path.write_bytes(atom(b"ftyp", b"1234") + atom(b"moov", b"abcd"))
            found = scan_atoms(path)
            self.assertEqual([item.name for item in found], ["ftyp", "moov"])
            self.assertFalse(any(item.truncated for item in found))

    def test_marks_cut_off_atom(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "clip.mp4"
            path.write_bytes(struct.pack(">I4s", 100, b"mdat") + b"short")
            found = scan_atoms(path)
            self.assertEqual(found[0].name, "mdat")
            self.assertTrue(found[0].truncated)


class CompatibilityTests(unittest.TestCase):
    def report(self, stream):
        return MediaReport(Path("x.mp4"), 10, [Atom("moov", 0, 8, 8)], [stream], {}, None)

    def test_identical_stream_scores_100(self):
        stream = {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}
        score, notes = compatibility(self.report(stream), self.report(dict(stream)))
        self.assertEqual(score, 100)
        self.assertEqual(notes, [])

    def test_unprobeable_damaged_is_unknown(self):
        good = self.report({"codec_type": "video", "codec_name": "h264"})
        bad = MediaReport(Path("bad.mp4"), 10, [], [], {}, "missing moov")
        score, notes = compatibility(good, bad)
        self.assertIsNone(score)
        self.assertTrue(notes)

    def test_missing_track_reduces_score(self):
        video = {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}
        audio = {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2}
        good = MediaReport(Path("good.mp4"), 10, [Atom("moov", 0, 8, 8)], [video, audio], {}, None)
        bad = self.report(dict(video))
        score, notes = compatibility(good, bad)
        self.assertLess(score, 100)
        self.assertTrue(any("Track count" in note for note in notes))

    def test_default_output(self):
        result = default_output("camera.mov")
        self.assertEqual(result.name, "camera_repaired.mov")

    def test_detects_xavc_and_frame_rate(self):
        report = MediaReport(
            Path("sony.mp4"),
            10,
            [],
            [{"codec_type": "video", "r_frame_rate": "50/1"}],
            {"tags": {"major_brand": "XAVC"}},
            None,
        )
        self.assertTrue(_is_xavc(report))
        self.assertEqual(_video_frame_rate(report), "50/1")

    def test_reads_recover_mp4_template_recommendation(self):
        lines = ["Now run:", "recover_mp4.exe corrupted_file result.h264 result.wav --sony"]
        self.assertEqual(_recover_mp4_template(lines), "--sony")

    def test_recover_mp4_template_defaults_safely(self):
        self.assertEqual(_recover_mp4_template(["no recommendation"]), "--sony")


class RecoveryLogTests(unittest.TestCase):
    def test_detects_untrunc_premature_end(self):
        lines = [
            "Error: unable to find correct codec -> premature end (~0.4619%)",
            "try '-s' to skip unknown sequences",
        ]
        self.assertTrue(_reported_premature_end(lines))

    def test_normal_completion_is_not_premature(self):
        self.assertFalse(_reported_premature_end(["Info: Found 309 packets", "Info: saving fixed.mp4"]))

    def test_partial_standard_pass_triggers_scan_and_keeps_larger_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reference = root / "good.mp4"
            damaged = root / "bad.mp4"
            output = root / "recovered.mp4"
            reference.write_bytes(b"reference")
            damaged.write_bytes(b"x" * 100_000)
            calls = []

            def fake_run(args, log):
                calls.append(args)
                destination = Path(args[args.index("-dst") + 1])
                if "-s" in args:
                    destination.write_bytes(b"y" * 80_000)
                    log("Info: scan-through completed")
                else:
                    destination.write_bytes(b"y" * 1_000)
                    log("Error: premature end (~1%); try '-s'")
                return 0

            def fake_validate(path, ffprobe=None):
                return MediaReport(path, path.stat().st_size, [], [{"codec_type": "video"}], {}, None)

            with patch("mp4repair.core._run_live", side_effect=fake_run), patch(
                "mp4repair.core._validate_output", side_effect=fake_validate
            ):
                _reference_repair(reference, damaged, output, root / "untrunc.exe", lambda _: None, None)

            self.assertEqual(len(calls), 2)
            self.assertNotIn("-s", calls[0])
            self.assertIn("-s", calls[1])
            self.assertEqual(output.stat().st_size, 80_000)


if __name__ == "__main__":
    unittest.main()
