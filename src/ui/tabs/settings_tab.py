from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QCheckBox, QScrollArea
)
from src.config import ConfigManager
from src.database import DatabaseManager
from src.ui.tabs.reset_tab import ResetBotTab


class SettingsTab(QWidget):
    """Settings tab — logging toggle and danger-zone actions."""

    def __init__(self, db: DatabaseManager, config: ConfigManager):
        super().__init__()
        self.db = db
        self.config = config
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)

        log_group = QGroupBox("Logging")
        log_form = QFormLayout(log_group)
        self.debug_check = QCheckBox("Enable debug logging")
        self.debug_check.setToolTip(
            "Shows classifier state, system prompt hints, and full LLM details in the log panel."
        )
        self.debug_check.stateChanged.connect(self._apply)
        log_form.addRow(self.debug_check)
        layout.addWidget(log_group)

        reset_group = QGroupBox("Reset Bot")
        reset_layout = QVBoxLayout(reset_group)
        self._reset_widget = ResetBotTab(db=self.db, config=self.config)
        reset_layout.addWidget(self._reset_widget)
        layout.addWidget(reset_group)

        layout.addStretch()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _load_values(self):
        self.debug_check.setChecked(self.config.bot.debug_logging)
        self._apply()

    def _apply(self):
        enabled = self.debug_check.isChecked()
        self.config.bot.debug_logging = enabled
        self.config.save_config()

        import logging as _logging
        if enabled:
            _logging.getLogger().setLevel(_logging.DEBUG)
        else:
            _logging.getLogger().setLevel(_logging.INFO)
            for noisy in ("pyrogram", "openai", "httpx", "httpcore", "asyncio"):
                _logging.getLogger(noisy).setLevel(_logging.WARNING)
