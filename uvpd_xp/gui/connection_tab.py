# -*- coding: utf-8 -*-
"""Baglanti, SMU ayarlari, guvenlik ve kablolama sekmesi."""

import tkinter as tk
from tkinter import ttk

from .. import transport as tr
from ..config import load_wiring
from ..diag import diagnose
from ..instrument import CURRENT_RANGES
from .common import Form, ScrollFrame, error, warn

SIM_RESOURCE = "SIM::UVPD::INSTR"


def connect_error_hint(text):
    """Hata metnine gore somut yonlendirme."""
    t = text.upper()
    if "ENOL" in t:
        return ("Bu GPIB adresinde cihaz yok.\n"
                "- Keithley acik mi, GPIB kablosu iki uctan da takili mi?\n"
                "- Adres dogru mu? (Keithley: MENU > COMMUNICATION > GPIB, fabrika 26)")
    if "EABO" in t or "ZAMAN ASIMI" in t or "TMO" in t:
        return ("Cihaz cevap vermedi (zaman asimi).\n"
                "- Baska bir program (LabVIEW vb.) cihazi kullaniyor olabilir; kapatin.\n"
                "- Keithley'i kapatip acin ve tekrar deneyin.")
    if "ENEB" in t:
        return ("GPIB karti/adaptoru bulunamadi.\n"
                "- USB-GPIB adaptoru takili mi? Aygit Yoneticisi'nde gorunuyor mu?\n"
                "- Adaptorun surucusu kurulu mu?")
    if "YUKLENEMEDI" in t or "YALNIZCA WINDOWS" in t:
        return ("Surucu DLL'i bulunamadi. 'Teshis' dugmesi hangi surucunun "
                "eksik oldugunu gosterir.")
    if "RSRC_NFOUND" in t or "0XBFFF0011" in t:
        return ("VISA bu adresi bulamadi. 'Kaynaklari tara' ile bulunan bir adresi "
                "secin ya da Arayuz olarak 'GPIB - gpib-32.dll' deneyin.")
    return "Ayrintili bilgi icin 'Teshis' dugmesini kullanin."


