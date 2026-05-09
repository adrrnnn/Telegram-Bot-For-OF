"""
UI Tabs Package
"""

from .accounts_tab import TelegramAccountsTab
from .profiles_tab import ModelProfilesTab
from .link_tab import ChangeOFLinkTab
from .start_bot_tab import StartBotTab
from .reset_tab import ResetBotTab

__all__ = [
    'TelegramAccountsTab',
    'ModelProfilesTab',
    'ChangeOFLinkTab',
    'StartBotTab',
    'ResetBotTab',
]
