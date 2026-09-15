# psybeat

Procedural **psytrance** generator. Renders a full arrangement (psy kick,
rolling gallop bass, sparse percussion, offbeat hats, acid/FM squelch leads,
dub delay + reverb, sidechain) straight to WAV/MP3 — no samples, no DAW.

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

Output lands in `out/psytrance_<bpm>bpm.{wav,mp3}`.

## What makes it psy (and not eurodance)

- **Kick drives a rolling bass gallop** — kick owns every beat, the bass hits
  on the three 16ths after each kick (3 notes/beat). No offbeat-bass eurodance.
- **No backbeat snare** — psy has no snare/clap on 2 and 4. Only sparse
  syncopated percussion and snare rolls into drops.
- **Root-locked hypnotic bass** (A A A G) — movement comes from the acid lead,
  not from trance chord pads.
- **Acid/FM squelch lead** with resonant filter sweeps and tanh drive, plus a
  sustained detuned trance melody (motif changes every 4 bars) into a dub
  delay — no supersaw chord stabs, no plucky stabs.
- **No trance breakdown** — the break strips kick/bass and builds with an
  acid motif, sweep and riser.

## Signal chain

| Element    | Synthesis                                                          |
|------------|--------------------------------------------------------------------|
| Kick       | sine, fast pitch sweep 244->49 Hz, short punchy decay, 2nd-harmonic punch |
| Snare      | bandpassed noise + tonal body (used for rolls/accents only)       |
| Perc       | rim/tom tone + bandpassed noise, sparse syncopated accents        |
| Hats       | highpassed noise, short (closed) / long (open) decays             |
| Bass       | sine + saw grit, slight pitch fall, short envelope, resonant LP   |
| Acid lead  | saw through a Q-swept resonant LP with tanh distortion (303-style)|
| FM squelch | FM blip, sparse softer accents (bar-ends)                         |
| Trance lead| sustained detuned saw, per-phrase motif, opens into the delay      |
| Lead FX    | dotted-eighth feedback delay + parallel-comb reverb               |
| Riser      | band-swept noise + rising tone, ends on a small impact            |
| Impact     | pitch-swept boom + noise burst, drops land on the downbeat        |
| Glue       | kick-keyed sidechain ducking, tanh master limiter                 |

## Structure (32 bars, --bars scales it proportionally)

| Bars   | Section    | Content                                                        |
|--------|------------|----------------------------------------------------------------|
| 0-4    | intro      | kick + rolling bass, sparse percussion                        |
| 4-8    | build      | full drums, hats; last bar = accelerating snare roll + riser  |
| 8-16   | **DROP 1** | full gallop bass, acid lead, FM accents, psy lead, impact     |
| 16-20  | breakdown  | kick/bass out - acid motif on the FX bus, uplift               |
| 20-22  | build 2    | snare roll + riser into the second drop                        |
| 22-28  | **DROP 2** | bigger: octave bass lifts, FM accents every bar, brighter      |
| 28-32  | outro      | strips back down                                                |

## Layout

```
src/psybeat.py   # the whole generator (CLI entry point)
tools/           # helper scripts
out/             # rendered audio (gitignored)
AGENTS.md        # instructions for agents working in this repo
```
