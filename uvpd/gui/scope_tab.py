"""Osiloskop darbe analizi sekmesi (v2).

Keithley 3390 kare dalgasiyla surulen UV lamba altinda, AMP120 transempedans
yukseltecinden alinan sinyalin osiloskop CSV kaydi yuklenir; tepki suresi,
fotoakim, duyarlilik, EQE, NEP ve D* hesaplanir. Cihaz baglantisi gerekmez.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import numpy as np

from .. import scope
from ..qtcompat import QtCore, QtWidgets, matplotlib_backend_modules
from .session import Session
from .widgets import FormBuilder, KeyValueTable, group, message

FigureCanvas, NavigationToolbar = matplotlib_backend_modules()
from matplotlib.figure import Figure  # noqa: E402

VIEW_WAVE = "wave"
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


def _time_unit(span: float):
    span = abs(span)
    if span < 2e-6:
        return 1e9, "ns"
    if span < 2e-3:
        return 1e6, "µs"
    if span < 2.0:
        return 1e3, "ms"
    return 1.0, "s"


class ScopePlot(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(6.0, 4.2), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toolbar)
        lay.addWidget(self.canvas, 1)

    def _new_axes(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.grid(True, alpha=0.25, linestyle=":")
        return ax

    def _current_axis(self, ax, gain: float) -> None:
        if gain:
            sec = ax.secondary_yaxis(
                "right", functions=(lambda v: v / gain * 1e6, lambda i: i * gain / 1e6))
            sec.set_ylabel("Akim (µA)")

    # ------------------------------------------------------------------
    def draw_trace(self, trace: scope.ScopeTrace, signal: str, ref: Optional[str]) -> None:
        ax = self._new_axes()
        k, unit = _time_unit(trace.duration)
        for name, y in trace.channels.items():
            if name == signal:
                ax.plot(trace.t * k, y, lw=0.9, color="#0891b2", label=name)
        if ref and ref in trace.channels:
            ax2 = ax.twinx()
            ax2.plot(trace.t * k, trace.channels[ref], lw=0.8, color="#ca8a04",
                     alpha=0.7, label=ref)
            ax2.set_ylabel(f"{ref} (V)")
        ax.set_xlabel(f"Zaman ({unit})")
        ax.set_ylabel(f"{signal} (V)")
        ax.set_title("Ham kayit")
        self.canvas.draw_idle()

    def draw_result(self, res: scope.PulseResult, view: str) -> None:
        ax = self._new_axes()
        if view == VIEW_EDGES:
            self._draw_edges(ax, res)
        elif view == VIEW_CYCLE:
            self._draw_cycle(ax, res)
        elif view == VIEW_PER_EDGE:
            self._draw_per_edge(ax, res)
        else:
            self._draw_wave(ax, res)
        self.canvas.draw_idle()

    def _draw_wave(self, ax, res: scope.PulseResult) -> None:
        k, unit = _time_unit(res.trace.duration)
        t = res.t * k
        for a, b in res.light_spans():
            ax.axvspan(a * k, b * k, color="#a855f7", alpha=0.10, lw=0)
        if res.reference is not None and np.isfinite(res.v_on) and np.isfinite(res.v_off):
            r = res.reference
            lo, hi = np.percentile(r, [2, 98])
            if hi > lo:
                scaled = res.v_off + (r - lo) / (hi - lo) * (res.v_on - res.v_off)
                ax.plot(t, scaled, lw=0.8, color="#ca8a04", alpha=0.55,
                        label=f"{res.settings.reference} (lamba, olcekli)")
        ax.plot(t, res.signal, lw=0.9, color="#0891b2", label=f"{res.settings.signal} (islenmis)")
        for lvl, name, col in ((res.v_on, "V_on", "#16a34a"), (res.v_off, "V_off", "#dc2626")):
            if np.isfinite(lvl):
                ax.axhline(lvl, color=col, ls="--", lw=0.9, label=f"{name} = {scope.fmt_si(lvl, 'V')}")
        t50 = [e.t50 * k for e in res.edges if np.isfinite(e.t50)]
        if t50:
            y50 = [0.5 * (e.v_before + e.v_after) for e in res.edges if np.isfinite(e.t50)]
            ax.plot(t50, y50, "o", ms=4, color="#111827", label="%50 gecisleri")
        ax.set_xlabel(f"Zaman ({unit})")
        ax.set_ylabel("Sinyal (V)")
        ax.set_title("Dalga formu — mor alanlar: lamba acik")
        self._current_axis(ax, res.gain)
        ax.legend(loc="best", fontsize=7)

    def _draw_edges(self, ax, res: scope.PulseResult) -> None:
        drawn = False
        span = max(res.on_width if np.isfinite(res.on_width) else 0,
                   res.off_width if np.isfinite(res.off_width) else 0) or 1e-3
        k, unit = _time_unit(span)
        for ae, name, col in ((res.avg_rise, "Acilis (yukselme)", "#16a34a"),
                              (res.avg_fall, "Kapanis (dusme)", "#dc2626")):
            if ae is None:
                continue
            ax.plot(ae.tau * k, ae.normalized, lw=1.3, color=col,
                    label=f"{name}: {scope.fmt_si(ae.timing.duration, 's')} (N={ae.count})")
            for tt in (ae.timing.t10, ae.timing.t90):
                if np.isfinite(tt):
                    ax.axvline(tt * k, color=col, lw=0.7, ls=":")
            drawn = True
        if drawn:
            ax.axhline(0.1, color="#6b7280", lw=0.7, ls="--")
            ax.axhline(0.9, color="#6b7280", lw=0.7, ls="--")
            ax.axvline(0, color="#6b7280", lw=0.7)
            ax.set_ylim(-0.3, 1.3)
            ax.legend(loc="lower right", fontsize=8)
        ax.set_xlabel(f"Sinyalin %50 noktasina gore zaman ({unit})")
        ax.set_ylabel("Normalize tepki (0 → 1)")
        ax.set_title("Cevrim ortalamasi alinmis kenarlar — kesikli: %10 / %90")

    def _draw_cycle(self, ax, res: scope.PulseResult) -> None:
        if res.cycle_tau.size:
            k, unit = _time_unit(res.period)
            ax.axvspan(0, res.on_width * k, color="#a855f7", alpha=0.10, lw=0,
                       label="lamba acik")
            ax.plot(res.cycle_tau * k, res.cycle_avg, lw=1.3, color="#0891b2",
                    label=f"ortalama ({res.on_edges.size} cevrim)")
            ax.set_xlabel(f"Lamba acilisina gore zaman ({unit})")
            ax.legend(loc="best", fontsize=8)
        ax.set_ylabel("Sinyal (V)")
        ax.set_title("Ortalama darbe (bir periyot)")
        self._current_axis(ax, res.gain)

    def _draw_per_edge(self, ax, res: scope.PulseResult) -> None:
        for kind, name, col in (("on", "Yukselme", "#16a34a"), ("off", "Dusme", "#dc2626")):
            vals = [(i + 1, e.duration * 1e6) for i, e in
                    enumerate(sorted(res.edges, key=lambda x: x.t_ref))
                    if e.kind == kind and np.isfinite(e.duration)]
            if vals:
                x, y = zip(*vals)
                ax.plot(x, y, "o-", color=col, ms=5, lw=0.8, label=name)
        if res.settings.system_rise_s:
            ax.axhline(res.settings.system_rise_s * 1e6, color="#6b7280", ls="--", lw=0.8,
                       label="sistem siniri")
        ax.set_xlabel("Kenar sirasi")
        ax.set_ylabel("%10–%90 sure (µs)")
        ax.set_title("Tek tek kenarlarin sureleri")
        ax.legend(loc="best", fontsize=8)

    def save(self, path: str) -> None:
        self.figure.savefig(path, dpi=300, bbox_inches="tight")


class ScopeTab(QtWidgets.QWidget):
    """5 · Osiloskop darbe analizi."""

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.trace: Optional[scope.ScopeTrace] = None
        self.result: Optional[scope.PulseResult] = None
        cfg = dict(DEFAULTS)
        cfg.update(session.settings.get("scope") or {})
        self.setAcceptDrops(True)

        # ---------------- 1) dosya ----------------
        f1 = FormBuilder()
        self.btn_open = QtWidgets.QPushButton("📂  Osiloskop CSV dosyasi ac…")
        self.btn_open.setStyleSheet("font-weight:700; padding:6px;")
        f1.add_row(self.btn_open)
        self.file_label = QtWidgets.QLabel("Dosya yuklenmedi (dosyayi pencereye de "
                                           "surukleyip birakabilirsiniz).")
        self.file_label.setWordWrap(True)
        f1.add_row(self.file_label)
        self.signal_ch = f1.combo("Sinyal kanali (AMP120)", [])
        self.ref_ch = f1.combo("Referans kanali (lamba)", [])
        self.light_high = f1.check(
            "Lamba referans YUKSEK iken yanar", cfg["light_on_high"],
            "3390 cikisi yuksekken lamba yaniyorsa isaretli birakin.")
        file_box = group("1) Osiloskop kaydi", f1.widget)

        # ---------------- 2) yukseltec ----------------
        f2 = FormBuilder()
        self.gain = f2.sci("Transempedans kazanci G (V/A)", cfg["gain_v_per_a"],
                           "Thorlabs AMP120: 1e5 V/A (100 kV/A), yuksek empedansli yukte.")
        self.load50 = f2.check(
            "Osiloskop girisi 50 Ω", cfg["load_50ohm"],
            "AMP120'nin cikis direnci 50 Ω'dur. Osiloskop girisi 50 Ω'a "
            "ayarliysa etkin kazanc yariya iner (5e4 V/A). 1 MΩ ise isaretlemeyin.")
        self.dc_coupled = f2.check(
            "CH2 DC kuplajli, AMP120 sifiri ayarli", cfg["dc_coupled"],
            "Isaretlenirse V_off karanlik seviye sayilir ve I_on/I_off orani "
            "hesaplanir. AC kuplajda (osiloskopta CH2 ~) isaretlemeyin.")
        self.sys_rise = f2.sci("Sistem yukselme suresi (s)", cfg["system_rise_s"],
                               "AMP120: 0.35 / 100 kHz ≈ 3.5 µs. Olculen sureden karesel "
                               "olarak cikarilir. 0 → duzeltme yok.")
        self.bandwidth = f2.sci("Gurultu bant genisligi B (Hz)", cfg["noise_bandwidth_hz"],
                                "NEP ve D* bu bant icindeki gurultuyle hesaplanir "
                                "(AMP120: 100 kHz).")
        amp_box = group("2) Yukseltec (Thorlabs AMP120)", f2.widget)

        # ---------------- 3) isik / dedektor ----------------
        f3 = FormBuilder()
        self.wavelength = f3.sci("Dalga boyu (nm)", session.settings.get("wavelength_nm", 365.0))
        self.power = f3.sci("Dedektore dusen optik guc (W)",
                            session.settings.get("optical_power_w", 2e-6),
                            "Lamba acikken dedektorun aktif alanina dusen guc.")
        self.area = f3.sci("Aktif alan (cm²)", session.settings.get("area_cm2", 0.04))
        self.dark = f3.sci("Karanlik akim (A, istege bagli)", cfg["dark_current_a"],
                           "Keithley I–V olcumunden ayni bias'taki karanlik akim. "
                           "Girilirse shot-gurultu D* de hesaplanir. 0 → kullanilmaz.")
        det_box = group("3) Isik ve dedektor", f3.widget)

        # ---------------- 4) analiz ----------------
        f4 = FormBuilder()
        self.smooth = f4.spin("Yumusatma (ornek)", cfg["smooth"], 1, 101,
                              "Hareketli ortalama. 1 = kapali. Buyuk degerler kenarlari "
                              "yavaslatir; gurultulu kayitlarda 3–5 deneyin.")
        self.plateau = QtWidgets.QDoubleSpinBox()
        self.plateau.setRange(0.05, 0.9)
        self.plateau.setSingleStep(0.05)
        self.plateau.setValue(float(cfg["plateau_fraction"]))
        f4.add("Plato payi", self.plateau,
               "Her yarim periyodun sonundaki bu kadarlik kisim seviye (V_on/V_off) "
               "ve gurultu icin kullanilir.")
        self.interleave = f4.check(
            "ADC cift/tek ornek ofsetini duzelt", cfg["fix_interleave"],
            "Bazi osiloskoplarda ardisik ornekler arasinda sabit bir ofset olur "
            "(araya-girmeli ADC). Otomatik bulunur ve cikarilir.")
        self.btn_analyze = QtWidgets.QPushButton("Σ  Analiz et")
        self.btn_analyze.setStyleSheet("font-weight:700; padding:6px;")
        f4.add_row(self.btn_analyze)
        an_box = group("4) Analiz", f4.widget)

        # ---------------- disa aktarim ----------------
        grid = QtWidgets.QGridLayout()
        self.btn_report = QtWidgets.QPushButton("Rapor (.txt)")
        self.btn_edges = QtWidgets.QPushButton("Kenar tablosu (.csv)")
        self.btn_avg = QtWidgets.QPushButton("Ortalama dalga (.csv)")
        self.btn_png = QtWidgets.QPushButton("Grafik (.png)")
        self.btn_copy = QtWidgets.QPushButton("Tabloyu kopyala")
        for i, b in enumerate((self.btn_report, self.btn_edges, self.btn_avg,
                               self.btn_png, self.btn_copy)):
            grid.addWidget(b, i // 2, i % 2)
        exp_w = QtWidgets.QWidget()
        exp_w.setLayout(grid)
        exp_box = group("5) Disa aktar", exp_w)

        left = QtWidgets.QVBoxLayout()
        for w in (file_box, amp_box, det_box, an_box, exp_box):
            left.addWidget(w)
        left.addStretch(1)
        left_w = QtWidgets.QWidget()
        left_w.setLayout(left)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_w)
        scroll.setMinimumWidth(400)

        # ---------------- sag taraf ----------------
        self.view = QtWidgets.QComboBox()
        self.view.addItem("Dalga formu", VIEW_WAVE)
        self.view.addItem("Ortalama kenarlar (normalize)", VIEW_EDGES)
        self.view.addItem("Ortalama darbe (bir periyot)", VIEW_CYCLE)
        self.view.addItem("Tek tek kenar sureleri", VIEW_PER_EDGE)
        vrow = QtWidgets.QHBoxLayout()
        vrow.setContentsMargins(0, 0, 0, 0)
        vrow.addWidget(QtWidgets.QLabel("Gosterim:"))
        vrow.addWidget(self.view)
        vrow.addStretch(1)
        vw = QtWidgets.QWidget()
        vw.setLayout(vrow)

        self.plot = ScopePlot()
        plot_w = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(plot_w)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(vw)
        pv.addWidget(self.plot, 1)

        self.table = KeyValueTable()
        self.warn_label = QtWidgets.QLabel("")
        self.warn_label.setWordWrap(True)
        self.warn_label.setStyleSheet("color:#b45309;")
        table_w = QtWidgets.QWidget()
        tv = QtWidgets.QVBoxLayout(table_w)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addWidget(QtWidgets.QLabel("Sonuclar:"))
        tv.addWidget(self.table, 1)
        tv.addWidget(self.warn_label)

        right = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        right.addWidget(plot_w)
        right.addWidget(table_w)
        right.setStretchFactor(0, 1)
        right.setStretchFactor(1, 1)
        right.setSizes([420, 380])
        self.table.setMinimumHeight(200)
        self.plot.setMinimumHeight(260)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(splitter)

        # ---------------- sinyaller ----------------
        self.btn_open.clicked.connect(self.open_dialog)
        self.btn_analyze.clicked.connect(self.analyze)
        self.view.currentIndexChanged.connect(self._draw)
        self.btn_report.clicked.connect(lambda: self._export("report"))
        self.btn_edges.clicked.connect(lambda: self._export("edges"))
        self.btn_avg.clicked.connect(lambda: self._export("avg"))
        self.btn_png.clicked.connect(lambda: self._export("png"))
        self.btn_copy.clicked.connect(self._copy_table)
        self._set_export_enabled(False)

    # ------------------------------------------------------------------
    def _set_export_enabled(self, on: bool) -> None:
        for b in (self.btn_report, self.btn_edges, self.btn_avg, self.btn_png, self.btn_copy):
            b.setEnabled(on)

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        urls = event.mimeData().urls()
        if urls:
            self.load_file(urls[0].toLocalFile())

    def open_dialog(self) -> None:
        directory = self.session.settings.get("scope_dir") or self.session.settings.get("data_dir", ".")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Osiloskop CSV dosyasi sec", directory,
            "CSV dosyalari (*.csv *.CSV);;Tum dosyalar (*)")
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> bool:
        try:
            trace = scope.load_scope_csv(path)
        except Exception as exc:
            message(self, "Okuma hatasi", f"{path}\n\n{exc}", "error")
            return False
        self.trace = trace
        self.session.settings["scope_dir"] = os.path.dirname(os.path.abspath(path))
        self.file_label.setText(f"<b>{os.path.basename(path)}</b><br>{trace.summary()}"
                                + "".join(f"<br>{n}" for n in trace.notes))
        self._fill_channels(trace)
        self.session.log(f"Osiloskop kaydi yuklendi: {path} — {trace.summary()}")
        self.analyze()
        return True

    def _fill_channels(self, trace: scope.ScopeTrace) -> None:
        names = trace.names
        prev_sig, prev_ref = self.signal_ch.currentData(), self.ref_ch.currentData()
        self.signal_ch.clear()
        self.ref_ch.clear()
        for n in names:
            self.signal_ch.addItem(n, n)
            self.ref_ch.addItem(n, n)
        self.ref_ch.addItem("(yok — sinyalin kendisi)", NO_REF)
        sig = prev_sig if prev_sig in names else ("CH2" if "CH2" in names else names[-1])
        others = [n for n in names if n != sig]
        ref = prev_ref if (prev_ref in names and prev_ref != sig) else (
            "CH1" if "CH1" in others else (others[0] if others else NO_REF))
        self.signal_ch.setCurrentIndex(self.signal_ch.findData(sig))
        self.ref_ch.setCurrentIndex(self.ref_ch.findData(ref))

    def settings(self) -> scope.PulseSettings:
        ref = self.ref_ch.currentData()
        dark = self.dark.value(0.0)
        return scope.PulseSettings(
            signal=self.signal_ch.currentData() or "CH2",
            reference=None if ref in (None, NO_REF) else ref,
            light_on_high=self.light_high.isChecked(),
            gain_v_per_a=self.gain.value(scope.AMP120_GAIN_V_PER_A),
            load_50ohm=self.load50.isChecked(),
            dc_coupled=self.dc_coupled.isChecked(),
            smooth=int(self.smooth.value()),
            fix_interleave=self.interleave.isChecked(),
            plateau_fraction=float(self.plateau.value()),
            wavelength_nm=self.wavelength.value(0.0) or None,
            optical_power_w=self.power.value(0.0) or None,
            area_cm2=self.area.value(0.0) or None,
            dark_current_a=dark or None,
            noise_bandwidth_hz=self.bandwidth.value(0.0),
            system_rise_s=self.sys_rise.value(0.0),
        )

    def _remember(self, s: scope.PulseSettings) -> None:
        self.session.settings["scope"] = {
            "gain_v_per_a": s.gain_v_per_a, "load_50ohm": s.load_50ohm,
            "dc_coupled": s.dc_coupled, "system_rise_s": s.system_rise_s,
            "noise_bandwidth_hz": s.noise_bandwidth_hz,
            "light_on_high": s.light_on_high, "smooth": s.smooth,
            "plateau_fraction": s.plateau_fraction, "fix_interleave": s.fix_interleave,
            "dark_current_a": s.dark_current_a or 0.0,
        }

    def analyze(self) -> None:
        if self.trace is None:
            message(self, "Dosya yok", "Once bir osiloskop CSV dosyasi acin.", "warn")
            return
        s = self.settings()
        if s.reference == s.signal:
            message(self, "Kanal secimi", "Sinyal ve referans ayni kanal olamaz; "
                    "referans icin '(yok)' secebilirsiniz.", "warn")
            return
        if not s.gain_v_per_a or s.gain_v_per_a <= 0:
            message(self, "Kazanc", "Transempedans kazanci pozitif olmali.", "warn")
            return
        try:
            self.result = scope.analyze_pulses(self.trace, s)
        except Exception as exc:
            self.result = None
            message(self, "Analiz hatasi", str(exc), "error")
            return
        self._remember(s)
        res = self.result
        self.table.set_rows(res.report_rows())
        self.warn_label.setText("\n".join("⚠ " + w for w in res.warnings))
        for w in res.warnings:
            self.session.log("Uyari: " + w)
        self._set_export_enabled(True)
        self._draw()
        self.session.log(
            f"Darbe analizi: f = {scope.fmt_si(res.frequency, 'Hz')}, "
            f"t_r = {scope.fmt_si(res.rise_time, 's')}, t_f = {scope.fmt_si(res.fall_time, 's')}, "
            f"I_ph = {scope.fmt_si(res.photocurrent, 'A')}, R = {res.responsivity:.4g} A/W")

    def _draw(self) -> None:
        if self.result is not None:
            self.plot.draw_result(self.result, self.view.currentData())
        elif self.trace is not None:
            ref = self.ref_ch.currentData()
            self.plot.draw_trace(self.trace, self.signal_ch.currentData(),
                                 None if ref == NO_REF else ref)

    # ------------------------------------------------------------------
    def _default_path(self, suffix: str) -> str:
        directory = self.session.settings.get("data_dir", ".")
        os.makedirs(directory, exist_ok=True)
        base = "osiloskop"
        if self.trace is not None and self.trace.path:
            base = os.path.splitext(os.path.basename(self.trace.path))[0]
        return os.path.join(directory, datetime.now().strftime("%Y%m%d_%H%M%S")
                            + f"_{base}_{suffix}")

    def export_to(self, kind: str, path: str) -> str:
        res = self.result
        if kind == "report":
            scope.write_report(res, path, self.session.settings.get("sample_name", ""))
        elif kind == "edges":
            scope.write_edges_csv(res, path)
        elif kind == "avg":
            scope.write_average_csv(res, path)
        else:
            self.plot.save(path)
        self.session.log(f"Kaydedildi: {path}")
        return path

    def _export(self, kind: str) -> None:
        if self.result is None:
            message(self, "Sonuc yok", "Once analiz yapin.", "warn")
            return
        spec = {"report": ("rapor.txt", "Metin (*.txt)"),
                "edges": ("kenarlar.csv", "CSV (*.csv)"),
                "avg": ("ortalama.csv", "CSV (*.csv)"),
                "png": ("grafik.png", "PNG (*.png);;PDF (*.pdf)")}[kind]
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Kaydet", self._default_path(spec[0]), spec[1])
        if path:
            self.export_to(kind, path)

    def _copy_table(self) -> None:
        QtWidgets.QApplication.clipboard().setText(self.table.to_text())
        self.session.log("Sonuc tablosu panoya kopyalandi (Excel'e yapistirilabilir).")
