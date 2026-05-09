"""
Telegram Accounts Tab
Manage profiles for Telegram accounts
"""

import asyncio
import pathlib
import threading
import webbrowser

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QDialog, QLineEdit, QCheckBox, QFormLayout,
    QMessageBox, QAbstractItemView, QMenu, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from src.database import DatabaseManager
from src.config import ConfigManager


def _session_name(phone: str) -> str:
    """Derive a unique Pyrogram session name from a phone number."""
    digits = "".join(c for c in phone if c.isdigit())
    return f"session_{digits}" if digits else "telegram_bot"


def _session_exists(phone: str, config: ConfigManager) -> bool:
    """Return True if a session file already exists for this phone number."""
    path = pathlib.Path(config.database.session_dir) / f"{_session_name(phone)}.session"
    return path.exists()


def _delete_session(phone: str, config: ConfigManager) -> None:
    """Delete the session file for a phone number if it exists."""
    path = pathlib.Path(config.database.session_dir) / f"{_session_name(phone)}.session"
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _session_valid(phone: str, api_id: int, api_hash: str, config: ConfigManager) -> bool:
    """
    Return True only if the existing session file can actually connect and
    authenticate.  Runs a quick connect + get_me check in a temporary event
    loop.  If any error occurs (auth revoked, file corrupt, etc.) returns False.
    """
    if not _session_exists(phone, config):
        return False

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    from pyrogram import Client

    async def _check():
        client = Client(
            name=_session_name(phone),
            api_id=api_id,
            api_hash=api_hash,
            phone_number=phone,
            workdir=config.database.session_dir,
        )
        try:
            await client.connect()
            await client.get_me()
            return True
        except Exception:
            return False
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    try:
        return loop.run_until_complete(_check())
    except Exception:
        return False
    finally:
        try:
            loop.close()
        except Exception:
            pass


