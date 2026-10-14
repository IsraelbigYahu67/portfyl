from pydantic import BaseModel, Field, field_validator
from datetime import date
from typing import Literal, Optional
from uuid import UUID


class TransactionCreate(BaseModel):
    # Input model for POST /portfolio/transactions. Only this model is strict:
    # the ledger is the source of truth and one NaN breaks every calculation
    # over the portfolio. TransactionResponse is deliberately a separate model
    # so stored legacy rows (e.g. a dividend with price 0) can still be read.
    ticker: str = Field(min_length=1, max_length=32)
    type: Literal["buy", "sell", "dividend"]
    shares: float = Field(gt=0, allow_inf_nan=False)
    price: float = Field(gt=0, allow_inf_nan=False)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    date: date
    notes: Optional[str] = None

    @field_validator("ticker", mode="before")
    @classmethod
    def _strip_ticker(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class TransactionResponse(BaseModel):
    # Field order matches the former TransactionCreate-derived shape, so the
    # JSON the API returns is unchanged.
    # Cash rows (deposit/withdrawal/fee/interest) have no ticker — the model column
    # is nullable. Trade creation still requires a ticker via TransactionCreate;
    # only the response schema is relaxed so GET /transactions (which returns ALL
    # rows for the portfolio, cash included) doesn't 500 serializing a null ticker.
    ticker: Optional[str] = None
    type: str
    shares: float
    price: float
    currency: str = "USD"
    date: date
    notes: Optional[str] = None
    # Public API identifier: the model's internal integer PK is never
    # serialized -- this reads the ORM's `public_id` column (see models.py).
    id: UUID = Field(validation_alias="public_id")
    name: Optional[str] = None
    fx_to_czk: Optional[float] = None

    model_config = {"from_attributes": True, "populate_by_name": True}
