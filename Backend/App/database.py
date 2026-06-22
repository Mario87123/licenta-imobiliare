import hashlib
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "app.db"))


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def ensure_column(cursor, table_name: str, column_name: str, definition: str):
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if column_name not in existing_columns:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def build_password_hash(password: str, salt: str = "default_admin_salt") -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000,
    ).hex()
    return f"{salt}${digest}"


def seed_default_admin(cursor):
    cursor.execute("SELECT id FROM users WHERE email = ?", ("admin@local.test",))
    if cursor.fetchone():
        return

    cursor.execute("""
        INSERT INTO users (name, email, password_hash, role)
        VALUES (?, ?, ?, ?)
    """, (
        "Administrator",
        "admin@local.test",
        build_password_hash("admin123"),
        "admin",
    ))


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price_eur INTEGER,
            surface_mp REAL,
            rooms INTEGER,
            neighborhood TEXT,
            city TEXT,
            nearby_neighborhood TEXT,
            location_confidence TEXT,
            floor INTEGER,
            total_floors INTEGER,
            year_built INTEGER,
            partitioning TEXT,
            url TEXT UNIQUE,
            source TEXT,
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            duplicate_group_id INTEGER,
            canonical_ad_id INTEGER,
            duplicate_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crawl_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            mode TEXT,
            status TEXT NOT NULL,
            message TEXT,
            max_pages INTEGER,
            max_ads INTEGER,
            pages_discovered INTEGER DEFAULT 0,
            ads_discovered INTEGER DEFAULT 0,
            ads_processed INTEGER DEFAULT 0,
            ads_inserted INTEGER DEFAULT 0,
            ads_updated INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            blocked_count INTEGER DEFAULT 0,
            cancel_requested INTEGER DEFAULT 0,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ignored_listing_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            source TEXT NOT NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(url, source)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rejected_duplicate_ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            url TEXT,
            matched_ad_id INTEGER,
            duplicate_score REAL,
            title TEXT,
            price_eur INTEGER,
            surface_mp REAL,
            rooms INTEGER,
            neighborhood TEXT,
            city TEXT,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(url, source)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorite_ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ad_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, ad_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(ad_id) REFERENCES ads(id)
        )
    """)


    ensure_column(cursor, "ads", "city", "TEXT")
    ensure_column(cursor, "ads", "nearby_neighborhood", "TEXT")
    ensure_column(cursor, "ads", "location_confidence", "TEXT")
    ensure_column(cursor, "ads", "first_seen_at", "TIMESTAMP")
    ensure_column(cursor, "ads", "last_seen_at", "TIMESTAMP")
    ensure_column(cursor, "ads", "last_crawled_at", "TIMESTAMP")
    ensure_column(cursor, "ads", "is_active", "INTEGER DEFAULT 1")
    ensure_column(cursor, "ads", "duplicate_group_id", "INTEGER")
    ensure_column(cursor, "ads", "canonical_ad_id", "INTEGER")
    ensure_column(cursor, "ads", "duplicate_score", "REAL")

    ensure_column(cursor, "crawl_jobs", "source", "TEXT")
    ensure_column(cursor, "crawl_jobs", "mode", "TEXT")
    ensure_column(cursor, "crawl_jobs", "max_pages", "INTEGER")
    ensure_column(cursor, "crawl_jobs", "max_ads", "INTEGER")
    ensure_column(cursor, "crawl_jobs", "pages_discovered", "INTEGER DEFAULT 0")
    ensure_column(cursor, "crawl_jobs", "ads_discovered", "INTEGER DEFAULT 0")
    ensure_column(cursor, "crawl_jobs", "ads_processed", "INTEGER DEFAULT 0")
    ensure_column(cursor, "crawl_jobs", "ads_inserted", "INTEGER DEFAULT 0")
    ensure_column(cursor, "crawl_jobs", "ads_updated", "INTEGER DEFAULT 0")
    ensure_column(cursor, "crawl_jobs", "error_count", "INTEGER DEFAULT 0")
    ensure_column(cursor, "crawl_jobs", "blocked_count", "INTEGER DEFAULT 0")
    ensure_column(cursor, "crawl_jobs", "cancel_requested", "INTEGER DEFAULT 0")
    ensure_column(cursor, "users", "last_login_at", "TIMESTAMP")

    seed_default_admin(cursor)

    cursor.execute("""
        UPDATE ads
        SET
            first_seen_at = COALESCE(first_seen_at, created_at, CURRENT_TIMESTAMP),
            last_seen_at = COALESCE(last_seen_at, created_at, CURRENT_TIMESTAMP),
            last_crawled_at = COALESCE(last_crawled_at, created_at, CURRENT_TIMESTAMP),
            is_active = COALESCE(is_active, 1)
    """)

    conn.commit()
    conn.close()
