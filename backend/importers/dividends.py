"""Collapse a broker's gross-dividend and withholding-tax legs into one net
ledger dividend, matching how T212 dividends are stored (cash_amount = what
was actually paid). Reversals and re-issues inside one group cancel out."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

_EPS = 1e-9


@dataclass(frozen=True)
class DividendLeg:
    group_key: str                 # same payment's gross and tax legs share it
    kind: Literal["gross", "tax"]
    ticker: str
    name: str | None
    pay_date: date
    currency: str
    amount: float                  # signed as reported: gross > 0, tax < 0
    shares: float | None = None
    executed_at: datetime | None = None
    fx_to_czk: float | None = None
    instrument_id: str | None = None


def net_dividend_rows(
    legs: Iterable[DividendLeg], *, source: str, stream: str = "dividends",
) -> tuple[list[dict], list[str], int]:
    """Returns (ledger rows, errors, number of fully reversed groups)."""
    groups: dict[str, list[DividendLeg]] = defaultdict(list)
    for leg in legs:
        groups[leg.group_key].append(leg)
    rows: list[dict] = []
    errors: list[str] = []
    skipped = 0
    for key in sorted(groups):
        group = groups[key]
        first = group[0]
        label = f"{first.ticker} {first.pay_date.isoformat()}"
        if len({leg.currency for leg in group}) != 1:
            errors.append(f"Dividend {label}: legs use different currencies")
            continue
        gross = sum(leg.amount for leg in group if leg.kind == "gross")
        tax = sum(leg.amount for leg in group if leg.kind == "tax")
        if abs(gross) < _EPS and abs(tax) < _EPS:
            skipped += 1
            continue
        if gross < _EPS:
            errors.append(
                f"Dividend {label}: withholding tax or reversal without the original "
                "payment in this file; import the statement that contains the payment"
            )
            continue
        net = gross + tax
        if net <= _EPS:
            errors.append(f"Dividend {label}: withholding tax exceeds the gross dividend")
            continue
        # The last positive gross leg is the payment that stands: a reissue
        # after a reversal carries the corrected share count.
        gross_leg = [leg for leg in group if leg.kind == "gross" and leg.amount > 0][-1]
        shares = gross_leg.shares if gross_leg.shares and gross_leg.shares > 0 else 1.0
        rows.append({
            "date": max(leg.pay_date for leg in group),
            "type": "dividend",
            "ticker": first.ticker,
            "name": first.name,
            "shares": shares,
            "price": net / shares,
            "currency": first.currency,
            "cash_amount": net,
            "cash_currency": first.currency,
            "notes": f"{source}: gross {gross:.4f}, tax {abs(tax):.4f} {first.currency}",
            "source": source,
            "source_event_stream": stream,
            "source_event_id": f"div:{key}",
            "source_instrument_id": gross_leg.instrument_id,
            "executed_at": gross_leg.executed_at,
            "fx_to_czk": gross_leg.fx_to_czk,
        })
    return rows, errors, skipped
