#!/usr/bin/env python3
"""Entry point: ``python3 scripts/run_gui.py``.

Wires the kascade / xigma_i source directories onto sys.path (see
compton_guide/bootstrap.py) before importing the app, so this works from a
plain checkout with no pip install of either physics package required.
"""

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from compton_guide import bootstrap
bootstrap.setup_paths()

from compton_guide.app import main

if __name__ == "__main__":
    main()
