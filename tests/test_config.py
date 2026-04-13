"""Unit tests for configuration management (config.py)."""

from __future__ import annotations

import os
import textwrap

import pytest

from flowgate.config import (
    IPWhitelistConfig,
    SecurityConfig,
    Settings,
    load_settings,
)


class TestDefaultSettings:
    def test_server_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        s = load_settings()
        assert s.server.host == "127.0.0.1"
        assert s.server.port == 7798

    def test_database_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        s = load_settings()
        assert s.database.path == "./data.db"

    def test_logging_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        s = load_settings()
        assert s.logging.level == "INFO"
        assert s.logging.log_prompts is True
        assert s.logging.log_responses is True
        assert s.logging.redact_secrets is True

    def test_security_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        s = load_settings()
        assert s.security.vault_enabled is True
        assert s.security.ip_whitelist.mode == "local_only"
        assert s.security.ip_whitelist.enabled is True
        assert s.security.auth_token_ttl_minutes == 60
        assert s.security.master_key_path == "~/.flowgate/master.key"


class TestLoadFromYAML:
    def test_load_server_config(self, tmp_path):
        cfg = tmp_path / "flowgate.yaml"
        cfg.write_text(textwrap.dedent("""\
            server:
              host: 0.0.0.0
              port: 9000
        """))
        s = load_settings(str(cfg))
        assert s.server.host == "0.0.0.0"
        assert s.server.port == 9000

    def test_load_database_config(self, tmp_path):
        cfg = tmp_path / "flowgate.yaml"
        cfg.write_text("database:\n  path: /tmp/test.db\n")
        s = load_settings(str(cfg))
        assert s.database.path == "/tmp/test.db"

    def test_load_logging_config(self, tmp_path):
        cfg = tmp_path / "flowgate.yaml"
        cfg.write_text(textwrap.dedent("""\
            logging:
              level: DEBUG
              log_prompts: false
              redact_secrets: false
        """))
        s = load_settings(str(cfg))
        assert s.logging.level == "DEBUG"
        assert s.logging.log_prompts is False
        assert s.logging.redact_secrets is False

    def test_load_security_config(self, tmp_path):
        cfg = tmp_path / "flowgate.yaml"
        cfg.write_text(textwrap.dedent("""\
            security:
              vault_enabled: false
              auth_token_ttl_minutes: 30
              master_key_path: /tmp/custom.master.key
              ip_whitelist:
                enabled: true
                mode: whitelist
                allowed_ips:
                  - 10.0.0.1
                  - 192.168.1.0/24
        """))
        s = load_settings(str(cfg))
        assert s.security.vault_enabled is False
        assert s.security.auth_token_ttl_minutes == 30
        assert s.security.master_key_path == "/tmp/custom.master.key"
        assert s.security.ip_whitelist.mode == "whitelist"
        assert "10.0.0.1" in s.security.ip_whitelist.allowed_ips

    def test_missing_file_uses_defaults(self):
        s = load_settings("/nonexistent/path/flowgate.yaml")
        assert s.server.host == "127.0.0.1"

    def test_empty_yaml_uses_defaults(self, tmp_path):
        cfg = tmp_path / "flowgate.yaml"
        cfg.write_text("")
        s = load_settings(str(cfg))
        assert s.server.port == 7798


class TestEnvVarSubstitution:
    def test_resolve_env_var_in_string(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_DB_PATH", "/env/path/test.db")
        cfg = tmp_path / "flowgate.yaml"
        cfg.write_text("database:\n  path: ${TEST_DB_PATH}\n")
        s = load_settings(str(cfg))
        assert s.database.path == "/env/path/test.db"

    def test_missing_env_var_becomes_empty_string(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        cfg = tmp_path / "flowgate.yaml"
        cfg.write_text("database:\n  path: ${MISSING_VAR}\n")
        s = load_settings(str(cfg))
        assert s.database.path == ""

    def test_non_env_var_string_unchanged(self, tmp_path):
        cfg = tmp_path / "flowgate.yaml"
        cfg.write_text("database:\n  path: ./data.db\n")
        s = load_settings(str(cfg))
        assert s.database.path == "./data.db"


class TestIPWhitelistConfig:
    def test_default_mode_is_local_only(self):
        cfg = IPWhitelistConfig()
        assert cfg.mode == "local_only"

    def test_default_allowed_ips(self):
        cfg = IPWhitelistConfig()
        assert "127.0.0.1" in cfg.allowed_ips
        assert "::1" in cfg.allowed_ips

    def test_custom_ips(self):
        cfg = IPWhitelistConfig(allowed_ips=["10.0.0.1", "192.168.0.0/24"])
        assert "10.0.0.1" in cfg.allowed_ips


class TestSecurityConfig:
    def test_defaults(self):
        cfg = SecurityConfig()
        assert cfg.vault_enabled is True
        assert cfg.auth_token_ttl_minutes == 60

    def test_nested_ip_whitelist(self):
        cfg = SecurityConfig(ip_whitelist=IPWhitelistConfig(mode="open"))
        assert cfg.ip_whitelist.mode == "open"
