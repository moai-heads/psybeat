# psybeat

Procedural psychedelic-trance beat generator. Renders a full arrangement
(kick, snare/clap, rolling 16th bass, hats, acid lead, sidechain, master FX)
straight to WAV/MP3 — no samples, no DAW.

## Requirements

- Python 3.10+ with `numpy`, `scipy`, `soundfile`
- `ffmpeg` (on PATH) for MP3 encoding

```bash
pip install numpy scipy soundfile
```

## Usage

```bash
python3 src/psybeat.py                       # 145 BPM, 16 bars -> out/
python3 src/psybeat.py --bpm 148 --bars 32   # custom
python3 src/psybeat.py --no-mp3              # WAV only
```

Output lands in `out/psytrance_kick_snare_<bpm>bpm.{wav,mp3}`.

## Signal chain

| Element   | Synthesis                                                            |
|-----------|----------------------------------------------------------------------|
| Kick      | sine, pitch sweep 105->46 Hz, exp amp decay, tanh saturation, click  |
| Snare     | bandpassed noise (1.3-7.5 kHz) + 185/278 Hz tonal body              |
| Clap      | bandpassed noise, 4-burst decaying envelope                          |
| Hats      | highpassed noise, short (closed) / long (open) decays                |
| Bass      | detuned saw pair + sub sine, resonant LP, tight ~16th envelope       |
| Acid lead | sawtooth through an envelope-swept resonant LP (303-style)           |
| Glue      | kick-keyed sidechain ducking, 3/16 slap delay, tanh master limiter   |

## Layout

```
src/psybeat.py   # the whole generator (CLI entry point)
tools/           # helper scripts
out/             # rendered audio (gitignored)
AGENTS.md        # instructions for agents working in this repo
```
