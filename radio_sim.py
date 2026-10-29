"""
Radio channel simulator v2 (problem #16). Adds what real VHF does that Day 2's version didn't:

  1. Noise level measured on SPEECH ONLY. (v1 averaged over silences too, so its
     "0 dB" was really cleaner than 0 dB on the words.)
  2. Push-to-talk clipping: people start talking before the button opens the channel,
     so the first 60-200 ms of speech is lost ("..ndia 2817" instead of "Air India 2817").
  3. Squelch tail: the short burst of loud static when the button is released.
  4. Real background noise: if you put WAV files in noise/ (engine, apron, wind, traffic),
     one is mixed in at random. Without files, only synthetic radio hiss is used.

What it still does NOT do (stated, not hidden): two people transmitting at once,
signal fading over distance, radio interference whistles. Those need real radios or recordings.
"""
import os
import glob
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, resample_poly

SR = 8000
BAND = butter(4, [300, 3400], btype="band", fs=SR, output="sos")


def _speech_mask(x, frame=160):
    """True where someone is talking (energy above 10% of the loudest frames)."""
    n = len(x) // frame
    e = np.array([np.mean(x[i * frame:(i + 1) * frame] ** 2) for i in range(n)])
    if n == 0 or e.max() == 0:
        return np.ones(len(x), bool)
    active = e > 0.1 * np.percentile(e, 95)
    mask = np.repeat(active, frame)
    return np.pad(mask, (0, len(x) - len(mask)), constant_values=False)


def _mulaw(x, mu=255):
    c = np.sign(x) * np.log1p(mu * np.abs(x)) / np.log1p(mu)
    c = np.round(c * 127) / 127
    return np.sign(c) * ((1 + mu) ** np.abs(c) - 1) / mu


def _background(rng, length):
    files = glob.glob("noise/*.wav")
    if not files:
        return None
    y, sr = sf.read(rng.choice(files))
    if y.ndim > 1:
        y = y.mean(axis=1)
    y = resample_poly(y, SR, sr)
    if len(y) < length:
        y = np.tile(y, length // len(y) + 1)
    start = rng.integers(0, len(y) - length + 1)
    return y[start:start + length]


def radio(x, sr, snr_db, seed, return_clean=False):
    rng = np.random.default_rng(seed)
    if x.ndim > 1:
        x = x.mean(axis=1)
    x = resample_poly(x, SR, sr)
    x = sosfilt(BAND, x)

    # 2. push-to-talk clipping: cut 60-200 ms from where speech starts
    m = _speech_mask(x)
    if m.any():
        first = int(np.argmax(m))
        cut = int(rng.uniform(0.06, 0.20) * SR)
        x[first:first + cut] = 0.0
    x = 0.7 * x / (np.max(np.abs(x)) + 1e-9)

    # 1. noise at the requested level, measured on speech only
    m = _speech_mask(x)
    p_speech = np.mean(x[m] ** 2) if m.any() else np.mean(x ** 2)
    hiss = sosfilt(BAND, rng.normal(size=len(x)))
    bg = _background(rng, len(x))
    noise = hiss if bg is None else 0.5 * hiss / (np.std(hiss) + 1e-9) + \
        0.5 * sosfilt(BAND, bg) / (np.std(sosfilt(BAND, bg)) + 1e-9)
    noise *= np.sqrt(p_speech / (10 ** (snr_db / 10)) / (np.mean(noise ** 2) + 1e-12))

    crackle = np.zeros(len(x))
    idx = rng.choice(len(x), size=max(1, int(20 * len(x) / SR)), replace=False)
    crackle[idx] = rng.uniform(-0.3, 0.3, size=len(idx))
    y = x + noise + crackle

    # 3. squelch tail: 120-250 ms of loud static at the end
    tail = int(rng.uniform(0.12, 0.25) * SR)
    y = np.concatenate([y, sosfilt(BAND, rng.normal(size=tail)) * 0.3])

    out = _mulaw(np.clip(y, -0.9, 0.9))
    if return_clean:
        return out, np.concatenate([x, np.zeros(tail)])
    return out


def measured_snr(clean_8k, noisy_8k):
    """Check: SNR on speech parts, so we can verify the label is true."""
    n = min(len(clean_8k), len(noisy_8k))
    c, y = clean_8k[:n], noisy_8k[:n]
    m = _speech_mask(c)
    g = np.dot(y[m], c[m]) / (np.dot(c[m], c[m]) + 1e-12)
    resid = y[m] - g * c[m]
    return 10 * np.log10(np.mean((g * c[m]) ** 2) / (np.mean(resid ** 2) + 1e-12))
