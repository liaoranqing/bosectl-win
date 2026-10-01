#!/usr/bin/env python3
"""Entry script for the packaged console CLI (``bosectl-cli.exe``).

The ``-cli`` suffix is not cosmetic: ``BoseCtl.exe`` and ``bosectl.exe``
lower-case to the same filename, so on Windows and macOS they would be one
file and one would silently overwrite the other whenever both are downloaded
into the same folder.

Deliberately does not import ``gui`` (or tkinter): the console build stays
small and starts instantly, and it keeps working on machines where the GUI
dependencies are unavailable.

Run it directly during development with ``python build/entry_cli.py``.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cli import main  # noqa: E402  (import after sys.path fix)

if __name__ == "__main__":
    sys.exit(main())
