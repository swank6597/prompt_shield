---
title: Token Vault
classification: Internal
owner: Payment Security Platform
department: Shared Security Services
product_owner: Director, Security Platforms
engineering_manager: Engineering Manager - Token Services
service_owner: Vault Operations
version: 1.0
document_id: PRD-TV-001
last_updated: 2026-07-23
review_cycle: Semi-Annual
status: Approved
approved_by: Security Governance Council
tags:
- tokenization
- pci
- payment-security
related_documents:
- mercury-payments.md
- merchant-registry.md
- orion-identity.md
- atlas-analytics.md
---

# Purpose

Token Vault provides centralized tokenization services for payment platforms. It replaces Primary Account Numbers (PANs) with internally managed surrogate tokens, allowing downstream applications to process transactions without storing sensitive cardholder information. The service is consumed primarily by Mercury Payments and selected internal payment services.

# Business Context

The platform supports enterprise payment processing by reducing the exposure of regulated payment data. Merchant onboarding workflows integrate with Token Vault through Mercury Payments, ensuring newly onboarded merchants use tokenized payment references from their first production transaction. The platform operates as a shared enterprise service with defined operational SLAs.

# Core Capabilities

- PAN tokenization
- Secure detokenization for authorized services
- Token lifecycle management
- Encryption key management
- Scheduled key rotation
- Audit logging
- Disaster recovery support
- High availability deployment

| Consumer | Purpose |
|---|---|
| Mercury Payments | Payment tokenization |
| Merchant Registry | Merchant payment references |
| Atlas Analytics | Token usage metrics only |

# Operational Model

All service requests require authenticated service identities provided by Orion Identity. Access policies follow least-privilege principles and are reviewed periodically. Production deployments follow Release Train governance with mandatory Production Readiness Reviews and Change Advisory Board approval.

Operational dashboards monitor vault availability, token generation latency, failed tokenization requests, encryption key health, replication status, and audit event volume. Security alerts are routed to the Security Operations team while infrastructure alerts are managed by Platform Engineering.

# Ownership

The Product Owner prioritizes roadmap initiatives while the Service Owner is responsible for production availability and operational compliance. Platform Engineering manages shared infrastructure. Security Engineering approves cryptographic changes and key rotation schedules. Quarterly reviews evaluate operational KPIs, audit findings, and disaster recovery readiness.
