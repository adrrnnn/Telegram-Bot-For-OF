"""
Main GUI Window for Telegram Bot Manager
"""

import logging
import pathlib
import threading
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget,
    QLabel, QStatusBar, QStackedWidget, QMessageBox, QProgressBar, QDialog,
)
from PyQt5.QtCore import Qt, QTimer, QDateTime, QObject, pyqtSignal, pyqtSlot, QMetaObject
from PyQt5.QtGui import QFont, QIcon

from src.database import DatabaseManager
from src.config import ConfigManager
from src.runtime_paths import BUNDLE_DIR

logger = logging.getLogger(__name__)

_LOGO_PATH = BUNDLE_DIR / "assets" / "logo.png"


class VerificationInvoker(QObject):
    """Shows the code / password dialog on the GUI thread (Pyrogram calls from a worker thread)."""

    def __init__(self, main_window: "TelegramBotMainWindow"):
        super().__init__(main_window)
        self._main = main_window
        self._code_result: Optional[str] = None
        self._pending_prompt: str = ""

    @staticmethod
    def _is_password_prompt(prompt: str) -> bool:
        pl = (prompt or "").lower()
        return any(
            k in pl
            for k in (
                "password",
                "two-step",
                "two step",
                "2fa",
                "cloud password",
                "telegram password",
            )
        )

    @pyqtSlot()
    def _prompt(self):
        self._code_result = None
        if self._main._closing:
            return

        prompt = self._pending_prompt or ""

        if self._is_password_prompt(prompt):
            from src.ui.dialogs.verification_dialog import TwoFactorDialog

            dlg = TwoFactorDialog(parent=self._main)
            self._main._active_verification_dialog = dlg
            try:
                if dlg.exec_() == QDialog.Accepted:
                    self._code_result = dlg.get_password()
            finally:
                self._main._active_verification_dialog = None
            return

        from src.ui.dialogs.verification_dialog import VerificationCodeDialog

        dlg = VerificationCodeDialog(parent=self._main, telegram_prompt_excerpt=prompt[:200])
        self._main._active_verification_dialog = dlg
        try:
            if dlg.exec_() == QDialog.Accepted:
                self._code_result = dlg.get_code()
        finally:
            self._main._active_verification_dialog = None

    def prompt_blocking(self, prompt: str = "") -> Optional[str]:
        self._code_result = None
        self._pending_prompt = prompt or ""
        QMetaObject.invokeMethod(self, "_prompt", Qt.BlockingQueuedConnection)
        return self._code_result


