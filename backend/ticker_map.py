"""Yahoo Finance ticker remapping.

Some instruments don't resolve under the listing symbol the broker uses
(notably a few LSE-listed UCITS ETFs that Yahoo only carries under the
Amsterdam/Milan listings). We keep an explicit allowlist mapping the
broker symbol -> a Yahoo-recognised equivalent that tracks the same fund
in the same trading currency.
"""

TICKER_FALLBACKS = {
    # iShares Copper Miners UCITS ETF: Yahoo has no LSE (.L) feed; the
    # Amsterdam listing tracks the same NAV in USD.
    "COPM.L": "COPM.AS",
}


def yf_symbol(ticker: str) -> str:
    if not ticker:
        return ticker
    return TICKER_FALLBACKS.get(ticker.upper(), ticker)
