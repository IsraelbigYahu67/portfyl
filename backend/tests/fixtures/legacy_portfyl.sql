PRAGMA foreign_keys = ON;

CREATE TABLE portfolios (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    is_default INTEGER DEFAULT 0,
    t212_csv_covered_through TEXT,
    created_at TEXT
);

CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ticker TEXT,
    name TEXT,
    type TEXT NOT NULL,
    shares REAL NOT NULL,
    price REAL NOT NULL,
    amount REAL,
    currency TEXT,
    cash_amount REAL,
    cash_currency TEXT,
    date TEXT NOT NULL,
    notes TEXT,
    source TEXT,
    fx_to_czk REAL,
    created_at TEXT
);

CREATE TABLE watchlists (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    created_at TEXT
);

CREATE TABLE watchlist_items (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    note TEXT,
    created_at TEXT,
    UNIQUE (watchlist_id, ticker)
);

CREATE TABLE benchmarks (
    id INTEGER PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    ticker TEXT,
    is_default INTEGER DEFAULT 0,
    is_preset INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE benchmark_components (
    id INTEGER PRIMARY KEY,
    benchmark_id INTEGER NOT NULL REFERENCES benchmarks(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    weight REAL NOT NULL,
    UNIQUE (benchmark_id, ticker)
);

CREATE TABLE broker_connections (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    broker TEXT NOT NULL,
    api_key TEXT NOT NULL,
    api_secret TEXT,
    environment TEXT,
    auto_sync INTEGER,
    last_synced_at TEXT,
    t212_csv_covered_through TEXT,
    created_at TEXT
);

CREATE TABLE broker_balances (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    broker TEXT NOT NULL,
    base_currency TEXT,
    cash REAL,
    stock REAL,
    options_value REAL,
    net_liquidation REAL,
    cash_by_currency TEXT,
    as_of TEXT,
    updated_at TEXT
);

CREATE TABLE options_trades (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    underlying TEXT NOT NULL,
    strike REAL NOT NULL,
    expiry TEXT NOT NULL,
    put_call TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    open_price REAL NOT NULL,
    close_price REAL,
    open_date TEXT NOT NULL,
    close_date TEXT,
    status TEXT NOT NULL,
    multiplier INTEGER,
    currency TEXT,
    pnl REAL,
    commission REAL,
    source TEXT,
    fx_to_czk REAL,
    notes TEXT,
    created_at TEXT
);

CREATE TABLE polymarket_positions (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    condition_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    market_slug TEXT,
    question TEXT NOT NULL,
    outcome TEXT NOT NULL,
    size REAL NOT NULL,
    avg_price REAL NOT NULL,
    current_price REAL,
    resolved_price REAL,
    status TEXT NOT NULL,
    pnl REAL,
    source TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE discord_webhooks (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    portfolio_id INTEGER NOT NULL UNIQUE REFERENCES portfolios(id) ON DELETE CASCADE,
    webhook_url TEXT NOT NULL,
    notify_trades INTEGER,
    notify_dividends INTEGER,
    notify_milestones INTEGER,
    created_at TEXT
);

CREATE TABLE app_settings (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    key TEXT NOT NULL UNIQUE,
    value TEXT,
    updated_at TEXT
);

CREATE TABLE trade_notes (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    transaction_id INTEGER NOT NULL UNIQUE REFERENCES transactions(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    tags TEXT,
    sentiment TEXT,
    updated_at TEXT
);

CREATE TABLE cash_interest_rates (
    id INTEGER PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    currency TEXT NOT NULL,
    annual_rate REAL NOT NULL,
    enabled INTEGER NOT NULL,
    start_date TEXT,
    created_at TEXT
);

CREATE TABLE dividend_notifications (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    sent_at TEXT
);

CREATE TABLE price_alerts (
    id INTEGER PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'default',
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL,
    target_price REAL NOT NULL,
    note TEXT,
    enabled INTEGER NOT NULL,
    status TEXT NOT NULL,
    last_triggered_at TEXT,
    triggered_price REAL,
    created_at TEXT
);

INSERT INTO portfolios VALUES
    (1, 'default', 'Main', '#2563eb', 1, '2026-08-31T20:00:00+00:00', '2025-01-01T09:00:00+00:00'),
    (2, 'default', 'Retirement', '#16a34a', 0, NULL, '2025-02-01T09:00:00+00:00');

INSERT INTO transactions VALUES
    (1, 1, 'AAPL', 'Apple', 'buy', 10, 150, NULL, 'USD', NULL, NULL, '2025-01-02', 'opening trade', 'manual', 23.10, '2025-01-02T10:00:00+00:00'),
    (2, 1, NULL, 'Cash deposit', 'deposit', 0, 0, 1000, 'USD', NULL, NULL, '2025-01-03', NULL, 't212_csv', 23.15, '2025-01-03T10:00:00+00:00'),
    (3, 2, 'MSFT', 'Microsoft', 'buy', 5, 400, NULL, 'USD', 2001.25, 'USD', '2025-02-03', NULL, 'ibkr', 23.50, '2025-02-03T10:00:00+00:00'),
    (4, 2, 'AAPL', 'Apple', 'dividend', 10, 0.24, NULL, 'USD', 2.40, 'USD', '2025-03-01', NULL, 't212_api', 23.40, '2025-03-01T10:00:00+00:00');

INSERT INTO watchlists VALUES (10, 'default', 'Ideas', '#f59e0b', '2025-01-05T12:00:00+00:00');
INSERT INTO watchlist_items VALUES (20, 'default', 10, 'NVDA', 'Wait for pullback', '2025-01-05T12:05:00+00:00');
INSERT INTO benchmarks VALUES (30, 1, 'Growth Basket', 'basket', NULL, 1, 0, '2025-01-06T10:00:00+00:00');
INSERT INTO benchmark_components VALUES (40, 30, 'QQQ', 1.0);

INSERT INTO broker_connections VALUES
    (50, 'default', 1, 'trading212', 'fixture-api-key', 'fixture-secret', 'demo', 1, '2026-08-31T21:00:00+00:00', '2026-08-31T20:00:00+00:00', '2025-01-07T10:00:00+00:00');
INSERT INTO broker_balances VALUES
    (60, 'default', 2, 'ibkr', 'USD', 500, 2000, 120, 2620, '{"USD":500}', '2026-08-31', '2026-08-31T21:00:00+00:00');

INSERT INTO options_trades VALUES
    (70, 'default', 2, 'MSFT', 420, '2026-12-18', 'C', 1, 8.5, 12.25, '2026-01-10', '2026-02-10', 'closed', 100, 'USD', 375, 2.5, 'ibkr', 23.4, 'fixture option', '2026-01-10T10:00:00+00:00');
INSERT INTO polymarket_positions VALUES
    (80, 'default', 1, 'condition-1', 'asset-yes', 'sample-market', 'Will the fixture pass?', 'Yes', 100, 0.42, 0.61, NULL, 'open', NULL, 'polymarket', '2026-01-11T10:00:00+00:00', '2026-08-31T10:00:00+00:00');
INSERT INTO discord_webhooks VALUES
    (90, 'default', 1, 'https://discord.invalid/api/webhooks/fixture', 1, 1, 0, '2025-01-08T10:00:00+00:00');

INSERT INTO app_settings (id, key, value, updated_at) VALUES
    (1, 'deepseek_api_key', 'fixture-deepseek-key', '2026-08-01T10:00:00+00:00'),
    (2, 'deepseek_model', 'deepseek-chat', '2026-08-01T10:00:00+00:00'),
    (3, 'broker_sync_mode', 'daily', '2026-08-01T10:00:00+00:00'),
    (4, 'broker_sync_daily_time', '04:30', '2026-08-01T10:00:00+00:00'),
    (5, 'broker_sync_interval_hours', '12', '2026-08-01T10:00:00+00:00'),
    (6, 'broker_sync_last_run', '2026-08-31T04:30:00+00:00', '2026-08-31T04:30:00+00:00');

INSERT INTO trade_notes VALUES (100, 'default', 1, 'Thesis remains intact.', 'quality,long-term', 'bullish', '2026-08-15T10:00:00+00:00');
INSERT INTO cash_interest_rates VALUES (110, 1, 'USD', 0.045, 1, '2025-01-03', '2025-01-03T10:00:00+00:00');
INSERT INTO dividend_notifications VALUES (120, 'default', 2, 'AAPL', '2025-03-01', '2025-02-20T10:00:00+00:00');
INSERT INTO price_alerts VALUES (130, 'default', 1, 'NVDA', 'below', 100, 'Starter price', 1, 'active', NULL, NULL, '2026-08-20T10:00:00+00:00');
