#!/usr/bin/env node
"use strict";
/*
 * abc_to_midi.js: converts an ABC file to a Standard MIDI File using abcjs.
 *
 * Usage:
 *   node abc_to_midi.js <input.abc> <output.mid> [options]
 *
 * Options:
 *   --tune N              1-based position of the tune in the file (default 1)
 *   --qpm N               override tempo (quarter notes per minute)
 *   --transpose N         transpose in semitones
 *   --program N           default GM program (0-127) for voices
 *   --chord-program N     GM program for the chord track
 *   --bass-program N      GM program for the bass notes of chords
 *   --no-chords           do not generate accompaniment from chord symbols
 *
 * On success prints one JSON line to stdout: {"tunes":N,"tune":N,"bytes":N,"warnings":[...]}
 * On failure prints a message to stderr and exits with code 1.
 */

const fs = require("fs");
const abcjs = require("abcjs");

function fail(msg) {
  process.stderr.write(msg + "\n");
  process.exit(1);
}

function parseArgs(argv) {
  const positional = [];
  const opts = { tune: 1, chords: true };
  const intFlags = {
    "--tune": "tune",
    "--qpm": "qpm",
    "--transpose": "transpose",
    "--program": "program",
    "--chord-program": "chordProgram",
    "--bass-program": "bassProgram",
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--no-chords") {
      opts.chords = false;
    } else if (a in intFlags) {
      const v = parseInt(argv[++i], 10);
      if (Number.isNaN(v)) fail(`Option ${a} needs an integer value`);
      opts[intFlags[a]] = v;
    } else if (a.startsWith("--")) {
      fail(`Unknown option: ${a}`);
    } else {
      positional.push(a);
    }
  }
  if (positional.length !== 2) fail("Usage: abc_to_midi.js <input.abc> <output.mid> [options]");
  return { input: positional[0], output: positional[1], opts };
}

const stripTags = (s) => String(s).replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();

function main() {
  const { input, output, opts } = parseArgs(process.argv.slice(2));

  let abc;
  try {
    abc = fs.readFileSync(input, "utf8");
  } catch (e) {
    fail(`Cannot read ${input}: ${e.message}`);
  }

  const tunes = abcjs.parseOnly(abc);
  if (!tunes || tunes.length === 0) fail("No tune found in the ABC file");
  if (opts.tune < 1 || opts.tune > tunes.length) {
    fail(`--tune ${opts.tune} is out of range: the file contains ${tunes.length} tune(s)`);
  }

  const tune = tunes[opts.tune - 1];
  if (!tune.lines || tune.lines.length === 0) fail("The selected tune has no music lines");

  const params = { midiOutputType: "binary" };
  if (opts.qpm !== undefined) params.qpm = opts.qpm;
  if (opts.transpose !== undefined) params.midiTranspose = opts.transpose;
  if (opts.program !== undefined) params.program = opts.program;
  if (opts.chordProgram !== undefined) params.chordprog = opts.chordProgram;
  if (opts.bassProgram !== undefined) params.bassprog = opts.bassProgram;
  if (!opts.chords) params.chordsOff = true;

  let midi = abcjs.synth.getMidiFile(tune, params);
  if (Array.isArray(midi)) midi = midi[0];
  if (!midi || midi.length < 14) fail("abcjs did not produce MIDI data");

  fs.writeFileSync(output, Buffer.from(midi));

  const warnings = (tune.warnings || []).map(stripTags);
  process.stdout.write(
    JSON.stringify({ tunes: tunes.length, tune: opts.tune, bytes: midi.length, warnings }) + "\n"
  );
}

main();
