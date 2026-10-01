# -*- coding: utf-8 -*-
"""5 - Osiloskop darbe analizi sekmesi (XP surumu, v2).

Keithley 3390 kare dalgasiyla surulen UV lamba altinda, AMP120 transempedans
yukseltecinden alinan sinyalin osiloskop CSV kaydi yuklenir; tepki suresi,
fotoakim, duyarlilik, EQE, NEP ve D* hesaplanir. Cihaz baglantisi gerekmez.
"""

import os
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, ttk

from .. import scope
from ..analysis import isfinite
from .common import Form, KeyValueTable, ScrollFrame, error, info, warn
from .plot import CanvasPlot

VIEW_WAVE = "wave"
VIEW_WAVE_I = "wave_i"
VIEW_EDGES = "edges"
VIEW_CYCLE = "cycle"
VIEW_PER_EDGE = "per_edge"

NO_REF = "__none__"

DEFAULTS = {
    "gain_v_per_a": scope.AMP120_GAIN_V_PER_A,
    "load_50ohm": False,
    "dc_coupled": False,
    "system_rise_s": scope.AMP120_RISE_S,
    "noise_bandwidth_hz": scope.AMP120_BANDWIDTH_HZ,
    "light_on_high": True,
    "smooth": 1,
    "plateau_fraction": 0.3,
    "fix_interleave": True,
    "dark_current_a": 0.0,
}

MAX_PLOT_POINTS = 3000


def time_unit(span):
    span = abs(span)
    if span < 2e-6:
        return 1e9, "ns"
    if span < 2e-3:
        return 1e6, "us"
    if span < 2.0:
        return 1e3, "ms"
    return 1.0, "s"


def decimate(xs, ys, maxn=MAX_PLOT_POINTS):
    """Cizim icin nokta azaltma: her kovada min ve max korunur (zarf kaybolmaz)."""
    n = len(xs)
    if n <= maxn:
        return list(xs), list(ys)
    b = int(n / (maxn / 2.0)) + 1
    ox, oy = [], []
    for s in range(0, n, b):
        seg = list(range(s, min(s + b, n)))
        good = [k for k in seg if isfinite(ys[k])]
        if not good:
            continue
        kmin = min(good, key=lambda k: ys[k])
        kmax = max(good, key=lambda k: ys[k])
        for k in sorted({kmin, kmax}):
            ox.append(xs[k])
            oy.append(ys[k])
    return ox, oy


def _points_series(xs, ys):
    """Tek tek noktalar: araya NaN konur, cizici her birini nokta olarak cizer."""
    nan = float("nan")
    ox, oy = [], []
    for x, y in zip(xs, ys):
        ox += [x, nan]
        oy += [y, nan]
    return ox, oy


