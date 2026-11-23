from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Callable

from .sony_engine import SonyEngineError, cached_extractor, download_extractor


LogFn = Callable[[str], None]
MEDIA_EXTENSIONS = {".mp4", ".mov", ".m4v", ".3gp", ".m4a"}


class RepairError(RuntimeError):
    """A repair could not be completed safely."""


@dataclass(frozen=True)
class Atom:
    name: str
    offset: int
    declared_size: int
    available_size: int
    truncated: bool = False


@dataclass
class MediaReport:
    path: Path
    size: int
    atoms: list[Atom] = field(default_factory=list)
    streams: list[dict] = field(default_factory=list)
    format: dict = field(default_factory=dict)
    probe_error: str | None = None

    @property
    def atom_names(self) -> list[str]:
        return [a.name for a in self.atoms]

    @property
    def has_moov(self) -> bool:
        return "moov" in self.atom_names

    @property
    def has_mdat(self) -> bool:
        return "mdat" in self.atom_names

    @property
    def is_probeable(self) -> bool:
        return bool(self.streams) and self.probe_error is None


@dataclass
class RepairResult:
    output: Path
    method: str
    report: MediaReport


def _app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _tool(name: str) -> str | None:
    if os.name == "nt" and name in {"ffmpeg", "ffprobe"}:
        bundled = _app_directory() / "vendor" / "media" / f"{name}.exe"
        if bundled.is_file():
            return str(bundled)
    return shutil.which(name)


