"""
PyQt5 Screen Layouts for Telegram Bot UI.

Provides functions to create each of the 6 main screens:
1. Home - Dashboard with stats and activity
2. Accounts - Account management
3. Profiles - Profile management
4. Settings - Configuration
5. Monitor - Real-time monitoring
6. Logs - Activity history
"""

import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QGroupBox, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from src.database import DatabaseManager
from src.config import ConfigManager

logger = logging.getLogger(__name__)


def create_home_screen(db: DatabaseManager) -> QWidget:
    """Create home/dashboard screen."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    
    # Title
    title = QLabel("Dashboard")
    title_font = QFont()
    title_font.setPointSize(14)
    title_font.setBold(True)
    title.setFont(title_font)
    layout.addWidget(title)
    
    # Stats grid
    stats_layout = QGridLayout()
    
    # Create stat boxes
    stats = {
        "Accounts": "0",
        "Profiles": "0",
        "Conversations": "0",
        "Status": "●"
    }
    
    for i, (key, value) in enumerate(stats.items()):
        stat_box = QGroupBox(key)
        stat_layout = QVBoxLayout(stat_box)
        stat_label = QLabel(value)
        stat_label_font = QFont()
        stat_label_font.setPointSize(16)
        stat_label_font.setBold(True)
        stat_label.setFont(stat_label_font)
        stat_layout.addWidget(stat_label)
        stat_box.setObjectName(f"stat_{key.lower()}")
        stats_layout.addWidget(stat_box, 0, i)
    
    layout.addLayout(stats_layout)
    
    # Activity log
    activity_label = QLabel("Recent Activity")
    activity_label.setFont(QFont("Arial", 10, QFont.Bold))
    layout.addWidget(activity_label)
    
    activity_log = QTextEdit()
    activity_log.setReadOnly(True)
    activity_log.setObjectName("activity_log")
    activity_log.setMaximumHeight(150)
    layout.addWidget(activity_log)
    
    # Quick action buttons
    button_layout = QHBoxLayout()
    buttons = ["Add Account", "Create Profile", "Start Monitoring", "View Settings"]
    for btn_text in buttons:
        btn = QPushButton(btn_text)
        btn.setObjectName(f"btn_{btn_text.lower().replace(' ', '_')}")
        button_layout.addWidget(btn)
    
    layout.addLayout(button_layout)
    layout.addStretch()
    
    # Add refresh method
    def refresh():
        try:
            if db:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("SELECT COUNT(*) FROM accounts")
                    accounts = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM profiles")
                    profiles = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM conversations")
                    conversations = cursor.fetchone()[0]
                    
                    # Update stat labels
                    layout.itemAt(1).itemAt(0).widget().findChild(QLabel).setText(str(accounts))
                    layout.itemAt(1).itemAt(1).widget().findChild(QLabel).setText(str(profiles))
                    layout.itemAt(1).itemAt(2).widget().findChild(QLabel).setText(str(conversations))
        except Exception as e:
            logger.error(f"Error refreshing home screen: {e}")
    
    widget.refresh = refresh
    return widget


def create_accounts_screen(db: DatabaseManager) -> QWidget:
    """Create accounts management screen."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    
    # Title
    title = QLabel("Manage Accounts")
    title_font = QFont()
    title_font.setPointSize(12)
    title_font.setBold(True)
    title.setFont(title_font)
    layout.addWidget(title)
    
    # Search bar
    search_layout = QHBoxLayout()
    search_label = QLabel("Search:")
    search_input = QLineEdit()
    search_input.setPlaceholderText("Filter by username...")
    search_button = QPushButton("Search")
    search_button.setMaximumWidth(80)
    search_layout.addWidget(search_label)
    search_layout.addWidget(search_input)
    search_layout.addWidget(search_button)
    layout.addLayout(search_layout)
    
    # Accounts table
    table = QTableWidget()
    table.setColumnCount(6)
    table.setHorizontalHeaderLabels(["ID", "Username", "Email", "Status", "Phone", "Created"])
    table.setObjectName("accounts_table")
    layout.addWidget(table)
    
    # Add account form
    form_group = QGroupBox("Add New Account")
    form_layout = QFormLayout(form_group)
    
    username_input = QLineEdit()
    email_input = QLineEdit()
    phone_input = QLineEdit()
    password_input = QLineEdit()
    password_input.setEchoMode(QLineEdit.Password)
    
    form_layout.addRow("Username:", username_input)
    form_layout.addRow("Email:", email_input)
    form_layout.addRow("Phone:", phone_input)
    form_layout.addRow("Password:", password_input)
    
    layout.addWidget(form_group)
    
    # Action buttons
    button_layout = QHBoxLayout()
    buttons = ["Add Account", "Edit", "Delete", "Test", "Export"]
    for btn_text in buttons:
        btn = QPushButton(btn_text)
        btn.setObjectName(f"btn_{btn_text.lower()}")
        button_layout.addWidget(btn)
    
    layout.addLayout(button_layout)
    layout.addStretch()
    
    # Add refresh method
    def refresh():
        try:
            if db:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, username, email, status, phone, created_at FROM accounts")
                    rows = cursor.fetchall()
                    
                    table.setRowCount(0)
                    for row_idx, row in enumerate(rows):
                        table.insertRow(row_idx)
                        for col_idx, value in enumerate(row):
                            item = QTableWidgetItem(str(value))
                            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                            table.setItem(row_idx, col_idx, item)
        except Exception as e:
            logger.error(f"Error loading accounts: {e}")
    
    widget.refresh = refresh
    return widget


