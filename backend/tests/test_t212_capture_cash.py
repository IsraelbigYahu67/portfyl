import pytest

from scripts.t212_capture_cash_transactions import (
    CASH_ENDPOINT,
    collect_pages,
    select_examples,
    summarize,
    validate_cash_next_path,
)


def _tx(kind, amount, ref="r", when="2026-03-01T10:00:00Z"):
    return {
        "type": kind,
        "amount": amount,
        "currency": "EUR",
        "reference": ref,
        "dateTime": when,
    }


def test_next_path_must_stay_on_the_cash_endpoint():
    ok = f"/api/v0{CASH_ENDPOINT}?limit=50&cursor=abc"
    assert validate_cash_next_path(ok) == f"{CASH_ENDPOINT}?limit=50&cursor=abc"
    assert validate_cash_next_path(None) is None
    assert validate_cash_next_path("https://evil.example/api/v0/equity/history/transactions") is None
    assert validate_cash_next_path("/api/v0/equity/history/orders?limit=50") is None
    assert validate_cash_next_path(f"{CASH_ENDPOINT}?limit=50&token=x") is None


def test_collect_pages_follows_next_path_until_the_page_budget():
    pages = {
        None: ([_tx("DEPOSIT", 100, "a")], f"{CASH_ENDPOINT}?cursor=1"),
        f"{CASH_ENDPOINT}?cursor=1": ([_tx("FEE", -1, "b")], f"{CASH_ENDPOINT}?cursor=2"),
        f"{CASH_ENDPOINT}?cursor=2": ([_tx("TRANSFER", 5, "c")], None),
    }
    calls = []

    def fetch(path):
        calls.append(path)
        return pages[path]

    items, exhausted = collect_pages(fetch, max_pages=2)
    assert [i["reference"] for i in items] == ["a", "b"]
    assert exhausted is False
    assert len(calls) == 2

    items, exhausted = collect_pages(fetch, max_pages=5)
    assert [i["reference"] for i in items] == ["a", "b", "c"]
    assert exhausted is True


def test_summary_counts_types_and_amount_signs():
    items = [
        _tx("DEPOSIT", 100),
        _tx("DEPOSIT", 50),
        _tx("WITHDRAW", -20),
        _tx("TRANSFER", 7),
        _tx("TRANSFER", -7),
    ]
    summary = summarize(items)
    assert summary["DEPOSIT"] == {"count": 2, "positive": 2, "negative": 0}
    assert summary["WITHDRAW"] == {"count": 1, "positive": 0, "negative": 1}
    assert summary["TRANSFER"] == {"count": 2, "positive": 1, "negative": 1}


def test_examples_cap_known_types_but_keep_every_transfer_and_unknown():
    items = [_tx("DEPOSIT", i, f"d{i}") for i in range(1, 8)]
    items += [_tx("TRANSFER", i, f"t{i}") for i in range(1, 6)]
    items += [_tx("MYSTERY", 1, "m1")]
    picked = select_examples(items, per_type=3)
    kinds = [i["type"] for i in picked]
    assert kinds.count("DEPOSIT") == 3
    assert kinds.count("TRANSFER") == 5
    assert kinds.count("MYSTERY") == 1


def test_capture_never_needs_the_key_on_the_command_line():
    import scripts.t212_capture_cash_transactions as mod

    with pytest.raises(SystemExit):
        mod.read_credentials({})