class TelegramAuthDialog(QDialog):
    """
    Handles the Telegram login flow for a newly added account.

    Runs the Pyrogram authentication steps in a background thread and
    communicates back to the UI via Qt signals so dialogs are always
    shown on the main thread.
    """

    _status_signal = pyqtSignal(str)
    _code_needed_signal = pyqtSignal()
    _password_needed_signal = pyqtSignal()
    _done_signal = pyqtSignal(bool, str)

    def __init__(self, parent=None, account_data: dict = None, session_workdir: str = "."):
        super().__init__(parent)
        self.account_data = account_data or {}
        self._session_workdir = session_workdir
        self._cancelled = False
        self._auth_failed = False
        self._code_event = threading.Event()
        self._password_event = threading.Event()
        self._code_value: list = [None]
        self._password_value: list = [None]

        self.setWindowTitle("Telegram Login")
        self.setModal(True)
        self.setFixedSize(420, 200)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout()

        self._status_label = QLabel("Connecting to Telegram...")
        layout.addWidget(self._status_label)

        self._code_input = QLineEdit()
        self._code_input.setPlaceholderText("Enter the code Telegram sent to your phone")
        self._code_input.setEnabled(False)
        self._code_input.returnPressed.connect(self._on_submit)
        layout.addWidget(self._code_input)

        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("Enter your 2FA password")
        self._password_input.setEchoMode(QLineEdit.Password)
        self._password_input.setEnabled(False)
        self._password_input.setVisible(False)
        self._password_input.returnPressed.connect(self._on_submit)
        layout.addWidget(self._password_input)

        btn_row = QHBoxLayout()
        self._submit_btn = QPushButton("Submit")
        self._submit_btn.setEnabled(False)
        self._submit_btn.clicked.connect(self._on_submit)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._submit_btn)
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _connect_signals(self):
        self._status_signal.connect(self._status_label.setText)
        self._code_needed_signal.connect(self._show_code_input)
        self._password_needed_signal.connect(self._show_password_input)
        self._done_signal.connect(self._on_done)

    def _show_code_input(self):
        self._code_input.setEnabled(True)
        self._code_input.setFocus()
        self._submit_btn.setEnabled(True)
        self._submit_btn.setText("Submit Code")

    def _show_password_input(self):
        self._code_input.setVisible(False)
        self._password_input.setVisible(True)
        self._password_input.setEnabled(True)
        self._password_input.setFocus()
        self._submit_btn.setEnabled(True)
        self._submit_btn.setText("Submit Password")
        self._cancel_btn.setText("Skip (login later)")

    def _on_submit(self):
        if self._password_input.isEnabled():
            password = self._password_input.text().strip()
            if not password:
                # Keep dialog open — user must enter a password or click Cancel
                self._password_input.setFocus()
                return
            self._password_value[0] = password
            self._submit_btn.setEnabled(False)
            self._password_event.set()
        else:
            code = self._code_input.text().strip()
            if not code:
                self._code_input.setFocus()
                return
            self._code_value[0] = code
            self._submit_btn.setEnabled(False)
            self._code_event.set()

    def reject(self):
        self._cancelled = True
        self._code_event.set()
        self._password_event.set()
        super().reject()

    def _on_done(self, success: bool, message: str):
        if success:
            QMessageBox.information(self, "Success", message)
            self.accept()
        else:
            self._auth_failed = True
            if not self._cancelled and message:
                QMessageBox.critical(self, "Login Failed", message)
            # Call super().reject() directly so _cancelled stays False for auth failures
            super().reject()

    def start_auth(self):
        threading.Thread(target=self._run_auth, daemon=True).start()

    def _run_auth(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._auth_async())
        except Exception as e:
            self._done_signal.emit(False, str(e))
        finally:
            loop.close()

    async def _auth_async(self):
        from pyrogram import Client
        from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired

        phone = self.account_data.get("phone", "")
        api_id = self.account_data.get("api_id")
        api_hash = self.account_data.get("api_hash", "")
        name = _session_name(phone)

        client = Client(
            name=name,
            api_id=int(api_id),
            api_hash=api_hash,
            phone_number=phone,
            workdir=self._session_workdir,
        )

        try:
            self._status_signal.emit("Sending code to your Telegram app...")
            await client.connect()
            sent = await client.send_code(phone)

            self._status_signal.emit("Code sent. Check your Telegram app and enter it below.")
            self._code_needed_signal.emit()

            if not self._code_event.wait(timeout=120) or self._cancelled:
                self._done_signal.emit(False, "Cancelled")
                return

            code = self._code_value[0]
            if not code:
                self._done_signal.emit(False, "Cancelled")
                return

            self._status_signal.emit("Verifying...")

            try:
                await client.sign_in(phone, sent.phone_code_hash, code)
            except PhoneCodeInvalid:
                self._done_signal.emit(False, "Incorrect code. Please try again.")
                return
            except PhoneCodeExpired:
                self._done_signal.emit(False, "Code expired. Delete this account entry and add it again to get a new code.")
                return
            except SessionPasswordNeeded:
                self._status_signal.emit("2FA enabled. Enter your password below.")
                self._password_needed_signal.emit()

                if not self._password_event.wait(timeout=120) or self._cancelled:
                    self._done_signal.emit(False, "Cancelled")
                    return

                password = self._password_value[0]
                if not password:
                    self._done_signal.emit(False, "Cancelled")
                    return

                self._status_signal.emit("Verifying password...")
                await client.check_password(password)

            self._done_signal.emit(True, "Account logged in and ready.")

        finally:
            try:
                await client.disconnect()
            except Exception:
                pass


