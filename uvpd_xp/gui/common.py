# -*- coding: utf-8 -*-
"""Arayuz ortak bilesenleri: oturum durumu, arka plan isci, form yardimcilari."""

import queue
import threading
import traceback

import tkinter as tk
from tkinter import messagebox, ttk

from ..config import load_settings, save_settings
from ..instrument import SmuConfig, create_instrument


# ==========================================================================
# Oturum: cihaz + olcum listesi + olay yayini
# ==========================================================================
class Session(object):
    """Sekmeler bu nesne uzerinden haberlesir. Tum olaylar ana is parcaciginda."""

    def __init__(self, simulate=False):
        self.settings = load_settings()
        if simulate:
            self.settings["backend"] = "sim"
            self.settings["resource"] = "SIM::UVPD::INSTR"
        self.instrument = None
        self.datasets = []
        self.busy = False
        self._listeners = {}

    # ---------------- olaylar ----------------
    def on(self, event, callback):
        self._listeners.setdefault(event, []).append(callback)

    def emit(self, event, *args):
        for cb in list(self._listeners.get(event, [])):
            try:
                cb(*args)
            except Exception:
                traceback.print_exc()

    def log(self, text):
        self.emit("log", str(text))

    def set_busy(self, value):
        if bool(value) != self.busy:
            self.busy = bool(value)
            self.emit("busy", self.busy)

    # ---------------- cihaz ----------------
    @property
    def connected(self):
        return self.instrument is not None and self.instrument.connected

    @property
    def simulated(self):
        return self.settings.get("backend") == "sim"

    def connect(self, resource, backend):
        self.disconnect()
        inst = create_instrument(resource, backend=backend)
        idn = inst.connect()
        self.instrument = inst
        self.settings["resource"] = resource
        self.settings["backend"] = backend
        self.save()
        self.log("Baglandi ({0}): {1}".format(getattr(inst, "transport_kind", backend), idn))
        self.emit("connection", True)
        self.emit("status", "Bagli: {0}".format(resource))
        return idn

    def disconnect(self):
        if self.instrument is not None:
            try:
                self.instrument.close()
            except Exception as exc:
                self.log("Kapatma hatasi: {0}".format(exc))
            self.instrument = None
            self.log("Baglanti kapatildi.")
            self.emit("connection", False)
            self.emit("status", "Bagli degil")

    # ---------------- olcumler ----------------
    def add_dataset(self, ds):
        self.datasets.append(ds)
        self.emit("datasets")
        self.log("Olcum eklendi: {0} ({1} nokta)".format(ds.label, len(ds)))

    def remove_dataset(self, index):
        if 0 <= index < len(self.datasets):
            ds = self.datasets.pop(index)
            self.emit("datasets")
            self.log("Olcum silindi: {0}".format(ds.label))

    def dataset(self, index):
        if index is not None and 0 <= index < len(self.datasets):
            return self.datasets[index]
        return None

    def smu_config(self):
        s = self.settings
        return SmuConfig(
            channel=s.get("channel", "a"),
            source_func=s.get("source_func", "voltage"),
            compliance=float(s.get("compliance", 1e-3)),
            nplc=float(s.get("nplc", 1.0)),
            filter_count=int(s.get("filter_count", 1)),
            four_wire=bool(s.get("four_wire", False)),
            low_range_i=float(s.get("low_range_i", 1e-9)),
            auto_zero=s.get("auto_zero", "auto"),
            high_capacitance=bool(s.get("high_capacitance", False)),
        )

    def save(self):
        try:
            save_settings(self.settings)
        except (IOError, OSError) as exc:
            self.log("Ayarlar kaydedilemedi: {0}".format(exc))


