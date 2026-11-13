"""Security Primitives: Argon2id Hashing, Token Generation, and CSRF Protection

Single Organization Edition: Physio One Clinic.
Supports Argon2id natively with high-security standard library fallback
when Windows AppLocker/WDAC blocks external CFFI DLLs.
"""
import base64
import hashlib
import hmac
import secrets
import time
from typing import Optional, Tuple, Dict

# Attempt to load argon2-cffi; if blocked by host policy, use scrypt fallback
_has_argon2 = False
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
    _ph = PasswordHasher(
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        salt_len=16,
    )
    _has_argon2 = True
except (ImportError, Exception):
    _has_argon2 = False


def hash_password(plain_password: str) -> str:
    """Hash a password using Argon2id (or high-security scrypt fallback if CFFI is blocked)."""
    if _has_argon2:
        return _ph.hash(plain_password)
    
    # Secure scrypt fallback (RFC 7914 compliant, standard library)
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(
        plain_password.encode("utf-8"),
        salt=bytes.fromhex(salt),
        n=16384,
        r=8,
        p=1,
        maxmem=64 * 1024 * 1024,
    )
    return f"$scrypt$n=16384,r=8,p=1${salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against an Argon2id or scrypt hash."""
    if not plain_password or not hashed_password:
        return False

    if hashed_password.startswith("$argon2"):
        if not _has_argon2:
            return False
        try:
            return _ph.verify(hashed_password, plain_password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    if hashed_password.startswith("$scrypt$"):
        try:
            parts = hashed_password.split("$")
            # format: ['', 'scrypt', 'n=16384,r=8,p=1', '<salt>', '<hex_key>']
            salt_hex = parts[3]
            expected_key_hex = parts[4]
            computed_key = hashlib.scrypt(
                plain_password.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=16384,
                r=8,
                p=1,
                maxmem=64 * 1024 * 1024,
            )
            return hmac.compare_digest(computed_key.hex(), expected_key_hex)
        except Exception:
            return False

    return False


def generate_session_token() -> str:
    """Generate a high-entropy URL-safe session token (32 bytes = 256 bits)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Create a deterministic SHA-256 hash of a session token for secure database indexing.
    
    The plaintext token is only held by the client; the database stores only the hash.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_hex(32)


def verify_csrf_token(header_token: Optional[str], cookie_token: Optional[str]) -> bool:
    """Verify that the CSRF token in the request header matches the cookie token using constant time comparison."""
    if not header_token or not cookie_token:
        return False
    return hmac.compare_digest(header_token, cookie_token)


# In-memory sliding window rate limiter for login protection
# Maps IP or email to list of timestamps
class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, lockout_seconds: int = 600):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self.attempts: Dict[str, list] = {}
        self.lockouts: Dict[str, float] = {}

    def is_locked(self, identifier: str) -> Tuple[bool, int]:
        """Check if an identifier (e.g. IP or email) is locked out.
        Returns (is_locked, remaining_seconds).
        """
        now = time.time()
        lockout_expiry = self.lockouts.get(identifier, 0)
        if now < lockout_expiry:
            return True, int(lockout_expiry - now)
        return False, 0

    def record_attempt(self, identifier: str, success: bool):
        """Record a login attempt. If failed and threshold exceeded, lock out."""
        now = time.time()
        if success:
            self.attempts.pop(identifier, None)
            self.lockouts.pop(identifier, None)
            return

        # Prune old attempts
        window_start = now - self.window_seconds
        current_attempts = [ts for ts in self.attempts.get(identifier, []) if ts > window_start]
        current_attempts.append(now)
        self.attempts[identifier] = current_attempts

        if len(current_attempts) >= self.max_attempts:
            self.lockouts[identifier] = now + self.lockout_seconds
            self.attempts.pop(identifier, None)

    def reset(self):
        """Reset all rate limit tracking (useful for tests)."""
        self.attempts.clear()
        self.lockouts.clear()


login_rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=300, lockout_seconds=600)
