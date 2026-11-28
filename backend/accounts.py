"""
User accounts and saved assessments (SQLite).

- Passwords are hashed with bcrypt. Nothing else about the password is stored.
- A login creates a random session token. The browser keeps it in an HttpOnly cookie;
  the database keeps only an HMAC of it (signed with settings.SECRET_KEY), so a copy of
  the database cannot be used to log in.
- Saved assessments keep the score, details, skeleton GIF and key frames. The uploaded
  video itself is never kept.
"""
import hashlib
import hmac
import json
import re
import secrets
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import bcrypt

import settings
from errors import UserError

_lock = threading.Lock()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    pw_hash     TEXT NOT NULL,
    created     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created     REAL NOT NULL,
    expires     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS assessments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_id TEXT NOT NULL,
    created     REAL NOT NULL,
    score       REAL NOT NULL,
    details     TEXT NOT NULL,
    video_name  TEXT,
    folder      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assess_user ON assessments(user_id, created);
"""


@contextmanager
def db():
    con = sqlite3.connect(settings.DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init():
    with db() as con:
        con.executescript(SCHEMA)
        con.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))


# ------------------------------------------------------------------ users
def _clean_email(email):
    return (email or "").strip().lower()


def _check_password(password):
    if len(password) < 8:
        raise UserError(400, "The password must be at least 8 characters.")
    if len(password.encode("utf-8")) > 72:
        raise UserError(400, "The password can be at most 72 characters.")


def public_user(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def create_user(name, email, password):
    name = (name or "").strip()
    email = _clean_email(email)
    password = password or ""
    if not name:
        raise UserError(400, "Enter your name.")
    if len(name) > 80:
        raise UserError(400, "The name can be at most 80 characters.")
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise UserError(400, "Enter a valid email address.")
    _check_password(password)
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    with _lock, db() as con:
        if con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise UserError(409, "An account with this email already exists. Log in instead.")
        cur = con.execute("INSERT INTO users (name, email, pw_hash, created) VALUES (?, ?, ?, ?)",
                          (name, email, pw_hash, time.time()))
        return {"id": cur.lastrowid, "name": name, "email": email}


# A fixed hash so a login for an unknown email takes as long as a wrong password
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


def authenticate(email, password):
    email = _clean_email(email)
    pw = (password or "").encode("utf-8")[:72]
    with db() as con:
        row = con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    stored = row["pw_hash"].encode("ascii") if row else _DUMMY_HASH
    ok = bcrypt.checkpw(pw, stored)
    if not row or not ok:
        raise UserError(401, "The email or password is not correct.")
    return public_user(row)


# ------------------------------------------------------------------ sessions
def _token_hash(token):
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def new_session(user_id):
    token = secrets.token_urlsafe(32)
    now = time.time()
    with db() as con:
        con.execute("INSERT INTO sessions (token_hash, user_id, created, expires) VALUES (?, ?, ?, ?)",
                    (_token_hash(token), user_id, now, now + settings.SESSION_DAYS * 86400))
    return token


def user_for_token(token):
    if not token:
        return None
    with db() as con:
        row = con.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires > ?", (_token_hash(token), time.time())).fetchone()
    return public_user(row) if row else None


def end_session(token):
    if token:
        with db() as con:
            con.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


# ------------------------------------------------------------------ assessments
def save_assessment(user_id, exercise_id, score, details, video_name, gif_path, keyframes):
    """Copies the GIF and key frames into data/assessments/<folder>/ and stores the row."""
    folder = secrets.token_hex(12)
    dest = settings.SAVED_DIR / folder
    dest.mkdir(parents=True, exist_ok=True)
    if gif_path and Path(gif_path).is_file():
        shutil.copyfile(gif_path, dest / "skeleton.gif")
    for i, (inp, skel) in enumerate(keyframes or []):
        shutil.copyfile(inp, dest / f"input_{i}.jpg")
        shutil.copyfile(skel, dest / f"skeleton_{i}.jpg")
    with db() as con:
        cur = con.execute(
            "INSERT INTO assessments (user_id, exercise_id, created, score, details, video_name, folder) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, exercise_id, time.time(), float(score), json.dumps(details), video_name, folder))
        return cur.lastrowid


def _row_to_dict(row):
    return {"id": row["id"], "exercise_id": row["exercise_id"], "created": row["created"],
            "score": row["score"], "details": json.loads(row["details"]), "video_name": row["video_name"]}


def list_assessments(user_id):
    with db() as con:
        rows = con.execute("SELECT * FROM assessments WHERE user_id = ? ORDER BY created DESC",
                           (user_id,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_assessment(user_id, assessment_id):
    """Returns (dict, folder path) or raises 404. Only the owner can see an assessment."""
    with db() as con:
        row = con.execute("SELECT * FROM assessments WHERE id = ? AND user_id = ?",
                          (assessment_id, user_id)).fetchone()
    if row is None:
        raise UserError(404, "This assessment was not found.")
    return _row_to_dict(row), settings.SAVED_DIR / row["folder"]


def delete_assessment(user_id, assessment_id):
    _, folder = get_assessment(user_id, assessment_id)
    with db() as con:
        con.execute("DELETE FROM assessments WHERE id = ? AND user_id = ?", (assessment_id, user_id))
    shutil.rmtree(folder, ignore_errors=True)


def saved_keyframes(folder):
    pairs = []
    for i in range(settings.KEYFRAMES):
        a, b = folder / f"input_{i}.jpg", folder / f"skeleton_{i}.jpg"
        if a.is_file() and b.is_file():
            pairs.append((a, b))
    return pairs
