---
title: Atlas Analytics
classification: Internal
owner: Analytics Platform Team
department: Enterprise Analytics
product_owner: Director, Analytics
engineering_manager: Engineering Manager - Analytics
service_owner: Analytics Operations
version: 1.0
document_id: PRD-AA-001
last_updated: 2026-07-23
review_cycle: Semi-Annual
status: Approved
approved_by: Data Governance Council
tags: [analytics, reporting]
related_documents:
- mercury-payments.md
- orion-identity.md
- nexus-portal.md
---

# Purpose
Atlas Analytics is the enterprise reporting platform providing executive dashboards, operational reporting, KPI scorecards, fraud analytics, and scheduled business reports.

## Data Sources
The platform consumes payment events from Mercury Payments, authentication events from Orion Identity, merchant metadata, and operational telemetry.

## Capabilities
- Executive dashboards
- Operational dashboards
- Fraud analytics
- Scheduled reporting
- Alerting
- Self-service analytics

| Source | Usage |
|---|---|
| Mercury Payments | Payment KPIs |
| Orion Identity | Identity metrics |
| Merchant Registry | Merchant insights |

## Operations
Dashboards refresh using scheduled processing windows. Operational SLAs cover report availability, refresh completion, and data quality monitoring. Product ownership reviews KPI trends during Quarterly Business Reviews.
