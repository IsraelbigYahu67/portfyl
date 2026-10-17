# Broker integrace, fáze 1: implementační plán

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uživatel Portfylu dostane do portfolia celou historii z IBKR (Flex sync + Flex XML upload), eToro (Public API), Degira, XTB, Schwabu a Fidelity, a to bez duplicit, s čistými dividendami po srážkové dani a se stejným preview → commit → 24h undo, jaký má dnes CSV import.

**Architecture:** Nový balíček `backend/importers/`. Každý broker je jeden modul ve
`backend/importers/formats/`, který soubor rozpozná a převede ho na normalizované
řádky `Transaction`. Registry moduly najde sama (`pkgutil`), takže paralelní
sessions nesahají na stejný soubor. Stávající `/import-csv/preview` a `/commit`
zkusí registry jako první a teprve pak stávající T212/Native větev. Sdílené
pomocné moduly řeší čísla podle locale, stabilní ID událostí, párování dividendy
se srážkovou daní a převod ISIN/burzy na Yahoo ticker (OpenFIGI). API zdroje
(IBKR Flex sync, eToro) používají stejné parsery a zapisují idempotentně přes
`source_event_id`.

**Tech Stack:** FastAPI (sync `def`), SQLAlchemy 2.0, PostgreSQL + RLS, `httpx`
(sync klient), `xml.etree` (stdlib, s odmítnutím DOCTYPE), `pandas`, `openpyxl`
(nová závislost, jen pro XTB), React 18 + Vitest.

**Spec:** `docs/research/2026-10-16-broker-integrations.md` (research a rozhodnutí
o dvou fázích). Tento plán pokrývá **jen fázi 1**. SnapTrade (fáze 2) dostane
vlastní plán až po splnění spouštěče ze specu.

## Global Constraints

- Žádné neoficiální/reverse-engineered API, žádné ukládání hesla ani 2FA uživatele (spec, „Co bych nedělal“).
- Robinhood ve fázi 1 není. Schwab Trader API a Fidelity Access také ne, jen CSV.
- Endpointy a dependency, které sahají na `Session`, jsou plain `def`. Async helpery se volají přes `private_loop.run_on_private_loop`. Před pomalým outbound voláním se volá `database.release_request_connections()` (`tests/test_event_loop_not_blocked.py`).
- Veřejná API ID jsou UUID `public_id`. Žádné integer ID ven.
- Každý dotaz je workspace-scoped (`require_portfolio`, `workspace_id == ...`). RLS nenahrazuje aplikační filtr.
- Peníze se normalizují do CZK přes `fx_to_czk`. Pokud ho broker nedá v CZK, zůstane `None` a doplní ho `_prepare_import_transactions` (`fx.bulk_fetch_fx`).
- Dividenda je v ledgeru **jeden řádek s čistou částkou** (`cash_amount` = vyplaceno po srážce), stejně jako u T212.
- Nové formáty jsou **append** (`mandatory_replace=False`). Replace celého portfolia zůstává jen pro T212 CSV.
- Fail-closed: neznámý typ řádku, který hýbe penězi nebo pozicí, je chyba v preview, ne tiché přeskočení. Přeskočit se smí jen to, co ledger záměrně nemodeluje (opce zpracuje Options, CFD, informační řádky), a to s počítadlem důvodu.
- Žádná migrace ve fázi 1. `BrokerConnection.broker` je volný string a existující partial unique index z `0016_transaction_provenance` (`workspace_id, portfolio_id, source, source_event_stream, source_event_id`) dedup pokrývá. Pokud task zjistí, že migraci potřebuje, zastaví se a migrace se stane samostatnou vlnou s jedním vlastníkem (+ `EXPECTED_ALEMBIC_HEAD`).
- Hotspoty (`routers/portfolio.py`, `main.py`, `jobs.py`, `requirements*.txt`, `requirements*.lock`, `frontend/package.json`, `frontend/src/api.js`) vlastní v každé vlně nejvýš jeden task.
- Tax Report a Screener se nikam nepřidávají. Nové importy jsou sdílené (local i cloud). API sync je za capability `broker_sync` (Investor), soubory za `csv_import` (Free). Nové capability se nezakládají.
- Hodnoty `Transaction.source`: `ibkr`, `etoro`, `degiro`, `xtb`, `schwab`, `fidelity`. Stejný `source` pro upload i API sync stejného brokera, aby se deduplikovaly navzájem.

## Review Focus

1. **Překrývající se exporty.** Uživatel nahraje IBKR XML za 2024 a 2025, pak zapne Flex sync za posledních 365 dní. Nebo Degiro export leden–červen a pak leden–prosinec. Očekávání: žádný řádek dvakrát. Testy: `test_ibkr_overlapping_statements_are_idempotent` (Task 3), `test_occurrence_ids_stable_across_overlapping_exports` (Task 1), `test_degiro_reimport_same_rows_no_duplicates` (Task 5).
2. **Dividenda a srážková daň jsou na různých řádcích, včetně opravy.** IBKR typicky dividendu stornuje a vyplatí znovu, WHT může přijít s jiným datem. Očekávání: jeden čistý dividendový řádek, storno + reissue se vyruší, WHT bez dividendy je chyba (ne tichá ztráta). Testy: `test_net_dividend_reversal_and_reissue`, `test_tax_without_gross_is_error` (Task 1), `test_ibkr_dividend_with_withholding` (Task 3).
3. **Instrument, který nejde převést na ticker** (exotické ETF, OpenFIGI 429/výpadek). Očekávání: preview vypíše konkrétní ISIN/název a nic se neuloží s `ticker=None` ani s ISIN místo tickeru. Testy: `test_unresolved_instrument_is_error` (Task 2), `test_openfigi_rate_limit_raises_unavailable` (Task 2), `test_degiro_unresolved_isin_blocks_preview` (Task 5).
4. **Čísla a data podle locale.** Degiro CZ/DE: `1.234,56`, `dd-mm-yyyy`. Schwab: `$1,234.56`, `($12.00)`, `-$5.00`, „01/15/2025 as of 01/14/2025“. Očekávání: `1.234` se nikdy nepřečte jako 1.234 kusu, když je to tisíc. Testy: `test_parse_number_*` (Task 1), `test_degiro_czech_locale_file` (Task 5), `test_schwab_as_of_dates_and_parentheses` (Task 6).
5. **Páka, short a nepodporované třídy aktiv** (eToro CFD/copy, XTB CFD, IBKR BOND/FUT/CASH). Očekávání: CFD a páka se neimportují jako nákup akcií, ale jsou spočítané v `skipped_reasons`. IBKR forex obchody jsou `fx_out`/`fx_in`. Testy: `test_ibkr_forex_trade_becomes_fx_legs`, `test_ibkr_unsupported_asset_counted` (Task 3), `test_etoro_leveraged_position_skipped` (Task 8), `test_xtb_cfd_rows_skipped` (Task 9).

---

## Rozdělení na vlny a paralelní sessions

Každá řádka „Lane“ = vlastní git branch/worktree (`feat/broker-<lane>`), vlastní
porty (backend `8000 + n`, frontend `5173 + n`), vlastní testovací DB
(`TEST_DATABASE_URL=.../portfyl_test_<lane>`). Nikdo necommituje přímo do `main`.

| Vlna | Lane | Tasky | Soubory (exkluzivně) | Závisí na |
|---|---|---|---|---|
| 0 | founder | Task 0 (vzorky exportů, otázky) | `backend/tests/fixtures/brokers/**` | – |
| 1 | `foundation` | Task 1 | `backend/importers/{__init__,base,registry,numbers,ids,dividends}.py`, `backend/importers/formats/__init__.py`, `routers/portfolio.py` (jen plugin větev), testy | – |
| 1 | `instruments` | Task 2 | `backend/importers/instruments.py`, `backend/importers/openfigi.py`, testy; na konci jedna větev v `routers/portfolio.py` (503 při výpadku OpenFIGI) **až po merge Tasku 1** | jen rozhraní z Tasku 1 (níže je napsané celé) |
| 2 | `ibkr` | Task 3 → Task 4 | `importers/formats/ibkr_flex.py`, `backend/ibkr_ledger.py`, `routers/ibkr.py` | vlna 1 |
| 2 | `degiro` | Task 5 | `importers/formats/degiro_*.py` | vlna 1 |
| 2 | `us-csv` | Task 6 → Task 7 | `importers/formats/{schwab,fidelity}.py` | vlna 1 |
| 2 | `etoro-client` | Task 8 | `backend/etoro_client.py`, `backend/etoro_mapper.py` | vlna 1 |
| 3 | `xtb` | Task 9 | `requirements*.txt`, `requirements*.lock` (**hotspot**), `importers/formats/xtb.py` | vlna 1 |
| 3 | `etoro-wiring` | Task 10 | `routers/etoro.py`, `main.py`, `jobs.py`, `deploy/cloudrun.md` (**hotspoty**) | Task 8 |
| 4 | `frontend` | Task 11 | `frontend/src/pages/Import.jsx`, `frontend/src/components/import/BrokerGuides.jsx`, `frontend/src/pages/Settings.jsx`, `frontend/src/api.js` | vlna 3 |
| 5 | `integration` | Task 12 | `CLAUDE.md`, research doc status | vše |

Vlna 1: `foundation` a `instruments` běží paralelně (disjunktní soubory). Vlna 2:
čtyři lanes paralelně, každý jen přidává nové soubory (+ `ibkr` mění
`routers/ibkr.py`, který nikdo jiný nemění). Vlna 3: `xtb` a `etoro-wiring`
paralelně (různé hotspoty). Před koncem každého tasku: rebase na aktuální
`main`, znovu `python -m pytest tests/ --ignore=tests/postgres -q` a vyřešit
konflikty lokálně.

## File Structure

```
backend/importers/
  __init__.py          # prázdné
  base.py              # ImportFile, ParseResult, ImportFormat, validate_rows, ALLOWED_ROW_KEYS
  registry.py          # auto-discovery formats/*.py, detect_format()
  numbers.py           # parse_number(raw, decimal=...), detect_decimal(values)
  ids.py               # occurrence_ids(keys) – stabilní ID pro řádky bez broker ID
  dividends.py         # DividendLeg, net_dividend_rows()
  instruments.py       # InstrumentRef, InstrumentResolver, DefaultInstrumentResolver, VENUE_SUFFIX
  openfigi.py          # OpenFigiClient (sync httpx), OpenFigiUnavailable
  formats/
    __init__.py
    ibkr_flex.py       # FORMAT + parse_flex_statement(xml_text, resolver)
    degiro_transactions.py
    degiro_account.py
    schwab.py
    fidelity.py
    xtb.py
backend/ibkr_ledger.py       # apply_flex_ledger(): Flex sync → ledger (idempotentně)
backend/etoro_client.py      # EtoroClient (REST, rate limit, stránkování po letech)
backend/etoro_mapper.py      # eToro JSON → ledger řádky
backend/routers/etoro.py     # connect/status/sync/auto-sync/disconnect
backend/tests/fixtures/brokers/<broker>/...   # anonymizované vzorky
frontend/src/components/import/BrokerGuides.jsx
```

Ledger řádek (dict), který každý parser vrací. Klíče jsou podmnožina
`import_workflow._IMPORTED_FIELDS` (jinak `Transaction(**row)` spadne):

| klíč | povinné | poznámka |
|---|---|---|
| `date` | ano | `datetime.date` |
| `type` | ano | `cash_ledger.POSITION_TYPES ∪ CASH_TYPES` |
| `ticker` | obchody, dividendy, split | Yahoo symbol; u cash řádků `None` |
| `name` | ne | |
| `shares`, `price` | ano (`float`) | u cash řádků `0.0` (sloupce jsou NOT NULL) |
| `amount` | cash řádky | kladné, směr dává `type` |
| `currency` | ano | měna ceny (obchod) nebo částky (cash) |
| `cash_amount`, `cash_currency` | ne | přesný dopad na hotovost (vč. poplatků), kladné |
| `notes` | ne | |
| `source` | ano | např. `"ibkr"` |
| `source_event_stream`, `source_event_id` | ano | stabilní napříč exporty |
| `source_instrument_id` | ne | ISIN/conid/instrumentId |
| `executed_at` | ne | timezone-aware UTC |
| `fx_to_czk` | ne | jen když broker dá kurz přímo k CZK |

---

### Task 0: Vzorky exportů a otevřené otázky (founder, bez kódu)

Bez reálných exportů jsou parsery Degiro/XTB/Fidelity/eToro odhad. Tenhle task
dělá founder, ne agent. Agentní tasky 5, 7, 8, 9 začínají kontrolou, že vzorky
existují, a když chybí, pracují se syntetickými fixtures z tohoto plánu a
v PR to výslovně uvedou.

**Files:**
- Create: `backend/tests/fixtures/brokers/README.md`
- Create: `backend/tests/fixtures/brokers/<broker>/*` (anonymizované soubory)

- [ ] **Step 1: Stáhnout exporty z reálných účtů** (kde účet existuje): IBKR Activity Flex XML (sekce Trades, CashTransactions, CorporateActions, Transfers, OpenPositions; formát data `yyyyMMdd`, času `HHmmss`, oddělovač `;`), Degiro `Transactions.csv` + `Account.csv` v **EN i CZ** UI, XTB xStation Account History XLSX, Schwab Transactions CSV, Fidelity Activity CSV, a pro eToro odpovědi endpointů (trade history, cash-account transactions, positions, instruments) uložené jako JSON.
- [ ] **Step 2: Anonymizovat.** Čísla účtů nahradit `U0000000`/`XXXX`, jména smazat, částky nechat (jsou potřeba pro testy). Ověřit `git diff --stat`, že tam není nic osobního.
- [ ] **Step 3: Zapsat odpovědi na otázky ze specu** do `backend/tests/fixtures/brokers/README.md`:
  1. eToro: ve kterém endpointu jsou dividendy a srážková daň (název pole a typu).
  2. eToro: jestli partner tým povolí OAuth app pro portfolio tracker (e-mail odeslán / odpověď).
  3. XTB: přesné názvy listů a sloupců, měna účtu, formát komentáře u nákupu (`OPEN BUY 10 @ 190.50`?), jak vypadá částečný prodej, UK ceny v pencích ano/ne.
  4. Lynx: jde vygenerovat Flex Web Service token.
  5. Bloomberg `exchCode` pro Prahu (předpoklad `CP`) – jeden OpenFIGI dotaz na ISIN `CZ0005112300` (ČEZ).
- [ ] **Step 4: Commit**

```bash
git add backend/tests/fixtures/brokers
git commit -m "test: add anonymized broker export samples"
```

---

### Task 1: Import foundation (registry, čísla, ID, dividendy, napojení na preview/commit)

**Files:**
- Create: `backend/importers/__init__.py`, `backend/importers/base.py`, `backend/importers/registry.py`, `backend/importers/numbers.py`, `backend/importers/ids.py`, `backend/importers/dividends.py`, `backend/importers/formats/__init__.py`
- Modify: `backend/routers/portfolio.py` (`_ParsedImport`, `_parse_import_content`, `preview_import_csv`, `commit_import_csv`)
- Test: `backend/tests/test_importers_foundation.py`, `backend/tests/test_import_plugin_routing.py`

**Interfaces:**
- Consumes: `import_workflow._IMPORTED_FIELDS`, `cash_ledger.POSITION_TYPES`, `cash_ledger.CASH_TYPES`
- Produces:
  - `importers.base.ImportFile(filename: str, content: bytes)` (frozen dataclass), `.text(encoding="utf-8-sig") -> str`
  - `importers.base.ParseResult(format_name: str, rows: list[dict], source_events: int, skipped_reasons: dict[str, int], errors: list[str])`, property `skipped -> int`
  - `importers.base.ImportFormat(key: str, format_name: str, detect: Callable[[ImportFile], bool], parse: Callable[[ImportFile, InstrumentResolver], ParseResult])`
  - `importers.base.validate_rows(rows: list[dict]) -> list[str]`
  - `importers.registry.detect_format(file: ImportFile) -> ImportFormat | None`, `importers.registry.FORMATS: tuple[ImportFormat, ...]`, `class AmbiguousFormat(ValueError)`
  - `importers.numbers.parse_number(raw, *, decimal: str) -> float | None`, `importers.numbers.detect_decimal(values: Iterable[str]) -> str`
  - `importers.ids.occurrence_ids(keys: Iterable[tuple]) -> list[str]`
  - `importers.dividends.DividendLeg`, `importers.dividends.net_dividend_rows(legs, *, source: str, stream: str = "dividends") -> tuple[list[dict], list[str], int]`
  - `routers.portfolio.get_instrument_resolver() -> InstrumentResolver` (FastAPI-free factory, testy ho monkeypatchují)

- [ ] **Step 1: Napsat failing testy pro čísla a ID**

```python
# backend/tests/test_importers_foundation.py
from datetime import date

import pytest

from importers.ids import occurrence_ids
from importers.numbers import detect_decimal, parse_number


@pytest.mark.parametrize("raw, decimal, expected", [
    ("1,234.56", ".", 1234.56),
    ("$1,234.56", ".", 1234.56),
    ("-$1,234.56", ".", -1234.56),
    ("$-5.00", ".", -5.0),
    ("($12.00)", ".", -12.0),
    ("1.234,56", ",", 1234.56),
    ("1 234,56", ",", 1234.56),
    ("1 234,56", ",", 1234.56),
    ("-0,5", ",", -0.5),
    ("190.5", ".", 190.5),
    (12, ".", 12.0),
])
def test_parse_number_locales(raw, decimal, expected):
    assert parse_number(raw, decimal=decimal) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "", "  ", "-", "--"])
def test_parse_number_empty_is_none(raw):
    assert parse_number(raw, decimal=".") is None


def test_parse_number_garbage_raises():
    with pytest.raises(ValueError):
        parse_number("abc", decimal=".")


def test_parse_number_rejects_wrong_locale_ambiguity():
    # "1.234" in a comma-decimal file is one thousand two hundred thirty-four.
    assert parse_number("1.234", decimal=",") == 1234.0


def test_detect_decimal():
    assert detect_decimal(["1234,56", "-3,1", "10"]) == ","
    assert detect_decimal(["1234.56", "-3.1", "10"]) == "."
    assert detect_decimal(["10", "20"]) == "."
    with pytest.raises(ValueError):
        detect_decimal(["1,5", "2.5"])


def test_occurrence_ids_distinguish_identical_rows():
    ids = occurrence_ids([("2025-01-02", "buy", "AAPL", 1), ("2025-01-02", "buy", "AAPL", 1)])
    assert ids[0] != ids[1]
    assert ids[0].endswith("#1") and ids[1].endswith("#2")


def test_occurrence_ids_stable_across_overlapping_exports():
    q1 = [("2025-01-02", "buy", "AAPL", 1), ("2025-02-03", "sell", "AAPL", 1)]
    full_year = [*q1, ("2025-07-01", "buy", "MSFT", 2)]
    assert occurrence_ids(q1) == occurrence_ids(full_year)[:2]
```

- [ ] **Step 2: Spustit, ověřit že padají**

Run: `cd backend && python -m pytest tests/test_importers_foundation.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'importers'`

- [ ] **Step 3: Implementovat `numbers.py` a `ids.py`**

```python
# backend/importers/__init__.py
```

```python
# backend/importers/formats/__init__.py
"""Broker import formats. Every module here exposes `FORMAT: ImportFormat`;
importers.registry discovers them, so adding a broker never edits a shared file."""
```

```python
# backend/importers/numbers.py
"""Locale-explicit number parsing for broker exports.

Every format states its decimal separator (or detects it once per file with
detect_decimal); a parser never guesses per cell, because "1.234" is a
thousand in a Czech Degiro export and one point two in a US one.
"""
from __future__ import annotations

from collections.abc import Iterable
import math
import re

_CURRENCY_TOKENS = ("Kč", "CZK", "USD", "EUR", "GBP", "$", "€", "£")
_EMPTY = {"", "-", "--"}
_COMMA_DECIMAL = re.compile(r"^[-+(]?\d+(\.\d{3})*,\d+\)?$|^[-+(]?\d+,\d{1,2}\)?$")
_DOT_DECIMAL = re.compile(r"^[-+(]?\d+(,\d{3})*\.\d+\)?$")


def parse_number(raw, *, decimal: str) -> float | None:
    if decimal not in {".", ","}:
        raise ValueError(f"unsupported decimal separator {decimal!r}")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and math.isnan(raw):
            return None
        return float(raw)
    text = str(raw).strip().replace(" ", "").replace(" ", "")
    if text in _EMPTY:
        return None
    sign = 1.0
    if text.startswith("(") and text.endswith(")"):
        sign = -1.0
        text = text[1:-1]
    for token in _CURRENCY_TOKENS:
        text = text.replace(token, "")
    if text.startswith("-"):
        sign = -sign
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]
    thousands = "," if decimal == "." else "."
    text = text.replace(thousands, "")
    if decimal == ",":
        text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"not a number: {raw!r}") from None
    if not math.isfinite(value):
        raise ValueError(f"not a finite number: {raw!r}")
    return sign * value


def detect_decimal(values: Iterable[str]) -> str:
    comma = dot = False
    for value in values:
        text = str(value).strip().replace(" ", "").replace(" ", "")
        if _COMMA_DECIMAL.match(text):
            comma = True
        elif _DOT_DECIMAL.match(text):
            dot = True
    if comma and dot:
        raise ValueError("file mixes comma and dot decimal separators")
    return "," if comma else "."
```

```python
# backend/importers/ids.py
"""Stable event ids for exports that carry no broker transaction id.

The id is a digest of the row's business content plus its occurrence number
among identical rows *in the same file*. Two genuinely identical fills on one
day stay two rows, and an overlapping later export (Q1, then the full year)
reproduces the same ids, so the existing source_event_id dedup applies.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
import hashlib
import json


def occurrence_ids(keys: Iterable[tuple]) -> list[str]:
    seen: Counter[str] = Counter()
    ids: list[str] = []
    for key in keys:
        encoded = json.dumps(key, default=str, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
        seen[digest] += 1
        ids.append(f"{digest}#{seen[digest]}")
    return ids
```

