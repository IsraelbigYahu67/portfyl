from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.sql import func

from database import Base
from secrets_crypto import EncryptedValue, get_secret_cipher


def _uuid_primary_key():
    return Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _public_id():
    return Column(
        Uuid(as_uuid=True),
        nullable=False,
        unique=True,
        default=uuid.uuid4,
        index=True,
    )


def _workspace_id(*, nullable: bool = False):
    return Column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=nullable,
        index=True,
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email = lower(trim(email))",
            name="ck_users_email_normalized",
        ),
    )

    id = _uuid_primary_key()
    firebase_uid = Column(String, nullable=True, unique=True, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    disabled_at = Column(DateTime(timezone=True), nullable=True)


class Workspace(Base):
    __tablename__ = "workspaces"

    id = _uuid_primary_key()
    public_id = _public_id()
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at = Column(DateTime(timezone=True), nullable=True)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_membership_user_workspace"),
    )

    id = _uuid_primary_key()
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id = _workspace_id()
    role = Column(String, nullable=False, default="owner", server_default="owner")
    status = Column(String, nullable=False, default="active", server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = _uuid_primary_key()
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_digest = Column(String(64), nullable=False, unique=True, index=True)
    csrf_digest = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    user_agent = Column(String, nullable=True)


class UserSetting(Base):
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_setting_key"),)

    id = _uuid_primary_key()
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key = Column(String, nullable=False, index=True)
    value = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class WorkspaceSetting(Base):
    __tablename__ = "workspace_settings"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key", name="uq_workspace_setting_key"),
    )

    id = _uuid_primary_key()
    workspace_id = _workspace_id()
    key = Column(String, nullable=False, index=True)
    value = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AuditLog(Base):
    """Immutable security event with either workspace or personal scope.

    Workspace events are visible in that workspace.  Events with a null
    ``workspace_id`` (session lifecycle, personal AI credentials) are visible
    only to ``actor_user_id``.  Migration 0009 enforces the same rule with
    forced PostgreSQL RLS.
    """

    __tablename__ = "audit_logs"

    id = _uuid_primary_key()
    public_id = _public_id()
    workspace_id = _workspace_id(nullable=True)
    actor_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=True)
    target_id = Column(String, nullable=True)
    event_metadata = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class JobRun(Base):
    """Last successful completion of each recurring operational job."""

    __tablename__ = "job_runs"

    id = _uuid_primary_key()
    job_name = Column(String, nullable=False, unique=True, index=True)
    last_success_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint("workspace_id", "metric", "period_start", name="uq_usage_counter_period"),
        UniqueConstraint("workspace_id", "id", name="uq_usage_counter_workspace_id"),
        CheckConstraint("used >= 0", name="ck_usage_counter_nonnegative"),
        CheckConstraint("period_end > period_start", name="ck_usage_counter_period_order"),
    )

    id = _uuid_primary_key()
    workspace_id = _workspace_id()
    metric = Column(String, nullable=False, index=True)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    used = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class UsageReservation(Base):
    __tablename__ = "usage_reservations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "metric", "idempotency_key", name="uq_usage_reservation_idempotency"),
        ForeignKeyConstraint(
            ["workspace_id", "counter_id"],
            ["usage_counters.workspace_id", "usage_counters.id"],
            name="fk_usage_reservation_workspace_counter",
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="ck_usage_reservation_positive"),
        CheckConstraint("status IN ('reserved', 'finalized', 'released')", name="ck_usage_reservation_status"),
    )

    id = _uuid_primary_key()
    public_id = _public_id()
    workspace_id = _workspace_id()
    counter_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    metric = Column(String, nullable=False, index=True)
    idempotency_key = Column(String(255), nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="reserved", server_default="reserved")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finalized_at = Column(DateTime(timezone=True), nullable=True)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sending', 'sent', 'failed')", name="ck_notification_outbox_status"),
        CheckConstraint("attempts >= 0", name="ck_notification_outbox_attempts"),
    )

    id = _uuid_primary_key()
    public_id = _public_id()
    workspace_id = _workspace_id()
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    deduplication_key = Column(String, nullable=False, unique=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String, nullable=False, default="pending", server_default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


# Transitional import compatibility until Task 7 replaces key-only settings
# callers with explicit user/workspace-scoped helpers. No app_settings table is
# mapped or created.
AppSetting = WorkspaceSetting


class DataMigrationRun(Base):
    __tablename__ = "data_migration_runs"

    id = _uuid_primary_key()
    source_fingerprint = Column(String(64), nullable=False, unique=True, index=True)
    workspace_id = _workspace_id()
    owner_email = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    table_counts = Column(JSON, nullable=False, default=dict)
    control_totals = Column(JSON, nullable=False, default=dict)
    validation_report = Column(JSON, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_portfolio_workspace_id"),
        UniqueConstraint("workspace_id", "name", name="uq_portfolio_workspace_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    name = Column(String, nullable=False)
    color = Column(String, nullable=True)
    is_default = Column(Boolean, default=False)
    t212_csv_covered_through = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_transaction_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_transaction_workspace_portfolio",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    portfolio_id = Column(Integer, nullable=False, index=True)
    ticker = Column(String, index=True, nullable=True)
    name = Column(String, nullable=True)
    type = Column(String, nullable=False)
    shares = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=True)
    currency = Column(String, default="USD")
    cash_amount = Column(Float, nullable=True)
    cash_currency = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    notes = Column(String, nullable=True)
    source = Column(String, nullable=True)
    fx_to_czk = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_watchlist_workspace_id"),
        UniqueConstraint("workspace_id", "name", name="uq_watchlist_workspace_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    name = Column(String, nullable=False)
    color = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("workspace_id", "watchlist_id", "ticker", name="uq_watchlist_item_ticker"),
        ForeignKeyConstraint(
            ["workspace_id", "watchlist_id"],
            ["watchlists.workspace_id", "watchlists.id"],
            name="fk_watchlist_item_workspace_watchlist",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    watchlist_id = Column(Integer, nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Benchmark(Base):
    __tablename__ = "benchmarks"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_benchmark_workspace_id"),
        UniqueConstraint("workspace_id", "portfolio_id", "name", name="uq_benchmark_workspace_portfolio_name"),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_benchmark_workspace_portfolio",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(is_preset IS TRUE AND workspace_id IS NULL AND portfolio_id IS NULL) "
            "OR (is_preset IS FALSE AND workspace_id IS NOT NULL AND portfolio_id IS NOT NULL)",
            name="ck_benchmark_preset_scope",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id(nullable=True)
    portfolio_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    ticker = Column(String, nullable=True)
    is_default = Column(Boolean, default=False, index=True)
    is_preset = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BenchmarkComponent(Base):
    __tablename__ = "benchmark_components"
    __table_args__ = (
        UniqueConstraint("workspace_id", "benchmark_id", "ticker", name="uq_benchmark_component_ticker"),
        ForeignKeyConstraint(
            ["workspace_id", "benchmark_id"],
            ["benchmarks.workspace_id", "benchmarks.id"],
            name="fk_benchmark_component_workspace_benchmark",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id(nullable=True)
    benchmark_id = Column(Integer, ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String, nullable=False)
    weight = Column(Float, nullable=False)


class BrokerConnection(Base):
    __tablename__ = "broker_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "broker", "portfolio_id", name="uq_broker_workspace_portfolio"),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_broker_connection_workspace_portfolio",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    portfolio_id = Column(Integer, nullable=False, index=True)
    broker = Column(String, nullable=False)
    api_key_ciphertext = Column(LargeBinary, nullable=False)
    api_key_key_version = Column(String, nullable=False)
    api_secret_ciphertext = Column(LargeBinary, nullable=True)
    api_secret_key_version = Column(String, nullable=True)
    environment = Column(String, default="live")
    auto_sync = Column(Boolean, default=False)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    t212_csv_covered_through = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Dead-letter state: jobs.broker_autosync_pass increments consecutive_failures
    # on every failed pass and resets it on the next success. At
    # BROKER_AUTOSYNC_FAILURE_THRESHOLD it flips auto_sync off and
    # needs_attention on rather than retrying forever silently -- re-enabling
    # auto_sync through the normal update endpoints clears both.
    consecutive_failures = Column(Integer, nullable=False, default=0, server_default="0")
    needs_attention = Column(Boolean, nullable=False, default=False, server_default="false")
    last_error = Column(String, nullable=True)

    # `api_key`/`api_secret` are transparent encrypt-on-set/decrypt-on-get
    # properties over the ciphertext columns above -- every existing call
    # site (constructor kwargs, `conn.api_key`, `connection.api_key = ...`)
    # keeps working unchanged. The one thing this can't support is a SQL-
    # level filter like `BrokerConnection.api_key == value`, since ciphertext
    # is never equal across two encryptions of the same plaintext; compare
    # decrypted values in Python instead (see routers/broker.py's clash
    # check).
    @property
    def api_key(self) -> str:
        return get_secret_cipher().decrypt(
            EncryptedValue(self.api_key_ciphertext, self.api_key_key_version)
        )

    @api_key.setter
    def api_key(self, value: str) -> None:
        encrypted = get_secret_cipher().encrypt(value)
        self.api_key_ciphertext = encrypted.ciphertext
        self.api_key_key_version = encrypted.key_version

    @property
    def api_secret(self) -> str | None:
        if not self.api_secret_ciphertext:
            return None
        return get_secret_cipher().decrypt(
            EncryptedValue(self.api_secret_ciphertext, self.api_secret_key_version)
        )

    @api_secret.setter
    def api_secret(self, value: str | None) -> None:
        if not value:
            self.api_secret_ciphertext = None
            self.api_secret_key_version = None
            return
        encrypted = get_secret_cipher().encrypt(value)
        self.api_secret_ciphertext = encrypted.ciphertext
        self.api_secret_key_version = encrypted.key_version


class OptionsTrade(Base):
    __tablename__ = "options_trades"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "portfolio_id", "underlying", "strike", "expiry", "put_call",
            "open_date", "quantity", "open_price", name="uq_options_dedup",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_options_trade_workspace_portfolio",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    portfolio_id = Column(Integer, nullable=False, index=True)
    underlying = Column(String, nullable=False, index=True)
    strike = Column(Float, nullable=False)
    expiry = Column(Date, nullable=False)
    put_call = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    open_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=True)
    open_date = Column(Date, nullable=False)
    close_date = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="closed")
    multiplier = Column(Integer, default=100)
    currency = Column(String, default="USD")
    pnl = Column(Float, nullable=True)
    commission = Column(Float, nullable=True, default=0.0)
    source = Column(String, nullable=True)
    fx_to_czk = Column(Float, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BrokerBalance(Base):
    __tablename__ = "broker_balances"
    __table_args__ = (
        UniqueConstraint("workspace_id", "broker", "portfolio_id", name="uq_balance_workspace_portfolio"),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_broker_balance_workspace_portfolio",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    portfolio_id = Column(Integer, nullable=False, index=True)
    broker = Column(String, nullable=False)
    base_currency = Column(String, nullable=True)
    cash = Column(Float, nullable=True)
    stock = Column(Float, nullable=True)
    options_value = Column(Float, nullable=True)
    net_liquidation = Column(Float, nullable=True)
    cash_by_currency = Column(String, nullable=True)
    as_of = Column(Date, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PolymarketPosition(Base):
    __tablename__ = "polymarket_positions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "portfolio_id", "condition_id", "outcome", "asset_id",
            name="uq_poly_position",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_polymarket_position_workspace_portfolio",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    portfolio_id = Column(Integer, nullable=False, index=True)
    condition_id = Column(String, nullable=False, index=True)
    asset_id = Column(String, nullable=False)
    market_slug = Column(String, nullable=True)
    question = Column(String, nullable=False)
    outcome = Column(String, nullable=False)
    size = Column(Float, nullable=False)
    avg_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    resolved_price = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="open")
    pnl = Column(Float, nullable=True)
    source = Column(String, default="polymarket")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DiscordWebhook(Base):
    __tablename__ = "discord_webhooks"
    __table_args__ = (
        UniqueConstraint("workspace_id", "portfolio_id", name="uq_discord_workspace_portfolio"),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_discord_webhook_workspace_portfolio",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    portfolio_id = Column(Integer, nullable=False, index=True)
    webhook_url_ciphertext = Column(LargeBinary, nullable=False)
    webhook_url_key_version = Column(String, nullable=False)
    notify_trades = Column(Boolean, default=True)
    notify_dividends = Column(Boolean, default=True)
    notify_milestones = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Transparent encrypt-on-set/decrypt-on-get, same rationale as
    # BrokerConnection.api_key/api_secret above.
    @property
    def webhook_url(self) -> str:
        return get_secret_cipher().decrypt(
            EncryptedValue(self.webhook_url_ciphertext, self.webhook_url_key_version)
        )

    @webhook_url.setter
    def webhook_url(self, value: str) -> None:
        encrypted = get_secret_cipher().encrypt(value)
        self.webhook_url_ciphertext = encrypted.ciphertext
        self.webhook_url_key_version = encrypted.key_version


class TradeNote(Base):
    __tablename__ = "trade_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            name="fk_trade_note_workspace_transaction",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    transaction_id = Column(Integer, nullable=False, unique=True, index=True)
    content = Column(String, nullable=False, default="")
    tags = Column(String, nullable=True)
    sentiment = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CashInterestRate(Base):
    __tablename__ = "cash_interest_rates"
    __table_args__ = (
        UniqueConstraint("workspace_id", "portfolio_id", "currency", name="uq_cash_rate_workspace_currency"),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_cash_interest_rate_workspace_portfolio",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    portfolio_id = Column(Integer, nullable=False, index=True)
    currency = Column(String, nullable=False)
    annual_rate = Column(Float, nullable=False, default=0.0)
    enabled = Column(Boolean, nullable=False, default=False)
    start_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DividendNotification(Base):
    __tablename__ = "dividend_notifications"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "portfolio_id", "ticker", "ex_date",
            name="uq_dividend_notification_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_dividend_notification_workspace_portfolio",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    portfolio_id = Column(Integer, nullable=False, index=True)
    ticker = Column(String, nullable=False)
    ex_date = Column(Date, nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())


class PriceAlert(Base):
    __tablename__ = "price_alerts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_price_alert_workspace_portfolio",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = _public_id()
    workspace_id = _workspace_id()
    portfolio_id = Column(Integer, nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    direction = Column(String, nullable=False)
    target_price = Column(Float, nullable=False)
    note = Column(String, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    status = Column(String, nullable=False, default="active", server_default="active")
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    triggered_price = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