class TelegramBotMainWindow(QMainWindow):
    """Main application window"""

    _api_warning_requested = pyqtSignal(str)
    _verification_complete = pyqtSignal(bool, str)
    _verification_status = pyqtSignal(str)

    SCREEN_VERIFICATION = 0
    SCREEN_MAIN = 1

    def __init__(self, db_manager: DatabaseManager, config_manager: ConfigManager):
        super().__init__()
        self.db = db_manager
        self.config = config_manager
        self._closing = False
        self._verification_thread: Optional[threading.Thread] = None
        self._active_verification_dialog = None

        self._verification_invoker = VerificationInvoker(self)
        self._api_warning_requested.connect(self._on_api_warning_requested)
        self._verification_complete.connect(self._on_verification_complete)
        self._verification_status.connect(self._on_verification_status)

        self.setWindowTitle("Telegram Bot Manager")
        self.setGeometry(100, 100, 1000, 700)
        self.setMinimumSize(800, 600)

        if _LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(_LOGO_PATH)))

        self._setup_ui()
        self._setup_status_bar()
        self._setup_timer()

        self._check_and_setup_account()

    def _setup_ui(self):
        """Initialize all UI components"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stacked_widget = QStackedWidget()

        verification_widget = QWidget()
        verification_layout = QVBoxLayout(verification_widget)
        verification_layout.setSpacing(20)
        verification_layout.setContentsMargins(40, 40, 40, 40)

        verification_layout.addStretch()

        title = QLabel("Verification Required")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        verification_layout.addWidget(title)

        self._verify_status_label = QLabel("Connecting to Telegram...")
        instructions_font = QFont()
        instructions_font.setPointSize(11)
        self._verify_status_label.setFont(instructions_font)
        self._verify_status_label.setAlignment(Qt.AlignCenter)
        self._verify_status_label.setWordWrap(True)
        self._verify_status_label.setStyleSheet("color: #444; line-height: 1.6;")
        verification_layout.addWidget(self._verify_status_label)

        progress = QProgressBar()
        progress.setMaximum(0)
        progress.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #f5f5f5;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #007AFF;
            }
        """
        )
        verification_layout.addWidget(progress)

        verification_layout.addStretch()

        self.verification_screen = verification_widget
        self.stacked_widget.addWidget(self.verification_screen)

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(self._get_tab_stylesheet())

        from src.ui.tabs.accounts_tab import TelegramAccountsTab
        from src.ui.tabs.profiles_tab import ModelProfilesTab
        from src.ui.tabs.link_tab import ChangeOFLinkTab
        from src.ui.tabs.start_bot_tab import StartBotTab
        from src.ui.tabs.settings_tab import SettingsTab

        self.accounts_tab = TelegramAccountsTab(self.db, self.config)
        self.profiles_tab = ModelProfilesTab(self.db, self.config)
        self.link_tab = ChangeOFLinkTab(self.db, self.config)
        self.start_bot_tab = StartBotTab(self.db, self.config)
        self.settings_tab = SettingsTab(self.db, self.config)

        self.tab_widget.addTab(self.accounts_tab, "Telegram Accounts")
        self.tab_widget.addTab(self.link_tab, "Change OF Link")
        self.tab_widget.addTab(self.profiles_tab, "Model Profiles")
        self.tab_widget.addTab(self.start_bot_tab, "Start Bot")
        self.tab_widget.addTab(self.settings_tab, "Settings")

        self.stacked_widget.addWidget(self.tab_widget)

        main_layout.addWidget(self.stacked_widget)
        central_widget.setLayout(main_layout)

    def _setup_status_bar(self):
        """Setup status bar at bottom"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.account_label = QLabel("Active Account: ---")
        self.account_label.setStyleSheet("color: #009900; margin-left: 10px;")
        self.status_bar.addWidget(self.account_label)

        self.time_label = QLabel("00:00:00")
        self.time_label.setStyleSheet("margin-right: 10px;")
        self.status_bar.addPermanentWidget(self.time_label)

        self._update_status_bar()

    def _setup_timer(self):
        """Setup timer for status bar updates"""
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_time)
        self.timer.start(1000)

    def _update_status_bar(self):
        """Update status bar with current info"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT phone FROM accounts WHERE account_type = 'telegram' AND is_active = 1 LIMIT 1"
                )
                result = cursor.fetchone()
            if result:
                phone = result[0]
                self.account_label.setText(f"Active Account: {phone}")
                self.account_label.setStyleSheet("color: #009900; margin-left: 10px;")
            else:
                self.account_label.setText("Active Account: None")
                self.account_label.setStyleSheet("color: #FF9900; margin-left: 10px;")
        except Exception:
            self.account_label.setText("Active Account: Error")

    def _update_time(self):
        """Update time in status bar"""
        current_time = QDateTime.currentDateTime().toString("hh:mm:ss")
        self.time_label.setText(current_time)

    def _get_tab_stylesheet(self) -> str:
        """Get CSS stylesheet for tabs"""
        return """
        QTabWidget::pane {
            border: 1px solid #E0E0E0;
        }
        QTabBar::tab {
            background-color: #f5f5f5;
            color: #212121;
            padding: 8px 16px;
            margin-right: 2px;
            border: 1px solid #E0E0E0;
            border-bottom: none;
        }
        QTabBar::tab:selected {
            background-color: #FFFFFF;
            color: #2196F3;
            border-bottom: 2px solid #2196F3;
        }
        QTabBar::tab:hover {
            background-color: #EEEEEE;
        }
        """

    def _on_api_warning_requested(self, message: str):
        QMessageBox.warning(self, "API Quota Exhausted", message)

    @pyqtSlot(str)
    def _on_verification_status(self, status: str):
        """Update the live status label on the verification screen."""
        try:
            self._verify_status_label.setText(status)
        except Exception:
            pass

    def _on_verification_complete(self, success: bool, err_msg: str):
        """Runs on the GUI thread after the verification worker finishes."""
        from src.bot_server import clear_verification_callback

        clear_verification_callback()
        if self._closing:
            return
        if success:
            logger.info("[GUI] Verification successful! Showing main screen...")
            self.show_main_screen()
            self.accounts_tab.load_accounts()
            self._update_status_bar()
        else:
            if err_msg:
                # A real error (wrong code, expired, network) — show it then re-check
                QMessageBox.critical(self, "Verification Error", err_msg)
                self._check_and_setup_account()
            else:
                # User cancelled (closed code or 2FA dialog) — account already saved,
                # just go straight to dashboard so they can Re-login from accounts tab
                logger.info("[GUI] Verification cancelled by user — going to dashboard")
                self.show_main_screen()
                self.accounts_tab.load_accounts()
                self._update_status_bar()

    def closeEvent(self, event):
        """Handle window close event"""
        self._closing = True

        from src.bot_server import clear_verification_callback

        clear_verification_callback()

        if self._active_verification_dialog is not None:
            try:
                self._active_verification_dialog.reject()
            except Exception as e:
                logger.debug("Closing verification dialog: %s", e)

        if self.start_bot_tab:
            try:
                self.start_bot_tab.stop_bot()
            except Exception as e:
                logger.debug(f"Error stopping bot on close: {e}")

        if self._verification_thread is not None and self._verification_thread.is_alive():
            self._verification_thread.join(timeout=8.0)

        clear_verification_callback()

        if self.timer:
            self.timer.stop()

        event.accept()

    def _check_and_setup_account(self):
        """Check if account exists, show setup dialog if not"""
        if self._closing:
            return
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM accounts WHERE account_type = 'telegram' LIMIT 1"
                )
                account_exists = cursor.fetchone() is not None

            if not account_exists:
                from src.ui.dialogs.setup_dialog import TelegramSetupDialog

                dialog = TelegramSetupDialog(self, self.db, self.config)
                if dialog.exec_():
                    self.show_verification_screen()
                    QTimer.singleShot(0, self._start_verification_thread)
                else:
                    logger.info("Initial setup cancelled — quitting application")
                    from PyQt5.QtWidgets import QApplication

                    QApplication.instance().quit()
            else:
                self.show_main_screen()

        except Exception as e:
            logger.exception("Error checking account: %s", e)
            self.show_main_screen()

    def _start_verification_thread(self):
        if self._closing:
            return
        if self._verification_thread is not None and self._verification_thread.is_alive():
            return
        self._verification_thread = threading.Thread(
            target=self._trigger_verification,
            name="telegram-verification",
            daemon=False,
        )
        self._verification_thread.start()

    def show_verification_screen(self):
        """Show the verification waiting screen"""
        self.stacked_widget.setCurrentIndex(self.SCREEN_VERIFICATION)

    def show_main_screen(self):
        """Show the main panel with tabs"""
        self.stacked_widget.setCurrentIndex(self.SCREEN_MAIN)

    def _trigger_verification(self):
        """
        Run Pyrogram verification in a worker thread using an explicit
        connect → send_code → dialog → sign_in flow so the user sees live
        status updates and the code dialog appears the instant the code is sent.
        """
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        from pyrogram import Client
        from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired
        from src.bot_server import clear_verification_callback

        class _Cancelled(Exception):
            pass

        async def run():
            # Resolve credentials (prefer active DB account over config fallback).
            t = self.config.telegram
            api_id = t.api_id
            api_hash = t.api_hash
            phone = t.phone_number
            try:
                account = self.db.get_current_account()
                if account:
                    if account.get("api_id"):
                        api_id = int(account["api_id"])
                    if account.get("api_hash"):
                        api_hash = account["api_hash"]
                    if account.get("phone"):
                        phone = account["phone"]
            except Exception as e:
                logger.debug("Could not read active account from DB: %s", e)

            phone_digits = "".join(c for c in (phone or "") if c.isdigit())
            session_name = f"session_{phone_digits}" if phone_digits else "telegram_bot"
            sessions_dir = pathlib.Path(self.config.database.session_dir)

            client = Client(
                name=session_name,
                api_id=api_id,
                api_hash=api_hash,
                phone_number=phone,
                workdir=str(sessions_dir),
            )

            try:
                self._verification_status.emit("Connecting to Telegram...")
                logger.info("[GUI] Connecting to Telegram servers...")
                await client.connect()

                self._verification_status.emit(
                    "Sending verification code to your Telegram app..."
                )
                logger.info("[GUI] Requesting verification code...")
                sent = await client.send_code(phone)

                self._verification_status.emit(
                    "Code sent. A dialog will appear — enter the code from your Telegram app."
                )
                logger.info("[GUI] Code sent, waiting for user to enter it...")

                code = await loop.run_in_executor(
                    None,
                    lambda: self._verification_invoker.prompt_blocking(
                        "Enter the verification code sent to your Telegram app:"
                    ),
                )

                if self._closing or not code:
                    raise _Cancelled()

                self._verification_status.emit("Verifying code...")
                logger.info("[GUI] Verifying code...")

                try:
                    await client.sign_in(phone, sent.phone_code_hash, code)
                except SessionPasswordNeeded:
                    self._verification_status.emit(
                        "2FA enabled. A password dialog will appear — enter your cloud password."
                    )
                    logger.info("[GUI] 2FA required, waiting for password...")

                    password = await loop.run_in_executor(
                        None,
                        lambda: self._verification_invoker.prompt_blocking(
                            "Two-step verification (2FA) is enabled. "
                            "Enter your Telegram cloud password:"
                        ),
                    )

                    if self._closing or not password:
                        raise _Cancelled()

                    self._verification_status.emit("Verifying 2FA password...")
                    await client.check_password(password)

                return True

            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

        try:
            logger.info("[GUI] Starting verification process...")
            result = loop.run_until_complete(asyncio.wait_for(run(), timeout=240.0))
            if not self._closing:
                self._verification_complete.emit(bool(result), "")

        except asyncio.TimeoutError:
            logger.error("[GUI] Telegram verification timed out after 240s")
            if not self._closing:
                self._verification_complete.emit(
                    False,
                    "Verification timed out after 240 seconds. "
                    "Check your internet connection and try again.",
                )

        except PhoneCodeInvalid:
            logger.warning("[GUI] Incorrect verification code entered")
            if not self._closing:
                self._verification_complete.emit(
                    False,
                    "Incorrect verification code. Please close and try again.",
                )

        except PhoneCodeExpired:
            logger.warning("[GUI] Verification code expired")
            if not self._closing:
                self._verification_complete.emit(
                    False,
                    "The verification code expired. Please close and try again "
                    "to request a new code.",
                )

        except Exception as e:
            # _Cancelled or any unexpected error
            if not isinstance(e, (KeyboardInterrupt, SystemExit)):
                logger.error("[GUI] Verification error: %s", e, exc_info=True)
            if not self._closing:
                msg = "" if e.__class__.__name__ == "_Cancelled" else f"Verification error: {e}"
                self._verification_complete.emit(False, msg)

        finally:
            try:
                loop.close()
            except Exception:
                pass
            clear_verification_callback()