Poznámka pro implementátora: ID je stabilní, jen pokud oba exporty obsahují
*všechny* identické řádky daného dne. Když export uřízne den v půlce, může
vzniknout duplikát. Exportní návody (Task 11) proto říkají „exportujte celé
kalendářní měsíce/kvartály“.

- [ ] **Step 4: Spustit, ověřit že prochází**

Run: `cd backend && python -m pytest tests/test_importers_foundation.py -v`
Expected: PASS

- [ ] **Step 5: Failing testy pro párování dividend**

```python
# append to backend/tests/test_importers_foundation.py
from importers.dividends import DividendLeg, net_dividend_rows


def _leg(kind, amount, key="A1", **kw):
    base = dict(group_key=key, kind=kind, ticker="AAPL", name="Apple",
                pay_date=date(2025, 2, 15), currency="USD", amount=amount, shares=10.0)
    base.update(kw)
    return DividendLeg(**base)


def test_net_dividend_single_row():
    rows, errors, skipped = net_dividend_rows([_leg("gross", 2.4), _leg("tax", -0.36)], source="ibkr")
    assert errors == [] and skipped == 0
    [row] = rows
    assert row["type"] == "dividend"
    assert row["cash_amount"] == pytest.approx(2.04)
    assert row["cash_currency"] == "USD"
    assert row["shares"] == 10.0
    assert row["price"] == pytest.approx(0.204)
    assert row["source"] == "ibkr" and row["source_event_stream"] == "dividends"
    assert row["source_event_id"] == "div:A1"


def test_net_dividend_reversal_and_reissue():
    legs = [_leg("gross", 2.4), _leg("tax", -0.36), _leg("gross", -2.4), _leg("tax", 0.36),
            _leg("gross", 2.5), _leg("tax", -0.375)]
    rows, errors, _ = net_dividend_rows(legs, source="ibkr")
    assert errors == []
    assert [r["cash_amount"] for r in rows] == [pytest.approx(2.125)]


def test_fully_reversed_dividend_is_skipped():
    rows, errors, skipped = net_dividend_rows([_leg("gross", 2.4), _leg("gross", -2.4)], source="ibkr")
    assert rows == [] and errors == [] and skipped == 1


def test_tax_without_gross_is_error():
    rows, errors, _ = net_dividend_rows([_leg("tax", -0.36)], source="ibkr")
    assert rows == [] and len(errors) == 1 and "AAPL" in errors[0]


def test_mixed_currency_group_is_error():
    _, errors, _ = net_dividend_rows([_leg("gross", 2.4), _leg("tax", -0.5, currency="EUR")], source="ibkr")
    assert errors


def test_unknown_share_count_uses_one():
    [row], _, _ = net_dividend_rows([_leg("gross", 3.0, shares=None)], source="degiro")
    assert row["shares"] == 1.0 and row["price"] == 3.0
```

- [ ] **Step 6: Spustit, ověřit FAIL** (`ModuleNotFoundError: importers.dividends`)

- [ ] **Step 7: Implementovat `dividends.py`**

```python
# backend/importers/dividends.py
"""Collapse a broker's gross-dividend and withholding-tax legs into one net
ledger dividend, matching how T212 dividends are stored (cash_amount = what
was actually paid). Reversals and re-issues inside one group cancel out."""
from __future__ import annotations

from collections import defaultdict
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


def net_dividend_rows(legs, *, source: str, stream: str = "dividends"):
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
        gross_leg = next(leg for leg in group if leg.kind == "gross" and leg.amount > 0)
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
```

- [ ] **Step 8: Spustit, ověřit PASS**

Run: `cd backend && python -m pytest tests/test_importers_foundation.py -v`

- [ ] **Step 9: Failing testy pro base + registry + routing**

```python
# backend/tests/test_import_plugin_routing.py
from datetime import date

import pytest
from fastapi import HTTPException

import importers.registry as registry
from importers.base import ImportFile, ImportFormat, ParseResult, validate_rows
from routers import portfolio as portfolio_router


def _row(**overrides):
    row = {
        "date": date(2025, 1, 2), "type": "buy", "ticker": "AAPL", "name": "Apple",
        "shares": 1.0, "price": 190.0, "currency": "USD", "source": "testbroker",
        "source_event_stream": "trades", "source_event_id": "T1",
    }
    row.update(overrides)
    return row


def test_validate_rows_rejects_unknown_keys_and_types():
    errors = validate_rows([_row(foo=1), _row(type="bonus")])
    assert any("foo" in e for e in errors)
    assert any("bonus" in e for e in errors)


def test_validate_rows_requires_event_identity():
    assert validate_rows([_row(source_event_id=None)])


def test_validate_rows_cash_row_needs_positive_amount():
    cash = _row(type="deposit", ticker=None, shares=0.0, price=0.0, amount=0.0)
    assert validate_rows([cash])


def test_registry_discovers_no_duplicate_keys():
    keys = [fmt.key for fmt in registry.FORMATS]
    assert len(keys) == len(set(keys))


def test_ambiguous_detection_raises(monkeypatch):
    fmt = ImportFormat("a", "A", lambda f: True, lambda f, r: None)
    other = ImportFormat("b", "B", lambda f: True, lambda f, r: None)
    monkeypatch.setattr(registry, "FORMATS", (fmt, other))
    with pytest.raises(registry.AmbiguousFormat):
        registry.detect_format(ImportFile("x.csv", b"x"))


def test_plugin_branch_runs_before_native(monkeypatch):
    fmt = ImportFormat(
        "testbroker", "Test Broker",
        lambda f: f.filename.endswith(".test"),
        lambda f, r: ParseResult("Test Broker", [_row()], source_events=3,
                                 skipped_reasons={"options": 2}, errors=[]),
    )
    monkeypatch.setattr(registry, "FORMATS", (fmt,))
    monkeypatch.setattr(portfolio_router, "get_instrument_resolver", lambda: None)
    parsed = portfolio_router._parse_import_content(b"anything", "export.test")
    assert parsed.format_name == "Test Broker"
    assert parsed.mandatory_replace is False
    assert parsed.skipped == 2 and parsed.skipped_reasons == {"options": 2}
    assert parsed.rows[0]["source"] == "testbroker"


def test_plugin_errors_become_400(monkeypatch):
    fmt = ImportFormat(
        "testbroker", "Test Broker", lambda f: True,
        lambda f, r: ParseResult("Test Broker", [], 1, {}, ["Row 2: boom"]),
    )
    monkeypatch.setattr(registry, "FORMATS", (fmt,))
    monkeypatch.setattr(portfolio_router, "get_instrument_resolver", lambda: None)
    with pytest.raises(HTTPException) as exc:
        portfolio_router._parse_import_content(b"x", "x.csv")
    assert exc.value.status_code == 400
    assert exc.value.detail["errors"] == ["Row 2: boom"]


def test_native_csv_still_parses_without_plugins(monkeypatch):
    monkeypatch.setattr(registry, "FORMATS", ())
    content = b"date,ticker,type,shares,price\n2025-01-02,AAPL,buy,1,190\n"
    parsed = portfolio_router._parse_import_content(content, "native.csv")
    assert parsed.format_name == "Native"
    assert parsed.skipped_reasons == {}
```

- [ ] **Step 10: Spustit, ověřit FAIL**

Run: `cd backend && python -m pytest tests/test_import_plugin_routing.py -v`

- [ ] **Step 11: Implementovat `base.py` a `registry.py`**

```python
# backend/importers/base.py
"""Contract between broker format modules and the CSV import endpoints."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

from cash_ledger import CASH_TYPES, POSITION_TYPES
from import_workflow import _IMPORTED_FIELDS

if TYPE_CHECKING:
    from importers.instruments import InstrumentResolver

ALLOWED_ROW_KEYS = frozenset(_IMPORTED_FIELDS)
LEDGER_TYPES = POSITION_TYPES | CASH_TYPES
MAX_REPORTED_ERRORS = 100


@dataclass(frozen=True)
class ImportFile:
    filename: str
    content: bytes

    def text(self, encoding: str = "utf-8-sig") -> str:
        return self.content.decode(encoding)

    def head(self, size: int = 4096) -> str:
        return self.content[:size].decode("utf-8-sig", errors="replace")


@dataclass
class ParseResult:
    format_name: str
    rows: list[dict]
    source_events: int
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def skipped(self) -> int:
        return sum(self.skipped_reasons.values())

    def skip(self, reason: str) -> None:
        self.skipped_reasons[reason] = self.skipped_reasons.get(reason, 0) + 1


@dataclass(frozen=True)
class ImportFormat:
    key: str
    format_name: str
    detect: Callable[[ImportFile], bool]
    parse: Callable[[ImportFile, "InstrumentResolver"], ParseResult]


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and value > 0


def validate_rows(rows: list[dict]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        label = f"Row {index} ({row.get('type')} {row.get('ticker') or ''})".rstrip()
        extra = set(row) - ALLOWED_ROW_KEYS
        if extra:
            errors.append(f"{label}: unsupported fields {sorted(extra)}")
        kind = row.get("type")
        if kind not in LEDGER_TYPES:
            errors.append(f"{label}: unsupported type {kind!r}")
            continue
        if not isinstance(row.get("date"), date):
            errors.append(f"{label}: date is missing")
        if not row.get("currency"):
            errors.append(f"{label}: currency is missing")
        if not row.get("source") or not row.get("source_event_stream") or not row.get("source_event_id"):
            errors.append(f"{label}: source event identity is missing")
        if kind in CASH_TYPES:
            if not _positive(row.get("amount")):
                errors.append(f"{label}: amount must be greater than 0")
        else:
            if not row.get("ticker"):
                errors.append(f"{label}: ticker is missing")
            if not _positive(row.get("shares")):
                errors.append(f"{label}: shares must be greater than 0")
            if not isinstance(row.get("price"), (int, float)) or row["price"] < 0:
                errors.append(f"{label}: price must be 0 or more")
    return errors[:MAX_REPORTED_ERRORS]
```

```python
# backend/importers/registry.py
"""Discovers broker formats in importers/formats/ (one module per broker)."""
from __future__ import annotations

import importlib
import pkgutil

from importers import formats as _formats_package
from importers.base import ImportFile, ImportFormat


class AmbiguousFormat(ValueError):
    pass


def _load_formats() -> tuple[ImportFormat, ...]:
    found: list[ImportFormat] = []
    for info in sorted(pkgutil.iter_modules(_formats_package.__path__), key=lambda i: i.name):
        module = importlib.import_module(f"importers.formats.{info.name}")
        fmt = getattr(module, "FORMAT", None)
        if isinstance(fmt, ImportFormat):
            found.append(fmt)
    keys = [fmt.key for fmt in found]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise RuntimeError(f"Duplicate import format keys: {duplicates}")
    return tuple(found)


FORMATS: tuple[ImportFormat, ...] = _load_formats()


def detect_format(file: ImportFile) -> ImportFormat | None:
    matches = []
    for fmt in FORMATS:
        try:
            if fmt.detect(file):
                matches.append(fmt)
        except Exception:
            continue  # a detector must never break another format's upload
    if len(matches) > 1:
        names = ", ".join(fmt.format_name for fmt in matches)
        raise AmbiguousFormat(f"File matches several broker formats: {names}")
    return matches[0] if matches else None
```

- [ ] **Step 12: Napojit registry v `routers/portfolio.py`**

Změny (jen tyto, nic dalšího v souboru):

```python
# imports near the top
from database import release_request_connections
from importers.base import ImportFile, validate_rows
from importers import registry as import_registry


def get_instrument_resolver():
    """Import-time resolver factory; tests monkeypatch it."""
    from importers.instruments import DefaultInstrumentResolver
    return DefaultInstrumentResolver.from_env()
```

`_ParsedImport` dostane pole `skipped_reasons: dict[str, int] = field(default_factory=dict)`
(import `field` z `dataclasses`) jako poslední pole.

`_read_import_upload`: text chyby změnit na `"Upload exceeds the 5 MiB limit"`.

`_parse_import_content(content: bytes, filename: str = "")`. Na úplný začátek funkce:

```python
    upload = ImportFile(filename=filename or "", content=content)
    try:
        plugin = import_registry.detect_format(upload)
    except import_registry.AmbiguousFormat as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if plugin is not None:
        return _parse_plugin_import(plugin, upload)
```

A nová funkce vedle:

```python
def _parse_plugin_import(plugin, upload: ImportFile) -> _ParsedImport:
    # Instrument resolution may call OpenFIGI; never hold a pooled DB
    # connection (taken by require_portfolio) across that outbound call.
    release_request_connections()
    result = plugin.parse(upload, get_instrument_resolver())
    errors = [*result.errors, *validate_rows(result.rows)]
    if errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"{result.format_name} import failed validation; nothing was imported",
                "errors": errors[:100],
            },
        )
    if not result.rows:
        raise HTTPException(
            status_code=400,
            detail={"message": "Import validation failed", "errors": ["File contains no importable rows"]},
        )
    return _ParsedImport(
        format_name=result.format_name,
        rows=result.rows,
        source_events=result.source_events,
        skipped=result.skipped,
        mandatory_replace=False,
        t212_covered_through=None,
        skipped_reasons=dict(result.skipped_reasons),
    )
```

V `preview_import_csv` i `commit_import_csv` volat
`_parse_import_content(_read_import_upload(file), file.filename or "")`. V preview
přidat před `return preview`: `preview["skipped_reasons"] = parsed.skipped_reasons`.

Ověřit, že `release_request_connections()` je no-op mimo request scope
(fast suite volá router funkce napřímo). Pokud ne, obalit `try/except RuntimeError`.

- [ ] **Step 13: Spustit nové i stávající import testy**

Run: `cd backend && python -m pytest tests/test_import_plugin_routing.py tests/test_importers_foundation.py tests/test_import_workflow.py tests/test_t212_import.py -v`
Expected: PASS (stávající T212/Native testy beze změny)

- [ ] **Step 14: Celý fast suite + commit**

Run: `cd backend && python -m pytest tests/ --ignore=tests/postgres -q`

```bash
git add backend/importers backend/routers/portfolio.py backend/tests/test_importers_foundation.py backend/tests/test_import_plugin_routing.py
git commit -m "feat(import): pluggable broker import formats with locale numbers and dividend netting"
```

---

### Task 2: Instrument resolver (ISIN/burza → Yahoo ticker přes OpenFIGI)

**Files:**
- Create: `backend/importers/instruments.py`, `backend/importers/openfigi.py`
- Test: `backend/tests/test_instrument_resolver.py`

**Interfaces:**
- Consumes: `cache.BoundedTTLCache(maxsize, ttl)`
- Produces:
  - `InstrumentRef(isin: str | None = None, symbol: str | None = None, venue: str | None = None, currency: str | None = None, name: str | None = None)` (frozen, hashable). `venue` je kanonický klíč z `VENUE_SUFFIX` (parser ho mapuje ze svých kódů burz).
  - `InstrumentResolver` Protocol: `resolve_many(refs: Sequence[InstrumentRef]) -> dict[InstrumentRef, str]` (chybějící klíč = nevyřešeno)
  - `DefaultInstrumentResolver(figi: OpenFigiClient | None)`, `DefaultInstrumentResolver.from_env()`
  - `unresolved_errors(refs, resolved) -> list[str]` (jednotný text chyby pro preview)
  - `VENUE_SUFFIX: dict[str, str]`, `yahoo_symbol(symbol: str, venue: str) -> str`
  - `openfigi.OpenFigiClient.map_isins(jobs: list[tuple[str, str | None]]) -> list[list[dict]]`, `openfigi.OpenFigiUnavailable(RuntimeError)`

- [ ] **Step 1: Failing testy**

```python
# backend/tests/test_instrument_resolver.py
import json

import httpx
import pytest

from importers.instruments import (
    DefaultInstrumentResolver, InstrumentRef, unresolved_errors, yahoo_symbol,
)
from importers.openfigi import OpenFigiClient, OpenFigiUnavailable


@pytest.mark.parametrize("symbol, venue, expected", [
    ("AAPL", "US", "AAPL"),
    ("BRK B", "US", "BRK-B"),
    ("BRK.B", "US", "BRK-B"),
    ("VWCE", "XETRA", "VWCE.DE"),
    ("VUSA", "LSE", "VUSA.L"),
    ("ASML", "AMSTERDAM", "ASML.AS"),
    ("CEZ", "PRAGUE", "CEZ.PR"),
    ("700", "HONGKONG", "0700.HK"),
])
def test_yahoo_symbol(symbol, venue, expected):
    assert yahoo_symbol(symbol, venue) == expected


def test_symbol_and_known_venue_needs_no_network():
    resolver = DefaultInstrumentResolver(figi=None)
    ref = InstrumentRef(symbol="VWCE", venue="XETRA", isin="IE00BK5BQT80")
    assert resolver.resolve_many([ref]) == {ref: "VWCE.DE"}


def _figi(handler):
    return OpenFigiClient(api_key=None, transport=httpx.MockTransport(handler))


def test_isin_resolved_via_openfigi_with_venue_filter():
    def handler(request):
        [job] = json.loads(request.read())
        assert job == {"idType": "ID_ISIN", "idValue": "IE00BK5BQT80", "exchCode": "GY"}
        return httpx.Response(200, json=[{"data": [
            {"ticker": "VWCE", "exchCode": "GY", "marketSector": "Equity"},
        ]}])
    resolver = DefaultInstrumentResolver(figi=_figi(handler))
    ref = InstrumentRef(isin="IE00BK5BQT80", venue="XETRA")
    assert resolver.resolve_many([ref]) == {ref: "VWCE.DE"}


def test_unresolved_instrument_is_error():
    def handler(request):
        return httpx.Response(200, json=[{"warning": "No identifier found."}])
    resolver = DefaultInstrumentResolver(figi=_figi(handler))
    ref = InstrumentRef(isin="XS0000000000", venue="XETRA", name="Obscure ETF")
    resolved = resolver.resolve_many([ref])
    assert resolved == {}
    [error] = unresolved_errors([ref], resolved)
    assert "XS0000000000" in error and "Obscure ETF" in error


def test_openfigi_rate_limit_raises_unavailable():
    resolver = DefaultInstrumentResolver(
        figi=_figi(lambda r: httpx.Response(429, headers={"Retry-After": "60"}))
    )
    with pytest.raises(OpenFigiUnavailable):
        resolver.resolve_many([InstrumentRef(isin="IE00BK5BQT80", venue="XETRA")])


def test_results_are_cached_between_calls():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=[{"data": [{"ticker": "VWCE", "exchCode": "GY", "marketSector": "Equity"}]}])
    resolver = DefaultInstrumentResolver(figi=_figi(handler))
    ref = InstrumentRef(isin="IE00BK5BQT80", venue="XETRA")
    resolver.resolve_many([ref])
    resolver.resolve_many([ref])
    assert len(calls) == 1


def test_batches_respect_job_limit():
    sizes = []

    def handler(request):
        jobs = json.loads(request.read())
        sizes.append(len(jobs))
        return httpx.Response(200, json=[{"warning": "No identifier found."}] * len(jobs))
    resolver = DefaultInstrumentResolver(figi=_figi(handler))
    refs = [InstrumentRef(isin=f"US00000000{i:02d}", venue="US") for i in range(23)]
    resolver.resolve_many(refs)
    assert sizes == [10, 10, 3]
```

- [ ] **Step 2: Spustit, ověřit FAIL**

Run: `cd backend && python -m pytest tests/test_instrument_resolver.py -v`

- [ ] **Step 3: Implementovat `openfigi.py`**

```python
# backend/importers/openfigi.py
"""Minimal sync OpenFIGI v3 /mapping client.

Sync on purpose: it runs inside plain-def import endpoints (threadpool) and
inside the IBKR sync's private loop thread, never on the main event loop.
Without an API key OpenFIGI allows 10 jobs per request and ~25 requests per
minute; with OPENFIGI_API_KEY 100 jobs per request.
"""
from __future__ import annotations

import os

import httpx

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


class OpenFigiUnavailable(RuntimeError):
    pass


class OpenFigiClient:
    def __init__(self, api_key: str | None, *, transport: httpx.BaseTransport | None = None,
                 timeout: float = 10.0):
        self.api_key = api_key
        self.jobs_per_request = 100 if api_key else 10
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["X-OPENFIGI-APIKEY"] = api_key
        self._client = httpx.Client(headers=headers, timeout=timeout, transport=transport)

    @classmethod
    def from_env(cls) -> "OpenFigiClient":
        return cls(os.environ.get("OPENFIGI_API_KEY") or None)

    def map_isins(self, jobs: list[tuple[str, str | None]]) -> list[list[dict]]:
        """jobs = [(isin, bloomberg_exch_code | None)] -> per-job list of matches."""
        results: list[list[dict]] = []
        for start in range(0, len(jobs), self.jobs_per_request):
            chunk = jobs[start:start + self.jobs_per_request]
            payload = [
                {"idType": "ID_ISIN", "idValue": isin, **({"exchCode": exch} if exch else {})}
                for isin, exch in chunk
            ]
            try:
                response = self._client.post(OPENFIGI_URL, json=payload)
            except httpx.HTTPError as exc:
                raise OpenFigiUnavailable(f"OpenFIGI request failed: {exc}") from exc
            if response.status_code == 429:
                raise OpenFigiUnavailable(
                    "Instrument lookup is rate-limited; try the import again in a minute"
                )
            if response.status_code >= 400:
                raise OpenFigiUnavailable(f"OpenFIGI returned HTTP {response.status_code}")
            for item in response.json():
                results.append(list(item.get("data") or []))
        return results
```