def create_profiles_screen(db: DatabaseManager) -> QWidget:
    """Create profiles management screen."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    
    # Title
    title = QLabel("Manage Profiles")
    title.setFont(QFont("Arial", 12, QFont.Bold))
    layout.addWidget(title)
    
    # Account selector
    account_layout = QHBoxLayout()
    account_label = QLabel("Select Account:")
    account_combo = QComboBox()
    account_combo.setObjectName("account_selector")
    load_button = QPushButton("Load")
    load_button.setMaximumWidth(80)
    account_layout.addWidget(account_label)
    account_layout.addWidget(account_combo)
    account_layout.addWidget(load_button)
    account_layout.addStretch()
    layout.addLayout(account_layout)
    
    # Profiles list
    profile_table = QTableWidget()
    profile_table.setColumnCount(2)
    profile_table.setHorizontalHeaderLabels(["Profile Name", "Conversations"])
    profile_table.setObjectName("profiles_table")
    layout.addWidget(profile_table)
    
    # Profile form
    form_group = QGroupBox("Profile Details")
    form_layout = QFormLayout(form_group)
    
    name_input = QLineEdit()
    age_spin = QSpinBox()
    age_spin.setRange(1, 100)
    location_input = QLineEdit()
    tone_combo = QComboBox()
    tone_combo.addItems(["Neutral", "Friendly", "Professional", "Casual"])
    
    form_layout.addRow("Name:", name_input)
    form_layout.addRow("Age:", age_spin)
    form_layout.addRow("Location:", location_input)
    form_layout.addRow("Tone:", tone_combo)
    
    layout.addWidget(form_group)
    
    # Action buttons
    button_layout = QHBoxLayout()
    buttons = ["Add Profile", "Save", "Delete", "Duplicate"]
    for btn_text in buttons:
        btn = QPushButton(btn_text)
        button_layout.addWidget(btn)
    
    layout.addLayout(button_layout)
    layout.addStretch()
    
    # Add refresh method
    def refresh():
        try:
            if db:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Load accounts
                    cursor.execute("SELECT id, username FROM accounts")
                    accounts = cursor.fetchall()
                    account_combo.clear()
                    for acc_id, username in accounts:
                        account_combo.addItem(username, acc_id)
                    
                    # Load profiles if account selected
                    if account_combo.count() > 0:
                        cursor.execute("SELECT name, active FROM profiles LIMIT 10")
                        profiles = cursor.fetchall()
                        
                        profile_table.setRowCount(0)
                        for row_idx, (name, active) in enumerate(profiles):
                            profile_table.insertRow(row_idx)
                            profile_table.setItem(row_idx, 0, QTableWidgetItem(name))
                            profile_table.setItem(row_idx, 1, QTableWidgetItem(str(active)))
        except Exception as e:
            logger.error(f"Error loading profiles: {e}")
    
    widget.refresh = refresh
    return widget


def create_settings_screen(db: DatabaseManager, config: ConfigManager) -> QWidget:
    """Create settings configuration screen."""
    from src.ui.tabs.settings_tab import SettingsTab
    return SettingsTab(db, config)


def create_monitor_screen(db: DatabaseManager) -> QWidget:
    """Create real-time monitoring screen."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    
    # Title and status
    title_layout = QHBoxLayout()
    title = QLabel("Monitor - Real-time Activity")
    title.setFont(QFont("Arial", 12, QFont.Bold))
    status_label = QLabel("● STOPPED")
    uptime_label = QLabel("Uptime: 0h 0m")
    cpu_label = QLabel("CPU: 0%")
    title_layout.addWidget(title)
    title_layout.addWidget(status_label)
    title_layout.addWidget(uptime_label)
    title_layout.addWidget(cpu_label)
    title_layout.addStretch()
    layout.addLayout(title_layout)
    
    # Accounts table
    accounts_table = QTableWidget()
    accounts_table.setColumnCount(5)
    accounts_table.setHorizontalHeaderLabels(["Account", "Status", "Activity", "Conversations", "Msg/Hour"])
    layout.addWidget(accounts_table)
    
    # Activity log
    activity_label = QLabel("Live Activity Log")
    activity_label.setFont(QFont("Arial", 10, QFont.Bold))
    layout.addWidget(activity_label)
    
    activity_log = QTextEdit()
    activity_log.setReadOnly(True)
    activity_log.setMaximumHeight(200)
    layout.addWidget(activity_log)
    
    # Control buttons
    button_layout = QHBoxLayout()
    buttons = ["Start", "Pause", "Stop", "Clear", "Export"]
    for btn_text in buttons:
        btn = QPushButton(btn_text)
        button_layout.addWidget(btn)
    
    layout.addLayout(button_layout)
    
    # Add refresh method
    def refresh():
        try:
            if db:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT username, status FROM accounts LIMIT 10")
                    rows = cursor.fetchall()
                    
                    accounts_table.setRowCount(0)
                    for row_idx, (username, status) in enumerate(rows):
                        accounts_table.insertRow(row_idx)
                        accounts_table.setItem(row_idx, 0, QTableWidgetItem(username))
                        accounts_table.setItem(row_idx, 1, QTableWidgetItem(status or "Offline"))
        except Exception as e:
            logger.error(f"Error refreshing monitor: {e}")
    
    widget.refresh = refresh
    return widget


