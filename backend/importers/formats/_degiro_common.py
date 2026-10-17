"""Shared Degiro CSV helpers. Degiro localizes headers and descriptions, so
columns are addressed by position and descriptions by keyword tables.

The keyword tables come from public examples, not yet from real exports in
every UI language: extend them only from a real sample (plan Task 0)."""
from __future__ import annotations

import csv
from datetime import date, datetime
import io
import re

from importers.base import ImportFile

ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
DATE = re.compile(r"^\d{2}-\d{2}-\d{4}$")

# Degiro "Reference exchange" -> canonical venue (importers.instruments).
DEGIRO_VENUES = {
    "NDQ": "US", "NSY": "US", "ASE": "US",
    "XET": "XETRA", "FRA": "FRANKFURT", "LSE": "LSE", "EAM": "AMSTERDAM",
    "EPA": "PARIS", "MIL": "MILAN", "SWX": "SIX", "PRA": "PRAGUE", "TOR": "TORONTO",
    "EBR": "BRUSSELS", "MAD": "MADRID", "WSE": "WARSAW", "HKS": "HONGKONG",
}
# Evaluated in this order: "dividend tax" contains "dividend", and currency
# conversions must win over the generic "fee".
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


def read_degiro_csv(file: ImportFile, *, head_only: bool = False) -> list[list[str]]:
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
