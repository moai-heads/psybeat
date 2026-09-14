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

    # ---------- arrangement ----------
    mix = np.zeros(N+SR)
    K, S, C, H, HO = kick(), snare(), clap(), hat(), hat(True)

    def place(buf, sig, tsec, gain=1.0):
        i = int(tsec*SR)
        j = min(i+len(sig), len(buf))
        buf[i:j] += sig[:j-i]*gain

    for bar in range(BARS):
        t0 = bar*BAR
        # kick on every beat
        for b in range(4):
            place(mix, K, t0+b*BEAT, 1.0)
        # snare/clap on 2 & 4
        for b in (1,3):
            place(mix, S, t0+b*BEAT, 0.9)
            place(mix, C, t0+b*BEAT, 0.55)
        # rolling 16th bassline
        pattern = [1]*16
        for s in range(16):
            if not pattern[s]: continue
            s16 = (s + bar*16)
            # subtle note movement: root A1, drop to G1 / F1 in places
            prog = [[55.0],[55.0],[55.0,55.0],[55.0]][bar%4]
            f = prog[s16 % len(prog)]
            if bar%8>=4 and s in (7,15): f *= 2      # octave lift
            place(mix, bass_note(f, int(STEP*SR*0.99)), t0+s*STEP, 0.95)
        # hats from bar 4
        if bar >= 4:
            place(mix, H,  t0+0*BEAT+STEP*0, 1)
            for b in range(4):
                place(mix, H, t0+b*BEAT+STEP*2, 0.85)
                place(mix, H, t0+b*BEAT+STEP*2+STEP, 0.5)
            place(mix, HO, t0+3*BEAT+STEP*3, 0.8)
        # acid lead from bar 8
        if bar >= 8:
            for s in range(16):
                if s % 2 == 1 and (bar+s) % 4 != 0: continue
                semi = ACID_SEMIS[s]
                f = 110.0*2**(semi/12)
                br = 1.0 if bar >= 12 else 0.7
                place(mix, acid_note(f, int(STEP*1.6*SR), br), t0+s*STEP, 0.5)

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
    ap.add_argument("--bars", type=int, default=16, help="length in bars (default 16)")
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
