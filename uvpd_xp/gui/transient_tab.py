# -*- coding: utf-8 -*-
"""Zaman tepkisi (UV ac/kapa) sekmesi."""

import os

import tkinter as tk
from tkinter import filedialog, ttk

from .. import analysis
from ..dataset import LIGHT, suggest_filename
from ..measurement import SampleInfo, TransientConfig, run_transient
from .common import Form, KeyValueTable, ScrollFrame, Worker, error, warn
from .plot import LINEAR, CanvasPlot, YScaleSelector


class TransientTab(ttk.Frame):
    def __init__(self, master, session):
        ttk.Frame.__init__(self, master, padding=6)
        self.session = session
        self.worker = None
        self._events = []
        self._last_t = 0.0
        self._last = None
        s = session.settings
        tr = s.get("transient", {})

        sf = ScrollFrame(self)
        sf.pack(side="left", fill="y", padx=(0, 6))
        left = sf.inner
        right = ttk.Panedwindow(self, orient="vertical")
        right.pack(side="left", fill="both", expand=True)

        f1 = Form(left, "Olcum parametreleri")
        f1.pack(fill="x", pady=(0, 4))
        self.sample_name = f1.text("Numune adi", s.get("sample_name", "numune"))
        self.bias = f1.sci("Bias (V veya A)", tr.get("bias", 1.0))
        self.duration = f1.sci("Toplam sure (s)", tr.get("duration", 60.0))
        self.interval = f1.sci("Ornekleme araligi (s)", tr.get("interval", 0.1))
        self.wavelength = f1.sci("Dalga boyu (nm)", s.get("wavelength_nm", 365.0))
        self.power = f1.sci("Optik guc (W)", s.get("optical_power_w", 2e-6))
        self.area = f1.sci("Aktif alan (cm2)", s.get("area_cm2", 0.04))
        self.autosave = f1.check("Bitince otomatik CSV kaydet", True)

        f2 = Form(left, "Otomatik UV cevrimi (opsiyonel)")
        f2.pack(fill="x", pady=(0, 4))
        self.cycle = f2.check("Shutter digital I/O ile", False)
        self.digio = f2.spin("Digital I/O hatti", 1, 1, 14)
        self.cycle_delay = f2.sci("Ilk bekleme (s)", 5.0)
        self.cycle_on = f2.sci("UV acik (s)", 10.0)
        self.cycle_off = f2.sci("UV kapali (s)", 10.0)

        bf = ttk.Frame(left)
        bf.pack(fill="x", pady=(2, 4))
        self.btn_start = ttk.Button(bf, text="Kaydi baslat", command=self.start)
        self.btn_stop = ttk.Button(bf, text="Durdur", command=self.stop, state="disabled")
        self.btn_on = ttk.Button(bf, text="UV ACIK isaretle", command=lambda: self._mark(1), state="disabled")
        self.btn_off = ttk.Button(bf, text="UV KAPALI isaretle", command=lambda: self._mark(0), state="disabled")
        self.btn_save = ttk.Button(bf, text="CSV kaydet", command=self.save_last)
        self.btn_start.grid(row=0, column=0, sticky="we", padx=1, pady=1)
        self.btn_stop.grid(row=0, column=1, sticky="we", padx=1, pady=1)
        self.btn_on.grid(row=1, column=0, sticky="we", padx=1, pady=1)
        self.btn_off.grid(row=1, column=1, sticky="we", padx=1, pady=1)
        self.btn_save.grid(row=2, column=0, columnspan=2, sticky="we", padx=1, pady=1)
        bf.columnconfigure(0, weight=1)
        bf.columnconfigure(1, weight=1)
        top = ttk.Frame(right)
        self.plot = CanvasPlot(top, "Zaman (s)", "Akim (A)", height=300)
        head = ttk.Frame(top)
        head.pack(fill="x", pady=(0, 3))
        YScaleSelector(head, self.plot, default=LINEAR).pack(side="left")
        self.readout = tk.StringVar(self, value="t = -    I = -")
        ttk.Label(top, textvariable=self.readout,
                  font=("Courier New", 9, "bold")).pack(side="bottom", anchor="w", pady=(3, 0))
        self.plot.pack(fill="both", expand=True)
        bottom = ttk.Labelframe(right, text="Tepki parametreleri (Ctrl+C ile kopyalanir)", padding=3)
        self.metrics = KeyValueTable(bottom, height=7)
        self.metrics.pack(fill="both", expand=True)
        right.add(top, weight=3)
        right.add(bottom, weight=1)

        self.cycle.trace("w", lambda *a: self._on_cycle())
        session.on("stop_request", self.stop)
        self._on_cycle()

    # ------------------------------------------------------------------
    def _on_cycle(self):
        st = "normal" if self.cycle.get() else "disabled"
        for v in (self.cycle_delay, self.cycle_on, self.cycle_off):
            v.widget.config(state=st)

    def _mark(self, state):
        self._events.append((self._last_t, state))
        self.session.log("Isaret: UV {0} @ t = {1:.2f} s".format("ACIK" if state else "KAPALI", self._last_t))
        inst = self.session.instrument
        if self.session.simulated and hasattr(inst, "set_uv"):
            inst.set_uv(bool(state))
        self.plot.set_spans(self._spans())

    def _spans(self):
        spans, start = [], None
        for t, st in self._events:
            if st == 1 and start is None:
                start = t
            elif st == 0 and start is not None:
                spans.append((start, t))
                start = None
        if start is not None:
            spans.append((start, max(self._last_t, start)))
        return spans

    # ------------------------------------------------------------------
    def start(self):
        if self.worker is not None and self.worker.running:
            return
        if not self.session.connected:
            warn(self, "Cihaz bagli degil", "Once cihaza baglanin.")
            return
        if not self.session.settings.get("interlock_confirmed"):
            warn(self, "Interlock onayi yok", "Baglanti sekmesinde INTERLOCK onayini isaretleyin.")
            return
        bias = self.bias.get(1.0)
        if self.session.settings.get("source_func") == "voltage" and abs(bias) > 60.0:
            error(self, "Sinir asimi", "Adapter Box C 10 icin U_max = 60 V DC.")
            return

        inst = self.session.instrument
        smu = self.session.smu_config()
        cfg = TransientConfig(bias=bias, duration=max(1.0, self.duration.get(60.0)),
                              interval=max(0.005, self.interval.get(0.1)),
                              cycle_enabled=bool(self.cycle.get()),
                              cycle_delay=self.cycle_delay.get(5.0),
                              cycle_on=self.cycle_on.get(10.0), cycle_off=self.cycle_off.get(10.0))
        sample = SampleInfo(name=self.sample_name.get().strip() or "numune", light_state=LIGHT,
                            wavelength_nm=self.wavelength.get(365.0),
                            optical_power_w=self.power.get(0.0) or None,
                            area_cm2=self.area.get(0.0) or None)
        self._events = []
        self._last_t = 0.0
        self.plot.clear()
        self.plot.add_series("i", "{0} @ {1:g}".format(sample.name, cfg.bias))
        self.metrics.set_rows([])

        line = self.digio.get()
        simulated = self.session.simulated

        def light_control(on):
            if simulated and hasattr(inst, "set_uv"):
                inst.set_uv(on)
            else:
                inst.write_digio_bit(line, on)

        events = self._events

        def job(on_point, should_stop, log):
            return run_transient(inst, smu, cfg, sample, on_point=on_point,
                                 should_stop=should_stop, log=log, light_events=events,
                                 light_control=light_control if cfg.cycle_enabled else None)

        self.worker = Worker(self, job, on_point=self._on_point, on_done=self._on_done,
                             on_error=self._on_error, on_log=self.session.log)
        self._set_running(True)
        s = self.session.settings
        s["transient"] = {"bias": cfg.bias, "duration": cfg.duration, "interval": cfg.interval}
        self.session.save()
        self.worker.start()

    def stop(self):
        if self.worker is not None and self.worker.running:
            self.worker.stop()

    def _on_point(self, idx, t, v, i):
        self._last_t = t
        self.plot.append("i", t, i)
        self.readout.set("t = {0:8.2f} s   I = {1:>12.6g} A".format(t, i))

    def _on_done(self, ds):
        self._set_running(False)
        self._last = ds
        if len(ds) == 0:
            return
        self.session.add_dataset(ds)
        self.plot.set_spans(analysis.light_spans(ds))
        m = analysis.transient_metrics(ds.t, ds.i)
        rows = m.as_rows()
        power = ds.effective_power_w()
        if power and analysis.isfinite(m.i_on):
            det = analysis.detector_metrics(
                m.i_off, m.i_on, wavelength_nm=ds.wavelength_nm, optical_power_w=power,
                area_cm2=ds.area_cm2, bias_v=ds.settings.get("transient", {}).get("bias", 0.0))
            rows = rows + [("-", "-")] + det.as_rows()[8:]
        self.metrics.set_rows(rows)
        for w in m.warnings:
            self.session.log("Uyari: " + w)
        if self.autosave.get():
            folder = self.session.settings.get("data_dir", ".")
            try:
                if not os.path.isdir(folder):
                    os.makedirs(folder)
                self.session.log("Kaydedildi: {0}".format(ds.to_csv(suggest_filename(ds, folder))))
            except (IOError, OSError) as exc:
                self.session.log("Otomatik kayit basarisiz: {0}".format(exc))

    def _on_error(self, text):
        self._set_running(False)
        self.session.log("HATA: " + text.splitlines()[0])
        error(self, "Olcum hatasi", text[:1500])

    def _set_running(self, running):
        self.btn_start.config(state="disabled" if running else "normal")
        self.btn_stop.config(state="normal" if running else "disabled")
        manual = "normal" if (running and not self.cycle.get()) else "disabled"
        self.btn_on.config(state=manual)
        self.btn_off.config(state=manual)
        self.session.set_busy(running)

    def save_last(self):
        if self._last is None or len(self._last) == 0:
            warn(self, "Veri yok", "Once bir kayit alin.")
            return
        folder = self.session.settings.get("data_dir", ".")
        path = filedialog.asksaveasfilename(
            parent=self, title="Kaydi kaydet", initialdir=folder,
            initialfile=os.path.basename(suggest_filename(self._last, folder)),
            defaultextension=".csv", filetypes=[("CSV dosyalari", "*.csv")])
        if path:
            self._last.to_csv(path)
            self.session.log("Kaydedildi: {0}".format(path))
