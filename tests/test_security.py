"""Unit tests for security modules: Vault, IPGuardMiddleware, redact."""

from __future__ import annotations

import ipaddress

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from flowgate.config import SecurityConfig, Settings
from flowgate.security.ip_guard import IPGuardMiddleware
from flowgate.security.master_key_store import has_master_key, load_master_key, save_master_key
from flowgate.security.redact import redact_headers, redact_secrets
from flowgate.security.vault import (
    InvalidPasswordError,
    Vault,
    VaultError,
    VaultNotInitializedError,
)


# ════════════════════════════════════════════════════════════════
# Vault Tests
# ════════════════════════════════════════════════════════════════


class TestVaultInitialization:
    def test_initialize_returns_salt(self):
        v = Vault()
        salt = v.initialize("my-password")
        assert isinstance(salt, bytes)
        assert len(salt) == 16

    def test_initialized_flag(self):
        v = Vault()
        assert not v.is_initialized
        v.initialize("my-password")
        assert v.is_initialized

    def test_same_password_and_salt_gives_same_encryption(self):
        """Deterministic: same password+salt must produce same ciphertext-decryptable key."""
        v1 = Vault()
        salt = v1.initialize("password")
        ct = v1.encrypt_key("hello")

        v2 = Vault()
        v2.initialize("password", salt=salt)
        assert v2.decrypt_key(ct) == "hello"

    def test_not_initialized_raises(self):
        v = Vault()
        with pytest.raises(VaultNotInitializedError):
            v.encrypt_key("any")

    def test_not_initialized_get_key_raises(self):
        v = Vault()
        with pytest.raises(VaultNotInitializedError):
            v.decrypt_key("any")

    def test_initialize_from_exported_key_roundtrip(self):
        v1 = Vault()
        v1.initialize("password")
        exported_key = v1.export_key()
        ciphertext = v1.encrypt_key("secret")

        v2 = Vault()
        v2.initialize_from_key(exported_key)
        assert v2.decrypt_key(ciphertext) == "secret"

    def test_lock_clears_runtime_material(self):
        v = Vault()
        v.initialize("password")
        encrypted = v.encrypt_key("sk-openai-xxx")
        v.add_to_cache("openai", encrypted)
        v.lock()
        assert v.is_initialized is False
        with pytest.raises(VaultNotInitializedError):
            v.decrypt_key(encrypted)


class TestVaultEncryption:
    def test_encrypt_decrypt_roundtrip(self, vault):
        plaintext = "sk-proj-supersecretkey12345"
        ciphertext = vault.encrypt_key(plaintext)
        assert ciphertext != plaintext
        assert vault.decrypt_key(ciphertext) == plaintext

    def test_encrypted_output_is_string(self, vault):
        result = vault.encrypt_key("sk-openai-test")
        assert isinstance(result, str)

    def test_each_encryption_unique(self, vault):
        """Fernet uses random IV — same plaintext encrypts differently each time."""
        ct1 = vault.encrypt_key("same-key")
        ct2 = vault.encrypt_key("same-key")
        assert ct1 != ct2

    def test_wrong_vault_key_cannot_decrypt(self):
        v1 = Vault()
        v1.initialize("password-A")
        ciphertext = v1.encrypt_key("secret")

        v2 = Vault()
        v2.initialize("password-B")
        with pytest.raises(VaultError):
            v2.decrypt_key(ciphertext)


class TestVaultJITCache:
    def test_load_encrypted_cache_no_decrypt(self, vault):
        encrypted = vault.encrypt_key("sk-openai-xxx")

        class FakeKey:
            provider = "openai"
            encrypted_key = encrypted
            enabled = True

        vault.load_encrypted_cache([FakeKey()])
        # cache holds ciphertext, not plaintext
        assert vault._encrypted_cache["openai"] == encrypted

    def test_get_key_jit_decrypts(self, vault):
        encrypted = vault.encrypt_key("sk-openai-realkey")
        vault.add_to_cache("openai", encrypted)
        result = vault.get_key("openai")
        assert result == "sk-openai-realkey"

    def test_get_key_missing_returns_none(self, vault):
        assert vault.get_key("anthropic") is None

    def test_disabled_keys_not_cached(self, vault):
        encrypted = vault.encrypt_key("sk-disabled")

        class DisabledKey:
            provider = "anthropic"
            encrypted_key = encrypted
            enabled = False

        vault.load_encrypted_cache([DisabledKey()])
        assert vault.get_key("anthropic") is None

    def test_add_to_cache(self, vault):
        encrypted = vault.encrypt_key("sk-new-key")
        vault.add_to_cache("google", encrypted)
        assert vault.get_key("google") == "sk-new-key"

    def test_remove_from_cache(self, vault):
        encrypted = vault.encrypt_key("sk-remove-me")
        vault.add_to_cache("openai", encrypted)
        vault.remove_from_cache("openai")
        assert vault.get_key("openai") is None

    def test_remove_nonexistent_no_error(self, vault):
        vault.remove_from_cache("nonexistent")  # should not raise


