#!/usr/bin/env python3
"""
Usage:
    python main.py              # Start the application
    python main.py --setup      # Print setup instructions
    python main.py --db-init    # Initialise the database and exit
"""

import sys
import logging
import ctypes
from pathlib import Path

# Bootstrap import path (project root or PyInstaller _MEIPASS)
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.runtime_paths import USER_DATA_DIR, ensure_user_dirs, is_frozen

ensure_user_dirs()

# Ensure logs directory exists before setting up file handler
log_handlers = [
    logging.FileHandler(USER_DATA_DIR / "logs" / "bot.log")
]

# Only log to console if running from terminal (not .pyw or detached)
if sys.stdin and sys.stdout:
    try:
        log_handlers.append(logging.StreamHandler())
    except Exception:
        pass

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)

# Suppress noisy third-party loggers by default
for _noisy in ("pyrogram", "pyrogram.session", "pyrogram.connection", "openai", "httpx", "httpcore", "asyncio"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

logger.warning(
    "Running in USER ACCOUNT mode — this automates a personal Telegram account, "
    "not a bot. Session files contain your login credentials; keep them secure."
)


def run_setup_wizard():
    """Run initial configuration setup."""
    logger.info("Running configuration setup wizard...")
    
    try:
        from src.config import ConfigManager
        
        config = ConfigManager()
        
        # Create default config template
        if not (USER_DATA_DIR / "config" / "config.json").exists():
            config.create_default_config()
        
        cfg_file = USER_DATA_DIR / "config" / "config.json"
        print("\n" + "=" * 60)
        print("TELEGRAM BOT - SETUP WIZARD")
        print("=" * 60)
        print("\n1. Get your Telegram API credentials from: https://my.telegram.org/apps")
        print("   - Create an app and copy api_id and api_hash")
        print(f"\n2. Edit this file and add your credentials:\n   {cfg_file}")
        if is_frozen():
            print(
                "\n3. Configure Cloudflare Worker in the same file (installed build):\n"
                "   - cloudflare.enabled, worker_url, auth_token\n"
                "   - LLM keys are fetched from GET …/api/keys only (never put sk- or Gemini keys in JSON)."
            )
            print("\n4. Run the bot again (or launch Telegram Bot from Start Menu)")
        else:
            print("\n3. (Optional) Add OpenAI API key to the same file or set OPENAI_API_KEY")
            print("   - Get from: https://platform.openai.com/api-keys")
            print("\n4. (Optional) Add Google Gemini API key or set GEMINI_API_KEY")
            print("   - Get from: https://ai.google.dev/")
            print(
                "\n   Or configure cloudflare in config.json to fetch keys from your Worker "
                "(recommended for distributed builds)."
            )
            print("\n5. Run the bot again (or launch Telegram Bot from Start Menu)")
        print("=" * 60 + "\n")
        
        return True
    
    except Exception as e:
        logger.error(f"Setup error: {e}")
        return False


def run_application():
    """Launch the main application UI with Telegram bot backend."""
    logger.info("Launching Telegram Bot application...")
    
    try:
        # Initialize backend
        from src.database import DatabaseManager
        from src.config import ConfigManager
        
        config = ConfigManager()
        db = DatabaseManager(config.database.db_path)
        db.initialize_database()  # Create schema if needed
        
        logger.info("Loading PyQt5 GUI...")

        from src.torch_bootstrap import preload_torch

        preload_torch()

        # Import PyQt5 and new GUI
        from PyQt5.QtWidgets import QApplication
        from src.app_instance_lock import acquire_single_instance
        from src.ui.main_gui import TelegramBotMainWindow

        if not acquire_single_instance():
            return True

        # Create Qt Application
        app = QApplication(sys.argv)
        
        # Hide console window on Windows (after Qt app created)
        if sys.platform == 'win32':
            try:
                hwnd = ctypes.windll.kernel32.GetConsoleWindow()
                if hwnd != 0:
                    ctypes.windll.kernel32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
            except Exception:
                pass
        
        # Create and show window
        logger.info("Opening main window...")
        
        window = TelegramBotMainWindow(db_manager=db, config_manager=config)
        window.show()
        
        # Bot will be started when user clicks "Start Bot" tab
        logger.info("GUI ready. Bot will start when user clicks 'Start Bot' tab.")
        
        # Run event loop
        result = app.exec_()
        
        logger.info("Application closed normally")
        return result == 0
    
    except Exception as e:
        logger.error(f"Application error: {e}")
        logger.exception("Full traceback:")
        return False


def parse_args():
    """Parse command line arguments."""
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        if arg == "--setup":
            return "setup"
        elif arg == "--db-init":
            return "db-init"
        elif arg in ["--help", "-h"]:
            return "help"
    
    return "run"


def show_help():
    """Show help message."""
    print(__doc__)


def main():
    """Main application entry point."""
    command = parse_args()
    
    if command == "help":
        show_help()
        return 0
    
    elif command == "setup":
        success = run_setup_wizard()
        return 0 if success else 1
    
    elif command == "db-init":
        from src.database import initialize_database_with_defaults
        success = initialize_database_with_defaults()
        return 0 if success else 1
    
    else:  # command == "run"
        success = run_application()
        return 0 if success else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n✓ Shutdown requested")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
