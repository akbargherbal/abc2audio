#!/usr/bin/env python3
"""abc2audio: convert ABC notation files to audio files.

Pipeline:  .abc --(abcjs, Node)--> .mid --(FluidSynth + SoundFont)--> .wav --(ffmpeg, optional)--> .mp3/.ogg/...

Examples:
    python abc2audio.py tune.abc -o tune.wav
    python abc2audio.py tune.abc -o tune.mp3 --tempo 120 --transpose 2
    python abc2audio.py songs/ --outdir audio/ --format mp3
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JS_SCRIPT = ROOT / "js" / "abc_to_midi.js"

# Formats other than WAV are produced by ffmpeg: extension -> ffmpeg codec arguments.
FFMPEG_ARGS: dict[str, list[str]] = {
    ".mp3": ["-codec:a", "libmp3lame", "-q:a", "2"],
    ".ogg": ["-codec:a", "libvorbis", "-q:a", "5"],
    ".flac": ["-codec:a", "flac"],
    ".m4a": ["-codec:a", "aac", "-b:a", "192k"],
}
SUPPORTED_EXTENSIONS = {".wav", *FFMPEG_ARGS}

SOUNDFONT_ENV = "ABC2AUDIO_SOUNDFONT"
SYSTEM_SOUNDFONTS = [
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/soundfonts/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/soundfonts/default.sf2",
    "/usr/share/sounds/sf2/TimGM6mb.sf2",
    "/opt/homebrew/share/soundfonts/default.sf2",
    "/usr/local/share/soundfonts/default.sf2",
]


class Abc2AudioError(Exception):
    """Any expected, user-facing failure."""


@dataclass
class Options:
    tune: int = 1
    tempo: int | None = None
    transpose: int | None = None
    program: int | None = None
    chord_program: int | None = None
    bass_program: int | None = None
    chords: bool = True
    soundfont: Path | None = None
    sample_rate: int = 44100
    gain: float = 1.0
    keep_midi: bool = False


# --------------------------------------------------------------------------- #
# Dependency checks
# --------------------------------------------------------------------------- #
def require_tool(name: str, hint: str) -> str:
    path = shutil.which(name)
    if not path:
        raise Abc2AudioError(f"'{name}' was not found on PATH. {hint}")
    return path


def check_node_setup() -> str:
    node = require_tool("node", "Install Node.js 18+ (https://nodejs.org).")
    if not (ROOT / "node_modules" / "abcjs").is_dir():
        raise Abc2AudioError(f"abcjs is not installed. Run: cd {ROOT} && npm install")
    return node


def find_soundfont(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise Abc2AudioError(f"SoundFont not found: {explicit}")
        return explicit

    env = os.environ.get(SOUNDFONT_ENV)
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            raise Abc2AudioError(f"${SOUNDFONT_ENV} points to a missing file: {p}")
        return p

    local = sorted((ROOT / "soundfonts").glob("*.sf2")) + sorted((ROOT / "soundfonts").glob("*.sf3"))
    if local:
        return local[0]

    for candidate in SYSTEM_SOUNDFONTS:
        if Path(candidate).is_file():
            return Path(candidate)

    raise Abc2AudioError(
        "No SoundFont found. Pass --soundfont FILE.sf2, set "
        f"${SOUNDFONT_ENV}, put a .sf2 in {ROOT / 'soundfonts'}, "
        "or install one (Debian/Ubuntu: apt install fluid-soundfont-gm)."
    )


# --------------------------------------------------------------------------- #
# Pipeline steps
# --------------------------------------------------------------------------- #
def run(cmd: list[str], what: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise Abc2AudioError(f"{what} failed (exit {proc.returncode}):\n{detail}")
    return proc


def abc_to_midi(abc_path: Path, midi_path: Path, opts: Options) -> dict:
    cmd = [check_node_setup(), str(JS_SCRIPT), str(abc_path), str(midi_path), "--tune", str(opts.tune)]
    for flag, value in (
        ("--qpm", opts.tempo),
        ("--transpose", opts.transpose),
        ("--program", opts.program),
        ("--chord-program", opts.chord_program),
        ("--bass-program", opts.bass_program),
    ):
        if value is not None:
            cmd += [flag, str(value)]
    if not opts.chords:
        cmd.append("--no-chords")

    proc = run(cmd, "ABC -> MIDI conversion")
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"tunes": 1, "warnings": []}


def midi_to_wav(midi_path: Path, wav_path: Path, soundfont: Path, opts: Options) -> None:
    fluidsynth = require_tool("fluidsynth", "Install FluidSynth (Debian/Ubuntu: apt install fluidsynth).")
    cmd = [
        fluidsynth, "-ni", "-q",
        "-g", str(opts.gain),
        "-r", str(opts.sample_rate),
        "-T", "wav", "-F", str(wav_path),
        str(soundfont), str(midi_path),
    ]
    run(cmd, "MIDI -> WAV rendering")
    if not wav_path.is_file() or wav_path.stat().st_size < 1000:
        raise Abc2AudioError("FluidSynth produced no audio (is the MIDI empty?)")


def encode(wav_path: Path, out_path: Path) -> None:
    ffmpeg = require_tool("ffmpeg", "Install ffmpeg to export formats other than WAV.")
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav_path), *FFMPEG_ARGS[out_path.suffix.lower()], str(out_path)]
    run(cmd, f"Encoding to {out_path.suffix}")


def convert(abc_path: Path, out_path: Path, opts: Options) -> dict:
    """Convert one ABC file to an audio file. Returns info about the conversion."""
    ext = out_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise Abc2AudioError(f"Unsupported output format '{ext}'. Use one of: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    soundfont = find_soundfont(opts.soundfont)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="abc2audio_") as tmp:
        tmpdir = Path(tmp)
        midi_path = tmpdir / "tune.mid"
        info = abc_to_midi(abc_path, midi_path, opts)

        if opts.keep_midi:
            shutil.copyfile(midi_path, out_path.with_suffix(".mid"))

        if ext == ".wav":
            midi_to_wav(midi_path, out_path, soundfont, opts)
        else:
            wav_path = tmpdir / "tune.wav"
            midi_to_wav(midi_path, wav_path, soundfont, opts)
            encode(wav_path, out_path)

    info["soundfont"] = str(soundfont)
    return info


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def collect_inputs(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            found = sorted(p.glob("*.abc"))
            if not found:
                print(f"warning: no .abc files in {p}", file=sys.stderr)
            files.extend(found)
        elif p.is_file():
            files.append(p)
        else:
            raise Abc2AudioError(f"Input not found: {p}")
    if not files:
        raise Abc2AudioError("No input files")
    return files


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="abc2audio",
        description="Convert ABC notation files (using abcjs) to WAV/MP3/OGG/FLAC/M4A.",
    )
    p.add_argument("inputs", nargs="+", type=Path, help="ABC file(s) or directories containing .abc files")
    p.add_argument("-o", "--output", type=Path, help="output file (single input only); format is taken from its extension")
    p.add_argument("--outdir", type=Path, help="output directory (default: next to each input)")
    p.add_argument("-f", "--format", default="wav", choices=sorted(e.lstrip(".") for e in SUPPORTED_EXTENSIONS),
                   help="output format when -o is not given (default: wav)")
    p.add_argument("--tune", type=int, default=1, metavar="N", help="1-based position of the tune in files with several tunes (default: 1)")
    p.add_argument("--tempo", type=int, metavar="QPM", help="override the tempo (quarter notes per minute)")
    p.add_argument("--transpose", type=int, metavar="SEMITONES", help="transpose by N semitones")
    p.add_argument("--program", type=int, metavar="0-127", help="default General MIDI instrument for the melody voices")
    p.add_argument("--chord-program", type=int, metavar="0-127", help="General MIDI instrument for the chord accompaniment")
    p.add_argument("--bass-program", type=int, metavar="0-127", help="General MIDI instrument for chord bass notes")
    p.add_argument("--no-chords", action="store_true", help="ignore chord symbols (no accompaniment)")
    p.add_argument("--soundfont", type=Path, metavar="FILE.sf2", help=f"SoundFont to use (or set ${SOUNDFONT_ENV})")
    p.add_argument("--sample-rate", type=int, default=44100, help="sample rate in Hz (default: 44100)")
    p.add_argument("--gain", type=float, default=1.0, help="FluidSynth master gain (default: 1.0)")
    p.add_argument("--keep-midi", action="store_true", help="also save the intermediate .mid next to the output")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        inputs = collect_inputs(args.inputs)
        if args.output and len(inputs) > 1:
            raise Abc2AudioError("-o/--output works with a single input; use --outdir for several files")

        opts = Options(
            tune=args.tune, tempo=args.tempo, transpose=args.transpose,
            program=args.program, chord_program=args.chord_program, bass_program=args.bass_program,
            chords=not args.no_chords, soundfont=args.soundfont,
            sample_rate=args.sample_rate, gain=args.gain, keep_midi=args.keep_midi,
        )
        opts.soundfont = find_soundfont(args.soundfont)  # fail early, before any work
    except Abc2AudioError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    failures = 0
    for abc in inputs:
        if args.output:
            out = args.output
        else:
            out = (args.outdir or abc.parent) / f"{abc.stem}.{args.format}"
        try:
            info = convert(abc, out, opts)
        except Abc2AudioError as e:
            failures += 1
            print(f"error: {abc}: {e}", file=sys.stderr)
            continue

        for w in info.get("warnings", []):
            print(f"warning: {abc.name}: {w}", file=sys.stderr)
        if info.get("tunes", 1) > 1 and args.tune == 1:
            print(f"note: {abc.name} has {info['tunes']} tunes; rendered #1 (use --tune N)", file=sys.stderr)
        print(f"{abc} -> {out}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
