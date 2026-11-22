"""Patched, vendored dmm-search3 client.

Changes vs upstream 0.3:
* no hard pin to requests==2.21.0 (works with requests 2.28+ / Python 3.11+)
* exports both ``DMM`` and the legacy ``API`` alias used by this bot
* default timeout and a reusable Session instead of a bare requests.get
"""

from .DMM import DMM

API = DMM

__all__ = ["API", "DMM"]
