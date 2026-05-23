import os
import uuid

import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_db():
    return psycopg2.connect(DATABASE_URL)


def _fetchone(cur):
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([d[0] for d in cur.description], row))


def init_db():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id                  TEXT PRIMARY KEY,
                email               TEXT UNIQUE NOT NULL,
                password_hash       TEXT NOT NULL,
                stripe_customer_id  TEXT,
                subscription_status TEXT DEFAULT 'trial',
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                config              JSONB DEFAULT '{}',
                knowledge           JSONB DEFAULT '{}'
            )
        """)
        conn.commit()
        for col, definition in [
            ("stripe_customer_id", "TEXT"),
            ("subscription_status", "TEXT DEFAULT 'trial'"),
            ("config", "JSONB DEFAULT '{}'"),
            ("knowledge", "JSONB DEFAULT '{}'"),
            ("email_verified", "BOOLEAN DEFAULT false"),
            ("total_conversations", "INTEGER DEFAULT 0"),
        ]:
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
                conn.commit()
            except psycopg2.errors.DuplicateColumn:
                conn.rollback()
    conn.close()


def create_user(email: str, password_hash: str) -> str:
    bot_id = str(uuid.uuid4())
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (%s, %s, %s)",
            (bot_id, email, password_hash),
        )
    conn.commit()
    conn.close()
    return bot_id


def get_user_by_email(email: str):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        row = _fetchone(cur)
    conn.close()
    return row


def get_user_by_id(user_id: str):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = _fetchone(cur)
    conn.close()
    return row


def update_subscription(user_id: str, status: str, customer_id: str = None):
    conn = get_db()
    with conn.cursor() as cur:
        if customer_id:
            cur.execute(
                "UPDATE users SET subscription_status=%s, stripe_customer_id=%s WHERE id=%s",
                (status, customer_id, user_id),
            )
        else:
            cur.execute("UPDATE users SET subscription_status=%s WHERE id=%s", (status, user_id))
    conn.commit()
    conn.close()


def get_user_by_customer_id(customer_id: str):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE stripe_customer_id = %s", (customer_id,))
        row = _fetchone(cur)
    conn.close()
    return row


def update_password(user_id: str, password_hash: str):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (password_hash, user_id))
    conn.commit()
    conn.close()


def set_email_verified(user_id: str):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET email_verified=true WHERE id=%s", (user_id,))
    conn.commit()
    conn.close()


def increment_conversations(user_id: str):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET total_conversations=total_conversations+1 WHERE id=%s", (user_id,))
    conn.commit()
    conn.close()


def load_user_config(user_id: str) -> dict:
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT config FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else {}


def save_user_config(user_id: str, config: dict):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET config=%s WHERE id=%s",
            (psycopg2.extras.Json(config), user_id),
        )
    conn.commit()
    conn.close()


def load_user_knowledge(user_id: str) -> dict:
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT knowledge FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else {}


def save_user_knowledge(user_id: str, knowledge: dict):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET knowledge=%s WHERE id=%s",
            (psycopg2.extras.Json(knowledge), user_id),
        )
    conn.commit()
    conn.close()
