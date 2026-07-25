---
title: Enterprise Service Catalog
version: 1.0
owner: Enterprise Service Management
business-unit: Technology Operations
classification: Internal
status: Approved
review-cycle: Annual
related-documents:
  - incident-escalation.md
  - sla-slo-policy.md
  - support-roles.md
  - ../operations/production-support.md
  - ../operations/incident-management.md
  - ../products/mercury-payments.md
  - ../products/orion-identity.md
---

# Enterprise Service Catalog

## Purpose

This document defines the enterprise service catalog for NovaBank Financial Technologies. It provides a standardized inventory of business and technology services delivered by the organization, identifies service ownership, establishes availability expectations, and defines the approved support channels for internal stakeholders and operational teams.

The catalog serves as the authoritative reference for service ownership and operational support responsibilities.

---

## Scope

This catalog applies to all production services supporting digital banking, payment processing, identity management, merchant onboarding, analytics, and enterprise platform operations.

---

# Business Services

The following business services support NovaBank's core operations.

| Service | Business Purpose | Primary Owner |
|---------|------------------|---------------|
| Mercury Payments | Secure payment authorization, settlement, and transaction processing | Payment Services |
| Orion Identity | Customer authentication, authorization, and identity lifecycle management | Identity Services |
| Merchant Registry | Merchant onboarding and lifecycle management | Merchant Operations |
| Nexus Portal | Customer self-service portal and account management | Digital Banking |
| Atlas Analytics | Enterprise reporting, dashboards, and business intelligence | Data & Analytics |
| Token Vault | Secure storage of credentials, API secrets, and encryption material | Information Security |

Business service owners are responsible for service strategy, availability, compliance, and lifecycle management.

---

# Technology Services

Technology services provide foundational capabilities supporting business applications.

| Technology Service | Description |
|--------------------|-------------|
| API Gateway | Secure routing and management of enterprise APIs |
| Identity Platform | Centralized authentication and access management |
| CI/CD Platform | Automated software build, testing, and deployment |
| Enterprise Monitoring | Application, infrastructure, and business monitoring |
| Centralized Logging | Collection and retention of operational logs |
| Backup & Recovery | Enterprise backup, restoration, and disaster recovery services |
| Event Streaming Platform | Reliable event-driven communication between enterprise systems |
| Configuration Management | Centralized configuration and secrets management |

Technology services are managed by Infrastructure Engineering and Technology Operations.

---

# Service Ownership

Each production service shall have clearly assigned ownership.

| Role | Responsibilities |
|------|------------------|
| Service Owner | Overall service lifecycle, roadmap, and business accountability |
| Technical Owner | System architecture, engineering, and technical governance |
| Operations Owner | Production support, monitoring, maintenance, and operational readiness |
| Information Security | Security governance and compliance oversight |

Ownership information shall be reviewed whenever major organizational or architectural changes occur.

---

# Availability Expectations

Enterprise services shall meet agreed operational objectives.

| Service Tier | Target Availability |
|--------------|--------------------|
| Tier 1 (Business Critical) | ≥ 99.95% |
| Tier 2 (Customer Facing) | ≥ 99.90% |
| Tier 3 (Internal Business Services) | ≥ 99.50% |

Planned maintenance windows are excluded from availability calculations when approved through the Change Management process.

---

# Support Channels

The following support channels are approved for operational issues and service requests.

- Enterprise Service Desk
- IT Service Management (ITSM) Platform
- Major Incident Bridge
- On-Call Support Teams
- Engineering Support Queue
- Security Operations Center (SOC)
- Enterprise Monitoring Alerts

Business-critical incidents shall be reported immediately through the Major Incident process defined in **incident-escalation.md**.

---

# Service Governance

Service Owners are responsible for:

- Maintaining accurate service documentation.
- Defining service dependencies.
- Reviewing service health metrics.
- Ensuring operational readiness.
- Coordinating disaster recovery testing.
- Maintaining support runbooks.
- Reviewing SLA and SLO performance.
- Supporting audit and compliance activities.

---

# References

- incident-escalation.md
- sla-slo-policy.md
- support-roles.md
- ../operations/production-support.md
- ../operations/incident-management.md
- ../operations/monitoring-observability.md
- ../operations/disaster-recovery.md
- ../products/mercury-payments.md
- ../products/orion-identity.md
```