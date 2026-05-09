"""
Start Bot Tab - Start and control the message listener bot
"""

import logging
import threading
import asyncio
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QPlainTextEdit, QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal, QMetaObject, Q_ARG
from src.database import DatabaseManager
from src.config import ConfigManager

logger = logging.getLogger(__name__)


class StartBotTab(QWidget):
    """Tab for starting bot and viewing logs"""

    # Signal is always delivered on the main thread regardless of which thread emits it
    _log_signal = pyqtSignal(str)
    # Fired from the bot thread when re-auth is needed; result fed back via _auth_result
    _reauth_needed = pyqtSignal(dict)  # emits account_data dict
    # Fired from the bot thread when the bot stops (any path) to reset UI
    _bot_stopped_signal = pyqtSignal(bool)  # True = clean stop, False = unexpected

    def __init__(self, db: DatabaseManager, config: ConfigManager):
        super().__init__()
        self.db = db
        self.config = config
        self.bot_running = False
        self.bot_paused = False
        self.bot_thread = None
        self.stop_event = threading.Event()
        # Used to pass re-auth result from GUI thread back to bot thread
        self._auth_result_event = threading.Event()
        self._auth_success = False
        self._reauth_needed.connect(self._on_reauth_needed)
        self._bot_stopped_signal.connect(self._on_bot_stopped)
        self._setup_ui()
        self._setup_logging()

    def _setup_logging(self):
        # Connect signal to appendPlainText so all updates land on the main thread
        self._log_signal.connect(self.log_display.appendPlainText)

        self.log_handler = LogCaptureHandler(self._log_signal)
        self.log_handler.setLevel(logging.DEBUG)
        self.log_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        logging.getLogger().addHandler(self.log_handler)

    def _setup_ui(self):
        layout = QVBoxLayout()

        self.status_label = QLabel("Status: ⚫ Ready to Start")
        layout.addWidget(self.status_label)

        button_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶ Start Bot")
        self.start_btn.clicked.connect(self.start_bot)
        self.pause_btn = QPushButton("⏸ Pause Bot")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)
        self.stop_btn = QPushButton("■ Stop Bot")
        self.stop_btn.clicked.connect(self.stop_bot)
        self.stop_btn.setEnabled(False)
        clear_logs_btn = QPushButton("Clear Logs")
        clear_logs_btn.clicked.connect(lambda: self.log_display.clear())

        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.pause_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(clear_logs_btn)
        layout.addLayout(button_layout)

        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setPlaceholderText("Logs will appear here when bot runs...")
        layout.addWidget(self.log_display)

        self.setLayout(layout)

    def start_bot(self):
        if self.bot_running:
            QMessageBox.warning(self, "Already Running", "Bot is already running!")
            return

        try:
            self.bot_running = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status_label.setText("Status: 🟢 Running")
            self.log_display.appendPlainText("\n[Bot Starting...]")

            self.bot_paused = False
            self.stop_event.clear()
            self.bot_thread = threading.Thread(target=self._run_bot_thread, daemon=True)
            self.bot_thread.start()
            self.pause_btn.setEnabled(True)

            logger.info("Bot thread started")

        except Exception as e:
            logger.error(f"Failed to start bot: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to start bot: {e}")
            self.bot_running = False
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("Status: ⚫ Ready to Start")

    def _on_bot_stopped(self, clean: bool):
        """Runs on the GUI thread — resets all Start Bot UI state."""
        self.bot_running = False
        self.bot_paused = False
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("⏸ Pause Bot")
        self.stop_btn.setEnabled(False)
        if clean:
            self.status_label.setText("Status: ⚫ Ready to Start")
            self.log_display.appendPlainText("[Bot Stopped]")
        else:
            self.status_label.setText("Status: ⚫ Stopped (unexpected)")
            self.log_display.appendPlainText("[Bot Stopped Unexpectedly]")

    def _on_reauth_needed(self, account_data: dict):
        """Runs on the main (GUI) thread — shows TelegramAuthDialog and reports result."""
        from src.ui.tabs.accounts_tab import TelegramAuthDialog, _delete_session

        phone = account_data.get("phone", "")
        _delete_session(phone, self.config)

        auth_dialog = TelegramAuthDialog(
            self, account_data, session_workdir=self.config.database.session_dir
        )
        auth_dialog.start_auth()
        result = auth_dialog.exec_()

        self._auth_success = result == auth_dialog.Accepted
        self._auth_result_event.set()

    def _run_bot_thread(self):
        try:
            from src.ui.tabs.accounts_tab import _session_valid, _session_exists

            # ── Pre-flight: check whether the active account session is usable ──
            account_data = None
            try:
                account = self.db.get_current_account()
                if account:
                    account_data = {
                        "phone":    account.get("phone", ""),
                        "api_id":   account.get("api_id"),
                        "api_hash": account.get("api_hash", ""),
                        "name":     account.get("name", ""),
                    }
            except Exception as e:
                logger.debug("Could not read active account for session check: %s", e)

            if account_data:
                phone    = account_data["phone"]
                api_id   = account_data["api_id"]
                api_hash = account_data["api_hash"]

                needs_reauth = False
                if not _session_exists(phone, self.config):
                    logger.info("No session file found for %s — re-auth required", phone)
                    needs_reauth = True
                else:
                    logger.info("Validating existing session for %s...", phone)
                    try:
                        valid = _session_valid(phone, int(api_id), api_hash, self.config)
                    except Exception:
                        valid = False
                    if not valid:
                        logger.warning("Session for %s is invalid or expired — re-auth required", phone)
                        needs_reauth = True
                    else:
                        logger.info("Session for %s is valid", phone)

                if needs_reauth:
                    # Ask the GUI thread to show the re-auth dialog, then wait
                    self._auth_result_event.clear()
                    self._auth_success = False
                    self._reauth_needed.emit(account_data)
                    self._auth_result_event.wait(timeout=300)  # 5-min guard against hang

                    if not self._auth_success:
                        logger.error("Re-authentication cancelled or failed — bot will not start")
                        return

                    logger.info("Re-authentication successful — starting bot")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            def show_warning(message: str):
                logger.warning(f"API Warning: {message}")

            from src.bot_server import run_bot_async

            logger.info("Starting message listener...")
            try:
                loop.run_until_complete(
                    run_bot_async(
                        self.db, self.config,
                        verify_only=False,
                        warning_callback=show_warning,
                        stop_event=self.stop_event,
                        pause_flag=lambda: self.bot_paused,
                    )
                )
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"Error in bot thread: {e}", exc_info=True)

        finally:
            clean = self.stop_event.is_set()
            if clean:
                logger.info("Bot stopped by user")
            else:
                logger.warning("Bot stopped unexpectedly")
            self._bot_stopped_signal.emit(clean)

    def toggle_pause(self):
        if not self.bot_running:
            return
        self.bot_paused = not self.bot_paused
        if self.bot_paused:
            self.pause_btn.setText("▶ Resume Bot")
            self.status_label.setText("Status: ⏸ Paused")
            logger.info("Bot paused, staying connected but not replying")
        else:
            self.pause_btn.setText("⏸ Pause Bot")
            self.status_label.setText("Status: 🟢 Running")
            logger.info("Bot resumed")

    def stop_bot(self):
        if not self.bot_running:
            return

        try:
            self.log_display.appendPlainText("[Bot Stopping...]")
            self.stop_event.set()
            self.stop_btn.setEnabled(False)
            logger.info("Stop bot requested")
            # UI reset is handled by _on_bot_stopped once the thread exits

        except Exception as e:
            logger.error(f"Error stopping bot: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error stopping bot: {e}")


class LogCaptureHandler(logging.Handler):
    """Routes log records to the GUI via a Qt signal (thread-safe)."""

    def __init__(self, signal: pyqtSignal):
        super().__init__()
        self._signal = signal

    def emit(self, record):
        try:
            msg = self.format(record)
            self._signal.emit(msg)
        except Exception:
            self.handleError(record)
