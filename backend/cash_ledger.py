"""Cash ledger: pure balance/interest math + the trade/cash type discriminator.

Cash flows share the Transaction table (discriminated by `type`). These frozensets
are the single source of truth used everywhere to keep cash rows out of holdings /
returns math.
"""
from __future__ import annotations

from datetime import date

TRADE_TYPES = frozenset({"buy", "sell", "dividend"})
CASH_TYPES = frozenset({"deposit", "withdrawal", "fee", "interest"})
