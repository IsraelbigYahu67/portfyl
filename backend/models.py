from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    # Scopes this row to one account. Single-user today (always "default"); lets us
    # add per-user isolation later without a schema rewrite. Identity is resolved by
    # auth.get_current_user(). Every per-user table carries an identical owner_id.
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)
    name = Column(String, nullable=False, unique=True)
    color = Column(String, nullable=True)  # tailwind/hex; optional UI hint
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String, index=True, nullable=True)   # was nullable=False; NULL for cash rows
    name = Column(String, nullable=True)
    type = Column(String, nullable=False)  # buy | sell | dividend
    shares = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=True)   # cash amount (native ccy) for cash rows (deposit/withdrawal/...); NULL for trades
    currency = Column(String, default="USD")
    # Settlement: the actual cash a trade/dividend moved, in the account currency
    # (T212 CSV `Total`, FX fees included). Positive magnitude; direction comes from
    # `type`. NULL on cash rows (`amount` is authoritative there) and on legacy trades
    # (signed_cash falls back to shares*price in the trade currency).
    cash_amount = Column(Float, nullable=True)
    cash_currency = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    notes = Column(String, nullable=True)
    source = Column(String, nullable=True)  # "manual" | "t212_api" | "csv"
    fx_to_czk = Column(Float, nullable=True)  # rate from `currency` to CZK on `date`
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    name = Column(String, nullable=False, unique=True)
    color = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "ticker", name="uq_watchlist_ticker"),)

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    watchlist_id = Column(Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Benchmark(Base):
    __tablename__ = "benchmarks"
    __table_args__ = (UniqueConstraint("portfolio_id", "name", name="uq_bench_pf_name"),)

    id = Column(Integer, primary_key=True, index=True)
    # NULL = system preset, visible to every portfolio. A row scoped to a portfolio
    # is private to that portfolio.
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)              # "ticker" | "basket"
    ticker = Column(String, nullable=True)             # yahoo symbol when kind == "ticker"
    is_default = Column(Boolean, default=False, index=True)
    is_preset = Column(Boolean, default=False)         # presets cannot be edited/deleted
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BenchmarkComponent(Base):
    __tablename__ = "benchmark_components"
    __table_args__ = (UniqueConstraint("benchmark_id", "ticker", name="uq_bench_ticker"),)

    id = Column(Integer, primary_key=True, index=True)
    benchmark_id = Column(Integer, ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String, nullable=False)
    weight = Column(Float, nullable=False)


