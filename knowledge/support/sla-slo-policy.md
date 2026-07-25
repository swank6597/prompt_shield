---
title: SLA and SLO Policy
version: 1.0
owner: Enterprise Service Management
business-unit: Technology Operations
classification: Internal
status: Approved
review-cycle: Annual
related-documents:
  - service-catalog.md
  - incident-escalation.md
  - support-roles.md
  - ../operations/production-support.md
  - ../operations/monitoring-observability.md
  - ../operations/incident-management.md
---

# SLA and SLO Policy

## Purpose

This document defines the Service Level Agreement (SLA) and Service Level Objective (SLO) framework for NovaBank Financial Technologies. The policy establishes measurable service targets that ensure consistent operational performance, customer satisfaction, and alignment with enterprise business commitments.

SLA and SLO metrics are continuously monitored to support proactive service management and continual improvement.

---

## Scope

This policy applies to all production business services, customer-facing applications, enterprise APIs, infrastructure platforms, and shared technology services managed by NovaBank Technology Operations.

Service Owners are accountable for defining and maintaining service objectives for their respective platforms.

---

# SLA Objectives

Service Level Agreements define the operational commitments provided to business stakeholders.

Primary SLA objectives include:

- Timely incident response
- Predictable service restoration
- Reliable platform availability
- Effective customer communication
- Compliance with operational support processes
- Continuous monitoring of service performance

Business-critical services shall maintain higher SLA commitments than internal support services.

---

# SLO Definitions

Service Level Objectives establish measurable internal performance targets used to achieve SLA commitments.

Standard SLO categories include:

| Objective | Measurement |
|-----------|-------------|
| Availability | Percentage of service uptime |
| Latency | Average API and application response time |
| Reliability | Successful transaction completion rate |
| Error Rate | Percentage of failed requests |
| Recovery Time | Average service restoration duration |
| Monitoring Coverage | Percentage of production components actively monitored |

SLOs are reviewed periodically to ensure alignment with business priorities and service maturity.

---

# Response Targets

The following response targets apply after incident classification.

| Severity | Initial Response Target |
|----------|-------------------------|
| **P1 – Critical** | Within 15 minutes |
| **P2 – High** | Within 30 minutes |
| **P3 – Medium** | Within 2 hours |
| **P4 – Low** | Within 1 business day |

Response targets measure the time between incident logging and initial engagement by the responsible support team.

---

# Resolution Targets

Resolution targets represent expected restoration timeframes.

| Severity | Target Resolution |
|----------|-------------------|
| **P1 – Critical** | Within 4 hours |
| **P2 – High** | Within 8 hours |
| **P3 – Medium** | Within 2 business days |
| **P4 – Low** | Within 5 business days |

Where permanent resolution cannot be achieved within the target timeframe, an approved workaround and ongoing communication shall be provided until final remediation.

---

# Availability Goals

Production services are assigned availability objectives based on business criticality.

| Service Tier | Availability Target |
|--------------|---------------------|
| Tier 1 – Business Critical | ≥ 99.95% |
| Tier 2 – Customer Facing | ≥ 99.90% |
| Tier 3 – Internal Services | ≥ 99.50% |

Planned maintenance windows approved through the Change Management process are excluded from availability calculations.

---

# Performance Monitoring

Enterprise Monitoring continuously measures SLA and SLO performance using:

- Application health monitoring
- Infrastructure monitoring
- API performance metrics
- Synthetic transaction monitoring
- Availability dashboards
- Alerting and notification systems
- Customer experience metrics

Breaches of established thresholds automatically generate operational alerts for investigation.

---

# Reporting Expectations

Operational performance reports shall be produced on a scheduled basis and include:

- SLA compliance percentage
- SLO achievement metrics
- Service availability
- Incident trends
- Mean Time to Acknowledge (MTTA)
- Mean Time to Restore Service (MTRS)
- Root Cause Analysis completion
- Problem Management trends

Monthly service review meetings evaluate performance results and identify improvement opportunities.

---

# Roles and Responsibilities

| Role | Responsibility |
|------|----------------|
| Service Owner | Define and approve SLA/SLO targets |
| Technology Operations | Monitor operational performance |
| Incident Manager | Coordinate restoration activities during major incidents |
| Engineering Teams | Resolve defects affecting service performance |
| Enterprise Service Management | Publish performance reports and oversee continual improvement |

---

# References

- service-catalog.md
- incident-escalation.md
- support-roles.md
- ../operations/production-support.md
- ../operations/monitoring-observability.md
- ../operations/incident-management.md
- ../operations/release-management.md