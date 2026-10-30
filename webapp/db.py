"""
db.py -- SQLite storage for the PulseCheck web app.

One small file database (data/pulsecheck.db). Timestamps are stored as naive
local ISO strings ("2026-10-06T14:30:00") because the demo runs as one
organisation in one time zone.
"""

import os
import sqlite3
from contextlib import contextmanager

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.environ.get("PULSECHECK_DB", os.path.join(ROOT, "data", "pulsecheck.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    lead_id INTEGER
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'employee',      -- employee | lead | admin
    team_id INTEGER,
    emp_code TEXT,
    consent INTEGER NOT NULL DEFAULT 1,         -- allow wellbeing analysis of own messages and chatbot talk
    physio_consent INTEGER NOT NULL DEFAULT 0,  -- allow use of heart-rate / skin-conductance readings
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    recipient_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'chat',          -- chat | checkin
    created_at TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    analyzed INTEGER NOT NULL DEFAULT 0,
    stress_risk REAL,
    stress_label TEXT,
    cues TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_pair ON messages(sender_id, recipient_id, created_at);
CREATE INDEX IF NOT EXISTS idx_msg_rcpt ON messages(recipient_id, is_read);
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,
    owner_id INTEGER NOT NULL,                  -- whose calendar this entry sits on
    organizer_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'meeting',       -- meeting | wellbeing
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meet_owner ON meetings(owner_id, start_ts);
CREATE TABLE IF NOT EXISTS moods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    value INTEGER NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mood_user ON moods(user_id, created_at);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,                         -- user | assistant
    content TEXT NOT NULL,
    tools TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id);
CREATE TABLE IF NOT EXISTS chat_state (
    user_id INTEGER PRIMARY KEY,
    state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,                        -- e.g. ESP32-DEMO
    key_hash TEXT NOT NULL,
    user_id INTEGER,                            -- owner; NULL = shared device
    label TEXT,
    last_seen TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkin_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    device_id TEXT NOT NULL,
    slot TEXT NOT NULL,                         -- morning | afternoon | evening
    status TEXT NOT NULL DEFAULT 'pending',     -- pending | measuring | done | failed | cancelled | expired
    message TEXT,
    reading_id INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sess_dev ON checkin_sessions(device_id, status);
CREATE INDEX IF NOT EXISTS idx_sess_user ON checkin_sessions(user_id, id);
CREATE TABLE IF NOT EXISTS physio_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_id INTEGER,
    device_id TEXT,
    slot TEXT NOT NULL,
    hr REAL NOT NULL,
    gsr REAL NOT NULL,
    quality REAL,
    n_samples INTEGER,
    source TEXT NOT NULL DEFAULT 'device',      -- device | simulated | seed
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_phys_user ON physio_readings(user_id, created_at);
"""


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


@contextmanager
def tx():
    """Connection that commits on success, rolls back on error."""
    c = _connect()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init():
    with tx() as c:
        c.executescript(SCHEMA)
        # small migration for databases created before the hardware module existed
        cols = {r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        if "physio_consent" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN physio_consent INTEGER NOT NULL DEFAULT 0")
        scols = {r["name"] for r in c.execute("PRAGMA table_info(checkin_sessions)").fetchall()}
        for col in ("picked_at", "measure_at"):          # live progress bar timing (epoch seconds)
            if col not in scols:
                c.execute(f"ALTER TABLE checkin_sessions ADD COLUMN {col} REAL")


def rows(sql, args=()):
    with tx() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql, args=()):
    with tx() as c:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None


def run(sql, args=()):
    """Execute a write; returns lastrowid."""
    with tx() as c:
        return c.execute(sql, args).lastrowid


def scalar(sql, args=(), default=None):
    with tx() as c:
        r = c.execute(sql, args).fetchone()
        return r[0] if r and r[0] is not None else default
