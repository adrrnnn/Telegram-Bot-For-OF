"""
PyQt5 Main Window for Telegram Bot UI.

Manages:
- Window creation and layout
- Tab navigation (6 screens)
- Database integration
- Event handling and signals
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QStatusBar, QTabWidget, QLabel
from PyQt5.QtCore import Qt, QTimer

from .screens import (
    create_home_screen,
    create_accounts_screen,
    create_profiles_screen,
    create_settings_screen,
    create_monitor_screen,
    create_logs_screen
)
from src.database import DatabaseManager
from src.config import ConfigManager

logger = logging.getLogger(__name__)


class TelegramBotMainWindow(QMainWindow):
    """Main application window using PyQt5."""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None, 
                 config_manager: Optional[ConfigManager] = None,
                 event_queue = None):
        """
        Initialize main window.
        
        Args:
            db_manager: Database connection manager
            config_manager: Configuration manager
            event_queue: Queue for bot events (future)
        """
        super().__init__()
        
        self.db = db_manager
        self.config = config_manager
        self.event_queue = event_queue
        
        # Window properties
        self.setWindowTitle("Telegram Bot Manager")
        self.setGeometry(100, 100, 1200, 800)
        
        # Setup UI
        self._create_ui()
        self._setup_timer()
        
        logger.info("Main window initialized")
    
    def _create_ui(self):
        """Create the main UI layout."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Tab widget with 6 screens
        self.tabs = QTabWidget()
        
        # Add screens
        self.home_screen = create_home_screen(self.db)
        self.accounts_screen = create_accounts_screen(self.db)
        self.profiles_screen = create_profiles_screen(self.db)
        self.settings_screen = create_settings_screen(self.db, self.config)
        self.monitor_screen = create_monitor_screen(self.db)
        self.logs_screen = create_logs_screen(self.db)
        
        self.tabs.addTab(self.home_screen, "🏠 Home")
        self.tabs.addTab(self.accounts_screen, "👤 Accounts")
        self.tabs.addTab(self.profiles_screen, "🎭 Profiles")
        self.tabs.addTab(self.settings_screen, "⚙️ Settings")
        self.tabs.addTab(self.monitor_screen, "📊 Monitor")
        self.tabs.addTab(self.logs_screen, "📋 Logs")
        
        # Connect tab change event
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        main_layout.addWidget(self.tabs)
        
        # Status bar
        self._setup_status_bar()
    
    def _setup_status_bar(self):
        """Setup status bar at bottom."""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        
        self.status_label = QLabel("Ready")
        self.time_label = QLabel()
        self.stats_label = QLabel()
        
        status_bar.addWidget(self.status_label, 1)
        status_bar.addPermanentWidget(self.stats_label, 0)
        status_bar.addPermanentWidget(self.time_label, 0)
        
        self._update_status_bar()
    
    def _update_status_bar(self):
        """Update status bar with current stats."""
        try:
            if self.db:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("SELECT COUNT(*) FROM accounts")
                    account_count = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM profiles")
                    profile_count = cursor.fetchone()[0]
                    
                    self.stats_label.setText(
                        f"Accounts: {account_count} | Profiles: {profile_count}"
                    )
        except Exception as e:
            logger.error(f"Error updating status: {e}")
        
        # Update time
        current_time = datetime.now().strftime("%H:%M:%S")
        self.time_label.setText(f"{current_time}")
    
    def _setup_timer(self):
        """Setup timer for periodic updates."""
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_status_bar)
        self.timer.start(1000)
    
    def _on_tab_changed(self, index: int):
        """Handle tab change and refresh data."""
        if index == 0 and hasattr(self.home_screen, 'refresh'):
            self.home_screen.refresh()
        elif index == 1 and hasattr(self.accounts_screen, 'refresh'):
            self.accounts_screen.refresh()
        elif index == 2 and hasattr(self.profiles_screen, 'refresh'):
            self.profiles_screen.refresh()
        elif index == 4 and hasattr(self.monitor_screen, 'refresh'):
            self.monitor_screen.refresh()
        elif index == 5 and hasattr(self.logs_screen, 'refresh'):
            self.logs_screen.refresh()
    
    def closeEvent(self, event):
        """Handle window close event."""
        self.timer.stop()
        logger.info("Application closed")
        event.accept()
