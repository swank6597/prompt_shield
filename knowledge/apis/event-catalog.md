---
title: Event Catalog
version: 1.0
owner: Enterprise Integration Engineering
business-unit: Enterprise Integration Services
classification: Internal
status: Approved
review-cycle: Quarterly
related-documents:
  - payment-api.md
  - identity-api.md
  - integration-guidelines.md
  - ../products/mercury-payments.md
  - ../products/orion-identity.md
  - ../operations/incident-management.md
  - ../operations/monitoring-observability.md
---

# Event Catalog

## Purpose

This document defines the enterprise event catalog used across NovaBank Financial Technologies. It standardizes business events exchanged between enterprise applications through the Enterprise Event Bus, enabling asynchronous communication, loose coupling, and reliable integration between payment, identity, fraud detection, analytics, and operational platforms.

The event catalog ensures consistent event naming, payload ownership, lifecycle management, and operational governance across all event producers and consumers.

---

## Business Overview

NovaBank adopts an event-driven architecture to support scalable business processes that span multiple applications. Rather than relying exclusively on synchronous REST communication, systems publish business events whenever significant domain actions occur.

Consumers subscribe only to events relevant to their business capabilities, reducing system dependencies while improving resilience and scalability.

Major event producers include:

- Mercury Payments
- Orion Identity
- Merchant Registry
- Nexus Portal
- Token Vault
- Fraud Detection Platform

Events are consumed by downstream applications including Atlas Analytics, Notification Services, Audit Services, Compliance Reporting, and Customer Experience platforms.

---

## Enterprise Event-Driven Architecture

The Enterprise Event Bus provides:

- Asynchronous message delivery
- Event persistence
- Guaranteed delivery
- Consumer isolation
- Retry management
- Dead-letter queue support
- Event replay capabilities
- Centralized monitoring

Each event contains standard metadata including:

- Event ID
- Correlation ID
- Event Type
- Source System
- Event Timestamp
- Schema Version
- Business Identifier

All published events must be immutable once committed.

---

## Major Business Events

The following business domains publish enterprise events:

| Domain | Sample Events |
|---------|---------------|
| Payments | Payment Authorized, Payment Settled |
| Identity | User Authenticated, Token Revoked |
| Fraud | Fraud Alert Raised, Transaction Flagged |
| Merchant | Merchant Created, Merchant Updated |
| Customer | Customer Registered, Profile Updated |
| Notifications | Email Sent, SMS Delivered |

Event ownership is maintained by the originating business domain.

---

## Payment Events

The Mercury Payments platform publishes operational and business events throughout the payment lifecycle.

Common payment events include:

- Payment Initiated
- Payment Authorized
- Payment Captured
- Payment Declined
- Payment Refunded
- Payment Cancelled
- Settlement Completed
- Settlement Failed

These events support downstream reconciliation, reporting, fraud analysis, customer notifications, and regulatory reporting.

---

## Identity Events

The Orion Identity platform publishes authentication and authorization events.

Examples include:

- User Authenticated
- Authentication Failed
- User Logged Out
- Access Token Issued
- Access Token Revoked
- Refresh Token Generated
- Password Changed
- Multi-Factor Authentication Completed
- Account Locked

Security Operations consumes these events for continuous monitoring and threat detection.

---

## Fraud Events

The Fraud Detection platform publishes high-priority security events to support real-time risk assessment.

Examples include:

- Fraud Alert Raised
- Suspicious Login Detected
- High Risk Transaction Identified
- Velocity Threshold Exceeded
- Merchant Risk Updated
- Device Reputation Changed
- Account Takeover Suspected

Fraud events may trigger automated workflows including transaction holds, customer notifications, and security investigations.

---

## Event Producers

Primary event producers include:

| Producer | Published Events |
|----------|------------------|
| Mercury Payments | Payment lifecycle events |
| Orion Identity | Authentication events |
| Merchant Registry | Merchant onboarding events |
| Nexus Portal | Customer activity events |
| Token Vault | Secret rotation events |
| Fraud Platform | Risk assessment events |

Each producer is responsible for event schema versioning and payload validation.

---

## Event Consumers

Typical event consumers include:

- Atlas Analytics
- Notification Services
- Audit Services
- Compliance Reporting
- Fraud Detection Platform
- Customer Relationship Management
- Enterprise Monitoring Platform

Consumers should process events independently without introducing direct dependencies on other subscribers.

---

## Retry Strategy

Transient processing failures are automatically retried using an exponential backoff policy.

Standard retry configuration:

- Initial retry after 30 seconds
- Maximum of five retry attempts
- Progressive retry intervals
- Idempotent event processing required
- Retry metrics reported to monitoring dashboards

Events exceeding retry thresholds are redirected to the Dead-Letter Queue.

---

## Dead-Letter Queue (DLQ) Handling

Messages are routed to the Dead-Letter Queue when:

- Maximum retry attempts are exceeded
- Payload validation fails
- Consumer processing repeatedly fails
- Unsupported event versions are detected

DLQ processing includes:

1. Root cause investigation
2. Payload validation
3. Consumer remediation
4. Event replay (where appropriate)
5. Incident creation for recurring failures

Operational handling procedures are documented in **../operations/operational-runbooks.md**.

---

## Security Considerations

Enterprise events must comply with NovaBank security policies.

Requirements include:

- TLS encryption for event transport
- Schema validation before publishing
- Digitally authenticated producers
- No plaintext credentials or secrets
- No payment card data in event payloads
- Correlation IDs for auditability
- Event retention aligned with compliance policies

Security-related events are monitored continuously by Security Operations.

---

## Monitoring Requirements

The Enterprise Event Bus is monitored for:

- Event throughput
- Processing latency
- Consumer lag
- Retry volume
- Dead-letter queue growth
- Message delivery success
- Event publishing failures
- Queue utilization

Operational metrics are reviewed through the enterprise monitoring dashboards defined in **../operations/monitoring-observability.md**.

---

## Best Practices

- Publish business events only after successful transaction completion.
- Design event payloads to be immutable.
- Ensure consumers are idempotent.
- Maintain backward compatibility during schema evolution.
- Avoid synchronous dependencies between producers and consumers.
- Monitor retry rates and DLQ growth continuously.
- Version event schemas without breaking existing integrations.

---

## References

- payment-api.md
- identity-api.md
- integration-guidelines.md
- ../products/mercury-payments.md
- ../products/orion-identity.md
- ../operations/incident-management.md
- ../operations/monitoring-observability.md
- ../operations/operational-runbooks.md