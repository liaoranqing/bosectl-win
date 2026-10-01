"""View registry for the main window.

Order matters: the first entry is the landing page, and every later entry
appears in the navigation rail in this sequence.
"""

from __future__ import annotations

from .about import AboutView
from .advanced import AdvancedView
from .audio import AudioView
from .base import Capabilities, View
from .connect import ConnectView
from .device import DeviceView
from .modes import ModesView

#: ``(view key, view class)`` pairs, in navigation order.
VIEWS = (
    ("connect", ConnectView),
    ("audio", AudioView),
    ("modes", ModesView),
    ("device", DeviceView),
    ("advanced", AdvancedView),
    ("about", AboutView),
)

__all__ = [
    "VIEWS", "View", "Capabilities",
    "ConnectView", "AudioView", "ModesView", "DeviceView", "AdvancedView",
    "AboutView",
]
