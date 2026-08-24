#!/usr/bin/env python3
"""UV fotodedektor olcum arayuzunu baslatir.

Kullanim:
    python run_gui.py              # normal (cihaza baglanilir)
    python run_gui.py --simulate   # cihazsiz deneme modu
"""

import sys

from uvpd.gui import run

if __name__ == "__main__":
    sys.exit(run())
