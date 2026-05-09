"""
Database initialization and management for Telegram Bot.

Manages SQLite schema creation and query helpers.
Schema includes: accounts, profiles, conversations, api_keys, and audit logging.
"""

import sqlite3
import os
import shutil
import logging
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database operations and schema initialization."""
    
    def __init__(self, db_path: str = "telegrambot.db"):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file (default: telegrambot.db)
        """
        self.db_path = db_path
        self.connection = None
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def initialize_database(self) -> bool:
        """
        Initialize database schema if it doesn't exist.
        
        Creates all required tables with proper schema and indexes.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            db_exists = os.path.exists(self.db_path)
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Only create tables if new database
                if not db_exists:
                    logger.info("Creating new database schema...")
                    self._create_schema(cursor)
                    conn.commit()
                    logger.info("Database schema created")
                else:
                    logger.info("Database already initialised")
                    # Verify tables exist (in case of partial setup)
                    self._verify_schema(cursor)
            
            return True
        
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False
    
    def _create_schema(self, cursor: sqlite3.Cursor):
        """Execute all schema creation SQL statements."""
        cursor.executescript(self._get_schema_sql())
    
    @staticmethod
    def _get_schema_sql() -> str:
        """Return the full database schema SQL."""
        return """
-- accounts: Telegram login credentials
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_type TEXT DEFAULT 'telegram',
    name TEXT NOT NULL,
    phone TEXT UNIQUE NOT NULL,
    api_id TEXT,
    api_hash TEXT,
    password TEXT,
    is_active BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_accounts_phone ON accounts(phone);
CREATE INDEX IF NOT EXISTS idx_accounts_active ON accounts(is_active);
CREATE INDEX IF NOT EXISTS idx_accounts_type ON accounts(account_type);

-- profiles: bot persona definitions
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Status
    is_current BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Persona Data
    name TEXT NOT NULL,
    age INTEGER,
    location TEXT,
    ethnicity TEXT,
    
    -- Customization
    system_prompt_custom TEXT,
    response_tone TEXT DEFAULT 'neutral',
    
    -- Template & Training Data
    template_ids TEXT,  -- JSON array: ["template_1", "template_3"]
    training_data_category TEXT,
    
    -- Rate Limiting
    max_daily_interactions INTEGER DEFAULT 100,
    interactions_today INTEGER DEFAULT 0,
    
    -- Tracking
    last_used TIMESTAMP,
    usage_count INTEGER DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_profiles_current ON profiles(is_current);
CREATE INDEX IF NOT EXISTS idx_profiles_name ON profiles(name);

-- conversations: one row per user/account pair, tracks state and funnel progress
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    account_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    chat_type TEXT DEFAULT 'private' CHECK(chat_type IN ('private', 'group', 'supergroup', 'channel')),
    last_message TEXT,
    last_message_time TIMESTAMP,
    of_link_sent BOOLEAN DEFAULT 0,
    state TEXT DEFAULT 'ACTIVE' CHECK(state IN ('ACTIVE', 'IDLE', 'EXPIRED')),
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived', 'deleted')),
    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    timeout_until TIMESTAMP,
    expiry_time TIMESTAMP NULL,
    funnel_done BOOLEAN DEFAULT 0,
    is_orphaned_cleanup BOOLEAN DEFAULT 0,
    cleanup_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    api_calls_count INTEGER DEFAULT 0,
    total_tokens_used INTEGER DEFAULT 0,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_account ON conversations(user_id, account_id);
CREATE INDEX IF NOT EXISTS idx_conversations_account ON conversations(account_id);
CREATE INDEX IF NOT EXISTS idx_conversations_state ON conversations(account_id, state);
CREATE INDEX IF NOT EXISTS idx_conversations_timeout_until 
    ON conversations(account_id, timeout_until) 
    WHERE state IN ('IDLE', 'EXPIRED');
CREATE INDEX IF NOT EXISTS idx_conversations_expiry_time 
    ON conversations(account_id, expiry_time) 
    WHERE state = 'EXPIRED';

-- messages: individual messages within a conversation
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    text TEXT,
    message_type TEXT DEFAULT 'text' CHECK(message_type IN ('text', 'photo', 'video', 'audio', 'document', 'voice', 'video_note')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    telegram_message_id INTEGER,
    is_edited BOOLEAN DEFAULT 0,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

-- api_keys: stored API credentials with quota tracking
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    provider TEXT NOT NULL CHECK(provider IN ('openai', 'gemini', 'fallback')),
    key_secret TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    key_order INTEGER,
    is_exhausted BOOLEAN DEFAULT 0,
    exhaustion_reason TEXT,
    quota_used_tokens BIGINT DEFAULT 0,
    quota_used_requests INTEGER DEFAULT 0,
    quota_limit_tokens BIGINT,
    quota_limit_requests INTEGER,
    quota_reset_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    error_count INTEGER DEFAULT 0,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_api_keys_account_active 
    ON api_keys(account_id, is_active, provider);
CREATE INDEX IF NOT EXISTS idx_api_keys_last_used 
    ON api_keys(account_id, provider, last_used_at);
CREATE INDEX IF NOT EXISTS idx_api_keys_exhausted 
    ON api_keys(account_id, is_exhausted);

-- api_usage_billing: monthly usage tracking per provider
CREATE TABLE IF NOT EXISTS api_usage_billing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    account_id INTEGER NOT NULL,
    month_year TEXT NOT NULL,  -- Format: '2026-02'
    provider TEXT NOT NULL,
    
    -- Usage Metrics
    total_tokens_used BIGINT DEFAULT 0,
    total_requests_used INTEGER DEFAULT 0,
    estimated_cost_dollars DECIMAL(10, 4) DEFAULT 0,
    
    FOREIGN KEY(account_id) REFERENCES accounts(id),
    UNIQUE(account_id, month_year, provider)
);

