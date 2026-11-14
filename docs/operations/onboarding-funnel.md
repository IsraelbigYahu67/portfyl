# Onboarding funnel and broker-demand runbook

Last updated: 2026-11-14

How to read the landing-to-first-import funnel and which brokers people ask
for. It builds on `docs/operations/posthog-activation-analytics.md`, which
covers the PostHog project, the consent gate and the production blocker
(`VITE_POSTHOG_KEY` stays unset in deployed builds until the legal review is
done). Nothing below changes that: until then no event leaves the browser.

The event names and property values are defined in one place,
`frontend/src/analytics/eventContract.js`. Anything not in that contract is
dropped (non-strict) or throws (dev/test).

## 1. The PostHog funnel

Main funnel, in this order:

1. `landing_viewed`
2. `broker_check_used` (optional branch: not every visitor tries the check)
3. `signup_started`
4. `signup_completed`
5. `onboarding_step_viewed` with `step = broker`
6. `onboarding_step_viewed` with `step = choices`
7. `portfolio_created`
8. `portfolio_data_imported`
9. `user_activation_reached`

Demo branch, a separate funnel: `demo_started` then `signup_cta_clicked`
(then continue at `signup_started` above).

Notes for reading it:

- `signup_started.source_surface` tells you where the visitor came from:
  `landing_hero`, `landing_closing`, `landing_broker_check`, `demo` or
  `direct`. Break the funnel down by it to see whether the landing broker
  check converts better than the hero button.
- `broker_check_used` has `result` (`supported` or `unsupported`) and
  `language` (`cs`, `en`, `de`). It fires once per distinct result, not per
  keystroke, and never contains the typed text.
- `onboarding_step_viewed.step` is `broker`, `choices` or `unsupported`
  (the "your broker is not supported yet" screen). The `unsupported` step
  is a drop-off branch, not part of the main path.
- `onboarding_broker_picked.broker_key` is a supported broker key or the
  fixed value `unsupported`, never the name the user typed. Use it for a
  breakdown of which brokers people choose.
- `broker_request_sent` has no properties. It only counts how many people
  asked to be notified; the names live in the database (section 2).

## 2. Which unsupported brokers do people ask for

Analytics deliberately carries no broker name. The names are stored in the
`broker_requests` table (workspace-scoped, row-level security forced), so the
overall ranking is read straight from the database. Run it with the
**migration-owner credential** (the restricted runtime role only sees its own
workspace's rows), against production Neon:

```sql
SELECT lower(broker_name) AS broker, count(*)
FROM broker_requests
GROUP BY 1
ORDER BY 2 DESC;
```

The names are free text typed by users (trimmed, whitespace collapsed, at
most 60 characters). Treat them as untrusted when pasting anywhere. The same
user is counted once per name per workspace. Keep results aggregate: do not
export names together with user or workspace identifiers.

## 3. Creating the funnel in PostHog is a manual step

Nobody has created these insights yet, and it is not automated. Creating the
funnels (and any dashboard) in the PostHog project is a manual step for the
founder, and it needs the founder's approval before anyone does it. Only do it
after the production blocker in `posthog-activation-analytics.md` is lifted,
otherwise there is no data to show.
