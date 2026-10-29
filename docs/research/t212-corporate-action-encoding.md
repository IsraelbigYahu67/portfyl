# Trading 212 corporate-action fill encoding (observed)

**Status: DRAFT, awaiting human review. Track B must not start until the
Sign-off line at the bottom is filled in.** Plan:
`docs/superpowers/plans/2026-09-24-t212-corporate-actions-incremental-sync.md`,
Task A2 / gate G1.

Sources (captured 2026-09-30 from the owner's local dev database by
`backend/scripts/t212_capture_corporate_actions.py`, run `initial`,
state `needs_review`; identifiers are redacted placeholders):

- `_captured/GNPX_US_EQ_2026-07-16.json`: Genprex (GNPX, ISIN US3724464017),
  **1-for-22 reverse split effective 2026-07-16**. Issuer ratio confirmed from
  the Nasdaq Trader corporate-action alert ECA2026-495 and Genprex's SEC 8-K
  (accession 0001437749-26-023480). Only one event, only one reverse split,
  **no forward split yet observed**.

## STOCK_SPLIT

1. **Fills per split event:** two, a close + open pair. Each fill arrives
   wrapped in its own `order` object, so the pair is two entries in the
   `orders` stream.
2. **Shared identifiers:** the legs do **not** share `order.id` (`id-0001` vs
   `id-0003`) or `fill.id` (`id-0002` vs `id-0004`). They share `filledAt`
   (`2026-07-16T07:32:21.000Z`), `order.createdAt`, `order.ticker`
   (`GNPX_US_EQ`), `order.instrument.isin`, and `order.currency` (CZK).
   The placeholders are assigned in event order, so whether the real ids are
   adjacent is **not known** from this capture.
3. **Leg direction:** close leg `order.side = "SELL"`, `fill.quantity = -15.0`
   (and `order.quantity`, `order.filledQuantity` also -15.0). Open leg
   `order.side = "BUY"`, `fill.quantity = +0.68181818`. Both are
   `order.type = "MARKET"`, `status = "FILLED"`, `fill.type = "STOCK_SPLIT"`.
   **The close leg's quantity is negative**; a mapper that assumes positive
   quantity on both sides will mis-sign it.
4. **Quantity meaning:** old total on the close leg, new total on the open
   leg, not a net delta. (15 → 0.68181818; 15/22 = 0.681818...). The CSV
   confirms -15 was the **whole** position: six buys of 5 shares (30) and one
   sell of 15 on 2026-04-20 leave 15; the later sell on 2026-08-07 is exactly
   0.68181818.
5. **`fill.price` per leg:** close leg = pre-split price (2.08133333 USD), open
   leg = post-split price (45.78933346 USD). Value conserved:
   15 × 2.08133333 = 31.22, 0.68181818 × 45.78933346 = 31.22.
6. **`fill.walletImpact`: present and NON-ZERO.** Both legs carry
   `netValue: 646.4` (CZK, `fxRate: 0.04829826`, i.e. 31.22 USD). The close
   leg also has `realisedProfitLoss: 0`; the open leg has no such key. Both
   values are **positive**, so the capture does not show which direction cash
   moves, or whether the two legs net to zero in the account. This is the
   stop condition in the plan's Track B header ("non-zero `walletImpact`,
   stop and revise this track with the user"). Evidence from the CSV (Q10):
   the same 646.40 CZK appears as `Total` on **both** legs (the current value
   of the position, before and after), the close leg has `Result 0.00`, and
   no cash-movement row accompanies the split. The two legs are the same
   value, so `walletImpact.netValue` looks **informational, not a cash
   movement**. Portfyl's CSV importer already behaves this way
   (`routers/portfolio.py` split branch sets `cash_amount: None`). The
   account cash balance across the event was **not** checked directly.
7. **Fractional remainder / cash-in-lieu:** none visible. The fractional share
   (0.68181818) is kept as a position; no separate cash fill appeared in the
   captured window.
8. **Derived ratio vs issuer:** 15 / 0.68181818 = 22.0000 → 22:1 reverse.
   Equals the issuer's announced 1-for-22. ✔
9. **Reverse split example:** yes, this is one. Forward split encoding is
   **unobserved**; symmetric handling is an assumption.
10. **Matching T212 CSV rows** (user export
    `from_2026-01-15_to_2026-09-30_*.csv`, rows 566-567, 2026-07-16 07:32:21
    UTC):
    - `Stock split close`: `ID EOF54214231310`, 15 shares @ 2.08133333 USD,
      `Result 0.00`, `Total 646.40 CZK`.
    - `Stock split open`: `ID EOF54214231315`, 0.68181818 shares @
      45.78933346 USD, `Total 646.40 CZK`.
    - The CSV `ID` is the API `fill.id` with an `EOF` prefix (verified against
      the staged events: `fill:54214231310` = SELL/-15, `fill:54214231315` =
      BUY/+0.68181818). **The two sources identify a split leg identically.**
    - Note the CSV lists the open leg *before* the close leg; leg order in a
      feed is not reliable, so pair by `side`, never by position.
    - Same-day CSV rows 564/565/568 are interest and an unrelated PEP buy; no
      cash-movement row accompanies the split.

