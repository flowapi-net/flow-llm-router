from __future__ import annotations

import base64
from datetime import datetime, timezone

from flowgate.app import _try_auto_unlock
from flowgate.config import DatabaseConfig, SecurityConfig, Settings
from flowgate.db.engine import get_session, init_db
from flowgate.db.models import ProviderKey, VaultMeta
from flowgate.security.master_key_store import save_master_key
from flowgate.security.vault import Vault


def test_auto_unlock_with_persisted_master_key(tmp_path):
    db_path = str(tmp_path / "auto_unlock.db")
    key_path = tmp_path / "master.key"
    settings = Settings(
        database=DatabaseConfig(path=db_path),
        security=SecurityConfig(master_key_path=str(key_path)),
    )

    init_db(db_path)
    seed_vault = Vault()
    salt = seed_vault.initialize("master-password")
    encrypted = seed_vault.encrypt_key("sk-test-123456")

    session = get_session(db_path)
    try:
        session.add(
            VaultMeta(
                id=1,
                salt=base64.b64encode(salt).decode(),
                password_hash=Vault.hash_password("master-password"),
            )
        )
        now = datetime.now(timezone.utc)
        session.add(
            ProviderKey(
                provider="openai",
                key_name="test",
                encrypted_key=encrypted,
                key_suffix="3456",
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    finally:
        session.close()

    save_master_key(settings, seed_vault.export_key())

    runtime_vault = Vault()
    _try_auto_unlock(runtime_vault, settings)

    assert runtime_vault.is_initialized is True
    assert runtime_vault.get_key("openai") == "sk-test-123456"
