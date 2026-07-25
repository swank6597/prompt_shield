---
title: Application Landscape
version: 1.0
owner: Enterprise Architecture Office
business-unit: Enterprise Technology
classification: Confidential
status: Approved
review-cycle: Annual
related-documents:
  - enterprise-architecture.md
  - system-integrations.md
  - deployment-architecture.md
  - ../products/mercury-payments.md
  - ../products/orion-identity.md
  - ../products/merchant-registry.md
  - ../support/service-catalog.md
---

# Application Landscape

## Purpose

This document provides an enterprise-wide view of the applications that support NovaBank Financial Technologies' business capabilities. It identifies application ownership, business responsibilities, shared platform services, and high-level dependencies to support architecture governance, operational planning, and technology decision-making.

The application landscape is maintained by the Enterprise Architecture Office and reviewed annually or following significant platform changes.

---

## Major Enterprise Applications

| Application | Business Function | Primary Owner |
|-------------|-------------------|---------------|
| Mercury Payments | Payment authorization, settlement, and transaction processing | Payments Engineering |
| Orion Identity | Identity, authentication, authorization, and access management | Identity Services |
| Merchant Registry | Merchant onboarding and lifecycle management | Merchant Operations |
| Nexus Portal | Customer digital banking experience | Digital Banking |
| Atlas Analytics | Enterprise reporting and operational intelligence | Data & Analytics |
| Token Vault | Enterprise credential and secret management | Information Security |

Each application is considered a business-owned platform supported by dedicated engineering and operations teams.

---

# Product Relationships

Enterprise applications operate as an integrated platform supporting financial services.

- Nexus Portal authenticates users through Orion Identity.
- Mercury Payments processes customer and merchant payment transactions.
- Merchant Registry provides merchant profile information to Mercury Payments.
- Atlas Analytics consumes operational and business events from enterprise platforms.
- Token Vault supplies managed credentials to approved enterprise services.
- Shared monitoring, logging, and identity services support all production applications.

Application integrations shall follow the enterprise architecture and integration standards.

---

# Internal Shared Services

The following shared services provide common enterprise capabilities:

- API Gateway
- Identity Services
- Event Streaming Platform
- Enterprise Monitoring
- Centralized Logging
- Configuration Management
- CI/CD Platform
- Notification Services
- Audit Logging
- Backup and Recovery Services

Shared services reduce duplication, simplify governance, and promote consistent operational practices across all business domains.

---

# Data Ownership

Business data ownership remains within the originating business domain.

| Business Domain | System of Record |
|-----------------|------------------|
| Customer Identity | Orion Identity |
| Payment Transactions | Mercury Payments |
| Merchant Information | Merchant Registry |
| Operational Metrics | Atlas Analytics |
| Secrets and Credentials | Token Vault |
| Customer Portal Preferences | Nexus Portal |

Applications may consume enterprise data through approved interfaces but shall not become secondary systems of record without Architecture Review Board approval.

---

# Application Responsibilities

Each enterprise application is responsible for:

- Managing its business capability.
- Maintaining data quality within its ownership domain.
- Publishing supported APIs and events.
- Enforcing enterprise security standards.
- Generating operational logs and audit records.
- Supporting monitoring and operational reporting.
- Maintaining documented recovery procedures.
- Meeting defined Service Level Objectives (SLOs).

Business capabilities shall remain loosely coupled to support independent evolution and deployment.

---

# High-Level Dependency Overview

Enterprise applications have the following dependency model:

- Customer-facing services depend on Orion Identity for authentication.
- Payment services depend on Merchant Registry for merchant validation.
- Atlas Analytics depends on business event publication from operational systems.
- All applications rely on shared infrastructure, monitoring, identity, and configuration services.
- Production services utilize Token Vault for secure credential retrieval.
- Operational support functions rely on centralized logging and observability platforms.

Cross-application dependencies shall be minimized and documented to reduce operational risk and improve service resilience.

---

# Compliance

Application architecture shall comply with Enterprise Architecture principles, Operational Resilience requirements, Secure Coding Standards, Information Security policies, and Regulatory Compliance obligations. Significant application changes shall undergo architecture review before implementation.

---

# References

- enterprise-architecture.md
- system-integrations.md
- deployment-architecture.md
- ../products/mercury-payments.md
- ../products/orion-identity.md
- ../products/merchant-registry.md
- ../support/service-catalog.md
- ../governance/operational-resilience.md