#!/usr/bin/env python3
"""
GUI Launcher for Telegram Bot

.pyw extension automatically hides console window on Windows
"""

import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.runtime_paths import USER_DATA_DIR

# Import and run main application
from main import main

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        # Log to file instead of console for GUI mode
        try:
            (USER_DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
            error_log = USER_DATA_DIR / "logs" / "error.log"
            with open(error_log, "a", encoding="utf-8") as f:
                f.write(f"Fatal error: {e}\n")
        except Exception:
            pass
        sys.exit(1)