V `_parse_plugin_import` (Task 1) se `OpenFigiUnavailable` musí převést na
HTTP 503 s textem výjimky. Tuhle jednu větev přidá **Task 2** do
`routers/portfolio.py`, až bude Task 1 mergnutý (jediný zásah Tasku 2 do
hotspotu; `try: result = plugin.parse(...) except OpenFigiUnavailable as exc: raise HTTPException(503, str(exc))`).
Plus test v `tests/test_import_plugin_routing.py`: parse vyhodí
`OpenFigiUnavailable` → `HTTPException.status_code == 503`.

- [ ] **Step 4: Implementovat `instruments.py`**

```python
# backend/importers/instruments.py
"""Broker instrument identity -> Yahoo Finance symbol.

Order: (1) broker symbol + known venue, no network; (2) ISIN via OpenFIGI,
filtered to the venue's Bloomberg exchange code; (3) unresolved -> the parser
reports an error. Never fall back to the ISIN or the product name as a
ticker: market data would silently be missing for that holding.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from cache import BoundedTTLCache
from importers.openfigi import OpenFigiClient

# Canonical venue key -> Yahoo suffix. Extend only with a verified example.
VENUE_SUFFIX: dict[str, str] = {
    "US": "",
    "XETRA": ".DE",
    "FRANKFURT": ".F",
    "LSE": ".L",
    "AMSTERDAM": ".AS",
    "PARIS": ".PA",
    "MILAN": ".MI",
    "SIX": ".SW",
    "PRAGUE": ".PR",
    "TORONTO": ".TO",
    "BRUSSELS": ".BR",
    "MADRID": ".MC",
    "VIENNA": ".VI",
    "WARSAW": ".WA",
    "HONGKONG": ".HK",
}
# Canonical venue key -> Bloomberg exchCode used by OpenFIGI. PRAGUE "CP" is
# confirmed by Task 0 step 3.5; remove it if that lookup disagrees.
VENUE_FIGI: dict[str, str] = {
    "US": "US", "XETRA": "GY", "FRANKFURT": "GF", "LSE": "LN", "AMSTERDAM": "NA",
    "PARIS": "FP", "MILAN": "IM", "SIX": "SW", "PRAGUE": "CP",
}
_POSITIVE_TTL = 30 * 24 * 3600
_NEGATIVE_TTL = 24 * 3600
_MISS = object()


@dataclass(frozen=True)
class InstrumentRef:
    isin: str | None = None
    symbol: str | None = None
    venue: str | None = None
    currency: str | None = None
    name: str | None = None


class InstrumentResolver(Protocol):
    def resolve_many(self, refs: Sequence[InstrumentRef]) -> dict[InstrumentRef, str]: ...


def yahoo_symbol(symbol: str, venue: str) -> str:
    clean = symbol.strip().upper()
    if venue == "US":
        return clean.replace(" ", "-").replace(".", "-").replace("/", "-")
    if venue == "HONGKONG" and clean.isdigit():
        clean = clean.zfill(4)
    return f"{clean.replace(' ', '-')}{VENUE_SUFFIX[venue]}"


def unresolved_errors(refs: Sequence[InstrumentRef], resolved: dict[InstrumentRef, str]) -> list[str]:
    errors = []
    for ref in dict.fromkeys(refs):
        if ref not in resolved:
            errors.append(
                f"Cannot determine the market ticker for {ref.name or ref.symbol or '?'} "
                f"(ISIN {ref.isin or '-'}, venue {ref.venue or '-'}); nothing was imported"
            )
    return errors


_SHARED_CACHE = BoundedTTLCache(maxsize=20_000, ttl=_POSITIVE_TTL)


class DefaultInstrumentResolver:
    def __init__(self, figi: OpenFigiClient | None, cache: BoundedTTLCache | None = None):
        self.figi = figi
        self.cache = cache if cache is not None else BoundedTTLCache(maxsize=20_000, ttl=_POSITIVE_TTL)

    @classmethod
    def from_env(cls) -> "DefaultInstrumentResolver":
        return cls(OpenFigiClient.from_env(), cache=_SHARED_CACHE)

    def resolve_many(self, refs: Sequence[InstrumentRef]) -> dict[InstrumentRef, str]:
        resolved: dict[InstrumentRef, str] = {}
        pending: list[InstrumentRef] = []
        for ref in dict.fromkeys(refs):
            if ref.symbol and ref.venue in VENUE_SUFFIX:
                resolved[ref] = yahoo_symbol(ref.symbol, ref.venue)
                continue
            if not ref.isin:
                continue
            key = (ref.isin, ref.venue)
            cached = self.cache.get(key, _MISS)
            if cached is _MISS:
                pending.append(ref)
            elif cached is not None:
                resolved[ref] = cached
        if pending and self.figi is not None:
            matches = self.figi.map_isins([(ref.isin, VENUE_FIGI.get(ref.venue or "")) for ref in pending])
            for ref, candidates in zip(pending, matches):
                ticker = self._pick(ref, candidates)
                self.cache.set((ref.isin, ref.venue), ticker, ttl=_POSITIVE_TTL if ticker else _NEGATIVE_TTL)
                if ticker:
                    resolved[ref] = ticker
        return resolved

    @staticmethod
    def _pick(ref: InstrumentRef, candidates: list[dict]) -> str | None:
        wanted = VENUE_FIGI.get(ref.venue or "")
        for item in candidates:
            if item.get("marketSector") not in (None, "Equity"):
                continue
            if wanted and item.get("exchCode") != wanted:
                continue
            venue = next((v for v, code in VENUE_FIGI.items() if code == item.get("exchCode")), None)
            if venue and item.get("ticker"):
                return yahoo_symbol(item["ticker"], venue)
        return None
```

Ověřit signaturu `BoundedTTLCache.get/set` v `backend/cache.py` (řádek ~42–60).
Pokud `set` nebere `ttl=`, upravit volání podle skutečné signatury (docstring
říká, že `set` umí TTL per entry).

Riziko k vědomí: preview a commit můžou běžet na různých Cloud Run instancích a
každá má vlastní cache. OpenFIGI vrací deterministické výsledky, takže
`preview_id` sedí. Kdyby se to v praxi rozcházelo (409 při commitu), je to
signál pro perzistentní cache tabulku, což je samostatná migrace mimo tento plán.

- [ ] **Step 5: Spustit, ověřit PASS**

Run: `cd backend && python -m pytest tests/test_instrument_resolver.py tests/test_import_plugin_routing.py -v`

- [ ] **Step 6: Commit**

```bash
git add backend/importers/instruments.py backend/importers/openfigi.py backend/tests/test_instrument_resolver.py backend/routers/portfolio.py backend/tests/test_import_plugin_routing.py
git commit -m "feat(import): resolve broker instruments to Yahoo tickers via venue map and OpenFIGI"
```

---

### Task 3: IBKR Flex XML parser (akcie, ETF, cash, splity, transfery)

**Files:**
- Create: `backend/importers/formats/ibkr_flex.py`
- Create: `backend/tests/fixtures/brokers/ibkr/flex_2025_sample.xml` (syntetický, níže; nahradit/doplnit reálným vzorkem z Tasku 0)
- Test: `backend/tests/test_ibkr_flex_import.py`

**Interfaces:**
- Consumes: `ImportFile`, `ParseResult`, `ImportFormat`, `DividendLeg`, `net_dividend_rows`, `InstrumentRef`, `InstrumentResolver`, `unresolved_errors`
- Produces: `FORMAT` (key `"ibkr_flex"`, format_name `"Interactive Brokers (Flex XML)"`), `SOURCE = "ibkr"`, `parse_flex_statement(xml_text: str, resolver: InstrumentResolver) -> ParseResult`, `has_ledger_sections(xml_text: str) -> bool`, `IBKR_VENUES: dict[str, str]`

Mapování (Flex atributy):

| Element | Podmínka | Ledger |
|---|---|---|
| `Trade` | `levelOfDetail` chybí nebo `EXECUTION`; `assetCategory` ∈ {STK, ETF, FUND} | `buy`/`sell` (`quantity` znaménko), `price=tradePrice`, `cash_amount=abs(netCash)`, `cash_currency=currency`, stream `trades`, id `transactionID` (fallback `tradeID`) |
| `Trade` | `assetCategory=CASH` (např. `EUR.USD`) | `fx_in` základní měny `abs(quantity)` + `fx_out` kotované měny `abs(quantity*tradePrice)`; při SELL naopak; komise → `fee` |
| `Trade` | `assetCategory=OPT` | skip `"options (synced to Options)"` |
| `Trade` | jiné (BOND, FUT, CFD, WAR, CRYPTO…) | skip `"unsupported asset: <cat>"` |
| `Trade` | komise v jiné měně než `currency` | navíc `fee` řádek v `ibCommissionCurrency` |
| `CashTransaction` | `levelOfDetail` chybí nebo `DETAIL`; `type` ∈ {Dividends, Payment In Lieu Of Dividends} | `DividendLeg(kind="gross")`, group `actionID` (fallback `conid:datum`) |
| `CashTransaction` | `Withholding Tax` | `DividendLeg(kind="tax")` |
| `CashTransaction` | `Deposits/Withdrawals` | `deposit` (>0) / `withdrawal` (<0) |
| `CashTransaction` | `Broker Interest Received` / `Bond Interest Received` | `interest` |
| `CashTransaction` | `Broker Interest Paid`, `Other Fees`, `Commission Adjustments` se zápornou částkou | `fee` |
| `CashTransaction` | cokoli jiného, nebo kladný poplatek | **chyba** |
| `CorporateAction` | `type="FS"` (forward split), kladné `quantity` | `split_open` |
| `CorporateAction` | `type="RS"`, stejný `symbol` | záporné → `split_close`, kladné → `split_open` |
| `CorporateAction` | jiné | **chyba** „corporate action X needs manual review“ |
| `Transfer` | `direction=IN`, `transferPrice>0` | `deposit` (`quantity*transferPrice`) + `buy` |
| `Transfer` | `direction=OUT`, `transferPrice>0` | `sell` + `withdrawal` |
| `Transfer` | cena 0/chybí | **chyba** „transfer without cost basis“ |

`fx_to_czk` = `fxRateToBase`, jen když je základní měna účtu `CZK`
(`AccountInformation@currency`, fallback `FlexStatement@currency`). Jinak `None`.
`executed_at`: `dateTime` ve formátu `yyyyMMdd;HHmmss` (nebo `yyyy-MM-dd;HH:mm:ss`)
je čas America/New_York → převést na UTC. Datum bez času → `executed_at=None`.

Sémantiku `FS`/`RS` (jedna řádka s přírůstkem vs. dvě řádky staré/nové) ověřit
na reálném vzorku z Tasku 0. Pokud IBKR u `FS` reportuje jinak, test
`test_forward_split` upravit podle vzorku, ne podle tohoto plánu.

- [ ] **Step 1: Syntetický fixture**

```xml
<!-- backend/tests/fixtures/brokers/ibkr/flex_2025_sample.xml -->
<FlexQueryResponse queryName="Portfyl" type="AF">
 <FlexStatements count="1">
  <FlexStatement accountId="U0000000" fromDate="20250101" toDate="20251231" period="Custom">
   <AccountInformation accountId="U0000000" currency="CZK"/>
   <Trades>
    <Trade assetCategory="STK" symbol="AAPL" description="APPLE INC" conid="265598" isin="US0378331005" listingExchange="NASDAQ" currency="USD" fxRateToBase="23.10" tradeDate="20250102" dateTime="20250102;093015" quantity="10" tradePrice="190.5" ibCommission="-1" ibCommissionCurrency="USD" netCash="-1906" buySell="BUY" tradeID="111" transactionID="9001" levelOfDetail="EXECUTION"/>
    <Trade assetCategory="STK" symbol="AAPL" description="APPLE INC" conid="265598" isin="US0378331005" listingExchange="NASDAQ" currency="USD" fxRateToBase="23.10" tradeDate="20250102" dateTime="20250102;093015" quantity="10" tradePrice="190.5" ibCommission="-1" ibCommissionCurrency="USD" netCash="-1906" buySell="BUY" tradeID="111" transactionID="" levelOfDetail="ORDER"/>
    <Trade assetCategory="STK" symbol="VWCE" description="VANGUARD FTSE ALL-WORLD" conid="1" isin="IE00BK5BQT80" listingExchange="IBIS2" currency="EUR" fxRateToBase="25.0" tradeDate="20250310" dateTime="20250310;040000" quantity="-2" tradePrice="120" ibCommission="-1.25" ibCommissionCurrency="EUR" netCash="238.75" buySell="SELL" tradeID="112" transactionID="9002" levelOfDetail="EXECUTION"/>
    <Trade assetCategory="CASH" symbol="EUR.USD" currency="USD" fxRateToBase="23.10" tradeDate="20250311" dateTime="20250311;100000" quantity="1000" tradePrice="1.08" ibCommission="-2" ibCommissionCurrency="USD" netCash="-1080" buySell="BUY" tradeID="113" transactionID="9003" levelOfDetail="EXECUTION"/>
    <Trade assetCategory="OPT" symbol="AAPL  250620C00200000" currency="USD" tradeDate="20250401" dateTime="20250401;100000" quantity="1" tradePrice="3" netCash="-300" buySell="BUY" tradeID="114" transactionID="9004" levelOfDetail="EXECUTION"/>
    <Trade assetCategory="BOND" symbol="T 4 1/2" currency="USD" tradeDate="20250402" dateTime="20250402;100000" quantity="1000" tradePrice="99" netCash="-990" buySell="BUY" tradeID="115" transactionID="9005" levelOfDetail="EXECUTION"/>
   </Trades>
   <CashTransactions>
    <CashTransaction type="Dividends" symbol="AAPL" conid="265598" isin="US0378331005" listingExchange="NASDAQ" currency="USD" fxRateToBase="23.20" dateTime="20250515" amount="2.5" description="AAPL(US0378331005) CASH DIVIDEND USD 0.25 PER SHARE (Ordinary Dividend)" transactionID="8001" actionID="A1" levelOfDetail="DETAIL"/>
    <CashTransaction type="Withholding Tax" symbol="AAPL" conid="265598" isin="US0378331005" listingExchange="NASDAQ" currency="USD" fxRateToBase="23.20" dateTime="20250515" amount="-0.375" description="AAPL(US0378331005) CASH DIVIDEND USD 0.25 PER SHARE - US TAX" transactionID="8002" actionID="A1" levelOfDetail="DETAIL"/>
    <CashTransaction type="Dividends" symbol="AAPL" conid="265598" currency="USD" dateTime="20250515" amount="2.5" transactionID="" actionID="A1" levelOfDetail="SUMMARY"/>
    <CashTransaction type="Deposits/Withdrawals" currency="CZK" fxRateToBase="1" dateTime="20250101" amount="50000" description="CASH RECEIPTS" transactionID="8003" levelOfDetail="DETAIL"/>
    <CashTransaction type="Broker Interest Received" currency="USD" fxRateToBase="23.0" dateTime="20250605" amount="1.2" description="USD CREDIT INT" transactionID="8004" levelOfDetail="DETAIL"/>
    <CashTransaction type="Other Fees" currency="USD" fxRateToBase="23.0" dateTime="20250605" amount="-10" description="MARKET DATA" transactionID="8005" levelOfDetail="DETAIL"/>
   </CashTransactions>
   <CorporateActions>
    <CorporateAction type="FS" symbol="NVDA" conid="4815747" isin="US67066G1040" listingExchange="NASDAQ" currency="USD" dateTime="20250610;202500" quantity="90" description="NVDA(US67066G1040) SPLIT 10 FOR 1" transactionID="7001" actionID="S1" levelOfDetail="DETAIL"/>
   </CorporateActions>
  </FlexStatement>
 </FlexStatements>
</FlexQueryResponse>
```

- [ ] **Step 2: Failing testy**

```python
# backend/tests/test_ibkr_flex_import.py
from datetime import datetime, timezone
from pathlib import Path

import pytest

from importers.base import ImportFile, validate_rows
from importers.formats import ibkr_flex
from importers.instruments import DefaultInstrumentResolver

FIXTURE = Path(__file__).parent / "fixtures" / "brokers" / "ibkr" / "flex_2025_sample.xml"


@pytest.fixture
def parsed():
    return ibkr_flex.parse_flex_statement(FIXTURE.read_text(), DefaultInstrumentResolver(figi=None))


def _by(rows, **match):
    return [r for r in rows if all(r.get(k) == v for k, v in match.items())]


def test_detects_flex_xml_only():
    assert ibkr_flex.FORMAT.detect(ImportFile("x.xml", FIXTURE.read_bytes()))
    assert not ibkr_flex.FORMAT.detect(ImportFile("x.csv", b"date,ticker\n"))


def test_rows_pass_shared_validation(parsed):
    assert parsed.errors == []
    assert validate_rows(parsed.rows) == []


def test_stock_buy_execution_only(parsed):
    [buy] = _by(parsed.rows, type="buy", ticker="AAPL")
    assert buy["shares"] == 10 and buy["price"] == 190.5
    assert buy["cash_amount"] == 1906 and buy["cash_currency"] == "USD"
    assert buy["fx_to_czk"] == 23.10
    assert buy["source"] == "ibkr" and buy["source_event_stream"] == "trades"
    assert buy["source_event_id"] == "9001"
    assert buy["source_instrument_id"] == "US0378331005"
    assert buy["executed_at"] == datetime(2025, 1, 2, 14, 30, 15, tzinfo=timezone.utc)


def test_xetra_sell_maps_to_de_ticker(parsed):
    [sell] = _by(parsed.rows, type="sell")
    assert sell["ticker"] == "VWCE.DE" and sell["shares"] == 2
    assert sell["cash_amount"] == 238.75


def test_ibkr_forex_trade_becomes_fx_legs(parsed):
    [fx_in] = _by(parsed.rows, type="fx_in")
    [fx_out] = _by(parsed.rows, type="fx_out")
    assert (fx_in["currency"], fx_in["amount"]) == ("EUR", 1000)
    assert (fx_out["currency"], fx_out["amount"]) == ("USD", pytest.approx(1080))
    assert _by(parsed.rows, type="fee", source_event_id="9003:commission")


def test_ibkr_unsupported_asset_counted(parsed):
    assert parsed.skipped_reasons["options (synced to Options)"] == 1
    assert parsed.skipped_reasons["unsupported asset: BOND"] == 1


def test_ibkr_dividend_with_withholding(parsed):
    [div] = _by(parsed.rows, type="dividend")
    assert div["cash_amount"] == pytest.approx(2.125)
    assert div["shares"] == pytest.approx(10.0)  # 2.5 gross / 0.25 per share
    assert div["source_event_id"] == "div:A1"


def test_cash_rows(parsed):
    [deposit] = _by(parsed.rows, type="deposit")
    assert deposit["amount"] == 50000 and deposit["fx_to_czk"] == 1.0
    assert _by(parsed.rows, type="interest")[0]["amount"] == 1.2
    assert _by(parsed.rows, type="fee", source_event_id="8005")[0]["amount"] == 10


def test_forward_split(parsed):
    [split] = _by(parsed.rows, type="split_open")
    assert split["ticker"] == "NVDA" and split["shares"] == 90


def test_ibkr_overlapping_statements_are_idempotent(parsed):
    again = ibkr_flex.parse_flex_statement(FIXTURE.read_text(), DefaultInstrumentResolver(figi=None))
    key = lambda r: (r["source_event_stream"], r["source_event_id"])
    assert sorted(map(key, parsed.rows)) == sorted(map(key, again.rows))
    assert len(set(map(key, parsed.rows))) == len(parsed.rows)


def test_unknown_cash_type_is_error():
    xml = FIXTURE.read_text().replace('type="Other Fees"', 'type="Mystery"')
    result = ibkr_flex.parse_flex_statement(xml, DefaultInstrumentResolver(figi=None))
    assert any("Mystery" in e for e in result.errors)


def test_unsupported_corporate_action_is_error():
    xml = FIXTURE.read_text().replace('type="FS"', 'type="SO"')
    result = ibkr_flex.parse_flex_statement(xml, DefaultInstrumentResolver(figi=None))
    assert any("SO" in e for e in result.errors)


def test_doctype_is_rejected():
    xml = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><FlexQueryResponse/>'
    result = ibkr_flex.parse_flex_statement(xml, DefaultInstrumentResolver(figi=None))
    assert result.errors and result.rows == []


def test_non_czk_base_leaves_fx_empty():
    xml = FIXTURE.read_text().replace('currency="CZK"/>', 'currency="EUR"/>', 1)
    result = ibkr_flex.parse_flex_statement(xml, DefaultInstrumentResolver(figi=None))
    assert all(r["fx_to_czk"] is None for r in result.rows)


def test_has_ledger_sections():
    assert ibkr_flex.has_ledger_sections(FIXTURE.read_text())
    assert not ibkr_flex.has_ledger_sections("<FlexQueryResponse><FlexStatements/></FlexQueryResponse>")
```

- [ ] **Step 3: Spustit, ověřit FAIL** (`ImportError: cannot import name 'ibkr_flex'`)

- [ ] **Step 4: Implementace**

