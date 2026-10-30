"""Smoke tests. Run with:  python -m unittest discover -s tests -v"""

import array
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import abc2audio  # noqa: E402

SAMPLES = sorted((ROOT / "tests" / "samples").glob("*.abc"))


def wav_stats(path: Path) -> tuple[float, int]:
    """Return (duration in seconds, peak amplitude) for a 16-bit WAV file."""
    with wave.open(str(path), "rb") as w:
        assert w.getsampwidth() == 2
        frames = w.readframes(w.getnframes())
        duration = w.getnframes() / w.getframerate()
    samples = array.array("h")
    samples.frombytes(frames)
    return duration, max(abs(s) for s in samples)


class ConvertTests(unittest.TestCase):
    def test_samples_exist(self):
        self.assertGreaterEqual(len(SAMPLES), 1)

    def test_each_sample_renders_audible_wav(self):
        for abc in SAMPLES:
            with self.subTest(abc=abc.name), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "out.wav"
                self.assertEqual(abc2audio.main([str(abc), "-o", str(out)]), 0)
                duration, peak = wav_stats(out)
                self.assertGreater(duration, 30)
                self.assertGreater(peak, 1000)  # not silence

    def test_tempo_override_changes_duration(self):
        abc = SAMPLES[0]
        with tempfile.TemporaryDirectory() as tmp:
            slow, fast = Path(tmp) / "slow.wav", Path(tmp) / "fast.wav"
            abc2audio.main([str(abc), "-o", str(slow), "--tempo", "60"])
            abc2audio.main([str(abc), "-o", str(fast), "--tempo", "120"])
            self.assertGreater(wav_stats(slow)[0], wav_stats(fast)[0] * 1.8)

    def test_mp3_and_keep_midi(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.mp3"
            self.assertEqual(abc2audio.main([str(SAMPLES[0]), "-o", str(out), "--keep-midi"]), 0)
            self.assertGreater(out.stat().st_size, 10_000)
            self.assertEqual(out.with_suffix(".mid").read_bytes()[:4], b"MThd")

    def test_batch_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(abc2audio.main([str(SAMPLES[0].parent), "--outdir", tmp]), 0)
            self.assertEqual(len(list(Path(tmp).glob("*.wav"))), len(SAMPLES))


class ErrorTests(unittest.TestCase):
    def test_missing_input(self):
        self.assertEqual(abc2audio.main(["does_not_exist.abc"]), 2)

    def test_unsupported_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(abc2audio.main([str(SAMPLES[0]), "-o", str(Path(tmp) / "x.xyz")]), 1)

    def test_tune_out_of_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(abc2audio.main([str(SAMPLES[0]), "-o", str(Path(tmp) / "x.wav"), "--tune", "9"]), 1)

    def test_empty_abc(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "empty.abc"
            bad.write_text("")
            self.assertEqual(abc2audio.main([str(bad), "-o", str(Path(tmp) / "x.wav")]), 1)


if __name__ == "__main__":
    unittest.main()