def create_logs_screen(db: DatabaseManager) -> QWidget:
    """Create activity logs screen."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    
    # Title
    title = QLabel("Activity Logs")
    title.setFont(QFont("Arial", 12, QFont.Bold))
    layout.addWidget(title)
    
    # Filters
    filter_layout = QHBoxLayout()
    filter_type = QComboBox()
    filter_type.addItems(["All", "Messages", "Conversations", "Errors", "API", "System"])
    account_filter = QComboBox()
    account_filter.addItem("All Accounts")
    
    filter_layout.addWidget(QLabel("Type:"))
    filter_layout.addWidget(filter_type)
    filter_layout.addWidget(QLabel("Account:"))
    filter_layout.addWidget(account_filter)
    filter_layout.addWidget(QPushButton("Apply"))
    filter_layout.addWidget(QPushButton("Clear"))
    filter_layout.addStretch()
    layout.addLayout(filter_layout)
    
    # Logs table
    logs_table = QTableWidget()
    logs_table.setColumnCount(5)
    logs_table.setHorizontalHeaderLabels(["Timestamp", "Type", "Account", "Description", "Status"])
    layout.addWidget(logs_table)
    
    # Event details
    details_label = QLabel("Event Details")
    details_label.setFont(QFont("Arial", 10, QFont.Bold))
    layout.addWidget(details_label)
    
    details_text = QTextEdit()
    details_text.setReadOnly(True)
    details_text.setMaximumHeight(100)
    layout.addWidget(details_text)
    
    # Action buttons
    button_layout = QHBoxLayout()
    buttons = ["Refresh", "Export CSV", "Export JSON", "Delete Old"]
    for btn_text in buttons:
        btn = QPushButton(btn_text)
        button_layout.addWidget(btn)
    
    layout.addLayout(button_layout)
    
    # Add refresh method
    def refresh():
        try:
            if db:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT timestamp, type, description FROM audit_log ORDER BY timestamp DESC LIMIT 20"
                    )
                    rows = cursor.fetchall()
                    
                    logs_table.setRowCount(0)
                    for row_idx, (timestamp, log_type, description) in enumerate(rows):
                        logs_table.insertRow(row_idx)
                        logs_table.setItem(row_idx, 0, QTableWidgetItem(str(timestamp)))
                        logs_table.setItem(row_idx, 1, QTableWidgetItem(log_type))
                        logs_table.setItem(row_idx, 2, QTableWidgetItem(""))
                        logs_table.setItem(row_idx, 3, QTableWidgetItem(description))
                        logs_table.setItem(row_idx, 4, QTableWidgetItem(""))
        except Exception as e:
            logger.error(f"Error loading logs: {e}")
    
    widget.refresh = refresh
    return widget