CREATE INDEX IF NOT EXISTS idx_api_usage_account_month 
    ON api_usage_billing(account_id, month_year);

-- audit_log: records reset/delete operations for debugging
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT,
    type TEXT,
    affected_accounts INTEGER,
    affected_conversations INTEGER,
    description TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    backup_file TEXT,
    user_confirmed BOOLEAN DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_audit_log_operation ON audit_log(operation);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);

-- deleted_accounts: soft-delete record for recovery
CREATE TABLE IF NOT EXISTS deleted_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    email TEXT,
    deleted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    backup_location TEXT,
    profile_count INTEGER,
    conversation_count INTEGER
);

CREATE INDEX IF NOT EXISTS idx_deleted_accounts_email ON deleted_accounts(email);
CREATE INDEX IF NOT EXISTS idx_deleted_accounts_deleted_at ON deleted_accounts(deleted_at);
        """
    
    def _verify_schema(self, cursor: sqlite3.Cursor):
        """Verify that all required tables exist and apply safe migrations."""
        required_tables = [
            'accounts', 'profiles', 'conversations', 'api_keys',
            'api_usage_billing', 'audit_log', 'deleted_accounts'
        ]
        
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        missing_tables = set(required_tables) - existing_tables
        if missing_tables:
            logger.warning(f"Missing tables: {missing_tables}")
        
        # Safe migrations — ADD COLUMN is always backwards-compatible in SQLite.
        # Catch errors silently; they just mean the column already exists.
        migrations = [
            "ALTER TABLE conversations ADD COLUMN funnel_done BOOLEAN DEFAULT 0",
        ]
        for sql in migrations:
            try:
                cursor.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists

        logger.info(f"Database verification passed ({len(existing_tables)} tables present)")
    
    # Query helpers
    
    def execute_query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Execute SELECT query and return results."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []
    
    def execute_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Execute SELECT query and return first result."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return None
    
    def execute_update(self, sql: str, params: tuple = ()) -> bool:
        """Execute INSERT/UPDATE/DELETE operation."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                return True
        except Exception as e:
            logger.error(f"Update failed: {e}")
            return False
    
    # Account methods
    
    def get_current_account(self) -> Optional[Dict[str, Any]]:
        """Get the active account."""
        row = self.execute_one(
            "SELECT * FROM accounts WHERE is_active = 1 LIMIT 1"
        )
        return dict(row) if row else None
    
    def get_account_by_id(self, account_id: int) -> Optional[Dict[str, Any]]:
        """Get account by ID."""
        row = self.execute_one(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        )
        return dict(row) if row else None
    
    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """Get all accounts."""
        rows = self.execute_query("SELECT * FROM accounts ORDER BY created_at DESC")
        return [dict(row) for row in rows]
    
    # Profile methods
    
    def get_current_profile(self) -> Optional[Dict[str, Any]]:
        """Get profile marked as current."""
        row = self.execute_one(
            "SELECT * FROM profiles WHERE is_current = 1 LIMIT 1"
        )
        return dict(row) if row else None
    
    def get_all_profiles(self) -> List[Dict[str, Any]]:
        """Get all profiles."""
        rows = self.execute_query(
            "SELECT * FROM profiles ORDER BY created_at DESC"
        )
        return [dict(row) for row in rows]
    
    def create_profile(self, name: str, age: int = None, location: str = None,
                      ethnicity: str = None) -> int:
        """Create new profile. Returns profile ID."""
        self.execute_update(
            """INSERT INTO profiles (name, age, location, ethnicity)
               VALUES (?, ?, ?, ?)""",
            (name, age, location, ethnicity)
        )
        
        row = self.execute_one(
            "SELECT id FROM profiles WHERE name = ?", (name,)
        )
        return row['id'] if row else 0
    
    # Conversation methods
    
    def get_recent_messages(
        self, user_id: int, account_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Return the last N messages for a conversation, oldest first.

        Returns an empty list if no conversation exists or if it is EXPIRED
        (so the LLM starts fresh after a long gap).

        Each item has keys: 'role' ('user' | 'bot'), 'text'.
        Short messages (≤2 chars) are excluded — they add no useful context.
        """
        row = self.execute_one(
            "SELECT id, state FROM conversations WHERE user_id = ? AND account_id = ?",
            (user_id, account_id),
        )

        if not row or row["state"] == "EXPIRED":
            return []

        rows = self.execute_query(
            """SELECT sender_id, text FROM messages
               WHERE conversation_id = ?
                 AND LENGTH(COALESCE(text, '')) > 2
               ORDER BY id DESC
               LIMIT ?""",
            (row["id"], limit),
        )

        # Reverse so the list is chronological (oldest first) for the LLM
        history = []
        for r in reversed(rows):
            role = "user" if r["sender_id"] == user_id else "bot"
            if r["text"]:
                history.append({"role": role, "text": r["text"]})
        return history

    def expire_old_conversations(self) -> None:
        """Mark ACTIVE conversations as EXPIRED when they pass their timeout."""
        self.execute_update(
            """UPDATE conversations
               SET state = 'EXPIRED'
               WHERE state = 'ACTIVE'
                 AND timeout_until IS NOT NULL
                 AND timeout_until < datetime('now')"""
        )

    def get_funnel_state(self, user_id: int, account_id: int) -> str:
        """
        Return the funnel state for a conversation.

        Returns:
            'done'    — user refused OF or received the final reply, bot stays silent
            'closing' — OF link was just sent, one final reply is still allowed
            'active'  — normal conversation
        """
        row = self.execute_one(
            "SELECT of_link_sent, funnel_done FROM conversations "
            "WHERE user_id = ? AND account_id = ?",
            (user_id, account_id),
        )
        if not row:
            return "active"
        if row["funnel_done"]:
            return "done"
        if row["of_link_sent"]:
            return "closing"
        return "active"

    def set_funnel_closing(self, user_id: int, account_id: int) -> None:
        """Mark that the OF link was sent — next user reply gets one final nudge."""
        self.execute_update(
            "UPDATE conversations SET of_link_sent = 1 "
            "WHERE user_id = ? AND account_id = ?",
            (user_id, account_id),
        )

    def set_funnel_done(self, user_id: int, account_id: int) -> None:
        """Mark conversation fully done — bot goes silent on this chat."""
        self.execute_update(
            "UPDATE conversations SET funnel_done = 1, of_link_sent = 1 "
            "WHERE user_id = ? AND account_id = ?",
            (user_id, account_id),
        )

    # Backup
    
    def backup_database(self, backup_path: str) -> bool:
        """Create a backup copy of the database."""
        try:
            if not os.path.exists(self.db_path):
                logger.error(f"Source database not found: {self.db_path}")
                return False
            
            # Ensure backup directory exists
            Path(backup_path).parent.mkdir(parents=True, exist_ok=True)

            # Use shutil.copy2 for the backup — avoids embedding the path
            # directly in a SQL string (VACUUM INTO doesn't support parameters).
            shutil.copy2(self.db_path, backup_path)
            
            logger.info(f"Database backed up to {backup_path}")
            return True
        
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return False
    
    def cleanup_expired_conversations(self, account_id: int, hours_to_keep: int = 24) -> int:
        """Delete EXPIRED conversations older than hours_to_keep. Returns rows deleted."""
        try:
            rows = self.execute_query(
                """SELECT id FROM conversations
                   WHERE account_id = ? AND state = 'EXPIRED'
                     AND expiry_time IS NOT NULL
                     AND expiry_time < datetime('now', ? || ' hours')""",
                (account_id, f"-{hours_to_keep}"),
            )

            conversation_ids = [row["id"] for row in rows]
            if conversation_ids:
                placeholders = ",".join("?" * len(conversation_ids))
                self.execute_update(
                    f"DELETE FROM conversations WHERE id IN ({placeholders})",
                    tuple(conversation_ids),
                )
                logger.info(f"Cleaned up {len(conversation_ids)} expired conversations")

            return len(conversation_ids)

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return 0


def initialize_database_with_defaults(db_path: Optional[str] = None) -> bool:
    """
    Initialize database and create necessary directories.
    
    Args:
        db_path: Path to database file
        
    Returns:
        bool: True if successful
    """
    from src.runtime_paths import USER_DATA_DIR

    if db_path is None:
        db_path = str(USER_DATA_DIR / "telegrambot.db")

    try:
        log_dir = USER_DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        sessions_dir = USER_DATA_DIR / "pyrogram_sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        db = DatabaseManager(db_path)
        success = db.initialize_database()
        
        if success:
            logger.info("Database initialisation complete")
        
        return success
    
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False


if __name__ == "__main__":
    # Setup basic logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize database
    print("Initializing Telegram Bot database...")
    success = initialize_database_with_defaults()
    
    if success:
        db = DatabaseManager()
        tables = db.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
        print(f"Database ready — {len(tables)} tables")
    else:
        print("Database initialisation failed")
