import json
import os
import sys

import pytest
from cryptography.fernet import Fernet

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def conn(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("BANK_ENC_KEY", Fernet.generate_key().decode())

    import db
    db.DB_PATH = db_path
    db.init_db()

    connection = db.get_connection()
    yield connection
    connection.close()


@pytest.fixture
def bank_connection(conn):
    cur = conn.execute(
        """
        INSERT INTO bank_connections (provider, label, account_ref, status, consent_id, secrets_enc, created_at)
        VALUES ('psd2', 'Test Bank', 'acc-1', 'valid', 'consent-1', '', '2026-01-01')
        """
    )
    conn.commit()
    return cur.lastrowid