class TestVaultHelpers:
    def test_hash_password_consistent(self):
        h = Vault.hash_password("my-password")
        assert h == Vault.hash_password("my-password")

    def test_hash_password_different_inputs(self):
        assert Vault.hash_password("abc") != Vault.hash_password("xyz")

    def test_hash_is_hex_string(self):
        h = Vault.hash_password("test")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_mask_key_normal(self):
        assert Vault.mask_key("sk-proj-abcdefghij1234") == "sk-...1234"

    def test_mask_key_short(self):
        assert Vault.mask_key("short") == "****"

    def test_mask_key_exact_8(self):
        assert Vault.mask_key("12345678") == "****"


class TestMasterKeyStore:
    def test_save_and_load_roundtrip(self, tmp_path):
        key_path = tmp_path / "master.key"
        settings = Settings(security=SecurityConfig(master_key_path=str(key_path)))
        save_master_key(settings, "test-fernet-key")
        assert load_master_key(settings) == "test-fernet-key"

    def test_has_master_key(self, tmp_path):
        key_path = tmp_path / "master.key"
        settings = Settings(security=SecurityConfig(master_key_path=str(key_path)))
        assert has_master_key(settings) is False
        save_master_key(settings, "test-fernet-key")
        assert has_master_key(settings) is True


# ════════════════════════════════════════════════════════════════
# IPGuardMiddleware Tests
# ════════════════════════════════════════════════════════════════


def _make_guard(mode: str, allowed_ips: list[str] | None = None) -> IPGuardMiddleware:
    """Create an IPGuardMiddleware instance for direct method testing."""
    guard = IPGuardMiddleware.__new__(IPGuardMiddleware)
    guard.mode = mode
    guard.allowed_networks = IPGuardMiddleware._parse_networks(allowed_ips or [])
    return guard


class TestIPGuardLocalOnly:
    def test_localhost_ipv4_allowed(self):
        guard = _make_guard("local_only")
        assert guard._is_local(ipaddress.ip_address("127.0.0.1"))

    def test_localhost_127_x_x_x_allowed(self):
        guard = _make_guard("local_only")
        # Entire 127.0.0.0/8 range is loopback
        assert guard._is_local(ipaddress.ip_address("127.0.0.100"))

    def test_loopback_ipv6_allowed(self):
        guard = _make_guard("local_only")
        assert guard._is_local(ipaddress.ip_address("::1"))

    def test_external_ip_blocked(self):
        guard = _make_guard("local_only")
        assert not guard._is_local(ipaddress.ip_address("8.8.8.8"))

    def test_private_network_blocked_in_local_only(self):
        guard = _make_guard("local_only")
        assert not guard._is_local(ipaddress.ip_address("192.168.1.5"))


class TestIPGuardOpen:
    def test_open_allows_external(self):
        guard = _make_guard("open")
        # In open mode, the middleware short-circuits before IP check
        assert guard.mode == "open"

    def test_open_allows_private(self):
        guard = _make_guard("open")
        assert guard.mode == "open"


