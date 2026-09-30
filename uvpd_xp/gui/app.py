# -*- coding: utf-8 -*-
"""Ana pencere: sekmeler, oturum olcum listesi ve gunluk paneli."""

import os
import sys
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, ttk

from .. import __version__
from ..dataset import Dataset, suggest_filename
from .analysis_tab import AnalysisTab
from .common import Session, error, info, warn
from .connection_tab import ConnectionTab
from .iv_tab import IVTab
from .transient_tab import TransientTab

TITLE = "UV Fotodedektor Olcumu - Keithley 2636 / Adapter Box C 10 (XP surumu)"


class App(object):
    def __init__(self, root, simulate=False):
        self.root = root
        self.session = Session(simulate=simulate)
        root.title(TITLE)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry("{0}x{1}".format(min(1240, sw - 20), min(820, sh - 60)))
        root.minsize(800, 560)
        self._style()

        # Ust cubuk: baglanti durumu + HER SEKMEDEN erisilen acil durdurma.
        # Ust ve alt cubuklar, kucuk ekranda sikismasinlar diye ONCE paketlenir.
        self.status = tk.StringVar(root, value="Bagli degil")
        self.busy_label = tk.StringVar(root, value="Hazir")
        topbar = ttk.Frame(root, padding=(4, 2))
        topbar.pack(fill="x", side="top")
        self.btn_estop = tk.Button(topbar, text="  CIKISI HEMEN KAPAT  ", bg="#c62828", fg="white",
                                   activebackground="#8e0000", activeforeground="white",
                                   font=("Tahoma", 9, "bold"), command=self.emergency_off)
        self.btn_estop.pack(side="right")
        ttk.Label(topbar, textvariable=self.status, font=("Tahoma", 9, "bold")).pack(side="left")
        ttk.Label(topbar, text="   |   ").pack(side="left")
        ttk.Label(topbar, textvariable=self.busy_label).pack(side="left")

        outer = ttk.Panedwindow(root, orient="vertical")
        outer.pack(fill="both", expand=True)
        top = ttk.Panedwindow(outer, orient="horizontal")

        self.nb = ttk.Notebook(top)
        self.tab_conn = ConnectionTab(self.nb, self.session)
        self.tab_an = AnalysisTab(self.nb, self.session)
        self.tab_iv = IVTab(self.nb, self.session, on_compare=self._compare_requested)
        self.tab_tr = TransientTab(self.nb, self.session)
        self.nb.add(self.tab_conn, text=" 1 - Baglanti ve Ayarlar ")
        self.nb.add(self.tab_iv, text=" 2 - I-V Olcumu ")
        self.nb.add(self.tab_tr, text=" 3 - Zaman Tepkisi ")
        self.nb.add(self.tab_an, text=" 4 - Karsilastirma ve Analiz ")
        top.add(self.nb, weight=5)

        side = ttk.Labelframe(top, text="Olcumler", padding=4)
        lf = ttk.Frame(side)
        lf.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(lf, width=22, activestyle="none", selectmode="extended",
                                  exportselection=False)
        lxs = ttk.Scrollbar(lf, orient="horizontal", command=self.listbox.xview)
        self.listbox.configure(xscrollcommand=lxs.set)
        self.listbox.pack(side="top", fill="both", expand=True)
        lxs.pack(side="top", fill="x")
        for txt, cmd in (("Yukle...", self.load_dataset),
                         ("Kaydet...", self.save_selected),
                         ("Sil", self.delete_selected)):
            ttk.Button(side, text=txt, command=cmd).pack(fill="x", pady=(2, 0))
        top.add(side, weight=1)
        outer.add(top, weight=5)

        logf = ttk.Labelframe(outer, text="Gunluk", padding=2)
        self.log_text = tk.Text(logf, height=5, wrap="none", font=("Courier New", 8), state="disabled")
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lsb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        lsb.pack(side="left", fill="y")
        outer.add(logf, weight=1)


        self._menu()
        s = self.session
        s.on("log", self._append_log)
        s.on("status", self.status.set)
        s.on("datasets", self._refresh_list)
        s.on("busy", self._on_busy)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        s.log("UV fotodedektor arayuzu (XP surumu) v{0} hazir. Python {1}".format(
            __version__, sys.version.split()[0]))
        if s.simulated:
            s.log("Simulasyon modu: gercek cihaz kullanilmiyor.")

    # ------------------------------------------------------------------
    def _style(self):
        # Fare tekerlegi, uzerinden gecilen acilir listenin degerini
        # DEGISTIRMESIN (kanal / kaynak tipi kazara degismesin).
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.root.unbind_class("TCombobox", seq)
            except tk.TclError:
                pass
        style = ttk.Style(self.root)
        names = style.theme_names()
        for th in ("xpnative", "winnative", "vista", "clam"):
            if th in names:
                try:
                    style.theme_use(th)
                except tk.TclError:
                    continue
                break

    def _menu(self):
        m = tk.Menu(self.root)
        mf = tk.Menu(m, tearoff=0)
        mf.add_command(label="Olcum yukle (CSV)...", command=self.load_dataset)
        mf.add_command(label="Secili olcumu kaydet...", command=self.save_selected)
        mf.add_separator()
        mf.add_command(label="Veri klasorunu sec...", command=self.choose_data_dir)
        mf.add_separator()
        mf.add_command(label="Cikis", command=self.on_close)
        m.add_cascade(label="Dosya", menu=mf)
        mh = tk.Menu(m, tearoff=0)
        mh.add_command(label="Surucu teshisi", command=self.tab_conn.run_diag)
        mh.add_command(label="Hakkinda", command=self._about)
        m.add_cascade(label="Yardim", menu=mh)
        self.root.config(menu=m)

    def _about(self):
        info(self.root, "Hakkinda",
             "UV Fotodedektor Olcum Arayuzu - XP surumu v{0}\n\n"
             "Keithley 2636 (TSP) + Adapter Box C 10\n"
             "Python {1} / Tk {2}\n\n"
             "Harici paket gerektirmez: GPIB icin gpib-32.dll,\n"
             "VISA icin visa32.dll dogrudan kullanilir.\n\n"
             "Veri klasoru: {3}".format(__version__, sys.version.split()[0], tk.TkVersion,
                                        self.session.settings.get("data_dir")))

    # ------------------------------------------------------------------
    def _append_log(self, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        t = self.log_text
        t.config(state="normal")
        t.insert("end", "[{0}] {1}\n".format(stamp, text))
        lines = int(t.index("end-1c").split(".")[0])
        if lines > 2000:
            t.delete("1.0", "{0}.0".format(lines - 2000))
        t.see("end")
        t.config(state="disabled")

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for k, ds in enumerate(self.session.datasets):
            self.listbox.insert("end", "{0}. {1} | {2} | {3} nk".format(k + 1, ds.label, ds.kind, len(ds)))

    def _on_busy(self, busy):
        self.busy_label.set("Olcum suruyor..." if busy else "Hazir")
        c = self.tab_conn
        if busy:
            # olcum sirasinda baglanti degistirilemez
            for b in (c.btn_scan, c.btn_connect, c.btn_disconnect):
                b.config(state="disabled")
        else:
            c._on_connection(self.session.connected)

    def emergency_off(self):
        """Acil durdurma: olcum suruyorsa durdur (cikis dongu sonunda kapanir),
        degilse cikisi hemen kapat."""
        s = self.session
        if s.busy:
            s.emit("stop_request")
            s.log("ACIL DURDURMA: olcum durduruluyor, cikis kapatilacak.")
            return
        if s.instrument is None:
            s.log("Acil durdurma: cihaz bagli degil.")
            return
        try:
            s.instrument.output_off()
            s.log("Cikis kapatildi (acil durdurma).")
        except Exception as exc:
            error(self.root, "Hata", str(exc))

    def _compare_requested(self, dark, light):
        self.nb.select(self.tab_an)
        self.tab_an.select_datasets(dark, light)

    # ------------------------------------------------------------------
    def load_dataset(self):
        paths = filedialog.askopenfilenames(parent=self.root, title="Olcum dosyalari sec",
                                            initialdir=self.session.settings.get("data_dir", "."),
                                            filetypes=[("CSV dosyalari", "*.csv"), ("Tum dosyalar", "*.*")])
        if isinstance(paths, str):          # bazi Tk surumleri tek string dondurur
            paths = self.root.tk.splitlist(paths)
        for p in paths:
            try:
                self.session.add_dataset(Dataset.from_csv(p))
            except Exception as exc:
                error(self.root, "Okuma hatasi", "{0}\n\n{1}".format(p, exc))

    def save_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            warn(self.root, "Secim yok", "Listeden bir olcum secin.")
            return
        folder = self.session.settings.get("data_dir", ".")
        for idx in sel:
            ds = self.session.dataset(int(idx))
            if ds is None:
                continue
            path = filedialog.asksaveasfilename(
                parent=self.root, title="Kaydet: " + ds.label, initialdir=folder,
                initialfile=os.path.basename(suggest_filename(ds, folder)),
                defaultextension=".csv", filetypes=[("CSV dosyalari", "*.csv")])
            if path:
                ds.to_csv(path)
                self.session.log("Kaydedildi: {0}".format(path))

    def delete_selected(self):
        for idx in sorted((int(i) for i in self.listbox.curselection()), reverse=True):
            self.session.remove_dataset(idx)

    def choose_data_dir(self):
        d = filedialog.askdirectory(parent=self.root, title="Veri klasoru sec",
                                    initialdir=self.session.settings.get("data_dir", "."))
        if d:
            self.session.settings["data_dir"] = d
            self.session.save()
            self.session.log("Veri klasoru: {0}".format(d))

    def on_close(self):
        for tab in (self.tab_iv, self.tab_tr):
            w = getattr(tab, "worker", None)
            if w is not None and w.running:
                w.stop()
                w.join(3.0)
        self.session.disconnect()
        self.session.save()
        # bekleyen zamanlayicilar (grafik yenileme, isci yoklama) iptal edilsin
        try:
            for aid in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.after_cancel(aid)
        except tk.TclError:
            pass
        self.root.destroy()


def run(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="UV fotodedektor olcum arayuzu (XP surumu)")
    ap.add_argument("--simulate", action="store_true", help="Cihazsiz simulasyon modu")
    args = ap.parse_args(argv)
    root = tk.Tk()
    App(root, simulate=args.simulate)
    root.mainloop()
    return 0
