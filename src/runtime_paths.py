"""
Writable vs read-only bundle paths.

When frozen (PyInstaller), the install directory under Program Files is not writable
for normal users. All persistent data must go under %APPDATA%\\TelegramBot.
"""

import os
import sys
from pathlib import Path

_APP_NAME = "TelegramBot"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def bundle_dir() -> Path:
    """Directory containing bundled code and assets (_internal when frozen)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """Directory for logs, config, database, and session files."""
    if is_frozen():
        base = os.environ.get("APPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
        return Path(base) / _APP_NAME
    return Path(__file__).resolve().parent.parent


USER_DATA_DIR = user_data_dir()
BUNDLE_DIR = bundle_dir()


def ensure_user_dirs() -> None:
    """Create standard writable folders under USER_DATA_DIR."""
    (USER_DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
    (USER_DATA_DIR / "config").mkdir(parents=True, exist_ok=True)