```python
# backend/importers/formats/ibkr_flex.py
"""IBKR Activity Flex Query XML -> ledger rows (stocks/ETFs, cash, splits).

Options stay with routers/ibkr.py's OptionsTrade sync and are only counted
here. The same parser serves the user's XML upload (history older than the
Flex Web Service's 365-day window) and the Flex Web Service sync
(ibkr_ledger.apply_flex_ledger), so both write identical event ids.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import re
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from importers.base import ImportFile, ImportFormat, ParseResult
from importers.dividends import DividendLeg, net_dividend_rows
from importers.instruments import InstrumentRef, InstrumentResolver, unresolved_errors

SOURCE = "ibkr"
_ET = ZoneInfo("America/New_York")
_STOCK_CATEGORIES = {"STK", "ETF", "FUND"}
_PER_SHARE = re.compile(r"([A-Z]{3})\s+([0-9.]+)\s+PER SHARE")

# IBKR listingExchange -> canonical venue (importers.instruments.VENUE_SUFFIX).
IBKR_VENUES = {
    "NASDAQ": "US", "NYSE": "US", "ARCA": "US", "AMEX": "US", "BATS": "US",
    "ISLAND": "US", "IEX": "US", "PINK": "US", "NYSENAT": "US",
    "IBIS": "XETRA", "IBIS2": "XETRA", "FWB": "FRANKFURT", "FWB2": "FRANKFURT",
    "LSE": "LSE", "LSEETF": "LSE", "AEB": "AMSTERDAM", "SBF": "PARIS",
    "BVME": "MILAN", "BVME.ETF": "MILAN", "EBS": "SIX", "SWX": "SIX",
    "PRA": "PRAGUE", "TSE": "TORONTO", "SEHK": "HONGKONG", "ENEXT.BE": "BRUSSELS",
    "BM": "MADRID", "VSE": "VIENNA", "WSE": "WARSAW",
}


def _detect(file: ImportFile) -> bool:
    head = file.head()
    return "<FlexQueryResponse" in head or "<FlexStatements" in head


def _parse(file: ImportFile, resolver: InstrumentResolver) -> ParseResult:
    return parse_flex_statement(file.text(), resolver)


FORMAT = ImportFormat("ibkr_flex", "Interactive Brokers (Flex XML)", _detect, _parse)


def _num(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _when(raw: str | None) -> tuple[date | None, datetime | None]:
    if not raw:
        return None, None
    text = raw.strip().replace("-", "").replace(":", "").replace(",", ";").replace(" ", "")
    day_part, _, time_part = text.partition(";")
    day = datetime.strptime(day_part[:8], "%Y%m%d").date()
    if not time_part:
        return day, None
    local = datetime.strptime(day_part[:8] + time_part[:6], "%Y%m%d%H%M%S").replace(tzinfo=_ET)
    return day, local.astimezone(timezone.utc)


def _detail(el: ET.Element, allowed: str) -> bool:
    return el.get("levelOfDetail") in (None, "", allowed)


def has_ledger_sections(xml_text: str) -> bool:
    return any(tag in xml_text for tag in ("<Trades", "<CashTransactions"))


def _ref(el: ET.Element) -> InstrumentRef:
    return InstrumentRef(
        isin=el.get("isin") or None,
        symbol=el.get("symbol") or None,
        venue=IBKR_VENUES.get((el.get("listingExchange") or "").upper()),
        currency=el.get("currency") or None,
        name=el.get("description") or el.get("symbol"),
    )


def parse_flex_statement(xml_text: str, resolver: InstrumentResolver) -> ParseResult:
    result = ParseResult("Interactive Brokers (Flex XML)", rows=[], source_events=0)
    if "<!DOCTYPE" in xml_text[:2048].upper() or "<!ENTITY" in xml_text.upper():
        result.errors.append("Flex XML must not contain a DOCTYPE or entity declarations")
        return result
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        result.errors.append(f"Could not parse IBKR XML: {exc}")
        return result

    for statement in root.iter("FlexStatement"):
        info = statement.find("AccountInformation")
        base = ((info.get("currency") if info is not None else None)
                or statement.get("currency") or "").upper()
        _parse_one(statement, base, resolver, result)
    return result


def _fx(el: ET.Element, base: str) -> float | None:
    return _num(el.get("fxRateToBase")) if base == "CZK" else None


def _needs_ticker(el: ET.Element) -> bool:
    if el.tag == "CashTransaction":
        return el.get("type") in _DIVIDEND_TYPES | {"Withholding Tax"}
    return bool(el.get("symbol")) and (el.get("assetCategory") or "STK") in _STOCK_CATEGORIES


def _parse_one(statement, base, resolver, result):
    trades = [t for t in statement.iter("Trade") if _detail(t, "EXECUTION")]
    cash = [c for c in statement.iter("CashTransaction") if _detail(c, "DETAIL")]
    actions = [a for a in statement.iter("CorporateAction") if _detail(a, "DETAIL")]
    transfers = list(statement.iter("Transfer"))
    result.source_events += len(trades) + len(cash) + len(actions) + len(transfers)

    refs = [_ref(el) for el in [*trades, *cash, *actions, *transfers] if _needs_ticker(el)]
    resolved = resolver.resolve_many(refs)
    ticker = lambda el: resolved.get(_ref(el))

    legs: list[DividendLeg] = []
    for trade in trades:
        _trade(trade, base, ticker, result)
    for row in cash:
        _cash(row, base, ticker, legs, result)
    for action in actions:
        _corporate_action(action, ticker, result)
    for transfer in transfers:
        _transfer(transfer, base, ticker, result)

    div_rows, div_errors, div_skipped = net_dividend_rows(legs, source=SOURCE)
    result.rows.extend(div_rows)
    result.errors.extend(div_errors)
    for _ in range(div_skipped):
        result.skip("fully reversed dividend")
    result.errors.extend(unresolved_errors([r for r in refs if r not in resolved], resolved))


def _event_id(el: ET.Element) -> str | None:
    return el.get("transactionID") or el.get("tradeID") or None


def _cash_row(common: dict, kind: str, amount: float, currency: str, event_id: str, notes=None) -> dict:
    return {**common, "type": kind, "ticker": None, "shares": 0.0, "price": 0.0,
            "amount": amount, "currency": currency, "notes": notes,
            "source_event_id": event_id, "fx_to_czk": None}


def _trade(el, base, ticker, result):
    category = (el.get("assetCategory") or "").upper()
    if category == "OPT":
        result.skip("options (synced to Options)")
        return
    if category not in _STOCK_CATEGORIES | {"CASH"}:
        result.skip(f"unsupported asset: {category or '?'}")
        return
    event_id = _event_id(el)
    day, executed_at = _when(el.get("dateTime") or el.get("tradeDate"))
    if event_id is None or day is None:
        result.errors.append(f"IBKR trade {el.get('symbol')}: missing transactionID or date")
        return
    currency = (el.get("currency") or "").upper()
    quantity = _num(el.get("quantity")) or 0.0
    price = _num(el.get("tradePrice")) or 0.0
    commission = abs(_num(el.get("ibCommission")) or 0.0)
    commission_ccy = (el.get("ibCommissionCurrency") or currency).upper()
    common = {"date": day, "executed_at": executed_at, "source": SOURCE,
              "source_event_stream": "trades", "fx_to_czk": _fx(el, base)}

    if category == "CASH":
        bought, _, quoted = (el.get("symbol") or "").partition(".")
        legs = [(bought, abs(quantity)), (quoted, abs(quantity * price))]
        incoming, outgoing = legs if quantity > 0 else legs[::-1]
        result.rows.append(_cash_row(common, "fx_in", incoming[1], incoming[0], f"{event_id}:in"))
        result.rows.append(_cash_row(common, "fx_out", outgoing[1], outgoing[0], f"{event_id}:out"))
        if commission:
            result.rows.append(_cash_row(common, "fee", commission, commission_ccy,
                                         f"{event_id}:commission", "IBKR FX commission"))
        return
    symbol = ticker(el)
    if symbol is None:
        return  # reported once via unresolved_errors
    net_cash = abs(_num(el.get("netCash")) or quantity * price)
    result.rows.append({
        **common, "type": "buy" if quantity > 0 else "sell", "ticker": symbol,
        "name": el.get("description"), "shares": abs(quantity), "price": price,
        "currency": currency, "cash_amount": net_cash, "cash_currency": currency,
        "source_event_id": event_id, "source_instrument_id": el.get("isin") or el.get("conid"),
        "notes": "IBKR",
    })
    if commission and commission_ccy != currency:
        result.rows.append(_cash_row(common, "fee", commission, commission_ccy,
                                     f"{event_id}:commission", f"IBKR commission {symbol}"))


_DIVIDEND_TYPES = {"Dividends", "Payment In Lieu Of Dividends"}
_FEE_TYPES = {"Broker Interest Paid", "Other Fees", "Commission Adjustments"}
_INTEREST_TYPES = {"Broker Interest Received", "Bond Interest Received"}


def _cash(el, base, ticker, legs, result):
    kind = el.get("type") or ""
    day, executed_at = _when(el.get("dateTime") or el.get("settleDate"))
    amount = _num(el.get("amount"))
    event_id = _event_id(el)
    currency = (el.get("currency") or "").upper()
    if day is None or amount is None or not currency:
        result.errors.append(f"IBKR cash transaction {kind}: missing date, amount or currency")
        return
    if kind in _DIVIDEND_TYPES or kind == "Withholding Tax":
        symbol = ticker(el)
        if symbol is None:
            return
        group = el.get("actionID") or f"{el.get('conid')}:{day.isoformat()}"
        per_share = _PER_SHARE.search(el.get("description") or "")
        shares = None
        if kind in _DIVIDEND_TYPES and per_share and float(per_share.group(2)) > 0:
            shares = abs(amount) / float(per_share.group(2))
        legs.append(DividendLeg(
            group_key=group, kind="tax" if kind == "Withholding Tax" else "gross",
            ticker=symbol, name=el.get("description"), pay_date=day, currency=currency,
            amount=amount, shares=shares, executed_at=executed_at, fx_to_czk=_fx(el, base),
            instrument_id=el.get("isin") or el.get("conid"),
        ))
        return
    if event_id is None:
        result.errors.append(f"IBKR cash transaction {kind} {day}: missing transactionID")
        return
    if kind == "Deposits/Withdrawals":
        ledger_type = "deposit" if amount > 0 else "withdrawal"
    elif kind in _INTEREST_TYPES and amount > 0:
        ledger_type = "interest"
    elif kind in _FEE_TYPES and amount < 0:
        ledger_type = "fee"
    else:
        result.errors.append(
            f"IBKR cash transaction {kind!r} ({amount} {currency} on {day}) is not supported yet"
        )
        return
    result.rows.append({
        "date": day, "type": ledger_type, "ticker": None, "shares": 0.0, "price": 0.0,
        "amount": abs(amount), "currency": currency, "notes": el.get("description"),
        "source": SOURCE, "source_event_stream": "cash", "source_event_id": event_id,
        "executed_at": executed_at, "fx_to_czk": _fx(el, base),
    })


def _corporate_action(el, ticker, result):
    kind = el.get("type") or ""
    quantity = _num(el.get("quantity")) or 0.0
    day, executed_at = _when(el.get("dateTime") or el.get("reportDate"))
    event_id = _event_id(el)
    if kind not in {"FS", "RS"} or day is None or event_id is None:
        result.errors.append(
            f"IBKR corporate action {kind} on {el.get('symbol')} needs manual review; nothing was imported"
        )
        return
    symbol = ticker(el)
    if symbol is None or quantity == 0:
        return
    result.rows.append({
        "date": day, "type": "split_open" if quantity > 0 else "split_close",
        "ticker": symbol, "name": el.get("description"), "shares": abs(quantity), "price": 0.0,
        "currency": (el.get("currency") or "USD").upper(), "notes": el.get("description"),
        "source": SOURCE, "source_event_stream": "corporate_actions", "source_event_id": event_id,
        "executed_at": executed_at, "source_instrument_id": el.get("isin") or el.get("conid"),
    })


def _transfer(el, base, ticker, result):
    direction = (el.get("direction") or "").upper()
    quantity = abs(_num(el.get("quantity")) or 0.0)
    price = _num(el.get("transferPrice")) or 0.0
    day, executed_at = _when(el.get("dateTime") or el.get("date"))
    event_id = _event_id(el)
    if direction not in {"IN", "OUT"} or price <= 0 or quantity <= 0 or day is None or event_id is None:
        result.errors.append(
            f"IBKR transfer of {el.get('symbol')} has no cost basis (transferPrice); "
            "add it manually after importing the rest"
        )
        return
    symbol = ticker(el)
    if symbol is None:
        return
    currency = (el.get("currency") or "USD").upper()
    value = quantity * price
    trade_type, cash_type = ("buy", "deposit") if direction == "IN" else ("sell", "withdrawal")
    common = {"date": day, "currency": currency, "source": SOURCE, "source_event_stream": "transfers",
              "executed_at": executed_at, "fx_to_czk": _fx(el, base),
              "notes": f"IBKR transfer {direction} ({el.get('type') or ''})".strip()}
    cash_row = {**common, "type": cash_type, "ticker": None, "shares": 0.0, "price": 0.0,
                "amount": value, "source_event_id": f"{event_id}:cash"}
    trade_row = {**common, "type": trade_type, "ticker": symbol, "name": el.get("description"),
                 "shares": quantity, "price": price, "cash_amount": value, "cash_currency": currency,
                 "source_event_id": f"{event_id}:position",
                 "source_instrument_id": el.get("isin") or el.get("conid")}
    result.rows.extend([cash_row, trade_row] if direction == "IN" else [trade_row, cash_row])
```

Poznámka: `fx_in`/`fx_out`/`fee` z FX obchodu mají `fx_to_czk=None` záměrně,
protože `fxRateToBase` na CASH obchodu platí pro kotovanou měnu, ne pro obě nohy.
`_prepare_import_transactions` je doplní z `bulk_fetch_fx`.

- [ ] **Step 5: Spustit, ověřit PASS**

Run: `cd backend && python -m pytest tests/test_ibkr_flex_import.py -v`

- [ ] **Step 6: Ověřit routing přes preview**

```python
# append to backend/tests/test_ibkr_flex_import.py
from routers import portfolio as portfolio_router


def test_flex_xml_routes_through_import_preview(monkeypatch):
    monkeypatch.setattr(portfolio_router, "get_instrument_resolver",
                        lambda: DefaultInstrumentResolver(figi=None))
    parsed = portfolio_router._parse_import_content(FIXTURE.read_bytes(), "statement.xml")
    assert parsed.format_name == "Interactive Brokers (Flex XML)"
    assert parsed.mandatory_replace is False
```

Run: `cd backend && python -m pytest tests/test_ibkr_flex_import.py -v`, pak `python -m pytest tests/ --ignore=tests/postgres -q`

- [ ] **Step 7: Commit**

```bash
git add backend/importers/formats/ibkr_flex.py backend/tests/test_ibkr_flex_import.py backend/tests/fixtures/brokers/ibkr
git commit -m "feat(ibkr): import stocks, cash, dividends and splits from Flex XML"
```

---

### Task 4: IBKR Flex Web Service sync zapisuje i akcie do ledgeru

**Files:**
- Create: `backend/ibkr_ledger.py`
- Modify: `backend/routers/ibkr.py` (`_run_ibkr_sync`, po fázi 4b)
- Test: `backend/tests/test_ibkr_ledger_sync.py`, nový test v `backend/tests/postgres/`

**Interfaces:**
- Consumes: `parse_flex_statement`, `has_ledger_sections`, `SOURCE`, `validate_rows`, `acquire_workspace_ledger_lock`, `resolve_entitlements`, `ensure_count_limit`, `fx.bulk_fetch_fx`, `cash_ledger.TRADE_TYPES`
- Produces: `apply_flex_ledger(db, portfolio, xml_text, *, resolver) -> dict` s klíči `status` (`"imported" | "sections_missing" | "needs_review"`), `imported`, `already_present`, `errors: list[str]`

Pravidla:
1. Bez sekcí `Trades`/`CashTransactions` → `sections_missing`, nic se nemění, opce fungují jako dřív.
2. Chyby parseru → `needs_review` + `conn.needs_attention = True`, `conn.last_error = první chyba`. Ledger beze změny.
3. **Ochrana proti duplicitám s ručním importem:** portfolio obsahuje obchod (`TRADE_TYPES`) se `source != "ibkr"` na ticker, který je ve výpisu → `needs_review` s textem „Portfolio už obsahuje ručně importované obchody pro AAPL, MSFT. Použijte samostatné portfolio pro IBKR nebo je smažte.“
4. Jinak vložit jen řádky, jejichž `(source, source_event_stream, source_event_id)` v portfoliu ještě není. Kapacitu ověřit přes `ensure_count_limit(entitlements, "transactions", used=<workspace count>, increase=len(new))`.
5. Commit dělá volající (stávající `db.commit()` na konci `_run_ibkr_sync`).

- [ ] **Step 1: Failing testy**

Vzor setupu převzít z `backend/tests/test_broker.py` (helpery v `tests/helpers.py`
vytváří workspace/portfolio a `BrokerConnection`).

```python
# backend/tests/test_ibkr_ledger_sync.py
from pathlib import Path

from ibkr_ledger import apply_flex_ledger
from importers.instruments import DefaultInstrumentResolver
from models import Transaction

FIXTURE = (Path(__file__).parent / "fixtures" / "brokers" / "ibkr" / "flex_2025_sample.xml").read_text()
RESOLVER = DefaultInstrumentResolver(figi=None)


def _txns(db, portfolio):
    return db.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).all()


def test_sync_imports_once_and_is_idempotent(db, portfolio):
    first = apply_flex_ledger(db, portfolio, FIXTURE, resolver=RESOLVER)
    db.commit()
    second = apply_flex_ledger(db, portfolio, FIXTURE, resolver=RESOLVER)
    db.commit()
    assert first["status"] == "imported" and first["imported"] > 0
    assert second["imported"] == 0 and second["already_present"] == first["imported"]
    assert len(_txns(db, portfolio)) == first["imported"]


def test_missing_sections_changes_nothing(db, portfolio):
    result = apply_flex_ledger(db, portfolio, "<FlexQueryResponse><FlexStatements/></FlexQueryResponse>",
                               resolver=RESOLVER)
    assert result["status"] == "sections_missing" and _txns(db, portfolio) == []


def test_manual_rows_for_same_ticker_block_import(db, portfolio, add_transaction):
    add_transaction(portfolio, ticker="AAPL", type="buy", shares=1, price=100, source="csv")
    result = apply_flex_ledger(db, portfolio, FIXTURE, resolver=RESOLVER)
    assert result["status"] == "needs_review" and "AAPL" in result["errors"][0]
    assert len(_txns(db, portfolio)) == 1


def test_parser_errors_block_import(db, portfolio):
    bad = FIXTURE.replace('type="Other Fees"', 'type="Mystery"')
    result = apply_flex_ledger(db, portfolio, bad, resolver=RESOLVER)
    assert result["status"] == "needs_review" and _txns(db, portfolio) == []
```

Pokud `tests/conftest.py` nemá fixtures `db`, `portfolio`, `add_transaction`,
přidat je **lokálně do tohoto test souboru** (conftest je sdílený). Postavit je
z helperů v `tests/helpers.py`, stejně jako `tests/test_broker.py`.
`bulk_fetch_fx` v testu monkeypatchnout na `lambda keys: {}`, aby test nešel na síť.

- [ ] **Step 2: Spustit, ověřit FAIL** (`ModuleNotFoundError: ibkr_ledger`)

- [ ] **Step 3: Implementace**

```python
# backend/ibkr_ledger.py
"""Write the Flex Web Service statement's stock/cash events into the ledger.

Idempotent by (source, stream, event id): the partial unique index from
migration 0016 backs the in-Python filter. Shares the parser with the Flex
XML upload, so a user can upload older yearly statements and keep the daily
sync running without duplicates.
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from cash_ledger import TRADE_TYPES
from edition import edition_from_env
from entitlements import ensure_count_limit, resolve_entitlements
from fx import bulk_fetch_fx
from importers.base import validate_rows
from importers.formats.ibkr_flex import SOURCE, has_ledger_sections, parse_flex_statement
from importers.instruments import InstrumentResolver
from ledger_mutation import acquire_workspace_ledger_lock
from models import Portfolio, Transaction


def apply_flex_ledger(db: Session, portfolio: Portfolio, xml_text: str, *,
                      resolver: InstrumentResolver) -> dict:
    if not has_ledger_sections(xml_text):
        return {"status": "sections_missing", "imported": 0, "already_present": 0, "errors": []}
    parsed = parse_flex_statement(xml_text, resolver)
    errors = [*parsed.errors, *validate_rows(parsed.rows)]
    if errors:
        return {"status": "needs_review", "imported": 0, "already_present": 0, "errors": errors[:20]}

    # FX does not depend on ledger state: fetch it before taking the lock.
    missing_fx = {(r["currency"], r["date"]) for r in parsed.rows if not r.get("fx_to_czk")}
    fx_map = bulk_fetch_fx(missing_fx) if missing_fx else {}

    acquire_workspace_ledger_lock(db, portfolio.workspace_id)
    existing = db.query(Transaction).filter(
        Transaction.workspace_id == portfolio.workspace_id,
        Transaction.portfolio_id == portfolio.id,
    ).all()
    incoming_tickers = {r["ticker"] for r in parsed.rows if r["type"] in TRADE_TYPES}
    foreign = sorted({
        t.ticker for t in existing
        if t.type in TRADE_TYPES and t.source != SOURCE and t.ticker in incoming_tickers
    })
    if foreign:
        return {"status": "needs_review", "imported": 0, "already_present": 0, "errors": [
            "Portfolio already contains manually imported trades for "
            f"{', '.join(foreign)}. Use a dedicated portfolio for IBKR or delete them first."
        ]}

    known = {
        (t.source, t.source_event_stream, t.source_event_id)
        for t in existing if t.source == SOURCE and t.source_event_id
    }
    new_rows = [
        r for r in parsed.rows
        if (r["source"], r["source_event_stream"], r["source_event_id"]) not in known
    ]
    if new_rows:
        entitlements = resolve_entitlements(
            db, edition=edition_from_env(os.environ), workspace_id=portfolio.workspace_id, env=os.environ,
        )
        used = db.query(Transaction).filter(Transaction.workspace_id == portfolio.workspace_id).count()
        ensure_count_limit(entitlements, "transactions", used=used, increase=len(new_rows))
        for row in new_rows:
            if not row.get("fx_to_czk"):
                row["fx_to_czk"] = 1.0 if row["currency"] == "CZK" else fx_map.get((row["currency"], row["date"]))
            db.add(Transaction(**row, workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id))
    return {"status": "imported", "imported": len(new_rows),
            "already_present": len(parsed.rows) - len(new_rows), "errors": []}
```

