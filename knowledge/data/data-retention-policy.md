title: Data Retention Policy
version: 1.0
owner: Enterprise Data Governance
business-unit: Data & Information Management
classification: Confidential
status: Approved
review-cycle: Annual
related-documents:
  - data-classification.md
  - customer-data-model.md
  - enterprise-data-glossary.md
  - ../operations/backup-restore.md
  - ../operations/disaster-recovery.md
  - ../engineering/secure-coding-standards.md
---

# Data Retention Policy

## Purpose

This policy establishes the enterprise requirements for retaining, archiving, and securely disposing of business and customer data across NovaBank Financial Technologies. The objective is to ensure information remains available for operational, legal, regulatory, and audit purposes while minimizing unnecessary storage of sensitive data.

Retention requirements apply throughout the complete information lifecycle and support enterprise governance standards.

---

## Scope

This policy applies to all structured and unstructured data managed by NovaBank, including customer records, payment transactions, identity information, application logs, audit records, source code repositories, operational documentation, backups, and analytics datasets.

Business units are responsible for ensuring their information assets comply with approved retention schedules.

---

## Retention Periods

The following minimum retention periods apply unless superseded by regulatory or contractual obligations.

| Data Category | Minimum Retention |
|--------------|-------------------|
| Customer Profiles | 7 Years |
| Payment Transactions | 7 Years |
| Merchant Records | 7 Years |
| Identity & Authentication Logs | 2 Years |
| Security Audit Logs | 5 Years |
| Operational Monitoring Logs | 1 Year |
| Incident & Problem Records | 5 Years |
| Source Code & Release Artifacts | Lifetime of supported product plus 3 Years |
| Engineering Documentation | Until superseded plus 2 Years |
| Backup Metadata | 1 Year |

Data Owners may request extended retention where justified by business or legal requirements.

---

## Archival Policy

Information no longer required for active business operations shall be moved to approved archival storage.

Archival requirements include:

- Encryption at rest
- Immutable storage where applicable
- Restricted administrative access
- Integrity verification
- Metadata preservation
- Searchable indexing for authorized retrieval
- Periodic archive validation

Archived information remains subject to enterprise access control and audit requirements.

---

## Secure Deletion

When retention obligations expire, data shall be permanently removed using approved destruction methods.

Secure deletion requirements include:

- Permanent removal from primary storage
- Deletion from replicated environments when retention expires
- Cryptographic erasure where supported
- Destruction verification
- Audit logging of deletion activities
- Disposal approval by the Data Owner

Sensitive information must not remain recoverable after disposal.

---

## Compliance Considerations

Retention activities shall support enterprise regulatory and governance obligations.

Compliance objectives include:

- Protection of customer information
- Demonstrable audit evidence
- Controlled access to historical records
- Consistent enterprise retention practices
- Preservation of information required for legal investigations
- Controlled disposal of obsolete information

Exceptions require documented approval from Enterprise Data Governance and Information Security.

---

## Backup Relationship

Operational backups are designed for disaster recovery and business continuity, not long-term archival.

Backups shall:

- Follow the Backup and Restore Standard
- Be encrypted during storage and transmission
- Support defined Recovery Point Objectives (RPO)
- Be periodically tested for successful restoration
- Respect approved retention schedules
- Be securely destroyed after expiration

Retention periods for archived business records are independent of backup retention schedules.

---

## Audit Requirements

Retention activities shall be fully auditable.

The following events must be recorded:

- Data creation
- Archival activities
- Restoration requests
- Retention policy exceptions
- Secure deletion events
- Administrative access
- Retention schedule modifications

Audit records shall be protected from unauthorized modification and retained according to enterprise audit requirements.

---

## Responsibilities

| Role | Responsibility |
|------|----------------|
| Data Owner | Define retention requirements |
| Enterprise Data Governance | Maintain retention policy |
| Information Security | Verify secure handling and disposal |
| Infrastructure Operations | Manage backup and archival platforms |
| Internal Audit | Validate compliance and governance controls |

---

## References

- data-classification.md
- customer-data-model.md
- enterprise-data-glossary.md
- ../operations/backup-restore.md
- ../operations/disaster-recovery.md
- ../engineering/secure-coding-standards.md
```