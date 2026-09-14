"""psybeat - procedural psychedelic-trance beat generator.

Renders a full arrangement (kick, snare/clap, rolling 16th bass, hats, acid
lead, sidechain ducking, master FX) to WAV and optionally MP3. Pure DSP,
no samples. See README.md and AGENTS.md.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

import numpy as np
from scipy.signal import sawtooth, butter, sosfilt, iirfilter
import soundfile as sf

SR = 44100


def render(bpm: float = 145.0, bars: int = 16, seed: int = 7) -> np.ndarray:
    """Render the track and return a float32 stereo-ready mono buffer."""
    BPM = bpm
    BEAT = 60.0 / BPM
    STEP = BEAT / 4          # 16th note
    BAR = BEAT * 4
    BARS = bars
    N = int(BARS * BAR * SR)
    rng = np.random.default_rng(seed)

    def env_ad(n, a, d, curve=3.0):
        t = np.arange(n)/SR
        atk = np.clip(t/max(a,1e-6),0,1)
        dec = np.exp(-t/d)
        return atk*dec

    # ---------- drums ----------
    def kick():
        n = int(0.45*SR); t = np.arange(n)/SR
        f = 46 + 105*np.exp(-t/0.018)          # pitch sweep
        ph = 2*np.pi*np.cumsum(f)/SR
        body = np.sin(ph)*np.exp(-t/0.085)
        click = rng.normal(0,1,n)*np.exp(-t/0.0012)*0.35
        # gentle saturation for punch
        s = np.tanh((body+click)*1.6)
        s *= (1-np.exp(-t/0.0008))
        return s*0.95

    def snare():
        n = int(0.35*SR); t = np.arange(n)/SR
        nz = rng.normal(0,1,n)
        sos = butter(2, [1300/(SR/2), 7500/(SR/2)], btype='band', output='sos')
        nz = sosfilt(sos, nz)
        noise = nz*np.exp(-t/0.075)
        tone  = (np.sin(2*np.pi*185*t)+0.6*np.sin(2*np.pi*278*t))*np.exp(-t/0.045)
        return (noise*0.7 + tone*0.5)*0.85

    def clap():
        n = int(0.3*SR); t = np.arange(n)/SR
        nz = sosfilt(butter(2,[900/(SR/2),6000/(SR/2)],btype='band',output='sos'), rng.normal(0,1,n))
        e = np.zeros(n)
        for off,g in [(0,1.0),(0.008,0.8),(0.016,0.65),(0.026,0.45)]:
            i = int(off*SR)
            e[i:] += g*np.exp(-(np.arange(n-i))/SR/0.035)
        return nz*e*0.5

    def hat(open_=False):
        n = int((0.22 if open_ else 0.07)*SR); t = np.arange(n)/SR
        nz = sosfilt(butter(3, 6500/(SR/2), btype='high', output='sos'), rng.normal(0,1,n))
        return nz*np.exp(-t/(0.075 if open_ else 0.012))*0.28

    # ---------- psy bass ----------
    def bass_note(f, n):
        t = np.arange(n)/SR
        osc = (sawtooth(2*np.pi*f*t) + 0.85*sawtooth(2*np.pi*f*1.004*t+0.4)
               + 0.5*np.sin(2*np.pi*f*0.5*t))
        e = env_ad(n, 0.0015, 0.055, 4.0)
        e *= np.clip(1.0 - t/(n/SR*0.98), 0, 1)**0.7
        x = osc*e
        sos = iirfilter(2, 780/(SR/2), btype='low', ftype='butter', output='sos')  # resonant LP
        return sosfilt(sos, x)*0.9

    # ---------- acid lead ----------
    ACID_SEMIS = [0,0,12,0, 3,0,7,12, 0,10,0,7, 3,12,0,15]   # A minor-ish
    def acid_note(f, n, bright):
        t = np.arange(n)/SR
        osc = sawtooth(2*np.pi*f*t)
        e = env_ad(n, 0.002, 0.085, 3)
        x = osc*e
        fc = 320 + 1500*np.exp(-t/0.10)*bright
        out = np.zeros(n)
        blk = 128
        for i in range(0, n, blk):
            j = min(i+blk, n)
            sos = iirfilter(2, min(fc[i]/(SR/2),0.98), btype='low', ftype='butter', output='sos')
            out[i:j] = sosfilt(sos, x[i:j])
        return out*0.5

    # ---------- supersaw / trance lead ----------
    def supersaw_note(f, n, voices=7, detune=0.012, cutoff=4200.0):
        t = np.arange(n)/SR
        out = np.zeros(n)
        spread = np.linspace(-detune, detune, voices)
        for i, d in enumerate(spread):
            out += sawtooth(2*np.pi*f*(1+d)*t + i*0.7)
        out /= voices
        e = env_ad(n, 0.006, 0.5, 2.0)
        e *= np.clip(1.0 - t/(n/SR*1.6), 0, 1)
        sos = iirfilter(2, min(cutoff/(SR/2), 0.98), btype='low', ftype='butter', output='sos')
        return sosfilt(sos, out*e)*0.55

    def pluck_note(f, n):
        """Short detuned pluck (rolling trance arp voice)."""
        t = np.arange(n)/SR
        osc = (sawtooth(2*np.pi*f*t) + 0.6*sawtooth(2*np.pi*f*1.01*t))
        e = env_ad(n, 0.001, 0.035, 4.0)
        x = osc*e
        fc = 900 + 6000*np.exp(-t/0.03)
        out = np.zeros(n)
        blk = 128
        for i in range(0, n, blk):
            j = min(i+blk, n)
            sos = iirfilter(2, min(fc[i]/(SR/2), 0.98), btype='low', ftype='butter', output='sos')
            out[i:j] = sosfilt(sos, x[i:j])
        return out*0.4

    # ---------- transition FX ----------
    def riser(n, f0=200.0, f1=6000.0, shape=2.0):
        """Uplifting noise + swept-tone riser ending on a small impact."""
        t = np.arange(n)/SR
        frac = t/max(t[-1], 1e-6)
        nz = rng.normal(0, 1, n)
        # resonant sweep on noise
        fc = f0 + (f1-f0)*frac**shape
        out = np.zeros(n)
        blk = 256
        for i in range(0, n, blk):
            j = min(i+blk, n)
            sos = iirfilter(2, [max(fc[i]/(SR/2)*0.5, 0.002), min(fc[i]/(SR/2), 0.98)],
                            btype='band', ftype='butter', output='sos')
            out[i:j] = sosfilt(sos, nz[i:j])
        # rising tone underneath
        fsw = f0*2 + (f1*0.25 - f0*2)*frac**2
        tone = np.sin(2*np.pi*np.cumsum(fsw)/SR)
        amp = frac**1.4
        return (out*0.5 + tone*0.25)*amp

    def impact(dur=1.2, g=1.0):
        n = int(dur*SR); t = np.arange(n)/SR
        boom = np.sin(2*np.pi*(60*np.exp(-t/0.12)+34)*t)*np.exp(-t/0.35)
        nz = sosfilt(butter(2, [200/(SR/2), 9000/(SR/2)], btype='band', output='sos'),
                     rng.normal(0, 1, n))*np.exp(-t/0.25)
        return (boom*0.8 + nz*0.4)*g

    def uplift(dur=0.8, g=1.0):
        """Reverse-style whoosh into a downbeat."""
        n = int(dur*SR); t = np.arange(n)/SR
        nz = sosfilt(butter(2, [300/(SR/2), 7000/(SR/2)], btype='band', output='sos'),
                     rng.normal(0, 1, n))
        return nz*(t/dur)**2*g

    # ---------- arrangement ----------
    # Section map as fractions of total length, so it scales with --bars.
    # 32 bars @ 145 BPM ->
    #   0-4 intro | 4-8 build | 8-16 DROP 1 | 16-20 breakdown
    #   20-22 build2 | 22-28 DROP 2 | 28-32 outro
    SECTIONS = [
        ("intro",     0.1250),
        ("build",     0.1250),
        ("drop1",     0.2500),
        ("breakdown", 0.1250),
        ("build2",    0.0625),
        ("drop2",     0.1875),
        ("outro",     0.1250),
    ]
    bounds, acc = {}, 0.0
    for name, frac in SECTIONS:
        b0 = int(round(acc*BARS)); acc += frac
        b1 = int(round(acc*BARS))
        for b in range(b0, b1):
            bounds[b] = name
    last_bar = BARS - 1

    mix = np.zeros(N + 2*SR)
    K, S, C, H, HO = kick(), snare(), clap(), hat(), hat(True)

    def place(buf, sig, tsec, gain=1.0):
        i = int(tsec*SR)
        j = min(i+len(sig), len(buf))
        if j > i:
            buf[i:j] += sig[:j-i]*gain

    # chord roots (semitones from A) cycled per bar: Am - F - C - G
    CHORD = [0, -4, 3, -2]
    TRIAD = [0, 3, 7]
    A2 = 110.0

    def chord_freqs(root_semi, octave=0):
        base = A2*2**(root_semi/12)*2**octave
        return [base*2**(s/12) for s in TRIAD]

    for bar in range(BARS):
        t0 = bar*BAR
        sec = bounds.get(bar, "outro")
        in_drop = sec in ("drop1", "drop2")
        is_drop2 = sec == "drop2"
        chord = CHORD[bar % len(CHORD)]

        drums = sec not in ("breakdown",)
        full_drums = in_drop or sec == "outro" or sec == "build"
        bass_on = sec not in ("breakdown",)

        # ---- kick (four on the floor) ----
        if drums:
            for b in range(4):
                place(mix, K, t0+b*BEAT, 1.0)

        # ---- snare/clap backbeat ----
        if full_drums:
            for b in (1, 3):
                place(mix, S, t0+b*BEAT, 0.9)
                place(mix, C, t0+b*BEAT, 0.55)
        elif sec == "intro" and bar >= 1:
            place(mix, S, t0+3*BEAT, 0.6)

        # ---- rolling 16th bassline ----
        if bass_on:
            bass_gain = 0.95 if not in_drop else 1.05
            for s in range(16):
                f = A2*2**(chord/12)*0.5          # A1-ish root
                if is_drop2 and s in (7, 15):
                    f *= 2                          # octave lift in drop 2
                elif in_drop and s in (15,):
                    f *= 2
                place(mix, bass_note(f, int(STEP*SR*0.99)), t0+s*STEP, bass_gain)

        # ---- hats ----
        if full_drums and sec != "intro":
            for b in range(4):
                place(mix, H,  t0+b*BEAT, 0.9)
                place(mix, H,  t0+b*BEAT+STEP*2, 0.8)
                place(mix, H,  t0+b*BEAT+STEP*2+STEP, 0.5)
            place(mix, HO, t0+3*BEAT+STEP*3, 0.8)
        elif in_drop and bar % 2 == 0:
            for b in range(4):
                place(mix, H, t0+b*BEAT+STEP*2, 0.7)

        # ---- DROP leads: supersaw chord + acid + arp pluck ----
        if in_drop:
            lead_gain = 0.42 if is_drop2 else 0.34
            # supersaw pads chording on the beat
            for b, ct in ((0, chord_freqs(chord)), (2, chord_freqs(chord, 1))):
                for f in ct:
                    place(mix, supersaw_note(f, int(BEAT*0.9*SR),
                                             voices=7, detune=0.010,
                                             cutoff=5200 if is_drop2 else 4200),
                          t0+b*BEAT, lead_gain)
            # acid 16th lead
            for s in range(16):
                if s % 2 == 1 and (bar+s) % 4 != 0:
                    continue
                f = A2*2**(chord/12)*2**(ACID_SEMIS[s]/12)
                place(mix, acid_note(f, int(STEP*1.6*SR), 1.0 if is_drop2 else 0.7),
                      t0+s*STEP, 0.45)
            # plucky 16th arp (drop 2 only) - octave-jumping chord tones
            if is_drop2:
                for s in range(16):
                    f = A2*2**(chord/12)*2**(TRIAD[s % 3]/12)*2**(1 if s % 4 >= 2 else 0)
                    place(mix, pluck_note(f, int(STEP*1.2*SR)), t0+s*STEP, 0.5)

        # ---- breakdown: atmospheric leads, no kick/bass ----
        if sec == "breakdown":
            # sustained supersaw chord across the section
            for f in chord_freqs(chord):
                place(mix, supersaw_note(f, int(BAR*SR*0.95), voices=9, detune=0.014,
                                         cutoff=2600), t0, 0.40)
            # slow acid motif on the offbeats
            for s in (2, 6, 10, 14):
                f = A2*2**(chord/12)*2**(ACID_SEMIS[s]/12)
                place(mix, acid_note(f, int(STEP*2.0*SR), 0.5), t0+s*STEP, 0.4)
            place(mix, uplift(0.7, 0.5), t0+BAR-0.7, 1.0)

        # ---- build risers: last bar of build/build2 accelerates snares + riser ----
        if sec in ("build", "build2") and bar == max(b for b in bounds if bounds[b] == sec):
            for i in range(16):
                g = 0.35 + 0.55*(i/15)
                place(mix, S, t0+i*STEP, g)
            place(mix, riser(int(BAR*SR), f0=250, f1=7000, shape=2.2), t0, 0.9)
            place(mix, uplift(BEAT*0.9, 0.8), t0+BAR-BEAT*0.9, 1.0)

        # ---- impacts landing on each drop's downbeat ----
        if in_drop and (bar == min(b for b in bounds if bounds[b] == sec)):
            place(mix, impact(1.4, 1.0), t0, 0.9)

        # ---- intro filter sweep feel: thin out first bars via gains already applied ----

    # ---------- sidechain duck (kick ducks the bass/lead) ----------
    duck = np.ones(len(mix))
    td = np.arange(int(0.09*SR))/SR
    dshape = 0.12 + 0.88*(1-np.exp(-td/0.006))*np.exp(-td/0.035)
    for bar in range(BARS):
        for b in range(4):
            i = int((bar*BAR+b*BEAT)*SR)
            j = min(i+len(td), len(mix))
            duck[i:j] = np.minimum(duck[i:j], dshape[:j-i])
    # apply duck mainly to bass/lead region (below 200Hz energy) - simple broadband is fine
    mix *= duck**0.55

    # ---------- fx: short slap delay on top end ----------
    d = int((BEAT*3/4)*SR)
    tail = mix.copy()
    tail[d:] += mix[:-d]*0.18
    mix = tail

    # ---------- master ----------
    mix /= np.max(np.abs(mix))
    mix = np.tanh(mix*1.35)*0.9
    mix /= np.max(np.abs(mix))
    mix *= 0.97
    fade = int(0.02*SR)
    mix[:fade] *= np.linspace(0,1,fade)
    mix[-int(0.6*SR):] *= np.linspace(1,0,int(0.6*SR))


    # trim trailing silence left by the placement padding
    nz = np.where(np.abs(mix) > 1e-4)[0]
    if len(nz):
        mix = mix[:min(len(mix), nz[-1] + int(0.3*SR))]

    return mix.astype("float32")


def encode_mp3(wav_path: str, mp3_path: str, bitrate: str = "192k") -> bool:
    """Encode WAV -> MP3 with ffmpeg. Returns True on success."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
             "-codec:a", "libmp3lame", "-b:a", bitrate, mp3_path],
            check=True,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render a psytrance beat.")
    ap.add_argument("--bpm", type=float, default=145.0, help="tempo (default 145)")
    ap.add_argument("--bars", type=int, default=32, help="length in bars (default 32)")
    ap.add_argument("--seed", type=int, default=7, help="RNG seed (default 7)")
    ap.add_argument("--outdir", default="out", help="output directory (default out/)")
    ap.add_argument("--no-mp3", action="store_true", help="skip MP3 encoding")
    args = ap.parse_args(argv)

    os.makedirs(args.outdir, exist_ok=True)
    mix = render(bpm=args.bpm, bars=args.bars, seed=args.seed)

    stem = f"psytrance_kick_snare_{int(round(args.bpm))}bpm"
    wav_path = os.path.join(args.outdir, stem + ".wav")
    sf.write(wav_path, mix, SR)

    dur = len(mix) / SR
    peak = float(np.max(np.abs(mix)))
    print(f"bars={args.bars} dur={dur:.2f}s peak={peak:.3f}")
    print(f"wrote {wav_path}")

    if not args.no_mp3:
        mp3_path = os.path.join(args.outdir, stem + ".mp3")
        if encode_mp3(wav_path, mp3_path):
            print(f"wrote {mp3_path}")
        else:
            print("warning: ffmpeg unavailable, skipped MP3", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