`ensure_count_limit` při překročení vyhazuje `HTTPException`. V syncu se
nechá propadnout do volajícího (stejně jako u CSV commitu). Ověřit, jak
`jobs.py` auto-sync zachází s `HTTPException` (dead-letter počítadlo), a
nepřidávat vlastní zachytávání.

- [ ] **Step 4: Napojit v `routers/ibkr.py`** za „Phase 4b“ (balance) a před „Phase 5“:

```python
    # Phase 4c: stock/ETF/cash ledger events from the same statement.
    from ibkr_ledger import apply_flex_ledger
    from importers.instruments import DefaultInstrumentResolver
    ledger = apply_flex_ledger(db, portfolio, xml_text, resolver=DefaultInstrumentResolver.from_env())
    if ledger["status"] == "needs_review":
        conn.needs_attention = True
        conn.last_error = ledger["errors"][0][:500]
```

A do návratového dictu přidat `"ledger": ledger`. Opce (fáze 5–7) běží beze
změny i při `needs_review`.

- [ ] **Step 5: Testy IBKR routeru a celý suite**

Run: `cd backend && python -m pytest tests/test_ibkr_ledger_sync.py tests/test_broker.py tests/test_event_loop_not_blocked.py -v`, pak `python -m pytest tests/ --ignore=tests/postgres -q`

- [ ] **Step 6: PostgreSQL suite** (unique index + RLS na skutečném Postgresu, vlastní DB lane `ibkr`)

Přidat `backend/tests/postgres/test_ibkr_ledger_postgres.py`: dva
`apply_flex_ledger` + commit za sebou nevyhodí `IntegrityError` a Bob v
isolation matrix nevidí Aliciny IBKR řádky (vzor v existujících
`tests/postgres/` testech, fixture `matrix_client` / alice/bob setup).

Run: `cd backend && TEST_DATABASE_URL=postgresql://<user>:<pw>@localhost:55432/portfyl_test_ibkr python -m pytest tests/postgres/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/ibkr_ledger.py backend/routers/ibkr.py backend/tests/test_ibkr_ledger_sync.py backend/tests/postgres/test_ibkr_ledger_postgres.py
git commit -m "feat(ibkr): Flex sync imports stocks, ETFs, cash and dividends idempotently"
```

---

### Task 5: Degiro CSV (`Transactions.csv` + `Account.csv`)

**Files:**
- Create: `backend/importers/formats/degiro_transactions.py`, `backend/importers/formats/degiro_account.py`, `backend/importers/formats/_degiro_common.py`
- Create: `backend/tests/fixtures/brokers/degiro/transactions_en.csv`, `transactions_cz.csv`, `account_en.csv` (syntetické, níže; reálné z Tasku 0 přidat vedle)
- Test: `backend/tests/test_degiro_import.py`

Modul `_degiro_common.py` registry přeskočí, protože nemá `FORMAT`.

**Interfaces:**
- Consumes: `parse_number`, `detect_decimal`, `occurrence_ids`, `DividendLeg`, `net_dividend_rows`, `InstrumentRef`, `unresolved_errors`
- Produces: `degiro_transactions.FORMAT` (key `degiro_transactions`, „Degiro (Transactions)“), `degiro_account.FORMAT` (key `degiro_account`, „Degiro (Account statement)“), `_degiro_common.DEGIRO_VENUES`, `_degiro_common.read_degiro_csv(file) -> list[list[str]]`, `_degiro_common.parse_degiro_date(text) -> date`, `_degiro_common.classify_description(text) -> str | None`

Detekce **podle pozice a obsahu, ne podle názvu sloupců** (UI jazyky mění hlavičky):
- Transactions: ≥ 19 sloupců; sloupec 3 v datových řádcích odpovídá ISIN `^[A-Z]{2}[A-Z0-9]{9}\d$`; sloupec 0 je datum `dd-mm-yyyy`.
- Account: 11–12 sloupců; sloupec 2 (Value date) je datum `dd-mm-yyyy`; sloupec 4 ISIN nebo prázdný.

Pozice sloupců Transactions (EN hlavičky jen pro orientaci):
`0 Date, 1 Time, 2 Product, 3 ISIN, 4 Reference exchange, 5 Venue, 6 Quantity, 7 Price, 8 (price ccy), 9 Local value, 10 (ccy), 11 Value, 12 (ccy), 13 Exchange rate, 14 AutoFX Fee, 15 Transaction and/or third party fees, 16 (ccy), 17 Total, 18 (ccy), 19 Order ID`.
Starší exporty nemají `AutoFX Fee`, pak se vše od indexu 14 posune o −1.
Rozlišení: počet sloupců hlavičky (20 vs 19).

Pozice sloupců Account:
`0 Date, 1 Time, 2 Value date, 3 Product, 4 ISIN, 5 Description, 6 FX, 7 Change ccy, 8 Change amount, 9 Balance ccy, 10 Balance amount, 11 Order Id`.

Mapování:
- Transactions: `quantity>0` → `buy`, `<0` → `sell`; `price` v měně sloupce 8; `cash_amount=abs(Total)`, `cash_currency` = měna u Total (zahrnuje poplatky i AutoFX); stream `trades`; id = `Order ID` + `:` + pořadí fillu v rámci Order ID (1, 2, …); bez Order ID → `occurrence_ids`. `executed_at`: `Date`+`Time` jsou Europe/Amsterdam → UTC.
- Account: řádky s `Order Id` jsou cash dopady obchodů/poplatků/AutoFX z Transactions.csv → **skip** `"trade settlement (imported from Transactions.csv)"`. Bez `Order Id` podle klíčových slov v popisu: dividenda → gross leg, srážková daň → tax leg (group `ISIN|value date`), vklad → `deposit`, výběr → `withdrawal`, connectivity/poplatek → `fee`, úrok → `interest`, `Valuta Creditering/Debitering` (a překlady) → `fx_in`/`fx_out` párované podle (datum, čas). Skupina FX musí mít přesně jeden `fx_out` a jeden `fx_in`, jinak chyba „unpaired currency conversion on …“. Neznámý popis s nenulovou částkou → **chyba**. Prázdná nebo nulová částka → skip `"informational row"`. ID všech cash řádků přes `occurrence_ids([(date, time, description, currency, amount)])`, stream `account`.

```python
# backend/importers/formats/_degiro_common.py (klíčová slova; rozšiřovat jen podle reálných vzorků)
DEGIRO_VENUES = {
    "NDQ": "US", "NSY": "US", "ASE": "US",
    "XET": "XETRA", "FRA": "FRANKFURT", "LSE": "LSE", "EAM": "AMSTERDAM",
    "EPA": "PARIS", "MIL": "MILAN", "SWX": "SIX", "PRA": "PRAGUE", "TOR": "TORONTO",
    "EBR": "BRUSSELS", "MAD": "MADRID", "WSE": "WARSAW", "HKS": "HONGKONG",
}
ACCOUNT_KEYWORDS = {
    "tax": ("dividend tax", "dividendová daň", "dividendensteuer", "dividendbelasting", "withholding"),
    "gross": ("dividend", "dividenda", "dividende", "dividendo"),
    "fx_in": ("valuta creditering", "fx credit", "připsání měny", "währungsgutschrift"),
    "fx_out": ("valuta debitering", "fx debit", "odepsání měny", "währungsbelastung"),
    "deposit": ("deposit", "vklad", "einzahlung", "storting"),
    "withdrawal": ("withdrawal", "výběr", "auszahlung", "terugstorting", "opname"),
    "interest": ("interest", "úrok", "zinsen", "rente"),
    "fee": ("connectivity", "fee", "poplatek", "gebühr", "kosten"),
}
```

Pořadí vyhodnocení je pořadí klíčů v dictu: `tax` před `gross` (`"dividend tax"`
obsahuje `"dividend"`), `fx_*` před `fee`.

- [ ] **Step 1: Syntetické fixtures** (formát podle research zdrojů; pokud reálný vzorek z Tasku 0 sloupce posouvá, upravit fixture i indexy):

`transactions_en.csv`:

```csv
Date,Time,Product,ISIN,Reference exchange,Venue,Quantity,Price,,Local value,,Value,,Exchange rate,AutoFX Fee,Transaction and/or third party fees,,Total,,Order ID
02-01-2025,15:31,APPLE INC,US0378331005,NDQ,XNAS,10,190.50,USD,-1905.00,USD,-1830.12,EUR,1.0409,-4.58,-1.00,EUR,-1835.70,EUR,0f1e2d3c-1111-2222-3333-444455556666
10-03-2025,09:05,VANGUARD FTSE ALL-WORLD UCITS ETF,IE00BK5BQT80,XET,XETA,-2,120.00,EUR,240.00,EUR,240.00,EUR,,0.00,-1.00,EUR,239.00,EUR,0f1e2d3c-7777-8888-9999-000011112222
```

`transactions_cz.csv` (stejný obchod, čárka jako desetinný oddělovač):

```csv
Datum,Čas,Produkt,ISIN,Reference,Místo,Počet,Cena,,Hodnota v místní měně,,Hodnota,,Směnný kurz,AutoFX poplatek,Transakční a/nebo externí poplatky,,Celkem,,ID objednávky
02-01-2025,15:31,APPLE INC,US0378331005,NDQ,XNAS,10,"190,50",USD,"-1905,00",USD,"-1830,12",EUR,"1,0409","-4,58","-1,00",EUR,"-1835,70",EUR,0f1e2d3c-1111-2222-3333-444455556666
```

`account_en.csv`:

```csv
Date,Time,Value date,Product,ISIN,Description,FX,Change,,Balance,,Order Id
02-01-2025,09:00,02-01-2025,,,flatex Deposit,,EUR,2000.00,EUR,2000.00,
15-05-2025,07:40,14-05-2025,APPLE INC,US0378331005,Dividend,,USD,2.50,USD,2.50,
15-05-2025,07:40,14-05-2025,APPLE INC,US0378331005,Dividend Tax,,USD,-0.38,USD,2.12,
15-05-2025,07:41,14-05-2025,,,Valuta Debitering,1.1200,USD,-2.12,USD,0.00,
15-05-2025,07:41,14-05-2025,,,Valuta Creditering,,EUR,1.89,EUR,165.89,
02-01-2025,15:31,02-01-2025,APPLE INC,US0378331005,"Buy 10 APPLE INC@190.5 USD (US0378331005)",,USD,-1905.00,USD,-1905.00,0f1e2d3c-1111-2222-3333-444455556666
31-01-2025,08:00,31-01-2025,,,DEGIRO Exchange Connectivity Fee 2025 (Nasdaq - NDQ),,EUR,-2.50,EUR,163.39,
```

- [ ] **Step 2: Failing testy**

```python
# backend/tests/test_degiro_import.py
from datetime import date
from pathlib import Path

import pytest

from importers.base import ImportFile, validate_rows
from importers.formats import degiro_account, degiro_transactions
from importers.formats._degiro_common import classify_description

FIX = Path(__file__).parent / "fixtures" / "brokers" / "degiro"


class FakeResolver:
    def __init__(self, mapping):
        self.mapping = mapping

    def resolve_many(self, refs):
        return {ref: self.mapping[ref.isin] for ref in refs if ref.isin in self.mapping}


RESOLVER = FakeResolver({"US0378331005": "AAPL", "IE00BK5BQT80": "VWCE.DE"})


def _file(name):
    return ImportFile(name, (FIX / name).read_bytes())


def test_detection_is_exclusive():
    assert degiro_transactions.FORMAT.detect(_file("transactions_en.csv"))
    assert degiro_transactions.FORMAT.detect(_file("transactions_cz.csv"))
    assert not degiro_account.FORMAT.detect(_file("transactions_en.csv"))
    assert degiro_account.FORMAT.detect(_file("account_en.csv"))
    assert not degiro_transactions.FORMAT.detect(_file("account_en.csv"))


def test_transactions_en():
    result = degiro_transactions.FORMAT.parse(_file("transactions_en.csv"), RESOLVER)
    assert result.errors == [] and validate_rows(result.rows) == []
    buy, sell = result.rows
    assert (buy["type"], buy["ticker"], buy["shares"], buy["price"], buy["currency"]) == ("buy", "AAPL", 10, 190.5, "USD")
    assert (buy["cash_amount"], buy["cash_currency"]) == (1835.70, "EUR")
    assert buy["date"] == date(2025, 1, 2)
    assert (sell["type"], sell["ticker"], sell["cash_amount"]) == ("sell", "VWCE.DE", 239.0)


def test_degiro_czech_locale_file():
    en = degiro_transactions.FORMAT.parse(_file("transactions_en.csv"), RESOLVER).rows[0]
    cz = degiro_transactions.FORMAT.parse(_file("transactions_cz.csv"), RESOLVER).rows[0]
    for key in ("shares", "price", "cash_amount", "source_event_id"):
        assert en[key] == cz[key]


def test_degiro_reimport_same_rows_no_duplicates():
    a = degiro_transactions.FORMAT.parse(_file("transactions_en.csv"), RESOLVER).rows
    b = degiro_transactions.FORMAT.parse(_file("transactions_en.csv"), RESOLVER).rows
    assert [r["source_event_id"] for r in a] == [r["source_event_id"] for r in b]
    assert len({r["source_event_id"] for r in a}) == len(a)


def test_degiro_unresolved_isin_blocks_preview():
    result = degiro_transactions.FORMAT.parse(_file("transactions_en.csv"), FakeResolver({}))
    assert any("US0378331005" in e for e in result.errors)
    assert all(r.get("ticker") for r in result.rows)


def test_account_statement():
    result = degiro_account.FORMAT.parse(_file("account_en.csv"), RESOLVER)
    assert result.errors == [] and validate_rows(result.rows) == []
    assert sorted(r["type"] for r in result.rows) == ["deposit", "dividend", "fee", "fx_in", "fx_out"]
    [div] = [r for r in result.rows if r["type"] == "dividend"]
    assert div["cash_amount"] == pytest.approx(2.12) and div["ticker"] == "AAPL"
    assert result.skipped_reasons == {"trade settlement (imported from Transactions.csv)": 1}


def test_tax_keyword_wins_over_dividend():
    assert classify_description("Dividend Tax") == "tax"
    assert classify_description("Dividendová daň") == "tax"
    assert classify_description("Dividend") == "gross"
    assert classify_description("Valuta Creditering") == "fx_in"
    assert classify_description("DEGIRO Exchange Connectivity Fee 2025") == "fee"


def test_unknown_account_description_is_error():
    text = (FIX / "account_en.csv").read_text().replace("flatex Deposit", "Something New")
    result = degiro_account.FORMAT.parse(ImportFile("a.csv", text.encode()), RESOLVER)
    assert any("Something New" in e for e in result.errors)


def test_unpaired_fx_is_error():
    lines = [l for l in (FIX / "account_en.csv").read_text().splitlines() if "Valuta Creditering" not in l]
    result = degiro_account.FORMAT.parse(ImportFile("a.csv", "\n".join(lines).encode()), RESOLVER)
    assert any("unpaired currency conversion" in e for e in result.errors)
```

- [ ] **Step 3: Spustit, ověřit FAIL**

Run: `cd backend && python -m pytest tests/test_degiro_import.py -v`

- [ ] **Step 4: Implementace `_degiro_common.py`**

```python
# backend/importers/formats/_degiro_common.py
"""Shared Degiro CSV helpers. Degiro localizes headers and descriptions, so
columns are addressed by position and descriptions by keyword tables."""
from __future__ import annotations

import csv
from datetime import date, datetime
import io
import re

ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
DATE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
# DEGIRO_VENUES, ACCOUNT_KEYWORDS: přesně podle bloku výše


def read_degiro_csv(file, *, head_only: bool = False) -> list[list[str]]:
    text = file.head() if head_only else file.text()
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect) if any(cell.strip() for cell in row)]


def parse_degiro_date(text: str) -> date:
    return datetime.strptime(text.strip(), "%d-%m-%Y").date()


def classify_description(description: str) -> str | None:
    lowered = description.lower()
    for kind, words in ACCOUNT_KEYWORDS.items():
        if any(word in lowered for word in words):
            return kind
    return None


def numeric_cells(rows: list[list[str]], indexes) -> list[str]:
    return [row[i] for row in rows for i in indexes if i < len(row) and row[i].strip()]
```

- [ ] **Step 5: Implementace `degiro_transactions.py`**

```python
# backend/importers/formats/degiro_transactions.py
"""Degiro Inbox -> Transactions CSV (trades only; cash events are in Account.csv)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from importers.base import ImportFile, ImportFormat, ParseResult
from importers.formats._degiro_common import (
    DATE, DEGIRO_VENUES, ISIN, numeric_cells, parse_degiro_date, read_degiro_csv,
)
from importers.ids import occurrence_ids
from importers.instruments import InstrumentRef, unresolved_errors
from importers.numbers import detect_decimal, parse_number

SOURCE = "degiro"
_AMS = ZoneInfo("Europe/Amsterdam")


def _detect(file: ImportFile) -> bool:
    rows = read_degiro_csv(file, head_only=True)
    if len(rows) < 2 or len(rows[0]) < 19:
        return False
    data = rows[1]
    return len(data) >= 19 and bool(DATE.match(data[0].strip())) and bool(ISIN.match(data[3].strip()))


def _parse(file: ImportFile, resolver) -> ParseResult:
    result = ParseResult("Degiro (Transactions)", rows=[], source_events=0)
    table = read_degiro_csv(file)
    header, rows = table[0], table[1:]
    shift = 0 if len(header) >= 20 else -1
    total, total_ccy, order = 17 + shift, 18 + shift, 19 + shift
    result.source_events = len(rows)
    try:
        decimal = detect_decimal(numeric_cells(rows, (6, 7, 9, 11, total)))
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    refs = [InstrumentRef(isin=r[3].strip(), venue=DEGIRO_VENUES.get(r[4].strip()),
                          name=r[2].strip(), currency=r[8].strip()) for r in rows]
    resolved = resolver.resolve_many(refs)
    fallback_ids = occurrence_ids([(r[0], r[1], r[3], r[6], r[7]) for r in rows])
    fills: Counter[str] = Counter()

    for index, (row, ref) in enumerate(zip(rows, refs)):
        label = f"Row {index + 2}"
        try:
            day = parse_degiro_date(row[0])
            quantity = parse_number(row[6], decimal=decimal)
            price = parse_number(row[7], decimal=decimal)
            total_value = parse_number(row[total], decimal=decimal)
        except ValueError as exc:
            result.errors.append(f"{label}: {exc}")
            continue
        if not quantity or price is None or total_value is None:
            result.errors.append(f"{label}: quantity, price or total is missing")
            continue
        ticker = resolved.get(ref)
        if ticker is None:
            continue
        order_id = row[order].strip() if order < len(row) else ""
        if order_id:
            fills[order_id] += 1
            event_id = f"{order_id}:{fills[order_id]}"
        else:
            event_id = fallback_ids[index]
        executed_at = None
        if row[1].strip():
            local = datetime.strptime(f"{row[0].strip()} {row[1].strip()}", "%d-%m-%Y %H:%M")
            executed_at = local.replace(tzinfo=_AMS).astimezone(timezone.utc)
        result.rows.append({
            "date": day, "type": "buy" if quantity > 0 else "sell", "ticker": ticker,
            "name": row[2].strip(), "shares": abs(quantity), "price": price,
            "currency": row[8].strip().upper(), "cash_amount": abs(total_value),
            "cash_currency": row[total_ccy].strip().upper(), "notes": "Degiro",
            "source": SOURCE, "source_event_stream": "trades", "source_event_id": event_id,
            "source_instrument_id": ref.isin, "executed_at": executed_at,
        })
    result.errors.extend(unresolved_errors([r for r in refs if r not in resolved], resolved))
    return result


FORMAT = ImportFormat("degiro_transactions", "Degiro (Transactions)", _detect, _parse)
```

- [ ] **Step 6: Implementace `degiro_account.py`** podle pravidel výše. Kostra:

```python
# backend/importers/formats/degiro_account.py
"""Degiro Account statement CSV: dividends, withholding, deposits, fees, FX."""
from __future__ import annotations

from collections import defaultdict

from importers.base import ImportFile, ImportFormat, ParseResult
from importers.dividends import DividendLeg, net_dividend_rows
from importers.formats._degiro_common import (
    DATE, ISIN, classify_description, numeric_cells, parse_degiro_date, read_degiro_csv,
)
from importers.ids import occurrence_ids
from importers.instruments import InstrumentRef, unresolved_errors
from importers.numbers import detect_decimal, parse_number

SOURCE = "degiro"
_CASH_KINDS = {"deposit", "withdrawal", "interest", "fee"}


def _detect(file: ImportFile) -> bool:
    rows = read_degiro_csv(file, head_only=True)
    if len(rows) < 2 or not 11 <= len(rows[0]) <= 12:
        return False
    data = rows[1]
    return (len(data) >= 11 and bool(DATE.match(data[2].strip()))
            and (not data[4].strip() or bool(ISIN.match(data[4].strip()))))


def _parse(file: ImportFile, resolver) -> ParseResult:
    result = ParseResult("Degiro (Account statement)", rows=[], source_events=0)
    rows = read_degiro_csv(file)[1:]
    result.source_events = len(rows)
    try:
        decimal = detect_decimal(numeric_cells(rows, (8, 10)))
    except ValueError as exc:
        result.errors.append(str(exc))
        return result
    ids = occurrence_ids([(r[0], r[1], r[5], r[7], r[8]) for r in rows])
    dividend_refs = {
        r[4].strip(): InstrumentRef(isin=r[4].strip(), name=r[3].strip())
        for r in rows if r[4].strip() and classify_description(r[5]) in {"gross", "tax"}
    }
    resolved = resolver.resolve_many(list(dividend_refs.values()))
    legs: list[DividendLeg] = []
    fx_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for index, row in enumerate(rows):
        label = f"Row {index + 2}"
        order_id = row[11].strip() if len(row) > 11 else ""
        if order_id:
            result.skip("trade settlement (imported from Transactions.csv)")
            continue
        try:
            amount = parse_number(row[8], decimal=decimal)
            value_date = parse_degiro_date(row[2] or row[0])
        except ValueError as exc:
            result.errors.append(f"{label}: {exc}")
            continue
        if not amount:
            result.skip("informational row")
            continue
        kind = classify_description(row[5])
        currency = row[7].strip().upper()
        base = {"date": value_date, "currency": currency, "source": SOURCE,
                "source_event_stream": "account", "source_event_id": ids[index],
                "ticker": None, "shares": 0.0, "price": 0.0, "notes": row[5].strip()}
        if kind in {"gross", "tax"}:
            ticker = resolved.get(dividend_refs.get(row[4].strip()))
            if ticker is None:
                continue  # reported via unresolved_errors
            legs.append(DividendLeg(
                group_key=f"{row[4].strip()}|{value_date.isoformat()}", kind=kind,
                ticker=ticker, name=row[3].strip(), pay_date=value_date,
                currency=currency, amount=amount, instrument_id=row[4].strip(),
            ))
        elif kind in {"fx_in", "fx_out"}:
            fx_groups[(row[0], row[1])].append({**base, "type": kind, "amount": abs(amount)})
        elif kind in _CASH_KINDS:
            result.rows.append({**base, "type": kind, "amount": abs(amount)})
        else:
            result.errors.append(f"{label}: unsupported Degiro account entry {row[5].strip()!r}")

    for (day, time), legs_fx in fx_groups.items():
        kinds = sorted(leg["type"] for leg in legs_fx)
        if kinds != ["fx_in", "fx_out"]:
            result.errors.append(f"unpaired currency conversion on {day} {time}")
            continue
        result.rows.extend(legs_fx)

    div_rows, div_errors, div_skipped = net_dividend_rows(legs, source=SOURCE)
    result.rows.extend(div_rows)
    result.errors.extend(div_errors)
    for _ in range(div_skipped):
        result.skip("fully reversed dividend")
    refs = list(dividend_refs.values())
    result.errors.extend(unresolved_errors([r for r in refs if r not in resolved], resolved))
    return result


FORMAT = ImportFormat("degiro_account", "Degiro (Account statement)", _detect, _parse)
```

Pozor: `deposit`/`withdrawal` podle klíčového slova, ale směr peněz se musí
shodovat se znaménkem (`deposit` s kladnou částkou, `withdrawal` se zápornou,
`fee` se zápornou, `interest` s kladnou). Nesoulad → chyba
„sign contradicts description“. Doplnit test
`test_sign_contradiction_is_error` (vklad se zápornou částkou).

- [ ] **Step 7: Spustit, ověřit PASS**, pak `python -m pytest tests/ --ignore=tests/postgres -q`

- [ ] **Step 8: Commit**

```bash
git add backend/importers/formats/degiro_transactions.py backend/importers/formats/degiro_account.py backend/importers/formats/_degiro_common.py backend/tests/test_degiro_import.py backend/tests/fixtures/brokers/degiro
git commit -m "feat(import): Degiro transactions and account statement CSV import"
```

---

### Task 6: Schwab Transactions CSV

**Files:**
- Create: `backend/importers/formats/schwab.py`, `backend/tests/fixtures/brokers/schwab/transactions.csv`
- Test: `backend/tests/test_schwab_import.py`

**Interfaces:**
- Consumes: `parse_number`, `occurrence_ids`, `DividendLeg`, `net_dividend_rows`, `InstrumentRef`
- Produces: `FORMAT` (key `schwab`, „Charles Schwab“)

Hlavička: `"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"`.
Starší exporty mají nad ní banner řádek (`"Transactions for account ..."`) a
na konci `"Transactions Total"`. Parser najde řádek hlavičky (první řádek,
jehož buňky obsahují `Date`, `Action`, `Symbol`, `Amount`) a zastaví se na řádku
začínajícím `Transactions Total`. Desetinná tečka vždy. Datum `MM/DD/YYYY`,
u „`01/15/2025 as of 01/14/2025`“ se bere první datum (vypořádání).

| Action | Ledger |
|---|---|
| `Buy`, `Reinvest Shares` | `buy`, `cash_amount=abs(Amount)` |
| `Sell` | `sell`, `cash_amount=abs(Amount)` |
| `Cash Dividend`, `Qualified Dividend`, `Non-Qualified Div`, `Reinvest Dividend`, `Special Dividend`, `Pr Yr Cash Div` | gross leg |
| `NRA Tax Adj`, `Foreign Tax Paid`, `NRA Withholding` | tax leg |
| `Bank Interest`, `Credit Interest` | `interest` |
| `MoneyLink Transfer`, `Wire Funds`, `Wire Received`, `Funds Received`, `Journal` | `deposit`/`withdrawal` podle znaménka |
| `ADR Mgmt Fee`, `Service Fee`, `Margin Interest` | `fee` |
| `Stock Split` | `split_open` (kladné množství) |
| jiné | **chyba** |

Dividendové legy: `group_key = f"{symbol}|{date}"`. Měna USD. Ticker:
`InstrumentRef(symbol=..., venue="US")` (bez sítě). ID přes
`occurrence_ids([(date, action, symbol, quantity, price, amount)])`, stream
`transactions`. Chybějící `Price` u `Buy` → `(abs(Amount) - fees) / Quantity`.

- [ ] **Step 1: Fixture**

```csv
"Transactions  for account XXXX-1234 as of 10/16/2026 10:00 AM ET"
"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"
"01/02/2025","Buy","AAPL","APPLE INC","10","$190.50","$0.00","-$1,905.00"
"02/14/2025 as of 02/13/2025","Qualified Dividend","AAPL","APPLE INC","","","","$2.50"
"02/14/2025","NRA Tax Adj","AAPL","APPLE INC","","","","($0.38)"
"03/03/2025","Sell","BRK B","BERKSHIRE HATHAWAY B","2","$480.00","$0.02","$959.98"
"03/31/2025","Bank Interest","","SCHWAB1 INT","","","","$1.15"
"04/01/2025","MoneyLink Transfer","","Tfr BANK","","","","$5,000.00"
"Transactions Total","","","","","","","$4,057.25"
```

- [ ] **Step 2: Failing testy**

```python
# backend/tests/test_schwab_import.py
from datetime import date
from pathlib import Path

import pytest

from importers.base import ImportFile, validate_rows
from importers.formats import schwab
from importers.instruments import DefaultInstrumentResolver

FILE = Path(__file__).parent / "fixtures" / "brokers" / "schwab" / "transactions.csv"
RESOLVER = DefaultInstrumentResolver(figi=None)


def _parse(content=None):
    return schwab.FORMAT.parse(ImportFile("schwab.csv", content or FILE.read_bytes()), RESOLVER)


def test_detect():
    assert schwab.FORMAT.detect(ImportFile("s.csv", FILE.read_bytes()))
    assert not schwab.FORMAT.detect(ImportFile("s.csv", b"date,ticker,type,shares,price\n"))


def test_schwab_as_of_dates_and_parentheses():
    result = _parse()
    assert result.errors == [] and validate_rows(result.rows) == []
    [div] = [r for r in result.rows if r["type"] == "dividend"]
    assert div["date"] == date(2025, 2, 14)
    assert div["cash_amount"] == pytest.approx(2.12)


def test_trades_and_class_shares():
    rows = _parse().rows
    [buy] = [r for r in rows if r["type"] == "buy"]
    assert (buy["ticker"], buy["shares"], buy["price"], buy["cash_amount"]) == ("AAPL", 10, 190.5, 1905.0)
    [sell] = [r for r in rows if r["type"] == "sell"]
    assert sell["ticker"] == "BRK-B" and sell["cash_amount"] == pytest.approx(959.98)


def test_cash_rows_and_total_line_ignored():
    rows = _parse().rows
    assert {r["type"] for r in rows} == {"buy", "sell", "dividend", "interest", "deposit"}
    assert len(rows) == 5


def test_file_without_banner():
    lines = FILE.read_text().splitlines()[1:]
    assert len(_parse("\n".join(lines).encode()).rows) == 5


def test_unknown_action_is_error():
    content = FILE.read_text().replace('"Bank Interest"', '"Mystery Action"').encode()
    assert any("Mystery Action" in e for e in _parse(content).errors)
```

- [ ] **Step 3: Spustit, ověřit FAIL**

- [ ] **Step 4: Implementace**

```python
# backend/importers/formats/schwab.py
"""Charles Schwab History -> Transactions CSV export."""
from __future__ import annotations

import csv
from datetime import datetime
import io

from importers.base import ImportFile, ImportFormat, ParseResult
from importers.dividends import DividendLeg, net_dividend_rows
from importers.ids import occurrence_ids
from importers.instruments import InstrumentRef
from importers.numbers import parse_number

SOURCE = "schwab"
_HEADER = {"Date", "Action", "Symbol", "Amount"}
_BUY = {"Buy", "Reinvest Shares"}
_SELL = {"Sell"}
_GROSS = {"Cash Dividend", "Qualified Dividend", "Non-Qualified Div", "Reinvest Dividend",
          "Special Dividend", "Pr Yr Cash Div"}
_TAX = {"NRA Tax Adj", "Foreign Tax Paid", "NRA Withholding"}
_INTEREST = {"Bank Interest", "Credit Interest"}
_TRANSFER = {"MoneyLink Transfer", "Wire Funds", "Wire Received", "Funds Received", "Journal"}
_FEE = {"ADR Mgmt Fee", "Service Fee", "Margin Interest"}


def _table(text: str) -> list[dict]:
    lines = list(csv.reader(io.StringIO(text)))
    start = next((i for i, row in enumerate(lines) if _HEADER.issubset({c.strip() for c in row})), None)
    if start is None:
        return []
    header = [c.strip() for c in lines[start]]
    rows = []
    for row in lines[start + 1:]:
        if not row or not any(c.strip() for c in row):
            continue
        if row[0].strip().startswith("Transactions Total"):
            break
        rows.append(dict(zip(header, (c.strip() for c in row))))
    return rows


def _detect(file: ImportFile) -> bool:
    head = file.head()
    return '"Fees & Comm"' in head and '"Action"' in head and '"Amount"' in head


def _parse(file: ImportFile, resolver) -> ParseResult:
    rows = _table(file.text())
    result = ParseResult("Charles Schwab", rows=[], source_events=len(rows))
    refs = {r["Symbol"]: InstrumentRef(symbol=r["Symbol"], venue="US") for r in rows if r.get("Symbol")}
    resolved = resolver.resolve_many(list(refs.values()))
    ids = occurrence_ids([(r["Date"], r["Action"], r.get("Symbol"), r.get("Quantity"),
                           r.get("Price"), r["Amount"]) for r in rows])
    legs: list[DividendLeg] = []
    for index, row in enumerate(rows):
        label = f"Schwab {row['Date']} {row['Action']}"
        try:
            day = datetime.strptime(row["Date"].split(" as of ")[0].strip(), "%m/%d/%Y").date()
            amount = parse_number(row["Amount"], decimal=".") or 0.0
            quantity = parse_number(row.get("Quantity"), decimal=".")
            price = parse_number(row.get("Price"), decimal=".")
            fees = parse_number(row.get("Fees & Comm"), decimal=".") or 0.0
        except ValueError as exc:
            result.errors.append(f"{label}: {exc}")
            continue
        action = row["Action"]
        ticker = resolved.get(refs.get(row.get("Symbol") or ""))
        common = {"date": day, "currency": "USD", "source": SOURCE,
                  "source_event_stream": "transactions", "source_event_id": ids[index],
                  "notes": row.get("Description") or action}
        if action in _BUY | _SELL:
            if not quantity or ticker is None:
                result.errors.append(f"{label}: quantity or symbol missing")
                continue
            if price is None:
                price = (abs(amount) - abs(fees)) / abs(quantity)
            result.rows.append({**common, "type": "buy" if action in _BUY else "sell", "ticker": ticker,
                                "name": row.get("Description"), "shares": abs(quantity), "price": price,
                                "cash_amount": abs(amount), "cash_currency": "USD"})
        elif action in _GROSS | _TAX:
            if ticker is None:
                result.errors.append(f"{label}: dividend without symbol")
                continue
            legs.append(DividendLeg(group_key=f"{ticker}|{day.isoformat()}",
                                    kind="tax" if action in _TAX else "gross", ticker=ticker,
                                    name=row.get("Description"), pay_date=day, currency="USD",
                                    amount=amount))
        elif action in _INTEREST | _TRANSFER | _FEE:
            if action in _INTEREST:
                kind = "interest"
            elif action in _FEE:
                kind = "fee"
            else:
                kind = "deposit" if amount > 0 else "withdrawal"
            result.rows.append({**common, "type": kind, "ticker": None, "shares": 0.0,
                                "price": 0.0, "amount": abs(amount)})
        elif action == "Stock Split" and ticker and quantity and quantity > 0:
            result.rows.append({**common, "type": "split_open", "ticker": ticker, "shares": quantity,
                                "price": 0.0})
        else:
            result.errors.append(f"{label}: unsupported Schwab action {action!r}")
    div_rows, div_errors, div_skipped = net_dividend_rows(legs, source=SOURCE)
    result.rows.extend(div_rows)
    result.errors.extend(div_errors)
    for _ in range(div_skipped):
        result.skip("fully reversed dividend")
    return result


FORMAT = ImportFormat("schwab", "Charles Schwab", _detect, _parse)
```

- [ ] **Step 5: PASS + fast suite**

- [ ] **Step 6: Commit**

```bash
git add backend/importers/formats/schwab.py backend/tests/test_schwab_import.py backend/tests/fixtures/brokers/schwab
git commit -m "feat(import): Charles Schwab transactions CSV import"
```

---

### Task 7: Fidelity Activity CSV

**Files:**
- Create: `backend/importers/formats/fidelity.py`, `backend/tests/fixtures/brokers/fidelity/activity.csv`
- Test: `backend/tests/test_fidelity_import.py`

**Interfaces:**
- Consumes: totéž jako Task 6
- Produces: `FORMAT` (key `fidelity`, „Fidelity“)

Formát [sekundární, ověřit na vzorku z Tasku 0]: několik prázdných řádků, pak
hlavička `Run Date,Action,Symbol,Description,Type,Quantity,Price ($),Commission ($),Fees ($),Accrued Interest ($),Amount ($),Settlement Date`,
na konci disclaimer (řádky, které nezačínají datem `MM/DD/YYYY`, se po
hlavičce ignorují). Action je volný text, klasifikace podle prefixu
(case-insensitive):

| Prefix Action | Ledger |
|---|---|
| `YOU BOUGHT`, `REINVESTMENT` | `buy` |
| `YOU SOLD` | `sell` |
| `DIVIDEND RECEIVED` | gross leg |
| `FOREIGN TAX PAID`, `NON-RESIDENT TAX` | tax leg |
| `INTEREST EARNED` | `interest` |
| `ELECTRONIC FUNDS TRANSFER`, `DIRECT DEPOSIT`, `TRANSFERRED FROM`, `TRANSFERRED TO`, `CASH CONTRIBUTION` | `deposit`/`withdrawal` podle znaménka |
| `FEE CHARGED` | `fee` |
| jiné | **chyba** |

Money-market symboly (`SPAXX`, `FDRXX`, `FZFXX`, `SPRXX`, symbol končící `**`):
`buy`/`sell`/`REINVESTMENT` těchto symbolů jsou sweep do hotovosti → skip
`"money market sweep"`. Jejich `DIVIDEND RECEIVED` je `interest`.

Struktura modulu je stejná jako `schwab.py` (`_table` hledá hlavičku s
`Run Date` a `Action`; `_classify(action)` vrací typ podle tabulky; ID přes
`occurrence_ids([(run_date, action, symbol, quantity, price, amount)])`, stream
`activity`; dividendy přes `net_dividend_rows(source="fidelity")`).

- [ ] **Step 1: Fixture**

```csv


Run Date,Action,Symbol,Description,Type,Quantity,Price ($),Commission ($),Fees ($),Accrued Interest ($),Amount ($),Settlement Date
01/02/2025,"YOU BOUGHT APPLE INC (AAPL) (Cash)",AAPL,APPLE INC,Cash,10,190.5,,,,-1905,01/03/2025
02/14/2025,"DIVIDEND RECEIVED APPLE INC (AAPL) (Cash)",AAPL,APPLE INC,Cash,,,,,,2.5,
02/14/2025,"FOREIGN TAX PAID APPLE INC (AAPL) (Cash)",AAPL,APPLE INC,Cash,,,,,,-0.38,
02/28/2025,"DIVIDEND RECEIVED FIDELITY GOVERNMENT MONEY MARKET (SPAXX) (Cash)",SPAXX,FIDELITY GOVERNMENT MONEY MARKET,Cash,,,,,,1.1,
02/28/2025,"REINVESTMENT FIDELITY GOVERNMENT MONEY MARKET (SPAXX) (Cash)",SPAXX,FIDELITY GOVERNMENT MONEY MARKET,Cash,1.1,1,,,,-1.1,
03/01/2025,"Electronic Funds Transfer Received (Cash)",,No Description,Cash,,,,,,5000,


"The data and information in this spreadsheet is provided to you solely for your use..."
```

- [ ] **Step 2: Failing testy**