class BrokerConnection(Base):
    __tablename__ = "broker_connections"
    __table_args__ = (UniqueConstraint("broker", "portfolio_id", name="uq_broker_portfolio"),)

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    broker = Column(String, nullable=False)  # "trading212"
    api_key = Column(String, nullable=False)
    api_secret = Column(String, nullable=True, default="")
    environment = Column(String, default="live")  # "live" | "demo"
    auto_sync = Column(Boolean, default=False)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OptionsTrade(Base):
    __tablename__ = "options_trades"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "underlying", "strike", "expiry", "put_call",
            "open_date", "quantity", "open_price",
            name="uq_options_dedup"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    underlying = Column(String, nullable=False, index=True)
    strike = Column(Float, nullable=False)
    expiry = Column(Date, nullable=False)
    put_call = Column(String, nullable=False)  # "P" or "C"
    quantity = Column(Integer, nullable=False)
    open_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=True)
    open_date = Column(Date, nullable=False)
    close_date = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="closed")  # closed | expired | assigned
    multiplier = Column(Integer, default=100)
    currency = Column(String, default="USD")
    pnl = Column(Float, nullable=True)
    commission = Column(Float, nullable=True, default=0.0)
    source = Column(String, nullable=True)  # "ibkr"
    fx_to_czk = Column(Float, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BrokerBalance(Base):
    """Latest account balance snapshot pulled from a broker (e.g. IBKR Flex).

    One row per (portfolio, broker). Refreshed on each sync from the same Flex
    statement that supplies trades, so it costs no extra broker requests. All
    monetary fields are in the account's base currency; `cash_by_currency` holds
    the per-currency cash breakdown as a JSON object string.
    """

    __tablename__ = "broker_balances"
    __table_args__ = (UniqueConstraint("broker", "portfolio_id", name="uq_balance_broker_portfolio"),)

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    broker = Column(String, nullable=False)  # "ibkr"
    base_currency = Column(String, nullable=True)        # account base currency, e.g. "USD"
    cash = Column(Float, nullable=True)                  # total cash in base currency
    stock = Column(Float, nullable=True)                 # stock market value in base
    options_value = Column(Float, nullable=True)         # options market value in base
    net_liquidation = Column(Float, nullable=True)       # total NAV in base
    cash_by_currency = Column(String, nullable=True)     # JSON: {"USD": 1234.5, "EUR": 67.8}
    as_of = Column(Date, nullable=True)                  # report date from the Flex statement
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PolymarketPosition(Base):
    __tablename__ = "polymarket_positions"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "condition_id", "outcome", "asset_id",
            name="uq_poly_position"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    condition_id = Column(String, nullable=False, index=True)
    asset_id = Column(String, nullable=False)
    market_slug = Column(String, nullable=True)
    question = Column(String, nullable=False)
    outcome = Column(String, nullable=False)  # "Yes" or "No"
    size = Column(Float, nullable=False)  # number of shares
    avg_price = Column(Float, nullable=False)  # average entry price (0-1)
    current_price = Column(Float, nullable=True)  # latest market price (0-1), null if resolved
    resolved_price = Column(Float, nullable=True)  # 1.0 or 0.0 if resolved
    status = Column(String, nullable=False, default="open")  # "open" | "resolved" | "closed"
    pnl = Column(Float, nullable=True)  # realized P&L in USD
    source = Column(String, default="polymarket")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DiscordWebhook(Base):
    __tablename__ = "discord_webhooks"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    webhook_url = Column(String, nullable=False)
    notify_trades = Column(Boolean, default=True)
    notify_dividends = Column(Boolean, default=True)
    notify_milestones = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AppSetting(Base):
    """Simple app-wide key/value store for global config & secrets.

    Used for settings that aren't portfolio-scoped — e.g. the DeepSeek API key
    and model that power the AI assistant. Plaintext, consistent with how broker
    keys are stored in this local app.
    """

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    key = Column(String, nullable=False, unique=True, index=True)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TradeNote(Base):
    __tablename__ = "trade_notes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    content = Column(String, nullable=False, default="")
    tags = Column(String, nullable=True)
    sentiment = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CashInterestRate(Base):
    __tablename__ = "cash_interest_rates"
    __table_args__ = (UniqueConstraint("portfolio_id", "currency", name="uq_cash_rate_pid_ccy"),)

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    currency = Column(String, nullable=False)          # "USD" | "GBP" | "EUR" | "CZK" ...
    annual_rate = Column(Float, nullable=False, default=0.0)  # decimal, e.g. 0.045 = 4.5% APY
    enabled = Column(Boolean, nullable=False, default=False)
    start_date = Column(Date, nullable=True)           # accrual start; NULL => first cash event
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DividendNotification(Base):
    """Dedup ledger for dividend ex-date Discord notifications: one row per
    (portfolio, ticker, ex_date) that has already been announced, so repeated
    job ticks and app restarts never re-send the same upcoming dividend."""
    __tablename__ = "dividend_notifications"
    __table_args__ = (UniqueConstraint("portfolio_id", "ticker", "ex_date", name="uq_divnotif_pid_ticker_ex"),)

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String, nullable=False)
    ex_date = Column(Date, nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())


class PriceAlert(Base):
    """A user-armed price threshold for a ticker. When the live price crosses it,
    the alert fires a Discord notification (via the portfolio's webhook) and flips
    to `triggered` so it won't re-fire until the user resets it. Portfolio-scoped
    so it can reach that portfolio's DiscordWebhook."""
    __tablename__ = "price_alerts"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, default="default", server_default="default", index=True)  # see Portfolio.owner_id
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    direction = Column(String, nullable=False)         # "above" | "below"
    target_price = Column(Float, nullable=False)
    note = Column(String, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)   # user arm/disarm switch
    status = Column(String, nullable=False, default="active", server_default="active")  # "active" | "triggered"
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    triggered_price = Column(Float, nullable=True)     # the price observed when it fired
    created_at = Column(DateTime(timezone=True), server_default=func.now())
