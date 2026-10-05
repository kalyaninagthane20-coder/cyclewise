"""Password hashing.

The first version of CycleWise stored unsalted SHA-256 hashes. Those are weak
(easy to brute-force with precomputed tables), so new passwords use Werkzeug's
salted scrypt hashes. Legacy hashes still log in, and are upgraded on next login.
"""
import hashlib
import hmac

from werkzeug.security import check_password_hash, generate_password_hash

_MODERN_PREFIXES = ("scrypt:", "pbkdf2:")


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    if stored_hash.startswith(_MODERN_PREFIXES):
        return check_password_hash(stored_hash, password)
    # legacy unsalted SHA-256 hex digest
    legacy = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(stored_hash, legacy)


def needs_upgrade(stored_hash: str) -> bool:
    """True when the stored hash is the legacy format and should be re-hashed."""
    return not stored_hash.startswith(_MODERN_PREFIXES)
