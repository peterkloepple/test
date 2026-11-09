# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m99d_stimme (v2.4.9)
# v2.4.9: 10 Aufnahmen, Raumgeraeusch wird herausgerechnet, Pruefung von Wortlaut/Sprechweise UND Stimmklang,
#         der Satz wird beim Entsperren nicht mehr angezeigt (nur du kennst ihn), Ansage + Signaltoene.
# v2.4.7: ohne das Python-Modul "wave" (war nicht in der EXE -> Programm startete nicht)
# Stimme als zweiter Schluessel nach der PIN.
#  - Einschalten: Einstellungen > PIN & Sperre > Karte "Stimme". Du sprichst deinen Satz 3x ein
#    (z. B. "Pfeiffer Audio, oeffne dich"), das Programm lernt daraus Klang und Sprechweise.
#  - Entsperren: PIN eingeben -> "Sprich jetzt deinen Satz" -> erst wenn Stimme UND Satz passen, ist das
#    Programm offen. Ohne Stimm-Treffer gibt es keine Sitzung (auch keine Handy-/LAN-Freigabe).
#  - Notfall-Code (wird beim Einschalten einmal angezeigt): ersetzt die Stimme, wenn sie nicht erkannt
#    wird (Erkaeltung, kaputtes Mikrofon, Laerm). Gut aufheben!
#  - Das Stimmprofil (Merkmale, keine Tonaufnahme) liegt verschluesselt mit dem Schluessel aus deiner PIN
#    im Datenordner (wie das Standard-Passwort, m97). PIN aendern verschluesselt es neu.
#  - Aufnahme direkt ueber die Windows-Audioschnittstelle (winmm, Standard-Mikrofon), 16 kHz mono, nichts
#    wird gespeichert oder verschickt. Erkennung: MFCC-Merkmale + DTW-Vergleich mit deinen 3 Aufnahmen
#    (textabhaengig: der Satz muss stimmen). Ohne Zusatz-Bibliothek; numpy wird genutzt, wenn vorhanden.
#  - Grenze: Das ist eine zusaetzliche Huerde, keine Bank-Sicherheit - eine gute Aufnahme deiner Stimme
#    kann die Pruefung taeuschen. Die PIN bleibt der eigentliche Schutz.
# Autor: T. Pfeiffer

import math
import struct as _m99d_struct

M99D_VERSION = "2.0.0"
M99D_SR = 16000
M99D_SEK = 4.0
M99D_SATZ = "Pfeiffer Audio, öffne dich"
M99D_STRENGE = {"locker": 1.45, "normal": 1.25, "streng": 1.10}
M99D_MAX_VERSUCHE = 5
M99D = {"pending": {}, "enroll": {}, "profil": None, "lock": threading.Lock(), "rec": threading.Lock(), "fake_i": 0}
M99D_TEST = (__name__ == "pa_selbsttest")

try:
    import numpy as _np
except Exception:
    _np = None


