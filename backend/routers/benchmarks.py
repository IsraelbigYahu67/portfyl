"""Benchmark management + portfolio-vs-benchmark comparison.

Benchmarks are either a single Yahoo symbol ("ticker") or a weighted basket of
symbols ("basket"). System presets (portfolio_id NULL, is_preset True) are
shared across portfolios and cannot be edited or deleted. User benchmarks are
scoped to a single portfolio.

The comparison endpoint reuses the Modified-Dietz TWR machinery from
routers.analytics so both endpoints agree on the portfolio return series.
"""

from datetime import date
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from database import get_db
from models import Benchmark, BenchmarkComponent, Transaction
from routers.portfolios import require_portfolio
from routers.analytics import (
    _benchmark_compare_metrics,
    _benchmark_daily_returns,
    _build_value_cashflow_series,
    _modified_dietz_daily_returns,
    _resolve_window,
    resolve_benchmark,
)


router = APIRouter(prefix="/analytics/benchmarks", tags=["benchmarks"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ComponentIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    weight: float = Field(gt=0)


class BenchmarkCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    kind: str = Field(pattern="^(ticker|basket)$")
    ticker: Optional[str] = Field(default=None, max_length=32)
    components: Optional[list[ComponentIn]] = None
    is_default: bool = False

    @model_validator(mode="after")
    def _check_shape(self):
        if self.kind == "ticker":
            if not (self.ticker and self.ticker.strip()):
                raise ValueError("ticker is required when kind='ticker'")
            if self.components:
                raise ValueError("components must be empty when kind='ticker'")
        else:
            if not self.components:
                raise ValueError("components required when kind='basket'")
            total = sum(c.weight for c in self.components)
            if abs(total - 1.0) > 1e-4:
                raise ValueError(f"component weights must sum to 1.0 (got {total:.4f})")
            tickers = {c.ticker.strip().upper() for c in self.components}
            if len(tickers) != len(self.components):
                raise ValueError("component tickers must be unique")
        return self


class BenchmarkPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    ticker: Optional[str] = Field(default=None, max_length=32)
    components: Optional[list[ComponentIn]] = None
    is_default: Optional[bool] = None


def _serialize(b: Benchmark, components: list[BenchmarkComponent] | None = None) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "kind": b.kind,
        "ticker": b.ticker,
        "is_default": bool(b.is_default),
        "is_preset": bool(b.is_preset),
        "portfolio_id": b.portfolio_id,
        "components": [
            {"ticker": c.ticker, "weight": c.weight}
            for c in (components or [])
        ],
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


def _load_components(db: Session, benchmark_id: int) -> list[BenchmarkComponent]:
    return (
        db.query(BenchmarkComponent)
        .filter(BenchmarkComponent.benchmark_id == benchmark_id)
        .all()
    )


def _clear_other_defaults(db: Session, pid: int) -> None:
    db.query(Benchmark).filter(
        Benchmark.portfolio_id == pid,
        Benchmark.is_default.is_(True),
    ).update({Benchmark.is_default: False}, synchronize_session=False)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("")
def list_benchmarks(
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    """Presets + this portfolio's own benchmarks."""
    rows = (
        db.query(Benchmark)
        .filter((Benchmark.portfolio_id.is_(None)) | (Benchmark.portfolio_id == pid))
        .order_by(Benchmark.is_preset.desc(), Benchmark.created_at.asc())
        .all()
    )
    ids = [r.id for r in rows]
    comps_by_bench: dict[int, list[BenchmarkComponent]] = {i: [] for i in ids}
    if ids:
        for c in db.query(BenchmarkComponent).filter(BenchmarkComponent.benchmark_id.in_(ids)).all():
            comps_by_bench.setdefault(c.benchmark_id, []).append(c)
    return [_serialize(r, comps_by_bench.get(r.id, [])) for r in rows]


@router.post("")
def create_benchmark(
    payload: BenchmarkCreate,
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    if payload.is_default:
        _clear_other_defaults(db, pid)

    b = Benchmark(
        portfolio_id=pid,
        name=payload.name.strip(),
        kind=payload.kind,
        ticker=payload.ticker.strip().upper() if payload.ticker else None,
        is_default=payload.is_default,
        is_preset=False,
    )
    db.add(b)
    db.flush()  # need b.id before inserting components

    if payload.kind == "basket":
        for c in payload.components or []:
            db.add(BenchmarkComponent(
                benchmark_id=b.id,
                ticker=c.ticker.strip().upper(),
                weight=c.weight,
            ))
    db.commit()
    db.refresh(b)
    return _serialize(b, _load_components(db, b.id))


@router.patch("/{benchmark_id}")
def update_benchmark(
    benchmark_id: int,
    payload: BenchmarkPatch,
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    b = db.query(Benchmark).filter(Benchmark.id == benchmark_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    if b.is_preset:
        # Preset can only be marked as the portfolio's default; renaming or editing
        # the underlying composition would mutate shared global state.
        if any(v is not None for v in (payload.name, payload.ticker, payload.components)):
            raise HTTPException(status_code=403, detail="System presets cannot be edited")
        if payload.is_default:
            _clear_other_defaults(db, pid)
            # Default is stored on the row itself, but presets are shared — so we
            # represent "preset X is this portfolio's default" by copying the
            # preset into a portfolio-scoped row with is_default=true.
            copy = Benchmark(
                portfolio_id=pid,
                name=b.name,
                kind=b.kind,
                ticker=b.ticker,
                is_default=True,
                is_preset=False,
            )
            db.add(copy)
            db.flush()
            for c in _load_components(db, b.id):
                db.add(BenchmarkComponent(benchmark_id=copy.id, ticker=c.ticker, weight=c.weight))
            db.commit()
            db.refresh(copy)
            return _serialize(copy, _load_components(db, copy.id))
        return _serialize(b, _load_components(db, b.id))

    if b.portfolio_id != pid:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    if payload.name is not None:
        b.name = payload.name.strip()
    if payload.ticker is not None and b.kind == "ticker":
        b.ticker = payload.ticker.strip().upper() or None
    if payload.components is not None and b.kind == "basket":
        total = sum(c.weight for c in payload.components)
        if abs(total - 1.0) > 1e-4:
            raise HTTPException(status_code=400, detail=f"component weights must sum to 1.0 (got {total:.4f})")
        db.query(BenchmarkComponent).filter(BenchmarkComponent.benchmark_id == b.id).delete(synchronize_session=False)
        for c in payload.components:
            db.add(BenchmarkComponent(benchmark_id=b.id, ticker=c.ticker.strip().upper(), weight=c.weight))
    if payload.is_default is True:
        _clear_other_defaults(db, pid)
        b.is_default = True
    elif payload.is_default is False:
        b.is_default = False

    db.commit()
    db.refresh(b)
    return _serialize(b, _load_components(db, b.id))


@router.delete("/{benchmark_id}")
def delete_benchmark(
    benchmark_id: int,
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    b = db.query(Benchmark).filter(Benchmark.id == benchmark_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    if b.is_preset:
        raise HTTPException(status_code=403, detail="System presets cannot be deleted")
    if b.portfolio_id != pid:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    db.query(BenchmarkComponent).filter(BenchmarkComponent.benchmark_id == b.id).delete(synchronize_session=False)
    db.delete(b)
    db.commit()
    return {"ok": True, "deleted_id": benchmark_id}


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

@router.get("/comparison")
def benchmark_comparison(
    period: str = "1y",
    benchmark_id: Optional[int] = None,
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    """Time series of cumulative TWR for portfolio vs chosen benchmark plus the
    daily active-return curve, with the same comparison metrics surfaced on
    /risk-metrics for the same window."""
    transactions = (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == pid)
        .order_by(Transaction.date)
        .all()
    )
    if not transactions:
        return {"series": [], "metrics": {}, "benchmark": None}

    window = _resolve_window(transactions, period)
    if window is None:
        return {"series": [], "metrics": {}, "benchmark": None}
    start_date, window_start = window

    V, C, closes_index = _build_value_cashflow_series(transactions, start_date)
    if V is None:
        return {"series": [], "metrics": {}, "benchmark": None}

    port_daily = _modified_dietz_daily_returns(V, C, window_start)
    if len(port_daily) < 2:
        return {"series": [], "metrics": {}, "benchmark": None}

    bench = resolve_benchmark(db, pid, benchmark_id)
    bench_daily = _benchmark_daily_returns(db, bench, start_date, closes_index)

    aligned = pd.DataFrame({"p": port_daily, "b": bench_daily}).dropna()
    if aligned.empty:
        return {
            "series": [],
            "metrics": {},
            "benchmark": {"id": bench.id, "name": bench.name, "kind": bench.kind} if bench else None,
            "period": period,
        }

    port_cum = (1 + aligned["p"]).cumprod() - 1
    bench_cum = (1 + aligned["b"]).cumprod() - 1
    active_cum = port_cum - bench_cum

    series = [
        {
            "date": str(idx.date()),
            "portfolio_pct": round(float(port_cum.loc[idx]) * 100, 2),
            "benchmark_pct": round(float(bench_cum.loc[idx]) * 100, 2),
            "active_pct": round(float(active_cum.loc[idx]) * 100, 2),
        }
        for idx in aligned.index
    ]

    metrics = _benchmark_compare_metrics(aligned["p"], aligned["b"])
    metrics["portfolio_return"] = round(float(port_cum.iloc[-1]) * 100, 2)
    metrics["benchmark_return"] = round(float(bench_cum.iloc[-1]) * 100, 2)
    metrics["active_return"] = round(metrics["portfolio_return"] - metrics["benchmark_return"], 2)

    return {
        "period": period,
        "benchmark": {"id": bench.id, "name": bench.name, "kind": bench.kind} if bench else None,
        "series": series,
        "metrics": metrics,
    }
