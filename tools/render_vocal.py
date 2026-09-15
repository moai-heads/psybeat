#!/usr/bin/env python3
"""Render the psytrance female vocal line to a dry WAV asset.

Uses piper (neural TTS) to synthesize the lyrics with a female voice, at
22.05 kHz mono, then resamples to the project rate (44.1 kHz) so
src/psybeat.py can load it.  The heavy processing (pitch/air, delay,
reverb, placement in the breakdown) happens in src/psybeat.py, keeping the
generator itself pure-DSP.

The piper venv + voice model live outside the repo:
    /root/.venv-piper                     (piper-tts + onnxruntime)
    /root/voices/en_US-amy-medium.onnx    (female voice)

Run:
    python3 tools/render_vocal.py            # -> assets/vocal_dry.wav
"""
from __future__ import annotations

import os
import sys
import wave

SYSTEM_SR = 44100
VOICE = "/root/voices/en_US-amy-medium.onnx"
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "vocal_dry.wav")

# --- the lyrics: one psychedelic couplet, ~4 bars at 145 BPM ----------------
# Placed across the breakdown; its delay/reverb tail runs into DROP 2.
LYRICS = (
    "The veil is thinning, the fractal blooms. "
    "We are the light behind your eyes."
)


def main() -> int:
    try:
        from piper import PiperVoice
    except ImportError:
        print("error: piper not importable; run under the piper venv", file=sys.stderr)
        return 2
    if not os.path.exists(VOICE):
        print(f"error: voice model missing: {VOICE}", file=sys.stderr)
        return 2

    voice = PiperVoice.load(VOICE)
    tmp = "/tmp/psybeat_vocal_22k.wav"
    with wave.open(tmp, "wb") as w:
        voice.synthesize_wav(LYRICS, w)
    with wave.open(tmp) as w:
        sr = w.getframerate()
        data = w.readframes(w.getnframes())

    import numpy as np
    from scipy.signal import resample_poly
    x = np.frombuffer(data, dtype="<i2").astype(np.float64) / 32768.0
    # 22050 -> 44100
    y = resample_poly(x, SYSTEM_SR, sr)
    y = y / max(1e-9, np.max(np.abs(y)))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    import soundfile as sf
    sf.write(os.path.abspath(OUT), y.astype("float32"), SYSTEM_SR)
    print(f"wrote {os.path.abspath(OUT)}  dur={len(y)/SYSTEM_SR:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