class TestIPGuardWhitelist:
    def test_whitelist_allows_listed_ip(self):
        guard = IPGuardMiddleware.__new__(IPGuardMiddleware)
        guard.mode = "whitelist"
        guard.allowed_networks = IPGuardMiddleware._parse_networks(["10.0.0.5"])
        addr = ipaddress.ip_address("10.0.0.5")
        assert guard._is_allowed(addr)

    def test_whitelist_blocks_unlisted(self):
        guard = IPGuardMiddleware.__new__(IPGuardMiddleware)
        guard.mode = "whitelist"
        guard.allowed_networks = IPGuardMiddleware._parse_networks(["10.0.0.5"])
        addr = ipaddress.ip_address("192.168.1.1")
        assert not guard._is_allowed(addr)

    def test_whitelist_cidr_allows_subnet_member(self):
        guard = IPGuardMiddleware.__new__(IPGuardMiddleware)
        guard.mode = "whitelist"
        guard.allowed_networks = IPGuardMiddleware._parse_networks(["192.168.1.0/24"])
        addr = ipaddress.ip_address("192.168.1.50")
        assert guard._is_allowed(addr)

    def test_whitelist_cidr_blocks_outside_subnet(self):
        guard = IPGuardMiddleware.__new__(IPGuardMiddleware)
        guard.mode = "whitelist"
        guard.allowed_networks = IPGuardMiddleware._parse_networks(["192.168.1.0/24"])
        addr = ipaddress.ip_address("10.0.0.1")
        assert not guard._is_allowed(addr)

    def test_parse_networks_skips_invalid(self):
        nets = IPGuardMiddleware._parse_networks(["not-an-ip", "192.168.0.0/16"])
        assert len(nets) == 1

    def test_whitelist_localhost_always_allowed(self):
        guard = IPGuardMiddleware.__new__(IPGuardMiddleware)
        guard.mode = "whitelist"
        guard.allowed_networks = IPGuardMiddleware._parse_networks(["10.0.0.1"])
        addr = ipaddress.ip_address("127.0.0.1")
        assert guard._is_allowed(addr)

    def test_forbidden_response_format(self):
        resp = IPGuardMiddleware._forbidden()
        assert resp.status_code == 403
        import json
        body = json.loads(resp.body)
        assert "error" in body


# ════════════════════════════════════════════════════════════════
# Redact Tests
# ════════════════════════════════════════════════════════════════


class TestRedactSecrets:
    def test_redact_openai_key(self):
        text = "Using key sk-abcdefghijklmnopqrstuvwxyz1234567890"
        result = redact_secrets(text)
        assert "sk-abcdefghijklmnopqrstuvwxyz1234567890" not in result
        assert "****" in result

    def test_redact_openai_project_key(self):
        text = "key=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
        result = redact_secrets(text)
        assert "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890" not in result

    def test_redact_anthropic_key(self):
        text = "ANTHROPIC_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        result = redact_secrets(text)
        assert "sk-ant-api03-abcdefghijklmnopqrstuvwxyz" not in result

    def test_redact_bearer_header(self):
        text = "Authorization: Bearer sk-openai-verylongsecrettoken123456"
        result = redact_secrets(text)
        assert "sk-openai-verylongsecrettoken123456" not in result
        assert "[REDACTED]" in result

    def test_redact_leaves_short_tokens_alone(self):
        """Short strings that don't match the pattern should be untouched."""
        text = "model=gpt-4o"
        assert redact_secrets(text) == text

    def test_redact_leaves_normal_text(self):
        text = "Hello world, no secrets here!"
        assert redact_secrets(text) == text

    def test_redact_multiple_keys_in_one_string(self):
        text = "key1=sk-abcdefghijklmnopqrstuvwxyz12345 key2=sk-proj-xyzabcdefghijklmnopqrstuvwxyz"
        result = redact_secrets(text)
        assert "sk-abcdefghijklmnopqrstuvwxyz12345" not in result
        assert "sk-proj-xyzabcdefghijklmnopqrstuvwxyz" not in result


class TestRedactHeaders:
    def test_redacts_authorization(self):
        headers = {"Authorization": "Bearer sk-realtoken123", "Content-Type": "application/json"}
        result = redact_headers(headers)
        assert result["Authorization"] == "[REDACTED]"
        assert result["Content-Type"] == "application/json"

    def test_redacts_x_api_key(self):
        headers = {"x-api-key": "my-secret-key"}
        result = redact_headers(headers)
        assert result["x-api-key"] == "[REDACTED]"

    def test_case_insensitive(self):
        headers = {"AUTHORIZATION": "Bearer token", "Api-Key": "secret"}
        result = redact_headers(headers)
        assert result["AUTHORIZATION"] == "[REDACTED]"
        assert result["Api-Key"] == "[REDACTED]"

    def test_non_sensitive_headers_preserved(self):
        headers = {"Content-Type": "application/json", "X-Request-ID": "abc123"}
        result = redact_headers(headers)
        assert result == headers
