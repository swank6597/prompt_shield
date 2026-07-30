knowledge/
└── data/
    └── enterprise-data-glossary.md

---
title: Enterprise Data Glossary
version: 1.0
owner: Enterprise Data Governance
business-unit: Data & Information Management
classification: Internal
status: Approved
review-cycle: Annual
related-documents:
  - data-classification.md
  - customer-data-model.md
  - data-retention-policy.md
  - ../products/mercury-payments.md
  - ../products/orion-identity.md
  - ../products/merchant-registry.md
  - ../apis/payment-api.md
  - ../apis/identity-api.md
---

# Enterprise Data Glossary

## Purpose

This glossary establishes standardized business terminology used across NovaBank Financial Technologies. Consistent definitions enable effective communication between engineering, operations, product management, security, compliance, analytics, and business teams while ensuring uniform interpretation of enterprise documentation and system design.

The glossary serves as the authoritative reference for commonly used business and technical terms across the Enterprise Context Intelligence (ECI) knowledge base.

---

## Payment Terminology

| Term | Definition |
|------|------------|
| Payment | A financial transaction initiated by a customer through an approved payment channel. |
| Payment Authorization | Validation confirming that a payment may proceed based on business and security rules. |
| Settlement | Final transfer of funds between participating financial institutions. |
| Refund | Reversal of a previously completed payment transaction. |
| Merchant | A registered business authorized to accept payments through Mercury Payments. |
| Transaction ID | Enterprise-generated identifier uniquely representing a payment transaction. |
| Payment Gateway | Service responsible for securely routing payment requests to external financial networks. |

---

## Identity Terminology

| Term | Definition |
|------|------------|
| Customer Identity | Enterprise representation of a customer managed by Orion Identity. |
| Authentication | Verification of a user's identity before granting system access. |
| Authorization | Evaluation of permissions to determine allowable actions after authentication. |
| Access Token | Short-lived credential used to authorize API requests. |
| Refresh Token | Credential used to obtain a new access token without re-authentication. |
| Multi-Factor Authentication (MFA) | Authentication process requiring multiple independent verification factors. |
| Role-Based Access Control (RBAC) | Authorization model that grants permissions based on assigned business roles. |

---

## Fraud Terminology

| Term | Definition |
|------|------------|
| Fraud Alert | Notification indicating potentially suspicious activity requiring investigation. |
| Risk Score | Numerical assessment representing the likelihood of fraudulent behavior. |
| Anomaly Detection | Identification of activities that deviate from established behavioral patterns. |
| Suspicious Activity | Transaction or event requiring additional validation before approval. |
| Case Management | Workflow used by fraud analysts to investigate and resolve alerts. |
| Device Fingerprint | Unique device characteristics used for fraud detection and identity verification. |

---

## Analytics Terminology

| Term | Definition |
|------|------------|
| KPI | Key Performance Indicator used to measure business or operational performance. |
| Dashboard | Visual representation of operational or business metrics. |
| Data Pipeline | Automated workflow that collects, transforms, and distributes enterprise data. |
| Event Stream | Continuous sequence of business events exchanged between enterprise systems. |
| Operational Metric | Measurement used to evaluate application health, availability, or performance. |
| Business Intelligence | Reporting and analytical capabilities supporting enterprise decision-making. |

---

## Internal Abbreviations

| Abbreviation | Meaning |
|--------------|---------|
| ECI | Enterprise Context Intelligence |
| API | Application Programming Interface |
| CI/CD | Continuous Integration / Continuous Delivery |
| CAB | Change Advisory Board |
| RCA | Root Cause Analysis |
| RPO | Recovery Point Objective |
| RTO | Recovery Time Objective |
| SLA | Service Level Agreement |
| SLO | Service Level Objective |
| PII | Personally Identifiable Information |
| MFA | Multi-Factor Authentication |
| RBAC | Role-Based Access Control |
| SBOM | Software Bill of Materials |
| SAST | Static Application Security Testing |
| SCA | Software Composition Analysis |

---

## Governance

Enterprise terminology shall remain consistent across engineering documentation, architecture diagrams, API specifications, operational runbooks, monitoring dashboards, and business reports. New business terms must be reviewed and approved by Enterprise Data Governance before adoption within official documentation.

Business owners are responsible for maintaining accurate terminology within their respective domains, while Engineering and Product teams shall reference this glossary when producing technical documentation.

---

## References

- data-classification.md
- customer-data-model.md
- data-retention-policy.md
- ../products/mercury-payments.md
- ../products/orion-identity.md
- ../products/merchant-registry.md
- ../apis/payment-api.md
- ../apis/identity-api.md
- ../operations/monitoring-observability.md