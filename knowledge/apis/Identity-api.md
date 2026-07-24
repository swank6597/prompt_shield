---
title: Identity API
version: 1.0
owner: Identity Engineering
business-unit: Identity & Access Management
classification: Restricted
status: Approved
review-cycle: Quarterly
related-documents:
  - ../products/orion-identity.md
  - payment-api.md
  - event-catalog.md
  - integration-guidelines.md
  - ../operations/incident-management.md
  - ../operations/monitoring-observability.md
---

# Identity API

## Purpose

The Identity API provides centralized authentication, authorization, identity lifecycle management, and token services for enterprise applications across NovaBank Financial Technologies. Built on the Orion Identity platform, it enables secure access to customer-facing applications, internal services, APIs, and partner integrations while enforcing enterprise security policies and regulatory compliance.

---

## Business Overview

The Identity API serves as the enterprise Identity Provider (IdP) for Digital Banking, Mercury Payments, Nexus Portal, Atlas Analytics, Merchant Registry, and Token Vault. It supports Single Sign-On (SSO), OAuth 2.0, OpenID Connect (OIDC), Multi-Factor Authentication (MFA), and service-to-service authentication.

All applications consuming enterprise APIs must authenticate through the Identity API before accessing protected resources. Authentication events are published to the Enterprise Event Bus for auditing and security monitoring.

---

## OAuth2 / OpenID Connect Overview

The Identity API implements OAuth 2.0 and OpenID Connect (OIDC) standards to provide secure authentication and delegated authorization.

Supported grant types include:

- Authorization Code
- Client Credentials
- Refresh Token

Supported authentication capabilities include:

- Single Sign-On (SSO)
- Multi-Factor Authentication (MFA)
- Role-Based Access Control (RBAC)
- Service-to-Service Authentication
- JSON Web Tokens (JWT)

OIDC is used to establish authenticated user identity, while OAuth 2.0 governs authorization to protected APIs.

---

## Authentication and Authorization Flow

The standard authentication flow consists of the following stages:

1. Client application redirects the user to Orion Identity.
2. User authentication is performed using enterprise credentials and MFA (when required).
3. Orion Identity validates credentials and applicable access policies.
4. Authorization code is issued to the client application.
5. The client exchanges the authorization code for access and refresh tokens.
6. The client invokes protected APIs using the access token.
7. APIs validate token signature, expiration, issuer, audience, and assigned scopes before processing the request.

Service-to-service integrations use the Client Credentials grant type with predefined application scopes.

---

## Token Lifecycle

The Identity API manages the complete lifecycle of OAuth tokens.

### Access Token

- Short-lived bearer token
- Used to access protected resources
- Digitally signed using enterprise signing keys
- Contains user identity, scopes, and expiration metadata

### Refresh Token

- Long-lived token
- Used to obtain new access tokens
- Securely stored by approved client applications
- Revoked upon logout or security policy violation

### Token Revocation

Tokens may be revoked due to:

- User logout
- Credential reset
- Suspicious activity
- Administrative action
- Security incident

Revocation events are propagated immediately to all participating services.

---

## Core REST Endpoints

| Method | Endpoint | Description |
|---------|----------|-------------|
| GET | /oauth2/authorize | Authorization endpoint |
| POST | /oauth2/token | Access token issuance |
| POST | /oauth2/introspect | Token validation |
| POST | /oauth2/revoke | Token revocation |
| GET | /userinfo | Retrieve authenticated user profile |
| GET | /.well-known/openid-configuration | OIDC discovery metadata |
| GET | /jwks | Public signing keys |

---

## Sample Token Request

```http
POST /oauth2/token
Content-Type: application/x-www-form-urlencoded
```

```
grant_type=client_credentials
client_id=payment-service
client_secret=********
scope=payments.write
```

---

## Sample Token Response

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "payments.write"
}
```

---

## Error Responses

The Identity API returns standardized OAuth-compliant responses.

| Status | Description |
|---------|-------------|
| 400 | Invalid request |
| 401 | Authentication failed |
| 403 | Insufficient privileges |
| 404 | Resource not found |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

Example Response

```json
{
  "error": "invalid_token",
  "error_description": "Access token has expired."
}
```

---

## Security Considerations

The Identity API implements enterprise security controls including:

- OAuth 2.0 and OpenID Connect compliance
- Mandatory TLS 1.2 or higher
- JWT signature validation
- Role-Based Access Control (RBAC)
- Multi-Factor Authentication
- Certificate-based trust
- Token encryption and signing
- Session timeout enforcement
- Audit logging for authentication events

Authentication credentials, signing keys, refresh tokens, and client secrets must never be stored or transmitted in plaintext. Secret management is provided through the Token Vault platform.

---

## Dependencies

The Identity API integrates with the following enterprise platforms:

- Orion Identity
- Token Vault
- Enterprise Directory Services
- Enterprise Event Bus
- Security Monitoring Platform
- API Gateway
- Payment API
- Monitoring and Observability Platform

Authentication failures and security-related incidents follow the operational procedures documented in:

- **../operations/incident-management.md**
- **../operations/production-support.md**
- **../operations/monitoring-observability.md**

---

## References

- ../products/orion-identity.md
- payment-api.md
- event-catalog.md
- integration-guidelines.md
- ../operations/incident-management.md
- ../operations/production-support.md
- ../operations/monitoring-observability.md