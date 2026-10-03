# Trading 212 cash-transaction encoding (observed)

**Status: SIGNED OFF 2026-10-03 (see the end). The cash mapper may be
implemented against this record.** Parent plan:
`docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md` §5.5 items 7-8
(the `/equity/history/transactions` stream, deliberately out of scope until now).

Sources:

- Capture 2026-10-03 by `backend/scripts/t212_capture_cash_transactions.py`
  against the owner's **live** account: 250 transactions (the first five pages,
  2026-06-03 to 2026-10-03; `exhausted: false`, older history not read).
  Redacted examples are in the git-ignored
  `backend/tests/fixtures/t212_cash_transactions/_captured/cash_live.json`.
- The owner's T212 CSV export `from_2026-01-15_to_2026-09-30_*.csv`, used to
  identify what each API type means (same technique as the split record).

## Payload shape

Every item has exactly five fields: `type`, `amount` (signed number, account
currency), `currency` (`CZK` in all 250), `dateTime` (ISO-8601 UTC with
milliseconds), `reference` (opaque id). There is **no subtype, merchant, ticker,
note, or counterparty field**, so anything the CSV shows beyond the five fields
is not recoverable from the API.

## Types and signs (all 250 observed)

| API `type` | Count | Signs | Meaning (matched against the CSV) |
|---|---|---|---|
| `DEPOSIT` | 6 | all + | Bank deposit (CSV `Deposit`, note "Bank Transfer", 3200.00) **and** `Spending cashback` (1.93 and 3.28 CZK). One API type, two CSV meanings. |
| `WITHDRAW` | 14 | all - | Card spending (`Card debit`: -218.80 NYT, -218.31 Cloudflare, -7.90 Kaufland). The API time is the settlement time, 15-24 h after the CSV card time, so match by amount and day, not timestamp. |
| `FEE` | 2 | all - | `ADR Fee` (-0.16 CZK, SKHY, 2026-08-25 13:27:57; CSV 13:28:09). The other (-0.16 on 2026-06-03 11:13:59) has **no** CSV row. |
| `INTEREST_ON_FREE_CASH` | 146 | all + | `Interest on cash`. |
| `LENDING_INTEREST` | 78 | all + | `Lending interest`. |
| `TRANSFER` | 4 | 3 +, 1 - | **All four match a CSV `Deposit`/`Withdrawal` to the second:** +200.00 (2026-07-15 15:14:19), +80.00 (2026-07-20 09:05:28), +24.20 (2026-07-20 12:29:26) are `Deposit`; -200.00 (2026-09-09 18:16:05) is `Withdrawal`. So `TRANSFER` is a bank transfer in or out, signed by direction. |

Directions are therefore **proven by sign**: positive adds cash, negative removes
it, for every type. No type has mixed signs except `TRANSFER`, whose sign is its
direction.

## Consequences for the existing cash model

- Portfyl's ledger already has `deposit`, `withdrawal`, `fee`, `interest`,
  `card_debit`, `cashback` (`backend/cash_ledger.py`). `deposit` and `cashback`
  are both external inflows and `withdrawal` and `card_debit` both external
  outflows (`cash_ledger.py:21-23`, `routers/analytics.py:705,1085`), so mapping
  API `DEPOSIT`/`WITHDRAW` to `deposit`/`withdrawal` gives **identical numbers**
  to the CSV's `cashback`/`card_debit` labels. Only the label (and the merchant
  name, which the API does not carry) differs.
- CSV `Withdrawal` and `Deposit` rows carry a UUID in the `ID` column, in the
  same format as API `reference`. The capture redacts `reference`, so equality
  is **not yet verified**.
- The CSV `ADR Fee` row has an **empty** `ID`, so a CSV import and an API import
  of the same ADR fee cannot be deduplicated by id.

## Decision (proposed, not approved)

1. `DEPOSIT` -> `deposit`; `WITHDRAW` -> `withdrawal`; `FEE` -> `fee`;
   `INTEREST_ON_FREE_CASH` and `LENDING_INTEREST` -> `interest`. Store the
   magnitude as the amount (positive) and the API type string in the row's
   source/notes. The numeric effect equals the CSV labels (see above).
2. `TRANSFER`: map to `deposit` when `amount > 0` and to `withdrawal` when
   `amount < 0`, preserving "TRANSFER" as the source subtype. **This relaxes
   the parent plan's rule (§5.5 item 8: TRANSFER enters `needs_review`)**, on
   evidence of 4 of 4 transfers matching CSV bank deposits/withdrawals. A zero
   amount, a currency that differs from the account currency, or any other
   unknown `type` still sends the run to `needs_review` without marking cash
   history complete.
3. Event identity is `cash:<reference>`; the timestamp is `dateTime`.
4. Cross-source dedupe against CSV cash rows by (type class, amount, UTC day)
   inside the CSV's covered window, with `reference` == CSV `ID` as the primary
   key once verified.

Open before sign-off:

1. Confirm the `TRANSFER` relaxation in item 2, or keep the plan's strict
   `needs_review` (safe but every account with a transfer, i.e. nearly every
   funded account, would never complete cash history).
2. Verify `reference` == CSV `ID` for `Deposit`/`Withdrawal` using the
   unredacted staged data (a one-off local query, nothing committed).
3. Decide how to handle the `FEE` with no CSV counterpart (2026-06-03): import
   it (the API is authoritative) or flag it.
4. Only one account, one currency (CZK) and a 4-month window were observed.
   Other currencies, FX-converted deposits and `Currency conversion` rows
   (present in the CSV) are unobserved in this stream and stay `needs_review`.

Sign-off: owner (tomzo), 2026-10-03, delegated in chat ("udělej jak uznáš za
vhodné, máš svolení moje"). Rulings taken on the owner's behalf, each with the
cost if wrong:

1. **TRANSFER maps by sign** (+ -> `deposit`, - -> `withdrawal`), as proposed.
   Cost if wrong: another account's TRANSFER may be an internal move (for
   example between Invest and another T212 account), which would be booked as
   an external flow and distort TWR/XIRR. Mitigation: the source subtype
   (`T212 TRANSFER`) is kept in the row notes so such rows are findable, and a
   zero or non-numeric amount or an empty currency still goes to `needs_review`.
2. **The FEE without a CSV counterpart is imported** (the API is authoritative).
   Cost if wrong: a 0.16 CZK fee too many.
3. **`reference` == CSV `ID` is not assumed.** Overlap with CSV rows is handled
   only by the CSV coverage cutoff (events at or before the export's end are
   settled by the CSV) plus one-to-one matching against rows with no provider
   identity on (type class, amount, currency, UTC day). Cost if wrong: a
   duplicate cash row for an event just after the export's end.
4. **"Currency differs from the account currency" is not checked**: the
   account currency is not stored. Each row keeps the event's own currency,
   exactly as the CSV importer does. Cost if wrong: none observed (all CZK).
5. `Currency conversion` and every unknown `type` stay `needs_review`.
