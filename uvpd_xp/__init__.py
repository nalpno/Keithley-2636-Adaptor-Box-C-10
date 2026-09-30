# -*- coding: utf-8 -*-
"""UV fotodedektor olcum arayuzu - Windows XP / Python 3.4 surumu.

Harici paket GEREKTIRMEZ (numpy, matplotlib, PyQt, pyvisa yok):
    transport   : gpib-32.dll / visa32.dll ile ctypes uzerinden haberlesme
    instrument  : Keithley 2636 TSP surucusu
    simulator   : cihazsiz test icin sahte SMU
    measurement : I-V taramasi ve zaman tepkisi
    analysis    : karsilastirma, R, EQE, D*, NEP, rise/fall (saf Python)
    dataset     : CSV okuma/yazma (modern surumle ayni bicim)
    diag        : surucu teshisi
    gui         : Tkinter arayuzu
"""

__version__ = "1.0.0-xp"
