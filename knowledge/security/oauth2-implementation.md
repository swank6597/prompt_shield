# OAuth2 Implementation at NovaBank

## Overview

NovaBank's internal services authenticate against **Orion Identity**,
our internal identity provider, using a customized OAuth2
Authorization Code flow with PKCE. This document describes our
specific implementation, not the general OAuth2 specification.

## Our OAuth2 Flow

1. The client (e.g., Nexus Customer Portal) redirects the user to
   Orion Identity's `/authorize` endpoint, including a PKCE
   `code_challenge`.
2. Orion Identity authenticates the user and issues a short-lived
   `auth_code` (90 seconds) tied to the original `code_challenge`.
3. The client exchanges the `auth_code` at Orion's `/token` endpoint,
   presenting the PKCE `code_verifier`.
4. Orion Identity issues an access token (15 minute expiry) and a
   refresh token (7 day expiry, rotated on every use — reuse of a
   previous refresh token immediately revokes the entire token family).
5. Access tokens are JWTs signed with an internal RS256 key pair
   managed by the Security team's HSM; downstream services validate
   the signature locally rather than calling back to Orion Identity
   for every request.

## Deviations from the Public OAuth2 Spec

- Refresh token rotation with automatic family revocation on reuse
  (public spec treats rotation as optional; we treat it as mandatory).
- A shortened 90-second authorization code lifetime, tighter than the
  10-minute maximum recommended publicly, adopted after a security
  review of code-interception risk on shared corporate networks.
- Token validation is fully local (JWKS cached from Orion Identity)
  rather than a token-introspection call, for latency reasons.

## Key Internal Terms

- **Orion Identity** — NovaBank's internal identity provider.
- **Token family revocation** — internal refresh-token-reuse defense.
- **Orion HSM signing keys** — internal RS256 key pair for JWTs.

## Ownership

Owned by the Identity & Access team. Any change to token lifetimes or
rotation behavior requires Security sign-off.
