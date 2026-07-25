---
title: Orion Identity
classification: Internal
owner: Identity Platform Team
department: Identity Services
product_owner: Director, Identity
engineering_manager: Engineering Manager - Identity
service_owner: Identity Operations
version: 1.0
document_id: PRD-OI-001
last_updated: 2026-07-23
review_cycle: Semi-Annual
status: Approved
approved_by: Security Governance Council
tags: [identity, iam]
related_documents:
- mercury-payments.md
- nexus-portal.md
- atlas-analytics.md
---

# Purpose
Orion Identity provides centralized authentication, authorization, federation, and identity lifecycle services for enterprise platforms. It supports SSO, MFA, OAuth 2.0, OpenID Connect, RBAC, provisioning, service accounts, and audit logging.

## Integrations
Mercury Payments uses Orion Identity for service authentication. Nexus Portal authenticates end users through Orion Identity. Atlas Analytics consumes identity events for reporting.

## Operations
Platform Engineering manages infrastructure while Security Engineering governs identity policies. Authentication metrics, provisioning times, token issuance latency, and service availability are reviewed during governance meetings. Planned enhancements include expanded federation and lifecycle automation.
