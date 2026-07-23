# NovaBank System Architecture Overview

## Company Context

NovaBank Financial Technologies runs four core products: **Mercury
Payments** (payment authorization), **Orion Identity** (identity and
access), **Atlas Analytics** (internal reporting/analytics), and the
**Nexus Customer Portal** (customer-facing web/mobile app).

## High-Level Architecture

All customer-facing traffic enters through the **Nexus API Gateway**,
which routes requests to backend services over an internal service
mesh. Services authenticate to each other using mutual TLS plus short
-lived service tokens issued by Orion Identity (see
`security/oauth2-implementation.md` for the user-facing auth flow).

- **Nexus API Gateway** — public entry point, rate limiting, routing.
- **Mercury Gateway** — payment authorization (see
  `products/mercury-payments.md`).
- **Orion Identity** — internal IdP for both users and services.
- **Atlas Analytics** — nightly ETL pipeline that aggregates
  transaction and usage data from Mercury and Nexus into an internal
  data warehouse (`atlas-warehouse`) for reporting.

## Data Flow

1. Nexus Customer Portal → Nexus API Gateway → backend services.
2. Mercury Gateway writes transaction events to an internal event bus
   (`novabank-events`).
3. Atlas Analytics consumes `novabank-events` nightly to build
   reporting tables in `atlas-warehouse`.
4. Internal dashboards (Business Analysis team) query
   `atlas-warehouse` directly; they never query production databases.

## Key Internal Terms

- **Nexus API Gateway** — public-facing entry point.
- **novabank-events** — internal event bus.
- **atlas-warehouse** — internal analytics data warehouse.

## Ownership

Owned by the Platform Architecture team. This document is the
canonical high-level reference; product-specific details live in the
respective `products/` and `security/` documents.
