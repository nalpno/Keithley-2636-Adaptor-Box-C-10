# -*- coding: utf-8 -*-
"""I-V taramasi sekmesi."""

import os

import tkinter as tk
from tkinter import filedialog, ttk

from ..dataset import DARK, LIGHT, suggest_filename
from ..measurement import SampleInfo, SweepConfig, run_sweep
from .common import Form, ScrollFrame, Worker, ask_ok, error, warn
from .plot import LOG_ABS, CanvasPlot, YScaleSelector

U_MAX, I_MAX = 60.0, 1.0      # Adapter Box C 10 sinirlari


class IVTab(ttk.Frame):
    def __init__(self, master, session, on_compare=None):
        ttk.Frame.__init__(self, master, padding=6)
        self.session = session
        self.on_compare = on_compare
        self.worker = None
        self._pending_dual = False
        self._dual_dark = None
        self._last = None
        self._key = None
        s = session.settings
        sw = s.get("sweep", {})

        sf = ScrollFrame(self)
        sf.pack(side="left", fill="y", padx=(0, 6))
        left = sf.inner
        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True)

        f1 = Form(left, "Numune ve isik kaynagi")
        f1.pack(fill="x", pady=(0, 4))
        self.sample_name = f1.text("Numune adi", s.get("sample_name", "numune"))
        self.light = f1.combo("Isik durumu", [("Karanlik", DARK), ("UV altinda", LIGHT)], DARK, width=14)
        self.wavelength = f1.sci("Dalga boyu (nm)", s.get("wavelength_nm", 365.0))
        self.power = f1.sci("Optik guc (W)", s.get("optical_power_w", 2e-6))
        self.area = f1.sci("Aktif alan (cm2)", s.get("area_cm2", 0.04))
        self.notes = f1.text("Not", "")

        f2 = Form(left, "Tarama parametreleri")
        f2.pack(fill="x", pady=(0, 4))
        self.start = f2.sci("Baslangic", sw.get("start", -2.0))
        self.stop = f2.sci("Bitis", sw.get("stop", 2.0))
        self.points = f2.spin("Nokta sayisi", sw.get("points", 101), 2, 100000)
        self.step = f2.value_label("Adim", "-")
        self.dual = f2.check("Cift yon (ileri+geri)", sw.get("dual", False))
        self.repeat = f2.spin("Tekrar", sw.get("repeat", 1), 1, 100)
        self.settle = f2.sci("Adim bekleme (s)", sw.get("settle_time", 0.05))
        self.autosave = f2.check("Bitince otomatik CSV kaydet", True)

        bf = ttk.Frame(left)
        bf.pack(fill="x", pady=(2, 4))
        self.btn_start = ttk.Button(bf, text="Taramayi baslat", command=lambda: self.start_sweep(False))
        self.btn_dual = ttk.Button(bf, text="Ikili olcum (karanlik -> UV)", command=lambda: self.start_sweep(True))
        self.btn_stop = ttk.Button(bf, text="Durdur", command=self.stop_sweep, state="disabled")
        self.btn_save = ttk.Button(bf, text="CSV kaydet", command=self.save_last)
        self.btn_clear = ttk.Button(bf, text="Grafigi temizle", command=lambda: self.plot.clear())
        self.btn_start.grid(row=0, column=0, sticky="we", padx=1, pady=1)
        self.btn_stop.grid(row=0, column=1, sticky="we", padx=1, pady=1)
        self.btn_dual.grid(row=1, column=0, columnspan=2, sticky="we", padx=1, pady=1)
        self.btn_save.grid(row=2, column=0, sticky="we", padx=1, pady=1)
        self.btn_clear.grid(row=2, column=1, sticky="we", padx=1, pady=1)
        bf.columnconfigure(0, weight=1)
        bf.columnconfigure(1, weight=1)

        self.plot = CanvasPlot(right, "Gerilim (V)", "Akim (A)")
        head = ttk.Frame(right)
        head.pack(fill="x", pady=(0, 3))
        YScaleSelector(head, self.plot, default=LOG_ABS).pack(side="left")
        self.progress = ttk.Progressbar(head, mode="determinate", length=120)
        self.progress.pack(side="left", padx=8)
        self.readout = tk.StringVar(self, value="V = -    I = -")
        ttk.Label(right, textvariable=self.readout,
                  font=("Courier New", 9, "bold")).pack(side="bottom", anchor="w", pady=(3, 0))
        self.plot.pack(fill="both", expand=True)

        for v in (self.start, self.stop, self.points):
            v.trace(self._update_step)
        self.light.bind_change(self._update_light)
        session.on("stop_request", self.stop_sweep)
        self._update_step()
        self._update_light()

    # ------------------------------------------------------------------
    def _update_step(self):
        n = max(2, self.points.get())
        step = (self.stop.get() - self.start.get()) / float(n - 1)
        unit = "V" if self.session.settings.get("source_func") == "voltage" else "A"
        self.step.set("{0:.6g} {1}".format(step, unit))

    def _update_light(self):
        st = "normal" if self.light.get() == LIGHT else "disabled"
        self.wavelength.widget.config(state=st)
        self.power.widget.config(state=st)

    def sample_info(self, light_state=None):
        return SampleInfo(
            name=self.sample_name.get().strip() or "numune",
            light_state=light_state or self.light.get(),
            wavelength_nm=self.wavelength.get(365.0),
            optical_power_w=self.power.get(0.0) or None,
            area_cm2=self.area.get(0.0) or None,
            notes=self.notes.get().strip())

    def sweep_config(self):
        return SweepConfig(start=self.start.get(), stop=self.stop.get(),
                           points=self.points.get(), dual=bool(self.dual.get()),
                           repeat=self.repeat.get(), settle_time=max(0.0, self.settle.get(0.05)))

    def _validate(self):
        s = self.session.settings
        if not self.session.connected:
            warn(self, "Cihaz bagli degil",
                 "Once 'Baglanti' sekmesinden cihaza baglanin (veya Arayuz = Simulasyon).")
            return False
        if not s.get("interlock_confirmed"):
            warn(self, "Interlock onayi yok",
                 "Baglanti sekmesinde 'INTERLOCK bagli / kapak kapali' isaretlenmeden "
                 "olcum baslatilamaz.")
            return False
        lvl = max(abs(self.start.get()), abs(self.stop.get()))
        comp = abs(float(s.get("compliance", 1e-3)))
        if s.get("source_func") == "voltage":
            if lvl > U_MAX:
                error(self, "Sinir asimi", "Adapter Box C 10 icin U_max = {0:g} V DC.".format(U_MAX))
                return False
            if comp > I_MAX:
                error(self, "Sinir asimi", "Akim limiti {0:g} A'i asamaz.".format(I_MAX))
                return False
        else:
            if lvl > I_MAX:
                error(self, "Sinir asimi", "Adapter Box C 10 icin I_max = {0:g} A DC.".format(I_MAX))
                return False
            if comp > U_MAX:
                error(self, "Sinir asimi", "Gerilim limiti {0:g} V'u asamaz.".format(U_MAX))
                return False
        return True

    # ------------------------------------------------------------------
    def start_sweep(self, dual=False, light_state=None):
        if self.worker is not None and self.worker.running:
            return
        if not self._validate():
            return
        self._pending_dual = dual
        if dual and light_state is None:
            light_state = DARK
            self._dual_dark = None

        sample = self.sample_info(light_state)
        cfg = self.sweep_config()
        smu = self.session.smu_config()
        inst = self.session.instrument
        if self.session.simulated and hasattr(inst, "set_uv"):
            inst.set_uv(sample.light_state == LIGHT)
        self._persist()

        self._key = "s{0}".format(self.plot.series_count())
        label = "Karanlik" if sample.light_state == DARK else "UV {0:g} nm".format(sample.wavelength_nm)
        self.plot.add_series(self._key, "{0} - {1}".format(sample.name, label), marker=True)
        self.progress.config(maximum=len(cfg.levels()) * max(1, cfg.repeat), value=0)

        def job(on_point, should_stop, log):
            return run_sweep(inst, smu, cfg, sample, on_point=on_point,
                             should_stop=should_stop, log=log)

        self.worker = Worker(self, job, on_point=self._on_point, on_done=self._on_done,
                             on_error=self._on_error, on_log=self.session.log)
        self._set_running(True)
        self.worker.start()

    def stop_sweep(self):
        if self.worker is not None and self.worker.running:
            self.worker.stop()
            self.session.log("Durdurma istegi gonderildi...")

    def _on_point(self, idx, t, v, i):
        self.plot.append(self._key, v, i)
        self.progress.config(value=idx + 1)
        self.readout.set("V = {0:>12.6g} V   I = {1:>12.6g} A".format(v, i))

    def _on_done(self, ds):
        self._set_running(False)
        self._last = ds
        if len(ds) == 0:
            self.session.log("Olcum bos dondu.")
            return
        self.session.add_dataset(ds)
        if self.autosave.get():
            self._autosave(ds)
        if self._pending_dual:
            if ds.light_state == DARK:
                self._dual_dark = ds
                ok = ask_ok(self, "UV kaynagini acin",
                            "Karanlik tarama tamamlandi.\n\n"
                            "Simdi {0:g} nm UV kaynagini acin ve numunenin kararli hale "
                            "gelmesini bekleyin.\n\nHazir olunca 'Tamam' tusuna basin.".format(
                                self.wavelength.get(365.0)))
                if ok:
                    self.start_sweep(True, LIGHT)
                else:
                    self._pending_dual = False
                    self._dual_dark = None
            else:
                self._pending_dual = False
                if self._dual_dark is not None and self.on_compare:
                    self.on_compare(self._dual_dark, ds)
                self._dual_dark = None

    def _on_error(self, text):
        self._set_running(False)
        self._pending_dual = False
        self.session.log("HATA: " + text.splitlines()[0])
        error(self, "Olcum hatasi", text[:1500])

    def _set_running(self, running):
        self.btn_start.config(state="disabled" if running else "normal")
        self.btn_dual.config(state="disabled" if running else "normal")
        self.btn_stop.config(state="normal" if running else "disabled")
        self.session.set_busy(running)

    # ------------------------------------------------------------------
    def _persist(self):
        s = self.session.settings
        s["sample_name"] = self.sample_name.get().strip()
        s["wavelength_nm"] = self.wavelength.get(365.0)
        s["optical_power_w"] = self.power.get(0.0)
        s["area_cm2"] = self.area.get(0.0)
        s["sweep"] = {"start": self.start.get(), "stop": self.stop.get(),
                      "points": self.points.get(), "dual": bool(self.dual.get()),
                      "repeat": self.repeat.get(), "settle_time": self.settle.get(0.05)}
        self.session.save()

    def _autosave(self, ds):
        folder = self.session.settings.get("data_dir", ".")
        try:
            if not os.path.isdir(folder):
                os.makedirs(folder)
            path = ds.to_csv(suggest_filename(ds, folder))
            self.session.log("Kaydedildi: {0}".format(path))
        except (IOError, OSError) as exc:
            self.session.log("Otomatik kayit basarisiz: {0}".format(exc))

    def save_last(self):
        if self._last is None or len(self._last) == 0:
            warn(self, "Veri yok", "Once bir tarama yapin.")
            return
        folder = self.session.settings.get("data_dir", ".")
        default = os.path.basename(suggest_filename(self._last, folder))
        path = filedialog.asksaveasfilename(parent=self, title="Olcumu kaydet",
                                            initialdir=folder, initialfile=default,
                                            defaultextension=".csv",
                                            filetypes=[("CSV dosyalari", "*.csv")])
        if path:
            self._last.to_csv(path)
            self.session.log("Kaydedildi: {0}".format(path))
