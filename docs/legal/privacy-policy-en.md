# Portfyl Privacy and Cookie Policy

> **DRAFT – DO NOT PUBLISH.** Items marked `[[TODO]]` must be filled in and
> the text reviewed by a Czech lawyer. Technical source:
> [../compliance/data-processing-inventory.md](../compliance/data-processing-inventory.md);
> open points: [poznamky-pro-pravnika.md](poznamky-pro-pravnika.md). This
> English version mirrors
> [zasady-ochrany-osobnich-udaju-cs.md](zasady-ochrany-osobnich-udaju-cs.md).

Effective from: `[[TODO: publication date]]` \
Version: 0.1 (draft)

This policy explains what personal data the Portfyl service processes, why,
for how long, who receives it and what rights you have. It follows
Regulation (EU) 2016/679 (GDPR), Czech Act No. 110/2019 Coll. and, for
cookies and browser storage, Section 89(3) of Czech Act No. 127/2005 Coll. on
Electronic Communications.

## 1. Controller and contact

**Jakub Zoubek**, Company ID (IČO) 67772366, registered business address
Brusinková 1983, 252 28 Černošice, Czech Republic ("**we**", "**us**").

For anything related to personal data, contact **support@portfyl.com**. We
have not appointed a Data Protection Officer because we are not required to.
`[[LAWYER: confirm]]`

## 2. What data we process

| Category | Examples | Source |
|---|---|---|
| **Account data** | e-mail, name (if you sign in with Google), internal account ID, e-mail verification date | you at registration, or Google if you sign in with Google |
| **Portfolio data** | portfolio names, transactions, tickers, quantities, prices, currencies, dates, cash, dividends, options, notes | you (manual entry, file import) or your broker if you connect it |
| **Broker and service connections** | encrypted API keys, sync status, an anonymised fingerprint of your broker account number, encrypted Discord webhook URL | you |
| **Subscription data** | plan, period, subscription status, customer and transaction IDs at the Payment Partner, country | the Payment Partner; **we never receive your card number** |
| **Technical and security data** | IP address, browser type, hashed session tokens, last sign-in time, security records (audit log), feature usage counts | automatically when you use the Service |
| **Support communication** | the content of e-mails you send us | you |
| **Analytics (consent only)** | pseudonymous app-usage events – after sign-in we link them to an internal account identifier, not to your e-mail or name; see Section 8 | automatically, only if you consent |

We do not process special categories of data (such as health data) and we do
not ask for national ID numbers or identity documents. The Service is only
for people aged 18 or over.

**Providing data.** An e-mail address is required to create an account –
without it we cannot provide the Service. Portfolio data, broker connections
and Discord are optional; without them only the related features are
unavailable. Consent to analytics is entirely voluntary and has no effect on
how the Service works.

## 3. Why we process data and on what legal basis

| Purpose | Legal basis (Art. 6 GDPR) |
|---|---|
| Creating and managing your account and providing the Service (calculations, imports, broker sync, notifications) | **performance of a contract** – Art. 6(1)(b) |
| Managing your subscription and communicating about it | **performance of a contract** – Art. 6(1)(b) |
| Securing the Service, preventing abuse, protecting the separation of users' data, handling incidents, error records | **legitimate interest** in secure operation – Art. 6(1)(f) |
| Handling complaints, questions and requests to exercise your rights | **contract** / **legal obligation** – Art. 6(1)(b) and (c) |
| Meeting tax and accounting obligations | **legal obligation** – Art. 6(1)(c) |
| Protecting our legal claims | **legitimate interest** – Art. 6(1)(f) |
| App-usage analytics | **consent** – Art. 6(1)(a); you can withdraw it at any time |

We do not send marketing e-mails. If we ever want to, we will ask for your
consent first.

We do not use automated decision-making or profiling with legal or similarly
significant effects on you.

## 4. Who receives your data

We do not sell data. We share it only with suppliers that help us run the
Service (**processors**), to the extent needed for their task and under a
data processing agreement:

| Supplier | Role | Where data is processed |
|---|---|---|
| Google Cloud (Google Cloud EMEA Ltd. / Google LLC) | application hosting (Cloud Run), encryption keys, operational logs, scheduled jobs | EU – Belgium (`europe-west1`); support may access from the US |
| Google Firebase Authentication | registration, sign-in, e-mail verification, Google sign-in | EU/US |
| Neon Inc. | database (PostgreSQL) and backups | EU – Frankfurt `[[VERIFY]]` |
| Cloudflare, Inc. | DNS, encrypted connections (TLS), attack protection | global network |
| PostHog Inc. (PostHog Cloud EU) | usage analytics – **only with your consent** | EU – Frankfurt |

**Independent controllers** – these process data under their own policies:

- **Payment Partner** – a Stripe group company trading under the Link brand
  (Stripe Managed Payments) `[[TODO: exact name and address of the selling
  entity]]` – accepts payments as the seller, issues receipts, handles VAT and
  deals with payment support, refunds and subscription management on
  link.com.
- **Your broker** (e.g. Trading 212, Interactive Brokers, eToro) – only if you
  connect it; we send it your API credentials and receive your account data.