def find_untrunc(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("UNTRUNC_PATH"):
        candidates.append(Path(os.environ["UNTRUNC_PATH"]))

    here = _app_directory()
    candidates.extend(
        [
            here / "vendor" / "media" / "untrunc.exe",
            here / "vendor" / "untrunc" / "untrunc.exe",
            here / "vendor" / "untrunc" / "untrunc",
            here / "tools" / "untrunc.exe",
        ]
    )
    on_path = _tool("untrunc") or _tool("untrunc.exe")
    if on_path:
        candidates.append(Path(on_path))
    return next((p.resolve() for p in candidates if p.is_file()), None)


def find_recover_mp4(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("RECOVER_MP4_PATH"):
        candidates.append(Path(os.environ["RECOVER_MP4_PATH"]))
    here = _app_directory()
    candidates.extend(
        [
            here / "vendor" / "recover_mp4" / "recover_mp4.exe",
            here / "tools" / "recover_mp4.exe",
        ]
    )
    if cached := cached_extractor():
        candidates.append(cached)
    on_path = _tool("recover_mp4") or _tool("recover_mp4.exe")
    if on_path:
        candidates.append(Path(on_path))
    return next((p.resolve() for p in candidates if p.is_file()), None)


def scan_atoms(path: Path) -> list[Atom]:
    """Read top-level ISO BMFF atoms without loading media payloads."""
    file_size = path.stat().st_size
    atoms: list[Atom] = []
    offset = 0
    with path.open("rb") as fh:
        while offset + 8 <= file_size:
            fh.seek(offset)
            header = fh.read(16)
            if len(header) < 8:
                break
            size32, raw_name = struct.unpack(">I4s", header[:8])
            name = raw_name.decode("latin-1", "replace")
            header_size = 8
            if size32 == 1:
                if len(header) < 16:
                    break
                declared = struct.unpack(">Q", header[8:16])[0]
                header_size = 16
            elif size32 == 0:
                declared = file_size - offset
            else:
                declared = size32

            # Garbage or a corrupt length: record it, then stop rather than seek wildly.
            if declared < header_size:
                atoms.append(Atom(name, offset, declared, max(0, file_size - offset), True))
                break
            available = min(declared, file_size - offset)
            truncated = declared > file_size - offset
            atoms.append(Atom(name, offset, declared, available, truncated))
            if truncated or declared == 0:
                break
            offset += declared
    return atoms


def _run_capture(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def probe(path: Path, ffprobe: str | None = None) -> tuple[list[dict], dict, str | None]:
    exe = ffprobe or _tool("ffprobe")
    if not exe:
        return [], {}, "ffprobe was not found. Install FFmpeg or add ffprobe to PATH."
    result = _run_capture(
        [
            exe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    if result.returncode != 0:
        message = result.stderr.strip() or f"ffprobe exited with code {result.returncode}"
        return [], {}, message
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return [], {}, f"ffprobe returned invalid JSON: {exc}"
    return payload.get("streams", []), payload.get("format", {}), None


def inspect_media(path: str | os.PathLike[str], ffprobe: str | None = None) -> MediaReport:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise RepairError(f"File not found: {source}")
    streams, fmt, error = probe(source, ffprobe)
    return MediaReport(source, source.stat().st_size, scan_atoms(source), streams, fmt, error)


def _stream_value(stream: dict, key: str) -> str:
    value = stream.get(key, "")
    return str(value).casefold()


def compatibility(reference: MediaReport, damaged: MediaReport) -> tuple[int | None, list[str]]:
    """Return a 0-100 reference match score when both files are probeable."""
    notes: list[str] = []
    if not reference.is_probeable:
        return 0, ["The reference file is not readable as media."]
    if not damaged.is_probeable:
        return None, ["The damaged file has no readable track metadata; compatibility cannot be pre-checked."]

    checks: list[tuple[bool, int, str]] = []
    if len(reference.streams) != len(damaged.streams):
        notes.append(f"Track count differs: reference {len(reference.streams)}, damaged {len(damaged.streams)}.")

    weights = {
        "codec_type": 18,
        "codec_name": 22,
        "codec_tag_string": 10,
        "width": 10,
        "height": 10,
        "pix_fmt": 5,
        "sample_rate": 8,
        "channels": 7,
        "time_base": 5,
        "profile": 5,
    }
    stream_types = sorted(
        {str(item.get("codec_type", "unknown")) for item in reference.streams + damaged.streams}
    )
    for stream_type in stream_types:
        good_group = sorted(
            (s for s in reference.streams if str(s.get("codec_type", "unknown")) == stream_type),
            key=lambda s: s.get("index", 0),
        )
        bad_group = sorted(
            (s for s in damaged.streams if str(s.get("codec_type", "unknown")) == stream_type),
            key=lambda s: s.get("index", 0),
        )
        # Missing/extra tracks matter, but should not outweigh matching video
        # codec and geometry when a partially readable file is inspected.
        for _ in range(abs(len(good_group) - len(bad_group))):
            checks.append((False, 25, "track_count"))
        for index, (good, bad) in enumerate(zip(good_group, bad_group), start=1):
            label = f"{stream_type} track {index}"
            for key, weight in weights.items():
                gv, bv = _stream_value(good, key), _stream_value(bad, key)
                if not gv and not bv:
                    continue
                match = gv == bv
                checks.append((match, weight, key))
                if not match:
                    notes.append(f"{label} {key} differs: reference {gv or 'n/a'}, damaged {bv or 'n/a'}.")
    if not checks:
        return 0, notes + ["No comparable stream properties were found."]
    earned = sum(weight for match, weight, _ in checks if match)
    possible = sum(weight for _, weight, _ in checks)
    return round(100 * earned / possible), notes


def describe(report: MediaReport) -> str:
    atoms = ", ".join(
        f"{a.name}{' (cut off)' if a.truncated else ''}" for a in report.atoms
    ) or "none recognized"
    lines = [
        f"File: {report.path}",
        f"Size: {report.size:,} bytes",
        f"Top-level atoms: {atoms}",
        f"Readable tracks: {len(report.streams)}",
    ]
    if report.probe_error:
        lines.append(f"Probe result: {report.probe_error}")
    elif report.format.get("duration"):
        lines.append(f"Duration: {report.format['duration']} seconds")
    if report.has_mdat and not report.has_moov:
        lines.append("Diagnosis: media payload exists, but the movie index (moov) is missing; use reference repair.")
    elif report.is_probeable:
        lines.append("Diagnosis: metadata is readable; a lossless remux may recover all complete packets.")
    else:
        lines.append("Diagnosis: container metadata is damaged or incomplete.")
    return "\n".join(lines)


def _run_live(args: list[str], log: LogFn, cwd: Path | None = None) -> int:
    log("$ " + subprocess.list2cmdline(args))
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=str(cwd) if cwd else None,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert process.stdout is not None
    for line in process.stdout:
        log(line.rstrip())
    return process.wait()


def _is_xavc(report: MediaReport) -> bool:
    if str(report.format.get("tags", {}).get("major_brand", "")).casefold() == "xavc":
        return True
    ftyp = next((atom for atom in report.atoms if atom.name == "ftyp" and not atom.truncated), None)
    if ftyp is None:
        return False

    # A truncated recording can retain its file type even when ffprobe can't read its tracks.
    with report.path.open("rb") as clip:
        clip.seek(ftyp.offset)
        header_size = 16 if clip.read(4) == b"\x00\x00\x00\x01" else 8
        clip.seek(ftyp.offset + header_size)
        payload = clip.read(max(0, min(ftyp.available_size - header_size, 4096))).upper()
    return payload[:4] == b"XAVC" or any(
        payload[offset : offset + 4] == b"XAVC" for offset in range(8, len(payload), 4)
    )


def _video_frame_rate(report: MediaReport) -> str:
    video = next((s for s in report.streams if s.get("codec_type") == "video"), None)
    if not video:
        raise RepairError("The reference has no video track.")
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = str(video.get(key, ""))
        try:
            rate = Fraction(value)
        except (ValueError, ZeroDivisionError):
            continue
        if rate > 0:
            return f"{rate.numerator}/{rate.denominator}"
    raise RepairError("Could not determine the reference video frame rate.")


def _recover_mp4_template(lines: list[str], default: str = "--sony") -> str:
    """Read recover_mp4's recorder-template recommendation from analyze output."""
    allowed = {
        "--sony",
        "--lav",
        "--mainconcept",
        "--qt",
        "--ext",
        "--gopro4",
        "--ambarella",
    }
    for line in reversed(lines):
        match = re.search(r"recover_mp4(?:\.exe)?\s+corrupted_file\s+\S+\s+\S+\s+(--[\w.]+)", line)
        if match and match.group(1) in allowed:
            return match.group(1)
    return default


def _temp_output(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{output.stem}.recovery-part.", suffix=output.suffix, dir=output.parent
    )
    os.close(fd)
    temp = Path(name)
    temp.unlink()  # Repair programs expect a destination that does not exist.
    return temp


def _validate_output(path: Path, ffprobe: str | None = None) -> MediaReport:
    if not path.is_file() or path.stat().st_size == 0:
        raise RepairError("The repair program did not create a non-empty output file.")
    report = inspect_media(path, ffprobe)
    if not report.streams:
        raise RepairError(f"The produced file has no readable media tracks: {report.probe_error or 'unknown error'}")
    return report


def _recovery_coverage(output: Path, damaged: Path) -> float:
    """Approximate how much source payload made it into a repaired container."""
    if not output.is_file() or damaged.stat().st_size <= 0:
        return 0.0
    return output.stat().st_size / damaged.stat().st_size


def _reported_premature_end(lines: list[str]) -> bool:
    joined = "\n".join(lines).casefold()
    return "premature end" in joined or "try '-s'" in joined or 'try "-s"' in joined


def _commit_temp(temp: Path, output: Path, overwrite: bool) -> None:
    if output.exists():
        if not overwrite:
            raise RepairError(f"Output already exists: {output}. Use --overwrite to replace it.")
        output.unlink()
    temp.replace(output)


def _remux(damaged: Path, temp: Path, ffmpeg: str, log: LogFn) -> None:
    code = _run_live(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-err_detect",
            "ignore_err",
            "-i",
            str(damaged),
            "-map",
            "0",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temp),
        ],
        log,
    )
    if code != 0:
        raise RepairError(f"FFmpeg remux failed with exit code {code}.")


def _reference_repair(
    reference: Path,
    damaged: Path,
    temp: Path,
    engine: Path,
    log: LogFn,
    ffprobe: str | None,
    force_scan: bool = False,
) -> MediaReport:
    standard = ("standard", [str(engine), "-n", "-dst", str(temp), str(reference), str(damaged)])
    scan = ("scan-through", [str(engine), "-n", "-s", "-dst", str(temp), str(reference), str(damaged)])
    attempts = [scan] if force_scan else [standard, scan]
    last_error = "unknown failure"
    candidates: list[tuple[Path, MediaReport, float]] = []
    try:
        for label, args in attempts:
            if temp.exists():
                temp.unlink()
            attempt_lines: list[str] = []

            def attempt_log(line: str) -> None:
                attempt_lines.append(line)
                log(line)

            log(f"Reference reconstruction ({label} pass)...")
            code = _run_live(args, attempt_log)
            try:
                report = _validate_output(temp, ffprobe)
                coverage = _recovery_coverage(temp, damaged)
                log(
                    f"{label.capitalize()} pass recovered approximately "
                    f"{coverage:.2%} of the damaged file's byte volume."
                )
                if code != 0:
                    log(f"Engine exited with code {code}, but its output passed media validation.")

                premature = _reported_premature_end(attempt_lines)
                suspicious = premature or coverage < 0.02
                if label == "standard" and not suspicious:
                    return report

                candidate = temp.with_name(f"{temp.stem}.{label}.candidate{temp.suffix}")
                if candidate.exists():
                    candidate.unlink()
                temp.replace(candidate)
                report.path = candidate
                candidates.append((candidate, report, coverage))

                if label == "standard":
                    reason = "reported a premature end" if premature else "recovered less than 2%"
                    log(
                        f"The standard pass {reason}; automatically continuing with "
                        "the deep scan-through pass (-s)."
                    )
            except RepairError as exc:
                last_error = str(exc)
                log(f"{label.capitalize()} pass did not produce a valid file: {exc}")

        if not candidates:
            raise RepairError(f"Reference reconstruction failed: {last_error}")

        # Prefer the candidate containing the greatest recovered byte volume.
        # This prevents a tiny, technically probeable metadata-only result from
        # winning over a much more complete scan-through recovery.
        selected, report, coverage = max(candidates, key=lambda item: item[0].stat().st_size)
        selected.replace(temp)
        report.path = temp
        if coverage < 0.02:
            log(
                "WARNING: Even the best candidate recovered less than 2% of the source. "
                "It is probably only a partial recovery; try a closer reference clip."
            )
        else:
            log(f"Selected the best recovery candidate ({coverage:.2%} byte coverage).")
        return report
    finally:
        for candidate, _, _ in candidates:
            if candidate.exists():
                candidate.unlink()


def _sony_extract_repair(
    reference: Path,
    damaged: Path,
    temp: Path,
    extractor: Path,
    ffmpeg: str,
    reference_report: MediaReport,
    log: LogFn,
    ffprobe: str | None,
) -> MediaReport:
    """Recover Sony XAVC elementary streams with recover_mp4, then remux."""
    fps = _video_frame_rate(reference_report)
    work = Path(tempfile.mkdtemp(prefix=".mp4repair-sony-", dir=temp.parent))
    try:
        log(f"Using Sony elementary-stream extractor: {extractor}")
        log("Analyzing the healthy XAVC reference...")
        analysis_lines: list[str] = []

        def analysis_log(line: str) -> None:
            analysis_lines.append(line)
            log(line)

        code = _run_live([str(extractor), str(reference), "--analyze"], analysis_log, cwd=work)
        video_header = work / "video.hdr"
        if code != 0 or not video_header.is_file():
            raise RepairError("recover_mp4 could not analyze the healthy reference or create video.hdr.")

        raw_video = work / "recovered.h264"
        raw_audio = work / "recovered.wav"
        template = _recover_mp4_template(analysis_lines, "--sony")
        log(f"Extracting H.264 and PCM with the recommended {template} template...")
        extraction_lines: list[str] = []

        def extraction_log(line: str) -> None:
            extraction_lines.append(line)
            log(line)

        code = _run_live(
            [str(extractor), str(damaged), str(raw_video), str(raw_audio), template],
            extraction_log,
            cwd=work,
        )
        if code != 0 and not raw_video.is_file():
            raise RepairError(f"Sony stream extraction failed with exit code {code}.")
        if not raw_video.is_file() or raw_video.stat().st_size < 1024:
            raise RepairError("Sony stream extraction did not recover a usable H.264 stream.")
        video_coverage = raw_video.stat().st_size / damaged.stat().st_size
        if video_coverage < 0.01:
            raise RepairError(
                f"Sony extraction recovered only {video_coverage:.2%} as H.264; "
                "the selected template did not match the recording."
            )
        if not any("idr frame" in line.casefold() or "idr nal unit size" in line.casefold() for line in extraction_lines):
            raise RepairError("Sony extraction found H.264 data but no independently decodable IDR keyframe.")

        log(
            f"Extracted video: {raw_video.stat().st_size:,} bytes; "
            f"audio: {raw_audio.stat().st_size if raw_audio.is_file() else 0:,} bytes."
        )
        mux_args = [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-fflags",
            "+genpts",
            "-r",
            fps,
            "-i",
            str(raw_video),
        ]
        has_audio = raw_audio.is_file() and raw_audio.stat().st_size > 1024
        if has_audio:
            mux_args.extend(["-i", str(raw_audio)])
        mux_args.extend(["-map", "0:v:0"])
        if has_audio:
            mux_args.extend(["-map", "1:a:0", "-c:a", "aac", "-b:a", "256k"])
        mux_args.extend(["-c:v", "copy", "-movflags", "+faststart", str(temp)])

        log(f"Remuxing recovered streams at {fps} fps...")
        code = _run_live(mux_args, log, cwd=work)
        if code != 0:
            raise RepairError(f"FFmpeg could not remux the extracted Sony streams (exit code {code}).")
        return _validate_output(temp, ffprobe)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def default_output(damaged: str | os.PathLike[str]) -> Path:
    source = Path(damaged).expanduser().resolve()
    suffix = source.suffix if source.suffix.casefold() in MEDIA_EXTENSIONS else ".mp4"
    return source.with_name(f"{source.stem}_repaired{suffix}")


def repair(
    reference: str | os.PathLike[str],
    damaged: str | os.PathLike[str],
    output: str | os.PathLike[str] | None = None,
    *,
    strategy: str = "auto",
    engine: str | os.PathLike[str] | None = None,
    extractor: str | os.PathLike[str] | None = None,
    overwrite: bool = False,
    log: LogFn | None = None,
) -> RepairResult:
    logger = log or (lambda _: None)
    good = Path(reference).expanduser().resolve()
    bad = Path(damaged).expanduser().resolve()
    out = Path(output).expanduser().resolve() if output else default_output(bad)
    if strategy not in {"auto", "reference", "deep-scan", "sony-xavc", "remux"}:
        raise RepairError(f"Unknown strategy: {strategy}")
    for path, label in ((good, "Reference"), (bad, "Damaged")):
        if not path.is_file():
            raise RepairError(f"{label} file not found: {path}")
    if good == bad or os.path.samefile(good, bad):
        raise RepairError("The reference and damaged paths must be different files.")
    if out in {good, bad}:
        raise RepairError("Output must not overwrite either input file.")
    if out.exists() and not overwrite:
        raise RepairError(f"Output already exists: {out}. Choose another name or use --overwrite.")

    ffprobe = _tool("ffprobe")
    ffmpeg = _tool("ffmpeg")
    if not ffprobe:
        raise RepairError("ffprobe was not found. Install FFmpeg and ensure it is on PATH.")

    ref_report = inspect_media(good, ffprobe)
    bad_report = inspect_media(bad, ffprobe)
    if not ref_report.is_probeable or not ref_report.has_moov:
        raise RepairError("The reference is not a complete, readable MP4/MOV file with a moov atom.")
    score, notes = compatibility(ref_report, bad_report)
    if score is not None:
        logger(f"Reference compatibility score: {score}/100")
        for note in notes[:8]:
            logger("Warning: " + note)
    else:
        logger(notes[0])

    temp = _temp_output(out)
    try:
        # A readable truncated file normally has an early moov atom; lossless remux is
        # more conservative than rebuilding its sample tables from a donor.
        if strategy == "remux" or (strategy == "auto" and bad_report.is_probeable):
            if not ffmpeg:
                if strategy == "remux":
                    raise RepairError("ffmpeg was not found. Install FFmpeg and ensure it is on PATH.")
            else:
                try:
                    logger("Trying lossless packet recovery with FFmpeg...")
                    _remux(bad, temp, ffmpeg, logger)
                    output_report = _validate_output(temp, ffprobe)
                    _commit_temp(temp, out, overwrite)
                    output_report.path = out
                    return RepairResult(out, "ffmpeg-remux", output_report)
                except RepairError as exc:
                    logger(f"Lossless remux was not sufficient: {exc}")
                    if strategy == "remux":
                        raise

        auto_xavc = strategy == "auto" and (_is_xavc(bad_report) or _is_xavc(ref_report))
        if strategy == "sony-xavc" or auto_xavc:
            if auto_xavc:
                logger("Auto detected Sony XAVC. Trying Sony recovery...")
            try:
                if not ffmpeg:
                    raise RepairError("Sony XAVC recovery requires FFmpeg.")
                sony_extractor = find_recover_mp4(extractor)
                if not sony_extractor:
                    if extractor is not None:
                        raise RepairError(f"Sony recovery engine not found: {extractor}")
                    sony_extractor = download_extractor(logger)
                output_report = _sony_extract_repair(
                    good,
                    bad,
                    temp,
                    sony_extractor,
                    ffmpeg,
                    ref_report,
                    logger,
                    ffprobe,
                )
            except (RepairError, SonyEngineError, OSError) as exc:
                if strategy == "sony-xavc":
                    raise RepairError(str(exc)) from exc
                logger(f"Sony XAVC recovery was unavailable or failed: {exc} Trying reference reconstruction...")
            else:
                _commit_temp(temp, out, overwrite)
                output_report.path = out
                return RepairResult(out, "sony-xavc-extraction", output_report)

        chosen_engine = find_untrunc(engine)
        if score is not None and score < 55:
            raise RepairError(
                "The reference appears incompatible (score below 55/100). "
                "Use a clip from the same device and recording settings."
            )
        if not chosen_engine:
            raise RepairError(
                "Reference repair is required, but untrunc was not found. "
                "Run install-engine.ps1, pass --engine PATH, or set UNTRUNC_PATH."
            )
        logger(f"Using reference engine: {chosen_engine}")
        output_report = _reference_repair(
            good,
            bad,
            temp,
            chosen_engine,
            logger,
            ffprobe,
            force_scan=strategy == "deep-scan",
        )
        _commit_temp(temp, out, overwrite)
        output_report.path = out
        return RepairResult(out, "reference-reconstruction", output_report)
    finally:
        if temp.exists():
            temp.unlink()
