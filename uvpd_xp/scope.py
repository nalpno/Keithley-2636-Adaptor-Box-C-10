# -*- coding: utf-8 -*-
"""Osiloskop CSV dosyalarindan darbe (pulse) tepkisi analizi - saf Python.

Modern surumdeki (uvpd/scope.py) analizin numpy GEREKTIRMEYEN karsiligi;
algoritmalar ve formuller aynidir.

Deney duzeni:
    Keithley 3390 kare dalga --> UV lamba surucusu (ve osiloskop CH1)
    Fotodedektor --> Thorlabs AMP120 (akim -> gerilim) --> osiloskop CH2

Akim I = V / G (AMP120: G = 1e5 V/A; osiloskop girisi 50 ohm ise AMP120'nin
50 ohm cikis direnci yuzunden etkin kazanc yariya iner).
"""

import bisect
import cmath
import io
import math
import re
from collections import OrderedDict

from .analysis import Q_E, isfinite, median, percentile, photon_energy_ev

NAN = float("nan")
INF = float("inf")

AMP120_GAIN_V_PER_A = 1.0e5      # Thorlabs AMP120, yuksek empedansli yuk
AMP120_RISE_S = 3.5e-6           # 0.35 / 100 kHz (katalog: < 3 us)
AMP120_BANDWIDTH_HZ = 1.0e5
AMP120_MAX_INPUT_A = 20e-6       # +/- 20 uA


# ============================================================================
# Kucuk yardimcilar
# ============================================================================
def fmt_si(value, unit="", digits=4):
    """3.52e-6, 's' -> '3.52 us' (XP konsolu/Tk icin ASCII 'u')."""
    if value is None or not isfinite(value):
        return "-"
    if value == 0:
        return ("0 " + unit).strip()
    prefixes = [(1e-12, "p"), (1e-9, "n"), (1e-6, "u"), (1e-3, "m"), (1.0, ""),
                (1e3, "k"), (1e6, "M")]
    mag = abs(value)
    scale, pre = prefixes[0]
    for s, p in prefixes:
        if mag >= s * 0.9995:
            scale, pre = s, p
    text = ("{0:." + str(digits) + "g}").format(value / scale)
    return (text + " " + pre + unit).strip()


def mean(values):
    return sum(values) / float(len(values)) if values else NAN


def stdev(values):
    """Orneklem standart sapmasi (ddof=1)."""
    n = len(values)
    if n < 2:
        return NAN
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def nan_stats(values):
    """(ortalama, std, N) - sonlu olmayan degerler atlanir."""
    v = [x for x in values if isfinite(x)]
    if not v:
        return NAN, NAN, 0
    return mean(v), (stdev(v) if len(v) > 1 else 0.0), len(v)


def moving_average(y, n):
    """Kenarlari tekrarlanarak dolgulanan merkezli hareketli ortalama."""
    n = int(n)
    if n <= 1 or len(y) < n:
        return [float(v) for v in y]
    pad_l, pad_r = n // 2, n - 1 - n // 2
    yp = [y[0]] * pad_l + list(y) + [y[-1]] * pad_r
    out = []
    s = sum(yp[:n])
    out.append(s / n)
    for k in range(n, len(yp)):
        s += yp[k] - yp[k - n]
        out.append(s / n)
    return out


def median_filter(y, n=5):
    n = int(n) | 1
    if n <= 1 or len(y) < n:
        return [float(v) for v in y]
    h = n // 2
    yp = [y[0]] * h + list(y) + [y[-1]] * h
    return [sorted(yp[k:k + n])[h] for k in range(len(y))]


def interleave_offset(y):
    """Cift/tek orneklerin sabit ofsetini (araya-girmeli ADC hatasi) bulur."""
    n = len(y)
    if n < 20:
        return 0.0
    a = median([y[k + 1] - y[k] for k in range(0, n - 1, 2)])
    b = median([y[k] - y[k + 1] for k in range(1, n - 1, 2)])
    if a == 0 or b == 0 or (a > 0) != (b > 0):
        return 0.0
    sign = 1.0 if a > 0 else -1.0
    return sign * min(abs(a), abs(b))


def remove_interleave(y, offset):
    if not offset:
        return [float(v) for v in y]
    h = offset / 2.0
    return [(v - h) if (k % 2) else (v + h) for k, v in enumerate(y)]


