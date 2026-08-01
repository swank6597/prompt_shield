"""
Tests for backend/auth/ against specs/authentication/requirements.md.

Direct-import style (no FastAPI TestClient/httpx), consistent with this
repo's existing tests (see conftest.py) - security.py/service.py/
dependencies.py are called directly rather than through HTTP.
"""

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# security.py raises at import time if PROMPTSHIELD_AUTH_SECRET_KEY is unset -
# set it (and reload config, in case some earlier test already imported it
# with no key set) before anything under backend/auth/ is imported.
os.environ.setdefault("PROMPTSHIELD_AUTH_SECRET_KEY", "test-only-secret-key-do-not-use-in-prod")

import config  # noqa: E402
importlib.reload(config)

from auth import security, service  # noqa: E402
from auth.dependencies import (  # noqa: E402
    get_current_user,
    get_current_user_optional,
    require_api_key,
    require_role,
)


@pytest.fixture(autouse=True)
def temp_auth_db(tmp_path, monkeypatch):
    """Every test gets its own empty SQLite file, never the real auth.db."""
    monkeypatch.setattr(config, "AUTH_DB_PATH", str(tmp_path / "auth_test.db"))
    yield


def _make_user(username="alice", password="correct-horse", role="admin"):
    return service.create_user(username, password, role)


# ---------------------------------------------------------------------------
# security.py
# ---------------------------------------------------------------------------

def test_hash_and_verify_round_trip():
    hashed = security.hash_secret("hunter2")
    assert security.verify_secret("hunter2", hashed)


def test_verify_wrong_secret_fails():
    hashed = security.hash_secret("hunter2")
    assert not security.verify_secret("wrong-password", hashed)


def test_issue_and_decode_access_token():
    token = security.issue_access_token(user_id=42, role="admin")
    payload = security.decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_decode_expired_token_raises():
    payload = {
        "sub": "1",
        "role": "admin",
        "iat": datetime.now(timezone.utc) - timedelta(minutes=120),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=61),
    }
    expired_token = pyjwt.encode(payload, security.AUTH_SECRET_KEY, algorithm="HS256")
    with pytest.raises(pyjwt.PyJWTError):
        security.decode_access_token(expired_token)


def test_decode_tampered_token_raises():
    token = security.issue_access_token(user_id=1, role="admin")
    # Flip a character in the middle of the signature segment, not the last
    # character - a base64url char at a byte boundary can encode only a few
    # significant bits, so flipping THAT one can coincidentally decode back
    # to the same bytes and make this test flaky.
    mid = len(token) // 2
    tampered = token[:mid] + ("A" if token[mid] != "A" else "B") + token[mid + 1:]
    with pytest.raises(pyjwt.PyJWTError):
        security.decode_access_token(tampered)


def test_generate_api_key_is_unique_and_nontrivial():
    keys = {security.generate_api_key() for _ in range(20)}
    assert len(keys) == 20
    assert all(len(k) >= 32 for k in keys)


# ---------------------------------------------------------------------------
# service.py - users / login / lockout
# ---------------------------------------------------------------------------

def test_create_user_rejects_short_password():
    with pytest.raises(ValueError):
        service.create_user("bob", "short", "viewer")


def test_authenticate_user_correct_credentials_succeeds():
    _make_user("alice", "correct-horse", "admin")
    user = service.authenticate_user("alice", "correct-horse")
    assert user is not None
    assert user.username == "alice"
    assert user.failed_attempts == 0


def test_authenticate_user_wrong_password_fails():
    _make_user("alice", "correct-horse", "admin")
    assert service.authenticate_user("alice", "wrong-password") is None


def test_authenticate_user_unknown_username_fails():
    assert service.authenticate_user("nobody", "whatever") is None


def test_authenticate_user_generic_failure_does_not_distinguish_reason():
    # Requirement 5.2: bad username and bad password both just return None -
    # no distinguishing exception/return value leaks which one was wrong.
    _make_user("alice", "correct-horse", "admin")
    assert service.authenticate_user("alice", "wrong") is None
    assert service.authenticate_user("nobody", "wrong") is None


def test_lockout_after_max_attempts_rejects_even_correct_password():
    _make_user("alice", "correct-horse", "admin")

    for _ in range(config.AUTH_LOGIN_MAX_ATTEMPTS):
        assert service.authenticate_user("alice", "wrong-password") is None

    # Account is now locked - even the CORRECT password is rejected.
    with pytest.raises(service.AccountLockedError):
        service.authenticate_user("alice", "correct-horse")


def test_successful_login_resets_failed_attempts():
    _make_user("alice", "correct-horse", "admin")
    service.authenticate_user("alice", "wrong-password")
    service.authenticate_user("alice", "wrong-password")
    user = service.authenticate_user("alice", "correct-horse")
    assert user.failed_attempts == 0


