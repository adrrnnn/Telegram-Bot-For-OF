"""
Telegram Bot UI Package - PyQt5-based desktop application.

Modules:
  - screens: All 6 screen layouts (home, accounts, profiles, settings, monitor, logs)
  - main_window: Main window manager with event loop
"""

__version__ = "1.0.19"

from .main_window import TelegramBotMainWindow
from .screens import (
    create_home_screen,
    create_accounts_screen,
    create_profiles_screen,
    create_settings_screen,
    create_monitor_screen,
    create_logs_screen
)

__all__ = [
    'TelegramBotMainWindow',
    'create_home_layout',
    'create_accounts_layout',
    'create_profiles_layout',
    'create_settings_layout',
    'create_monitor_layout',
    'create_logs_layout',
]
