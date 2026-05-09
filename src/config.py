"""
Configuration management for Telegram Bot application.

Loads and validates configuration from JSON files and environment variables.
Manages API credentials, database paths, and runtime settings.
Supports remote API key management via Cloudflare Workers.
"""

import json
import os
import logging
import shutil
from typing import Optional
from pathlib import Path
from dataclasses import dataclass, asdict

from src.runtime_paths import USER_DATA_DIR, BUNDLE_DIR, is_frozen

logger = logging.getLogger(__name__)


def _flush_logs() -> None:
    """Ensure file handlers persist lines before abrupt process exit."""
    for h in logging.root.handlers:
        try:
            h.flush()
        except Exception:
            pass


def _strip_opt(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _json_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if value is None:
        return default
    return bool(value)


def _fatal_installer(title: str, message: str) -> None:
    """Show a visible error and exit (windowed .exe has no console)."""
    import sys

    logger.critical("%s — %s", title, message.replace("\n", " "))
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
        except Exception:
            pass
    print(f"\n{title}\n{message}\n", file=sys.stderr)
    _flush_logs()
    raise SystemExit(1)

# Fallback Telegram API credentials — overridden by config.json or env vars.
DEFAULT_TELEGRAM_API_ID = 0
DEFAULT_TELEGRAM_API_HASH = ""


@dataclass
class TelegramConfig:
    """Telegram API credentials and settings."""
    api_id: int = DEFAULT_TELEGRAM_API_ID
    api_hash: str = DEFAULT_TELEGRAM_API_HASH
    phone_number: Optional[str] = None
    
    def validate(self) -> bool:
        """Validate that required fields are set."""
        if not self.api_id or not self.api_hash:
            logger.error("Missing Telegram API credentials (api_id, api_hash)")
            return False
        return True


@dataclass
class DatabaseConfig:
    """Database configuration."""
    db_path: str = "telegrambot.db"
    session_dir: str = "pyrogram_sessions"
    backup_dir: str = "backups"
    
    def ensure_directories(self):
        """Create necessary directories if they don't exist."""
        Path(self.session_dir).mkdir(parents=True, exist_ok=True)
        Path(self.backup_dir).mkdir(parents=True, exist_ok=True)


@dataclass
class ApiConfig:
    """API provider configuration."""
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    request_timeout: int = 30


@dataclass
class UiConfig:
    """UI/Desktop application configuration."""
    theme: str = "Dark"
    window_width: int = 1200
    window_height: int = 800
    font_size: int = 10
    log_panel_height: int = 200


@dataclass
class BotConfig:
    """Bot-specific runtime settings."""
    of_link: Optional[str] = None
    # How long the bot waits before replying (simulates reading the message)
    read_delay_min: float = 1.5   # seconds
    read_delay_max: float = 4.0   # seconds
    # Max time the typing indicator is shown (scales with response length)
    max_typing_delay: float = 12.0  # seconds
    # Seconds of inactivity before a conversation goes IDLE
    conversation_timeout: int = 180
    # Whether to show DEBUG-level logs in the log panel
    debug_logging: bool = False
    # Telegram user IDs that reset conversation state on greeting (test accounts only)
    test_user_ids: list = None

    def __post_init__(self):
        if self.test_user_ids is None:
            self.test_user_ids = []


@dataclass
class CloudflareConfig:
    """Cloudflare Workers configuration for remote API key management."""
    enabled: bool = False
    worker_url: Optional[str] = None
    auth_token: Optional[str] = None
    fallback_to_local: bool = True  # dev/source only: keep config keys if Worker fetch fails
    timeout: int = 30  # seconds to wait for Cloudflare response
    
    def is_configured(self) -> bool:
        """Check if Cloudflare is properly configured."""
        return self.enabled and self.worker_url and self.auth_token


class ConfigManager:
    """Manages application configuration from JSON and environment."""
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_dir: Directory containing config files (default: %APPDATA%/TelegramBot/config when installed)
        """
        if config_dir is None:
            config_dir = str(USER_DATA_DIR / "config")
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration objects
        self.telegram: Optional[TelegramConfig] = None
        self.database: DatabaseConfig = DatabaseConfig()
        self.api: ApiConfig = ApiConfig()
        self.ui: UiConfig = UiConfig()
        self.bot: BotConfig = BotConfig()
        self.cloudflare: CloudflareConfig = CloudflareConfig()
        
        # Load configuration
        self._load_config()
    
    def _load_config(self):
        """Load configuration from files and environment."""
        config_file = self.config_dir / "config.json"
        if not config_file.exists() and is_frozen():
            # Client builds may ship bundle.config.json (Worker URL + token baked at compile time).
            bundled = BUNDLE_DIR / "config" / "bundle.config.json"
            example = BUNDLE_DIR / "config" / "config.example.json"
            template = bundled if bundled.exists() else example
            if template.exists():
                try:
                    shutil.copy2(template, config_file)
                    logger.info("Copied bundled config template to %s", config_file)
                except Exception as e:
                    logger.warning("Could not copy default config: %s", e)

        if config_file.exists():
            self._load_json_config(str(config_file))
        
        # Override with environment variables
        self._load_env_config()

        # Installed .exe: Gemini/OpenAI keys must come from Cloudflare only (not config / env).
        if is_frozen():
            self._enforce_cloudflare_remote_keys_only()
        elif self.cloudflare.is_configured():
            self._fetch_from_cloudflare()

        self._resolve_database_paths()
        
        # Ensure directories exist
        self.database.ensure_directories()
        
        # Validate critical configuration
        if not self.telegram:
            logger.warning("Telegram configuration not found. Run setup wizard.")

    def _enforce_cloudflare_remote_keys_only(self) -> None:
        """PyInstaller build: LLM keys must be fetched from Cloudflare (not stored in shipped config)."""
        if not self.cloudflare.is_configured():
            _fatal_installer(
                "Cloudflare Worker required",
                "This app loads Gemini and OpenAI keys only from your Cloudflare Worker "
                "(they are not read from config.json, so API keys are not exposed on disk).\n\n"
                "Set cloudflare.enabled, worker_url, and auth_token in:\n\n"
                f"{self.config_dir / 'config.json'}\n\n"
                "Your Worker must implement GET …/api/keys returning JSON with "
                "gemini_key and/or openai_key.",
            )

        ok = self._fetch_from_cloudflare()
        if not ok:
            _fatal_installer(
                "Could not reach Cloudflare Worker",
                "Check worker_url, auth_token, network, and Worker /api/keys.\n\n"
                f"See log:\n{USER_DATA_DIR / 'logs' / 'bot.log'}",
            )

        if not self.api.gemini_api_key and not self.api.openai_api_key:
            _fatal_installer(
                "Worker returned no API keys",
                "GET /api/keys succeeded but the JSON did not include gemini_key or openai_key.",
            )

    def _resolve_database_paths(self):
        """Store DB, sessions, and backups under USER_DATA_DIR when paths are relative."""
        root = USER_DATA_DIR
        for attr in ("db_path", "session_dir", "backup_dir"):
            val = getattr(self.database, attr, None)
            if not val:
                continue
            p = Path(val)
            if not p.is_absolute():
                setattr(self.database, attr, str((root / val).resolve()))
    
    def _load_json_config(self, config_path: str):
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # Load Telegram config
            if 'telegram' in config_data:
                telegram_data = config_data['telegram']
                self.telegram = TelegramConfig(
                    api_id=telegram_data.get('api_id'),
                    api_hash=telegram_data.get('api_hash'),
                    phone_number=telegram_data.get('phone_number')
                )
            
            # Load API config (models from file; keys from file only when not frozen)
            if 'api' in config_data:
                api_data = config_data['api']
                self.api.openai_model = api_data.get('openai_model', 'gpt-4o-mini')
                self.api.gemini_model = api_data.get('gemini_model', 'gemini-2.5-flash')
                self.api.request_timeout = api_data.get('timeout', 30)
                if is_frozen():
                    logger.info(
                        "Installed build: OpenAI/Gemini API keys are not read from config "
                        "(Cloudflare Worker only)."
                    )
                else:
                    self.api.openai_api_key = api_data.get('openai_api_key') or api_data.get(
                        'openai_key'
                    )
                    self.api.gemini_api_key = api_data.get('gemini_api_key') or api_data.get(
                        'gemini_key'
                    )
                    logger.info(
                        "API keys from config: gemini=%s, openai=%s",
                        "set" if self.api.gemini_api_key else "missing",
                        "set" if self.api.openai_api_key else "missing",
                    )
            
            # Load Database config
            if 'database' in config_data:
                db_data = config_data['database']
                self.database.db_path = db_data.get('path', 'telegrambot.db')
                self.database.session_dir = db_data.get('session_dir', 'pyrogram_sessions')
                self.database.backup_dir = db_data.get('backup_dir', 'backups')
            
            # Load UI config
            if 'ui' in config_data:
                ui_data = config_data['ui']
                self.ui.theme = ui_data.get('theme', 'Dark')
                self.ui.window_width = ui_data.get('window_width', 1200)
                self.ui.window_height = ui_data.get('window_height', 800)
            
            # Load Bot config
            if 'bot' in config_data:
                bot_data = config_data['bot']
                self.bot.of_link = bot_data.get('of_link')
                self.bot.read_delay_min = bot_data.get('read_delay_min', 1.5)
                self.bot.read_delay_max = bot_data.get('read_delay_max', 4.0)
                self.bot.max_typing_delay = bot_data.get('max_typing_delay', 12.0)
                self.bot.conversation_timeout = bot_data.get('conversation_timeout', 180)
                self.bot.debug_logging = bot_data.get('debug_logging', False)
                self.bot.test_user_ids = bot_data.get('test_user_ids', [])
            
            # Load Cloudflare config
            if 'cloudflare' in config_data:
                cf_data = config_data['cloudflare']
                to = cf_data.get('timeout', 30)
                try:
                    to = int(to)
                except (TypeError, ValueError):
                    to = 30
                self.cloudflare = CloudflareConfig(
                    enabled=_json_bool(cf_data.get('enabled'), False),
                    worker_url=_strip_opt(cf_data.get('worker_url')),
                    auth_token=_strip_opt(cf_data.get('auth_token')),
                    fallback_to_local=_json_bool(cf_data.get('fallback_to_local'), True),
                    timeout=to,
                )
            
            logger.info(f"Configuration loaded from {config_path}")
        
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
    
    def _load_env_config(self):
        """Load configuration from environment variables."""
        # Telegram
        if os.getenv('TELEGRAM_API_ID'):
            if not self.telegram:
                self.telegram = TelegramConfig(
                    api_id=int(os.getenv('TELEGRAM_API_ID')),
                    api_hash=os.getenv('TELEGRAM_API_HASH'),
                    phone_number=os.getenv('TELEGRAM_PHONE')
                )
        
        # API keys via env — dev/source only (installed app uses Cloudflare only)
        if not is_frozen():
            if os.getenv('OPENAI_API_KEY'):
                self.api.openai_api_key = os.getenv('OPENAI_API_KEY')

            if os.getenv('GEMINI_API_KEY'):
                self.api.gemini_api_key = os.getenv('GEMINI_API_KEY')

        if os.getenv('TELEGRAM_BOT_DB'):
            self.database.db_path = os.getenv('TELEGRAM_BOT_DB')
    
    def _fetch_from_cloudflare(self) -> bool:
        """
        Fetch API keys from Cloudflare Worker.

        Uses ``requests`` (bundled CA certs) for reliable HTTPS in frozen Windows builds;
        raw ``urllib`` often fails TLS verification in PyInstaller without extra hooks.

        Returns:
            True if successful, False otherwise
        """
        import requests
        from requests import exceptions as req_exc

        if not self.cloudflare.is_configured():
            logger.warning("Cloudflare not properly configured (url, token missing)")
            return False

        url = f"{self.cloudflare.worker_url.rstrip('/')}/api/keys"
        headers = {
            "Authorization": f"Bearer {self.cloudflare.auth_token}",
            "User-Agent": "TelegramBot/1.0",
        }
        # Slow DNS / TLS on some PCs; bundled template may use 10s — floor at 30s.
        timeout = max(float(self.cloudflare.timeout), 30.0)

        def _log_http_error(status: int, reason: str, body_snip: str) -> None:
            if body_snip:
                logger.error("Cloudflare error response body: %s", body_snip)
            if status == 401:
                logger.error(
                    "Cloudflare auth failed (401) — check auth_token in config.json matches "
                    "BOT_AUTH_TOKEN in the worker"
                )
            elif status == 404:
                logger.error(
                    "Cloudflare worker not found (404) — check worker_url: %s",
                    self.cloudflare.worker_url,
                )
            elif status == 500:
                logger.error(
                    "Cloudflare worker returned 500 — often BOT_AUTH_TOKEN or GEMINI/OPENAI "
                    "env is misconfigured; read response body above"
                )
            else:
                logger.error("Cloudflare HTTP %s: %s", status, reason)

        try:
            logger.info("Fetching API keys from Cloudflare: %s", self.cloudflare.worker_url)
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code != 200:
                _log_http_error(
                    r.status_code,
                    getattr(r, "reason", "") or "",
                    (r.text or "")[:800],
                )
                logger.warning("Cloudflare key fetch failed (HTTP error)")
                return False
            try:
                data = r.json()
            except ValueError as e:
                logger.error("Cloudflare returned invalid JSON: %s", e)
                return False

            if data.get("gemini_key"):
                self.api.gemini_api_key = data["gemini_key"]
                logger.info("Gemini API key loaded from Cloudflare")

            if data.get("openai_key"):
                self.api.openai_api_key = data["openai_key"]
                logger.info("OpenAI API key loaded from Cloudflare")

            logger.info("API keys fetched from Cloudflare")
            return True

        except req_exc.SSLError as e:
            logger.error(
                "Cloudflare TLS/SSL error (requests) — common with strict PCs or outdated CA store: %s",
                e,
            )
            logger.warning("Cloudflare key fetch failed (network)")
            return False
        except req_exc.Timeout:
            logger.error(
                "Cloudflare request timed out after %ss — check network, DNS, or firewall",
                timeout,
            )
            logger.warning("Cloudflare key fetch failed (network)")
            return False
        except req_exc.RequestException as e:
            logger.error("Cloudflare request error: %s", e)
            logger.warning("Cloudflare key fetch failed (network)")
            return False

        except Exception as e:
            logger.error("Error fetching from Cloudflare: %s", e, exc_info=True)
            logger.warning("Cloudflare key fetch failed (network)")
            return False
    
    def save_config(self) -> bool:
        """Save current configuration to JSON file."""
        try:
            # API keys are intentionally excluded — they are fetched at runtime
            # from Cloudflare and must never be persisted locally so the same
            # Cloudflare worker is always the single source of truth across PCs.
            config_data = {
                'telegram': asdict(self.telegram) if self.telegram else {},
                'api': {
                    'openai_model': self.api.openai_model,
                    'gemini_model': self.api.gemini_model,
                    'timeout': self.api.request_timeout,
                },
                'database': asdict(self.database),
                'ui': asdict(self.ui),
                'bot': asdict(self.bot),
                'cloudflare': asdict(self.cloudflare),
            }
            
            config_file = self.config_dir / "config.json"
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            logger.info(f"Configuration saved to {config_file}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False
    
    def create_default_config(self) -> bool:
        """Create a default configuration template."""
        default_config = {
            "_WARNING": "DO NOT SHARE THIS FILE - IT CONTAINS SENSITIVE CREDENTIALS",
            "_LEGAL_NOTICE": {
                "mode": "USER ACCOUNT (not Bot API)",
                "risks": [
                    "Users will NOT know they're chatting with automation - they'll think you're replying",
                    "Automating user accounts violates Telegram Terms of Service",
                    "If this file is compromised, your entire Telegram account is at risk",
                    "Session files in pyrogram_sessions/ contain your login credentials",
                    "This setup ONLY works for your personal account - cannot be shared with others",
                    "For a compliant, shareable bot use Bot API with @BotFather instead"
                ],
                "how_to_get_credentials": "Visit https://my.telegram.org/apps with YOUR Telegram account and create an app"
            },
            "telegram": {
                "api_id": 0,
                "api_hash": "YOUR_API_HASH_HERE (get from my.telegram.org/apps)",
                "phone_number": "+1234567890 (your Telegram account phone)"
            },
            "api": {
                "openai_model": "gpt-4o-mini",
                "gemini_model": "gemini-2.5-flash",
                "timeout": 30
            },
            "database": {
                "path": "telegrambot.db",
                "session_dir": "pyrogram_sessions",
                "backup_dir": "backups"
            },
            "ui": {
                "theme": "Dark",
                "window_width": 1200,
                "window_height": 800,
                "font_size": 10
            },
            "bot": {
                "of_link": None
            },
            "cloudflare": {
                "enabled": True,
                "worker_url": "https://YOUR-WORKER.YOUR_SUBDOMAIN.workers.dev",
                "auth_token": "YOUR-WORKER-BEARER-TOKEN",
                "fallback_to_local": False,
                "timeout": 10
            },
            "_llm_keys_note": "Installed (.exe) builds: OpenAI/Gemini keys are fetched from Cloudflare Worker only — never put sk- or AI keys in this JSON."
        }
        
        try:
            config_file = self.config_dir / "config.json"
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            
            logger.info(f"Default configuration created at {config_file}")
            print(f"\n⚠️  IMPORTANT: Edit {config_file} with your Telegram API credentials!")
            print("   You can get API credentials from: https://my.telegram.org/apps")
            return True
        
        except Exception as e:
            logger.error(f"Failed to create default config: {e}")
            return False
    
    def validate(self) -> bool:
        """Validate that all required configuration is present."""
        errors = []
        
        # Check Telegram credentials
        if not self.telegram or not self.telegram.validate():
            errors.append("Telegram API credentials missing (api_id, api_hash)")
        
        # Check database path
        if not self.database.db_path:
            errors.append("Database path not configured")
        
        # LLM keys: required from config/env when running from source; installed app uses Cloudflare only
        if not is_frozen():
            if not self.api.openai_api_key and not self.api.gemini_api_key:
                errors.append("No API provider configured (OpenAI or Gemini)")
        
        if errors:
            for error in errors:
                logger.error(f"Configuration error: {error}")
            return False

        logger.info("Configuration validation passed")
        return True


def get_config() -> ConfigManager:
    """Get or create global configuration instance."""
    if not hasattr(get_config, '_instance'):
        get_config._instance = ConfigManager()
    return get_config._instance


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and show default configuration
    config = ConfigManager()
    success = config.create_default_config()
    
    if success:
        print("\nConfiguration template created.")
        print("Edit config/config.json with your credentials and run the app again.")
    else:
        print("\nFailed to create configuration.")
