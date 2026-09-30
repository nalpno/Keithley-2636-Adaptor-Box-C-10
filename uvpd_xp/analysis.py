# -*- coding: utf-8 -*-
"""UV fotodedektor analizi - saf Python (numpy GEREKTIRMEZ).

Formuller modern surumle aynidir:
    I_ph  = I_light - I_dark
    R     = |I_ph| / P_opt                      [A/W]
    EQE   = R * h*c / (q*lambda) = R * E_ph[eV] [x100 -> %]
    D*    = R * sqrt(A) / sqrt(2 q I_dark)       [Jones]  (shot-gurultu sinirli)
    NEP   = sqrt(2 q I_dark) / R                 [W/Hz^0.5]
"""

import math

Q_E = 1.602176634e-19      # C
H_PLANCK = 6.62607015e-34  # J*s
C_LIGHT = 2.99792458e8     # m/s
K_B = 1.380649e-23         # J/K

NAN = float("nan")


def isfinite(x):
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------
# Temel yardimcilar (numpy yerine)
# --------------------------------------------------------------------------
def photon_energy_ev(wavelength_nm):
    """E = h c / lambda  [eV]"""
    return (H_PLANCK * C_LIGHT / (float(wavelength_nm) * 1e-9)) / Q_E


def percentile(values, p):
    """numpy.percentile ile ayni (dogrusal interpolasyon)."""
    a = sorted(values)
    if not a:
        return NAN
    if len(a) == 1:
        return a[0]
    pos = (len(a) - 1) * (float(p) / 100.0)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(a) - 1)
    frac = pos - lo
    return a[lo] + frac * (a[hi] - a[lo])


def median(values):
    return percentile(values, 50)


def moving_average_same(y, k):
    """numpy.convolve(y, ones(k)/k, mode='same') esdegeri."""
    n = len(y)
    k = int(k)
    if k <= 1 or n == 0:
        return list(y)
    off = (k - 1) // 2
    out = []
    for idx in range(n):
        s = 0.0
        for j in range(k):
            m = idx + off - j
            if 0 <= m < n:
                s += y[m]
        out.append(s / k)
    return out


def monotonic_xy(x, y):
    """x'e gore siralar, ayni x degerlerinin y'lerini ortalar."""
    pairs = sorted(zip(x, y), key=lambda p: p[0])
    xs, ys = [], []
    idx = 0
    while idx < len(pairs):
        xv = pairs[idx][0]
        acc, cnt = 0.0, 0
        while idx < len(pairs) and pairs[idx][0] == xv:
            acc += pairs[idx][1]
            cnt += 1
            idx += 1
        xs.append(float(xv))
        ys.append(acc / cnt)
    return xs, ys


def interp(xq, xs, ys):
    """Dogrusal interpolasyon; aralik disi -> NaN. xs artan sirali olmali."""
    n = len(xs)
    if n == 0:
        return NAN
    if xq < xs[0] or xq > xs[-1]:
        return NAN
    if n == 1:
        return ys[0]
    lo, hi = 0, n - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= xq:
            lo = mid
        else:
            hi = mid
    x0, x1 = xs[lo], xs[hi]
    if x1 == x0:
        return ys[lo]
    return ys[lo] + (ys[hi] - ys[lo]) * (xq - x0) / (x1 - x0)


def linspace(a, b, n):
    n = int(n)
    if n <= 1:
        return [float(a)]
    step = (b - a) / float(n - 1)
    return [a + k * step for k in range(n)]


# --------------------------------------------------------------------------
# Karanlik / aydinlik karsilastirmasi
# --------------------------------------------------------------------------
def interpolate_to(ds, grid):
    xs, ys = monotonic_xy(ds.v, ds.i)
    return [interp(g, xs, ys) for g in grid]


def common_voltage_grid(a, b, points=0):
    xa, _ = monotonic_xy(a.v, a.i)
    xb, _ = monotonic_xy(b.v, b.i)
    if not xa or not xb:
        return []
    lo = max(xa[0], xb[0])
    hi = min(xa[-1], xb[-1])
    if hi <= lo:
        return []
    if points and points > 0:
        return linspace(lo, hi, points)
    base = xa if len(xa) >= len(xb) else xb
    grid = [x for x in base if lo <= x <= hi]
    return grid if len(grid) >= 2 else linspace(lo, hi, 101)


