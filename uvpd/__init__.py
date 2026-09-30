"""UV fotodedektor olcum arayuzu (Keithley 2636 + Adapter Box C 10).

Alt moduller:
    instrument   : Keithley 2636 TSP surucusu (GPIB/VISA)
    simulator    : cihazsiz test icin sahte SMU
    measurement  : I-V taramasi ve zaman tepkisi motorlari
    analysis     : karanlik/aydinlik karsilastirmasi, R, EQE, D*, rise/fall
    scope        : osiloskop CSV darbe analizi (v2; 3390 + UV lamba + AMP120)
    dataset      : olcum veri kabi ve CSV okuma/yazma
    gui          : PyQt/PySide arayuzu
"""

__version__ = "2.0.0"
__all__ = ["instrument", "simulator", "measurement", "analysis", "scope", "dataset",
           "config"]
