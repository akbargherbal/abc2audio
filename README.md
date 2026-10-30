# abc2audio

Convert [ABC notation](https://abcnotation.com) files into audio files from the command line, with no browser and no server.

```
.abc ──(abcjs, Node)──▶ .mid ──(FluidSynth + SoundFont)──▶ .wav ──(ffmpeg)──▶ .mp3 / .ogg / .flac / .m4a
```

[abcjs](https://github.com/paulrosen/abcjs) parses the ABC and generates the MIDI (so repeats, voices, chords, key and meter changes are interpreted exactly as abcjs does). FluidSynth renders the MIDI to audio using a SoundFont.

## Requirements

| Tool | Purpose | Install (Debian/Ubuntu) |
|------|---------|-------------------------|
| Python 3.9+ | CLI (standard library only) | already installed |
| Node.js 18+ | runs abcjs | `apt install nodejs npm` |
| FluidSynth | MIDI → WAV | `apt install fluidsynth` |
| A SoundFont (`.sf2`) | instrument sounds | `apt install fluid-soundfont-gm` |
| ffmpeg *(optional)* | MP3/OGG/FLAC/M4A output | `apt install ffmpeg` |

On macOS: `brew install node fluid-synth ffmpeg`.

## Setup

```bash
cd abc2audio
npm install
```

## Usage

```bash
# Single file (format is taken from the output extension)
python abc2audio.py tune.abc -o tune.wav
python abc2audio.py tune.abc -o tune.mp3

# Whole folder
python abc2audio.py songs/ --outdir audio/ --format mp3

# Tweak the result
python abc2audio.py tune.abc -o tune.mp3 --tempo 120 --transpose 2 --gain 1.5
python abc2audio.py tune.abc -o tune.wav --program 73 --no-chords   # flute, no accompaniment

# File with several tunes (X:1, X:2, ...): pick the 2nd one
python abc2audio.py book.abc -o second.wav --tune 2
```

### Options

| Option | Description |
|--------|-------------|
| `-o, --output FILE` | Output file (single input only). Format from extension: `.wav .mp3 .ogg .flac .m4a` |
| `--outdir DIR` | Output directory when converting several files (default: next to each input) |
| `-f, --format EXT` | Output format when `-o` is not given (default `wav`) |
| `--tune N` | 1-based position of the tune in a multi-tune file (default `1`) |
| `--tempo QPM` | Override the tempo (quarter notes per minute) |
| `--transpose N` | Transpose by N semitones |
| `--program 0-127` | General MIDI instrument for the melody voices |
| `--chord-program 0-127` | Instrument for the chord accompaniment |
| `--bass-program 0-127` | Instrument for chord bass notes |
| `--no-chords` | Ignore chord symbols (`"Cm7"`, …) so no accompaniment is generated |
| `--soundfont FILE.sf2` | SoundFont to use |
| `--sample-rate HZ` | Sample rate (default `44100`) |
| `--gain G` | FluidSynth master gain (default `1.0`; raise it if the output is quiet) |
| `--keep-midi` | Also save the intermediate `.mid` next to the output |

### SoundFont lookup order

1. `--soundfont FILE`
2. `$ABC2AUDIO_SOUNDFONT`
3. First `.sf2`/`.sf3` in `./soundfonts/`
4. Common system locations (e.g. `/usr/share/sounds/sf2/FluidR3_GM.sf2`)

The SoundFont decides how the instruments sound. Good free General MIDI options: *GeneralUser GS* and *FluidR3 GM*.

### Exit codes

`0` success · `1` at least one file failed · `2` bad arguments or missing dependency/input.

## Notes

- **Chord symbols produce accompaniment.** abcjs generates a chord track from annotations like `"Cm7"`. Use `--no-chords` for melody only.
- **Instruments:** unless the ABC sets `%%MIDI program`, all voices use piano (program 0). Use `--program` or add `%%MIDI program N` per voice in the ABC.
- **Sound differs slightly from the browser.** abcjs in the browser uses its own SoundFont samples; here the sound comes from the SoundFont you choose. Notes and timing are identical because both start from the same abcjs MIDI.

## Project layout

```
abc2audio/
├── abc2audio.py          # CLI (argparse, orchestration)
├── js/abc_to_midi.js     # abcjs → MIDI
├── soundfonts/           # optional: drop your .sf2 here
├── tests/                # sample ABC files + unittest suite
├── package.json
└── README.md
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Troubleshooting

| Message | Fix |
|---------|-----|
| `abcjs is not installed` | Run `npm install` in the project folder |
| `'fluidsynth' was not found on PATH` | Install FluidSynth |
| `No SoundFont found` | Pass `--soundfont`, or install `fluid-soundfont-gm` |
| `'ffmpeg' was not found` | Install ffmpeg, or output `.wav` |
| `The selected tune has no music lines` | The ABC file is empty or has no notes |