class Comparison(object):
    """Iki I-V egrisinin ortak eksende karsilastirmasi."""

    def __init__(self, v, i_dark, i_light, dark_name="karanlik", light_name="isik"):
        self.v = list(v)
        self.i_dark = list(i_dark)
        self.i_light = list(i_light)
        self.i_photo = [l - d for l, d in zip(self.i_light, self.i_dark)]
        self.ratio = []
        for l, d in zip(self.i_light, self.i_dark):
            self.ratio.append(abs(l) / abs(d) if d not in (0.0,) and isfinite(d) else NAN)
        self.dark_name = dark_name
        self.light_name = light_name

    def at(self, bias):
        """Istenen bias'a EN YAKIN ortak noktadaki degerler."""
        if not self.v:
            return {}
        idx = min(range(len(self.v)), key=lambda k: abs(self.v[k] - bias))
        return {
            "bias_V": self.v[idx],
            "i_dark_A": self.i_dark[idx],
            "i_light_A": self.i_light[idx],
            "i_photo_A": self.i_photo[idx],
            "on_off_ratio": self.ratio[idx],
        }


def compare(dark, light, points=0):
    grid = common_voltage_grid(dark, light, points)
    return Comparison(grid, interpolate_to(dark, grid), interpolate_to(light, grid),
                      dark_name=dark.label, light_name=light.label)


def subtract(a, b, points=0):
    grid = common_voltage_grid(a, b, points)
    ia = interpolate_to(a, grid)
    ib = interpolate_to(b, grid)
    return grid, [x - y for x, y in zip(ia, ib)]


# --------------------------------------------------------------------------
# Fotodedektor parametreleri
# --------------------------------------------------------------------------
def _fmt(x, unit=""):
    if not isfinite(x):
        return "-"
    return ("{0:.4g} {1}".format(x, unit)).strip()


class DetectorMetrics(object):
    def __init__(self, bias_v=0.0):
        self.bias_v = bias_v
        self.i_dark = NAN
        self.i_light = NAN
        self.i_photo = NAN
        self.on_off_ratio = NAN
        self.photosensitivity = NAN
        self.responsivity = NAN
        self.eqe_percent = NAN
        self.detectivity = NAN
        self.nep = NAN
        self.gain = NAN
        self.photon_energy_ev = NAN
        self.optical_power_w = NAN
        self.area_cm2 = NAN
        self.wavelength_nm = NAN
        self.warnings = []

    def as_table(self):
        """(etiket, sayi, birim) - rapor/CSV icin (birim ayri kolonda)."""
        return [
            ("Bias gerilimi", self.bias_v, "V"),
            ("Karanlik akim I_dark", self.i_dark, "A"),
            ("Aydinlik akim I_light", self.i_light, "A"),
            ("Fotoakim I_ph = I_light - I_dark", self.i_photo, "A"),
            ("Ac/Kapa orani |I_light/I_dark|", self.on_off_ratio, ""),
            ("Fotoduyarlilik (I_ph/I_dark)", self.photosensitivity, ""),
            ("Dalga boyu", self.wavelength_nm, "nm"),
            ("Foton enerjisi", self.photon_energy_ev, "eV"),
            ("Optik guc", self.optical_power_w, "W"),
            ("Aktif alan", self.area_cm2, "cm2"),
            ("Duyarlilik R", self.responsivity, "A/W"),
            ("EQE", self.eqe_percent, "%"),
            ("Kazanc G", self.gain, ""),
            ("Dedektivite D*", self.detectivity, "Jones"),
            ("NEP", self.nep, "W/Hz^0.5"),
        ]

    def as_rows(self):
        return [(k, _fmt(v, u)) for k, v, u in self.as_table()]