def channel_stats(y):
    """Osiloskobun Measure menusundeki gerilim olcumlerinin karsiligi."""
    vmax, vmin = max(y), min(y)
    mid = 0.5 * (vmax + vmin)

    def mode(vals):
        if not vals:
            return NAN
        counts = {}
        for v in vals:
            key = round(v, 12)
            counts[key] = counts.get(key, 0) + 1
        if len(counts) <= max(64, len(vals) // 20):          # nicemlenmis veri
            # numpy.unique + argmax: esit sayida en kucuk deger secilir
            top = max(counts.values())
            return min(k for k, c in counts.items() if c == top)
        lo, hi = min(vals), max(vals)
        if hi == lo:
            return lo
        bins = [0] * 100
        w = (hi - lo) / 100.0
        for v in vals:
            k = min(int((v - lo) / w), 99)
            bins[k] += 1
        k = bins.index(max(bins))
        return lo + (k + 0.5) * w

    top = mode([v for v in y if v >= mid])
    base = mode([v for v in y if v < mid])
    avg = mean(y)
    return {"max": vmax, "min": vmin, "pkpk": vmax - vmin,
            "high": top, "low": base, "amp": top - base,
            "avg": avg, "rms": math.sqrt(sum(v * v for v in y) / len(y)),
            "ac_rms": math.sqrt(sum((v - avg) ** 2 for v in y) / len(y))}


# ============================================================================
# CSV okuma
# ============================================================================
_PREFIX = {"k": 1e3, "m": 1e-3, "u": 1e-6, u"\u00b5": 1e-6, u"\u03bc": 1e-6,
           "n": 1e-9, "p": 1e-12}
_BASE_UNITS = {"volt": "V", "volts": "V", "v": "V",
               "second": "s", "seconds": "s", "sec": "s", "s": "s",
               "amp": "A", "ampere": "A", "a": "A"}
_NAME_UNIT = re.compile(r"^(.*?)\s*[\(\[]([^\)\]]*)[\)\]]\s*$")


def _unit_scale(unit):
    u = unit.strip().strip("()[]").strip()
    if u.lower() in _BASE_UNITS:
        return 1.0, _BASE_UNITS[u.lower()]
    if len(u) >= 2 and u[0] in _PREFIX and u[1:] in ("V", "s", "A"):
        return _PREFIX[u[0]], u[1:]
    return 1.0, u


def _split(line, delim):
    return [c.strip().strip('"').strip() for c in line.split(delim)]


def _is_number(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


def _to_float(text):
    try:
        return float(text)
    except ValueError:
        return NAN


class ScopeTrace(object):
    """Osiloskoptan okunan kayit: ortak zaman ekseni + kanallar (SI birimde)."""

    def __init__(self, t, channels, units=None, path="", notes=None):
        self.t = [float(v) for v in t]
        self.channels = OrderedDict((k, [float(v) for v in vals])
                                    for k, vals in channels.items())
        self.units = dict(units or {})
        self.path = path
        self.notes = list(notes or [])

    @property
    def names(self):
        return list(self.channels.keys())

    @property
    def dt(self):
        if len(self.t) < 2:
            return NAN
        return median([self.t[k + 1] - self.t[k] for k in range(len(self.t) - 1)])

    @property
    def duration(self):
        return self.t[-1] - self.t[0] if self.t else 0.0

    def channel(self, name):
        if name not in self.channels:
            raise ValueError("'{0}' kanali dosyada yok. Mevcut kanallar: {1}".format(
                name, ", ".join(self.names)))
        return self.channels[name]

    def summary(self):
        return "{0} nokta, ornekleme araligi {1}, kayit suresi {2}, kanallar: {3}".format(
            len(self.t), fmt_si(self.dt, "s"), fmt_si(self.duration, "s"), ", ".join(self.names))


def parse_scope_text(text, path=""):
    """Osiloskop CSV metnini okur (Rigol DS1000Z/DS2000/DS3100/DS4000 vb.)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("Dosya bos.")
    delim = max((",", ";", "\t"), key=lines[0].count)
    if lines[0].count(delim) == 0:
        raise ValueError("Sutun ayirici (virgul / noktali virgul / sekme) bulunamadi.")

    header_rows = []
    start = None
    for k, ln in enumerate(lines[:60]):
        cells = [c for c in _split(ln, delim) if c != ""]
        if len(cells) >= 2 and all(_is_number(c) for c in cells):
            start = k
            break
        header_rows.append(_split(ln, delim))
    if start is None:
        raise ValueError("Sayisal veri satiri bulunamadi - bu bir osiloskop CSV'si mi?")

    rows = []
    ncol = 0
    for ln in lines[start:]:
        cells = ln.split(delim)
        row = [_to_float(c.strip().strip('"')) if c.strip() else NAN for c in cells]
        rows.append(row)
        if len(row) > ncol:
            ncol = len(row)

    names = list(header_rows[0]) if header_rows else []
    names += [""] * (ncol - len(names))
    units = list(header_rows[1]) if len(header_rows) > 1 else []
    units += [""] * (max(ncol, len(names)) - len(units))
    for k, nm in enumerate(names):
        m = _NAME_UNIT.match(nm)
        if m:
            names[k] = m.group(1).strip()
            if not units[k] or _is_number(units[k]):
                units[k] = m.group(2)

    notes = []
    lower = [n.lower() for n in names]
    t_start = t_inc = None
    if "start" in lower and "increment" in lower and len(header_rows) > 1:
        try:
            t_start = float(header_rows[1][lower.index("start")])
            t_inc = float(header_rows[1][lower.index("increment")])
        except (ValueError, IndexError):
            t_start = t_inc = None

    def col(k):
        return [r[k] if k < len(r) else NAN for r in rows]

    x = col(0)
    if t_inc is not None:
        t = [t_start + v * t_inc for v in x]
        notes.append("Zaman ekseni Start/Increment'ten uretildi (adim {0}).".format(
            fmt_si(t_inc, "s")))
    else:
        scale, base = _unit_scale(units[0])
        if base not in ("s", ""):
            notes.append("Ilk sutun birimi '{0}' - zaman olarak kabul edildi.".format(units[0]))
        t = [v * scale for v in x]

    channels = OrderedDict()
    ch_units = {}
    for k in range(1, ncol):
        if k < len(lower) and lower[k] in ("start", "increment"):
            continue
        c = col(k)
        if not any(isfinite(v) for v in c):
            continue
        name = names[k] or "Sutun{0}".format(k + 1)
        scale, base = _unit_scale(units[k] if k < len(units) else "")
        channels[name] = [v * scale for v in c]
        ch_units[name] = base or "V"
    if not channels:
        raise ValueError("Dosyada kanal verisi bulunamadi.")

    good = [isfinite(t[i]) and all(isfinite(c[i]) for c in channels.values())
            for i in range(len(t))]
    ngood = sum(good)
    if ngood < 10:
        raise ValueError("Dosyada yeterli sayisal veri yok.")
    if ngood < len(t):
        notes.append("{0} eksik/bozuk satir atlandi.".format(len(t) - ngood))
        t = [v for v, g in zip(t, good) if g]
        channels = OrderedDict((k, [v for v, g in zip(c, good) if g])
                               for k, c in channels.items())
    return ScopeTrace(t, channels, ch_units, path, notes)


def load_scope_csv(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_scope_text(fh.read(), path)


# ============================================================================
# Kenar bulma ve pencereler
# ============================================================================
def detect_edges(t, y, median_n=5, hysteresis=(0.3, 0.7)):
    """Kare dalganin yukselen ve dusen kenar zamanlari (iki liste).

    Median filtre + histerezisli (Schmitt) esik; kenar zamani %50
    seviyesinin gecildigi an (dogrusal interpolasyon).
    """
    yf = median_filter(y, median_n)
    lo, hi = percentile(yf, 2), percentile(yf, 98)
    if not isfinite(hi - lo) or hi - lo <= 0:
        return [], []
    th_lo = lo + hysteresis[0] * (hi - lo)
    th_hi = lo + hysteresis[1] * (hi - lo)
    mid = 0.5 * (lo + hi)

    marks = [1 if v >= th_hi else (-1 if v <= th_lo else 0) for v in yf]
    first = next((m for m in marks if m != 0), 0)
    if first == 0:
        return [], []
    rises, falls = [], []
    state = first
    prev = 0
    n = len(yf)
    for k in range(n):
        m = marks[k]
        if m == 0 or m == state:
            continue
        state = m
        up = state > 0
        # %50 seviyesinin kenardan onceki son gecisi
        j = None
        for i in range(k, prev - 1, -1):
            if (yf[i] < mid) if up else (yf[i] > mid):
                j = i
                break
        if j is None:
            j = k - 1
        j = min(max(j, 0), n - 2)
        y0, y1 = yf[j], yf[j + 1]
        frac = 0.5 if y1 == y0 else min(max((mid - y0) / (y1 - y0), 0.0), 1.0)
        te = t[j] + frac * (t[j + 1] - t[j])
        (rises if up else falls).append(te)
        prev = k
    return rises, falls


def _slice(t, a, b):
    return bisect.bisect_left(t, a), bisect.bisect_left(t, b)


def window_residuals(t, y, a, b):
    """[a, b) araligindaki ortalama ve dogrusal egilimi cikarilmis artiklar."""
    i0, i1 = _slice(t, a, b)
    if i1 - i0 < 3:
        return NAN, []
    tt = [v - t[i0] for v in t[i0:i1]]
    yy = y[i0:i1]
    n = float(len(tt))
    sx, sy = sum(tt), sum(yy)
    sxx = sum(v * v for v in tt)
    sxy = sum(p * q for p, q in zip(tt, yy))
    den = n * sxx - sx * sx
    if den == 0:
        m = sy / n
        return m, [v - m for v in yy]
    slope = (n * sxy - sx * sy) / den
    icpt = (sy - slope * sx) / n
    return sy / n, [q - (slope * p + icpt) for p, q in zip(tt, yy)]


def window(t, y, a, b):
    """(ortalama, egilim cikarilmis gurultu, nokta sayisi)."""
    m, res = window_residuals(t, y, a, b)
    if len(res) < 3:
        return m, NAN, len(res)
    return m, math.sqrt(sum(r * r for r in res) / max(len(res) - 2, 1)), len(res)


def _dft_band(res, dt, f_max):
    n = len(res)
    kmax = n // 2
    if f_max and f_max > 0:
        kmax = min(kmax, int(math.floor(f_max * n * dt + 1e-9)))
    total = 0.0
    for k in range(1, kmax + 1):
        w = cmath.exp(-2j * math.pi * k / n)
        z = 1.0 + 0j
        acc = 0j
        for v in res:
            acc += v * z
            z *= w
        weight = 1.0 if (n % 2 == 0 and k == n // 2) else 2.0
        total += weight * (acc.real * acc.real + acc.imag * acc.imag)
    return total / float(n * n)


def band_power(res, dt, f_max):
    """Artiklarin 0 < f <= f_max bandindaki ortalama gucu (V^2) - Parseval ile.

    numpy.fft.rfft ile ayni sonuc. Cok uzun pencerelerde hiz icin 512
    orneklik bloklarin ortalamasi alinir (Bartlett yontemi).
    """
    n = len(res)
    if n < 4 or not (dt > 0):
        return NAN
    if n <= 1024:
        return _dft_band(res, dt, f_max)
    block = 512
    parts = []
    for s in range(0, n - block + 1, block):
        seg = res[s:s + block]
        m = sum(seg) / float(block)
        parts.append(_dft_band([v - m for v in seg], dt, f_max))
    return mean(parts)


# ============================================================================
# Ustel uydurma
# ============================================================================
class ExpFit(object):
    """Ortalama kenara ustel uydurma: v(t) = C + sum A_k exp(-t/tau_k)."""

    def __init__(self):
        self.tau = NAN
        self.rmse1 = NAN
        self.tau_fast = NAN
        self.tau_slow = NAN
        self.frac_fast = NAN
        self.rmse2 = NAN
        self.t_from = NAN
        self.t_to = NAN
        self.n = 0

    @property
    def f_statistic(self):
        if not (isfinite(self.rmse1) and isfinite(self.rmse2)) or self.n <= 6:
            return NAN
        sse1, sse2 = self.rmse1 ** 2 * self.n, self.rmse2 ** 2 * self.n
        if sse2 <= 0:
            return INF
        return ((sse1 - sse2) / 2.0) / (sse2 / (self.n - 5))

    @property
    def double_significant(self):
        f = self.f_statistic
        return (isfinite(self.rmse2) and (f > 10 or f == INF)
                and self.tau_slow > 3 * self.tau_fast
                and 0.05 < self.frac_fast < 0.95)


def _solve3(a, b):
    """3x3 dogrusal sistem (kismi pivotlu Gauss). Tekil ise None."""
    m = [list(a[i]) + [b[i]] for i in range(3)]
    for c in range(3):
        p = max(range(c, 3), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-300:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(c + 1, 3):
            f = m[r][c] / m[c][c]
            for k in range(c, 4):
                m[r][k] -= f * m[c][k]
    x = [0.0, 0.0, 0.0]
    for r in range(2, -1, -1):
        s = m[r][3] - sum(m[r][k] * x[k] for k in range(r + 1, 3))
        x[r] = s / m[r][r]
    return x


def _logspace(a, b, n):
    la, lb = math.log10(a), math.log10(b)
    return [10.0 ** (la + (lb - la) * k / (n - 1.0)) for k in range(n)]


def fit_exponential(t, v, dt):
    """Tek ve cift ustel uydurma (tau izgarasi + dogrusal en kucuk kareler)."""
    fit = ExpFit()
    pts = [(a, b) for a, b in zip(t, v) if isfinite(a) and isfinite(b)]
    if len(pts) < 8:
        return fit
    # hiz icin en fazla 400 noktaya indir (blok ortalamasi)
    if len(pts) > 400:
        step = int(math.ceil(len(pts) / 400.0))
        pts = [(mean([p[0] for p in pts[k:k + step]]), mean([p[1] for p in pts[k:k + step]]))
               for k in range(0, len(pts), step)]
    x = [p[0] - pts[0][0] for p in pts]
    vv = [p[1] for p in pts]
    span = x[-1]
    if span <= 0:
        return fit
    n = len(x)
    fit.t_from, fit.t_to, fit.n = pts[0][0], pts[-1][0], n
    taus = _logspace(max(dt, span / 1000.0) * 0.3, span * 5.0, 160)
    exps = [[math.exp(-xi / tau) for xi in x] for tau in taus]
    sv = sum(vv)
    svv = sum(q * q for q in vv)
    se = [sum(e) for e in exps]
    see = [sum(q * q for q in e) for e in exps]
    sev = [sum(p * q for p, q in zip(e, vv)) for e in exps]

    best = None
    for i, tau in enumerate(taus):
        den = n * see[i] - se[i] * se[i]
        if den == 0:
            continue
        a = (n * sev[i] - se[i] * sv) / den
        c = (sv - a * se[i]) / n
        sse = max(svv - a * sev[i] - c * sv, 0.0)
        rmse = math.sqrt(sse / n)
        if best is None or rmse < best[0]:
            best = (rmse, tau)
    if best is None:
        return fit
    fit.rmse1, fit.tau = best

    best2 = None
    sub = list(range(0, len(taus), 3))
    for i in sub:
        for j in sub:
            if taus[j] <= 2 * taus[i]:
                continue
            s12 = sum(p * q for p, q in zip(exps[i], exps[j]))
            sol = _solve3([[see[i], s12, se[i]], [s12, see[j], se[j]], [se[i], se[j], n]],
                          [sev[i], sev[j], sv])
            if sol is None:
                continue
            sse = max(svv - sol[0] * sev[i] - sol[1] * sev[j] - sol[2] * sv, 0.0)
            rmse = math.sqrt(sse / n)
            if best2 is None or rmse < best2[0]:
                best2 = (rmse, taus[i], taus[j], sol)
    if best2 is not None:
        rmse, tf, tsl, coef = best2
        a1, a2 = abs(coef[0]), abs(coef[1])
        if (coef[0] > 0) == (coef[1] > 0) and a1 + a2 > 0:
            fit.rmse2, fit.tau_fast, fit.tau_slow = rmse, tf, tsl
            fit.frac_fast = a1 / (a1 + a2)
    return fit


# ============================================================================
# Kenar zamanlamasi
# ============================================================================
class EdgeTiming(object):
    def __init__(self, kind, t_ref, v_before=NAN, v_after=NAN):
        self.kind = kind            # "on" (isik acildi) / "off" (isik kapandi)
        self.t_ref = t_ref          # referans (CH1) kenari
        self.t10 = NAN
        self.t50 = NAN
        self.t90 = NAN
        self.duration = NAN         # %10->%90 (acilis) / %90->%10 (kapanis)
        self.delay = NAN            # t50 - t_ref
        self.v_before = v_before
        self.v_after = v_after


def edge_timing(t, y, t_ref, v0, v1, t_start, t_stop, kind="on"):
    """v0 seviyesinden v1 seviyesine gecisin %10/%50/%90 zamanlari.

    Sinyal (y - v0)/(v1 - v0) ile 0->1 araligina normalize edilir; boylece
    yukselen ve dusen kenar ayni sekilde islenir.
    """
    e = EdgeTiming(kind, t_ref, v0, v1)
    amp = v1 - v0
    if not (isfinite(amp) and amp != 0):
        return e
    i0, i1 = _slice(t, t_start, t_stop)
    if i1 - i0 < 3:
        return e
    tt = t[i0:i1]
    p = [(v - v0) / amp for v in y[i0:i1]]

    def cross(j, level):
        if j <= 0:
            return tt[0]
        a, b = p[j - 1], p[j]
        frac = 0.5 if b == a else min(max((level - a) / (b - a), 0.0), 1.0)
        return tt[j - 1] + frac * (tt[j] - tt[j - 1])

    # %50 gecisi 3 ornekli ortalamada aranir (tek orneklik gurultu sicramasi
    # kenar sanilmasin); gecis zamani yine ham veriden hesaplanir.
    ps = moving_average(p, 3) if len(p) >= 6 else p
    k50 = next((k for k, v in enumerate(ps) if v >= 0.5), None)
    if k50 is None:
        return e
    while k50 > 0 and p[k50 - 1] >= 0.5:
        k50 -= 1
    while k50 < len(p) - 1 and p[k50] < 0.5:
        k50 += 1
    e.t50 = cross(k50, 0.5)
    e.delay = e.t50 - t_ref
    j10 = next((k for k in range(k50, -1, -1) if p[k] <= 0.1), None)
    if j10 is not None:
        e.t10 = cross(j10 + 1, 0.1)
    k90 = next((k for k in range(k50, len(p)) if p[k] >= 0.9), None)
    if k90 is not None:
        e.t90 = cross(k90, 0.9)
    if isfinite(e.t10) and isfinite(e.t90) and e.t90 > e.t10:
        e.duration = e.t90 - e.t10
    return e


# ============================================================================
# Darbe analizi
# ============================================================================
class PulseSettings(object):
    def __init__(self, signal="CH2", reference="CH1", light_on_high=True,
                 gain_v_per_a=AMP120_GAIN_V_PER_A, load_50ohm=False, dc_coupled=False,
                 smooth=1, fix_interleave=True, plateau_fraction=0.3,
                 wavelength_nm=None, optical_power_w=None, area_cm2=None,
                 dark_current_a=None, noise_bandwidth_hz=AMP120_BANDWIDTH_HZ,
                 system_rise_s=0.0):
        self.signal = signal
        self.reference = reference          # None: sinyalin kendisi referans
        self.light_on_high = light_on_high  # lamba referans YUKSEK iken yanar
        self.gain_v_per_a = gain_v_per_a
        self.load_50ohm = load_50ohm        # osiloskop girisi 50 ohm -> kazanc x 0.5
        self.dc_coupled = dc_coupled        # CH2 DC kuplajli, AMP120 sifiri ayarli
        self.smooth = smooth
        self.fix_interleave = fix_interleave
        self.plateau_fraction = plateau_fraction
        self.wavelength_nm = wavelength_nm
        self.optical_power_w = optical_power_w
        self.area_cm2 = area_cm2
        self.dark_current_a = dark_current_a
        self.noise_bandwidth_hz = noise_bandwidth_hz
        self.system_rise_s = system_rise_s

    @property
    def effective_gain(self):
        return self.gain_v_per_a * (0.5 if self.load_50ohm else 1.0)


class AveragedEdge(object):
    def __init__(self, tau, v, count, timing, fit):
        self.tau = tau
        self.v = v
        self.count = count
        self.timing = timing
        self.fit = fit

    @property
    def normalized(self):
        amp = self.timing.v_after - self.timing.v_before
        if not isfinite(amp) or amp == 0:
            return [NAN] * len(self.v)
        return [(q - self.timing.v_before) / amp for q in self.v]


class _Sampler(object):
    """Kayittan herhangi bir zamanda dogrusal interpolasyonla deger okur."""

    def __init__(self, t, y):
        self.t, self.y = t, y
        self.t0, self.t1 = t[0], t[-1]

    def __call__(self, tq):
        if tq < self.t0 or tq > self.t1:
            return NAN
        k = bisect.bisect_left(self.t, tq)
        if k == 0:
            return self.y[0]
        a, b = self.t[k - 1], self.t[k]
        f = 0.0 if b == a else (tq - a) / (b - a)
        return self.y[k - 1] + f * (self.y[k] - self.y[k - 1])


def _arange(a, b, step):
    n = int(math.ceil((b - a) / step - 1e-9))
    return [a + k * step for k in range(max(n, 0))]


def _stack_mean(sampler, centers, tau, min_frac=0.0):
    """Her merkez icin tau izgarasinda ornekleyip ortalar. (ortalama, kullanilan)."""
    sums = [0.0] * len(tau)
    cnts = [0] * len(tau)
    used = 0
    for c in centers:
        seg = [sampler(c + x) for x in tau]
        good = sum(1 for v in seg if isfinite(v))
        if good <= min_frac * len(tau):
            continue
        used += 1
        for k, v in enumerate(seg):
            if isfinite(v):
                sums[k] += v
                cnts[k] += 1
    return [s / c if c else NAN for s, c in zip(sums, cnts)], used


def _average_edge(sampler, centers, pre, post, dt, kind, frac, lead=0.0, guard=0.0):
    """Kenarlari kendi %50 noktalarina hizalayip ortalar (bkz. modern surum)."""
    if not centers or not (pre > 0 and post > 0 and dt > 0):
        return None
    tau = _arange(-lead - pre, -lead + post, dt)
    if len(tau) < 6:
        return None
    avg, used = _stack_mean(sampler, centers, tau, 1.0 / 3.0)
    if not used:
        return None
    pairs = [(a, b) for a, b in zip(tau, avg) if isfinite(b)]
    tau_g = [p[0] for p in pairs]
    v_g = [p[1] for p in pairs]
    v0 = window(tau_g, v_g, -lead - (frac + guard) * pre, -lead - guard * pre)[0]
    v1 = window(tau_g, v_g, -lead + post * (1 - frac - guard), -lead + post * (1 - guard))[0]
    timing = edge_timing(tau_g, v_g, -lead, v0, v1, -lead - 0.1 * pre, -lead + post, kind)
    t_from = timing.t10 if isfinite(timing.t10) else 0.0
    sel = [(a, b) for a, b in zip(tau_g, v_g) if a >= t_from]
    fit = fit_exponential([p[0] for p in sel], [p[1] for p in sel], dt)
    return AveragedEdge(tau_g, v_g, used, timing, fit)


def _level_windows(edges, t0, t1, l_on, l_off, frac, guard=0.0):
    """Her yari-periyodun sonundaki plato penceresi: (durum, a, b)."""
    out = []
    for k, (te, kind) in enumerate(edges):
        before = "off" if kind == "on" else "on"
        length = l_off if before == "off" else l_on
        a, b = te - (frac + guard) * length, te - guard * length
        prev_edge = edges[k - 1][0] if k > 0 else t0
        if a >= max(t0, prev_edge):
            out.append((before, a, b))
    if edges:
        te, kind = edges[-1]
        length = l_on if kind == "on" else l_off
        if te + length <= t1:
            out.append((kind, te + (1 - frac - guard) * length, te + (1 - guard) * length))
    return out


class PulseResult(object):
    def __init__(self, settings, trace, signal, reference, interleave_v):
        self.settings = settings
        self.trace = trace
        self.t = trace.t
        self.signal = signal
        self.reference = reference
        self.interleave_v = interleave_v
        self.on_edges = []
        self.off_edges = []
        self.period = NAN
        self.on_width = NAN
        self.off_width = NAN
        self.v_on = NAN
        self.v_off = NAN
        self.v_on_spread = NAN
        self.v_off_spread = NAN
        self.noise_on_v = NAN
        self.noise_off_v = NAN
        self.noise_on_band_v = NAN
        self.noise_off_band_v = NAN
        self.n_on_levels = 0
        self.n_off_levels = 0
        self.edges = []
        self.avg_rise = None
        self.avg_fall = None
        self.cycle_tau = []
        self.cycle_avg = []
        self.stats_signal = {}
        self.stats_reference = {}
        self.warnings = []

    # ------------------------------------------------------------ zamanlama
    @property
    def frequency(self):
        return 1.0 / self.period if isfinite(self.period) and self.period > 0 else NAN

    @property
    def duty(self):
        return self.on_width / self.period if isfinite(self.period) and self.period > 0 else NAN

    @property
    def n_cycles(self):
        return min(len(self.on_edges), len(self.off_edges))

    def light_spans(self):
        t0, t1 = self.t[0], self.t[-1]
        ev = sorted([(x, 1) for x in self.on_edges] + [(x, 0) for x in self.off_edges])
        spans, start = [], None
        if ev and ev[0][1] == 0:
            start = t0
        for tm, state in ev:
            if state == 1 and start is None:
                start = tm
            elif state == 0 and start is not None:
                spans.append((start, tm))
                start = None
        if start is not None:
            spans.append((start, t1))
        return spans

    def edge_stats(self, kind, attr="duration"):
        return nan_stats([getattr(e, attr) for e in self.edges if e.kind == kind])

    @property
    def rise_time(self):
        if self.avg_rise is not None and isfinite(self.avg_rise.timing.duration):
            return self.avg_rise.timing.duration
        return self.edge_stats("on")[0]

    @property
    def fall_time(self):
        if self.avg_fall is not None and isfinite(self.avg_fall.timing.duration):
            return self.avg_fall.timing.duration
        return self.edge_stats("off")[0]

    def corrected(self, tr):
        ts = self.settings.system_rise_s
        if not ts or not isfinite(tr):
            return tr
        if tr <= ts:
            return NAN
        return math.sqrt(tr * tr - ts * ts)

    @property
    def pulse_width_50(self):
        ons = sorted(e.t50 for e in self.edges if e.kind == "on" and isfinite(e.t50))
        offs = sorted(e.t50 for e in self.edges if e.kind == "off" and isfinite(e.t50))
        widths = []
        for a in ons:
            later = [b for b in offs if b > a]
            if later and later[0] - a < self.period:
                widths.append(later[0] - a)
        return median(widths) if widths else NAN

    # ------------------------------------------------------------ elektriksel
    @property
    def delta_v(self):
        return self.v_on - self.v_off

    @property
    def gain(self):
        return self.settings.effective_gain

    @property
    def photocurrent(self):
        return abs(self.delta_v) / self.gain if self.gain else NAN

    @property
    def photocurrent_spread(self):
        s = math.hypot(self.v_on_spread if isfinite(self.v_on_spread) else 0.0,
                       self.v_off_spread if isfinite(self.v_off_spread) else 0.0)
        return s / self.gain if self.gain else NAN

    @property
    def noise_off_used(self):
        return self.noise_off_band_v if isfinite(self.noise_off_band_v) else self.noise_off_v

    @property
    def noise_current(self):
        return self.noise_off_used / self.gain if self.gain else NAN

    @property
    def snr(self):
        n = self.noise_off_used
        return abs(self.delta_v) / n if isfinite(n) and n > 0 else NAN

    @property
    def responsivity(self):
        p = self.settings.optical_power_w
        return self.photocurrent / p if p else NAN

    @property
    def eqe_percent(self):
        lam = self.settings.wavelength_nm
        if not lam or not isfinite(self.responsivity):
            return NAN
        return self.responsivity * photon_energy_ev(lam) * 100.0

    @property
    def nep_measured(self):
        r = self.responsivity
        return self.noise_current / r if isfinite(r) and r > 0 else NAN

    @property
    def nep_measured_per_rthz(self):
        b = self.settings.noise_bandwidth_hz
        return self.nep_measured / math.sqrt(b) if b and b > 0 else NAN

    @property
    def dstar_measured(self):
        a, b = self.settings.area_cm2, self.settings.noise_bandwidth_hz
        nep = self.nep_measured
        if not (a and b and isfinite(nep) and nep > 0):
            return NAN
        return math.sqrt(a * b) / nep

    @property
    def dstar_shot(self):
        a, idark, r = self.settings.area_cm2, self.settings.dark_current_a, self.responsivity
        if not (a and idark and isfinite(r)):
            return NAN
        return r * math.sqrt(a) / math.sqrt(2 * Q_E * abs(idark))

    @property
    def nep_shot_per_rthz(self):
        idark, r = self.settings.dark_current_a, self.responsivity
        if not (idark and isfinite(r) and r > 0):
            return NAN
        return math.sqrt(2 * Q_E * abs(idark)) / r

    @property
    def i_on(self):
        return self.v_on / self.gain if self.gain else NAN

    @property
    def i_off(self):
        return self.v_off / self.gain if self.gain else NAN

    @property
    def on_off_ratio(self):
        if (self.settings.dc_coupled and self.v_off and isfinite(self.v_off)
                and (self.v_on > 0) == (self.v_off > 0)):
            return abs(self.v_on / self.v_off)
        return NAN

    # ------------------------------------------------------------ rapor
    def report_table(self):
        """(etiket, deger, birim) satirlari. deger: sayi (SI) veya metin.

        Basliklar ('-- ... --', '', '') bicimindedir. Rapor dosyasinda deger
        kolonu saf sayidir (Excel'de dogrudan kullanilir).
        """
        s = self.settings
        tr, tf = self.rise_time, self.fall_time
        tr_c, tf_c = self.corrected(tr), self.corrected(tf)
        tr_use = tr_c if isfinite(tr_c) else tr
        bw = 0.35 / tr_use if isfinite(tr_use) and tr_use > 0 else NAN
        rows = [
            ("-- Dosya --", "", ""),
            ("Dosya", self.trace.path or "-", ""),
            ("Ornek sayisi", float(len(self.t)), ""),
            ("Ornekleme araligi", self.trace.dt, "s"),
            ("Sinyal / referans kanali", "{0} / {1}".format(
                s.signal, s.reference or "(sinyalin kendisi)"), ""),
            ("-- Zamanlama (referans) --", "", ""),
            ("Periyot", self.period, "s"),
            ("Frekans", self.frequency, "Hz"),
            ("Isik acik suresi (+genislik)", self.on_width, "s"),
            ("Isik kapali suresi (-genislik)", self.off_width, "s"),
            ("Doluluk orani (isik acik)", self.duty * 100 if isfinite(self.duty) else NAN, "%"),
            ("Tam cevrim sayisi", float(self.n_cycles), ""),
            ("-- Tepki suresi --", "", ""),
            ("Yukselme suresi 10-90% (cevrim ortalamasi)", tr, "s"),
            ("Dusme suresi 90-10% (cevrim ortalamasi)", tf, "s"),
        ]
        for label, kind in (("Yukselme", "on"), ("Dusme", "off")):
            m, sd, n = self.edge_stats(kind)
            rows += [("{0}, tek tek kenarlar - ortalama".format(label), m, "s"),
                     ("{0}, tek tek kenarlar - std".format(label), sd, "s"),
                     ("{0}, tek tek kenarlar - N".format(label), float(n), "")]
        if s.system_rise_s:
            rows += [
                ("Sistem yukselme suresi (cikarilan)", s.system_rise_s, "s"),
                ("Duzeltilmis yukselme suresi", tr_c if isfinite(tr_c)
                 else "sistem sinirinda (olculemez)", "s" if isfinite(tr_c) else ""),
                ("Duzeltilmis dusme suresi", tf_c if isfinite(tf_c)
                 else "sistem sinirinda (olculemez)", "s" if isfinite(tf_c) else ""),
            ]
        rows += [
            ("Zaman sabiti tau = t_r / 2.2", tr_use / 2.197 if isfinite(tr_use) else NAN, "s"),
            ("-3 dB bant genisligi = 0.35 / t_r", bw, "Hz"),
        ]
        for label, ae in (("Acilis (yukselme)", self.avg_rise), ("Kapanis (dusme)", self.avg_fall)):
            if ae is None or not isfinite(ae.fit.tau):
                continue
            f = ae.fit
            rows.append(("{0}: tek ustel tau".format(label), f.tau, "s"))
            if f.double_significant:
                rows += [("{0}: cift ustel tau_hizli".format(label), f.tau_fast, "s"),
                         ("{0}: cift ustel tau_yavas".format(label), f.tau_slow, "s"),
                         ("{0}: hizli bilesen payi".format(label), f.frac_fast * 100, "%")]
        if s.reference:
            for label, kind in (("acilis", "on"), ("kapanis", "off")):
                m, sd, n = self.edge_stats(kind, "delay")
                rows += [("Gecikme: lamba {0} -> sinyal %50 (ort.)".format(label), m, "s"),
                         ("Gecikme: lamba {0} -> sinyal %50 (std)".format(label), sd, "s")]
        dv_spread = math.hypot(self.v_on_spread if isfinite(self.v_on_spread) else 0.0,
                               self.v_off_spread if isfinite(self.v_off_spread) else 0.0)
        snr = self.snr
        rows += [
            ("Sinyal darbe genisligi (%50)", self.pulse_width_50, "s"),
            ("-- Seviyeler (sinyal kanali) --", "", ""),
            ("V_on (isik acik plato)", self.v_on, "V"),
            ("V_off (isik kapali plato)", self.v_off, "V"),
            ("dV = V_on - V_off", self.delta_v, "V"),
            ("dV cevrimden cevrime degisim (std)", dv_spread, "V"),
            ("Gurultu isik kapali, tam bant (RMS)", self.noise_off_v, "V"),
            ("Gurultu isik acik, tam bant (RMS)", self.noise_on_v, "V"),
            ("Gurultu isik kapali, B icinde (RMS)", self.noise_off_band_v, "V"),
            ("Gurultu isik acik, B icinde (RMS)", self.noise_on_band_v, "V"),
            ("SNR = dV / karanlik gurultu (B icinde)", snr, ""),
            ("SNR (dB)", 20 * math.log10(snr) if isfinite(snr) and snr > 0 else NAN, "dB"),
        ]
        if self.interleave_v:
            rows.append(("ADC cift/tek ornek ofseti (duzeltildi)", self.interleave_v, "V"))
        rows += [
            ("-- Akim (I = V / G) --", "", ""),
            ("Etkin transempedans kazanci G" + (" (50 ohm yuk: x0.5)" if s.load_50ohm else ""),
             self.gain, "V/A"),
            ("Fotoakim I_ph = |dV| / G", self.photocurrent, "A"),
            ("Fotoakim cevrim degisimi (std)", self.photocurrent_spread, "A"),
            ("Karanlik gurultu akimi (RMS, B icinde)", self.noise_current, "A"),
        ]
        if s.dc_coupled:
            rows += [("I_on (isik acik)", self.i_on, "A"),
                     ("I_off (karanlik)", self.i_off, "A"),
                     ("Ac/kapa orani I_on / I_off", self.on_off_ratio, "")]
        else:
            rows.append(("I_on / I_off, karanlik akim",
                         "AC kuplajda hesaplanamaz (DC seviye yok)", ""))
        rows += [
            ("-- Fotodedektor --", "", ""),
            ("Dalga boyu", s.wavelength_nm if s.wavelength_nm else NAN, "nm"),
            ("Optik guc", s.optical_power_w if s.optical_power_w else NAN, "W"),
            ("Aktif alan", s.area_cm2 if s.area_cm2 else NAN, "cm2"),
            ("Duyarlilik R = I_ph / P", self.responsivity, "A/W"),
            ("EQE", self.eqe_percent, "%"),
            ("Gurultu bant genisligi B", s.noise_bandwidth_hz, "Hz"),
            ("NEP (olculen gurultu, B icinde)", self.nep_measured, "W"),
            ("NEP (olculen, /sqrt(Hz))", self.nep_measured_per_rthz, "W/Hz^0.5"),
            ("D* (olculen gurultu)", self.dstar_measured, "Jones"),
        ]
        if s.dark_current_a:
            rows += [("Karanlik akim (girilen)", s.dark_current_a, "A"),
                     ("D* (shot gurultu, karanlik akimdan)", self.dstar_shot, "Jones"),
                     ("NEP (shot, /sqrt(Hz))", self.nep_shot_per_rthz, "W/Hz^0.5")]
        st = self.stats_signal
        if st:
            rows += [("-- Osiloskop Measure karsiligi (ham sinyal) --", "", ""),
                     ("Vpp", st["pkpk"], "V"), ("Vmax", st["max"], "V"),
                     ("Vmin", st["min"], "V"), ("Vtop (High)", st["high"], "V"),
                     ("Vbase (Low)", st["low"], "V"), ("Vamp", st["amp"], "V"),
                     ("Vavg", st["avg"], "V"), ("Vrms", st["rms"], "V")]
        return rows

    def report_rows(self):
        """Ekrandaki tablo icin (etiket, okunakli deger) satirlari."""
        si = ("s", "V", "A", "Hz", "W")
        out = []
        for label, val, unit in self.report_table():
            if isinstance(val, str):
                out.append((label, val))
            elif not isfinite(val):
                out.append((label, "-"))
            elif label.endswith(" - N") or label in ("Ornek sayisi", "Tam cevrim sayisi"):
                out.append((label, str(int(val))))
            elif unit in si:
                out.append((label, fmt_si(val, unit)))
            else:
                out.append((label, ("{0:.4g} {1}".format(val, unit)).strip()))
        return out

    def edges_table(self):
        head = ["kenar", "tur", "t_ref_s", "t10_s", "t50_s", "t90_s",
                "sure_10_90_s", "gecikme_s", "V_once_V", "V_sonra_V"]
        rows = []
        for k, e in enumerate(sorted(self.edges, key=lambda x: x.t_ref)):
            rows.append([k + 1, e.kind, e.t_ref, e.t10, e.t50, e.t90,
                         e.duration, e.delay, e.v_before, e.v_after])
        return head, rows


def analyze_pulses(trace, settings):
    """Kare dalgayla surulen lamba altinda alinmis osiloskop kaydini analiz eder."""
    s = settings
    t = trace.t
    raw = trace.channel(s.signal)
    ref_raw = trace.channel(s.reference) if s.reference else None

    off = interleave_offset(raw) if s.fix_interleave else 0.0
    y = moving_average(remove_interleave(raw, off), s.smooth)

    res = PulseResult(s, trace, y, ref_raw, off)
    res.stats_signal = channel_stats(raw)
    if ref_raw is not None:
        res.stats_reference = channel_stats(ref_raw)

    # --------------------------------------------------------- kenarlar
    if ref_raw is not None:
        r = remove_interleave(ref_raw, interleave_offset(ref_raw) if s.fix_interleave else 0.0)
    else:
        r = moving_average(y, max(3, s.smooth))
    rises, falls = detect_edges(t, r)
    on_e, off_e = (rises, falls) if s.light_on_high else (falls, rises)
    res.on_edges, res.off_edges = on_e, off_e
    if not on_e or not off_e:
        res.warnings.append(
            "Referans kanalda kare dalga kenari bulunamadi. Kanal secimini "
            "kontrol edin veya kayda en az bir tam periyot sigdirin.")
        return res

    # --------------------------------------------------------- periyot ve genislik
    on_w = [min(b for b in off_e if b > a) - a for a in on_e if any(b > a for b in off_e)]
    off_w = [min(b for b in on_e if b > a) - a for a in off_e if any(b > a for b in on_e)]
    per = [on_e[k + 1] - on_e[k] for k in range(len(on_e) - 1)]
    per += [off_e[k + 1] - off_e[k] for k in range(len(off_e) - 1)]
    res.on_width = median(on_w) if on_w else NAN
    res.off_width = median(off_w) if off_w else NAN
    if per:
        res.period = median(per)
    elif isfinite(res.on_width) and isfinite(res.off_width):
        res.period = res.on_width + res.off_width
    if not isfinite(res.on_width) and isfinite(res.period):
        res.on_width = res.period - res.off_width
    if not isfinite(res.off_width) and isfinite(res.period):
        res.off_width = res.period - res.on_width
    l_on, l_off = res.on_width, res.off_width
    if not (isfinite(l_on) and isfinite(l_off) and l_on > 0 and l_off > 0):
        res.warnings.append("Isik acik/kapali sureleri belirlenemedi.")
        return res
    if res.n_cycles < 3:
        res.warnings.append(
            "Kayitta yalnizca {0} tam cevrim var; ortalamalar icin osiloskopta "
            "daha fazla periyot kaydedin.".format(res.n_cycles))

    # --------------------------------------------------------- plato seviyeleri
    frac = min(max(float(s.plateau_fraction), 0.05), 0.9)
    edges = sorted([(x, "on") for x in on_e] + [(x, "off") for x in off_e])
    # referans yoksa kenar sinyalin kendi %50 noktasidir; plato pencereleri
    # gecisin ilk yarisini icermesin diye kenardan biraz once biter
    guard = 0.1 if ref_raw is None else 0.0
    wins = _level_windows(edges, t[0], t[-1], l_on, l_off, frac, guard)
    dt = trace.dt
    band = s.noise_bandwidth_hz if s.noise_bandwidth_hz and s.noise_bandwidth_hz > 0 else 0.0
    lv = {"on": [], "off": []}
    nz = {"on": [0.0, 0, 0.0, 0], "off": [0.0, 0, 0.0, 0]}   # sum r2, sum(n-2), sum n*P_B, sum n
    for state, a, b in wins:
        m, rr = window_residuals(t, y, a, b)
        if isfinite(m) and len(rr) >= 3:
            lv[state].append(m)
            nz[state][0] += sum(v * v for v in rr)
            nz[state][1] += max(len(rr) - 2, 1)
            if band:
                nz[state][2] += len(rr) * band_power(rr, dt, band)
                nz[state][3] += len(rr)
    for state in ("on", "off"):
        vals = lv[state]
        level = median(vals) if vals else NAN
        spread = stdev(vals) if len(vals) > 1 else NAN
        noise = math.sqrt(nz[state][0] / nz[state][1]) if nz[state][1] else NAN
        nb = math.sqrt(nz[state][2] / nz[state][3]) if band and nz[state][3] else NAN
        if state == "on":
            res.v_on, res.v_on_spread, res.noise_on_v, res.n_on_levels = level, spread, noise, len(vals)
            res.noise_on_band_v = nb
        else:
            res.v_off, res.v_off_spread, res.noise_off_v, res.n_off_levels = level, spread, noise, len(vals)
            res.noise_off_band_v = nb

    # --------------------------------------------------------- tek tek kenarlar
    t0, t1 = t[0], t[-1]
    for k, (te, kind) in enumerate(edges):
        l_prev = l_off if kind == "on" else l_on
        l_next = l_on if kind == "on" else l_off
        v0 = window(t, y, te - (frac + guard) * l_prev, te - guard * l_prev)[0]
        nxt = edges[k + 1][0] if k + 1 < len(edges) else te + l_next
        if nxt > t1:
            continue
        v1 = window(t, y, nxt - (frac + guard) * l_next, nxt - guard * l_next)[0]
        start = max(te - 0.1 * l_prev, t0)
        res.edges.append(edge_timing(t, y, te, v0, v1, start, nxt, kind))

    # --------------------------------------------------------- cevrim ortalamasi
    sampler = _Sampler(t, y)

    def centers(kind, ref_edges):
        ok = [e for e in res.edges if e.kind == kind and isfinite(e.t50)]
        if not ok:
            return list(ref_edges), 0.0
        return [e.t50 for e in ok], median([e.delay for e in ok])

    c_on, lead_on = centers("on", on_e)
    c_off, lead_off = centers("off", off_e)
    res.avg_rise = _average_edge(sampler, c_on, l_off, l_on, dt, "on", frac, lead_on, guard)
    res.avg_fall = _average_edge(sampler, c_off, l_on, l_off, dt, "off", frac, lead_off, guard)
    if isfinite(res.period) and on_e and dt > 0:
        tau = _arange(-0.5 * l_off, res.period - 0.5 * l_off, dt)
        res.cycle_tau = tau
        res.cycle_avg = _stack_mean(sampler, on_e, tau)[0]

    # --------------------------------------------------------- uyarilar
    tr, tf = res.rise_time, res.fall_time
    if isfinite(res.delta_v) and res.delta_v < 0:
        res.warnings.append(
            "Isik acikken sinyal DUSUYOR (ters kutup). Hesaplar |dV| ile yapildi; "
            "lamba referans dusukken yaniyorsa 'Lamba referans YUKSEK iken yanar' "
            "secimini kaldirin.")
    for name, val in (("Yukselme", tr), ("Dusme", tf)):
        if isfinite(val) and isfinite(dt) and val < 3 * dt:
            res.warnings.append(
                "{0} suresi ({1}) yalnizca ~{2:.1f} ornek; cozunurluk yetersiz. "
                "Osiloskopta zaman olcegini kucultun (kenari buyutun) ve yeniden "
                "kaydedin.".format(name, fmt_si(val, "s"), val / dt))
    if s.system_rise_s and isfinite(tr) and tr < 1.5 * s.system_rise_s:
        res.warnings.append(
            "Olculen yukselme suresi ({0}) yukseltec/sistem sinirina ({1}) yakin. "
            "Dedektor bundan hizli olabilir; daha genis bantli bir yukseltec veya "
            "daha dusuk kazanc gerekir.".format(fmt_si(tr, "s"), fmt_si(s.system_rise_s, "s")))
    if isfinite(res.snr) and res.snr < 5:
        res.warnings.append("SNR dusuk ({0:.1f}); osiloskopta Average modunu veya "
                            "'Yumusatma' ayarini kullanin.".format(res.snr))
    vmax = max(abs(res.stats_signal["max"]), abs(res.stats_signal["min"]))
    limit = 1.0 if s.load_50ohm else 2.0
    is_amp120 = abs(s.gain_v_per_a - AMP120_GAIN_V_PER_A) < 1
    if is_amp120 and vmax > 0.9 * limit:
        res.warnings.append("Sinyal ({0}) AMP120 cikis sinirina (+/-{1:g} V) yakin - "
                            "doyum olabilir.".format(fmt_si(vmax, "V"), limit))
    if is_amp120 and isfinite(res.photocurrent) and res.photocurrent > AMP120_MAX_INPUT_A:
        res.warnings.append("Fotoakim AMP120 giris sinirini (+/-20 uA) asiyor.")
    return res


# ============================================================================
# Disa aktarma
# ============================================================================
def _num(x):
    if isinstance(x, str):
        return x
    return "{0:.6g}".format(x) if isfinite(x) else ""


def write_report(result, path, title=""):
    """Sekmeyle ayrilmis rapor: Parametre / Deger (saf sayi, SI) / Birim."""
    from datetime import datetime
    with io.open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(u"UV FOTODEDEKTOR DARBE (PULSE) TEPKISI RAPORU\n")
        fh.write(u"Tarih\t{0}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        if title:
            fh.write(u"Numune\t{0}\n".format(title))
        fh.write(u"Duzen\tKeithley 3390 kare dalga -> UV lamba; dedektor -> AMP120 -> osiloskop\n")
        fh.write(u"\nParametre\tDeger\tBirim\n")
        for label, val, unit in result.report_table():
            fh.write(u"{0}\t{1}\t{2}\n".format(label, _num(val), unit))
        if result.warnings:
            fh.write(u"\nUYARILAR\n")
            for w in result.warnings:
                fh.write(u"- {0}\n".format(w))
    return path


def write_edges_csv(result, path):
    head, rows = result.edges_table()
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(u",".join(head) + u"\n")
        for r in rows:
            fh.write(u",".join(x if isinstance(x, str) else
                               ("{0:.10g}".format(x) if isfinite(x) else "nan") for x in r) + u"\n")
    return path


def write_average_csv(result, path):
    g = result.gain or 1.0
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(u"# ortalama darbe, kazanc G = {0:g} V/A, periyot = {1:.10g} s\n".format(
            g, result.period))
        fh.write(u"tau_s,V_avg_V,I_avg_A\n")
        for a, b in zip(result.cycle_tau, result.cycle_avg):
            fh.write(u"{0:.10g},{1:.10g},{2:.10g}\n".format(a, b, b / g))
        for name, ae in (("yukselen", result.avg_rise), ("dusen", result.avg_fall)):
            if ae is None:
                continue
            fh.write(u"\n# ortalama {0} kenar ({1} kenar), normalize 0..1\n".format(name, ae.count))
            fh.write(u"tau_s,V_avg_V,normalize\n")
            for a, b, c in zip(ae.tau, ae.v, ae.normalized):
                fh.write(u"{0:.10g},{1:.10g},{2:.6g}\n".format(a, b, c))
    return path
