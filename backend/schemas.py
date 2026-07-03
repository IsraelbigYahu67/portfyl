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
    name: Optional[str] = None
    fx_to_czk: Optional[float] = None

    model_config = {"from_attributes": True}
