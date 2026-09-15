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
from scipy.signal import sawtooth, butter, sosfilt, iirfilter, lfilter
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

    def rbj_lp(fc, q):
        """Resonant (RBJ biquad) lowpass, returned as a one-section sos."""
        w0 = 2*np.pi*np.clip(fc, 20.0, SR*0.49)/SR
        alpha = np.sin(w0)/(2*q)
        b0 = (1-np.cos(w0))/2; b1 = 1-np.cos(w0); b2 = b0
        a0 = 1+alpha; a1 = -2*np.cos(w0); a2 = 1-alpha
        return np.array([[b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0]])

    # ---------- drums ----------
    def kick():
        # Psy kick: fast vertical pitch drop, short punchy decay, tight sub tail.
        n = int(0.28*SR); t = np.arange(n)/SR
        f = 49 + 195*np.exp(-t/0.0085)          # fast pitch sweep
        ph = 2*np.pi*np.cumsum(f)/SR
        body = np.sin(ph)*np.exp(-t/0.062)
        body += 0.30*np.sin(2*ph)*np.exp(-t/0.030)   # 2nd-harmonic punch
        click = rng.normal(0,1,n)*np.exp(-t/0.0009)*0.45
        s = np.tanh((body+click)*1.8)
        s *= (1-np.exp(-t/0.0006))
        return s*0.98

    def snare():
        n = int(0.35*SR); t = np.arange(n)/SR
        nz = rng.normal(0,1,n)
        sos = butter(2, [1300/(SR/2), 7500/(SR/2)], btype='band', output='sos')
        nz = sosfilt(sos, nz)
        noise = nz*np.exp(-t/0.075)
        tone  = (np.sin(2*np.pi*185*t)+0.6*np.sin(2*np.pi*278*t))*np.exp(-t/0.045)
        return (noise*0.7 + tone*0.5)*0.85

    def hat(open_=False):
        n = int((0.22 if open_ else 0.07)*SR); t = np.arange(n)/SR
        nz = sosfilt(butter(3, 6500/(SR/2), btype='high', output='sos'), rng.normal(0,1,n))
        return nz*np.exp(-t/(0.075 if open_ else 0.012))*0.28

    def perc():
        # Sparse rim/tom percussion for syncopated psy accents (no backbeat).
        n = int(0.12*SR); t = np.arange(n)/SR
        tone = (np.sin(2*np.pi*320*t) + 0.6*np.sin(2*np.pi*470*t))*np.exp(-t/0.020)
        nz = sosfilt(butter(2,[1800/(SR/2),8000/(SR/2)],btype='band',output='sos'),
                     rng.normal(0,1,n))*np.exp(-t/0.008)
        return (tone*0.5 + nz*0.5)*0.6

    # ---------- psy bass ----------
    def bass_note(f, n, res=1.1):
        # Psy rolling bass: sine fundamental + a touch of saw grit, fast pitch
        # fall on attack, short punchy envelope so 16ths never smear together.
        t = np.arange(n)/SR
        fenv = f*(1 + 0.05*np.exp(-t/0.010))          # slight downward pitch blip
        ph = 2*np.pi*np.cumsum(fenv)/SR
        osc = (np.sin(ph) + 0.35*np.sin(2*ph)
               + 0.22*sawtooth(2*np.pi*f*t))
        e = env_ad(n, 0.0009, 0.038, 5.0)
        e *= np.clip(1.0 - t/(n/SR*0.98), 0, 1)**0.6
        x = osc*e
        out = sosfilt(rbj_lp(840, 1.0 + res), x)  # resonant LP grit
        return out*0.95

    # ---------- acid lead ----------
    # Acid semitone patterns rotated per 4-bar phrase so the line evolves.
    ACID_PATTERNS = [
        [0,0,12,0, 3,0,7,12, 0,10,0,7, 3,12,0,15],
        [0,12,0,3, 0,7,0,10, 12,0,15,0, 12,7,3,0],
        [0,0,3,0, 7,0,10,12, 0,3,0,7, 12,0,10,0],
    ]
    ACID_SEMIS = ACID_PATTERNS[0]
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

    # ---------- psytrance lead voices ----------
    def fm_squelch(f, n, index=5.0):
        """Metallic FM squelch blip for psy accents."""
        t = np.arange(n)/SR
        mod = np.sin(2*np.pi*f*3.0*t)*np.exp(-t/0.03)
        ph = 2*np.pi*f*t + index*mod
        e = np.exp(-t/0.045)
        return np.sin(ph)*e*0.4

    def trance_lead_note(f, n, bend=0.0, bright=1.0, voices=3, detune=0.006):
        """Sustained detuned trance lead: sings into the delay instead of
        stabbing. Gentle attack + sustain/release, soft resonant filter open."""
        t = np.arange(n)/SR
        frac = np.clip(t/max(t[-1], 1e-6), 0, 1)
        fenv = f*2**(bend*frac)
        out = np.zeros(n)
        spread = np.linspace(-detune, detune, voices)
        for i, d in enumerate(spread):
            ph = 2*np.pi*np.cumsum(fenv*(1+d))/SR
            out += sawtooth(ph + i*0.5)
        out /= voices
        # sustain envelope: short attack, long release (no plucky decay)
        a = max(int(0.012*SR), 1); r = max(int(0.06*SR), 1)
        e = np.ones(n)
        e[:a] = np.linspace(0, 1, a)
        if n > r:
            e[-r:] *= np.linspace(1, 0, r)
        x = out*e
        fc = 600 + 3200*np.exp(-t/0.25)*bright
        y = np.zeros(n)
        for i in range(0, n, 128):
            j = min(i+128, n)
            y[i:j] = sosfilt(rbj_lp(fc[i], 3.2), x[i:j])
        return np.tanh(y*1.5)*0.4

    # Lead motifs, indexed per 4-bar phrase (step, semitone, length in steps).
    # Different contour each phrase so the hook evolves instead of repeating.
    LEAD_MOTIFS = [
        [(0, 0, 4), (4, 3, 2), (6, 7, 2), (8, 10, 4), (12, 7, 4)],
        [(0, 12, 2), (2, 10, 2), (4, 7, 4), (8, 3, 2), (10, 0, 2), (12, -2, 4)],
        [(0, 0, 2), (2, 7, 2), (4, 10, 2), (6, 12, 2), (8, 10, 2), (10, 7, 2), (12, 3, 4)],
        [(0, 3, 4), (4, 7, 4), (8, 10, 2), (10, 12, 2), (12, 15, 4)],
    ]

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

    def dub_delay(x, time, fb=0.45, mix=0.4):
        """Feedback echo (dotted-eighth style) for the lead bus."""
        d = int(time*SR)
        y = x.copy()
        acc = x.copy()
        for k in range(1, 6):
            shift = k*d
            if shift >= len(x):
                break
            acc[shift:] += x[:len(x)-shift]*(fb**k)
        return x + mix*acc

    def reverb(x, mix=0.22):
        """Cheap feedback-comb reverb (parallel combs via lfilter)."""
        out = np.zeros_like(x)
        for tcomb, g in [(0.0297, 0.78), (0.0371, 0.74), (0.0411, 0.71), (0.0437, 0.68)]:
            d = int(tcomb*SR)
            a = np.zeros(d+1); a[0] = 1.0; a[d] = -g
            out += lfilter([1.0], a, x)
        out /= 4.0
        return x*(1-mix) + out*mix

    def process_lead(x):
        """Dub delay + reverb glue for the psy lead bus."""
        d = int((BEAT*3/4)*SR)          # dotted eighth
        y = dub_delay(x, BEAT*3/4, fb=0.42, mix=0.38)
        y = reverb(y, mix=0.25)
        return y*0.9


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
    lead = np.zeros(N + 2*SR)   # lead bus -> delay/reverb FX
    K, S, P, H, HO = kick(), snare(), perc(), hat(), hat(True)

    def place(buf, sig, tsec, gain=1.0):
        i = int(tsec*SR)
        j = min(i+len(sig), len(buf))
        if j > i:
            buf[i:j] += sig[:j-i]*gain

    # Hypnotic mostly-root bassline: A A A G (semitones from A).
    # Psy basses lock to the root; movement comes from the acid lead, not chords.
    CHORD = [0, 0, 0, -2]
    A2 = 110.0

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

        # ---- sparse syncopated percussion (psy has NO backbeat snare) ----
        if in_drop and bar % 2 == 1:
            place(mix, P, t0+1*BEAT+STEP*3, 0.7)
            place(mix, P, t0+3*BEAT+STEP*1, 0.6)
        elif sec == "intro" and bar >= 2:
            place(mix, P, t0+2*BEAT, 0.5)

        # ---- rolling psy bassline: kick on the beat, 3 bass hits per beat ----
        # The kick owns step 0 of each beat; the bass gallops on steps 1,2,3
        # (the classic "rolling" 3-note-per-beat psytrance bassline).
        if bass_on:
            bass_gain = 0.95 if not in_drop else 1.05
            root = A2*2**(chord/12)*0.5           # A1-ish root
            for b in range(4):
                for k in (1, 2, 3):
                    f = root
                    s_glob = b*4 + k
                    # psychedelic movement: octave/fifth lifts on off accents
                    if in_drop and s_glob == 15:
                        f *= 2                     # bar-end octave lift
                    elif is_drop2 and s_glob in (7, 11):
                        f *= 2
                    elif sec == "build" and k == 3:
                        f *= 2**(1 if b % 2 else 0)
                    place(mix, bass_note(f, int(STEP*SR*0.62)), t0+b*BEAT+k*STEP, bass_gain)

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

        # ---- DROP leads: acid squelch + sparse FM accents + trance lead ----
        if in_drop:
            lg = 0.5 if is_drop2 else 0.42
            pidx = (bar // 4 + (1 if is_drop2 else 0)) % len(ACID_PATTERNS)
            pat = ACID_PATTERNS[pidx]
            # acid 16th squelch line (into the FX lead bus)
            for s in range(16):
                if s % 2 == 1 and (bar+s) % 4 != 0:
                    continue
                f = A2*2**(chord/12)*2**(pat[s]/12)
                place(lead, acid_note(f, int(STEP*1.6*SR), 1.0 if is_drop2 else 0.7),
                      t0+s*STEP, 0.5)
            # FM squelch: sparse softer accents on the last bar of each phrase
            if bar % 4 == 3:
                for s in (11, 15):
                    f = A2*2**(chord/12)*2**((pat[s]+7)/12)
                    place(lead, fm_squelch(f, int(STEP*SR), index=3.5), t0+s*STEP, 0.4)
            # sustained trance lead: motif varies per 4-bar phrase
            motif = LEAD_MOTIFS[(bar // 4) % len(LEAD_MOTIFS)]
            for i, (s, semi, ln) in enumerate(motif):
                f = A2*2*2**(semi/12)            # an octave up: bright lead register
                bend = (0.25 if i % 3 == 1 else (-0.25 if i % 3 == 2 else 0.0))
                place(lead, trance_lead_note(f, int(ln*STEP*SR), bend=bend,
                                             bright=1.25 if is_drop2 else 1.0,
                                             voices=4 if is_drop2 else 3),
                      t0+s*STEP, lg*0.75)

        # ---- breakdown: lead motif on the FX bus, no kick/bass ----
        if sec == "breakdown":
            # slow acid motif into the lead bus (gets delay/reverb)
            for s, semi in [(0, 0), (4, 3), (8, 7), (12, 10)]:
                f = A2*2**(chord/12)*2**(semi/12)
                place(lead, acid_note(f, int(BEAT*1.5*SR), 0.7), t0+s*STEP, 0.5)
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

    mix += process_lead(lead)

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

    stem = f"psytrance_{int(round(args.bpm))}bpm"
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
