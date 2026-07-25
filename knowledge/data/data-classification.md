title: Data Classification Standard
version: 1.0
owner: Enterprise Data Governance
business-unit: Data & Information Management
classification: Confidential
status: Approved
review-cycle: Annual
related-documents:
  - customer-data-model.md
  - data-retention-policy.md
  - enterprise-data-glossary.md
  - ../engineering/secure-coding-standards.md
  - ../operations/backup-restore.md
  - ../products/token-vault.md
---

# Data Classification Standard

## Purpose

This document defines the enterprise data classification framework for NovaBank Financial Technologies. The standard establishes consistent requirements for identifying, handling, storing, transmitting, and protecting information assets throughout their lifecycle. Proper classification enables appropriate security controls while supporting regulatory compliance and operational efficiency.

---

## Scope

This standard applies to all structured and unstructured information created, processed, transmitted, or stored by NovaBank systems, employees, contractors, and approved third-party service providers.

The policy covers customer information, payment records, application data, operational documentation, source code, infrastructure configurations, analytics datasets, and business records.

---

## Data Classification Levels

NovaBank maintains three enterprise classification levels.

| Classification | Description | Typical Examples |
|----------------|-------------|------------------|
| **Internal** | Business information intended for employees and authorized partners. | Engineering documentation, operational procedures, architecture diagrams |
| **Confidential** | Sensitive business or customer information requiring controlled access. | Customer profiles, transaction records, internal financial reports, API specifications |
| **Restricted** | Highly sensitive information requiring the highest level of protection. | Encryption keys, authentication secrets, production credentials, Token Vault data, security incident investigations |

Information owners are responsible for assigning and periodically reviewing data classifications.

---

## Sensitive Data Categories

The following information is considered sensitive and must receive enhanced protection:

- Personally Identifiable Information (PII)
- Customer account information
- Payment card data
- Authentication credentials
- OAuth tokens
- Encryption keys
- API secrets
- Financial transaction records
- Fraud investigation records
- Internal risk assessments
- Security monitoring data

Sensitive data shall only be collected when required for legitimate business purposes.

---

## Handling Requirements

Data must be handled according to its assigned classification.

| Classification | Handling Requirements |
|----------------|----------------------|
| Internal | Accessible to authorized employees through approved enterprise systems |
| Confidential | Encrypted during transmission and stored using enterprise-approved security controls |
| Restricted | Strict access controls, encryption at rest and in transit, comprehensive audit logging, and privileged access management |

Copies of classified information must retain the original classification.

---

## Storage Guidelines

Enterprise information shall be stored only within approved platforms and repositories.

Requirements include:

- Encryption for Confidential and Restricted data
- Approved enterprise storage services
- Regular backup according to the Data Retention Policy
- Continuous monitoring for unauthorized access
- Periodic integrity verification
- Secure replication for disaster recovery

Local storage of Restricted information on unmanaged devices is prohibited.

---

## Access Controls

Access shall follow the Principle of Least Privilege.

Security controls include:

- Role-Based Access Control (RBAC)
- Multi-Factor Authentication (MFA)
- Periodic access reviews
- Privileged access monitoring
- Segregation of duties
- Just-in-time administrative access where applicable

Access permissions shall be reviewed at least quarterly or upon role changes.

---

## Sharing Restrictions

Information sharing must align with business need and approved governance processes.

Requirements include:

- Share only the minimum necessary information.
- Use enterprise-approved collaboration platforms.
- Encrypt Confidential and Restricted information during transmission.
- Obtain Data Owner approval before sharing Restricted information externally.
- Prohibit sharing production credentials or customer data through email, public repositories, or unauthorized messaging platforms.

Third-party data sharing requires contractual security and confidentiality obligations.

---

## Responsibilities

| Role | Responsibility |
|------|----------------|
| Data Owner | Assign and maintain data classification |
| Information Security | Define protection standards |
| Engineering Teams | Implement technical safeguards |
| Business Units | Ensure proper data handling |
| Internal Audit | Verify compliance with classification policies |

---

## Compliance

Compliance with this standard is verified through periodic audits, security assessments, access reviews, and monitoring activities. Non-compliance may result in corrective actions, security investigations, or disciplinary measures in accordance with enterprise information security policies.

---

## References

- customer-data-model.md
- data-retention-policy.md
- enterprise-data-glossary.md
- ../engineering/secure-coding-standards.md
- ../operations/backup-restore.md
- ../products/token-vault.md