class AccountFormDialog(QDialog):
    """Dialog for adding/editing Telegram accounts"""
    
    def __init__(self, parent=None, db=None, account_data=None):
        super().__init__(parent)
        self.db = db
        self.account_data = account_data
        self.is_edit = account_data is not None
        
        self.setWindowTitle("Edit Account" if self.is_edit else "Add New Account")
        self.setModal(True)
        self.setGeometry(200, 200, 500, 350)
        
        self._setup_ui()
        
        if self.is_edit:
            self._load_account_data()
    
    def _setup_ui(self):
        """Setup form UI"""
        layout = QFormLayout()

        # Account Name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Personal, Work, Bot Testing")
        layout.addRow("Account Name *", self.name_input)

        # API ID + link button
        api_id_row = QHBoxLayout()
        self.api_id_input = QLineEdit()
        self.api_id_input.setPlaceholderText("e.g., 12345678")
        api_id_row.addWidget(self.api_id_input)
        get_creds_btn = QPushButton("Get credentials")
        get_creds_btn.setFixedWidth(110)
        get_creds_btn.clicked.connect(
            lambda: webbrowser.open("https://my.telegram.org/apps")
        )
        api_id_row.addWidget(get_creds_btn)
        layout.addRow("API ID *", api_id_row)

        # API Hash
        self.api_hash_input = QLineEdit()
        self.api_hash_input.setPlaceholderText("e.g., a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4")
        layout.addRow("API Hash *", self.api_hash_input)

        # Phone
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("+1234567890")
        layout.addRow("Phone Number *", self.phone_input)

        # Set as active (only for add mode)
        if not self.is_edit:
            self.active_checkbox = QCheckBox("Set as active account")
            self.active_checkbox.setChecked(True)
            layout.addRow("", self.active_checkbox)
        
        # Buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        clear_btn = QPushButton("Clear")
        
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)
        clear_btn.clicked.connect(self._clear_fields)
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(clear_btn)
        layout.addRow("", button_layout)
        
        self.setLayout(layout)
    
    def _load_account_data(self):
        """Load existing account data into form"""
        if self.account_data:
            self.name_input.setText(self.account_data.get('name', ''))
            self.api_id_input.setText(str(self.account_data.get('api_id', '') or ''))
            self.api_hash_input.setText(self.account_data.get('api_hash', '') or '')
            self.phone_input.setText(self.account_data.get('phone', ''))

    def _clear_fields(self):
        """Clear all form fields"""
        self.name_input.clear()
        self.api_id_input.clear()
        self.api_hash_input.clear()
        self.phone_input.clear()
    
    def _validate_inputs(self) -> bool:
        """Validate form inputs"""
        import re
        name = self.name_input.text().strip()
        phone = self.phone_input.text().strip()

        # Check required fields
        if not name:
            QMessageBox.warning(self, "Validation Error", "Account name is required")
            return False

        if len(name) < 2 or len(name) > 50:
            QMessageBox.warning(self, "Validation Error", "Account name must be 2-50 characters")
            return False

        api_id = self.api_id_input.text().strip()
        if not api_id or not api_id.isdigit():
            QMessageBox.warning(self, "Validation Error", "API ID must be a number (from my.telegram.org/apps)")
            return False

        api_hash = self.api_hash_input.text().strip()
        if not api_hash or len(api_hash) < 10:
            QMessageBox.warning(self, "Validation Error", "API Hash is required (from my.telegram.org/apps)")
            return False

        if not phone:
            QMessageBox.warning(self, "Validation Error", "Phone number is required")
            return False
        
        # Validate phone format
        if not re.match(r'^\+?\d{10,15}$', phone.replace(' ', '').replace('-', '')):
            QMessageBox.warning(self, "Validation Error", "Invalid phone format")
            return False
        
        return True
    
    def _save(self):
        """Save account to database"""
        if not self._validate_inputs():
            return
        
        try:
            name = self.name_input.text().strip()
            api_id = int(self.api_id_input.text().strip())
            api_hash = self.api_hash_input.text().strip()
            phone = self.phone_input.text().strip()

            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                if self.is_edit and self.account_data:
                    cursor.execute(
                        """UPDATE accounts
                           SET name = ?, api_id = ?, api_hash = ?, phone = ?,
                               updated_at = datetime('now')
                           WHERE id = ?""",
                        (name, api_id, api_hash, phone, self.account_data['id'])
                    )
                else:
                    cursor.execute("SELECT id FROM accounts WHERE phone = ?", (phone,))
                    if cursor.fetchone():
                        QMessageBox.warning(self, "Duplicate", "An account with this phone already exists")
                        return

                    cursor.execute("SELECT id FROM accounts WHERE name = ?", (name,))
                    if cursor.fetchone():
                        QMessageBox.warning(self, "Duplicate", "An account with this name already exists")
                        return

                    is_active = self.active_checkbox.isChecked() if not self.is_edit else False
                    if is_active:
                        cursor.execute(
                            "UPDATE accounts SET is_active = 0 WHERE account_type = 'telegram'"
                        )
                    cursor.execute(
                        """INSERT INTO accounts
                               (account_type, name, api_id, api_hash, phone, is_active, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                        ('telegram', name, api_id, api_hash, phone, is_active)
                    )
            
            QMessageBox.information(self, "Success", "Account saved successfully")
            self.accept()
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save account: {e}")
    
    def get_account_data(self):
        """Return account data including credentials needed for auth."""
        return {
            'name': self.name_input.text().strip(),
            'phone': self.phone_input.text().strip(),
            'api_id': self.api_id_input.text().strip(),
            'api_hash': self.api_hash_input.text().strip(),
        }


class TelegramAccountsTab(QWidget):
    """Tab for managing Telegram accounts"""
    
    def __init__(self, db: DatabaseManager, config: ConfigManager):
        super().__init__()
        self.db = db
        self.config = config
        self._setup_ui()
        self.load_accounts()
    
    def _setup_ui(self):
        """Setup UI components"""
        layout = QVBoxLayout()
        
        # Current Account Section
        current_group = QGroupBox("Current Account")
        current_layout = QVBoxLayout()
        
        self.current_name_label = QLabel("Account: ---")
        self.current_phone_label = QLabel("Phone: ---")
        self.current_status_label = QLabel("Status: Not Set")
        self.current_status_label.setStyleSheet("color: #FF9900;")
        
        current_layout.addWidget(self.current_name_label)
        current_layout.addWidget(self.current_phone_label)
        current_layout.addWidget(self.current_status_label)
        
        button_layout = QHBoxLayout()
        edit_btn = QPushButton("Edit")
        view_pwd_btn = QPushButton("View Details")
        edit_btn.clicked.connect(self._edit_current_account)
        view_pwd_btn.clicked.connect(self._view_password)
        button_layout.addWidget(edit_btn)
        button_layout.addWidget(view_pwd_btn)
        button_layout.addStretch()
        current_layout.addLayout(button_layout)
        
        current_group.setLayout(current_layout)
        layout.addWidget(current_group)
        
        # Accounts Table
        table_group = QGroupBox("All Saved Accounts")
        table_layout = QVBoxLayout()
        
        # Search bar
        search_layout = QHBoxLayout()
        search_label = QLabel("Search by name or phone:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to filter accounts...")
        self.search_input.textChanged.connect(self._filter_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        table_layout.addLayout(search_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["", "Name", "Phone", "Status", "Session", "Created", "Actions"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setColumnWidth(0, 30)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 120)
        self.table.setColumnWidth(6, 220)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemClicked.connect(self._on_table_clicked)

        table_layout.addWidget(self.table)
        table_group.setLayout(table_layout)
        layout.addWidget(table_group)
        
        # Add button
        add_btn = QPushButton("+ Add New Account")
        add_btn.clicked.connect(self._add_account)
        layout.addWidget(add_btn)
        
        self.setLayout(layout)
    
    def load_accounts(self):
        """Load accounts from database"""
        try:
            # Clear search filter
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, name, phone, is_active, created_at FROM accounts 
                       WHERE account_type = 'telegram'
                       ORDER BY created_at DESC"""
                )
                accounts = cursor.fetchall()
                
                # Update current account
                cursor.execute(
                    """SELECT name, phone FROM accounts 
                       WHERE account_type = 'telegram' AND is_active = 1 LIMIT 1"""
                )
                current = cursor.fetchone()
            
            if current:
                self.current_name_label.setText(f"Account: {current[0]}")
                self.current_phone_label.setText(f"Phone: {current[1]}")
                self.current_status_label.setText("Status: [OK] Active")
                self.current_status_label.setStyleSheet("color: #009900;")
            else:
                self.current_name_label.setText("Account: ---")
                self.current_phone_label.setText("Phone: ---")
                self.current_status_label.setText("Status: Not Set")
                self.current_status_label.setStyleSheet("color: #FF9900;")
            
            # Populate table
            self.table.setRowCount(len(accounts))
            for row, (acc_id, name, phone, is_active, created_at) in enumerate(accounts):
                # Radio button
                radio_item = QTableWidgetItem("●" if is_active else "○")
                radio_item.setData(Qt.UserRole, acc_id)
                radio_item.setTextAlignment(Qt.AlignCenter)
                
                # Name
                name_item = QTableWidgetItem(name)
                
                # Phone
                phone_item = QTableWidgetItem(phone)
                
                # Status
                status_item = QTableWidgetItem("Active" if is_active else "Inactive")
                status_item.setData(Qt.UserRole, acc_id)
                
                # Created
                created_item = QTableWidgetItem(created_at)
                
                # Session status
                has_session = _session_exists(phone, self.config)
                session_text = "Ready" if has_session else "Not logged in"
                session_item = QTableWidgetItem(session_text)
                session_item.setForeground(QColor("#009900") if has_session else QColor("#CC0000"))
                session_item.setTextAlignment(Qt.AlignCenter)

                # Actions buttons
                actions_widget = QWidget()
                actions_layout = QHBoxLayout()

                edit_btn = QPushButton("Edit")
                delete_btn = QPushButton("Delete")
                relogin_btn = QPushButton("Re-login")
                relogin_btn.setToolTip("Clear session and run full login / 2FA flow again")
                edit_btn.clicked.connect(lambda checked, aid=acc_id: self._edit_account(aid))
                delete_btn.clicked.connect(lambda checked, aid=acc_id: self._delete_account(aid))
                relogin_btn.clicked.connect(lambda checked, aid=acc_id: self._relogin_account(aid))

                actions_layout.addWidget(edit_btn)
                actions_layout.addWidget(relogin_btn)
                actions_layout.addWidget(delete_btn)
                actions_layout.setContentsMargins(0, 0, 0, 0)
                actions_widget.setLayout(actions_layout)

                # Add to table
                self.table.setItem(row, 0, radio_item)
                self.table.setItem(row, 1, name_item)
                self.table.setItem(row, 2, phone_item)
                self.table.setItem(row, 3, status_item)
                self.table.setItem(row, 4, session_item)
                self.table.setItem(row, 5, created_item)
                self.table.setCellWidget(row, 6, actions_widget)

                # Highlight active row
                if is_active:
                    for col in range(6):
                        item = self.table.item(row, col)
                        if item:
                            item.setBackground(QColor("#E3F2FD"))
                
                # Make radio clickable
                radio_item.setText("●" if is_active else "○")

        except Exception as e:
            print(f"Error loading accounts: {e}")
    
    def _on_table_clicked(self, item):
        """Handle table item click - for radio button selection"""
        if item.column() == 0:  # Radio column
            row = item.row()
            self._on_radio_clicked(row)
    
    def _on_radio_clicked(self, row: int):
        """Handle radio button click"""
        acc_id = self.table.item(row, 0).data(Qt.UserRole)
        self._set_account_active(acc_id)
    
    def _set_account_active(self, account_id: int):
        """Set account as active"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE accounts SET is_active = 0 WHERE account_type = 'telegram'")
                cursor.execute("UPDATE accounts SET is_active = 1 WHERE id = ?", (account_id,))
            self.load_accounts()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to set active account: {e}")
    
    def _filter_table(self, search_text: str):
        """Filter table rows by search text (name or phone)"""
        search_text = search_text.lower().strip()

        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 1)
            phone_item = self.table.item(row, 2)

            if name_item and phone_item:
                name = name_item.text().lower()
                phone = phone_item.text().lower()
                if search_text in name or search_text in phone:
                    self.table.showRow(row)
                else:
                    self.table.hideRow(row)
            else:
                self.table.showRow(row)
    
    def _add_account(self):
        """Add new account, then immediately run the Telegram login flow."""
        dialog = AccountFormDialog(self, self.db)
        if dialog.exec_() == QDialog.Accepted:
            account_data = dialog.get_account_data()
            phone = account_data.get("phone", "")
            api_id = account_data.get("api_id")
            api_hash = account_data.get("api_hash", "")

            if phone:
                # Check whether the existing session (if any) is actually valid.
                # If the file exists but is stale/revoked, delete it and re-run login.
                needs_login = True
                if _session_exists(phone, self.config):
                    try:
                        valid = _session_valid(phone, int(api_id), api_hash, self.config)
                    except Exception:
                        valid = False
                    if valid:
                        needs_login = False
                    else:
                        _delete_session(phone, self.config)

                if needs_login:
                    auth_dialog = TelegramAuthDialog(
                        self, account_data, session_workdir=self.config.database.session_dir
                    )
                    auth_dialog.start_auth()
                    auth_dialog.exec_()

            self.load_accounts()
    
    def _edit_account(self, account_id: int):
        """Edit existing account"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, name, api_id, api_hash, phone, password FROM accounts WHERE id = ?",
                    (account_id,)
                )
                row = cursor.fetchone()

            if row:
                account_data = {
                    'id': row[0],
                    'name': row[1],
                    'api_id': row[2],
                    'api_hash': row[3],
                    'phone': row[4],
                    'password': row[5],
                }
                dialog = AccountFormDialog(self, self.db, account_data)
                if dialog.exec_() == QDialog.Accepted:
                    self.load_accounts()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to edit account: {e}")
    
    def _relogin_account(self, account_id: int):
        """Force a fresh Telegram login for this account, clearing any existing session."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, name, api_id, api_hash, phone FROM accounts WHERE id = ?",
                    (account_id,)
                )
                row = cursor.fetchone()

            if not row:
                QMessageBox.warning(self, "Not Found", "Account not found.")
                return

            account_data = {
                'id': row[0],
                'name': row[1],
                'api_id': row[2],
                'api_hash': row[3],
                'phone': row[4],
            }
            phone = account_data["phone"]

            reply = QMessageBox.question(
                self,
                "Re-login",
                f"This will clear the existing session for {phone} and ask Telegram to send a new "
                "verification code.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            _delete_session(phone, self.config)

            auth_dialog = TelegramAuthDialog(
                self, account_data, session_workdir=self.config.database.session_dir
            )
            auth_dialog.start_auth()
            auth_dialog.exec_()
            self.load_accounts()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to re-login: {e}")

    def _delete_account(self, account_id: int):
        """Delete account and all related data (cascade delete)."""
        reply = QMessageBox.question(
            self, 
            "Confirm Delete", 
            "Delete this account and ALL associated data?\n\n"
            "This will permanently delete:\n"
            "• All conversations for this account\n"
            "• All messages in those conversations\n"
            "• All API keys for this account\n"
            "• All audit logs for this account\n\n"
            "This action CANNOT be undone!",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()

                    # Fetch phone so we can delete the session file after DB cleanup
                    cursor.execute(
                        "SELECT phone FROM accounts WHERE id = ?", (account_id,)
                    )
                    phone_row = cursor.fetchone()
                    account_phone = phone_row[0] if phone_row else None

                    # Get all conversation IDs for this account (for cascade delete)
                    cursor.execute(
                        "SELECT id FROM conversations WHERE account_id = ?",
                        (account_id,)
                    )
                    conversation_ids = [row[0] for row in cursor.fetchall()]
                    
                    # Delete messages for all conversations of this account
                    if conversation_ids:
                        placeholders = ','.join('?' * len(conversation_ids))
                        cursor.execute(
                            f"DELETE FROM messages WHERE conversation_id IN ({placeholders})",
                            conversation_ids
                        )
                    
                    # Delete conversations for this account
                    cursor.execute(
                        "DELETE FROM conversations WHERE account_id = ?",
                        (account_id,)
                    )
                    
                    # Delete API keys for this account
                    cursor.execute(
                        "DELETE FROM api_keys WHERE account_id = ?",
                        (account_id,)
                    )
                    
                    # Delete audit log entries for this account
                    cursor.execute(
                        "DELETE FROM audit_log WHERE affected_accounts = ?",
                        (account_id,)
                    )
                    
                    # Finally delete the account itself
                    cursor.execute(
                        "DELETE FROM accounts WHERE id = ?",
                        (account_id,)
                    )
                    
                    conn.commit()

                # Remove the session file so re-adding the same phone triggers fresh login
                if account_phone:
                    _delete_session(account_phone, self.config)

                QMessageBox.information(
                    self,
                    "Success",
                    "Account and all associated data deleted successfully."
                )
                self.load_accounts()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete account: {e}")
    
    def _edit_current_account(self):
        """Edit current account"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, phone, password FROM accounts WHERE is_active = 1 LIMIT 1"
                )
                row = cursor.fetchone()
            
            if row:
                self._edit_account(row[0])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to get current account: {e}")
    
    def _view_password(self):
        """View account password"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name, phone, password FROM accounts WHERE is_active = 1 LIMIT 1")
                row = cursor.fetchone()
            
            if row:
                name, phone, password = row
                msg = f"""
Telegram Account Info:

Account: {name}
Phone: {phone}
2FA Password: {"Set" if password else "Not Set"}

⚠ This information is sensitive. Don't share!
                """
                QMessageBox.information(self, "Account Details", msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to get account details: {e}")
    
    def _show_context_menu(self, position):
        """Show right-click context menu"""
        item = self.table.itemAt(position)
        if not item:
            return
        
        menu = QMenu()
        # Add context menu options here
        menu.exec_(self.table.mapToGlobal(position))