class ConnectionTab(ttk.Frame):
    def __init__(self, master, session):
        ttk.Frame.__init__(self, master, padding=6)
        self.session = session
        s = session.settings

        sf = ScrollFrame(self)
        sf.pack(side="left", fill="y", padx=(0, 6))
        left = sf.inner
        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True)

        # ---------------- 1) baglanti ----------------
        f1 = Form(left, "1) Cihaz baglantisi")
        f1.pack(fill="x", pady=(0, 6))
        self.backend = f1.combo("Arayuz", tr.BACKEND_LABELS, s.get("backend", "auto"), width=34)
        self.resource_var = tk.StringVar(self, value=s.get("resource", "GPIB0::26::INSTR"))
        self.resource = ttk.Combobox(f1, textvariable=self.resource_var, width=34)
        f1._add("Kaynak", self.resource)
        f1.full(ttk.Label(f1, foreground="#6b6b6b",
                          text="Ornek: GPIB0::26::INSTR  (Keithley fabrika GPIB adresi 26)"))

        btns = ttk.Frame(f1)
        self.btn_scan = ttk.Button(btns, text="Kaynaklari tara", command=self.scan)
        self.btn_diag = ttk.Button(btns, text="Teshis", command=self.run_diag)
        self.btn_connect = ttk.Button(btns, text="Bagla", command=self.connect)
        self.btn_disconnect = ttk.Button(btns, text="Baglantiyi kes",
                                         command=self.session.disconnect, state="disabled")
        for b in (self.btn_scan, self.btn_diag, self.btn_connect, self.btn_disconnect):
            b.pack(side="left", padx=(0, 4))
        f1.full(btns, pady=4)
        self.idn = f1.value_label("Cihaz kimligi", "-")

        # ---------------- 2) SMU ----------------
        f2 = Form(left, "2) SMU olcum ayarlari")
        f2.pack(fill="x", pady=(0, 6))
        self.channel = f2.combo("SMU kanali", [("Kanal A", "a"), ("Kanal B", "b")],
                                s.get("channel", "a"))
        self.source_func = f2.combo("Kaynak tipi",
                                    [("Gerilim kaynagi / akim olc (V->I)", "voltage"),
                                     ("Akim kaynagi / gerilim olc (I->V)", "current")],
                                    s.get("source_func", "voltage"))
        self.compliance = f2.sci("Limit (compliance)", s.get("compliance", 1e-3))
        self.nplc = f2.sci("NPLC (0.001-25)", s.get("nplc", 1.0))
        self.filter_count = f2.spin("Filtre (ortalama) sayisi", s.get("filter_count", 1), 1, 100)
        self.low_range = f2.combo("Otomatik kademe alt siniri",
                                  [("{0:g} A".format(r), r) for r in CURRENT_RANGES[:8]],
                                  s.get("low_range_i", 1e-9))
        self.four_wire = f2.check("4 uclu (remote sense)", s.get("four_wire", False))
        self.auto_zero = f2.combo("Auto-zero", [("Otomatik", "auto"), ("Bir kez", "once"),
                                                ("Kapali", "off")], s.get("auto_zero", "auto"))
        self.high_c = f2.check("Yuksek kapasite modu", s.get("high_capacitance", False))
        f2.full(ttk.Label(f2, foreground="#6b6b6b",
                          text="Limit: gerilim kaynaginda akim [A], akim kaynaginda gerilim [V]"))

        # ---------------- 3) guvenlik ----------------
        f3 = Form(left, "3) Guvenlik")
        f3.pack(fill="x")
        lim = load_wiring().get("limitler", {})
        f3.full(ttk.Label(f3, foreground="#a04000",
                          text="Adapter Box C 10: U_max = {0:g} V DC, I_max = {1:g} A DC".format(
                              lim.get("u_max_v", 60), lim.get("i_max_a", 1))))
        self.interlock = f3.check("INTERLOCK bagli / kapak kapali", s.get("interlock_confirmed", False))
        f3.full(ttk.Label(f3, foreground="#6b6b6b",
                          text="Acil durdurma: pencerenin sag ustundeki kirmizi dugme\n"
                               "(her sekmeden erisilebilir)."))

        # ---------------- 4) kablolama ----------------
        f4 = ttk.Labelframe(right, text="4) Kablolama haritasi (config/wiring.json)", padding=4)
        f4.pack(fill="both", expand=True)
        cols = ("smu", "kablo", "kutu", "not")
        self.wiring = ttk.Treeview(f4, columns=cols, show="headings", height=10)
        for col, title, w in zip(cols, ("Keithley 2636", "Kablo", "Adapter Box C 10", "Not"),
                                 (170, 150, 110, 360)):
            self.wiring.heading(col, text=title)
            self.wiring.column(col, width=w, anchor="w")
        sb = ttk.Scrollbar(f4, orient="vertical", command=self.wiring.yview)
        hsb = ttk.Scrollbar(f4, orient="horizontal", command=self.wiring.xview)
        self.wiring.configure(yscrollcommand=sb.set, xscrollcommand=hsb.set)
        self.wiring.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="we")
        f4.rowconfigure(0, weight=1)
        f4.columnconfigure(0, weight=1)
        for row in load_wiring().get("baglantilar", []):
            self.wiring.insert("", "end", values=(row.get("smu", ""), row.get("kablo", ""),
                                                  row.get("kutu", ""), row.get("not", "")))

        # ---------------- olaylar ----------------
        for c in (self.channel, self.source_func, self.low_range, self.auto_zero, self.backend):
            c.bind_change(self.push)
        for v in (self.compliance, self.nplc, self.filter_count):
            v.trace(self.push)
        for v in (self.four_wire, self.high_c, self.interlock):
            v.trace("w", lambda *a: self.push())
        self.backend.bind_change(self._on_backend)
        session.on("connection", self._on_connection)
        self.push()

    # ------------------------------------------------------------------
    def push(self):
        s = self.session.settings
        s["backend"] = self.backend.get()
        s["channel"] = self.channel.get()
        s["source_func"] = self.source_func.get()
        s["compliance"] = self.compliance.get(1e-3)
        s["nplc"] = self.nplc.get(1.0)
        s["filter_count"] = self.filter_count.get()
        s["low_range_i"] = float(self.low_range.get())
        s["four_wire"] = bool(self.four_wire.get())
        s["auto_zero"] = self.auto_zero.get()
        s["high_capacitance"] = bool(self.high_c.get())
        s["interlock_confirmed"] = bool(self.interlock.get())

    def _on_backend(self):
        if self.backend.get() == tr.BACKEND_SIM:
            self.resource_var.set(SIM_RESOURCE)
        elif self.resource_var.get().upper().startswith("SIM"):
            self.resource_var.set("GPIB0::26::INSTR")

    def _busy_cursor(self, on):
        try:
            self.winfo_toplevel().config(cursor="watch" if on else "")
            self.update_idletasks()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    def scan(self):
        backend = self.backend.get()
        self._busy_cursor(True)
        try:
            if backend == tr.BACKEND_SIM:
                found, notes = [SIM_RESOURCE], ["Simulasyon"]
            elif backend == tr.BACKEND_GPIB:
                found, notes = tr.gpib_scan(), ["gpib-32.dll"]
            elif backend == tr.BACKEND_VISA:
                found, notes = tr.visa_scan(), ["visa32.dll"]
            else:
                found, notes = tr.scan_all()
        except Exception as exc:
            self._busy_cursor(False)
            self.session.log("Tarama hatasi: {0}".format(exc))
            error(self, "Tarama hatasi", "{0}\n\n{1}".format(exc, connect_error_hint(str(exc))))
            return
        self._busy_cursor(False)
        for n in notes:
            self.session.log("Tarama - " + n)
        if not found:
            warn(self, "Kaynak yok",
                 "Hicbir cihaz bulunamadi.\n\nKeithley acik ve GPIB kablosu takili mi?\n"
                 "Ayrinti icin 'Teshis' dugmesini kullanin.")
            return
        self.resource["values"] = found
        if self.resource_var.get() not in found:
            self.resource_var.set(found[0])
        self.session.log("{0} kaynak bulundu: {1}".format(len(found), ", ".join(found)))
        self.session.emit("status", "{0} kaynak bulundu".format(len(found)))

    def connect(self):
        self.push()
        resource = self.resource_var.get().strip()
        backend = self.backend.get()
        if not resource:
            warn(self, "Kaynak yok", "Bir kaynak adresi girin veya 'Kaynaklari tara' deyin.")
            return
        self._busy_cursor(True)
        try:
            idn = self.session.connect(resource, backend)
        except Exception as exc:
            self._busy_cursor(False)
            self.session.log("Baglanti hatasi ({0}): {1}".format(resource, exc))
            error(self, "Baglanti hatasi",
                  "{0} adresine baglanilamadi.\n\n{1}\n\n{2}".format(
                      resource, connect_error_hint(str(exc)), exc))
            return
        self._busy_cursor(False)
        self.idn.set(idn)

    def _on_connection(self, connected):
        self.btn_connect.config(state="disabled" if connected else "normal")
        self.btn_disconnect.config(state="normal" if connected else "disabled")
        self.btn_scan.config(state="disabled" if connected else "normal")
        if not connected:
            self.idn.set("-")

    # ------------------------------------------------------------------
    def run_diag(self):
        self._busy_cursor(True)
        try:
            rep = diagnose()
        finally:
            self._busy_cursor(False)
        self.session.log("Teshis calistirildi.")

        top = tk.Toplevel(self)
        top.title("Surucu / baglanti teshisi")
        top.geometry("720x480")
        txt = tk.Text(top, wrap="word", font=("Courier New", 9))
        txt.insert("1.0", rep.text)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True, padx=6, pady=6)
        row = ttk.Frame(top)
        row.pack(fill="x", padx=6, pady=(0, 6))

        def copy():
            top.clipboard_clear()
            top.clipboard_append(rep.text)

        ttk.Button(row, text="Panoya kopyala", command=copy).pack(side="left")
        if rep.backend is not None:
            def apply():
                self.backend.set(rep.backend)
                if rep.resources:
                    self.resource["values"] = rep.resources
                    self.resource_var.set(rep.resources[0])
                self.push()
                self.session.log("Teshis onerisi uygulandi: arayuz={0}".format(rep.backend))
                top.destroy()
            ttk.Button(row, text="Oneriyi uygula", command=apply).pack(side="left", padx=6)
        ttk.Button(row, text="Kapat", command=top.destroy).pack(side="right")