# ---------------------------------------------------------------------------
# service.py - devices
# ---------------------------------------------------------------------------

def test_create_device_returns_working_plaintext_key():
    device, api_key = service.create_device("laptop-1")
    resolved = service.resolve_device(api_key)
    assert resolved is not None
    assert resolved.id == device.id


def test_resolve_device_rejects_unknown_key():
    assert service.resolve_device("not-a-real-key") is None


def test_revoked_device_key_no_longer_resolves():
    admin = _make_user("admin1", "correct-horse", "admin")
    device, api_key = service.create_device("laptop-1")

    assert service.resolve_device(api_key) is not None
    assert service.revoke_device(device.id, acting_admin=admin) is True
    assert service.resolve_device(api_key) is None


def test_revoke_nonexistent_device_returns_false():
    admin = _make_user("admin1", "correct-horse", "admin")
    assert service.revoke_device(999, acting_admin=admin) is False


def test_device_bound_to_owner_when_created_with_user():
    user = _make_user("alice", "correct-horse", "viewer")
    device, _ = service.create_device("alices-phone", owner_user_id=user.id)
    assert device.owner_user_id == user.id


# ---------------------------------------------------------------------------
# Requirement 7: admin actions are audited too, not exempt
# ---------------------------------------------------------------------------

def test_device_revoke_by_admin_is_recorded_with_admin_actor_id():
    admin = _make_user("root-admin", "correct-horse", "admin")
    device, _ = service.create_device("some-device")

    service.revoke_device(device.id, acting_admin=admin)

    entries, total = service.get_audit_log(action="device_revoke")
    assert total == 1
    assert entries[0]["actor_user_id"] == admin.id
    assert entries[0]["target"] == str(device.id)
    assert bool(entries[0]["success"]) is True


def test_login_attempts_are_audited_without_storing_password():
    _make_user("alice", "correct-horse", "admin")
    service.authenticate_user("alice", "wrong-password")
    service.authenticate_user("alice", "correct-horse")

    entries, total = service.get_audit_log()
    actions = [e["action"] for e in entries]
    assert "login_failure" in actions
    assert "login_success" in actions
    for entry in entries:
        assert "wrong-password" not in (entry["detail"] or "")
        assert "correct-horse" not in (entry["detail"] or "")


def test_device_enroll_is_audited():
    service.create_device("new-device")
    entries, total = service.get_audit_log(action="device_enroll")
    assert total == 1


# ---------------------------------------------------------------------------
# dependencies.py
# ---------------------------------------------------------------------------

def test_require_api_key_accepts_valid_key():
    _, api_key = service.create_device("laptop-1")
    device = require_api_key(x_api_key=api_key)
    assert device.label == "laptop-1"


def test_require_api_key_rejects_missing_key():
    with pytest.raises(HTTPException) as exc_info:
        require_api_key(x_api_key=None)
    assert exc_info.value.status_code == 401


def test_require_api_key_rejects_revoked_key():
    admin = _make_user("admin1", "correct-horse", "admin")
    device, api_key = service.create_device("laptop-1")
    service.revoke_device(device.id, acting_admin=admin)

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(x_api_key=api_key)
    assert exc_info.value.status_code == 401


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    """Mirrors what fastapi.security.HTTPBearer hands get_current_user in
    a real request, for direct-call tests (no TestClient/httpx)."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_get_current_user_rejects_missing_bearer_token():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(user=get_current_user_optional(credentials=None))
    assert exc_info.value.status_code == 401


def test_get_current_user_accepts_valid_token():
    user = _make_user("alice", "correct-horse", "viewer")
    token = security.issue_access_token(user.id, user.role)
    resolved = get_current_user(user=get_current_user_optional(credentials=_credentials(token)))
    assert resolved.username == "alice"


def test_get_current_user_optional_returns_none_for_expired_token():
    payload = {
        "sub": "1", "role": "admin",
        "iat": datetime.now(timezone.utc) - timedelta(minutes=120),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=61),
    }
    expired_token = pyjwt.encode(payload, security.AUTH_SECRET_KEY, algorithm="HS256")
    assert get_current_user_optional(credentials=_credentials(expired_token)) is None


def test_require_role_admin_rejects_viewer():
    viewer = _make_user("bob", "correct-horse", "viewer")
    token = security.issue_access_token(viewer.id, viewer.role)
    guard = require_role("admin")

    caller = get_current_user(user=get_current_user_optional(credentials=_credentials(token)))
    with pytest.raises(HTTPException) as exc_info:
        guard(user=caller)
    assert exc_info.value.status_code == 403


def test_require_role_admin_accepts_admin():
    admin = _make_user("root-admin", "correct-horse", "admin")
    token = security.issue_access_token(admin.id, admin.role)
    guard = require_role("admin")

    caller = get_current_user(user=get_current_user_optional(credentials=_credentials(token)))
    assert guard(user=caller).username == "root-admin"