class ScopeTab(ttk.Frame):
    def __init__(self, master, session):
        ttk.Frame.__init__(self, master, padding=6)
        self.session = session
        self.trace = None
        self.result = None
        cfg = dict(DEFAULTS)
        cfg.update(session.settings.get("scope") or {})

        sf = ScrollFrame(self)
        sf.pack(side="left", fill="y", padx=(0, 6))
        left = sf.inner
        right = ttk.Panedwindow(self, orient="vertical")
        right.pack(side="left", fill="both", expand=True)

        # ---------------- 1) dosya ----------------
        f1 = Form(left, "1) Osiloskop kaydi")
        f1.pack(fill="x", pady=(0, 4))
        f1.full(ttk.Button(f1, text="Osiloskop CSV dosyasi ac...", command=self.open_dialog))
        self.file_info = tk.StringVar(self, value="Dosya yuklenmedi.")
        f1.full(ttk.Label(f1, textvariable=self.file_info, wraplength=250, justify="left"))
        self.signal_ch = f1.combo("Sinyal kanali (AMP120)", [], None, width=12)
        self.ref_ch = f1.combo("Referans kanali (lamba)", [], None, width=12)
        self.light_high = f1.check("Lamba referans YUKSEK iken yanar", cfg["light_on_high"])

        # ---------------- 2) yukseltec ----------------
        f2 = Form(left, "2) Yukseltec (Thorlabs AMP120)")
        f2.pack(fill="x", pady=(0, 4))
        self.gain = f2.sci("Kazanc G (V/A)", cfg["gain_v_per_a"])
        self.load50 = f2.check("Osiloskop girisi 50 ohm", cfg["load_50ohm"])
        self.dc_coupled = f2.check("CH2 DC kuplajli, sifir ayarli", cfg["dc_coupled"])
        self.sys_rise = f2.sci("Sistem yukselme suresi (s)", cfg["system_rise_s"])
        self.bandwidth = f2.sci("Gurultu bant genisligi B (Hz)", cfg["noise_bandwidth_hz"])
        f2.full(ttk.Label(
            f2, foreground="#555555", wraplength=250, justify="left",
            text="AMP120: G = 1e5 V/A (1 Mohm giriste). Osiloskop 50 ohm ise "
                 "kutucugu isaretleyin (G yariya iner). Sistem yukselme suresi "
                 "0.35/100 kHz = 3.5 us; olculen sureden karesel cikarilir "
                 "(0 = duzeltme yok). CH2 AC kuplajliysa (ekranda CH2 ~) "
                 "DC kutucugunu bos birakin."))

        # ---------------- 3) isik / dedektor ----------------
        s = session.settings
        f3 = Form(left, "3) Isik ve dedektor")
        f3.pack(fill="x", pady=(0, 4))
        self.wavelength = f3.sci("Dalga boyu (nm)", s.get("wavelength_nm", 365.0))
        self.power = f3.sci("Dedektore dusen guc (W)", s.get("optical_power_w", 2e-6))
        self.area = f3.sci("Aktif alan (cm2)", s.get("area_cm2", 0.04))
        self.dark = f3.sci("Karanlik akim (A, 0=yok)", cfg["dark_current_a"] or 0.0)

        # ---------------- 4) analiz ----------------
        f4 = Form(left, "4) Analiz")
        f4.pack(fill="x", pady=(0, 4))
        self.smooth = f4.spin("Yumusatma (ornek, 1=kapali)", cfg["smooth"], 1, 101)
        self.plateau = f4.sci("Plato payi (0.05-0.9)", cfg["plateau_fraction"])
        self.interleave = f4.check("ADC cift/tek ofsetini duzelt", cfg["fix_interleave"])
        f4.full(ttk.Button(f4, text="Analiz et", command=self.analyze))

        # ---------------- 5) disa aktar ----------------
        f5 = ttk.Labelframe(left, text="5) Disa aktar", padding=4)
        f5.pack(fill="x")
        self.export_buttons = []
        for text, cmd in (("Rapor (.txt, Excel'e uygun)", lambda: self._export("report")),
                          ("Kenar tablosu (.csv)", lambda: self._export("edges")),
                          ("Ortalama dalga (.csv)", lambda: self._export("avg")),
                          ("Grafik (.eps)", lambda: self._export("eps")),
                          ("Tabloyu panoya kopyala", self.copy_table)):
            b = ttk.Button(f5, text=text, command=cmd, state="disabled")
            b.pack(fill="x", pady=1)
            self.export_buttons.append(b)

        # ---------------- sag taraf ----------------
        top = ttk.Frame(right)
        bar = ttk.Frame(top)
        bar.pack(fill="x", pady=(0, 3))
        ttk.Label(bar, text="Gosterim:").pack(side="left")
        self._views = [("Dalga formu (V)", VIEW_WAVE),
                       ("Dalga formu (akim, uA)", VIEW_WAVE_I),
                       ("Ortalama kenarlar (normalize)", VIEW_EDGES),
                       ("Ortalama darbe (bir periyot)", VIEW_CYCLE),
                       ("Tek tek kenar sureleri", VIEW_PER_EDGE)]
        self.view = ttk.Combobox(bar, state="readonly", width=30,
                                 values=[t for t, _ in self._views])
        self.view.current(0)
        self.view.pack(side="left", padx=4)
        self.view.bind("<<ComboboxSelected>>", lambda e: self.draw())
        self.plot = CanvasPlot(top, "Zaman (us)", "Sinyal (V)", height=300)
        self.plot.pack(fill="both", expand=True)

        bottom = ttk.Labelframe(right, text="Sonuclar (Ctrl+C ile kopyalanir)", padding=3)
        self.table = KeyValueTable(bottom, height=9)
        self.table.tree.column("k", width=210, minwidth=120)
        self.table.tree.column("v", width=130, minwidth=90)
        # uyarilar tablonun USTUNDE: kucuk ekranda da gorunsun
        self.warn_var = tk.StringVar(self, value="")
        self.warn_label = ttk.Label(bottom, textvariable=self.warn_var, foreground="#b45309",
                                    wraplength=440, justify="left")
        self.warn_label.pack(fill="x", side="top")
        self.table.pack(fill="both", expand=True)
        right.add(top, weight=3)
        right.add(bottom, weight=2)

    # ------------------------------------------------------------------
    def view_key(self):
        idx = self.view.current()
        return self._views[idx][1] if 0 <= idx < len(self._views) else VIEW_WAVE

    def set_view(self, key):
        for k, (_t, v) in enumerate(self._views):
            if v == key:
                self.view.current(k)
        self.draw()

    def open_dialog(self):
        folder = (self.session.settings.get("scope_dir")
                  or self.session.settings.get("data_dir", "."))
        path = filedialog.askopenfilename(
            parent=self, title="Osiloskop CSV dosyasi sec", initialdir=folder,
            filetypes=[("CSV dosyalari", "*.csv"), ("Tum dosyalar", "*.*")])
        if path:
            self.load_file(path)

    def load_file(self, path):
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            trace = scope.load_scope_csv(path)
        except Exception as exc:
            self.config(cursor="")
            error(self, "Okuma hatasi", "{0}\n\n{1}".format(path, exc))
            return False
        self.trace = trace
        self.session.settings["scope_dir"] = os.path.dirname(os.path.abspath(path))
        text = os.path.basename(path) + "\n" + trace.summary()
        if trace.notes:
            text += "\n" + "\n".join(trace.notes)
        self.file_info.set(text)
        self._fill_channels(trace)
        self.session.log("Osiloskop kaydi yuklendi: {0} - {1}".format(path, trace.summary()))
        self.config(cursor="")
        self.analyze()
        return True

    def _fill_channels(self, trace):
        names = trace.names
        prev_sig, prev_ref = self.signal_ch.get(), self.ref_ch.get()
        self.signal_ch.set_items([(n, n) for n in names], keep=False)
        self.ref_ch.set_items([(n, n) for n in names] + [("(yok - sinyalin kendisi)", NO_REF)],
                              keep=False)
        sig = prev_sig if prev_sig in names else ("CH2" if "CH2" in names else names[-1])
        others = [n for n in names if n != sig]
        if prev_ref in names and prev_ref != sig:
            ref = prev_ref
        elif "CH1" in others:
            ref = "CH1"
        else:
            ref = others[0] if others else NO_REF
        self.signal_ch.set(sig)
        self.ref_ch.set(ref)

    def settings(self):
        ref = self.ref_ch.get()
        dark = self.dark.get(0.0)
        return scope.PulseSettings(
            signal=self.signal_ch.get() or "CH2",
            reference=None if ref in (None, NO_REF) else ref,
            light_on_high=bool(self.light_high.get()),
            gain_v_per_a=self.gain.get(scope.AMP120_GAIN_V_PER_A),
            load_50ohm=bool(self.load50.get()),
            dc_coupled=bool(self.dc_coupled.get()),
            smooth=self.smooth.get(),
            fix_interleave=bool(self.interleave.get()),
            plateau_fraction=self.plateau.get(0.3),
            wavelength_nm=self.wavelength.get(0.0) or None,
            optical_power_w=self.power.get(0.0) or None,
            area_cm2=self.area.get(0.0) or None,
            dark_current_a=dark or None,
            noise_bandwidth_hz=self.bandwidth.get(0.0),
            system_rise_s=self.sys_rise.get(0.0))

    def _remember(self, s):
        self.session.settings["scope"] = {
            "gain_v_per_a": s.gain_v_per_a, "load_50ohm": s.load_50ohm,
            "dc_coupled": s.dc_coupled, "system_rise_s": s.system_rise_s,
            "noise_bandwidth_hz": s.noise_bandwidth_hz, "light_on_high": s.light_on_high,
            "smooth": s.smooth, "plateau_fraction": s.plateau_fraction,
            "fix_interleave": s.fix_interleave, "dark_current_a": s.dark_current_a or 0.0}

    def analyze(self):
        if self.trace is None:
            warn(self, "Dosya yok", "Once bir osiloskop CSV dosyasi acin.")
            return
        s = self.settings()
        if s.reference == s.signal:
            warn(self, "Kanal secimi", "Sinyal ve referans ayni kanal olamaz; referans "
                                       "icin '(yok)' secebilirsiniz.")
            return
        if not s.gain_v_per_a or s.gain_v_per_a <= 0:
            warn(self, "Kazanc", "Transempedans kazanci pozitif olmali.")
            return
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.result = scope.analyze_pulses(self.trace, s)
        except Exception as exc:
            self.result = None
            self.config(cursor="")
            error(self, "Analiz hatasi", str(exc))
            return
        self.config(cursor="")
        self._remember(s)
        res = self.result
        self.table.set_rows(res.report_rows())
        self.warn_var.set("\n".join("UYARI: " + w for w in res.warnings))
        for w in res.warnings:
            self.session.log("Uyari: " + w)
        for b in self.export_buttons:
            b.config(state="normal")
        self.draw()
        r_txt = "{0:.4g} A/W".format(res.responsivity) if isfinite(res.responsivity) else "-"
        self.session.log("Darbe analizi: f = {0}, t_r = {1}, t_f = {2}, I_ph = {3}, R = {4}".format(
            scope.fmt_si(res.frequency, "Hz"), scope.fmt_si(res.rise_time, "s"),
            scope.fmt_si(res.fall_time, "s"), scope.fmt_si(res.photocurrent, "A"), r_txt))

    # ------------------------------------------------------------------
    def draw(self):
        p = self.plot
        p.clear()
        res = self.result
        if res is None:
            if self.trace is not None:
                k, unit = time_unit(self.trace.duration)
                sig = self.signal_ch.get()
                if sig in self.trace.channels:
                    x, y = decimate([v * k for v in self.trace.t], self.trace.channels[sig])
                    p.set_labels("Zaman ({0})".format(unit), "Sinyal (V)", "Ham kayit")
                    p.add_series("s", sig, color="#0891b2", width=1)
                    p.set_data("s", x, y)
            p.redraw()
            return
        view = self.view_key()
        if view == VIEW_EDGES:
            self._draw_edges(p, res)
        elif view == VIEW_CYCLE:
            self._draw_cycle(p, res)
        elif view == VIEW_PER_EDGE:
            self._draw_per_edge(p, res)
        else:
            self._draw_wave(p, res, view == VIEW_WAVE_I)
        p.redraw()

    def _draw_wave(self, p, res, as_current):
        k, unit = time_unit(res.trace.duration)
        f = (1e6 / res.gain) if as_current else 1.0
        t = [v * k for v in res.t]
        p.set_labels("Zaman ({0})".format(unit), "Akim (uA)" if as_current else "Sinyal (V)",
                     "Dalga formu (mor: lamba acik)")
        p.set_spans([(a * k, b * k) for a, b in res.light_spans()])
        if res.reference is not None and isfinite(res.v_on) and isfinite(res.v_off):
            lo = scope.percentile(res.reference, 2)
            hi = scope.percentile(res.reference, 98)
            if hi > lo:
                scaled = [(res.v_off + (r - lo) / (hi - lo) * (res.v_on - res.v_off)) * f
                          for r in res.reference]
                x, y = decimate(t, scaled)
                p.add_series("ref", "{0} (lamba, olcekli)".format(res.settings.reference),
                             color="#ca8a04", width=1)
                p.set_data("ref", x, y)
        x, y = decimate(t, [v * f for v in res.signal])
        p.add_series("sig", "{0} (islenmis)".format(res.settings.signal), color="#0891b2", width=1)
        p.set_data("sig", x, y)
        for lvl, name, col in ((res.v_on, "V_on", "#16a34a"), (res.v_off, "V_off", "#dc2626")):
            if isfinite(lvl):
                p.add_series(name, "{0} = {1}".format(name, scope.fmt_si(lvl, "V")),
                             color=col, dash=(6, 3), width=1)
                p.set_data(name, [t[0], t[-1]], [lvl * f, lvl * f])
        pts = [(e.t50 * k, 0.5 * (e.v_before + e.v_after) * f)
               for e in res.edges if isfinite(e.t50)]
        if pts:
            x, y = _points_series([q[0] for q in pts], [q[1] for q in pts])
            p.add_series("t50", "%50 gecisleri", color="#111827", width=1)
            p.set_data("t50", x, y)

    def _draw_edges(self, p, res):
        span = max(res.on_width if isfinite(res.on_width) else 0.0,
                   res.off_width if isfinite(res.off_width) else 0.0) or 1e-3
        k, unit = time_unit(span)
        p.set_labels("Sinyalin %50 noktasina gore zaman ({0})".format(unit),
                     "Normalize tepki (0 -> 1)",
                     "Ortalama kenarlar (kesikli: %10 / %90)")
        xs = []
        for ae, key, name, col in ((res.avg_rise, "rise", "Acilis", "#16a34a"),
                                   (res.avg_fall, "fall", "Kapanis", "#dc2626")):
            if ae is None:
                continue
            x = [v * k for v in ae.tau]
            xs += [x[0], x[-1]]
            p.add_series(key, "{0}: {1} (N={2})".format(
                name, scope.fmt_si(ae.timing.duration, "s"), ae.count), color=col, width=2)
            p.set_data(key, x, ae.normalized)
        if xs:
            for lvl in (0.1, 0.9):
                key = "l{0}".format(lvl)
                p.add_series(key, "%{0:.0f}".format(lvl * 100), color="#6b7280", dash=(4, 3), width=1)
                p.set_data(key, [min(xs), max(xs)], [lvl, lvl])

    def _draw_cycle(self, p, res):
        k, unit = time_unit(res.period if isfinite(res.period) else 1e-3)
        p.set_labels("Lamba acilisina gore zaman ({0})".format(unit), "Sinyal (V)",
                     "Ortalama darbe (mor: lamba acik)")
        if res.cycle_tau:
            p.set_spans([(0.0, res.on_width * k)])
            x, y = decimate([v * k for v in res.cycle_tau], res.cycle_avg)
            p.add_series("cyc", "ortalama ({0} cevrim)".format(len(res.on_edges)),
                         color="#0891b2", width=2)
            p.set_data("cyc", x, y)

    def _draw_per_edge(self, p, res):
        p.set_labels("Kenar sirasi", "10-90% sure (us)", "Tek tek kenarlarin sureleri")
        ordered = sorted(res.edges, key=lambda e: e.t_ref)
        for kind, name, col in (("on", "Yukselme", "#16a34a"), ("off", "Dusme", "#dc2626")):
            vals = [(i + 1, e.duration * 1e6) for i, e in enumerate(ordered)
                    if e.kind == kind and isfinite(e.duration)]
            if vals:
                p.add_series(kind, name, color=col, marker=True, width=1)
                p.set_data(kind, [v[0] for v in vals], [v[1] for v in vals])
        ts = res.settings.system_rise_s
        if ts and ordered:
            p.add_series("sys", "sistem siniri", color="#6b7280", dash=(4, 3), width=1)
            p.set_data("sys", [1, len(ordered)], [ts * 1e6, ts * 1e6])

    # ------------------------------------------------------------------
    def _ask_path(self, title, suffix, ext, types):
        folder = self.session.settings.get("data_dir", ".")
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder)
            except OSError:
                folder = "."
        base = "osiloskop"
        if self.trace is not None and self.trace.path:
            base = os.path.splitext(os.path.basename(self.trace.path))[0]
        default = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + base + suffix
        return filedialog.asksaveasfilename(parent=self, title=title, initialdir=folder,
                                            initialfile=default, defaultextension=ext,
                                            filetypes=types)

    def export_to(self, kind, path):
        res = self.result
        if kind == "report":
            scope.write_report(res, path, self.session.settings.get("sample_name", ""))
        elif kind == "edges":
            scope.write_edges_csv(res, path)
        elif kind == "avg":
            scope.write_average_csv(res, path)
        else:
            self.plot.save_postscript(path)
        self.session.log("Kaydedildi: {0}".format(path))
        return path

    def _export(self, kind):
        if self.result is None:
            warn(self, "Sonuc yok", "Once analiz yapin.")
            return
        spec = {"report": ("Raporu kaydet", "_rapor.txt", ".txt", [("Metin dosyalari", "*.txt")]),
                "edges": ("Kenar tablosu", "_kenarlar.csv", ".csv", [("CSV dosyalari", "*.csv")]),
                "avg": ("Ortalama dalga", "_ortalama.csv", ".csv", [("CSV dosyalari", "*.csv")]),
                "eps": ("Grafigi kaydet", "_grafik.eps", ".eps",
                        [("Encapsulated PostScript", "*.eps")])}[kind]
        path = self._ask_path(*spec)
        if not path:
            return
        self.export_to(kind, path)
        if kind == "report":
            info(self, "Rapor kaydedildi",
                 "{0}\n\nExcel'de acmak icin: Veri > Metinden, ayirici = Sekme (Tab).\n"
                 "Deger kolonu SI birimindedir (s, V, A, W).".format(path))

    def copy_table(self):
        self.clipboard_clear()
        self.clipboard_append(self.table.to_text())
        self.session.log("Sonuc tablosu panoya kopyalandi (Excel'e yapistirilabilir).")
