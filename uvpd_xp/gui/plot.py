# -*- coding: utf-8 -*-
"""Tk Canvas uzerinde canli grafik (matplotlib GEREKTIRMEZ).

Dogrusal ve logaritmik |I| eksen, cok serili cizim, lejant, isik
pencerelerini golgeleme ve EPS (PostScript) olarak kaydetme destekler.
"""

import math
from collections import OrderedDict

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

LINEAR = "linear"
LOG_ABS = "log"

COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
          "#8c564b", "#17becf", "#e377c2"]


def _finite(x):
    try:
        return math.isfinite(x)
    except TypeError:
        return False


def nice_ticks(lo, hi, target=6):
    """Okunakli (1-2-5) dogrusal eksen isaretleri."""
    span = hi - lo
    if span <= 0 or not _finite(span):
        return [lo]
    raw = span / float(target)
    mag = 10.0 ** math.floor(math.log10(raw))
    r = raw / mag
    if r < 1.5:
        step = 1.0 * mag
    elif r < 3.0:
        step = 2.0 * mag
    elif r < 7.0:
        step = 5.0 * mag
    else:
        step = 10.0 * mag
    first = math.ceil(lo / step) * step
    ticks = []
    t = first
    while t <= hi + step * 1e-9 and len(ticks) < 50:
        ticks.append(0.0 if abs(t) < step * 1e-9 else t)
        t += step
    return ticks


def log_ticks(lmin, lmax):
    """Logaritmik eksen: onluk (decade) isaretleri."""
    n = int(lmax - lmin)
    step = 1
    while n / step > 8:
        step += 1
    return list(range(int(lmin), int(lmax) + 1, step))


def fmt_tick(v):
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 1e4 or a < 1e-3:
        return "{0:.1e}".format(v).replace("e-0", "e-").replace("e+0", "e")
    return "{0:.4g}".format(v)


