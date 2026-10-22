"""Normalization of volatile values (timestamps, UUIDs).

The implementation lives in `standalone.py` (which must stay free of `reverseai` imports
because it is copied into sandboxes); this module re-exports it for package code.
"""

from reverseai.oracle.standalone import VOLATILE, is_volatile, normalize

__all__ = ["VOLATILE", "is_volatile", "normalize"]