# ==========================================================================
# Arka plan isci (olcumler arayuzu dondurmesin diye)
# ==========================================================================
class Worker(object):
    """func(on_point, should_stop, log) -> Dataset fonksiyonunu is parcaciginda calistirir.

    Tk thread-safe olmadigi icin sonuclar kuyruk ile ana is parcacigina
    tasinir ve ``after`` ile yoklanir.
    """

    POLL_MS = 50

    def __init__(self, root, func, on_point=None, on_done=None, on_error=None, on_log=None):
        self.root = root
        self.func = func
        self.on_point = on_point
        self.on_done = on_done
        self.on_error = on_error
        self.on_log = on_log
        self._q = queue.Queue()
        self._stop = threading.Event()
        self._finished = False
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True

    def start(self):
        self._thread.start()
        self.root.after(self.POLL_MS, self._poll)

    def stop(self):
        self._stop.set()

    @property
    def running(self):
        return not self._finished

    def _run(self):
        q = self._q
        try:
            ds = self.func(on_point=lambda *a: q.put(("point", a)),
                           should_stop=self._stop.is_set,
                           log=lambda m: q.put(("log", m)))
            q.put(("done", ds))
        except Exception as exc:
            q.put(("error", "{0}\n\n{1}".format(exc, traceback.format_exc())))

    def _poll(self):
        for _ in range(2000):
            try:
                kind, payload = self._q.get_nowait()
            except queue.Empty:
                break
            try:
                if kind == "point" and self.on_point:
                    self.on_point(*payload)
                elif kind == "log" and self.on_log:
                    self.on_log(payload)
                elif kind == "done":
                    self._finished = True
                    if self.on_done:
                        self.on_done(payload)
                elif kind == "error":
                    self._finished = True
                    if self.on_error:
                        self.on_error(payload)
            except Exception:
                traceback.print_exc()
        if not self._finished:
            try:
                self.root.after(self.POLL_MS, self._poll)
            except tk.TclError:
                self._finished = True          # pencere kapatildi

    def join(self, timeout=None):
        self._thread.join(timeout)


# ==========================================================================
# Form yardimcilari
# ==========================================================================
def parse_float(text, default=0.0):
    try:
        return float(str(text).strip().replace(",", "."))
    except ValueError:
        return default


class SciVar(object):
    """Bilimsel gosterimi kabul eden sayi alani (1e-9, -2.5 ...)."""

    def __init__(self, master, value=0.0, width=14):
        self.var = tk.StringVar(master, value="{0:g}".format(float(value)))
        self.widget = ttk.Entry(master, textvariable=self.var, width=width, justify="right")

    def get(self, default=0.0):
        return parse_float(self.var.get(), default)

    def set(self, value):
        self.var.set("{0:g}".format(float(value)))

    def trace(self, cb):
        self.var.trace("w", lambda *a: cb())


class ComboVar(object):
    """Salt okunur acilir liste: gorunen metin <-> deger eslemesi."""

    def __init__(self, master, items, current=None, width=28):
        self.items = list(items)
        self.widget = ttk.Combobox(master, state="readonly", width=width,
                                   values=[t for t, _ in self.items])
        self.set(current if current is not None else (self.items[0][1] if self.items else None))

    def get(self):
        idx = self.widget.current()
        if 0 <= idx < len(self.items):
            return self.items[idx][1]
        return None

    def set(self, value):
        for k, (_t, v) in enumerate(self.items):
            if v == value:
                self.widget.current(k)
                return
        if self.items:
            self.widget.current(0)

    def set_items(self, items, keep=True):
        cur = self.get() if keep else None
        self.items = list(items)
        self.widget["values"] = [t for t, _ in self.items]
        if cur is not None and any(v == cur for _, v in self.items):
            self.set(cur)
        elif self.items:
            self.widget.current(0)
        else:
            self.widget.set("")

    def bind_change(self, cb):
        # add="+" : ayni olaya birden fazla dinleyici baglanabilsin
        self.widget.bind("<<ComboboxSelected>>", lambda e: cb(), add="+")


class Form(ttk.Labelframe):
    """Etiket + alan satirlarindan olusan cerceve."""

    def __init__(self, master, title):
        ttk.Labelframe.__init__(self, master, text=title, padding=(6, 4))
        self._row = 0
        self.columnconfigure(1, weight=1)

    def _add(self, label, widget):
        ttk.Label(self, text=label).grid(row=self._row, column=0, sticky="e", padx=(0, 6), pady=1)
        widget.grid(row=self._row, column=1, sticky="we", pady=1)
        self._row += 1
        return widget

    def sci(self, label, value, width=14):
        v = SciVar(self, value, width)
        self._add(label, v.widget)
        return v

    def text(self, label, value="", width=22):
        var = tk.StringVar(self, value=value)
        self._add(label, ttk.Entry(self, textvariable=var, width=width))
        return var

    def combo(self, label, items, current=None, width=26):
        c = ComboVar(self, items, current, width)
        self._add(label, c.widget)
        return c

    def check(self, label, value=False):
        var = tk.BooleanVar(self, value=bool(value))
        self._add(label, ttk.Checkbutton(self, variable=var))
        return var

    def spin(self, label, value, lo=0, hi=100000, width=8):
        var = tk.StringVar(self, value=str(int(value)))
        sb = tk.Spinbox(self, from_=lo, to=hi, textvariable=var, width=width, justify="right")
        self._add(label, sb)
        return IntField(var, int(value), lo, hi)

    def value_label(self, label, text="-"):
        var = tk.StringVar(self, value=text)
        self._add(label, ttk.Label(self, textvariable=var))
        return var

    def full(self, widget, pady=3):
        widget.grid(row=self._row, column=0, columnspan=2, sticky="we", pady=pady)
        self._row += 1
        return widget


