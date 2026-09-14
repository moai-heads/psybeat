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
python3 src/psybeat.py                       # 145 BPM, 32 bars -> out/
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
| Supersaw  | 7-9 detuned saws, lowpassed - trance lead/pad chords                |
| Pluck     | detuned saw, fast-decay envelope-swept LP - rolling 16th arp          |
| Riser     | band-swept noise + rising tone, ends on a small impact               |
| Impact    | pitch-swept boom + noise burst, drops land on the downbeat           |
| Glue      | kick-keyed sidechain ducking, 3/16 slap delay, tanh master limiter   |

## Structure (32 bars, --bars scales it proportionally)

| Bars   | Section    | Content                                                        |
|--------|------------|----------------------------------------------------------------|
| 0-4    | intro      | kick + rolling bass, sparse snare                            |
| 4-8    | build      | full drums, hats; last bar = accelerating snare roll + riser |
| 8-16   | **DROP 1** | kick, full bass, supersaw chords, acid lead, impact on bar 8 |
| 16-20  | breakdown  | kick/bass drop out - sustained pad + slow acid, uplift        |
| 20-22  | build 2    | snare roll + riser into the second drop                       |
| 22-28  | **DROP 2** | as drop 1 + octave bass lifts + plucky 16th arp, brighter     |
| 28-32  | outro      | strips back down                                                |

Chord progression is a per-bar cycle of Am - F - C - G.

## Layout

```
src/psybeat.py   # the whole generator (CLI entry point)
tools/           # helper scripts
out/             # rendered audio (gitignored)
AGENTS.md        # instructions for agents working in this repo
```
