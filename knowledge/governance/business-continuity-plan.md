---
title: Business Continuity Plan
version: 1.0
owner: Enterprise Risk & Compliance
business-unit: Governance, Risk & Compliance
classification: Confidential
status: Approved
review-cycle: Annual
related-documents:
  - enterprise-risk-management.md
  - vendor-risk-policy.md
  - operational-resilience.md
  - ../operations/disaster-recovery.md
  - ../operations/backup-restore.md
  - ../operations/incident-management.md
  - ../support/sla-slo-policy.md
---

# Business Continuity Plan

## Purpose

This Business Continuity Plan (BCP) establishes the enterprise framework for maintaining critical business operations during disruptive events affecting NovaBank Financial Technologies. The plan defines governance, recovery priorities, communication procedures, and operational responsibilities to ensure continuity of customer-facing and internal business services while minimizing financial, operational, and regulatory impact.

The Business Continuity Plan complements the Disaster Recovery Plan by focusing on business operations rather than technology recovery alone.

---

## Scope

This plan applies to all business units, technology teams, production services, corporate functions, third-party providers, and operational support organizations involved in delivering critical banking and payment services.

Business Continuity requirements shall be incorporated into strategic planning, operational procedures, and annual resilience testing.

---

# Critical Business Functions

The following services are designated as business-critical.

| Business Function | Supporting Platform | Business Priority |
|-------------------|--------------------|-------------------|
| Payment Processing | Mercury Payments | Critical |
| Customer Authentication | Orion Identity | Critical |
| Merchant Operations | Merchant Registry | High |
| Customer Self-Service | Nexus Portal | High |
| Enterprise Analytics | Atlas Analytics | Medium |
| Secret & Credential Management | Token Vault | Critical |

Business Owners are responsible for maintaining continuity procedures for their respective services.

---

# Recovery Objectives

Business continuity planning aligns with enterprise recovery objectives.

| Objective | Target |
|-----------|--------|
| Critical Service Recovery | ≤ 4 Hours |
| Recovery Point Objective (RPO) | ≤ 15 Minutes |
| Recovery Time Objective (RTO) | ≤ 4 Hours |
| Critical Communication Activation | ≤ 30 Minutes |
| Executive Notification | ≤ 15 Minutes |

Recovery objectives are reviewed annually or following significant architectural or business changes.

---

# Business Continuity Procedures

During a disruptive event, the following activities shall be performed:

1. Identify and assess the business impact.
2. Activate the Business Continuity Team.
3. Notify executive leadership and service owners.
4. Prioritize restoration of critical business functions.
5. Execute documented continuity procedures.
6. Coordinate with Disaster Recovery and Technology Operations teams.
7. Monitor service restoration progress.
8. Validate operational readiness before resuming normal business operations.
9. Conduct a post-event review and update continuity documentation.

Operational decisions shall prioritize customer impact, regulatory obligations, and employee safety.

---

# Communication Plan

Effective communication is essential during business disruption.

Communication activities include:

- Initial incident notification
- Executive leadership updates
- Business unit coordination
- Technology Operations updates
- Customer communications (where applicable)
- Regulatory notifications when required
- Third-party vendor coordination
- Recovery status reporting
- Business resumption confirmation

The Incident Manager serves as the primary coordination point for enterprise communications during major disruptions.

---

# Testing Schedule

Business continuity capabilities shall be validated through regular testing.

| Test Activity | Frequency |
|--------------|-----------|
| Business Continuity Plan Review | Annual |
| Tabletop Exercise | Semi-Annual |
| Disaster Recovery Exercise | Annual |
| Communication Tree Validation | Quarterly |
| Critical Vendor Participation | Annual |
| Recovery Objective Validation | Annual |

Testing results shall be documented, reviewed by Enterprise Risk & Compliance, and tracked until identified improvement actions are completed.

---

# Roles and Responsibilities

| Role | Responsibility |
|------|----------------|
| Executive Leadership | Approve continuity strategy and recovery priorities |
| Enterprise Risk & Compliance | Maintain the Business Continuity Program |
| Business Unit Owners | Maintain continuity procedures for business functions |
| Technology Operations | Restore supporting technology platforms |
| Incident Manager | Coordinate enterprise response activities |
| Information Security | Support secure recovery of critical systems |

---

# Compliance

Business continuity activities shall comply with enterprise governance standards, regulatory obligations, Disaster Recovery procedures, and Operational Resilience requirements. Plan reviews, test results, corrective actions, and recovery evidence shall be retained in accordance with the Data Retention Policy and made available for audit upon request.

---

# References

- enterprise-risk-management.md
- vendor-risk-policy.md
- operational-resilience.md
- ../operations/disaster-recovery.md
- ../operations/backup-restore.md
- ../operations/incident-management.md
- ../support/sla-slo-policy.md
- ../support/incident-escalation.md