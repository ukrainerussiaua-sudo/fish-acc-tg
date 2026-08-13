# ==============================
# database.py — локальная SQLite
# ==============================
import sqlite3
from pathlib import Path
from config import DB_PATH

DB_FILE = Path(DB_PATH).resolve()
DB_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(str(DB_FILE), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    Path("accounts").mkdir(exist_ok=True)
    Path("temp").mkdir(exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_name TEXT NOT NULL UNIQUE,
            phone TEXT,
            country TEXT,
            reg_date TEXT,
            spam_status TEXT DEFAULT 'unknown',
            status TEXT DEFAULT 'free' CHECK(status IN ('free','given','banned')),
            given_to INTEGER,
            has_tdata INTEGER NOT NULL DEFAULT 1 CHECK(has_tdata IN (0,1)),
            has_session INTEGER NOT NULL DEFAULT 0 CHECK(has_session IN (0,1)),
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message_id INTEGER,
            admin_message_id INTEGER,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
        CREATE INDEX IF NOT EXISTS idx_accounts_given_to ON accounts(given_to);
        CREATE INDEX IF NOT EXISTS idx_accounts_phone ON accounts(phone);
        """)


def add_account(folder_name, phone=None, country=None, reg_date=None, spam_status="unknown"):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO accounts(folder_name, phone, country, reg_date, spam_status)
               VALUES(?, ?, ?, ?, ?)""",
            (folder_name, phone, country, reg_date, spam_status),
        )
        return cur.lastrowid


def get_free_accounts():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM accounts WHERE status='free' ORDER BY id").fetchall()


def get_all_accounts():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM accounts ORDER BY id DESC").fetchall()


def get_user_accounts(user_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM accounts WHERE given_to=? AND status='given' ORDER BY id DESC", (user_id,)
        ).fetchall()


def get_account_by_id(acc_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM accounts WHERE id=?", (acc_id,)).fetchone()


def give_account(acc_id, user_id) -> bool:
    """Атомарно выдаёт только свободный аккаунт."""
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE accounts
               SET status='given', given_to=?
               WHERE id=? AND status='free'""",
            (user_id, acc_id),
        )
        return cur.rowcount == 1


def ban_account(acc_id):
    with get_conn() as conn:
        conn.execute("UPDATE accounts SET status='banned' WHERE id=?", (acc_id,))


def update_account_session(acc_id, has_session: bool):
    with get_conn() as conn:
        conn.execute("UPDATE accounts SET has_session=? WHERE id=?", (int(bool(has_session)), acc_id))


def update_account_spam(acc_id, spam_status):
    with get_conn() as conn:
        conn.execute("UPDATE accounts SET spam_status=? WHERE id=?", (spam_status, acc_id))


def update_account_info(acc_id, phone=None, country=None, reg_date=None):
    fields, values = [], []
    if phone is not None:
        fields.append("phone=?"); values.append(phone)
    if country is not None:
        fields.append("country=?"); values.append(country)
    if reg_date is not None:
        fields.append("reg_date=?"); values.append(reg_date)
    if not fields:
        return
    values.append(acc_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE accounts SET {', '.join(fields)} WHERE id=?", values)


def get_given_accounts():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM accounts WHERE status='given' ORDER BY id DESC").fetchall()


def get_banned_accounts():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM accounts WHERE status='banned' ORDER BY id DESC").fetchall()


def clear_database(target="all"):
    if target not in {"all", "given", "banned"}:
        raise ValueError("target must be all, given or banned")
    with get_conn() as conn:
        sql = "DELETE FROM accounts" if target == "all" else "DELETE FROM accounts WHERE status=?"
        conn.execute(sql, () if target == "all" else (target,))


def register_user(user_id, username, full_name):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO users(user_id, username, full_name)
               VALUES(?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   username=excluded.username,
                   full_name=excluded.full_name""",
            (user_id, username, full_name),
        )


def get_all_users():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users ORDER BY registered_at DESC").fetchall()
