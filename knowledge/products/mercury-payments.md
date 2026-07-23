# Mercury Payments

## Overview

Mercury Payments is NovaBank Financial Technologies' core payment
authorization platform. It handles real-time authorization, settlement,
and reconciliation for card and bank-transfer transactions across
NovaBank's retail and merchant products.

## Payment Authorization Flow

1. A transaction request arrives at the Mercury Gateway from either the
   Nexus Customer Portal or a merchant-facing API integration.
2. The Gateway performs a risk check via the internal Fraud Scoring
   Service before forwarding the request to the acquiring bank.
3. If the acquiring bank does not respond within 4 seconds, Mercury
   retries the authorization up to three times using exponential
   backoff before failing over to the secondary backup gateway
   (`mercury-failover-gw`).
4. Successful authorizations are written to the `MercuryLedger` service,
   which reconciles nightly against the settlement files received from
   the card networks.

## Retry and Failover Behavior

Mercury's retry logic is intentionally conservative: three retries,
backoff starting at 500ms, doubling each attempt. This was chosen after
an incident where an aggressive retry policy caused duplicate
authorizations during a partner outage. The failover gateway runs a
reduced feature set (authorization only, no loyalty-point calculation)
to keep failover fast during partner-side outages.

## Key Internal Terms

- **Mercury Gateway** — the primary authorization service.
- **Fraud Scoring Service** — internal risk engine, not exposed externally.
- **MercuryLedger** — internal ledger/reconciliation service.
- **mercury-failover-gw** — the secondary/backup authorization path.

## Ownership

Owned by the Payments Platform team. Any changes to retry/failover
behavior require sign-off from the Payments Platform lead and Security.