def detector_metrics(i_dark, i_light, wavelength_nm=None, optical_power_w=None,
                     area_cm2=None, bias_v=0.0):
    m = DetectorMetrics(bias_v)
    m.i_dark = float(i_dark)
    m.i_light = float(i_light)
    m.i_photo = m.i_light - m.i_dark
    if m.i_dark != 0 and isfinite(m.i_dark):
        m.on_off_ratio = abs(m.i_light) / abs(m.i_dark)
        m.photosensitivity = (abs(m.i_light) - abs(m.i_dark)) / abs(m.i_dark)
    else:
        m.warnings.append("I_dark = 0, oran hesaplanamadi.")

    if wavelength_nm:
        m.wavelength_nm = float(wavelength_nm)
        m.photon_energy_ev = photon_energy_ev(wavelength_nm)
    if area_cm2:
        m.area_cm2 = float(area_cm2)

    if optical_power_w and optical_power_w > 0:
        m.optical_power_w = float(optical_power_w)
        m.responsivity = abs(m.i_photo) / m.optical_power_w
        if wavelength_nm:
            m.eqe_percent = 100.0 * m.responsivity * m.photon_energy_ev
            m.gain = m.eqe_percent / 100.0
        if area_cm2 and m.i_dark != 0 and isfinite(m.i_dark):
            noise = math.sqrt(2.0 * Q_E * abs(m.i_dark))
            m.detectivity = m.responsivity * math.sqrt(float(area_cm2)) / noise
            m.nep = noise / m.responsivity if m.responsivity else NAN
        elif not area_cm2:
            m.warnings.append("Aktif alan girilmedi; D* hesaplanamadi.")
    else:
        m.warnings.append("Optik guc girilmedi; R, EQE ve D* hesaplanamadi.")
    return m


def metrics_from_comparison(cmp_, bias_v, wavelength_nm=None, optical_power_w=None,
                            area_cm2=None):
    pt = cmp_.at(bias_v)
    if not pt:
        m = DetectorMetrics()
        m.warnings.append("Ortak gerilim araligi bulunamadi.")
        return m
    return detector_metrics(pt["i_dark_A"], pt["i_light_A"], wavelength_nm=wavelength_nm,
                            optical_power_w=optical_power_w, area_cm2=area_cm2,
                            bias_v=pt["bias_V"])


# --------------------------------------------------------------------------
# Diyot parametreleri
# --------------------------------------------------------------------------
def linear_fit(x, y):
    """En kucuk kareler: y = a*x + b -> (a, b)."""
    n = float(len(x))
    sx = sum(x)
    sy = sum(y)
    sxx = sum(v * v for v in x)
    sxy = sum(a * b for a, b in zip(x, y))
    den = n * sxx - sx * sx
    if den == 0:
        return NAN, NAN
    a = (n * sxy - sx * sy) / den
    b = (sy - a * sx) / n
    return a, b


def diode_parameters(v, i, v_min=0.1, v_max=0.5, temperature_k=300.0):
    """ln(I) = ln(I0) + qV/(n k T) egiminden idealite n ve I0."""
    pts = [(vv, ii) for vv, ii in zip(v, i)
           if v_min <= vv <= v_max and ii > 0 and isfinite(ii)]
    out = {"ideality": NAN, "i0": NAN, "points": len(pts)}
    if len(pts) < 3:
        return out
    slope, intercept = linear_fit([p[0] for p in pts], [math.log(p[1]) for p in pts])
    kt_q = K_B * temperature_k / Q_E
    if isfinite(slope) and slope > 0:
        out["ideality"] = 1.0 / (slope * kt_q)
    if isfinite(intercept):
        out["i0"] = math.exp(intercept)
    return out


def rectification_ratio(v, i, bias=1.0):
    xs, ys = monotonic_xy(v, i)
    if len(xs) < 2 or bias > xs[-1] or -bias < xs[0]:
        return NAN
    ip = interp(bias, xs, ys)
    im = interp(-bias, xs, ys)
    return abs(ip) / abs(im) if im else NAN