# ============================================================ 1. recording (Windows winmm, no extra library)
def _m99d_rec_windows(sek):
    import ctypes
    from ctypes import wintypes

    class WAVEFORMATEX(ctypes.Structure):
        _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD), ("nSamplesPerSec", wintypes.DWORD),
                    ("nAvgBytesPerSec", wintypes.DWORD), ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                    ("cbSize", wintypes.WORD)]

    class WAVEHDR(ctypes.Structure):
        pass
    WAVEHDR._fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD), ("dwBytesRecorded", wintypes.DWORD),
                        ("dwUser", ctypes.c_size_t), ("dwFlags", wintypes.DWORD), ("dwLoops", wintypes.DWORD),
                        ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]
    wm = ctypes.WinDLL("winmm")
    wm.waveInOpen.argtypes = [ctypes.POINTER(wintypes.HANDLE), ctypes.c_uint, ctypes.POINTER(WAVEFORMATEX), ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]
    for fn in ("waveInPrepareHeader", "waveInUnprepareHeader", "waveInAddBuffer"):
        getattr(wm, fn).argtypes = [wintypes.HANDLE, ctypes.POINTER(WAVEHDR), ctypes.c_uint]
    for fn in ("waveInStart", "waveInStop", "waveInReset", "waveInClose"):
        getattr(wm, fn).argtypes = [wintypes.HANDLE]
    if wm.waveInGetNumDevs() == 0:
        raise ValueError("Kein Mikrofon gefunden. Bitte ein Mikrofon/Headset anschließen.")
    fmt = WAVEFORMATEX(1, 1, M99D_SR, M99D_SR * 2, 2, 16, 0)
    h = wintypes.HANDLE()
    r = wm.waveInOpen(ctypes.byref(h), 0xFFFFFFFF, ctypes.byref(fmt), 0, 0, 0)
    if r != 0:
        raise ValueError(f"Mikrofon lässt sich nicht öffnen (Fehler {r}) – wird es gerade von einem anderen Programm benutzt?")
    n = int(sek * M99D_SR) * 2
    buf = ctypes.create_string_buffer(n)
    hdr = WAVEHDR()
    hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
    hdr.dwBufferLength = n
    try:
        wm.waveInPrepareHeader(h, ctypes.byref(hdr), ctypes.sizeof(hdr))
        wm.waveInAddBuffer(h, ctypes.byref(hdr), ctypes.sizeof(hdr))
        wm.waveInStart(h)
        t0 = time.time()
        while not (hdr.dwFlags & 1) and time.time() - t0 < sek + 3:     # WHDR_DONE
            time.sleep(0.05)
        wm.waveInStop(h)
        wm.waveInReset(h)
        wm.waveInUnprepareHeader(h, ctypes.byref(hdr), ctypes.sizeof(hdr))
        data = buf.raw[:hdr.dwBytesRecorded]
    finally:
        wm.waveInClose(h)
    return list(_m99d_struct.unpack("<%dh" % (len(data) // 2), data[:len(data) // 2 * 2]))


def _m99d_read_wav(path):
    """16 bit PCM WAV -> samples (own small RIFF reader; the module "wave" is not part of the EXE)"""
    raw = open(path, "rb").read()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("Keine WAV-Datei.")
    pos, ch, sr, sw, data = 12, 1, M99D_SR, 2, b""
    while pos + 8 <= len(raw):
        cid, size = raw[pos:pos + 4], _m99d_struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            ch, sr = _m99d_struct.unpack("<HI", body[2:8])
            sw = _m99d_struct.unpack("<H", body[14:16])[0] // 8
        elif cid == b"data":
            data = body
        pos += 8 + size + (size & 1)
    if sw != 2:
        raise ValueError("WAV muss 16 bit sein.")
    x = list(_m99d_struct.unpack("<%dh" % (len(data) // 2), data[:len(data) // 2 * 2]))
    if ch > 1:
        x = x[::ch]
    if sr != M99D_SR:                                      # simple resampling (nearest)
        f = sr / M99D_SR
        x = [x[min(len(x) - 1, int(i * f))] for i in range(int(len(x) / f))]
    return x


def stimme_aufnehmen(sek=None):
    """record from the default microphone -> list of int16 samples (16 kHz mono)"""
    sek = float(sek or get_settings().get("m99d_sek") or M99D_SEK)
    fake = os.environ.get("PA_STIMME_WAV")                 # tests only: wav file or folder with wav files (in turn)
    if fake:
        files = sorted(os.path.join(fake, f) for f in os.listdir(fake) if f.lower().endswith(".wav")) if os.path.isdir(fake) else [fake]
        p = files[M99D["fake_i"] % len(files)]
        M99D["fake_i"] += 1
        return _m99d_read_wav(p)
    if not sys.platform.startswith("win"):
        raise ValueError("Die Sprachprüfung gibt es nur unter Windows.")
    if not M99D["rec"].acquire(timeout=10):
        raise ValueError("Das Mikrofon nimmt gerade schon auf.")
    try:
        return _m99d_rec_windows(sek)
    finally:
        M99D["rec"].release()


# ============================================================ 2. features (MFCC) and comparison (DTW)
def _m99d_fft_pow(fr, nfft):
    """power spectrum of one frame (pure python radix-2 FFT)"""
    n = nfft
    a = [complex(v, 0) for v in fr] + [0j] * (n - len(fr))
    j = 0
    for i in range(1, n):                                   # bit reversal
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    size = 2
    while size <= n:
        half = size // 2
        tw = _M99D_TW[size]
        for start in range(0, n, size):
            for k in range(half):
                u = a[start + k]
                v = a[start + k + half] * tw[k]
                a[start + k] = u + v
                a[start + k + half] = u - v
        size *= 2
    return [(c.real * c.real + c.imag * c.imag) / n for c in a[:n // 2 + 1]]


_M99D_TW = {}
_s = 2
while _s <= 512:
    _M99D_TW[_s] = [complex(math.cos(-2 * math.pi * k / _s), math.sin(-2 * math.pi * k / _s)) for k in range(_s // 2)]
    _s *= 2


def _m99d_melbank(nfft=512, nmel=26, sr=M99D_SR, fmin=80, fmax=7600):
    mel = lambda f: 2595 * math.log10(1 + f / 700)
    imel = lambda m: 700 * (10 ** (m / 2595) - 1)
    pts = [imel(mel(fmin) + (mel(fmax) - mel(fmin)) * i / (nmel + 1)) for i in range(nmel + 2)]
    bins = [int((nfft + 1) * p / sr) for p in pts]
    bank = []
    for m in range(1, nmel + 1):
        f = []
        for k in range(bins[m - 1], bins[m + 1] + 1):
            if k < bins[m] and bins[m] > bins[m - 1]:
                f.append((k, (k - bins[m - 1]) / (bins[m] - bins[m - 1])))
            elif k >= bins[m] and bins[m + 1] > bins[m]:
                f.append((k, (bins[m + 1] - k) / (bins[m + 1] - bins[m])))
        bank.append([(k, wgt) for k, wgt in f if wgt > 0 and k <= nfft // 2])
    return bank


_M99D_BANK = _m99d_melbank()
_M99D_HAM = [0.54 - 0.46 * math.cos(2 * math.pi * i / 399) for i in range(400)]
_M99D_DCT = [[math.cos(math.pi * c * (m + 0.5) / 26) for m in range(26)] for c in range(13)]


def _m99d_powspec(frames):
    """frames (lists, already windowed) -> list of power spectra (257 bins)"""
    if _np is not None:
        P = (_np.abs(_np.fft.rfft(_np.array(frames, dtype=float), 512)) ** 2) / 512
        return P
    return [_m99d_fft_pow(fr, 512) for fr in frames]


def stimme_merkmale(x):
    """samples -> (features, info)
    v2.4.9: noise robust - the room noise is measured in the quiet parts of the recording and subtracted
    (spectral subtraction); voice activity by SNR; features = 12 MFCC + 12 delta (speed of change), mean-normalised."""
    info = {"dauer": 0, "pegel": 0, "clip": 0.0, "snr": 0.0}
    if not x or len(x) < 1600:
        return [], info
    info["clip"] = round(sum(1 for v in x if abs(v) >= 32000) / len(x), 4)
    pe = [x[0]] + [x[i] - 0.97 * x[i - 1] for i in range(1, len(x))]
    frames = [[v * h for v, h in zip(pe[i:i + 400], _M99D_HAM)] for i in range(0, len(pe) - 400, 160)]
    if len(frames) < 10:
        return [], info
    P = _m99d_powspec(frames)
    en = [float(sum(row[3:129])) + 1e-9 for row in P]          # speech band ~100 Hz - 4 kHz (mains hum does not count)
    order = sorted(range(len(en)), key=lambda k: en[k])
    quiet = order[:max(3, len(en) // 7)]                       # quietest ~15 % of the frames = room noise
    noise = [sum(float(P[k][b]) for k in quiet) / len(quiet) for b in range(257)]
    n_en = sum(noise[3:129]) + 1e-9
    db = [10 * math.log10(e / n_en) for e in en]
    p90 = sorted(db)[int(len(db) * 0.9)]
    thr = max(4.0, min(9.0, p90 * 0.5))                           # adaptive: works in quiet and in noisy rooms
    speech = [k for k, d in enumerate(db) if d > thr]
    raw_peak = max(abs(v) for v in x)
    info["pegel"] = int(raw_peak)
    if not speech:
        return [], info
    a, b = max(0, speech[0] - 4), min(len(frames), speech[-1] + 5)
    info["dauer"] = round((b - a) * 0.01, 2)
    sp = [en[k] for k in speech]
    info["snr"] = round(10 * math.log10((sum(sp) / len(sp)) / n_en), 1)
    feats = []
    for k in range(a, b):
        row = P[k]
        clean = [max(float(row[bb]) - 1.5 * noise[bb], 0.03 * float(row[bb])) for bb in range(257)]
        e = [math.log(sum(clean[kk] * w for kk, w in f) + 1e-6) for f in _M99D_BANK]
        feats.append([sum(d * v for d, v in zip(rw, e)) for rw in _M99D_DCT[1:13]])
    n = len(feats)
    mean = [sum(f[i] for f in feats) / n for i in range(12)]
    st = [[f[i] - mean[i] for i in range(12)] for f in feats]
    out = []
    for t in range(n):                                          # delta over +-2 frames
        a2, a1, b1, b2 = st[max(0, t - 2)], st[max(0, t - 1)], st[min(n - 1, t + 1)], st[min(n - 1, t + 2)]
        dl = [((b1[i] - a1[i]) + 2 * (b2[i] - a2[i])) / 10.0 for i in range(12)]
        out.append([round(v, 4) for v in st[t] + dl])
    return out, info


def stimme_abstand(a, b):
    """DTW distance of two feature sequences (normalised by path length; Sakoe-Chiba band)"""
    la, lb = len(a), len(b)
    if not la or not lb:
        return 1e9
    band = max(int(max(la, lb) * 0.25), abs(la - lb) + 2)
    INF = float("inf")
    if _np is not None:
        A, B = _np.array(a), _np.array(b)
        D = _np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(axis=2))
        acc = _np.full((la + 1, lb + 1), INF)
        acc[0, 0] = 0.0
        for i in range(1, la + 1):
            j0, j1 = max(1, int(i * lb / la) - band), min(lb, int(i * lb / la) + band)
            row, prev = acc[i], acc[i - 1]
            for j in range(j0, j1 + 1):
                row[j] = D[i - 1, j - 1] + min(prev[j], row[j - 1], prev[j - 1])
        return float(acc[la, lb]) / (la + lb)
    prev = [INF] * (lb + 1)
    prev[0] = 0.0
    for i in range(1, la + 1):
        cur = [INF] * (lb + 1)
        ai = a[i - 1]
        j0, j1 = max(1, int(i * lb / la) - band), min(lb, int(i * lb / la) + band)
        for j in range(j0, j1 + 1):
            bj = b[j - 1]
            d = math.sqrt(sum((p - q) * (p - q) for p, q in zip(ai, bj)))
            cur[j] = d + min(prev[j], cur[j - 1], prev[j - 1])
        prev = cur
    return prev[lb] / (la + lb)


def stimme_qualitaet(info):
    """German hint if a recording is unusable, else ''"""
    if info.get("pegel", 0) < 300:
        return ("Kein Ton vom Mikrofon. Mikrofon angeschlossen? Windows: Einstellungen → Datenschutz → Mikrofon → "
                "„Desktop-Apps Zugriff erlauben“ einschalten.")
    if info.get("dauer", 0) < 0.6:
        return "Zu kurz oder zu leise – bitte den ganzen Satz deutlich sprechen."
    if info.get("clip", 0) > 0.02:
        return "Zu laut / übersteuert – etwas weiter vom Mikrofon weg sprechen."
    if info.get("snr", 99) < 5:
        return "Zu viele Nebengeräusche – bitte etwas lauter sprechen oder leiser Raum."
    return ""


# ============================================================ 3. profile (encrypted with the PIN key, m97)
def _m99d_cfg():
    s = get_settings()
    return {"aktiv": bool(s.get("m99d_aktiv")), "satz": str(s.get("m99d_satz") or M99D_SATZ),
            "strenge": s.get("m99d_strenge") if s.get("m99d_strenge") in M99D_STRENGE else "normal"}


def _m99d_profil_laden(key=None):
    key = key or M97.get("key")
    tok = _m97_raw("m99d_profil_enc")
    if not key or not tok:
        return None
    try:
        return json.loads(_m97_fernet(key).decrypt(str(tok).encode()).decode("utf-8"))
    except Exception:
        return None


def _m99d_profil_speichern(profil, key=None):
    key = key or M97.get("key")
    if not key:
        raise ValueError("Bitte erst mit der PIN entsperren.")
    tok = _m97_fernet(key).encrypt(json.dumps(profil).encode("utf-8")).decode()
    x("INSERT OR REPLACE INTO settings (k, v) VALUES (?, ?)", ("m99d_profil_enc", json.dumps(tok)))
    M99D["profil"] = profil


def _m99d_notfall_neu():
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = "-".join("".join(secrets.choice(alpha) for _ in range(4)) for _ in range(3))
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", code.replace("-", "").encode(), salt, 150000).hex()
    set_setting("m99d_notfall", {"salt": salt.hex(), "hash": h, "zeit": now_iso()})
    return code


def _m99d_notfall_ok(code):
    n = get_settings().get("m99d_notfall") or {}
    if not n.get("hash"):
        return False
    c = re.sub(r"[^A-Za-z0-9]", "", str(code or "")).upper()
    h = hashlib.pbkdf2_hmac("sha256", c.encode(), bytes.fromhex(n["salt"]), 150000).hex()
    return secrets.compare_digest(h, n["hash"])


M99D_N = 10                     # v2.4.9: 10 recordings for the voice profile
M99D_K = {"locker": 3.2, "normal": 2.4, "streng": 1.7}     # how many standard deviations above your own spread
# all 10 recordings are made in one sitting - on another day the voice varies more, so there is a margin relative to
# your own average (wording/way of speaking, timbre)
M99D_REL = {"locker": (1.25, 2.6), "normal": (1.18, 2.1), "streng": (1.10, 1.6)}


def _m99d_spk_model(seqs):
    """voice timbre: mean / variance of the 12 static coefficients over all frames"""
    fr = [f[:12] for s_ in seqs for f in s_]
    n = max(1, len(fr))
    mu = [sum(f[i] for f in fr) / n for i in range(12)]
    var = [max(0.05, sum((f[i] - mu[i]) ** 2 for f in fr) / n) for i in range(12)]
    return mu, var


def _m99d_spk_score(seq, mu, var):
    """mean squared z-distance of the frame-averaged timbre (small = same voice)"""
    n = max(1, len(seq))
    m = [sum(f[i] for f in seq) / n for i in range(12)]
    sd = [sum((f[i] - m[i]) ** 2 for f in seq) / n for i in range(12)]
    return sum((m[i] - mu[i]) ** 2 / var[i] + abs(math.log((sd[i] + 1e-3) / var[i])) for i in range(12)) / 12


def _m99d_dtw_score(seq, vorlagen, k=3):
    d = sorted(stimme_abstand(seq, t) for t in vorlagen)
    return sum(d[:k]) / len(d[:k])


def stimme_vergleich(feats, profil, strenge=None):
    """-> (ok, score, schwelle). v2: wording + way of speaking (DTW to the 3 closest of your recordings) AND voice timbre."""
    st = strenge or _m99d_cfg()["strenge"]
    if profil.get("v2") is None:                                  # profile from v2.4.6-2.4.8 (3 recordings)
        sch = profil["basis"] * M99D_STRENGE.get(st, 1.25)
        score = min(stimme_abstand([f[:12] for f in feats], t) for t in profil["vorlagen"])
        return score <= sch and 0.5 <= len(feats) / max(1, profil["laenge"]) <= 2.0, round(score, 3), round(sch, 3)
    k = M99D_K.get(st, 2.4)
    v = profil["v2"]
    rd, rs = M99D_REL.get(st, (1.18, 2.1))
    d_thr = max(v["d_mean"] + k * v["d_std"], v["d_max"] * (1.08 if st == "locker" else 1.0 if st == "normal" else 0.95), v["d_mean"] * rd)
    s_thr = max(v["s_mean"] + k * v["s_std"], v["s_max"] * (1.15 if st == "locker" else 1.05 if st == "normal" else 1.0), v["s_mean"] * rs)
    d = _m99d_dtw_score(feats, profil["vorlagen"])
    sp = _m99d_spk_score(feats, v["mu"], v["var"])
    dur_ok = 0.6 <= len(feats) / max(1, profil["laenge"]) <= 1.7
    ok = d <= d_thr and sp <= s_thr and dur_ok
    # one number for the display: worst of both, relative to its limit (1.0 = limit)
    score = max(d / d_thr, sp / s_thr) if d_thr and s_thr else 9
    return ok, round(score, 3), 1.0


def stimme_lernen(samples):
    """10 enrolment feature sequences -> profile (or ValueError naming the recordings to repeat)"""
    if len(samples) < M99D_N:
        raise ValueError(f"Bitte den Satz {M99D_N}x einsprechen ({len(samples)} von {M99D_N} fertig).")
    nrs = sorted(samples)
    seqs = [samples[n] for n in nrs]
    loo_d, loo_s = [], []
    for i in range(len(seqs)):
        rest = seqs[:i] + seqs[i + 1:]
        loo_d.append(_m99d_dtw_score(seqs[i], rest))
        mu, var = _m99d_spk_model(rest)
        loo_s.append(_m99d_spk_score(seqs[i], mu, var))
    med = sorted(loo_d)[len(loo_d) // 2]
    bad = [nrs[i] for i, dv in enumerate(loo_d) if dv > med * 1.6 + 0.3]
    if bad:
        raise ValueError("Diese Aufnahmen passen nicht zu den anderen (anderer Satz, Versprecher oder Störgeräusch): Nr. "
                         + ", ".join(map(str, bad)) + " – bitte nur diese neu einsprechen.")
    mean = lambda a: sum(a) / len(a)
    std = lambda a: math.sqrt(sum((v - mean(a)) ** 2 for v in a) / len(a))
    mu, var = _m99d_spk_model(seqs)
    return {"vorlagen": seqs, "laenge": mean([len(s_) for s_ in seqs]), "zeit": now_iso(), "v": M99D_VERSION,
            "v2": {"mu": [round(v, 4) for v in mu], "var": [round(v, 4) for v in var],
                   "d_mean": round(mean(loo_d), 4), "d_std": round(std(loo_d), 4), "d_max": round(max(loo_d), 4),
                   "s_mean": round(mean(loo_s), 4), "s_std": round(std(loo_s), 4), "s_max": round(max(loo_s), 4)}}


# keep the profile readable after a PIN change (m97 re-keys on _m92_store)
@chain_step("_m92_store", "m99d_stimme")
def _m99d_step__m92_store(_next, pin):
    prof = _m99d_profil_laden() if _m99d_cfg()["aktiv"] else None
    _next(pin)
    if prof:
        try:
            _m99d_profil_speichern(prof)
        except Exception:
            traceback.print_exc()


# ============================================================ 4. unlock: PIN -> voice -> session
def _m99d_pending(vt):
    with M99D["lock"]:
        now = time.time()
        for k in [k for k, v in M99D["pending"].items() if now - v["t"] > 180]:
            M99D["pending"].pop(k, None)
        return M99D["pending"].get(str(vt or ""))


@chain_step("_m92_post", "m99d_stimme")
def _m99d_step_m92_post(_next, handler, p):
    cfg = _m99d_cfg()
    if M92_TESTLAUF or not cfg["aktiv"]:
        return _next(handler, p)
    if p == "/api/m92/unlock":
        d = _m92_json(handler)
        ok, err, wait = m92_verify(d.get("pin"))
        if not ok:
            time.sleep(0.4)
            return handler._send(200, {"ok": False, "error": err, "wait": wait})
        M99D["profil"] = _m99d_profil_laden()
        vt = secrets.token_urlsafe(18)
        with M99D["lock"]:
            M99D["pending"][vt] = {"t": time.time(), "n": 0}
        s_ = get_settings()
        # v2.4.9: the sentence is NOT sent to the lock page - only you know it
        return handler._send(200, {"ok": True, "stimme": True, "vtoken": vt, "sek": float(s_.get("m99d_sek") or M99D_SEK),
                                   "ansage": s_.get("m99d_ansage", True) is not False, "toene": s_.get("m99d_toene", True) is not False})
    if p == "/api/m92/stimme":
        d = _m92_json(handler)
        pe = _m99d_pending(d.get("vtoken"))
        if not pe:
            return handler._send(200, {"ok": False, "neu": True, "error": "Zeit abgelaufen – bitte die PIN neu eingeben."})
        try:
            feats, info = stimme_merkmale(stimme_aufnehmen())
        except ValueError as e:
            return handler._send(200, {"ok": False, "error": str(e), "rest": M99D_MAX_VERSUCHE - pe["n"]})
        q_ = stimme_qualitaet(info)
        if q_:
            return handler._send(200, {"ok": False, "error": q_, "rest": M99D_MAX_VERSUCHE - pe["n"]})
        prof = M99D["profil"]
        ok, score, sch = stimme_vergleich(feats, prof) if prof else (False, 0, 0)
        if ok:
            with M99D["lock"]:
                M99D["pending"].pop(d.get("vtoken"), None)
            set_setting("m99d_letzte", {"zeit": now_iso(), "score": score, "schwelle": sch, "ok": True})
            return handler._send(200, {"ok": True}, extra=_m92_new_session())
        pe["n"] += 1
        set_setting("m99d_letzte", {"zeit": now_iso(), "score": score, "schwelle": sch, "ok": False})
        if pe["n"] >= M99D_MAX_VERSUCHE:
            with M99D["lock"]:
                M99D["pending"].pop(d.get("vtoken"), None)
            return handler._send(200, {"ok": False, "neu": True, "error": "Stimme nicht erkannt – bitte die PIN neu eingeben (oder Notfall-Code)."})
        return handler._send(200, {"ok": False, "error": "Stimme nicht erkannt – bitte nochmal deutlich den Satz sprechen.",
                                   "rest": M99D_MAX_VERSUCHE - pe["n"]})
    if p == "/api/m92/stimme_notfall":
        d = _m92_json(handler)
        pe = _m99d_pending(d.get("vtoken"))
        if not pe:
            return handler._send(200, {"ok": False, "neu": True, "error": "Zeit abgelaufen – bitte die PIN neu eingeben."})
        time.sleep(0.6)
        if _m99d_notfall_ok(d.get("code")):
            with M99D["lock"]:
                M99D["pending"].pop(d.get("vtoken"), None)
            set_setting("m99d_letzte", {"zeit": now_iso(), "notfall": True, "ok": True})
            return handler._send(200, {"ok": True}, extra=_m92_new_session())
        pe["n"] += 1
        if pe["n"] >= M99D_MAX_VERSUCHE:
            with M99D["lock"]:
                M99D["pending"].pop(d.get("vtoken"), None)
            return handler._send(200, {"ok": False, "neu": True, "error": "Notfall-Code falsch – bitte die PIN neu eingeben."})
        return handler._send(200, {"ok": False, "error": "Notfall-Code falsch."})
    return _next(handler, p)


# lock page: voice step after the PIN
M99D_PAGE_CSS = """
.vbox{display:none;margin-top:6px}
.vbox.on{display:block}
.mic{width:96px;height:96px;border-radius:50%;border:0;background:var(--acc);color:#fff;cursor:pointer;margin:6px auto 12px;display:flex;align-items:center;justify-content:center;box-shadow:0 0 0 0 rgba(138,108,240,.6)}
.mic svg{width:40px;height:40px;stroke:#fff;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.mic.rec{background:var(--bad);animation:pulse 1s infinite}
.mic:disabled{opacity:.5;cursor:default}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(226,87,79,.55)}100%{box-shadow:0 0 0 22px rgba(226,87,79,0)}}
.satz{font:600 18px/1.35 var(--disp);margin:2px 0 14px;color:#fff}
.bar{height:6px;border-radius:3px;background:var(--bg2);overflow:hidden;margin:0 auto 10px;max-width:260px}
.bar i{display:block;height:100%;width:0;background:var(--acc2)}
.nf{color:var(--mute);font-size:12px;cursor:pointer;text-decoration:underline;margin-top:8px;display:inline-block}
.nfin{display:none;margin-top:10px}
.nfin.on{display:block}
.nfin input{background:var(--bg2);border:1.5px solid #34304a;color:var(--ink);border-radius:10px;padding:9px 12px;font:600 16px var(--disp);letter-spacing:2px;text-align:center;width:220px;text-transform:uppercase}
.nfin button{margin-left:6px;background:var(--acc);color:#fff;border:0;border-radius:10px;padding:10px 14px;font:600 13px var(--font);cursor:pointer}
"""
M99D_PAGE_HTML = """ <div class="vbox" id="vbox">
  <div class="sub" style="margin-bottom:6px">PIN richtig.</div>
  <div class="satz" id="vsatz">Sprich jetzt deinen Satz.</div>
  <button class="mic" id="vmic" title="Aufnehmen (Leertaste)"><svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg></button>
  <div class="bar"><i id="vbar"></i></div>
  <div class="msg" id="vmsg"></div>
  <span class="nf" id="vnf">Stimme klappt nicht? Notfall-Code eingeben</span>
  <div class="nfin" id="vnfin"><input id="vcode" placeholder="XXXX-XXXX-XXXX" maxlength="14" autocomplete="off"><button id="vcodego">OK</button></div>
 </div>
"""
M99D_PAGE_JS = r"""
let vtok = "", vsek = 4, vbusy = false, vansage = true, vtoene = true, vac = null;
function vmsg(t, ok){ const m = $("vmsg"); m.textContent = t || ""; m.className = "msg" + (ok ? " ok" : ""); }
// v2.4.9: acoustic guidance - spoken prompt + signal tones (nothing of it is recorded: the tone ends before the recording starts)
function vtone(seq){
  if (!vtoene) return Promise.resolve();
  try {
    vac = vac || new (window.AudioContext || window.webkitAudioContext)();
    let t = vac.currentTime + 0.02, end = t;
    for (const [f, d] of seq) {
      const o = vac.createOscillator(), g = vac.createGain();
      o.type = "sine"; o.frequency.value = f; g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.015);
      g.gain.exponentialRampToValueAtTime(0.0001, t + d); o.connect(g); g.connect(vac.destination); o.start(t); o.stop(t + d + 0.02); t += d + 0.04; end = t;
    }
    return new Promise(res => setTimeout(res, (end - vac.currentTime) * 1000 + 60));
  } catch (e) { return Promise.resolve(); }
}
function vsay(text){
  if (!vansage || !window.speechSynthesis) return Promise.resolve();
  return new Promise(res => {
    try {
      const u = new SpeechSynthesisUtterance(text); u.lang = "de-DE"; u.rate = 1.05;
      const de = speechSynthesis.getVoices().find(v => /^de/i.test(v.lang)); if (de) u.voice = de;
      u.onend = () => setTimeout(res, 150); u.onerror = () => res(); speechSynthesis.cancel(); speechSynthesis.speak(u);
      setTimeout(res, 4000);
    } catch (e) { res(); }
  });
}
const V_START = [[880, 0.12]], V_OK = [[660, 0.1], [990, 0.16]], V_NO = [[300, 0.18], [220, 0.28]];
function vstart(r){
  vtok = r.vtoken; vsek = r.sek || 4; vansage = r.ansage !== false; vtoene = r.toene !== false;
  $("pad").style.display = "none"; $("dots").style.display = "none"; $("msg").textContent = ""; $("sub").style.display = "none";
  $("vbox").classList.add("on"); vmsg("Auf das Mikrofon tippen (oder Leertaste). Nach dem Ton sprechen.", true);
  vsay("PIN richtig. Tippe auf das Mikrofon und sprich nach dem Ton deinen Satz.");
}
function vreset(t){
  vtok = ""; $("vbox").classList.remove("on"); $("pad").style.display = ""; $("dots").style.display = ""; $("sub").style.display = "";
  $("vnfin").classList.remove("on"); msg(t || ""); padOn(true); dots();
}
async function vrec(){
  if (vbusy || !vtok) return; vbusy = true;
  try { speechSynthesis && speechSynthesis.cancel(); } catch (e) {}
  const mic = $("vmic"); mic.disabled = true; vmsg("Achtung …", true);
  await vtone(V_START);
  mic.classList.add("rec"); vmsg("Sprich jetzt deinen Satz …", true);
  const bar = $("vbar"); bar.style.transition = "none"; bar.style.width = "0"; void bar.offsetWidth;
  bar.style.transition = "width " + vsek + "s linear"; bar.style.width = "100%";
  let r; try { r = await post("/api/m92/stimme", {vtoken: vtok}); } catch (e) { r = {ok: false, error: "Keine Verbindung zum Programm."}; }
  mic.classList.remove("rec"); mic.disabled = false; vbusy = false; bar.style.transition = "none"; bar.style.width = "0";
  if (r.ok) { vmsg("Stimme erkannt – entsperrt", true); await vtone(V_OK); location.replace("/"); return; }
  await vtone(V_NO);
  if (r.neu) { vreset(r.error); vsay("Nicht erkannt. Bitte die PIN neu eingeben."); return; }
  vmsg((r.error || "Nicht erkannt.") + (r.rest ? " (noch " + r.rest + " Versuche)" : ""));
  vsay(/Ton|Mikrofon/.test(r.error || "") ? "Kein Ton vom Mikrofon." : "Nicht erkannt. Bitte nochmal.");
}
async function vcode(){
  const c = $("vcode").value.trim(); if (!c) return;
  let r; try { r = await post("/api/m92/stimme_notfall", {vtoken: vtok, code: c}); } catch (e) { r = {ok: false, error: "Keine Verbindung."}; }
  if (r.ok) { vmsg("Notfall-Code richtig – entsperrt", true); await vtone(V_OK); location.replace("/"); return; }
  if (r.neu) { vreset(r.error); return; }
  vmsg(r.error || "Falsch.");
}
document.addEventListener("DOMContentLoaded", () => {});
setTimeout(() => {
  $("vmic").onclick = vrec; $("vnf").onclick = () => { $("vnfin").classList.toggle("on"); $("vcode").focus(); };
  $("vcodego").onclick = vcode; $("vcode").onkeydown = e => { e.stopPropagation(); if (e.key === "Enter") vcode(); };
  document.addEventListener("keydown", e => { if (vtok && (e.key === " " || e.key === "Enter") && document.activeElement !== $("vcode")) { e.preventDefault(); e.stopImmediatePropagation(); vrec(); } }, true);
}, 0);
"""


def _m99d_patch_page():
    global M92_PAGE
    pg = M92_PAGE
    if "id=\"vbox\"" in pg:
        return
    pg = pg.replace("</style></head>", M99D_PAGE_CSS + "</style></head>", 1)
    pg = pg.replace(' <div class="foot">', M99D_PAGE_HTML + ' <div class="foot">', 1)
    pg = pg.replace('  if (r.ok) { msg("Entsperrt", true); padOn(false); location.replace("/"); return; }',
                    '  if (r.ok && r.stimme) { padOn(false); vstart(r); return; }\n'
                    '  if (r.ok) { msg("Entsperrt", true); padOn(false); location.replace("/"); return; }', 1)
    pg = pg.replace("document.addEventListener(\"keydown\", e => {\n  if (/^\\d$/.test(e.key))",
                    "document.addEventListener(\"keydown\", e => {\n  if (vtok) return;\n  if (/^\\d$/.test(e.key))", 1)
    pg = pg.replace("</script></body></html>", M99D_PAGE_JS + "</script></body></html>", 1)
    pg = pg.replace("Zugang nur mit PIN", "Zugang nur mit PIN__STIMME__", 1)
    M92_PAGE = pg


_m99d_patch_page()
@chain_step("_m92_page", "m99d_stimme")
def _m99d_step__m92_page(_next, ):
    return _next().replace("__STIMME__", " und Stimme" if _m99d_cfg()["aktiv"] else "")


# never offer "Rueckgaengig" for PIN / voice data (an undo must not bring back an old PIN or profile)
try:
    M89_SKIP.add("m92_pin")
    M89_SKIP_PATHS = tuple(M89_SKIP_PATHS) + ("/api/m99d/",)
except NameError:
    pass


# ============================================================ 5. settings (card "Stimme" in PIN & Sperre)
def m99d_status():
    c = _m99d_cfg()
    s = get_settings()
    prof = _m99d_profil_laden() if c["aktiv"] else None
    return {"ok": True, "aktiv": c["aktiv"], "satz": (prof or {}).get("satz") or c["satz"], "strenge": c["strenge"],
            "aufnahmen": sorted(M99D["enroll"].keys()), "n": M99D_N, "alt": bool(prof) and not prof.get("v2"),
            "profil": bool(prof), "letzte": s.get("m99d_letzte") or {}, "notfall": bool((s.get("m99d_notfall") or {}).get("hash")),
            "windows": sys.platform.startswith("win") or bool(os.environ.get("PA_STIMME_WAV")), "sek": float(s.get("m99d_sek") or M99D_SEK),
            "ansage": s.get("m99d_ansage", True) is not False, "toene": s.get("m99d_toene", True) is not False}


def m99d_aufnahme(d):
    nr = int(d.get("nr") or 0)
    if not 1 <= nr <= M99D_N:
        raise ValueError(f"Aufnahme 1 bis {M99D_N}.")
    feats, info = stimme_merkmale(stimme_aufnehmen())
    q_ = stimme_qualitaet(info)
    if q_:
        M99D["enroll"].pop(nr, None)
        return {"ok": False, "error": q_, "info": info}
    M99D["enroll"][nr] = feats
    return {"ok": True, "nr": nr, "info": info, "aufnahmen": sorted(M99D["enroll"].keys())}


def _m99d_pin_ok(pin):
    ok, err, wait = m92_verify(pin)
    if not ok:
        raise ValueError("PIN: " + (err or "falsch"))


def m99d_aktivieren(d):
    _m99d_pin_ok(d.get("pin"))
    prof = stimme_lernen(dict(M99D["enroll"]))
    satz = str(d.get("satz") or M99D_SATZ).strip()[:80] or M99D_SATZ
    prof["satz"] = satz                       # v2.4.9: the sentence is secret - stored only inside the encrypted profile
    x("DELETE FROM settings WHERE k='m99d_satz'")
    if d.get("strenge") in M99D_STRENGE:
        set_setting("m99d_strenge", d["strenge"])
    _m99d_profil_speichern(prof)
    first = not get_settings().get("m99d_aktiv")
    code = _m99d_notfall_neu() if (first or d.get("neuer_code") or not get_settings().get("m99d_notfall")) else ""
    set_setting("m99d_aktiv", True)
    M99D["enroll"].clear()
    return dict(m99d_status(), notfall_code=code)


def m99d_test(d):
    prof = _m99d_profil_laden()
    if not prof or (not prof.get("v2") and len(M99D["enroll"]) >= M99D_N):
        prof = stimme_lernen(dict(M99D["enroll"]))
    feats, info = stimme_merkmale(stimme_aufnehmen())
    q_ = stimme_qualitaet(info)
    if q_:
        return {"ok": False, "error": q_, "info": info}
    ok, score, sch = stimme_vergleich(feats, prof, d.get("strenge"))
    return {"ok": True, "erkannt": ok, "score": score, "schwelle": sch, "info": info}


def m99d_einstellen(d):
    if d.get("strenge") in M99D_STRENGE:
        set_setting("m99d_strenge", d["strenge"])
    if "sek" in d:
        try:
            set_setting("m99d_sek", max(2.5, min(8.0, float(d["sek"]))))
        except Exception:
            pass
    if d.get("satz") and not _m99d_cfg()["aktiv"]:
        set_setting("m99d_satz", str(d["satz"]).strip()[:80])
    for k in ("ansage", "toene"):
        if k in d:
            set_setting("m99d_" + k, bool(d[k]))
    return m99d_status()


def m99d_notfall(d):
    _m99d_pin_ok(d.get("pin"))
    return dict(m99d_status(), notfall_code=_m99d_notfall_neu())


def m99d_aus(d):
    _m99d_pin_ok(d.get("pin"))
    set_setting("m99d_aktiv", False)
    x("DELETE FROM settings WHERE k IN ('m99d_profil_enc', 'm99d_notfall')")
    M99D["profil"] = None
    return m99d_status()


def m99d_verwerfen(d):
    M99D["enroll"].clear()
    return m99d_status()


HOOK_GET["/api/m99d/status"] = lambda h, qs: h._send(200, m99d_status())
HOOK_POST["/api/m99d/aufnahme"] = _wb_r(m99d_aufnahme)
HOOK_POST["/api/m99d/aktivieren"] = _wb_r(m99d_aktivieren)
HOOK_POST["/api/m99d/test"] = _wb_r(m99d_test)
HOOK_POST["/api/m99d/einstellen"] = _wb_r(m99d_einstellen)
HOOK_POST["/api/m99d/notfall"] = _wb_r(m99d_notfall)
HOOK_POST["/api/m99d/aus"] = _wb_r(m99d_aus)
HOOK_POST["/api/m99d/verwerfen"] = _wb_r(m99d_verwerfen)


def _m99d_boot(d):
    st = d.get("settings") or {}
    for k in ("m99d_profil_enc", "m99d_notfall", "m99d_letzte"):
        st.pop(k, None)
    d["m99d"] = {"aktiv": _m99d_cfg()["aktiv"]}


HOOK_BOOT.append(_m99d_boot)


def _m99d_selftest():
    err = []
    try:
        def ton(f0, formants, dur=1.2, sr=M99D_SR):
            out = []
            for i in range(int(dur * sr)):
                t = i / sr
                seg = min(len(formants) - 1, int(t / dur * len(formants)))
                v = sum(math.sin(2 * math.pi * f0 * h * t) / h * (2.0 if any(abs(f0 * h - fm) < 160 for fm in formants[seg]) else 0.3)
                        for h in range(1, 12))
                out.append(int(3500 * v))
            return [0] * 3000 + out + [0] * 3000
        a = stimme_merkmale(ton(120, [(700, 1200), (300, 2300), (500, 900)]))[0]
        b = stimme_merkmale(ton(122, [(690, 1180), (310, 2280), (510, 920)]))[0]
        c = stimme_merkmale(ton(220, [(300, 2300), (700, 1200), (300, 900)]))[0]
        if not a or not b or not c:
            err.append("m99d: keine Merkmale")
        elif not stimme_abstand(a, b) < stimme_abstand(a, c):
            err.append("m99d: Vergleich trennt nicht")
        if "id=\"vbox\"" not in M92_PAGE or "vstart(r)" not in M92_PAGE or "r.satz" in M92_PAGE:
            err.append("m99d: Sperrseite ohne Sprachschritt")
    except Exception as e:
        err.append(f"m99d Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m99d_selftest)
