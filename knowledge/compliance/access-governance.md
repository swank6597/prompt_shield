---
title: Access Governance Standard
version: 1.0
owner: Identity & Access Management
business-unit: Governance, Risk & Compliance
classification: Confidential
status: Approved
review-cycle: Annual
related-documents:
  - regulatory-compliance.md
  - audit-guidelines.md
  - exception-management.md
  - ../engineering/secure-coding-standards.md
  - ../data/data-classification.md
  - ../apis/identity-api.md
  - ../products/orion-identity.md
---

# Access Governance Standard

## Purpose

This document defines the enterprise access governance framework for NovaBank Financial Technologies. The standard establishes requirements for provisioning, maintaining, reviewing, and revoking logical access to enterprise systems while ensuring access aligns with business responsibilities, regulatory obligations, and information security policies.

Access governance supports secure operations across engineering, payment processing, identity management, customer services, and corporate business functions.

---

## Scope

This standard applies to:

- Employees
- Contractors
- Third-party service providers
- Enterprise applications
- Cloud platforms
- Development environments
- Production systems
- Administrative accounts
- Service accounts

All logical access must follow this governance standard regardless of hosting environment.

---

## Role-Based Access Model

NovaBank implements a centralized **Role-Based Access Control (RBAC)** model managed through **Orion Identity**.

Access is granted based on approved business roles rather than individual user requests.

Typical role categories include:

| Role Category | Example Access |
|--------------|----------------|
| Business User | Customer and operational applications |
| Software Engineer | Development environments and source repositories |
| DevOps Engineer | CI/CD platforms and deployment infrastructure |
| Security Administrator | Security monitoring and incident response systems |
| Database Administrator | Managed database platforms |
| Auditor | Read-only access to approved audit evidence |

Role definitions are maintained by Identity & Access Management (IAM) in partnership with business owners.

---

## Least Privilege

Access shall follow the Principle of Least Privilege.

Requirements include:

- Grant only the minimum permissions required.
- Separate administrative and standard user accounts.
- Restrict production access to authorized personnel.
- Use temporary privileged access where feasible.
- Remove unnecessary permissions promptly.
- Review privileged roles regularly.

Privilege accumulation through multiple role assignments should be avoided.

---

## Joiner / Mover / Leaver Process

User lifecycle events shall follow standardized identity governance procedures.

### Joiner

- Verify employment authorization.
- Assign approved business role.
- Provision required applications.
- Enable Multi-Factor Authentication (MFA).
- Record provisioning activities.

### Mover

- Review new business responsibilities.
- Remove obsolete permissions.
- Assign new approved role.
- Update group memberships.
- Validate segregation of duties.

### Leaver

- Disable user accounts immediately upon termination.
- Revoke privileged access.
- Remove remote access.
- Revoke API credentials and authentication tokens.
- Archive audit records.

Access changes should be completed within defined service level objectives.

---

## Privileged Access Reviews

Privileged accounts require enhanced governance.

Review activities include:

- Quarterly access reviews
- Administrative account verification
- Shared account validation
- Service account ownership confirmation
- Emergency access usage review
- Privileged session monitoring
- Segregation of duties assessment

Inactive privileged accounts shall be disabled or removed.

---

## Access Certification

Business managers shall periodically certify user access.

Certification activities verify:

- Business justification
- Role appropriateness
- Least privilege compliance
- Manager approval
- System ownership validation
- Removal of unnecessary permissions

Certification campaigns are coordinated by the Identity & Access Management team and tracked through enterprise governance processes.

---

## Responsibilities

| Role | Responsibility |
|------|----------------|
| Identity & Access Management | Maintain RBAC model and provisioning processes |
| Business Managers | Approve and certify user access |
| Information Security | Monitor privileged access and policy compliance |
| System Owners | Define application-specific roles |
| Internal Audit | Validate governance controls |

---

## Compliance

Compliance with this standard is verified through periodic access reviews, certification campaigns, audit activities, and continuous monitoring. Exceptions require documented approval through the Enterprise Exception Management process.

---

## References

- regulatory-compliance.md
- audit-guidelines.md
- exception-management.md
- ../engineering/secure-coding-standards.md
- ../data/data-classification.md
- ../apis/identity-api.md
- ../products/orion-identity.md
- ../operations/incident-management.md