## Other non-TRADE types seen

None in this capture. (The run staged 50 orders and 21 dividends; the only
non-TRADE fills are the two above.) `STOCK_DISTRIBUTION`,
`STOCK_ACQUISITION` and `FOP*` remain `needs_review`. `SPIN_OFF` and the
forward split are covered below.

## Addendum 2026-10-28: forward split and SPIN_OFF observed

Both come from the owner's local `initial` run on 2026-10-28.

**Forward split:** Booking (`PCLN_US_EQ`, ISIN US09857L1089), 25:1,
`filledAt 2026-04-06T06:08:47Z`. It has the same shape as the reverse
split above. The close leg is SELL `-0.08` @ 4706.625. The open leg is BUY
`+2.0` @ 188.265. Both legs carry `walletImpact.netValue` 7867.89 CZK. The
share ratio (25) and the price ratio (25.0) agree. With that, open item 2 above is closed:
`collapse_split_pairs` now accepts forward splits through the same checks
(equal wallet values, price ratio, small exact fraction).

**SPIN_OFF:** Mobility Global (`MBGL_US_EQ`, ISIN US60744M1062),
`filledAt 2026-07-02T12:42:17Z`.

- **One fill only**: `order.side = "BUY"`, `fill.quantity = +1.0`,
  `fill.price = 0`, `fill.walletImpact = {currency: CZK, netValue: 0,
  fxRate: 1}`. There is no leg on the parent instrument and no cash moves.
- Mapping (`t212_sync._is_mappable_spin_off`): a `buy` of the new shares at
  price 0 with no cash. Total portfolio value and return stay correct. The
  parent's cost basis is not split, so the parent shows less gain and the
  spin-off shows its whole value as gain. This matches what Trading 212
  shows.
- Any other shape keeps the run in `needs_review` with
  `HISTORY_SPIN_OFF_UNVERIFIED_ERROR`, which stays blocked until a CSV covers
  the event. Other shapes are a SELL leg, a non-zero price or `netValue`, a
  missing `walletImpact`, or a non-positive quantity.

## Decision (proposed, not approved)

Chosen pair-collapse rule: group `STOCK_SPLIT` fills by
(`order.instrument.isin` or `order.ticker`, `fill.filledAt`). A valid pair is
exactly one leg with `order.side == "SELL"` (close, negative `fill.quantity`)
and one with `order.side == "BUY"` (open, positive `fill.quantity`). Anything
else (one leg, three legs, both same side) → `needs_review`.

Ratio formula: `ratio = open.quantity / |close.quantity|`
(0.68181818 / 15 = 0.04545454 = 1/22). Express as new-per-old shares; the
mapper should compare it against the price ratio
`close.price / open.price` (2.0813 / 45.7893 = 0.04545) and refuse to apply
if they differ by more than a small tolerance, sending the run to
`needs_review`.

Differences from hypothesis H1 (plan Track B header):

- H1 holds for legs, sides and prices (SELL = close at old price, BUY = open
  at new price).
- **Sign of the close quantity:** negative in the API payload (H1 does not
  say).
- **Both legs non-zero `walletImpact`**: contradicts the "must be 0 for a pure
  split" assumption in question 6. Proposed resolution: the mapper **ignores
  `walletImpact` for split legs** and writes no cash row, matching the CSV
  importer. It must still require equal `netValue` on both legs, and send the
  pair to `needs_review` if they differ (a real cash component would show up
  as unequal values).
- Legs do **not** share `order.id`/`fill.id`; pairing must use instrument +
  `filledAt`. The leg id is `fill:<fill.id>`, which equals the CSV `ID`
  without the `EOF` prefix, so one split leg dedupes identically whether it
  arrives from the API or from a CSV.

Open before sign-off:

1. Confirm the `walletImpact` decision above (ignore; require equal values).
2. A forward-split example, if one exists in any other portfolio or demo
   account; otherwise forward splits stay `needs_review` until one is seen.
   The rule is symmetric (ratio = open/|close|), but only the reverse case is
   verified.
3. Only one real event has been observed. Acceptable for the first mapper
   release if the `needs_review` fallbacks above stay strict.

Sign-off: owner (tomzo), 2026-09-30, approved in chat with both decisions
above: (1) `walletImpact` is ignored for split legs and both legs must carry
equal values, otherwise `needs_review`; (2) only the verified reverse-split
encoding is mapped, anything else stays `needs_review`. Mapper may be
implemented against this record.
