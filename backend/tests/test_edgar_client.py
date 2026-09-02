"""Tests for edgar_client.py -- fetching + best-effort parsing of SEC 13D/13G
cover-page fields (shares owned, percent of class) that Shibui's
beneficial_ownership table doesn't carry (see StockDetail.jsx's
ShibuiOwnershipFilingsSection and market.py's get_shibui_activist_stakes).
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# fetch_filing_document
# ---------------------------------------------------------------------------


class TestFetchFilingDocument:
    def test_builds_correct_url_and_sends_user_agent(self, monkeypatch):
        import edgar_client

        captured = {}

        class FakeResponse:
            text = "<html>ok</html>"

            def raise_for_status(self):
                pass

        def fake_get(url, headers=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse()

        monkeypatch.setattr(edgar_client.httpx, "get", fake_get)
        monkeypatch.setattr(edgar_client, "_throttle", lambda: None)

        out = edgar_client.fetch_filing_document("0001045810", "0001045810-24-000029", "nvda-13g.htm")

        assert out == "<html>ok</html>"
        # Leading zeros stripped from the CIK, dashes stripped from the accession number.
        assert captured["url"] == (
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581024000029/nvda-13g.htm"
        )
        assert "tom.zoubek@gmail.com" in captured["headers"]["User-Agent"]

    def test_raises_edgar_error_on_http_failure(self, monkeypatch):
        import edgar_client
        import httpx

        def fake_get(url, headers=None, timeout=None):
            raise httpx.ConnectError("boom")

        monkeypatch.setattr(edgar_client.httpx, "get", fake_get)
        monkeypatch.setattr(edgar_client, "_throttle", lambda: None)

        with pytest.raises(edgar_client.EdgarError):
            edgar_client.fetch_filing_document("1045810", "0001045810-24-000029", "doc.htm")

    def test_raises_edgar_error_on_bad_status(self, monkeypatch):
        import edgar_client
        import httpx

        class FakeResponse:
            def raise_for_status(self):
                raise httpx.HTTPStatusError("404", request=None, response=None)

        monkeypatch.setattr(edgar_client.httpx, "get", lambda *a, **k: FakeResponse())
        monkeypatch.setattr(edgar_client, "_throttle", lambda: None)

        with pytest.raises(edgar_client.EdgarError):
            edgar_client.fetch_filing_document("1045810", "0001045810-24-000029", "doc.htm")


# ---------------------------------------------------------------------------
# _throttle -- keeps every caller under SEC's 10 req/s fair-access limit
# ---------------------------------------------------------------------------


class TestThrottle:
    def test_sleeps_when_called_again_too_soon(self, monkeypatch):
        import edgar_client

        edgar_client._last_request_at = 0.0
        times = iter([100.0, 100.05])
        sleeps = []
        monkeypatch.setattr(edgar_client.time, "monotonic", lambda: next(times))
        monkeypatch.setattr(edgar_client.time, "sleep", lambda s: sleeps.append(s))

        edgar_client._throttle()
        edgar_client._throttle()

        assert len(sleeps) == 1
        assert sleeps[0] == pytest.approx(edgar_client._MIN_INTERVAL - 0.05, abs=1e-6)

    def test_does_not_sleep_when_calls_are_far_apart(self, monkeypatch):
        import edgar_client

        edgar_client._last_request_at = 0.0
        times = iter([100.0, 105.0])
        sleeps = []
        monkeypatch.setattr(edgar_client.time, "monotonic", lambda: next(times))
        monkeypatch.setattr(edgar_client.time, "sleep", lambda s: sleeps.append(s))

        edgar_client._throttle()
        edgar_client._throttle()

        assert sleeps == []


# ---------------------------------------------------------------------------
# parse_ownership_summary -- Item 5 cover-page extraction
# ---------------------------------------------------------------------------

# Real Schedule 13G cover-page item numbering/labels (Rule 13d-102) -- rows
# 9 and 11. Boilerplate text is SEC-mandated and identical across filers.
_SC_13G_COVER_PAGE = """
<table>
<tr><td>1</td><td>NAMES OF REPORTING PERSONS<br/>NVIDIA CORPORATION</td></tr>
<tr><td>2</td><td>CHECK THE APPROPRIATE BOX IF A MEMBER OF A GROUP (a) [ ] (b) [ ]</td></tr>
<tr><td>3</td><td>SEC USE ONLY</td></tr>
<tr><td>4</td><td>CITIZENSHIP OR PLACE OF ORGANIZATION<br/>Delaware</td></tr>
<tr><td colspan="2">NUMBER OF SHARES BENEFICIALLY OWNED BY EACH REPORTING PERSON WITH:</td></tr>
<tr><td>5</td><td>SOLE VOTING POWER<br/>24,000,000</td></tr>
<tr><td>6</td><td>SHARED VOTING POWER<br/>0</td></tr>
<tr><td>7</td><td>SOLE DISPOSITIVE POWER<br/>24,000,000</td></tr>
<tr><td>8</td><td>SHARED DISPOSITIVE POWER<br/>0</td></tr>
<tr><td>9</td><td>AGGREGATE AMOUNT BENEFICIALLY OWNED BY EACH REPORTING PERSON<br/>24,000,000</td></tr>
<tr><td>10</td><td>CHECK BOX IF THE AGGREGATE AMOUNT IN ROW (9) EXCLUDES CERTAIN SHARES [ ]</td></tr>
<tr><td>11</td><td>PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (9)<br/>6.2%</td></tr>
<tr><td>12</td><td>TYPE OF REPORTING PERSON<br/>CO</td></tr>
</table>
"""

# Real Schedule 13D cover-page item numbering (Rule 13d-101) -- rows 11 and
# 13, different numbers than 13G but the same label text, proving the parser
# matches on label text rather than row number.
_SC_13D_COVER_PAGE = """
<table>
<tr><td>1</td><td>NAMES OF REPORTING PERSONS<br/>ACTIVIST CAPITAL LLC</td></tr>
<tr><td>2</td><td>CHECK THE APPROPRIATE BOX IF A MEMBER OF A GROUP (a) [ ] (b) [ ]</td></tr>
<tr><td>3</td><td>SEC USE ONLY</td></tr>
<tr><td>4</td><td>SOURCE OF FUNDS<br/>WC</td></tr>
<tr><td>5</td><td>CHECK BOX IF DISCLOSURE OF LEGAL PROCEEDINGS IS REQUIRED PURSUANT TO ITEMS 2(d) or 2(e) [ ]</td></tr>
<tr><td>6</td><td>CITIZENSHIP OR PLACE OF ORGANIZATION<br/>Delaware</td></tr>
<tr><td colspan="2">NUMBER OF SHARES BENEFICIALLY OWNED BY EACH REPORTING PERSON WITH:</td></tr>
<tr><td>7</td><td>SOLE VOTING POWER<br/>3,450,000</td></tr>
<tr><td>8</td><td>SHARED VOTING POWER<br/>0</td></tr>
<tr><td>9</td><td>SOLE DISPOSITIVE POWER<br/>3,450,000</td></tr>
<tr><td>10</td><td>SHARED DISPOSITIVE POWER<br/>0</td></tr>
<tr><td>11</td><td>AGGREGATE AMOUNT BENEFICIALLY OWNED BY EACH REPORTING PERSON<br/>3,450,000</td></tr>
<tr><td>12</td><td>CHECK BOX IF THE AGGREGATE AMOUNT IN ROW (11) EXCLUDES CERTAIN SHARES [ ]</td></tr>
<tr><td>13</td><td>PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (11)<br/>8.1%</td></tr>
<tr><td>14</td><td>TYPE OF REPORTING PERSON<br/>OO</td></tr>
</table>
"""


class TestParseOwnershipSummary:
    def test_extracts_13g_cover_page_fields(self):
        import edgar_client

        out = edgar_client.parse_ownership_summary(_SC_13G_COVER_PAGE)

        assert out == {"shares_owned": 24_000_000.0, "percent_of_class": 6.2}

    def test_extracts_13d_cover_page_fields_despite_different_row_numbers(self):
        import edgar_client

        out = edgar_client.parse_ownership_summary(_SC_13D_COVER_PAGE)

        assert out == {"shares_owned": 3_450_000.0, "percent_of_class": 8.1}

    def test_returns_none_fields_when_labels_are_missing(self):
        import edgar_client

        out = edgar_client.parse_ownership_summary("<html><body><p>Not a 13D/13G at all.</p></body></html>")

        assert out == {"shares_owned": None, "percent_of_class": None}

    def test_skips_small_stray_numbers_between_label_and_real_value(self):
        """A row-number-like digit sitting right after the label (e.g. a
        footnote marker) must not be mistaken for the share count."""
        import edgar_client

        html = (
            "<p>AGGREGATE AMOUNT BENEFICIALLY OWNED BY EACH REPORTING PERSON (5)</p>"
            "<p>2,500,000</p>"
        )

        out = edgar_client.parse_ownership_summary(html)

        assert out["shares_owned"] == 2_500_000.0