class IntField(object):
    def __init__(self, var, default, lo, hi):
        self.var = var
        self.default = default
        self.lo = lo
        self.hi = hi

    def get(self):
        try:
            v = int(float(self.var.get()))
        except ValueError:
            v = self.default
        return max(self.lo, min(self.hi, v))

    def set(self, value):
        self.var.set(str(int(value)))

    def trace(self, cb):
        self.var.trace("w", lambda *a: cb())


class ScrollFrame(ttk.Frame):
    """Dikey kaydirilabilir cerceve. Icerik ``.inner`` icine eklenir.

    Kucuk ekranlarda (XP'de 1024x768) sol panellerin kesilmemesi icin.
    Kaydirma cubugu yalnizca gerektiginde gorunur.
    """

    def __init__(self, master):
        ttk.Frame.__init__(self, master)
        bg = ttk.Style().lookup("TFrame", "background") or None
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        if bg:
            self.canvas.configure(background=bg)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self._sb_visible = False
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)

    def _on_inner(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"),
                              width=self.inner.winfo_reqwidth())
        self._update_sb()

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self._win, width=event.width)
        self._update_sb()

    def _update_sb(self):
        need = self.inner.winfo_reqheight() > self.canvas.winfo_height() > 1
        if need and not self._sb_visible:
            self.vsb.pack(side="left", fill="y")
            self._sb_visible = True
        elif not need and self._sb_visible:
            self.vsb.pack_forget()
            self.canvas.yview_moveto(0)
            self._sb_visible = False

    def _wheel(self, event):
        if not self._sb_visible:
            return
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step * 2, "units")

    def _bind_wheel(self, event=None):
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", self._wheel)
        self.canvas.bind_all("<Button-5>", self._wheel)

    def _unbind_wheel(self, event=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(seq)


class KeyValueTable(ttk.Frame):
    """Iki kolonlu (Parametre / Deger) tablo. Ctrl+C secili satirlari kopyalar."""

    def __init__(self, master, height=10, headings=("Parametre", "Deger")):
        ttk.Frame.__init__(self, master)
        self.tree = ttk.Treeview(self, columns=("k", "v"), show="headings", height=height)
        self.tree.heading("k", text=headings[0])
        self.tree.heading("v", text=headings[1])
        self.tree.column("k", width=230, anchor="w")
        self.tree.column("v", width=150, anchor="e")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.tree.bind("<Control-c>", self._copy)
        self.tree.bind("<Control-C>", self._copy)

    def set_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        for k, v in rows:
            self.tree.insert("", "end", values=(k, v))

    def rows(self):
        return [tuple(self.tree.item(i, "values")) for i in self.tree.get_children()]

    def to_text(self):
        return "\n".join("{0}\t{1}".format(k, v) for k, v in self.rows())

    def _copy(self, event=None):
        sel = self.tree.selection() or self.tree.get_children()
        text = "\n".join("{0}\t{1}".format(*self.tree.item(i, "values")) for i in sel)
        self.clipboard_clear()
        self.clipboard_append(text)
        return "break"


# ==========================================================================
# Mesaj kutulari
# ==========================================================================
def info(parent, title, text):
    messagebox.showinfo(title, text, parent=parent)


def warn(parent, title, text):
    messagebox.showwarning(title, text, parent=parent)


def error(parent, title, text):
    messagebox.showerror(title, text, parent=parent)


def ask_ok(parent, title, text):
    return messagebox.askokcancel(title, text, parent=parent)
