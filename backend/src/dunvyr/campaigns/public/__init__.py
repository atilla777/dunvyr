"""Campaigns public contract.

No other bounded context consumes campaigns yet, so this module intentionally
exposes nothing beyond the package marker. Keep it free of inner layers: future
snapshots/DTOs live here as frozen dataclasses or Protocols.
"""

from __future__ import annotations

__all__: list[str] = []
