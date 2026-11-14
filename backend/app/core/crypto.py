"""Cryptographic Secret Storage Utility

Single Organization Edition: Physio One.
Provides symmetric authenticated encryption (Fernet AES-128-CBC + HMAC-SHA256)
for WhatsApp provider tokens, secrets, and sensitive integration configuration.
"""
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from app.core.config import settings


def _get_fernet_key() -> bytes:
    """Derive a URL-safe base64 32-byte key from APP_SECRET or ENCRYPTION_KEY."""
    secret = getattr(settings, "ENCRYPTION_KEY", None) or settings.APP_SECRET
    # Create deterministic 32-byte digest
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext secret returning an encoded ciphertext string."""
    if not plaintext:
        return ""
    f = Fernet(_get_fernet_key())
    encrypted = f.encrypt(plaintext.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt an encrypted ciphertext string back to plaintext."""
    if not ciphertext:
        return ""
    try:
        f = Fernet(_get_fernet_key())
        decrypted = f.decrypt(ciphertext.encode("utf-8"))
        return decrypted.decode("utf-8")
    except Exception as e:
        raise ValueError("Failed to decrypt stored secret. Invalid key or corrupted data.") from e

