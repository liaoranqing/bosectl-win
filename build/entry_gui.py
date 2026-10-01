#!/usr/bin/env python3
"""Entry script for the packaged windowed GUI (``BoseCtl.exe``).

PyInstaller analyses this file to find the imports to freeze. Keeping the
entry point this thin matters: everything real lives in ``gui`` and
``pybmap``, which are also importable normally, so the frozen build and the
source tree exercise the same code paths.

Run it directly during development with ``python build/entry_gui.py``.
"""

import os
import sys

# Make the repository root importable when this file is executed straight
# from a source checkout. In a frozen build the modules are already bundled
# and this is a harmless no-op.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.app import main  # noqa: E402  (import after sys.path fix)

if __name__ == "__main__":
    sys.exit(main())