```python
# backend/tests/test_fidelity_import.py
from pathlib import Path

import pytest

from importers.base import ImportFile, validate_rows
from importers.formats import fidelity
from importers.instruments import DefaultInstrumentResolver

FILE = Path(__file__).parent / "fixtures" / "brokers" / "fidelity" / "activity.csv"
RESOLVER = DefaultInstrumentResolver(figi=None)


def _parse(content=None):
    return fidelity.FORMAT.parse(ImportFile("f.csv", content or FILE.read_bytes()), RESOLVER)


def test_detect():
    assert fidelity.FORMAT.detect(ImportFile("f.csv", FILE.read_bytes()))
    assert not fidelity.FORMAT.detect(ImportFile("f.csv", b"date,ticker,type,shares,price\n"))


def test_buy_and_dividend_net():
    result = _parse()
    assert result.errors == [] and validate_rows(result.rows) == []
    [buy] = [r for r in result.rows if r["type"] == "buy"]
    assert (buy["ticker"], buy["shares"], buy["cash_amount"]) == ("AAPL", 10, 1905)
    [div] = [r for r in result.rows if r["type"] == "dividend"]
    assert div["cash_amount"] == pytest.approx(2.12)


def test_money_market_sweep_skipped():
    result = _parse()
    assert result.skipped_reasons == {"money market sweep": 1}
    assert [r["amount"] for r in result.rows if r["type"] == "interest"] == [1.1]


def test_disclaimer_ignored():
    assert {r["type"] for r in _parse().rows} == {"buy", "dividend", "interest", "deposit"}


def test_unknown_action_is_error():
    content = FILE.read_text().replace("YOU BOUGHT", "YOU TELEPORTED").encode()
    assert _parse(content).errors


def test_occurrence_ids_unique():
    ids = [(r["source_event_stream"], r["source_event_id"]) for r in _parse().rows]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 3: FAIL → Step 4: implementace podle tabulky → Step 5: PASS + fast suite**

- [ ] **Step 6: Commit**

```bash
git add backend/importers/formats/fidelity.py backend/tests/test_fidelity_import.py backend/tests/fixtures/brokers/fidelity
git commit -m "feat(import): Fidelity activity CSV import"
```

---

### Task 8: eToro klient a mapper (bez routeru)

**Files:**
- Create: `backend/etoro_client.py`, `backend/etoro_mapper.py`
- Create: `backend/tests/fixtures/brokers/etoro/*.json` (z Tasku 0; jinak syntetické podle tabulky níže, v PR výslovně uvést)
- Test: `backend/tests/test_etoro_client.py`, `backend/tests/test_etoro_mapper.py`

**Interfaces:**
- Produces:
  - `EtoroClient(app_key: str, user_key: str, *, transport=None, base_url="https://public-api.etoro.com")` se sync metodami `trade_history(min_date: date) -> list[dict]`, `positions() -> list[dict]`, `cash_transactions(min_date: date) -> list[dict]`, `instruments(ids: Iterable[int]) -> dict[int, dict]`
  - `EtoroAuthError(RuntimeError)`, `EtoroRateLimited(RuntimeError)` s `retry_after: float`
  - `etoro_mapper.map_account(history, positions, cash, instruments) -> ParseResult` (rows se `source="etoro"`)

Fakta ze specu [ověřeno]: hlavičky `x-api-key` (app key Portfylu) a `x-user-key`
(uživatel, Read permission, Real), `GET /api/v1/trading/info/trade/history?minDate=...`
se stránkováním a oknem < 1 rok na request, limit 60 req/60 s sdílený, 429
s `Retry-After`. **Přesné cesty** pro positions, cash-account transactions a
instruments a **názvy polí** odpovědí se doplní z `api-portal.etoro.com/llms.txt`
a z JSON vzorků v Tasku 0. Implementátor je zapíše do konstant `ENDPOINTS` a
`FIELD_*` v hlavičce modulů a do tabulky v PR popisu. Kód je napsaný proti
těmto konstantám, takže změna se týká jen jich. Ověřit také base URL.

Model mapování (nezávislý na přesných názvech polí):
- Každá eToro pozice = `buy` při otevření (`openRate`, `units`, `openTimestamp`), uzavřená navíc `sell` (`closeRate`, `closeTimestamp`). ID `"{positionId}:open"` / `"{positionId}:close"`, stream `positions`.
- `leverage > 1` nebo `isBuy == false` → skip `"CFD / leveraged position"`. Copy-trading pozice (mirror ID) → skip `"copy trading"` (MVP; samostatný follow-up).
- Instrument: `instrumentId` → `instruments()` → symbol + burza → `InstrumentRef`. Krypto (`type == "crypto"`) → `"{SYMBOL}-USD"`.
- Měna účtu USD, `currency="USD"`, `cash_amount = units*rate` (eToro poplatky jsou ve spreadu).
- Cash transakce: vklad/výběr → `deposit`/`withdrawal`; dividenda → gross leg (eToro připisuje čistou částku, takže jen gross, `notes` „net of withholding“; ověřit Task 0 bod 1); poplatky → `fee`; neznámý typ → chyba.
- Okna: `trade_history` iteruje `min_date` po 360 dnech do dneška a stránkuje, dokud stránka není prázdná.

- [ ] **Step 1: Failing testy klienta** (httpx `MockTransport`)

```python
# backend/tests/test_etoro_client.py
from datetime import date

import httpx
import pytest

from etoro_client import EtoroAuthError, EtoroClient, EtoroRateLimited


def _client(handler):
    return EtoroClient("app", "user", transport=httpx.MockTransport(handler))


def test_sends_both_keys():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={"items": []})
    _client(handler).positions()
    assert seen["x-api-key"] == "app" and seen["x-user-key"] == "user"


def test_history_walks_yearly_windows_and_pages():
    calls = []

    def handler(request):
        calls.append((request.url.params.get("minDate"), request.url.params.get("page")))
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json={"items": [{"positionId": len(calls)}] if page == 1 else []})
    rows = _client(handler).trade_history(date(2024, 1, 1))
    windows = {c[0] for c in calls}
    assert len(windows) >= 3
    assert len(rows) == len(windows)


def test_401_raises_auth_error():
    with pytest.raises(EtoroAuthError):
        _client(lambda r: httpx.Response(401)).positions()


def test_429_raises_with_retry_after():
    with pytest.raises(EtoroRateLimited) as exc:
        _client(lambda r: httpx.Response(429, headers={"Retry-After": "12"})).positions()
    assert exc.value.retry_after == 12
```

Testy počítají s tím, že odpovědi mají seznam pod klíčem `FIELD_ITEMS`
(syntetický `"items"`). Po Tasku 0 upravit podle reálné odpovědi.

- [ ] **Step 2: Failing testy mapperu**

```python
# backend/tests/test_etoro_mapper.py
from etoro_mapper import map_account
from importers.base import validate_rows

INSTRUMENTS = {1001: {"symbol": "AAPL", "exchange": "NASDAQ", "type": "stock"},
               2002: {"symbol": "BTC", "exchange": "", "type": "crypto"}}


def _pos(pid, iid=1001, leverage=1, is_buy=True, closed=False):
    item = {"positionId": pid, "instrumentId": iid, "isBuy": is_buy, "leverage": leverage,
            "units": 2.0, "openRate": 190.0, "openTimestamp": "2025-01-02T14:30:00Z"}
    if closed:
        item.update(closeRate=200.0, closeTimestamp="2025-03-03T15:00:00Z")
    return item


def test_closed_position_is_buy_and_sell():
    result = map_account([_pos(1, closed=True)], [], [], INSTRUMENTS)
    assert validate_rows(result.rows) == []
    assert [(r["type"], r["source_event_id"]) for r in result.rows] == [("buy", "1:open"), ("sell", "1:close")]


def test_open_position_is_buy_only():
    result = map_account([], [_pos(2)], [], INSTRUMENTS)
    assert [r["type"] for r in result.rows] == ["buy"]


def test_etoro_leveraged_position_skipped():
    result = map_account([_pos(3, leverage=5, closed=True)], [_pos(4, is_buy=False)], [], INSTRUMENTS)
    assert result.rows == [] and result.skipped_reasons == {"CFD / leveraged position": 2}


def test_crypto_ticker():
    [row] = map_account([], [_pos(5, iid=2002)], [], INSTRUMENTS).rows
    assert row["ticker"] == "BTC-USD"


def test_position_open_in_history_and_positions_is_not_duplicated():
    result = map_account([_pos(6, closed=True)], [_pos(6)], [], INSTRUMENTS)
    assert sorted(r["source_event_id"] for r in result.rows) == ["6:close", "6:open"]


def test_unknown_instrument_is_error():
    result = map_account([], [_pos(7, iid=9999)], [], INSTRUMENTS)
    assert result.errors and result.rows == []
```

- [ ] **Step 3: Spustit, ověřit FAIL**

- [ ] **Step 4: Implementace klienta**

```python
# backend/etoro_client.py
"""eToro Public API client (read-only, personal keys).

Sync httpx: called from routers/etoro.py's plain-def sync and from the
autosync job. 60 requests per 60 s are shared across endpoints, so the client
spaces calls and surfaces 429 as EtoroRateLimited instead of sleeping on the
caller's thread for minutes.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
import time

import httpx

# Cesty kromě trade_history a FIELD_ITEMS ověřit v Tasku 0 (llms.txt + vzorky).
ENDPOINTS = {
    "trade_history": "/api/v1/trading/info/trade/history",
    "positions": "/api/v1/trading/info/portfolio",
    "cash_transactions": "/api/v1/trading/info/cash-transactions",
    "instruments": "/api/v1/market-data/instruments",
}
FIELD_ITEMS = "items"
WINDOW_DAYS = 360
MIN_INTERVAL = 1.05  # seconds between calls -> stays under 60/60s


class EtoroAuthError(RuntimeError):
    pass


class EtoroRateLimited(RuntimeError):
    def __init__(self, retry_after: float):
        super().__init__(f"eToro rate limit, retry after {retry_after}s")
        self.retry_after = retry_after


class EtoroClient:
    def __init__(self, app_key: str, user_key: str, *, transport=None,
                 base_url: str = "https://public-api.etoro.com"):
        self._client = httpx.Client(
            base_url=base_url, timeout=20.0, transport=transport,
            headers={"x-api-key": app_key, "x-user-key": user_key, "accept": "application/json"},
        )
        self._throttle = transport is None
        self._last_call = 0.0

    def _get(self, path: str, **params) -> dict:
        if self._throttle:
            wait = MIN_INTERVAL - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
        self._last_call = time.monotonic()
        response = self._client.get(path, params={k: v for k, v in params.items() if v is not None})
        if response.status_code in (401, 403):
            raise EtoroAuthError("eToro rejected the API key (check Read permission and Real environment)")
        if response.status_code == 429:
            raise EtoroRateLimited(float(response.headers.get("Retry-After", "60")))
        response.raise_for_status()
        return response.json()

    def _paged(self, path: str, **params) -> list[dict]:
        items: list[dict] = []
        page = 1
        while True:
            batch = self._get(path, page=page, **params).get(FIELD_ITEMS) or []
            if not batch:
                return items
            items.extend(batch)
            page += 1

    def trade_history(self, min_date: date) -> list[dict]:
        rows: list[dict] = []
        start = min_date
        today = datetime.now(timezone.utc).date()
        while start <= today:
            rows.extend(self._paged(ENDPOINTS["trade_history"], minDate=start.isoformat()))
            start += timedelta(days=WINDOW_DAYS)
        return rows

    def positions(self) -> list[dict]:
        return self._get(ENDPOINTS["positions"]).get(FIELD_ITEMS) or []

    def cash_transactions(self, min_date: date) -> list[dict]:
        return self._paged(ENDPOINTS["cash_transactions"], minDate=min_date.isoformat())

    def instruments(self, ids: Iterable[int]) -> dict[int, dict]:
        wanted = sorted(set(ids))
        if not wanted:
            return {}
        data = self._get(ENDPOINTS["instruments"], instrumentIds=",".join(map(str, wanted)))
        return {int(item["instrumentId"]): item for item in data.get(FIELD_ITEMS) or []}
```

Pozor na okna: pokud API vrací pro `minDate` všechno od data do dneška (ne jen
okno), dedup řeší mapper (`positionId`). Ověřit na vzorku a případně přidat
`maxDate`.

- [ ] **Step 5: Implementace mapperu**

```python
# backend/etoro_mapper.py
"""eToro positions/history/cash JSON -> ledger rows. Real (unleveraged long)
positions only; CFDs, shorts and copy-trading are counted, never imported."""
from __future__ import annotations

from datetime import datetime, timezone

from importers.base import ParseResult
from importers.dividends import DividendLeg, net_dividend_rows
from importers.instruments import DefaultInstrumentResolver, InstrumentRef

SOURCE = "etoro"
# Pole ověřit na vzorcích z Tasku 0.
FIELD_POSITION_ID = "positionId"
FIELD_INSTRUMENT_ID = "instrumentId"
FIELD_MIRROR_ID = "mirrorId"
ETORO_VENUES = {"NASDAQ": "US", "NYSE": "US", "XETRA": "XETRA", "LSE": "LSE",
                "EURONEXT AMSTERDAM": "AMSTERDAM", "EURONEXT PARIS": "PARIS", "BORSA ITALIANA": "MILAN"}


def _dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def _ticker(info: dict | None, resolver) -> str | None:
    if not info:
        return None
    if info.get("type") == "crypto":
        return f"{info['symbol'].upper()}-USD"
    ref = InstrumentRef(symbol=info.get("symbol"), venue=ETORO_VENUES.get((info.get("exchange") or "").upper()))
    return resolver.resolve_many([ref]).get(ref)


def map_account(history, positions, cash, instruments, *, resolver=None) -> ParseResult:
    resolver = resolver or DefaultInstrumentResolver(figi=None)
    result = ParseResult("eToro", rows=[], source_events=len(history) + len(positions) + len(cash))
    by_id: dict[str, dict] = {}
    for item in [*positions, *history]:  # closed history wins over open snapshot
        by_id[str(item[FIELD_POSITION_ID])] = item
    for pid, item in sorted(by_id.items()):
        if item.get(FIELD_MIRROR_ID):
            result.skip("copy trading")
            continue
        if (item.get("leverage") or 1) > 1 or item.get("isBuy") is False:
            result.skip("CFD / leveraged position")
            continue
        ticker = _ticker(instruments.get(int(item[FIELD_INSTRUMENT_ID])), resolver)
        if ticker is None:
            result.errors.append(f"eToro instrument {item[FIELD_INSTRUMENT_ID]} has no market ticker")
            continue
        units = float(item["units"])
        opened = _dt(item["openTimestamp"])
        common = {"ticker": ticker, "shares": units, "currency": "USD", "cash_currency": "USD",
                  "source": SOURCE, "source_event_stream": "positions",
                  "source_instrument_id": str(item[FIELD_INSTRUMENT_ID]), "notes": "eToro"}
        open_rate = float(item["openRate"])
        result.rows.append({**common, "type": "buy", "date": opened.date(), "executed_at": opened,
                            "price": open_rate, "cash_amount": units * open_rate,
                            "source_event_id": f"{pid}:open"})
        if item.get("closeTimestamp"):
            closed = _dt(item["closeTimestamp"])
            close_rate = float(item["closeRate"])
            result.rows.append({**common, "type": "sell", "date": closed.date(), "executed_at": closed,
                                "price": close_rate, "cash_amount": units * close_rate,
                                "source_event_id": f"{pid}:close"})
    # Cash: mapování typů doplnit podle vzorků (Task 0 bod 1) — vklad/výběr/
    # poplatek -> cash řádky, dividenda -> DividendLeg(kind="gross"), neznámý
    # typ -> result.errors. Do té doby neprázdné `cash` je chyba, ne tiché přeskočení:
    if cash:
        result.errors.append("eToro cash transactions are not mapped yet; see Task 0 question 1")
    div_rows, div_errors, _ = net_dividend_rows([], source=SOURCE)
    result.rows.extend(div_rows)
    result.errors.extend(div_errors)
    return result
```

Mapování cash transakcí je jediná vědomá mezera v kódu tohoto plánu. Dokud
není odpověď na otázku 1 z Tasku 0, mapper cash odmítne (fail-closed) a router
v Tasku 10 volá `cash_transactions()` jen tehdy, když je mapování hotové
(`CASH_MAPPED = True` v `etoro_mapper.py`). Až vzorek existuje: přidat tabulku
typ → ledger, testy `test_cash_deposit`, `test_cash_dividend_is_net`,
`test_unknown_cash_type_is_error` a přepnout `CASH_MAPPED`.

- [ ] **Step 6: PASS + fast suite → Step 7: Commit**

```bash
git add backend/etoro_client.py backend/etoro_mapper.py backend/tests/test_etoro_client.py backend/tests/test_etoro_mapper.py backend/tests/fixtures/brokers/etoro
git commit -m "feat(etoro): read-only Public API client and ledger mapper"
```

---

### Task 9: XTB XLSX (vlna 3, vlastní hotspot lockfiles)

**Files:**
- Modify: `backend/requirements.txt` (`openpyxl>=3.1`), `backend/requirements.lock`, `backend/requirements-dev.lock`
- Create: `backend/importers/formats/xtb.py`
- Test: `backend/tests/test_xtb_import.py` (fixture generuje test přes `openpyxl`; reálný vzorek z Tasku 0 do `backend/tests/fixtures/brokers/xtb/`)

**Interfaces:**
- Consumes: `parse_number`, `DividendLeg`, `net_dividend_rows`, `InstrumentRef`, `unresolved_errors`
- Produces: `FORMAT` (key `xtb`, „XTB (xStation)“), `XTB_SUFFIX_VENUES: dict[str, str]`

- [ ] **Step 1: Přidat závislost a přegenerovat locky** (z kořene repa, podle CLAUDE.md)

```bash
uv pip compile backend/requirements.txt --universal --generate-hashes --python-version 3.12 -o backend/requirements.lock
uv pip compile backend/requirements-dev.txt --universal --generate-hashes --python-version 3.12 -c backend/requirements.lock -o backend/requirements-dev.lock
uv pip install --require-hashes -r backend/requirements-dev.lock
```

Ověřit, že `git diff backend/requirements.lock` přidává jen `openpyxl` a
`et-xmlfile` a nic jiného se neposunulo (bez `--upgrade`).

- [ ] **Step 2: Failing testy.** Předpokládaná struktura podle research [ověřit Task 0]: list `CASH OPERATION HISTORY`, úvodní řádky (účet, `Currency` + hodnota), pak hlavička `ID | Type | Time | Comment | Symbol | Amount`.

```python
# backend/tests/test_xtb_import.py
import io
from datetime import datetime

import pytest
from openpyxl import Workbook

from importers.base import ImportFile, validate_rows
from importers.formats import xtb
from importers.instruments import DefaultInstrumentResolver

RESOLVER = DefaultInstrumentResolver(figi=None)


def _workbook(rows, currency="CZK"):
    wb = Workbook()
    ws = wb.active
    ws.title = "CASH OPERATION HISTORY"
    ws.append(["Account", "51234567"])
    ws.append(["Currency", currency])
    ws.append([])
    ws.append(["ID", "Type", "Time", "Comment", "Symbol", "Amount"])
    for row in rows:
        ws.append(row)
    wb.create_sheet("CLOSED POSITION HISTORY")
    buffer = io.BytesIO()
    wb.save(buffer)
    return ImportFile("xtb.xlsx", buffer.getvalue())


ROWS = [
    [1, "Deposit", datetime(2025, 1, 2, 9, 0), "Deposit", None, 50000],
    [2, "Stocks/ETF purchase", datetime(2025, 1, 2, 15, 31), "OPEN BUY 10 @ 190.50", "AAPL.US", -44005.5],
    [3, "DIVIDENT", datetime(2025, 5, 15, 8, 0), "AAPL.US USD 0.2500/ SHR", "AAPL.US", 57.75],
    [4, "Withholding Tax", datetime(2025, 5, 15, 8, 0), "AAPL.US USD WHT 15%", "AAPL.US", -8.66],
    [5, "Stocks/ETF sale", datetime(2025, 6, 2, 10, 0), "CLOSE BUY 4 @ 200.00", "AAPL.US", 18480.0],
    [6, "close trade", datetime(2025, 6, 3, 10, 0), "CLOSE BUY 0.1 @ 18000", "US500", 1200.0],
    [7, "Free-funds Interest", datetime(2025, 6, 30, 0, 0), "Free-funds Interest", None, 35.2],
    [8, "Free-funds Interest Tax", datetime(2025, 6, 30, 0, 0), "Free-funds Interest Tax", None, -5.28],
    [9, "CEZ.CZ purchase", datetime(2025, 7, 1, 10, 0), "OPEN BUY 5 @ 1000", "CEZ.CZ", -5000],
]


def test_detect_xlsx_only():
    assert xtb.FORMAT.detect(_workbook(ROWS))
    assert not xtb.FORMAT.detect(ImportFile("x.csv", b"a,b\n"))


def test_trades_from_comment():
    result = xtb.FORMAT.parse(_workbook(ROWS[:5]), RESOLVER)
    assert result.errors == [] and validate_rows(result.rows) == []
    [buy] = [r for r in result.rows if r["type"] == "buy"]
    assert (buy["ticker"], buy["shares"], buy["price"], buy["currency"]) == ("AAPL", 10, 190.5, "USD")
    assert (buy["cash_amount"], buy["cash_currency"]) == (44005.5, "CZK")
    [sell] = [r for r in result.rows if r["type"] == "sell"]
    assert sell["shares"] == 4 and sell["price"] == 200.0


def test_dividend_net_in_account_currency():
    [div] = [r for r in xtb.FORMAT.parse(_workbook(ROWS[:5]), RESOLVER).rows if r["type"] == "dividend"]
    assert div["cash_amount"] == pytest.approx(49.09) and div["cash_currency"] == "CZK"


def test_xtb_cfd_rows_skipped():
    result = xtb.FORMAT.parse(_workbook([ROWS[5]]), RESOLVER)
    assert result.skipped_reasons == {"CFD trade": 1}
    assert result.errors == []


def test_interest_tax_becomes_fee():
    rows = xtb.FORMAT.parse(_workbook(ROWS[6:8]), RESOLVER).rows
    assert sorted((r["type"], r["amount"]) for r in rows) == [("fee", 5.28), ("interest", 35.2)]


def test_unknown_type_is_error():
    result = xtb.FORMAT.parse(_workbook([ROWS[8]]), RESOLVER)
    assert any("CEZ.CZ purchase" in e for e in result.errors)


def test_event_ids_are_xtb_ids():
    ids = [r["source_event_id"] for r in xtb.FORMAT.parse(_workbook(ROWS[:2]), RESOLVER).rows]
    assert ids == ["1", "2"]


def test_missing_account_currency_is_error():
    wb_file = _workbook(ROWS[:1], currency=None)
    assert xtb.FORMAT.parse(wb_file, RESOLVER).errors
```

- [ ] **Step 3: Spustit, ověřit FAIL**

- [ ] **Step 4: Implementace**

```python
# backend/importers/formats/xtb.py
"""XTB xStation 5 Account History export (XLSX), cash-operations sheet.

The cash-operations sheet alone carries every money and position movement
for stocks/ETFs: buys/sells encode quantity and price in the comment. CFD
lines are counted and skipped; they are not ownership.
"""
from __future__ import annotations

from datetime import datetime, timezone
import io
import re
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from importers.base import ImportFile, ImportFormat, ParseResult
from importers.dividends import DividendLeg, net_dividend_rows
from importers.instruments import InstrumentRef, unresolved_errors

SOURCE = "xtb"
_SERVER_TZ = ZoneInfo("Europe/Warsaw")  # ověřit Task 0
_TRADE = re.compile(r"^(OPEN|CLOSE) BUY ([0-9.]+)(?:/[0-9.]+)? @ ([0-9.]+)$")
XTB_SUFFIX_VENUES = {"US": "US", "DE": "XETRA", "UK": "LSE", "NL": "AMSTERDAM", "FR": "PARIS",
                     "IT": "MILAN", "CH": "SIX", "CZ": "PRAGUE", "PL": "WARSAW", "ES": "MADRID",
                     "BE": "BRUSSELS"}
_PRICE_CCY = {"US": "USD", "DE": "EUR", "NL": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR",
              "BE": "EUR", "UK": "GBX", "CH": "CHF", "CZ": "CZK", "PL": "PLN"}  # UK=GBX ověřit
_CASH = {"deposit": "deposit", "withdrawal": "withdrawal", "free-funds interest": "interest",
         "free-funds interest tax": "fee", "sec fee": "fee", "commission": "fee"}
_CFD = {"close trade", "profit/loss", "swap", "rollover"}


def _sheet(wb):
    return next((ws for ws in wb.worksheets if "CASH OPERATION" in ws.title.upper()), None)


def _detect(file: ImportFile) -> bool:
    if file.content[:2] != b"PK":
        return False
    wb = load_workbook(io.BytesIO(file.content), read_only=True, data_only=True)
    try:
        return _sheet(wb) is not None
    finally:
        wb.close()


def _parse(file: ImportFile, resolver) -> ParseResult:
    result = ParseResult("XTB (xStation)", rows=[], source_events=0)
    wb = load_workbook(io.BytesIO(file.content), read_only=True, data_only=True)
    try:
        values = [list(row) for row in _sheet(wb).iter_rows(values_only=True)]
    finally:
        wb.close()
    account_ccy = next((str(r[1]).upper() for r in values
                        if r and r[0] == "Currency" and len(r) > 1 and r[1]), None)
    header_at = next((i for i, r in enumerate(values) if r and {"ID", "Type", "Amount"} <= set(r)), None)
    if not account_ccy or header_at is None:
        result.errors.append("XTB export: account currency or the cash-operations header is missing")
        return result
    col = {name: i for i, name in enumerate(values[header_at]) if name}
    rows = [r for r in values[header_at + 1:] if r and r[col["ID"]] is not None]
    result.source_events = len(rows)

    def ref_for(symbol: str) -> InstrumentRef:
        base, _, suffix = symbol.rpartition(".")
        return InstrumentRef(symbol=base, venue=XTB_SUFFIX_VENUES.get(suffix), name=symbol)

    # Only symbols of stock/ETF trades and dividends need a ticker; CFD
    # symbols (US500) must never be reported as unresolved.
    symbols = {r[col["Symbol"]] for r in rows
               if r[col["Symbol"]] and str(r[col["Type"]] or "").strip().lower() not in _CFD}
    refs = {s: ref_for(s) for s in symbols}
    resolved = resolver.resolve_many(list(refs.values()))
    legs: list[DividendLeg] = []

    for row in rows:
        event_id = str(row[col["ID"]])
        kind = str(row[col["Type"]] or "").strip()
        when = row[col["Time"]]
        if not isinstance(when, datetime):
            result.errors.append(f"XTB {event_id}: time is missing")
            continue
        executed_at = when.replace(tzinfo=_SERVER_TZ).astimezone(timezone.utc)
        amount = float(row[col["Amount"]] or 0.0)
        symbol = row[col["Symbol"]]
        comment = str(row[col["Comment"]] or "").strip()
        lowered = kind.lower()
        common = {"date": executed_at.date(), "executed_at": executed_at, "source": SOURCE,
                  "source_event_stream": "cash_operations", "source_event_id": event_id, "notes": comment}
        if lowered in _CFD:
            result.skip("CFD trade")
        elif lowered in _CASH:
            result.rows.append({**common, "type": _CASH[lowered], "ticker": None, "shares": 0.0,
                                "price": 0.0, "amount": abs(amount), "currency": account_ccy})
        elif lowered in {"stocks/etf purchase", "stocks/etf sale"}:
            match = _TRADE.match(comment)
            ticker = resolved.get(refs.get(symbol))
            if not match:
                result.errors.append(f"XTB {event_id}: cannot read quantity/price from {comment!r}")
                continue
            if ticker is None:
                continue
            suffix = symbol.rpartition(".")[2]
            result.rows.append({**common, "type": "buy" if match.group(1) == "OPEN" else "sell",
                                "ticker": ticker, "name": symbol, "shares": float(match.group(2)),
                                "price": float(match.group(3)), "currency": _PRICE_CCY.get(suffix, account_ccy),
                                "cash_amount": abs(amount), "cash_currency": account_ccy,
                                "source_instrument_id": symbol})
        elif lowered in {"divident", "dividend", "withholding tax"}:
            ticker = resolved.get(refs.get(symbol))
            if ticker is None:
                continue
            legs.append(DividendLeg(group_key=f"{symbol}|{executed_at.date().isoformat()}",
                                    kind="tax" if lowered == "withholding tax" else "gross",
                                    ticker=ticker, name=symbol, pay_date=executed_at.date(),
                                    currency=account_ccy, amount=amount, executed_at=executed_at,
                                    instrument_id=symbol))
        else:
            result.errors.append(f"XTB {event_id}: unsupported operation type {kind!r}")

    div_rows, div_errors, div_skipped = net_dividend_rows(legs, source=SOURCE)
    result.rows.extend(div_rows)
    result.errors.extend(div_errors)
    for _ in range(div_skipped):
        result.skip("fully reversed dividend")
    all_refs = list(refs.values())
    result.errors.extend(unresolved_errors([r for r in all_refs if r not in resolved], resolved))
    return result


FORMAT = ImportFormat("xtb", "XTB (xStation)", _detect, _parse)
```

`test_xtb_cfd_rows_skipped` navíc ověří `result.errors == []`, tedy že se CFD
symbol nehlásí jako nevyřešený ticker.

Pro dividendy v měně účtu má `DividendLeg.currency = account_ccy`, takže
`price` dividendy je v CZK, ne v USD. To je v pořádku, protože analytika
dividend čte `cash_amount`/`cash_currency` (`signed_cash`).

- [ ] **Step 5: PASS + fast suite na 3.12 i 3.14** (lockfile změna, podle CLAUDE.md)

```bash
cd backend && python -m pytest tests/ --ignore=tests/postgres -q
uv venv .venv314 --python 3.14
uv pip install --python .venv314 --require-hashes -r requirements-dev.lock
.venv314/Scripts/python -m pytest tests/ --ignore=tests/postgres -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/requirements.lock backend/requirements-dev.lock backend/importers/formats/xtb.py backend/tests/test_xtb_import.py
git commit -m "feat(import): XTB xStation XLSX import (adds openpyxl)"
```

---

### Task 10: eToro router, auto-sync a konfigurace (vlna 3, hotspoty `main.py`, `jobs.py`)

**Files:**
- Create: `backend/routers/etoro.py`, `backend/ledger_import.py`
- Modify: `backend/ibkr_ledger.py` (použije `ledger_import`), `backend/main.py` (mount), `backend/jobs.py` (větev `elif conn.broker == "etoro"` v auto-sync passu, ~ř. 312–342), `deploy/cloudrun.md` (secret `PORTFYL_ETORO_APP_KEY`)
- Test: `backend/tests/test_etoro_router.py`

**Interfaces:**
- Consumes: `EtoroClient`, `EtoroAuthError`, `EtoroRateLimited`, `map_account`, `CASH_MAPPED`, `validate_rows`, vzor `routers/ibkr.py` (connect/status/auto-sync/disconnect, `require_capability("broker_sync")`, `require_writable_broker("etoro")`, `rate_limit("broker_sync", by="workspace")`, audit eventy `broker.connection.created/deleted`)
- Produces:
  - `ledger_import.insert_new_provider_rows(db, portfolio, rows, *, source) -> dict` (vytaženo z `apply_flex_ledger`: FX, lock, ochrana proti ručním řádkům, dedup, kapacita, insert; vrací `status`/`imported`/`already_present`/`errors`)
  - `POST /api/broker/etoro/connect {user_key}`, `GET /api/broker/etoro/status`, `POST /api/broker/etoro/sync`, `POST /api/broker/etoro/auto-sync {enabled}`, `DELETE /api/broker/etoro/connect`
  - `etoro_sync(db, workspace_id, portfolio_id) -> dict` (sync def, volá ho router i jobs)

Chování:
- `connect`: chybí `PORTFYL_ETORO_APP_KEY` → 503 „eToro integration is not configured“. Klíč ověřit jedním `positions()` voláním (`EtoroAuthError` → 400 s návodem: Settings → Trading → API Key Management, permission Read, Real). Uložit do `BrokerConnection(broker="etoro", api_key=user_key)`, šifrováno stávajícími properties.
- `etoro_sync`: `release_request_connections()` před outbound, `min_date = last_synced_at.date() - 30 dní` nebo `2007-01-01` při prvním syncu, `map_account(...)` (cash jen pokud `CASH_MAPPED`), chyby → `needs_attention` + `last_error`, jinak `insert_new_provider_rows(..., source="etoro")`. `EtoroRateLimited` → 429 s `Retry-After`. `EtoroAuthError` → `needs_attention`, `last_error`.
- Plain `def` všude. `jobs.py`: eToro větev volá `etoro_sync` přímo (je sync), ne přes loop.
- Tento task vlastní `ibkr_ledger.py` (Task 4 je v té době mergnutý) a refaktoruje ho na `insert_new_provider_rows`. Testy Tasku 4 musí dál procházet beze změny.

- [ ] **Step 1: Failing testy** (router funkce volané napřímo, `EtoroClient` nahrazený fake třídou)

```python
# backend/tests/test_etoro_router.py
import pytest
from fastapi import HTTPException

from etoro_client import EtoroAuthError
from routers import etoro as etoro_router


class FakeClient:
    def __init__(self, app_key, user_key, **kw):
        self.user_key = user_key

    def positions(self):
        if self.user_key == "bad":
            raise EtoroAuthError("bad key")
        return []

    def trade_history(self, min_date):
        return [{"positionId": 1, "instrumentId": 1001, "isBuy": True, "leverage": 1, "units": 2.0,
                 "openRate": 190.0, "openTimestamp": "2025-01-02T14:30:00Z",
                 "closeRate": 200.0, "closeTimestamp": "2025-03-03T15:00:00Z"}]

    def cash_transactions(self, min_date):
        return []

    def instruments(self, ids):
        return {1001: {"symbol": "AAPL", "exchange": "NASDAQ", "type": "stock"}}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PORTFYL_ETORO_APP_KEY", "app")
    monkeypatch.setattr(etoro_router, "EtoroClient", FakeClient)


def test_connect_requires_app_key(monkeypatch, db, portfolio, context):
    monkeypatch.delenv("PORTFYL_ETORO_APP_KEY")
    with pytest.raises(HTTPException) as exc:
        etoro_router.connect(etoro_router.ConnectBody(user_key="u"), db=db, portfolio=portfolio, context=context)
    assert exc.value.status_code == 503


def test_connect_rejects_bad_key(db, portfolio, context):
    with pytest.raises(HTTPException) as exc:
        etoro_router.connect(etoro_router.ConnectBody(user_key="bad"), db=db, portfolio=portfolio, context=context)
    assert exc.value.status_code == 400


def test_sync_is_idempotent(db, portfolio, context, monkeypatch):
    monkeypatch.setattr("ledger_import.bulk_fetch_fx", lambda keys: {})
    etoro_router.connect(etoro_router.ConnectBody(user_key="u"), db=db, portfolio=portfolio, context=context)
    first = etoro_router.etoro_sync(db, portfolio.workspace_id, portfolio.id)
    db.commit()
    second = etoro_router.etoro_sync(db, portfolio.workspace_id, portfolio.id)
    assert first["imported"] == 2 and second["imported"] == 0


def test_status_never_returns_key(db, portfolio, context):
    etoro_router.connect(etoro_router.ConnectBody(user_key="secret-user-key"), db=db, portfolio=portfolio, context=context)
    status = etoro_router.get_status(db=db, portfolio=portfolio)
    assert "secret-user-key" not in str(status)
```

Fixtures `db`, `portfolio`, `context` postavit jako v `tests/test_broker.py`
(lokálně v souboru, pokud nejsou v conftestu).

- [ ] **Step 2: Spustit, ověřit FAIL**

- [ ] **Step 3: Vytáhnout `ledger_import.insert_new_provider_rows`** z `ibkr_ledger.apply_flex_ledger` (kód od „FX does not depend on ledger state“ dál, parametrizovaný `source`). `apply_flex_ledger` po refaktoru:

```python
def apply_flex_ledger(db, portfolio, xml_text, *, resolver):
    if not has_ledger_sections(xml_text):
        return {"status": "sections_missing", "imported": 0, "already_present": 0, "errors": []}
    parsed = parse_flex_statement(xml_text, resolver)
    errors = [*parsed.errors, *validate_rows(parsed.rows)]
    if errors:
        return {"status": "needs_review", "imported": 0, "already_present": 0, "errors": errors[:20]}
    return insert_new_provider_rows(db, portfolio, parsed.rows, source=SOURCE)
```

Run: `cd backend && python -m pytest tests/test_ibkr_ledger_sync.py -v` → PASS (beze změny testů; monkeypatch `bulk_fetch_fx` přesměrovat na `ledger_import.bulk_fetch_fx`, pokud ho test patchuje přes modul).

- [ ] **Step 4: Implementovat `routers/etoro.py`.** Strukturu connect/status/auto-sync/disconnect zkopírovat z `routers/ibkr.py` (ř. 362–567), Flex volání nahradit `EtoroClient`. Router `APIRouter(prefix="/broker/etoro")`. Mount v `main.py` vedle `ibkr.router`:

```python
app.include_router(etoro.router, prefix="/api", dependencies=_CSRF_DEPENDENCIES)
```

- [ ] **Step 5: `jobs.py`.** V auto-sync passu (vedle `elif conn.broker == "ibkr":`) přidat:

```python
            elif conn.broker == "etoro":
                from routers.etoro import etoro_sync
                r = etoro_sync(db, workspace_id, conn.portfolio_id)
```

Dead-letter počítadlo (`consecutive_failures`) funguje stejně jako u IBKR.
Ověřit testem v `tests/test_broker_dead_letter.py` (přidat případ pro eToro).

- [ ] **Step 6: Ověřit, že `/broker` je portfolio-scoped cesta** (frontend posílá `portfolio_id` automaticky, `PORTFOLIO_AGNOSTIC_PREFIXES` se nemění).

- [ ] **Step 7: `deploy/cloudrun.md`:** do sekce secretů přidat `PORTFYL_ETORO_APP_KEY` (Secret Manager, `--set-secrets`) a volitelně `OPENFIGI_API_KEY`. Hodnoty necommitovat.

- [ ] **Step 8: Testy**

Run: `cd backend && python -m pytest tests/test_etoro_router.py tests/test_ibkr_ledger_sync.py tests/test_broker_dead_letter.py tests/test_event_loop_not_blocked.py -v`, pak celý fast suite a `tests/postgres/` (vlastní DB lane `etoro`).

- [ ] **Step 9: Commit**

```bash
git add backend/routers/etoro.py backend/ledger_import.py backend/ibkr_ledger.py backend/main.py backend/jobs.py deploy/cloudrun.md backend/tests/test_etoro_router.py backend/tests/test_broker_dead_letter.py
git commit -m "feat(etoro): connect, sync and auto-sync eToro accounts via Public API"
```

---

### Task 11: Frontend: návody k exportu, nové formáty v importu, eToro v nastavení

**Files:**
- Create: `frontend/src/components/import/BrokerGuides.jsx`, `frontend/src/components/import/BrokerGuides.test.jsx`
- Modify: `frontend/src/pages/Import.jsx` (badge, `accept`, skipped reasons, varování o replace jen u T212), `frontend/src/pages/Import.test.jsx`, `frontend/src/pages/Settings.jsx` (karta eToro, informace o IBKR akciovém syncu), `frontend/src/api.js` (eToro volání)

**Interfaces:**
- Consumes: preview response `format`, `counts`, `skipped_reasons: Record<string, number>`; IBKR sync response `ledger.status`/`ledger.errors`; eToro endpointy z Tasku 10
- Produces: `<BrokerGuides />` (accordion podle brokera), `api.js`: `fetchEtoroStatus`, `connectEtoro(userKey)`, `syncEtoro()`, `setEtoroAutoSync(enabled)`, `disconnectEtoro()`

Obsah návodů (jazyk podle stávajícího UI v `Import.jsx`):
- **IBKR:** Reporting → Flex Queries → Activity Flex Query; zaškrtnout Trades (Execution), Cash Transactions (Detail), Corporate Actions, Transfers, Open Positions, Account Information; formát XML; datum `yyyyMMdd`, čas `HHmmss`, oddělovač `;`. Pro historii starší než rok vygenerovat XML po letech a nahrát všechny. Plus text promptu pro IBKR AI konfigurátor Flex Query. Lynx: stejný postup.
- **Degiro:** Inbox → Transactions → celé měsíce → Export CSV; Inbox → Account Statement → Export CSV. Nahrát oba soubory, každý zvlášť.
- **XTB:** xStation 5 (web) → Historie účtu → Peněžní operace → Export (Excel).
- **Schwab:** Accounts → History → Transactions → All → Export; po celých kvartálech (limit 1500 řádků).
- **Fidelity:** Activity & Orders → Download.
- **eToro:** Nastavení → Trading → API Key Management → nový klíč, oprávnění Read, prostředí Real → vložit v Portfylu do Nastavení → Brokeři.

- [ ] **Step 1: Failing testy**

```jsx
// frontend/src/components/import/BrokerGuides.test.jsx
import { fireEvent, render, screen } from "@testing-library/react";
import BrokerGuides from "./BrokerGuides";

test("lists every phase-1 broker", () => {
  render(<BrokerGuides />);
  for (const name of ["Interactive Brokers", "Degiro", "XTB", "Charles Schwab", "Fidelity", "eToro"]) {
    expect(screen.getByRole("button", { name: new RegExp(name, "i") })).toBeInTheDocument();
  }
});

test("expands the IBKR guide with required Flex sections", () => {
  render(<BrokerGuides />);
  fireEvent.click(screen.getByRole("button", { name: /Interactive Brokers/i }));
  expect(screen.getByText(/Cash Transactions/)).toBeInTheDocument();
  expect(screen.getByText(/Corporate Actions/)).toBeInTheDocument();
});
```

V `Import.test.jsx` přidat: preview s `format: "Degiro (Transactions)"` a
`skipped_reasons: {"trade settlement (imported from Transactions.csv)": 3}` →
zobrazí se důvod a počet; **nezobrazí** se varování o nahrazení portfolia
(to jen pro „Trading 212“).

- [ ] **Step 2: FAIL** (`cd frontend && npm test -- BrokerGuides`)
- [ ] **Step 3: Implementace** ve stávajícím stylu (tokeny z `index.css`, existující `FormatBadge` rozšířit o neutrální barvu pro ne-T212 formáty). File input `accept=".csv,.xml,.xlsx"`. Texty „CSV“ v UI změnit na „soubor/export“, kde se týkají i XML/XLSX.
- [ ] **Step 4: Ověření**

```bash
cd frontend && npm test && npm run test:cloud && npm run build && npm run build:cloud
```

- [ ] **Step 5: UI ověření v prohlížeči** (vlastní porty lane `frontend`): spustit backend + frontend, přihlásit se testovacím Firebase účtem, nahrát fixtures z `backend/tests/fixtures/brokers/*` přes Import → preview → commit → undo; screenshot preview pro Degiro a IBKR XML; v Nastavení zkontrolovat kartu eToro (bez app key ukáže „není nakonfigurováno“).
- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/import frontend/src/pages/Import.jsx frontend/src/pages/Import.test.jsx frontend/src/pages/Settings.jsx frontend/src/api.js
git commit -m "feat(frontend): broker export guides, multi-format import preview, eToro connection"
```

---

### Task 12: Integrace, PostgreSQL gate, dokumentace

**Files:**
- Modify: `CLAUDE.md` (sekce Architecture: `backend/importers/`, nové `source` hodnoty, eToro router v seznamu routerů), `docs/research/2026-10-16-broker-integrations.md` (nahoře řádek „Fáze 1 implementována podle plánu `docs/superpowers/plans/2026-10-16-portfyl-broker-integrations.md`“)

- [ ] **Step 1:** Rebase na `main`, vyřešit konflikty.
- [ ] **Step 2:** `cd backend && python -m pytest tests/ -v` (fast suite + `tests/postgres/` proti disposable DB `portfyl_test_integration`).
- [ ] **Step 3:** `alembic heads` == `EXPECTED_ALEMBIC_HEAD` (`0023_allocation_targets`; fáze 1 migraci nepřidává).
- [ ] **Step 4:** Frontend: `npm test && npm run test:cloud && npm run build && npm run build:cloud`.
- [ ] **Step 5:** End-to-end v prohlížeči: jedno portfolio na broker (IBKR XML, Degiro oba soubory, XTB, Schwab, Fidelity). Dashboard ukazuje pozice s cenami (tickery se našly na Yahoo), Dividends ukazuje čisté dividendy, druhý import stejného souboru přidá 0 řádků, undo vrátí stav.
- [ ] **Step 6:** Aktualizovat dokumentaci a commit.

```bash
git add CLAUDE.md docs/research/2026-10-16-broker-integrations.md
git commit -m "docs: document broker import architecture"
```

---

## Mimo rozsah tohoto plánu (follow-upy)

- **IBKR `OpenPositions` rekonciliace** (porovnání dopočtených pozic s brokerem, `BrokerPosition` snapshot jako u T212). Samostatný task po Tasku 4.
- **Per-workspace ruční mapování instrumentů** (UI „tento ISIN = tento ticker“), když OpenFIGI nic nenajde. Potřebuje migraci.
- **Perzistentní cache OpenFIGI** (tabulka), pokud se ukáže nesoulad preview/commit mezi instancemi.
- **eToro OAuth 2.0 + PKCE** místo osobního klíče (po odpovědi partner týmu).
- **eToro copy-trading pozice.**
- **Fáze 2: SnapTrade** (samostatný plán, až po splnění spouštěče ze specu).

## Self-review

- Pokrytí specu: IBKR Trades/Cash/CorporateActions/Transfers ✔ (Task 3–4), OpenPositions → follow-up (vědomě), ConversionRates → nahrazeno `fxRateToBase` při CZK bázi a `bulk_fetch_fx` jinak; XML upload pro historii > 365 dní ✔ (Task 1+3); eToro osobní klíče ✔ (Task 8, 10), OAuth → follow-up; Degiro oba CSV + vícejazyčnost + ISIN mapování ✔ (Task 2, 5); XTB XLSX + `openpyxl` jako hotspot ✔ (Task 9); Schwab/Fidelity ✔ (Task 6–7); sdílená vrstva `ImportRow` → realizováno jako ledger dict + `validate_rows` ✔; capability → bez nových, `csv_import`/`broker_sync` ✔; onboarding návody ✔ (Task 11); otevřené otázky specu → Task 0.
- Placeholdery: vědomé neznámé jsou eToro cesty/pole (+ mapování cash transakcí, fail-closed do odpovědi z Tasku 0), přesné XTB/Fidelity sloupce a sémantika IBKR `FS`/`RS`. Jsou izolované do konstant (`ENDPOINTS`, `FIELD_*`, `CASH_MAPPED`, indexy sloupců) a Task 0 je dodává z reálných vzorků.
- Konzistence typů: `ParseResult(format_name, rows, source_events, skipped_reasons, errors)`, `InstrumentRef(isin, symbol, venue, currency, name)`, `resolve_many`, `net_dividend_rows(legs, *, source, stream)`, `DividendLeg` pole a `insert_new_provider_rows(db, portfolio, rows, *, source)` jsou stejné ve všech taskách.
