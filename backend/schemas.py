from pydantic import BaseModel
from datetime import date
from typing import Optional


class TransactionCreate(BaseModel):
    ticker: str
    type: str
    shares: float
    price: float
    currency: str = "USD"
    date: date
    notes: Optional[str] = None


class TransactionResponse(TransactionCreate):
    id: int
    # Cash rows (deposit/withdrawal/fee/interest) have no ticker — the model column
    # is nullable. Trade creation still requires a ticker via TransactionCreate;
    # only the response schema is relaxed so GET /transactions (which returns ALL
    # rows for the portfolio, cash included) doesn't 500 serializing a null ticker.
    ticker: Optional[str] = None
    name: Optional[str] = None
    fx_to_czk: Optional[float] = None

    model_config = {"from_attributes": True}
