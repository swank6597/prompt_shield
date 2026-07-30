---
title: Support Roles and Responsibilities
version: 1.0
owner: Enterprise Service Management
business-unit: Technology Operations
classification: Internal
status: Approved
review-cycle: Annual
related-documents:
  - service-catalog.md
  - incident-escalation.md
  - sla-slo-policy.md
  - ../operations/production-support.md
  - ../operations/incident-management.md
  - ../operations/operational-runbooks.md
  - ../operations/monitoring-observability.md
  - ../products/mercury-payments.md
  - ../products/orion-identity.md
---

# Support Roles and Responsibilities

## Purpose

This document defines the operational support organization for NovaBank Financial Technologies. It establishes the responsibilities of Level 1 (L1), Level 2 (L2), and Level 3 (L3) support teams, clarifies product ownership, defines on-call expectations, and standardizes communication practices to ensure consistent support for enterprise services.

The support model enables efficient incident resolution while maintaining service availability and operational excellence.

---

## Scope

This standard applies to all production applications, APIs, infrastructure platforms, shared services, and customer-facing systems operated by NovaBank, including Mercury Payments, Orion Identity, Merchant Registry, Nexus Portal, Atlas Analytics, and Token Vault.

---

# Support Organization

NovaBank follows a three-tier support model.

| Support Level | Primary Responsibility |
|---------------|------------------------|
| **L1 – Service Desk** | Initial incident intake, user communication, triage, and basic troubleshooting |
| **L2 – Application & Platform Support** | Functional analysis, infrastructure investigation, and service restoration |
| **L3 – Engineering Support** | Product expertise, code-level diagnosis, defect resolution, and permanent fixes |

Major incidents are coordinated by the Incident Manager with support from all operational teams.

---

# Level 1 (L1) Responsibilities

The Service Desk serves as the primary point of contact for operational support.

Responsibilities include:

- Receive incidents and service requests
- Categorize and prioritize tickets
- Perform initial diagnosis using approved runbooks
- Resolve known issues within documented procedures
- Escalate unresolved incidents to L2
- Communicate ticket status to users
- Maintain accurate incident records within the ITSM platform

L1 personnel shall not perform production configuration changes without approved authorization.

---

# Level 2 (L2) Responsibilities

L2 teams provide specialized application and platform support.

Responsibilities include:

- Investigate application and infrastructure issues
- Analyze monitoring alerts and system logs
- Restore degraded services
- Coordinate with infrastructure and security teams
- Validate production fixes
- Escalate product defects to L3 Engineering
- Support planned maintenance and release activities

L2 teams maintain operational documentation and update support runbooks as required.

---

# Level 3 (L3) Responsibilities

L3 Engineering provides expert product support.

Responsibilities include:

- Perform code-level troubleshooting
- Resolve software defects
- Develop emergency hotfixes
- Review recurring incidents
- Conduct Root Cause Analysis (RCA)
- Improve system reliability and performance
- Provide technical guidance during major incidents

L3 teams collaborate with Product Owners to prioritize permanent corrective actions.

---

# Product Ownership

Each enterprise platform has designated business and technical ownership.

| Product | Business Owner | Technical Owner |
|----------|----------------|-----------------|
| Mercury Payments | Payment Services | Payments Engineering |
| Orion Identity | Identity Services | Identity Engineering |
| Merchant Registry | Merchant Operations | Platform Engineering |
| Nexus Portal | Digital Banking | Customer Experience Engineering |
| Atlas Analytics | Data & Analytics | Analytics Engineering |
| Token Vault | Information Security | Security Engineering |

Product Owners are responsible for service roadmap, operational health, and lifecycle governance.

---

# On-Call Responsibilities

Business-critical services require continuous operational support.

On-call responsibilities include:

- Respond to production alerts within defined SLA targets
- Participate in Major Incident bridges
- Support emergency deployments and approved hotfixes
- Validate service recovery after restoration
- Escalate unresolved issues to appropriate technical teams
- Document actions taken during incident response
- Participate in post-incident reviews

On-call schedules shall be maintained by Engineering Managers and reviewed regularly to ensure adequate coverage.

---

# Communication Expectations

Support teams shall maintain timely and accurate communication throughout the incident lifecycle.

Communication requirements include:

- Acknowledge incidents within established response targets
- Provide regular status updates during major incidents
- Notify stakeholders of service restoration
- Document technical findings and resolution activities
- Escalate risks promptly to Service Owners and Incident Managers
- Maintain professional communication across all support channels

All operational communications shall follow the Enterprise Incident Escalation Standard.

---

# References

- service-catalog.md
- incident-escalation.md
- sla-slo-policy.md
- ../operations/production-support.md
- ../operations/incident-management.md
- ../operations/operational-runbooks.md
- ../operations/monitoring-observability.md
- ../products/mercury-payments.md
- ../products/orion-identity.md