# service.py
# Business logic for authentication: user login + lockout tracking, device
# enrollment/resolution/revocation, and audit-log writes. routes.py should
# stay thin and delegate everything here - see specs/authentication/design.md.

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import AUTH_LOGIN_MAX_ATTEMPTS, AUTH_LOGIN_LOCKOUT_MINUTES, AUTH_MIN_PASSWORD_LENGTH

from .db import get_connection
from .security import hash_secret, verify_secret, generate_api_key


@dataclass
class User:
    id: int
    username: str
    password_hash: str
    role: str
    is_active: bool
    failed_attempts: int
    locked_until: Optional[str]


@dataclass
class Device:
    id: int
    label: str
    key_hash: str
    owner_user_id: Optional[int]
    created_at: str
    last_used_at: Optional[str]
    revoked_at: Optional[str]


class AccountLockedError(Exception):
    """Raised by authenticate_user() when the account is currently locked
    out. Callers (routes.py) should still respond with the same generic 401
    as a bad-password attempt (see design.md's error-handling table) - this
    exception exists only so the caller can choose not to re-increment the
    lockout counter while it's already locked, not to change the HTTP
    response shape."""


def _row_to_user(row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        role=row["role"],
        is_active=bool(row["is_active"]),
        failed_attempts=row["failed_attempts"],
        locked_until=row["locked_until"],
    )


def _row_to_device(row) -> Device:
    return Device(
        id=row["id"],
        label=row["label"],
        key_hash=row["key_hash"],
        owner_user_id=row["owner_user_id"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        revoked_at=row["revoked_at"],
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(conn, action: str, actor_user_id: Optional[int] = None,
           actor_label: Optional[str] = None, target: Optional[str] = None,
           success: bool = True, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO auth_audit_log "
        "(actor_user_id, actor_label, action, target, success, detail) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (actor_user_id, actor_label, action, target, 1 if success else 0, detail),
    )


def record_audit_event(action: str, actor_user_id: Optional[int] = None,
                        actor_label: Optional[str] = None, target: Optional[str] = None,
                        success: bool = True, detail: str = "") -> None:
    """Standalone audit write for callers that aren't already inside one of
    the transactions below (e.g. routes.py logging a logout)."""
    conn = get_connection()
    try:
        _audit(conn, action, actor_user_id, actor_label, target, success, detail)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(username: str, password: str, role: str) -> User:
    if len(password) < AUTH_MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {AUTH_MIN_PASSWORD_LENGTH} characters")

    conn = get_connection()
    try:
        password_hash = hash_secret(password)
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_user(row)
    finally:
        conn.close()


def get_user_by_username(username: str) -> Optional[User]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[User]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    Returns the User on success, None on unknown username or wrong
    password. Raises AccountLockedError if the account is currently within
    its lockout window (Requirement 5.4) - even a correct password is
    rejected in that state.
    """
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            _audit(conn, "login_failure", actor_label=username, target=username,
                   success=False, detail="unknown username")
            conn.commit()
            return None

        user = _row_to_user(row)

        if user.locked_until:
            locked_until = datetime.fromisoformat(user.locked_until)
            if datetime.now(timezone.utc) < locked_until:
                _audit(conn, "login_failure", actor_user_id=user.id, actor_label=username,
                       target=username, success=False, detail="account locked")
                conn.commit()
                raise AccountLockedError()
            # Lockout window elapsed - fall through and evaluate normally.

        if not user.is_active or not verify_secret(password, user.password_hash):
            new_failed = user.failed_attempts + 1
            locked_until_value = None
            action = "login_failure"
            if new_failed >= AUTH_LOGIN_MAX_ATTEMPTS:
                locked_until_value = (
                    datetime.now(timezone.utc) + timedelta(minutes=AUTH_LOGIN_LOCKOUT_MINUTES)
                ).isoformat()
                action = "account_locked"
            conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                (new_failed, locked_until_value, user.id),
            )
            _audit(conn, action, actor_user_id=user.id, actor_label=username, target=username,
                   success=False, detail=f"failed_attempts={new_failed}")
            conn.commit()
            return None

        conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
            (user.id,),
        )
        _audit(conn, "login_success", actor_user_id=user.id, actor_label=username,
               target=username, success=True)
        conn.commit()
        user.failed_attempts = 0
        user.locked_until = None
        return user
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

def create_device(label: str, owner_user_id: Optional[int] = None) -> tuple[Device, str]:
    """Returns (device, plaintext_api_key). The plaintext key exists only in
    this return value and the HTTP response that carries it - it is never
    persisted or logged."""
    conn = get_connection()
    try:
        plaintext_key = generate_api_key()
        key_hash = hash_secret(plaintext_key)
        cur = conn.execute(
            "INSERT INTO devices (label, key_hash, owner_user_id) VALUES (?, ?, ?)",
            (label, key_hash, owner_user_id),
        )
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (cur.lastrowid,)).fetchone()
        device = _row_to_device(row)
        _audit(conn, "device_enroll", actor_user_id=owner_user_id, actor_label=label,
               target=str(device.id), success=True, detail=f"label={label}")
        conn.commit()
        return device, plaintext_key
    finally:
        conn.close()


def resolve_device(api_key: str) -> Optional[Device]:
    """
    Validates an API key against active (non-revoked) devices.

    NOTE: this is an O(n) bcrypt-compare loop, not an indexed lookup -
    bcrypt hashes can't be looked up by index. Fine at this project's scale
    (see specs/authentication/design.md's "Known limitation"); if device
    count grows large, switch the *lookup* key to a fast indexable hash
    (e.g. SHA-256) while keeping bcrypt for password storage.
    """
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM devices WHERE revoked_at IS NULL").fetchall()
        for row in rows:
            device = _row_to_device(row)
            if verify_secret(api_key, device.key_hash):
                conn.execute(
                    "UPDATE devices SET last_used_at = ? WHERE id = ?",
                    (_now_iso(), device.id),
                )
                conn.commit()
                device.last_used_at = _now_iso()
                return device
        return None
    finally:
        conn.close()


def revoke_device(device_id: int, acting_admin: User) -> bool:
    """Returns False if the device doesn't exist or is already revoked."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        if row is None or row["revoked_at"] is not None:
            return False
        conn.execute(
            "UPDATE devices SET revoked_at = ? WHERE id = ?",
            (_now_iso(), device_id),
        )
        _audit(conn, "device_revoke", actor_user_id=acting_admin.id,
               actor_label=acting_admin.username, target=str(device_id), success=True)
        conn.commit()
        return True
    finally:
        conn.close()


def list_devices() -> list[Device]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM devices ORDER BY created_at DESC").fetchall()
        return [_row_to_device(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Audit log reads
# ---------------------------------------------------------------------------

def get_audit_log(limit: int = 50, offset: int = 0,
                   actor_user_id: Optional[int] = None,
                   action: Optional[str] = None) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        clauses = []
        params: list = []
        if actor_user_id is not None:
            clauses.append("actor_user_id = ?")
            params.append(actor_user_id)
        if action is not None:
            clauses.append("action = ?")
            params.append(action)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        total = conn.execute(
            f"SELECT COUNT(*) as c FROM auth_audit_log {where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM auth_audit_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [dict(r) for r in rows], total
    finally:
        conn.close()
