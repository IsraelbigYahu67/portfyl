---
type: hub
layer: backend
tags: [arch/hub]
generated: false
---
# Alerts and integrations

This area is about Portfyl reaching out to the user, and a few optional add-ons around the portfolio. The user can set price alerts, plug in a Discord webhook to be told about trades, dividends and alerts, write notes on individual trades, and choose how often their brokers auto-sync. The Polymarket and Options routers are further add-ons, gated to the Pro plan in the cloud edition.

Most of the work happens in background jobs that Cloud Scheduler triggers. Every job loops over workspaces one by one, so one customer's data is never touched while handling another (see [[Jobs and Cloud Scheduler]]).

## How it works
- **Price alerts**: [[routers.alerts]] lets a user arm a threshold ("above" or "below" a target price) for a ticker. `run_check` fetches live prices ([[market_data]]) and, when a price crosses its threshold, flips the alert to `triggered` and sends a Discord message. A triggered alert does not fire again until it is reset, so a price that stays past the line does not spam the channel. If the Discord send fails, the flag is not saved, so the next pass retries.
- **Who runs the check**: `POST /api/alerts/check` runs it for one portfolio on demand. The scheduled `alerts` job (`POST /api/internal/jobs/alerts`, see [[routers.internal_jobs]]) calls `alert_check_all_workspaces` in [[jobs]]. Alert counts are limited per plan, and sending to Discord needs the `notification_integrations` capability ([[entitlements]], [[plans]]).
- **Discord webhooks**: [[routers.discord]] stores one webhook per portfolio with three switches (`notify_trades`, `notify_dividends`, `notify_milestones`) plus a test-message endpoint. The webhook URL is a secret, so it is stored encrypted ([[secrets_crypto]]) and never returned or logged. [[discord_webhooks]] accepts only real Discord webhook addresses and re-checks the URL before every send, to stop server-side request forgery. `send_discord_notification` returns True, False (failed) or None (no webhook).
- **What is announced**: after an auto-sync imports new trades, the autosync pass posts them if `notify_trades` is on. The dividends job (`dividend_exdate_pass`) sends one digest of upcoming ex-dividend dates, and a [[dividend_notifications (table)]] row per portfolio, ticker and date guarantees each is announced once.
- **Auto-sync schedule**: [[routers.settings]] reads and writes the workspace's schedule (`GET` and `PUT /api/settings/sync-schedule`): a daily time or an interval of 1 to 168 hours, evaluated in the `BROKER_SYNC_TIMEZONE` zone (default Europe/Prague). The values are workspace settings ([[app_settings]]) read by the autosync job. The same router also serves the workspace audit log. The schedule UI is [[components.SyncScheduleSettings]]; the minimum interval depends on the plan.
- **Trade notes**: [[routers.notes]] gets, saves and deletes one note per transaction (text, tags, sentiment) and lists all notes. The UI is [[components.TradeNoteModal]] on [[pages.Transactions]]. An import in replace mode removes notes, and the import preview reports how many.
- **Polymarket**: [[routers.polymarket]] connects a public wallet address, syncs positions into [[polymarket_positions (table)]] and shows a summary. It needs the `polymarket` capability (Pro).
- **Options**: the `options` router stores options trades in [[options_trades (table)]]. The Options page was removed from the frontend on 2026-11-04 but the backend router remains. See [[Edition boundary]].
- **Notification outbox**: [[notifications]] has a provider-neutral delivery helper for the [[notification_outbox (table)]]. In the code I checked, only tests call that helper; the running app does not use it yet.
- **Frontend**: [[components.DiscordSettings]] (webhook form), [[pages.Watchlists]] (alerts next to watchlists), [[lib.portfolioAlerts]] and [[pages.Settings]].

## Key code
- [[routers.alerts]]: alert CRUD and the `run_check` logic.
- [[routers.discord]]: webhook CRUD, test and `send_discord_notification`.
- [[discord_webhooks]]: webhook URL validation.
- [[routers.settings]]: auto-sync schedule and audit log.
- [[routers.notes]]: trade notes.
- [[routers.polymarket]]: Polymarket wallet sync.
- [[routers.options]]: options trades (backend only).
- [[notifications]]: outbox delivery helper.
- [[jobs]]: autosync, dividend digest and alert sweeps across workspaces.
- [[routers.internal_jobs]]: the endpoints Cloud Scheduler calls.
- [[components.DiscordSettings]]: Discord settings UI.
- [[components.SyncScheduleSettings]]: auto-sync schedule UI.
- [[components.TradeNoteModal]]: trade note editor.

## Data
- [[price_alerts (table)]]: alert thresholds and triggered state.
- [[discord_webhooks (table)]]: encrypted webhook per portfolio plus notify switches.
- [[dividend_notifications (table)]]: which ex-dividend dates were announced.
- [[trade_notes (table)]]: one note per transaction.
- [[polymarket_positions (table)]] and [[options_trades (table)]]: add-on data.
- [[notification_outbox (table)]]: pending and sent transactional notifications.
- Migrations: [[0005_discord_webhook_expand]] and [[0007_discord_webhook_contract]] moved webhook URLs to encrypted storage.

## Related hubs
- [[Jobs and Cloud Scheduler]]
- [[Market data]]
- [[Broker importers and sync]]
- [[Billing and Stripe]]
- [[Secrets and security]]
- [[Emails]]
- [[Edition boundary]]

## Docs
- [[superpowers/specs/2026-07-13-broker-sync-schedule-design]]: design of the auto-sync schedule.
- [[superpowers/specs/2026-09-03-portfyl-job-triggering-design]]: how Cloud Scheduler triggers jobs.
- [[operations/scheduler-monitoring]]: monitoring the scheduled jobs.
- [[superpowers/plans/2026-09-01-portfyl-saas-monetization]]: plan limits for alerts and integrations.
- [[security/tenant-isolation-matrix]]: tenant isolation checks that cover these tables.
