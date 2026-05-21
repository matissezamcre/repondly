import sqlite3
import uuid
from pathlib import Path

import os
_data_root = Path(os.getenv("DATA_ROOT", str(Path(__file__).parent)))
DB_PATH = _data_root / "repondly.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                  TEXT PRIMARY KEY,
            email               TEXT UNIQUE NOT NULL,
            password_hash       TEXT NOT NULL,
            stripe_customer_id  TEXT,
            subscription_status TEXT DEFAULT 'trial',
            created_at          TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migrate existing tables
    for col, definition in [
        ("stripe_customer_id", "TEXT"),
        ("subscription_status", "TEXT DEFAULT 'trial'"),
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        except Exception:
            pass
    conn.commit()
    conn.close()


def create_user(email: str, password_hash: str) -> str:
    bot_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
        (bot_id, email, password_hash),
    )
    conn.commit()
    conn.close()
    return bot_id


def get_user_by_email(email: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def update_subscription(user_id: str, status: str, customer_id: str = None):
    conn = get_db()
    if customer_id:
        conn.execute(
            "UPDATE users SET subscription_status=?, stripe_customer_id=? WHERE id=?",
            (status, customer_id, user_id),
        )
    else:
        conn.execute("UPDATE users SET subscription_status=? WHERE id=?", (status, user_id))
    conn.commit()
    conn.close()


def get_user_by_customer_id(customer_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
    conn.close()
    return row
