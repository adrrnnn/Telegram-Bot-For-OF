"""
Reset Bot Tab - clears all data rows while keeping the DB schema intact.
"""

import logging
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QCheckBox,
    QPushButton, QHBoxLayout, QMessageBox
)
from src.database import DatabaseManager
from src.config import ConfigManager
from src.runtime_paths import USER_DATA_DIR

logger = logging.getLogger(__name__)


class ResetBotTab(QWidget):
    """Wipes all user data (accounts, profiles, conversations, logs) without dropping tables."""

    def __init__(self, db: DatabaseManager, config: ConfigManager):
        super().__init__()
        self.db = db
        self.config = config
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        warning = QLabel("WARNING: This operation cannot be undone.")
        warning.setStyleSheet("font-weight: bold; color: #FF9900;")
        layout.addWidget(warning)

        info = QLabel(
            "The following will be permanently deleted:\n\n"
            "  • All Telegram accounts\n"
            "  • All model profiles\n"
            "  • All conversations and messages\n"
            "  • All audit log entries\n"
            "  • All log files\n\n"
            "The database file and schema will remain."
        )
        layout.addWidget(info)

        self.confirm_checkbox = QCheckBox("I understand this will delete all data permanently")
        layout.addWidget(self.confirm_checkbox)

        button_layout = QHBoxLayout()
        self.reset_btn = QPushButton("Reset Everything")
        self.reset_btn.setEnabled(False)
        self.reset_btn.clicked.connect(self._reset)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(lambda: self.confirm_checkbox.setChecked(False))

        self.confirm_checkbox.stateChanged.connect(
            lambda state: self.reset_btn.setEnabled(state == 2)
        )

        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        layout.addStretch()
        self.setLayout(layout)

    def _reset(self):
        reply = QMessageBox.question(
            self,
            "Confirm Reset",
            "Are you sure? This will delete all accounts, profiles, and conversations.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        errors = []

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                tables = [
                    "messages",
                    "conversations",
                    "api_usage_billing",
                    "api_keys",
                    "audit_log",
                    "deleted_accounts",
                    "profiles",
                    "accounts",
                ]
                for table in tables:
                    try:
                        cursor.execute(f"DELETE FROM {table}")
                    except Exception as e:
                        errors.append(f"{table}: {e}")
        except Exception as e:
            errors.append(f"Database: {e}")

        # Clear log files
        logs_dir = USER_DATA_DIR / "logs"
        if logs_dir.exists():
            for log_file in logs_dir.glob("*.log"):
                try:
                    log_file.unlink()
                except Exception as e:
                    errors.append(f"{log_file.name}: {e}")

        self.confirm_checkbox.setChecked(False)

        if errors:
            logger.error(f"Reset completed with errors: {errors}")
            QMessageBox.warning(
                self,
                "Reset Completed with Errors",
                "Reset finished but some items could not be cleared:\n\n" + "\n".join(errors),
            )
        else:
            logger.info("Bot reset completed successfully")
            QMessageBox.information(self, "Reset Complete", "All data has been cleared.")
