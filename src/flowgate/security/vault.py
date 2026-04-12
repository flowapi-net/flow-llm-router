"""Just-In-Time decryption vault for API keys.

Only the Fernet key lives in memory. API key plaintext is decrypted on each
LLM call and discarded immediately after use.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_PBKDF2_ITERATIONS = 600_000


class VaultError(Exception):
    """Base exception for vault operations."""


class VaultNotInitializedError(VaultError):
    """Raised when vault operations are attempted before initialization."""


class InvalidPasswordError(VaultError):
    """Raised when the master password is incorrect."""


class Vault:
    """JIT-decryption API key vault.

    Memory footprint: only the Fernet key (32 bytes) and an encrypted-text
    cache (ciphertext is safe to hold). Plaintext API keys exist only as
    short-lived local variables in ``get_key()``.
    """

    def __init__(self) -> None:
        self._fernet: Fernet | None = None
        self._encrypted_cache: dict[str, str] = {}

    @property
    def is_initialized(self) -> bool:
        return self._fernet is not None

    def initialize(self, master_password: str, salt: bytes | None = None) -> bytes:
        """Derive the Fernet key from *master_password* via PBKDF2.

        Called once at startup (~0.3-0.5 s).  Returns the salt (generated if
        *salt* is ``None``).
        """
        if salt is None:
            salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_PBKDF2_ITERATIONS,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
        self._fernet = Fernet(key)
        return salt

    def _require_init(self) -> Fernet:
        if self._fernet is None:
            raise VaultNotInitializedError("Vault has not been initialized with a master password")
        return self._fernet

    def encrypt_key(self, plaintext_key: str) -> str:
        """Encrypt an API key and return the base-64 ciphertext."""
        return self._require_init().encrypt(plaintext_key.encode()).decode()

    def decrypt_key(self, encrypted_key: str) -> str:
        """Decrypt a single ciphertext and return the plaintext API key.

        Callers should use the return value immediately and avoid storing it in
        long-lived data structures.
        """
        try:
            return self._require_init().decrypt(encrypted_key.encode()).decode()
        except InvalidToken as exc:
            raise VaultError("Decryption failed – wrong master password or corrupted data") from exc

    def load_encrypted_cache(self, provider_keys: list) -> None:
        """Populate the in-memory ciphertext cache from DB records.

        Only *enabled* keys are loaded.  No decryption happens here.
        """
        self._encrypted_cache = {}
        for pk in provider_keys:
            if pk.enabled:
                self._encrypted_cache[pk.provider] = pk.encrypted_key

    def get_key(self, provider: str) -> str | None:
        """JIT decrypt: return plaintext API key for *provider*.

        ~0.01 ms (AES decrypt).  The returned string should be passed directly
        to ``litellm.acompletion(api_key=...)`` and not stored.
        """
        encrypted = self._encrypted_cache.get(provider)
        if encrypted is None:
            return None
        return self.decrypt_key(encrypted)

    def add_to_cache(self, provider: str, encrypted_key: str) -> None:
        """Insert or replace a ciphertext entry at runtime."""
        self._encrypted_cache[provider] = encrypted_key

    def remove_from_cache(self, provider: str) -> None:
        """Remove a provider's ciphertext from the runtime cache."""
        self._encrypted_cache.pop(provider, None)

    @staticmethod
    def hash_password(password: str) -> str:
        """SHA-256 hash of *password* – used **only** for verification, not encryption."""
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def mask_key(key: str) -> str:
        """Return a masked representation like ``sk-...abcd``."""
        if len(key) <= 8:
            return "****"
        return key[:3] + "..." + key[-4:]