class CanvasPlot(ttk.Frame):
    MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 72, 16, 30, 46

    def __init__(self, master, xlabel="Gerilim (V)", ylabel="Akim (A)", width=420, height=320):
        ttk.Frame.__init__(self, master)
        self.canvas = tk.Canvas(self, width=width, height=height, bg="white",
                                highlightthickness=1, highlightbackground="#b0b0b0")
        self.canvas.pack(fill="both", expand=True)
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.title = ""
        self.yscale = LINEAR
        self.series = OrderedDict()
        self.spans = []
        self._color_idx = 0
        self._pending = False
        self._font = tkfont.Font(family="Tahoma", size=8)
        self._font_b = tkfont.Font(family="Tahoma", size=9, weight="bold")
        self.canvas.bind("<Configure>", lambda e: self.schedule())

    # ---------------- veri ----------------
    def clear(self):
        self.series = OrderedDict()
        self.spans = []
        self._color_idx = 0
        self.redraw()

    def add_series(self, key, label, color=None, dash=None, marker=False, width=2):
        if color is None:
            color = COLORS[self._color_idx % len(COLORS)]
            self._color_idx += 1
        self.series[key] = {"label": label, "color": color, "dash": dash,
                            "marker": marker, "width": width, "x": [], "y": []}
        self.schedule()
        return self.series[key]

    def append(self, key, x, y):
        s = self.series.get(key)
        if s is None:
            s = self.add_series(key, key)
        s["x"].append(float(x))
        s["y"].append(float(y))
        self.schedule()

    def set_data(self, key, xs, ys):
        s = self.series.get(key)
        if s is None:
            s = self.add_series(key, key)
        s["x"] = [float(v) for v in xs]
        s["y"] = [float(v) for v in ys]
        self.schedule()

    def set_spans(self, spans):
        self.spans = [(float(a), float(b)) for a, b in spans]
        self.schedule()

    def set_labels(self, xlabel=None, ylabel=None, title=None):
        if xlabel is not None:
            self.xlabel = xlabel
        if ylabel is not None:
            self.ylabel = ylabel
        if title is not None:
            self.title = title
        self.schedule()

    def set_yscale(self, mode):
        self.yscale = mode
        self.redraw()

    def series_count(self):
        return len(self.series)

    # ---------------- cizim ----------------
    def schedule(self):
        if not self._pending:
            self._pending = True
            self._after_id = self.after(150, self.redraw)

    def destroy(self):
        aid = getattr(self, "_after_id", None)
        if aid is not None:
            try:
                self.after_cancel(aid)
            except tk.TclError:
                pass
        ttk.Frame.destroy(self)

    def _points(self, s):
        pts = []
        for x, y in zip(s["x"], s["y"]):
            if not (_finite(x) and _finite(y)):
                pts.append(None)
                continue
            if self.yscale == LOG_ABS:
                y = abs(y)
                if y <= 0:
                    pts.append(None)
                    continue
            pts.append((x, y))
        return pts

    def redraw(self):
        self._pending = False
        self._after_id = None
        c = self.canvas
        c.delete("all")
        W = max(c.winfo_width(), int(c["width"]) if c.winfo_width() < 10 else 0)
        H = max(c.winfo_height(), int(c["height"]) if c.winfo_height() < 10 else 0)
        x0, x1 = self.MARGIN_L, W - self.MARGIN_R
        y0, y1 = self.MARGIN_T, H - self.MARGIN_B
        if x1 - x0 < 40 or y1 - y0 < 40:
            return

        all_pts = {}
        xs, ys = [], []
        for key, s in self.series.items():
            pts = self._points(s)
            all_pts[key] = pts
            for p in pts:
                if p is not None:
                    xs.append(p[0])
                    ys.append(p[1])

        if self.title:
            c.create_text((x0 + x1) / 2.0, 14, text=self.title, font=self._font_b)
        self._axis_labels(c, x0, x1, y0, y1)

        if not xs:
            c.create_rectangle(x0, y0, x1, y1, outline="#404040")
            c.create_text((x0 + x1) / 2.0, (y0 + y1) / 2.0, text="Veri yok",
                          fill="#909090", font=self._font)
            return

        xmin, xmax = min(xs), max(xs)
        for a, b in self.spans:
            xmin, xmax = min(xmin, a), max(xmax, b)
        if xmax == xmin:
            d = abs(xmin) * 0.1 or 1.0
            xmin, xmax = xmin - d, xmax + d
        pad = (xmax - xmin) * 0.02
        xmin, xmax = xmin - pad, xmax + pad

        if self.yscale == LOG_ABS:
            lmin = math.floor(math.log10(min(ys)))
            lmax = math.ceil(math.log10(max(ys)))
            if lmax == lmin:
                lmax += 1
            ymin, ymax = 10.0 ** lmin, 10.0 ** lmax

            def fy(y):
                return y1 - (math.log10(y) - lmin) / float(lmax - lmin) * (y1 - y0)
            yticks = [(10.0 ** e, "1e{0}".format(e)) for e in log_ticks(lmin, lmax)]
        else:
            ymin, ymax = min(ys), max(ys)
            if ymax == ymin:
                d = abs(ymin) * 0.1 or 1e-12
                ymin, ymax = ymin - d, ymax + d
            pad = (ymax - ymin) * 0.05
            ymin, ymax = ymin - pad, ymax + pad

            def fy(y):
                return y1 - (y - ymin) / (ymax - ymin) * (y1 - y0)
            yticks = [(t, fmt_tick(t)) for t in nice_ticks(ymin, ymax)]

        def fx(x):
            return x0 + (x - xmin) / (xmax - xmin) * (x1 - x0)

        # isik pencereleri
        for a, b in self.spans:
            c.create_rectangle(max(x0, fx(a)), y0, min(x1, fx(b)), y1,
                               fill="#ece6f7", outline="")

        # izgara + isaretler
        for t in nice_ticks(xmin, xmax):
            px = fx(t)
            c.create_line(px, y0, px, y1, fill="#e4e4e4")
            c.create_line(px, y1, px, y1 + 4, fill="#404040")
            c.create_text(px, y1 + 6, text=fmt_tick(t), anchor="n", font=self._font)
        for val, lab in yticks:
            if not (ymin <= val <= ymax):
                continue
            py = fy(val)
            c.create_line(x0, py, x1, py, fill="#e4e4e4")
            c.create_line(x0 - 4, py, x0, py, fill="#404040")
            c.create_text(x0 - 6, py, text=lab, anchor="e", font=self._font)
        if self.yscale == LINEAR and ymin < 0 < ymax:
            c.create_line(x0, fy(0.0), x1, fy(0.0), fill="#a0a0a0")

        # seriler
        for key, s in self.series.items():
            segs, cur = [], []
            for p in all_pts[key]:
                if p is None:
                    if len(cur) >= 2:
                        segs.append(cur)
                    cur = []
                else:
                    cur.append((fx(p[0]), fy(p[1])))
            if cur:
                segs.append(cur)
            for seg in segs:
                if len(seg) >= 2:
                    coords = [v for xy in seg for v in xy]
                    kw = {"fill": s["color"], "width": s["width"]}
                    if s["dash"]:
                        kw["dash"] = s["dash"]
                    c.create_line(*coords, **kw)
                elif len(seg) == 1:
                    px, py = seg[0]
                    c.create_oval(px - 2, py - 2, px + 2, py + 2, outline=s["color"], fill=s["color"])
            npts = sum(1 for p in all_pts[key] if p is not None)
            if s["marker"] and npts <= 400:
                for p in all_pts[key]:
                    if p is not None:
                        px, py = fx(p[0]), fy(p[1])
                        c.create_rectangle(px - 1.5, py - 1.5, px + 1.5, py + 1.5,
                                           outline=s["color"], fill=s["color"])

        c.create_rectangle(x0, y0, x1, y1, outline="#404040")
        self._legend(c, x0, y0)

    def _axis_labels(self, c, x0, x1, y0, y1):
        c.create_text((x0 + x1) / 2.0, y1 + 30, text=self.xlabel, font=self._font)
        ylab = ("|{0}|".format(self.ylabel) if self.yscale == LOG_ABS else self.ylabel)
        try:
            c.create_text(14, (y0 + y1) / 2.0, text=ylab, angle=90, font=self._font)
        except tk.TclError:
            c.create_text(4, y0 - 12, text=ylab, anchor="w", font=self._font)

    def _legend(self, c, x0, y0):
        items = [(s["label"], s["color"], s["dash"]) for s in self.series.values()
                 if s["x"]]
        if not items:
            return
        lh = 14
        width = max(self._font.measure(t) for t, _, _ in items) + 34
        bx, by = x0 + 8, y0 + 8
        c.create_rectangle(bx, by, bx + width, by + lh * len(items) + 6,
                           fill="white", outline="#c0c0c0")
        for k, (text, color, dash) in enumerate(items):
            yy = by + 10 + k * lh
            kw = {"fill": color, "width": 2}
            if dash:
                kw["dash"] = dash
            c.create_line(bx + 6, yy, bx + 24, yy, **kw)
            c.create_text(bx + 28, yy, text=text, anchor="w", font=self._font)

    def save_postscript(self, path):
        self.redraw()
        self.canvas.postscript(file=path, colormode="color")


class YScaleSelector(ttk.Frame):
    def __init__(self, master, plot, default=LINEAR):
        ttk.Frame.__init__(self, master)
        self.plot = plot
        ttk.Label(self, text="Y ekseni:").pack(side="left")
        self._items = [("Dogrusal", LINEAR), ("Logaritmik |I|", LOG_ABS)]
        self.combo = ttk.Combobox(self, state="readonly", width=16,
                                  values=[t for t, _ in self._items])
        self.combo.pack(side="left", padx=4)
        self.combo.current(1 if default == LOG_ABS else 0)
        plot.yscale = default
        self.combo.bind("<<ComboboxSelected>>",
                        lambda e: plot.set_yscale(self._items[self.combo.current()][1]))