# --------------------------------------------------------------------------
# Zaman tepkisi
# --------------------------------------------------------------------------
class TransientMetrics(object):
    def __init__(self):
        self.i_off = NAN
        self.i_on = NAN
        self.on_off_ratio = NAN
        self.rise_time_s = NAN
        self.fall_time_s = NAN
        self.n_cycles = 0
        self.warnings = []

    def as_table(self):
        return [
            ("Kapali (karanlik) akim", self.i_off, "A"),
            ("Acik (UV) akim", self.i_on, "A"),
            ("Ac/Kapa orani", self.on_off_ratio, ""),
            ("Yukselme suresi (10-90%)", self.rise_time_s, "s"),
            ("Dusme suresi (90-10%)", self.fall_time_s, "s"),
            ("Algilanan cevrim sayisi", float(self.n_cycles), ""),
        ]

    def as_rows(self):
        rows = [(k, _fmt(v, u)) for k, v, u in self.as_table()]
        rows[-1] = (rows[-1][0], str(self.n_cycles))
        return rows


def light_spans(ds):
    """Meta verideki isik olaylarindan (t, 0/1) golgelenecek araliklari uretir."""
    events = ds.settings.get("light_events") or []
    if not events:
        return []
    t_end = ds.t[-1] if ds.t else 0.0
    spans, start = [], None
    for t, state in sorted(events, key=lambda e: e[0]):
        if int(state) == 1 and start is None:
            start = float(t)
        elif int(state) == 0 and start is not None:
            spans.append((start, float(t)))
            start = None
    if start is not None:
        spans.append((start, t_end))
    return spans


def _interp_cross(t, y, level, k):
    if k <= 0:
        return float(t[0])
    y0, y1 = y[k - 1], y[k]
    if y1 == y0:
        return float(t[k])
    frac = (level - y0) / (y1 - y0)
    return float(t[k - 1] + frac * (t[k] - t[k - 1]))


def _cross_forward(t, y, level, start, above):
    for k in range(start, len(y)):
        if (y[k] >= level) if above else (y[k] <= level):
            return _interp_cross(t, y, level, k)
    return None


def _cross_backward(t, y, level, end, above):
    for k in range(min(end, len(y) - 1), -1, -1):
        if (y[k] >= level) if above else (y[k] <= level):
            return _interp_cross(t, y, level, min(k + 1, len(t) - 1))
    return None


def transient_metrics(t, i, smooth=1):
    """UV ac/kapa cevrimlerinden yukselme/dusme sureleri ve ac/kapa orani."""
    m = TransientMetrics()
    t = [float(x) for x in t]
    y = [abs(float(x)) for x in i]
    if len(t) < 10:
        m.warnings.append("Yeterli nokta yok.")
        return m
    if smooth and smooth > 1:
        y = moving_average_same(y, smooth)

    lo = percentile(y, 10)
    hi = percentile(y, 90)
    m.i_off, m.i_on = lo, hi
    if lo > 0:
        m.on_off_ratio = hi / lo
    if hi - lo <= 0:
        m.warnings.append("Isik ac/kapa gecisi algilanamadi.")
        return m

    mid = lo + 0.5 * (hi - lo)
    above = [v > mid for v in y]
    rise_idx = [k for k in range(len(y) - 1) if not above[k] and above[k + 1]]
    fall_idx = [k for k in range(len(y) - 1) if above[k] and not above[k + 1]]
    m.n_cycles = min(len(rise_idx), len(fall_idx))

    lvl10 = lo + 0.1 * (hi - lo)
    lvl90 = lo + 0.9 * (hi - lo)
    rises, falls = [], []
    for r in rise_idx:
        t10 = _cross_backward(t, y, lvl10, r, above=False)
        t90 = _cross_forward(t, y, lvl90, r, above=True)
        if t10 is not None and t90 is not None and t90 > t10:
            rises.append(t90 - t10)
    for f in fall_idx:
        t90 = _cross_backward(t, y, lvl90, f, above=True)
        t10 = _cross_forward(t, y, lvl10, f, above=False)
        if t10 is not None and t90 is not None and t10 > t90:
            falls.append(t10 - t90)
    if rises:
        m.rise_time_s = median(rises)
    if falls:
        m.fall_time_s = median(falls)
    if not rises and not falls:
        m.warnings.append("Kenar bulunamadi; ornekleme araligini kucultun.")
    return m
