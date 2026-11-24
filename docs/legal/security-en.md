# Portfyl Security

Updated: 22 November 2026

Portfyl is a portfolio overview: it reads data about your investments but
**never places trades or withdrawal orders**. This page describes how we
protect your data, what you can do yourself and how to report a
vulnerability to us.

## 1. How we protect data

- **Broker keys and tokens** are stored encrypted. In the cloud service they
  are encrypted with Google Cloud KMS. We do not write them to operational
  logs or to data exports.
- **Encrypted connection.** Portfyl is used over HTTPS. The sign-in cookie
  carries the `HttpOnly`, `Secure` and `SameSite=Lax` attributes and the
  `__Host-` prefix, so it is not sent unencrypted and scripts on the page
  cannot read it. We send security headers (Content-Security-Policy,
  `X-Content-Type-Options`, `Referrer-Policy`) and the pages cannot be
  embedded in a foreign frame.
- **Separation of users.** Each user's data is kept apart from everyone
  else's twice: in the application and in the PostgreSQL database itself,
  using row-level security.
- **Sessions.** After sign-in you receive a random opaque token; on the
  server we store only its hash, never the token itself. A session expires
  after 30 days and can be revoked: by signing out, by signing out of all
  devices or by changing your password. Data-changing requests are protected
  against CSRF and we rate-limit requests (including sign-in and e-mail
  sending).

## 2. Sign-in and passwords

E-mail and password sign-in, or sign-in with Google, is handled by Firebase
Authentication (Google). You send your password directly to Firebase;
Portfyl does not store it in its database.

## 3. Your data and deleting it

- We **do not sell** your data.
- When you disconnect a broker, the stored key is deleted.
- Deleting your account takes effect immediately: the data is removed from
  the database at once. Disaster-recovery backups may keep deleted data for
  at most 7 days, after which it is irreversibly overwritten.

Details on personal data are in the [Privacy
Policy](privacy-policy-en.md).

## 4. What we recommend you do

- At your broker, create a key for Portfyl with **read-only permissions**
  (where the broker allows it) and do not give it trading or withdrawal
  permissions.
- You can revoke the key at any time in your broker account settings;
  Portfyl then stops loading data from that broker.
- Use a strong, unique password and share it with no one.

## 5. How to report a vulnerability

If you have found a security issue, e-mail **support@portfyl.com**. Please
tell us where you found it, how to reproduce it and what impact it may have;
do not attach other people's data and do not exploit the issue. We will
respond without undue delay. We do not run a bug bounty programme.

We handle personal-data breaches under Articles 33 and 34 of the GDPR
(notifying the Czech Office for Personal Data Protection and, where the
risk requires it, the people affected).