- **Discord** – only if you set up Discord notifications.
- **Market-data providers** (e.g. Yahoo Finance, SEC EDGAR) – receive only
  tickers and date ranges, never your personal data or portfolio contents.

We may also disclose data to public authorities where the law requires it.

## 5. Transfers outside the EU

Some suppliers (Google, Cloudflare, Neon, PostHog) are US companies or
provide support from outside the EU. Transfers to the US rely on the European
Commission's adequacy decision (**EU-U.S. Data Privacy Framework**) where the
supplier is certified, and otherwise on the Commission's **Standard
Contractual Clauses**. `[[LAWYER: verify each supplier's certification and
DPA]]` We will provide a copy of the Standard Contractual Clauses on request
at support@portfyl.com; the list of EU-U.S. Data Privacy Framework certified
companies is at https://www.dataprivacyframework.gov.

## 6. How long we keep data

| Data | Retention |
|---|---|
| Account, portfolios and all in-app data | while your account exists; for deletion requests see below |
| Database backups | data deleted from the app may remain in backups for at most `[[TODO: 7 days]]`, then it is irreversibly overwritten |
| Operational logs | 30 days; they contain no portfolio content or passwords |
| Session records | 30 days after expiry or sign-out |
| Security records (audit log) | while your account exists; deleted with it |
| Support communication | 1 year after resolution |
| Payment records | kept by the Payment Partner; we keep subscription records for as long as tax law requires `[[LAWYER: add period]]` |
| Analytics data (with consent) | at most 1 year |

**Deleting your account:** go to Settings → Data & privacy. For security, we
first ask you to sign in again. Deletion takes place after a 30-day period during which you can cancel it; all account
data is then removed from the database and disappears from backups no later
than the period stated above.

Cancelling a subscription **does not delete** your account – it only moves
to the Free plan.

## 7. Your rights

You have the right to:

- **access** the data we hold about you;
- **rectify** inaccurate data;
- **erasure** ("right to be forgotten") – you can delete your account
  yourself in the app;
- **restrict** processing;
- **data portability** – you can download your data as JSON in Settings;
- **withdraw consent** (e.g. to analytics) at any time in cookie settings,
  without affecting earlier processing;
- **lodge a complaint** with the Czech Office for Personal Data Protection
  (Úřad pro ochranu osobních údajů), Pplk. Sochora 27, 170 00 Prague 7,
  `https://uoou.gov.cz`, or with the supervisory authority in your EU
  country.

**Right to object.** You may object at any time, at support@portfyl.com, to
processing we carry out on the basis of legitimate interest (security,
protection of legal claims). We will stop that processing unless we show
compelling legitimate grounds that override your interests.

Send requests to **support@portfyl.com**. We will reply within one month; in
justified cases we may extend this by a further two months and will tell you
in advance. To
protect your account, we may ask you to confirm that the request comes from
your account's e-mail address.

## 8. Cookies and browser storage

**Necessary or requested by you (no consent needed, Section 89(3) of Act
No. 127/2005 Coll.)** – the Service does not work without them, or would not
remember your settings:

| Name | Type | Purpose | Duration |
|---|---|---|---|
| `__Host-portfyl_session` | cookie | keeps you signed in (random session identifier) | up to 30 days |
| `portfyl_analytics_consent` | first-party cookie shared by `portfyl.com` and subdomains | remembers your analytics consent choice | 180 days |
| `sb_theme`, `sb_theme_style`, `sb_palette`, `sb_currency`, `sb_portfolio_id`, `sb_view_mode`, `portfyl_landing_language` | localStorage | appearance, currency, selected portfolio, view mode and landing-page language | until you clear them |
| `sb_dashboard_layout_v3`, `sb_dashboard_widget_order_v4`, `sb_dashboard_widgets_hidden`, `sb_stock_report_sections`, `sb_stock_report_tabs` | localStorage | dashboard layout and stock-detail settings | until you clear them |
| `__cf_bm` and other Cloudflare cookies | cookie | bot and attack protection | up to 30 minutes |

**Analytics (consent only)** – PostHog Cloud EU. These are stored only after
you accept analytics:

| Name | Type | Purpose | Duration |
|---|---|---|---|
| `ph_<project>_posthog` | cookie and localStorage | visitor and session identifier for analytics | as set by PostHog, typically 1 year |
| `portfyl_captured_once:*`, `portfyl_activation_v1:*` | localStorage | so one-time events are not sent twice and activation state is remembered | until you clear them |

We measure only a fixed list of events (e.g. "opened the demo", "created a
portfolio"). After sign-in we link them to an internal account identifier (a
pseudonym), not to your e-mail or name. We never collect your e-mail, name,
portfolio contents, transactions, amounts or notes. Session recording is
disabled. **If you reject analytics or have not yet decided, we send nothing
to PostHog**, and no analytics cookies or storage are created.

We do not use advertising or third-party tracking cookies.

## 9. Security

We protect data with, among other things, encrypted connections (HTTPS),
encryption of API keys and webhooks with keys managed in Google Cloud KMS,
database-level separation of each user's data, revocable sessions and
security event logging. Portfolio contents and secrets are excluded from
operational logs.

## 10. Changes to this policy

We may update this policy. We will tell you about material changes in advance
by e-mail or in the app. The current version is always at
https://portfyl.com/privacy.
